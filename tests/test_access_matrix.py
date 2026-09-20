from auditor_bola.config import (
    ChequeoAcceso,
    ConfigObjetivo,
    Cuenta,
    Endpoint,
)
from auditor_bola.engine import auditar_matriz_acceso


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class JsonResponse(FakeResponse):
    def __init__(self, status_code, payload):
        super().__init__(status_code)
        self.payload = payload

    def json(self):
        return self.payload


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
    # Solo GET se ejecuta sin evidencia adicional. POST queda registrado como
    # NO_EJECUTABLE hasta disponer de un payload de prueba seguro.
    assert len(calls) == 2
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
    post_rows = [row for row in rows if row.metodo == "POST"]
    assert len(post_rows) == 2
    assert all(row.clasificacion == "NO_EJECUTABLE" for row in post_rows)
    assert all("payload de prueba seguro" in row.detalle for row in post_rows)


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



def test_matriz_clasifica_hallazgo_con_politica_rbac_explicita(
    monkeypatch,
):
    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5050",
        cuentas=[
            Cuenta("ana", "x", "member"),
            Cuenta("admin", "x", "admin"),
        ],
        endpoints=[],
        roles_privilegiados=["admin"],
        chequeos_acceso=[
            ChequeoAcceso(
                id_control="P1-RBAC-001",
                nombre="admin restringido",
                cuenta="ana",
                metodo="GET",
                ruta="/api/admin",
                acceso_esperado=False,
            )
        ],
        endpoints_detectados=[
            {"metodo": "GET", "ruta": "/api/admin"}
        ],
    )

    monkeypatch.setattr(
        "auditor_bola.engine.request_http",
        lambda *args, **kwargs: FakeResponse(200),
    )

    rows = auditar_matriz_acceso(cfg)
    ana = next(row for row in rows if row.cuenta == "ana")

    assert ana.vulnerable is True
    assert ana.acceso_esperado is False
    assert ana.clasificacion == "HALLAZGO_CONFIRMADO"
    assert ana.fuente_politica == "control_acceso"
    assert ana.id_control_referencia == "P1-RBAC-001"


def test_matriz_marca_posible_hallazgo_desde_candidato_rbac(
    monkeypatch,
):
    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5050",
        cuentas=[
            Cuenta("ana", "x", "member"),
            Cuenta("admin", "x", "admin"),
        ],
        endpoints=[],
        roles_privilegiados=["admin"],
        endpoints_detectados=[
            {"metodo": "GET", "ruta": "/api/management/report"}
        ],
        candidatos_pilar1=[
            {
                "familia": "RBAC_ABAC",
                "metodo": "GET",
                "ruta_detectada": "/api/management/report",
            }
        ],
    )

    monkeypatch.setattr(
        "auditor_bola.engine.request_http",
        lambda *args, **kwargs: FakeResponse(200),
    )

    rows = auditar_matriz_acceso(cfg)
    ana = next(row for row in rows if row.cuenta == "ana")
    admin = next(row for row in rows if row.cuenta == "admin")

    assert ana.vulnerable is True
    assert ana.clasificacion == "POSIBLE_HALLAZGO"
    assert ana.fuente_politica == "candidato_rbac"
    assert ana.confianza == "media"
    assert admin.vulnerable is None
    assert admin.clasificacion == "ACCESO"


def test_matriz_reutiliza_politica_de_otro_usuario_del_mismo_rol(
    monkeypatch,
):
    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5050",
        cuentas=[
            Cuenta("ana", "x", "member"),
            Cuenta("bruno", "x", "member"),
        ],
        endpoints=[],
        chequeos_acceso=[
            ChequeoAcceso(
                id_control="P1-RBAC-BASE",
                nombre="reporte restringido",
                cuenta="ana",
                metodo="GET",
                ruta="/api/report",
                acceso_esperado=False,
            )
        ],
        endpoints_detectados=[
            {"metodo": "GET", "ruta": "/api/report"}
        ],
    )

    def fake_request(method, url, *, cuenta, **kwargs):
        return FakeResponse(403 if cuenta.username == "ana" else 200)

    monkeypatch.setattr(
        "auditor_bola.engine.request_http",
        fake_request,
    )

    rows = auditar_matriz_acceso(cfg)
    bruno = next(row for row in rows if row.cuenta == "bruno")

    assert bruno.vulnerable is True
    assert bruno.clasificacion == "HALLAZGO_CONFIRMADO"
    assert bruno.fuente_politica == "politica_mismo_rol"


def test_matriz_compara_forma_conteo_e_ids_sin_inventar_vulnerabilidad(
    monkeypatch,
):
    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5050",
        cuentas=[
            Cuenta("ana", "x", "member"),
            Cuenta("bob", "x", "member"),
        ],
        endpoints=[],
        endpoints_detectados=[
            {"metodo": "GET", "ruta": "/api/items"}
        ],
    )

    def fake_request(method, url, *, cuenta, **kwargs):
        if cuenta.username == "ana":
            return JsonResponse(200, [{"id": 1, "owner": "ana"}])
        return JsonResponse(
            200,
            [
                {"id": 1, "owner": "ana"},
                {"id": 2, "owner": "bob"},
            ],
        )

    monkeypatch.setattr(
        "auditor_bola.engine.request_http",
        fake_request,
    )

    rows = auditar_matriz_acceso(cfg)
    by_user = {row.cuenta: row for row in rows}

    assert by_user["ana"].object_count == 1
    assert by_user["bob"].object_count == 2
    assert by_user["ana"].object_ids == ["1"]
    assert by_user["bob"].object_ids == ["1", "2"]
    assert by_user["ana"].response_signature
    assert by_user["bob"].response_signature
    assert by_user["ana"].response_signature != by_user["bob"].response_signature
    assert by_user["ana"].response_comparison
    assert by_user["bob"].response_comparison
    # Sin política de autorización, la diferencia aporta evidencia pero no se
    # promociona automáticamente a vulnerabilidad.
    assert by_user["ana"].vulnerable is None
    assert by_user["bob"].vulnerable is None
