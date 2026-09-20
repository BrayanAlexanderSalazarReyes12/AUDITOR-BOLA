import json

from auditor_bola.config import ChequeoPilar2, ConfigObjetivo
from auditor_bola.pilar2 import auditar_pilar2
from auditor_bola.pilar2_engine import discover_pilar2
from auditor_bola.profile_builder import build_profile_draft, detect_project
from auditor_bola.security_model import consolidate_runtime_results


def _cfg(checks):
    return ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:1",
        cuentas=[],
        endpoints=[],
        chequeos_pilar2=checks,
    )


def test_descubrimiento_p2_no_confirma_documentacion_como_secreto(tmp_path):
    (tmp_path / "README.md").write_text(
        'Ejemplo: SECRET_KEY=os.getenv("APP_SECRET", "dev-secret")\n',
        encoding="utf-8",
    )

    discovered = discover_pilar2(tmp_path, [])

    secret_candidates = [
        item
        for item in discovered["candidatos"]
        if item["familia"] == "SECRET"
    ]
    secret_checks = [
        item
        for item in discovered["controles"]
        if item.get("familia") == "SECRET"
    ]

    assert secret_candidates
    assert all(
        item["estado"] == "evidencia_insuficiente"
        for item in secret_candidates
    )
    assert secret_checks == []


