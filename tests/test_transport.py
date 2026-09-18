from auditor_bola.config import Cuenta
from auditor_bola.transport import preparar_autenticacion


def test_auth_basic():
    cuenta = Cuenta("ana", "clave", "analista")
    auth, headers = preparar_autenticacion(cuenta)
    assert auth == ("ana", "clave")
    assert headers == {}


def test_auth_bearer():
    cuenta = Cuenta(
        username="api-user",
        password=None,
        role="cliente",
        auth_type="bearer",
        token="abc123",
    )
    auth, headers = preparar_autenticacion(cuenta)
    assert auth is None
    assert headers["Authorization"] == "Bearer abc123"


def test_auth_header_personalizado():
    cuenta = Cuenta(
        username="svc",
        password=None,
        role="servicio",
        auth_type="header",
        headers={"X-API-Key": "demo-key"},
    )
    auth, headers = preparar_autenticacion(cuenta)
    assert auth is None
    assert headers["X-API-Key"] == "demo-key"
