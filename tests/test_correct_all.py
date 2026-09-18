from auditor_bola.config import ChequeoPilar2, ConfigObjetivo, Correccion
from auditor_bola.cycle import ciclo_correctivo, corregir_controles
from auditor_bola.runner import diagnosticar


def _cfg_dos_hallazgos():
    return ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
        chequeos_pilar2=[
            ChequeoPilar2(
                id_control="P2-CONFIG-001",
                nombre="Debug deshabilitado",
                tipo="source_contains",
                archivo="config/app.properties",
                patron_inseguro="debug=true",
                patron_seguro="debug=false",
            ),
            ChequeoPilar2(
                id_control="P2-CONFIG-002",
                nombre="Modo inseguro deshabilitado",
                tipo="source_contains",
                archivo="config/app.properties",
                patron_inseguro="unsafe=true",
                patron_seguro="unsafe=false",
            ),
        ],
        correcciones=[
            Correccion(
                control_id="P2-CONFIG-001",
                archivo="config/app.properties",
                operaciones=[
                    {
                        "estrategia": "replace_exact",
                        "buscar": "debug=true",
                        "reemplazar": "debug=false",
                    }
                ],
            )
        ],
    )


def test_corregir_controles_no_omite_hallazgo_sin_receta(tmp_path):
    target = tmp_path / "target"
    config_file = target / "config" / "app.properties"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(
        "debug=true\nunsafe=true\n",
        encoding="utf-8",
    )

    cfg = _cfg_dos_hallazgos()
    inicial = diagnosticar(cfg, target)
    assert sum(x["estado"] == "HALLAZGO" for x in inicial["pilar2"]) == 2

    resultados = corregir_controles(
        cfg,
        ["P2-CONFIG-001", "P2-CONFIG-002"],
        target,
        evidence_base=tmp_path / "evidencias",
    )

    por_control = {item["control"]: item for item in resultados}
    assert por_control["P2-CONFIG-001"]["estado_final"] == "CORREGIDO"
    assert (
        por_control["P2-CONFIG-002"]["estado_final"]
        == "PENDIENTE_SIN_RECETA"
    )
    assert "debug=false" in config_file.read_text(encoding="utf-8")
    assert "unsafe=true" in config_file.read_text(encoding="utf-8")


def test_fallo_de_reinicio_hace_rollback(tmp_path):
    target = tmp_path / "target"
    config_file = target / "config" / "app.properties"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("debug=true\n", encoding="utf-8")

    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
        chequeos_pilar2=[
            ChequeoPilar2(
                id_control="P2-CONFIG-001",
                nombre="Debug",
                tipo="source_contains",
                archivo="config/app.properties",
                patron_inseguro="debug=true",
                patron_seguro="debug=false",
            )
        ],
        correcciones=[
            Correccion(
                control_id="P2-CONFIG-001",
                archivo="config/app.properties",
                operaciones=[
                    {
                        "estrategia": "replace_exact",
                        "buscar": "debug=true",
                        "reemplazar": "debug=false",
                    }
                ],
            )
        ],
    )

    llamadas = {"n": 0}

    def reiniciar_fallando():
        llamadas["n"] += 1
        raise RuntimeError("reinicio simulado falló")

    resultado = ciclo_correctivo(
        cfg,
        "P2-CONFIG-001",
        target,
        evidence_base=tmp_path / "evidencias",
        reiniciar=reiniciar_fallando,
    )

    assert resultado["estado_final"] == "ERROR"
    assert resultado["rollback"] is True
    assert config_file.read_text(encoding="utf-8") == "debug=true\n"


def test_replace_exact_es_idempotente_si_el_reemplazo_ya_existe(tmp_path):
    target = tmp_path / "target"
    config_file = target / "config" / "app.properties"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("debug=false\nunsafe=true\n", encoding="utf-8")

    cfg = _cfg_dos_hallazgos()

    # El control de debug ya no es hallazgo; debe quedar SIN_HALLAZGO
    # y no intentar romper el archivo por no encontrar el texto inseguro.
    resultado = ciclo_correctivo(
        cfg,
        "P2-CONFIG-001",
        target,
        evidence_base=tmp_path / "evidencias",
    )

    assert resultado["estado_final"] == "SIN_HALLAZGO"
    assert config_file.read_text(encoding="utf-8") == "debug=false\nunsafe=true\n"