def test_secret_fallback_sin_contexto_productivo_queda_por_confirmar(
    tmp_path,
):
    (tmp_path / "settings.py").write_text(
        'import os\nSECRET_KEY=os.getenv("APP_SECRET", "dev-secret")\n',
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    checks = [
        item
        for item in profile["chequeos_pilar2"]
        if item.get("familia") == "SECRET"
    ]

    assert len(checks) == 1
    cfg = _cfg([ChequeoPilar2(**checks[0])])
    result = auditar_pilar2(cfg, tmp_path)[0]

    assert result.estado == "POR_CONFIRMAR"
    assert result.vulnerable is False
    assert result.confianza == "media"
    assert result.evidencia[0]["valor_expuesto"] is False


def test_secret_fallback_con_contexto_produccion_confirma_hallazgo(
    tmp_path,
):
    (tmp_path / "production.py").write_text(
        'import os\nENVIRONMENT="production"\n'
        'JWT_SECRET=os.getenv("JWT_SECRET", "dev-secret")\n',
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    check = next(
        item
        for item in profile["chequeos_pilar2"]
        if item.get("familia") == "SECRET"
    )
    result = auditar_pilar2(
        _cfg([ChequeoPilar2(**check)]),
        tmp_path,
    )[0]

    assert result.estado == "HALLAZGO"
    assert result.vulnerable is True
    assert result.confianza == "media-alta"


def test_limit_bypass_estatico_no_se_eleva_a_vulnerabilidad(tmp_path):
    (tmp_path / "api.py").write_text(
        "def handle(data):\n"
        "    urgent = data.get('urgent')\n"
        "    limit = 10\n"
        "    if urgent:\n"
        "        limit = 1000\n"
        "    return limit\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    check = next(
        item
        for item in profile["chequeos_pilar2"]
        if item.get("familia") == "LIMIT_BYPASS"
    )
    result = auditar_pilar2(
        _cfg([ChequeoPilar2(**check)]),
        tmp_path,
    )[0]

    assert result.estado == "POR_CONFIRMAR"
    assert result.vulnerable is False
    assert result.casos_prueba[0]["tipo"] == "diferencial_limite"


def test_limit_bypass_con_guardia_permanece_solo_como_evidencia(tmp_path):
    (tmp_path / "api.py").write_text(
        "def handle(data, user):\n"
        "    urgent = data.get('urgent')\n"
        "    limit = 10\n"
        "    if urgent and user.role == 'admin':\n"
        "        limit = 1000\n"
        "    return limit\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))

    assert not any(
        item.get("familia") == "LIMIT_BYPASS"
        for item in profile["chequeos_pilar2"]
    )
    candidates = [
        item
        for item in profile["candidatos_pilar2"]
        if item["familia"] == "LIMIT_BYPASS"
    ]
    assert candidates
    assert all(
        item["estado"] == "evidencia_insuficiente"
        for item in candidates
    )


def test_container_multistage_usa_usuario_del_stage_final(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12 AS builder\n"
        "USER root\n"
        "RUN echo build\n"
        "FROM python:3.12-slim AS runtime\n"
        "USER app\n"
        "CMD [\"python\", \"app.py\"]\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    check = next(
        item
        for item in profile["chequeos_pilar2"]
        if item.get("familia") == "CONTAINER"
    )
    result = auditar_pilar2(
        _cfg([ChequeoPilar2(**check)]),
        tmp_path,
    )[0]

    assert result.estado == "SIN_HALLAZGO"
    assert result.vulnerable is False
    assert (
        result.configuracion_detectada["stage_final"]["user"]
        == "app"
    )


def test_container_sin_user_no_se_asume_root(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nCMD [\"python\", \"app.py\"]\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    check = next(
        item
        for item in profile["chequeos_pilar2"]
        if item.get("familia") == "CONTAINER"
    )
    result = auditar_pilar2(
        _cfg([ChequeoPilar2(**check)]),
        tmp_path,
    )[0]

    assert result.estado == "POR_CONFIRMAR"
    assert result.vulnerable is False
    assert result.confianza == "media"


def test_container_compose_privileged_confirma_hallazgo(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nUSER app\n",
        encoding="utf-8",
    )
    (tmp_path / "compose.yaml").write_text(
        "services:\n"
        "  api:\n"
        "    build: .\n"
        "    privileged: true\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    check = next(
        item
        for item in profile["chequeos_pilar2"]
        if item.get("familia") == "CONTAINER"
    )
    result = auditar_pilar2(
        _cfg([ChequeoPilar2(**check)]),
        tmp_path,
    )[0]

    assert result.estado == "HALLAZGO"
    assert result.vulnerable is True
    runtime = result.configuracion_detectada["runtime"]
    assert any(item["privileged_true"] for item in runtime)


def test_deduplicacion_cors_agrupa_pruebas_misma_causa_raiz():
    result = {
        "pilar1": {
            "bola": [],
            "acceso": [],
            "alcance_agente": [],
            "matriz_acceso": [],
        },
        "pilar2": [
            {
                "id_control": "P2-CORS-T1",
                "nombre": "cors",
                "tipo": "cors_reflection",
                "familia": "CORS",
                "componente": "middleware/cors",
                "ruta": "/one",
                "metodo": "GET",
                "estado": "HALLAZGO",
                "vulnerable": True,
                "detalle": "origin externo aceptado",
                "causa_raiz": "politica_cors",
                "evidencia": [{"tipo": "http_runtime", "ruta": "/one"}],
            },
            {
                "id_control": "P2-CORS-T2",
                "nombre": "cors",
                "tipo": "cors_reflection",
                "familia": "CORS",
                "componente": "middleware/cors",
                "ruta": "/two",
                "metodo": "GET",
                "estado": "HALLAZGO",
                "vulnerable": True,
                "detalle": "origin externo aceptado",
                "causa_raiz": "politica_cors",
                "evidencia": [{"tipo": "http_runtime", "ruta": "/two"}],
            },
        ],
        "resumen": {},
    }

    findings = consolidate_runtime_results(result)

    assert len(findings) == 1
    assert findings[0]["familia"] == "CORS"
    assert set(findings[0]["relacionado_con"]) == {
        "P2-CORS-T1",
        "P2-CORS-T2",
    }


def test_secretos_distintos_no_se_deduplican_solo_por_familia():
    result = {
        "pilar1": {
            "bola": [],
            "acceso": [],
            "alcance_agente": [],
            "matriz_acceso": [],
        },
        "pilar2": [
            {
                "id_control": "P2-SECRET-A",
                "nombre": "secret a",
                "tipo": "secret_fallback_context",
                "familia": "SECRET",
                "componente": "settings.py:JWT_SECRET",
                "archivo": "settings.py",
                "estado": "HALLAZGO",
                "vulnerable": True,
                "detalle": "fallback jwt",
                "causa_raiz": "gestion_secretos",
            },
            {
                "id_control": "P2-SECRET-B",
                "nombre": "secret b",
                "tipo": "secret_fallback_context",
                "familia": "SECRET",
                "componente": "settings.py:DB_PASSWORD",
                "archivo": "settings.py",
                "estado": "HALLAZGO",
                "vulnerable": True,
                "detalle": "fallback db",
                "causa_raiz": "gestion_secretos",
            },
        ],
        "resumen": {},
    }

    findings = consolidate_runtime_results(result)

    assert len(findings) == 2


def test_perfil_p2_expone_candidatos_controles_y_recetas_abstractas(
    tmp_path,
):
    (tmp_path / "app.py").write_text(
        "def handle(data):\n"
        "    force = data.get('force')\n"
        "    quota = 10\n"
        "    if force:\n"
        "        quota = 100\n"
        "    return quota\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))

    assert profile["candidatos_pilar2"]
    assert profile["estrategias_correccion_pilar2"]
    strategy = next(
        item
        for item in profile["estrategias_correccion_pilar2"]
        if item["familia"] == "LIMIT_BYPASS"
    )
    serialized = json.dumps(strategy).lower()
    assert "tramitia" not in serialized
    assert "replace_exact" not in serialized
