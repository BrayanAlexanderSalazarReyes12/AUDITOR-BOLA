import json

from auditor_bola.profile_builder import build_profile_draft, detect_project
from auditor_bola.security_model import (
    attach_runtime_consolidation,
    consolidate_runtime_results,
    enrich_profile,
    stable_finding_id,
)


def test_perfil_explica_controles_y_separa_hallazgo_de_casos(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text(
        "from flask import Flask\n"
        "app = Flask(__name__)\n"
        "@app.get('/api/items/<int:item_id>')\n"
        "def item(item_id): return {'id': item_id}\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))

    assert "modelo_seguridad" in profile
    assert "familias_controles" in profile
    assert "controles_explicados" in profile
    assert "hallazgos_modelados" in profile
    assert profile["metadata_detectada"]["motor_evidencia"]["version"] == 3
    assert profile["metadata_detectada"]["motor_evidencia"][
        "deduplicacion_semantica"
    ] is True

    candidate = next(
        item
        for item in profile["controles_explicados"]
        if item["familia"] == "BOLA"
    )
    assert candidate["estado"] == "evidencia_insuficiente"
    assert candidate["hipotesis"]
    assert candidate["casos_prueba"]
    assert candidate["id_control_semantico"].startswith("P1-BOLA-")


def test_propiedad_por_alias_numerico_de_identidad(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text(
        "from flask import Flask\n"
        "app = Flask(__name__)\n"
        "@app.get('/api/orders/<int:order_id>')\n"
        "def get_order(order_id): return {'id': order_id}\n",
        encoding="utf-8",
    )

    fixtures = tmp_path / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "accounts.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "id": 7,
                        "username": "ana.demo",
                        "password": "x",
                        "role": "member",
                    },
                    {
                        "id": 8,
                        "username": "bob.demo",
                        "password": "x",
                        "role": "member",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (fixtures / "orders.json").write_text(
        json.dumps(
            {
                "orders": [
                    {
                        "id": 44,
                        "user_id": 7,
                        "description": "demo",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    bola = [
        item
        for item in profile["chequeos_pilar1"]
        if item.get("tipo") == "bola"
    ]

    assert bola
    assert bola[0]["id_prueba"] == "44"
    assert bola[0]["propietario_esperado"] == "ana.demo"


def test_ids_semanticos_son_estables_y_no_dependientes_de_app():
    first = stable_finding_id(
        "BOLA",
        endpoint="/api/orders/{id}",
        method="GET",
        resource="orders",
        root_cause="autorizacion_objeto",
    )
    second = stable_finding_id(
        "BOLA",
        endpoint="/api/orders/123",
        method="GET",
        resource="orders",
        root_cause="autorizacion_objeto",
    )
    assert first == second
    assert first.startswith("P1-BOLA-")


def test_runtime_consolida_varios_casos_rbac_en_un_hallazgo():
    result = {
        "pilar1": {
            "bola": [],
            "acceso": [
                {
                    "id_control": "P1-RBAC-A",
                    "nombre": "operacion privilegiada",
                    "cuenta": "ana",
                    "rol": "member",
                    "endpoint": "/api/report",
                    "metodo": "GET",
                    "acceso_esperado": False,
                    "acceso_real": True,
                    "http_status": 200,
                    "vulnerable": True,
                },
                {
                    "id_control": "P1-RBAC-B",
                    "nombre": "operacion privilegiada",
                    "cuenta": "bruno",
                    "rol": "member",
                    "endpoint": "/api/report",
                    "metodo": "GET",
                    "acceso_esperado": False,
                    "acceso_real": True,
                    "http_status": 200,
                    "vulnerable": True,
                },
            ],
            "alcance_agente": [],
            "matriz_acceso": [],
        },
        "pilar2": [],
        "resumen": {},
    }

    findings = consolidate_runtime_results(result)

    assert len(findings) == 1
    finding = findings[0]
    assert finding["familia"] == "RBAC_ABAC"
    assert finding["estado"] == "confirmado"
    assert len(finding["casos_prueba"]) == 2
    assert set(finding["relacionado_con"]) == {
        "P1-RBAC-A",
        "P1-RBAC-B",
    }


def test_runtime_deduplica_cors_global_entre_endpoints():
    result = {
        "pilar1": {
            "bola": [],
            "acceso": [],
            "alcance_agente": [],
            "matriz_acceso": [],
        },
        "pilar2": [
            {
                "id_control": "P2-CORS-A",
                "nombre": "cors",
                "tipo": "cors_reflection",
                "ruta": "/health",
                "metodo": "GET",
                "estado": "HALLAZGO",
                "detalle": "origin reflejado con credenciales",
            },
            {
                "id_control": "P2-CORS-B",
                "nombre": "cors",
                "tipo": "cors_reflection",
                "ruta": "/api/users",
                "metodo": "GET",
                "estado": "HALLAZGO",
                "detalle": "origin reflejado con credenciales",
            },
        ],
        "resumen": {},
    }

    enriched = attach_runtime_consolidation(result)

    assert len(enriched["hallazgos_consolidados"]) == 1
    finding = enriched["hallazgos_consolidados"][0]
    assert finding["familia"] == "CORS"
    assert len(finding["casos_prueba"]) == 2
    assert enriched["resumen"]["hallazgos_unicos_confirmados"] == 1
