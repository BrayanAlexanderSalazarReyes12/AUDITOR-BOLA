from auditor_bola.config import ConfigObjetivo, Cuenta, Endpoint
from auditor_bola.engine import auditar_matriz_acceso


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def test_matriz_prueba_cada_endpoint_con_cada_usuario(monkeypatch):
    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5050",
        cuentas=[
            Cuenta("ana", "x", "member"),
            Cuenta("bob", "x", "admin"),
        ],
        endpoints=[],
        endpoints_detectados=[
            {"metodo": "GET", "ruta": "/api/items"},
            {"metodo": "POST", "ruta": "/api/search"},
        ],
    )
    calls = []

    def fake_request(method, url, *, cuenta, cuerpo=None, **kwargs):
        calls.append((method, url, cuenta.username, cuerpo))
        return FakeResponse(200 if cuenta.username == "bob" else 403)

    monkeypatch.setattr(
        "auditor_bola.engine.request_http",
        fake_request,
    )

    rows = auditar_matriz_acceso(cfg)

    assert len(rows) == 4
    assert len(calls) == 4
    assert {
        (row.metodo, row.endpoint_detectado, row.cuenta)
        for row in rows
    } == {
        ("GET", "/api/items", "ana"),
        ("GET", "/api/items", "bob"),
        ("POST", "/api/search", "ana"),
        ("POST", "/api/search", "bob"),
    }
    assert any(
        row.cuenta == "bob"
        and row.clasificacion == "ACCESO"
        for row in rows
    )
    assert any(
        row.cuenta == "ana"
        and row.clasificacion == "DENEGADO"
        for row in rows
    )
    assert all(
        body == {}
        for method, _url, _user, body in calls
        if method == "POST"
    )


def test_matriz_materializa_endpoint_parametrizado_con_id_bola(
    monkeypatch,
):
    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5050",
        cuentas=[Cuenta("ana", "x", "member")],
        endpoints=[
            Endpoint(
                "GET",
                "/api/items/{id}",
                "44",
                "ana",
                id_control="P1-BOLA-001",
            )
        ],
        endpoints_detectados=[
            {
                "metodo": "GET",
                "ruta": "/api/items/<int:item_id>",
            }
        ],
    )
    calls = []

    def fake_request(method, url, *, cuenta, cuerpo=None, **kwargs):
        calls.append((method, url, cuenta.username))
        return FakeResponse(200)

    monkeypatch.setattr(
        "auditor_bola.engine.request_http",
        fake_request,
    )

    rows = auditar_matriz_acceso(cfg)

    assert len(rows) == 1
    assert rows[0].endpoint_ejecutado == "/api/items/44"
    assert calls == [
        ("GET", "http://127.0.0.1:5050/api/items/44", "ana")
    ]


def test_matriz_registra_delete_pero_no_lo_ejecuta(monkeypatch):
    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5050",
        cuentas=[
            Cuenta("ana", "x", "member"),
            Cuenta("bob", "x", "admin"),
        ],
        endpoints=[],
        endpoints_detectados=[
            {"metodo": "DELETE", "ruta": "/api/items/10"}
        ],
    )
    calls = []

    monkeypatch.setattr(
        "auditor_bola.engine.request_http",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    rows = auditar_matriz_acceso(cfg)

    assert len(rows) == 2
    assert calls == []
    assert all(row.clasificacion == "NO_EJECUTABLE" for row in rows)
    assert all("DELETE omitido" in row.detalle for row in rows)


def test_matriz_no_inventa_id_para_ruta_parametrizada(monkeypatch):
    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5050",
        cuentas=[Cuenta("ana", "x", "member")],
        endpoints=[],
        endpoints_detectados=[
            {"metodo": "GET", "ruta": "/api/items/{item_id}"}
        ],
    )
    calls = []

    monkeypatch.setattr(
        "auditor_bola.engine.request_http",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    rows = auditar_matriz_acceso(cfg)

    assert len(rows) == 1
    assert calls == []
    assert rows[0].clasificacion == "NO_EJECUTABLE"
