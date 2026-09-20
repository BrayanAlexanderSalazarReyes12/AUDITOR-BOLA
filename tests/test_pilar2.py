import pytest
from auditor_bola.config import ChequeoPilar2, ConfigObjetivo
from auditor_bola.pilar2 import auditar_pilar2
from auditor_bola.runner import diagnosticar


def _cfg(checks):
    return ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:1",
        cuentas=[],
        endpoints=[],
        chequeos_pilar2=checks,
    )


def test_detecta_secreto_inseguro_en_fuente(tmp_path):
    target = tmp_path / "app"
    target.mkdir()
    (target / "settings.py").write_text(
        'SECRET_KEY=os.getenv("APP_SECRET", DEFAULT_SECRET)',
        encoding="utf-8",
    )
    check = ChequeoPilar2(
        id_control="P2-SECRET-MANUAL",
        nombre="secret",
        tipo="source_contains",
        archivo="app/settings.py",
        patron_inseguro='SECRET_KEY=os.getenv("APP_SECRET", DEFAULT_SECRET)',
        patron_seguro="valor seguro en producción",
    )
    result = auditar_pilar2(_cfg([check]), tmp_path)[0]
    assert result.estado == "HALLAZGO"
    assert result.vulnerable is True
    assert result.familia == "SECRET"
    assert result.severidad == "ALTA"
    assert result.confianza == "media-alta"
    assert result.causa_raiz == "gestion_secretos"
    assert result.evidencia
    assert result.evidencia[0]["tipo"] == "fuente_estatica"
    assert result.evidencia[0]["linea_insegura"] == 1
    assert result.recomendacion


def test_docker_non_root_pasa(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nUSER appuser\n", encoding="utf-8"
    )
    check = ChequeoPilar2(
        id_control="P2-DOCKER-004",
        nombre="docker",
        tipo="docker_non_root",
        archivo="Dockerfile",
    )
    result = auditar_pilar2(_cfg([check]), tmp_path)[0]
    assert result.estado == "SIN_HALLAZGO"



def test_diagnostico_no_declara_cero_hallazgos_si_no_hay_controles(tmp_path):
    cfg = ConfigObjetivo(
        sistema="sin-controles",
        base_url="http://127.0.0.1:5050",
        cuentas=[],
        endpoints=[],
    )

    with pytest.raises(
        RuntimeError,
        match="0 controles activos",
    ):
        diagnosticar(
            cfg,
            tmp_path,
            require_both_pillars=True,
        )



def test_diagnostico_p1_p2_exige_ambos_pilares(tmp_path):
    only_p2 = ConfigObjetivo(
        sistema="solo-p2",
        base_url="http://127.0.0.1:5050",
        cuentas=[],
        endpoints=[],
        chequeos_pilar2=[
            ChequeoPilar2(
                id_control="P2-CONFIG-001",
                nombre="config",
                tipo="source_contains",
                archivo="app.cfg",
                patron_inseguro="debug=true",
            )
        ],
    )
    (tmp_path / "app.cfg").write_text(
        "debug=true\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Pilar 1"):
        diagnosticar(
            only_p2,
            tmp_path,
            require_both_pillars=True,
        )



def test_source_regex_detecta_configuracion_insegura(tmp_path):
    (tmp_path / "settings.py").write_text(
        "DEBUG = True\n",
        encoding="utf-8",
    )
    check = ChequeoPilar2(
        id_control="P2-REGEX-001",
        nombre="debug",
        tipo="source_regex",
        archivo="settings.py",
        patron_inseguro=r"(?m)^\s*DEBUG\s*=\s*True\s*$",
    )

    result = auditar_pilar2(_cfg([check]), tmp_path)[0]

    assert result.estado == "HALLAZGO"
    assert "regex insegura presente=True" in result.detalle


def test_pilar2_conserva_evidencia_estructurada_en_dict(tmp_path):
    (tmp_path / "settings.py").write_text(
        "SESSION_COOKIE_SECURE = False\n",
        encoding="utf-8",
    )
    check = ChequeoPilar2(
        id_control="P2-COOKIE-001",
        nombre="cookie session secure",
        tipo="source_regex",
        archivo="settings.py",
        patron_inseguro=r"SESSION_COOKIE_SECURE\s*=\s*False",
    )

    result = auditar_pilar2(_cfg([check]), tmp_path)[0].as_dict()

    assert result["estado"] == "HALLAZGO"
    assert result["familia"] == "SESSION"
    assert result["causa_raiz"] == "configuracion_sesion"
    assert result["evidencia"][0]["archivo"] == "settings.py"
    assert result["recomendacion"]