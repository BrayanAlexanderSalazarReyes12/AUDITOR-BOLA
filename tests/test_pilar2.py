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
    target = tmp_path / "tramitia"
    target.mkdir()
    (target / "__init__.py").write_text(
        'SECRET_KEY=os.getenv("TRAMITIA_SECRET", SECRETO_POR_DEFECTO)',
        encoding="utf-8",
    )
    check = ChequeoPilar2(
        id_control="P2-SECRET-002",
        nombre="secret",
        tipo="source_contains",
        archivo="tramitia/__init__.py",
        patron_inseguro='SECRET_KEY=os.getenv("TRAMITIA_SECRET", SECRETO_POR_DEFECTO)',
        patron_seguro="valor seguro en producción",
    )
    result = auditar_pilar2(_cfg([check]), tmp_path)[0]
    assert result.estado == "HALLAZGO"


def test_docker_non_root_pasa(tmp_path):
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nUSER tramitia\n", encoding="utf-8"
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
