from auditor_bola.config import ChequeoPilar2, ConfigObjetivo, Correccion
from auditor_bola.cycle import ciclo_correctivo


def _cfg_reinicio():
    return ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
        chequeos_pilar2=[
            ChequeoPilar2(
                id_control="P2-CONFIG-RESTART",
                nombre="Config segura",
                tipo="source_contains",
                archivo="config/app.properties",
                patron_inseguro="modo=inseguro",
                patron_seguro="modo=seguro",
            )
        ],
        correcciones=[
            Correccion(
                control_id="P2-CONFIG-RESTART",
                archivo="config/app.properties",
                requiere_reinicio=True,
                operaciones=[
                    {
                        "estrategia": "replace_exact",
                        "buscar": "modo=inseguro",
                        "reemplazar": "modo=seguro",
                    }
                ],
            )
        ],
    )


def test_requiere_reinicio_no_verifica_con_codigo_viejo(tmp_path):
    target = tmp_path / "target"
    archivo = target / "config" / "app.properties"
    archivo.parent.mkdir(parents=True)
    archivo.write_text("modo=inseguro\n", encoding="utf-8")

    resultado = ciclo_correctivo(
        _cfg_reinicio(),
        "P2-CONFIG-RESTART",
        target,
        evidence_base=tmp_path / "evidencias",
        reiniciar=None,
    )

    assert resultado["estado_final"] == "REQUIERE_REINICIO"
    assert resultado["rollback"] is True
    assert archivo.read_text(encoding="utf-8") == "modo=inseguro\n"


def test_requiere_reinicio_con_callback_continua_verificacion(tmp_path):
    target = tmp_path / "target"
    archivo = target / "config" / "app.properties"
    archivo.parent.mkdir(parents=True)
    archivo.write_text("modo=inseguro\n", encoding="utf-8")

    llamadas = {"n": 0}

    def reiniciar():
        llamadas["n"] += 1

    resultado = ciclo_correctivo(
        _cfg_reinicio(),
        "P2-CONFIG-RESTART",
        target,
        evidence_base=tmp_path / "evidencias",
        reiniciar=reiniciar,
    )

    assert resultado["estado_final"] == "CORREGIDO"
    assert resultado["estado_despues"] == "SIN_HALLAZGO"
    assert llamadas["n"] == 1
    assert archivo.read_text(encoding="utf-8") == "modo=seguro\n"
