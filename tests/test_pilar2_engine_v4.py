from types import SimpleNamespace

from auditor_bola.config import ChequeoPilar2, ConfigObjetivo
from auditor_bola.pilar2 import auditar_pilar2
from auditor_bola.pilar2_discovery import discover_pilar2_profile
from auditor_bola.runner import diagnosticar
from auditor_bola.security_model import consolidate_runtime_results


def _cfg(checks, *, base_url="http://127.0.0.1:5050", candidates=None):
    return ConfigObjetivo(
        sistema="generic-app",
        base_url=base_url,
        cuentas=[],
        endpoints=[],
        chequeos_pilar2=checks,
        candidatos_pilar2=list(candidates or []),
    )


def test_secret_fallback_desplegable_genera_control_sin_exponer_valor(tmp_path):
    (tmp_path / "settings.py").write_text(
        'import os\nSECRET_KEY = os.getenv("APP_SECRET", "development-secret")\n',
        encoding="utf-8",
    )

    discovery = discover_pilar2_profile(tmp_path, [])

    controls = [
        item for item in discovery["checks"]
        if item.get("familia") == "SECRET"
    ]
    candidates = [
        item for item in discovery["candidates"]
        if item.get("familia") == "SECRET"
    ]

    assert controls
    assert candidates
    metadata = controls[0]["metadata"]
    assert metadata["valor_fallback_redactado"] != "development-secret"
    assert metadata["fallback_sha256"]
    serialized = repr(controls[0]) + repr(candidates[0])
    assert "development-secret" not in serialized


def test_secret_en_documentacion_permanece_candidato_no_hallazgo(tmp_path):
    (tmp_path / "README.md").write_text(
        'Ejemplo: SECRET_KEY = os.getenv("APP_SECRET", "development-secret")\n',
        encoding="utf-8",
    )

    discovery = discover_pilar2_profile(tmp_path, [])

    assert not [
        item for item in discovery["checks"]
        if item.get("familia") == "SECRET"
    ]
    secret_candidates = [
        item for item in discovery["candidates"]
        if item.get("familia") == "SECRET"
    ]
    assert secret_candidates
    evidence = secret_candidates[0]["evidencia"][0]
    assert evidence["tipo_fuente"] == "documentacion"
    assert secret_candidates[0]["estado"] == "candidato"


def test_docker_multistage_evalua_solo_runtime_final(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12 AS builder\n"
        "USER root\n"
        "RUN echo build\n"
        "FROM python:3.12-slim AS runtime\n"
        "RUN useradd -m appuser\n"
        "USER appuser\n"
        "CMD [\"python\", \"app.py\"]\n",
        encoding="utf-8",
    )
    check = ChequeoPilar2(
        id_control="P2-CONTAINER-MULTISTAGE",
        nombre="runtime non-root",
        tipo="container_security",
        familia="CONTAINER",
        archivo="Dockerfile",
    )

    result = auditar_pilar2(_cfg([check]), tmp_path)[0]

    assert result.estado == "SIN_HALLAZGO"
    assert result.vulnerable is False
    assert result.configuracion_detectada["usuario_efectivo"] == "appuser"
    assert len(result.configuracion_detectada["dockerfile"]["stages"]) == 2


