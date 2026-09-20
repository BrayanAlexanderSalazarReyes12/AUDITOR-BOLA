from auditor_bola.config import ConfigObjetivo, Cuenta
from auditor_bola.p1_resolver import resolve_live_bola_candidates


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_resuelve_bola_desde_coleccion_autenticada(monkeypatch):
    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5050",
        cuentas=[
            Cuenta(
                username="ana.vargas",
                password="x",
                role="analista",
            ),
            Cuenta(
                username="bruno.mejia",
                password="x",
                role="analista",
            ),
        ],
        endpoints=[],
    )
    metadata = {
        "candidatos_pilar1": [
            {
                "familia": "BOLA",
                "metodo": "GET",
                "ruta_detectada": (
                    "/api/solicitudes/<int:solicitud_id>"
                ),
                "archivos_fuente": ["tramitia/api.py"],
            }
        ]
    }

    def fake_request(method, url, *, cuenta, timeout, **kwargs):
        assert method == "GET"
        assert url == "http://127.0.0.1:5050/api/solicitudes"
        return FakeResponse(
            200,
            [
                {
                    "id": 1,
                    "propietario": "ana.vargas",
                    "resumen": "demo",
                }
            ],
        )

    monkeypatch.setattr(
        "auditor_bola.p1_resolver.request_http",
        fake_request,
    )

    resolved = resolve_live_bola_candidates(
        cfg,
        metadata,
        base_url="http://127.0.0.1:5050",
    )

    assert len(resolved) == 1
    endpoint = resolved[0]
    assert endpoint.ruta == "/api/solicitudes/{id}"
    assert endpoint.id_prueba == "1"
    assert endpoint.propietario_esperado == "ana.vargas"
    assert endpoint.id_control == "P1-AUTO-LIVE-BOLA-001"


def test_no_resuelve_bola_si_la_api_no_expone_propietario(monkeypatch):
    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5050",
        cuentas=[
            Cuenta(
                username="ana.vargas",
                password="x",
                role="analista",
            )
        ],
        endpoints=[],
    )
    metadata = {
        "candidatos_pilar1": [
            {
                "familia": "BOLA",
                "metodo": "GET",
                "ruta_detectada": "/api/items/<int:item_id>",
            }
        ]
    }

    monkeypatch.setattr(
        "auditor_bola.p1_resolver.request_http",
        lambda *args, **kwargs: FakeResponse(
            200,
            [{"id": 7, "nombre": "sin propietario"}],
        ),
    )

    assert (
        resolve_live_bola_candidates(
            cfg,
            metadata,
            base_url="http://127.0.0.1:5050",
        )
        == []
    )


def test_descubrimiento_p1_en_vivo_es_solo_lectura(monkeypatch):
    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5050",
        cuentas=[
            Cuenta(
                username="ana.vargas",
                password="x",
                role="analista",
            )
        ],
        endpoints=[],
    )
    metadata = {
        "candidatos_pilar1": [
            {
                "familia": "BOLA",
                "metodo": "PATCH",
                "ruta_detectada": "/api/items/<int:item_id>",
            }
        ]
    }
    calls = []

    monkeypatch.setattr(
        "auditor_bola.p1_resolver.request_http",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert (
        resolve_live_bola_candidates(
            cfg,
            metadata,
            base_url="http://127.0.0.1:5050",
        )
        == []
    )
    assert calls == []



def test_resuelve_bola_con_campos_semanticos_no_estandar(monkeypatch):
    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5050",
        cuentas=[
            Cuenta(
                username="ana.vargas",
                password="x",
                role="analista",
            )
        ],
        endpoints=[],
    )
    metadata = {
        "candidatos_pilar1": [
            {
                "familia": "BOLA",
                "metodo": "GET",
                "ruta_detectada": "/api/tickets/{ticket_id}",
            }
        ]
    }

    monkeypatch.setattr(
        "auditor_bola.p1_resolver.request_http",
        lambda *args, **kwargs: FakeResponse(
            200,
            {
                "records": [
                    {
                        "ticket_id": 88,
                        "author": "ana.vargas",
                        "subject": "demo",
                    }
                ]
            },
        ),
    )

    resolved = resolve_live_bola_candidates(
        cfg,
        metadata,
        base_url="http://127.0.0.1:5050",
    )

    assert len(resolved) == 1
    assert resolved[0].id_prueba == "88"
    assert resolved[0].propietario_esperado == "ana.vargas"
    assert "campo id ticket_id" in resolved[0].pistas_codigo
    assert "campo propietario author" in resolved[0].pistas_codigo



def test_resuelve_get_y_patch_bola_con_mismo_valor(monkeypatch):
    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5050",
        cuentas=[
            Cuenta(
                username="ana.vargas",
                password="x",
                role="member",
            ),
            Cuenta(
                username="bruno.mejia",
                password="x",
                role="member",
            ),
        ],
        endpoints=[],
    )
    metadata = {
        "candidatos_pilar1": [
            {
                "familia": "BOLA",
                "metodo": "GET",
                "ruta_detectada": "/api/tickets/{ticket_id}",
            },
            {
                "familia": "BOLA",
                "metodo": "PATCH",
                "ruta_detectada": "/api/tickets/{ticket_id}",
            },
        ]
    }

    monkeypatch.setattr(
        "auditor_bola.p1_resolver.request_http",
        lambda *args, **kwargs: FakeResponse(
            200,
            {
                "records": [
                    {
                        "ticket_id": 88,
                        "author": "ana.vargas",
                        "summary": "sin cambios",
                    }
                ]
            },
        ),
    )

    resolved = resolve_live_bola_candidates(
        cfg,
        metadata,
        base_url="http://127.0.0.1:5050",
    )

    assert [item.metodo for item in resolved] == ["GET", "PATCH"]
    patch = resolved[1]
    assert patch.id_prueba == "88"
    assert patch.propietario_esperado == "ana.vargas"
    assert patch.cuerpo_prueba == {"summary": "sin cambios"}