def test_docker_sin_user_es_por_confirmar_no_vulnerabilidad_confirmada(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nCMD [\"python\", \"app.py\"]\n",
        encoding="utf-8",
    )
    check = ChequeoPilar2(
        id_control="P2-CONTAINER-NO-USER",
        nombre="runtime user",
        tipo="container_security",
        familia="CONTAINER",
        archivo="Dockerfile",
    )

    result = auditar_pilar2(_cfg([check]), tmp_path)[0]

    assert result.estado == "POR_CONFIRMAR"
    assert result.estado_control == "por_confirmar"
    assert result.vulnerable is False
    assert result.confianza == "media"


def test_compose_root_o_privileged_confirma_hallazgo(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nUSER appuser\n",
        encoding="utf-8",
    )
    (tmp_path / "compose.yaml").write_text(
        "services:\n"
        "  api:\n"
        "    build: .\n"
        '    user: "0"\n'
        "    privileged: true\n",
        encoding="utf-8",
    )
    check = ChequeoPilar2(
        id_control="P2-CONTAINER-RUNTIME",
        nombre="runtime privileges",
        tipo="container_security",
        familia="CONTAINER",
        archivo="Dockerfile",
    )

    result = auditar_pilar2(_cfg([check]), tmp_path)[0]

    assert result.estado == "HALLAZGO"
    assert result.vulnerable is True
    assert result.confianza == "alta"
    assert result.configuracion_detectada["usuario_efectivo"] == "0"
    assert result.configuracion_detectada["configuraciones_peligrosas"]


def test_limit_estatico_crea_candidato_y_no_hallazgo_automatico(tmp_path):
    (tmp_path / "api.py").write_text(
        "def create_task(request):\n"
        "    urgent = request.json.get('urgent', False)\n"
        "    max_size = 10\n"
        "    if urgent:\n"
        "        max_size = 1000\n"
        "    payload = request.json.get('payload', '')\n"
        "    return len(payload) <= max_size\n",
        encoding="utf-8",
    )
    endpoints = [
        {
            "metodo": "POST",
            "ruta": "/tasks",
            "archivos": ["api.py"],
        }
    ]

    discovery = discover_pilar2_profile(tmp_path, endpoints)

    limit_candidates = [
        item for item in discovery["candidates"]
        if item.get("familia") == "LIMIT_BYPASS"
    ]
    assert limit_candidates
    assert limit_candidates[0]["estado"] == "por_confirmar"
    assert not [
        item for item in discovery["checks"]
        if item.get("familia") == "LIMIT_BYPASS"
    ]
    assert limit_candidates[0]["prueba_sugerida"]["tipo"] == "limit_differential"


def test_cors_runtime_confirma_reflexion_con_credenciales(tmp_path, monkeypatch):
    class Response:
        status_code = 200
        headers = {
            "Access-Control-Allow-Origin": "",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
        }

    def fake_request(method, url, cuenta=None, headers=None, cuerpo=None, timeout=10):
        response = Response()
        response.headers = dict(Response.headers)
        response.headers["Access-Control-Allow-Origin"] = headers.get("Origin")
        response.headers["Vary"] = "Origin"
        return response

    monkeypatch.setattr("auditor_bola.pilar2.request_http", fake_request)

    check = ChequeoPilar2(
        id_control="P2-CORS-GENERIC",
        nombre="cors policy",
        tipo="cors_policy",
        familia="CORS",
        metodo="GET",
        ruta="/api/items",
        headers={"Origin": "https://origen-no-autorizado.example"},
    )

    result = auditar_pilar2(_cfg([check]), tmp_path)[0]

    assert result.estado == "HALLAZGO"
    assert result.vulnerable is True
    assert result.confianza == "alta"
    assert len(result.evidencia) >= 4
    assert "reflexion_origin_con_credenciales" in (
        result.configuracion_detectada["condiciones_inseguras"]
    )


def test_cors_descubrimiento_elije_varios_get_seguros(tmp_path):
    (tmp_path / "server.py").write_text(
        "response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin')\n"
        "response.headers['Access-Control-Allow-Credentials'] = 'true'\n",
        encoding="utf-8",
    )
    endpoints = [
        {"metodo": "GET", "ruta": "/api/items", "archivos": ["server.py"]},
        {"metodo": "GET", "ruta": "/health", "archivos": ["server.py"]},
        {"metodo": "GET", "ruta": "/users", "archivos": ["server.py"]},
        {"metodo": "DELETE", "ruta": "/api/items/{id}", "archivos": ["server.py"]},
    ]

    discovery = discover_pilar2_profile(tmp_path, endpoints)
    cors_checks = [
        item for item in discovery["checks"]
        if item.get("familia") == "CORS"
    ]

    assert len(cors_checks) == 3
    assert {item["ruta"] for item in cors_checks} == {
        "/api/items", "/health", "/users"
    }
    assert all(item["metodo"] == "GET" for item in cors_checks)


def test_fingerprint_cors_consolida_controles_en_un_hallazgo():
    result = {
        "pilar1": {
            "bola": [],
            "acceso": [],
            "alcance_agente": [],
            "matriz_acceso": [],
        },
        "pilar2": [
            {
                "id_control": "P2-CORS-TEST-A",
                "nombre": "cors A",
                "tipo": "cors_policy",
                "familia": "CORS",
                "estado": "HALLAZGO",
                "vulnerable": True,
                "ruta": "/health",
                "metodo": "GET",
                "detalle": "reflection",
                "confianza": "alta",
                "severidad": "ALTA",
                "causa_raiz": "politica_cors",
                "fingerprint": "same-root-cors",
                "componente": "cors-middleware",
                "evidencia": [{"endpoint": "/health"}],
                "casos_prueba": [{"ruta": "/health"}],
            },
            {
                "id_control": "P2-CORS-TEST-B",
                "nombre": "cors B",
                "tipo": "cors_policy",
                "familia": "CORS",
                "estado": "HALLAZGO",
                "vulnerable": True,
                "ruta": "/users",
                "metodo": "GET",
                "detalle": "reflection",
                "confianza": "alta",
                "severidad": "ALTA",
                "causa_raiz": "politica_cors",
                "fingerprint": "same-root-cors",
                "componente": "cors-middleware",
                "evidencia": [{"endpoint": "/users"}],
                "casos_prueba": [{"ruta": "/users"}],
            },
        ],
    }

    findings = consolidate_runtime_results(result)

    assert len(findings) == 1
    finding = findings[0]
    assert finding["familia"] == "CORS"
    assert finding["estado"] == "confirmado"
    assert set(finding["relacionado_con"]) == {
        "P2-CORS-TEST-A", "P2-CORS-TEST-B"
    }
    assert len(finding["casos_prueba"]) >= 2


def test_runner_separa_controles_hallazgos_y_duplicados_p2(tmp_path):
    (tmp_path / "cors_a.cfg").write_text("unsafe=true\n", encoding="utf-8")
    (tmp_path / "cors_b.cfg").write_text("unsafe=true\n", encoding="utf-8")
    checks = [
        ChequeoPilar2(
            id_control="P2-CORS-A",
            nombre="cors evidence A",
            tipo="source_contains",
            familia="CORS",
            archivo="cors_a.cfg",
            patron_inseguro="unsafe=true",
            componente="global-cors",
        ),
        ChequeoPilar2(
            id_control="P2-CORS-B",
            nombre="cors evidence B",
            tipo="source_contains",
            familia="CORS",
            archivo="cors_b.cfg",
            patron_inseguro="unsafe=true",
            componente="global-cors",
        ),
    ]
    cfg = _cfg(
        checks,
        candidates=[
            {
                "candidate_id": "P2-CANDIDATE-CORS-X",
                "familia": "CORS",
                "estado": "prueba_preparada",
            }
        ],
    )

    result = diagnosticar(cfg, tmp_path)

    assert result["resumen"]["pilar2_controles_ejecutados"] == 2
    assert result["resumen"]["pilar2_candidatos"] == 1
    assert result["resumen"]["pilar2_vulnerabilidades_confirmadas"] == 2
    assert result["resumen"]["pilar2_hallazgos_unicos"] == 1
    assert result["resumen"]["pilar2_duplicados_consolidados"] == 1
