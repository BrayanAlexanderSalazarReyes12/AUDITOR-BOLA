from auditor_bola.config import ChequeoPilar2, ConfigObjetivo, Correccion
from auditor_bola.cycle import (
    ciclo_correctivo,
    rollback_todas_desde_evidencias,
)


def _config_cadena():
    return ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
        chequeos_pilar2=[
            ChequeoPilar2(
                id_control="P2-PASO-1",
                nombre="Paso uno",
                tipo="source_contains",
                archivo="config/app.properties",
                patron_inseguro="estado=uno",
                patron_seguro="estado=dos",
            ),
            ChequeoPilar2(
                id_control="P2-PASO-2",
                nombre="Paso dos",
                tipo="source_contains",
                archivo="config/app.properties",
                patron_inseguro="estado=dos",
                patron_seguro="estado=tres",
            ),
        ],
        correcciones=[
            Correccion(
                control_id="P2-PASO-1",
                archivo="config/app.properties",
                operaciones=[
                    {
                        "estrategia": "replace_exact",
                        "buscar": "estado=uno",
                        "reemplazar": "estado=dos",
                    }
                ],
            ),
            Correccion(
                control_id="P2-PASO-2",
                archivo="config/app.properties",
                operaciones=[
                    {
                        "estrategia": "replace_exact",
                        "buscar": "estado=dos",
                        "reemplazar": "estado=tres",
                    }
                ],
            ),
        ],
    )


def test_revertir_todas_restaurar_cadena_en_orden_inverso(tmp_path):
    target = tmp_path / "target"
    archivo = target / "config" / "app.properties"
    archivo.parent.mkdir(parents=True)
    archivo.write_text("estado=uno\n", encoding="utf-8")
    evidencias = tmp_path / "evidencias"

    cfg = _config_cadena()

    primero = ciclo_correctivo(
        cfg,
        "P2-PASO-1",
        target,
        evidence_base=evidencias,
    )
    assert primero["estado_final"] == "CORREGIDO"
    assert archivo.read_text(encoding="utf-8") == "estado=dos\n"

    segundo = ciclo_correctivo(
        cfg,
        "P2-PASO-2",
        target,
        evidence_base=evidencias,
    )
    assert segundo["estado_final"] == "CORREGIDO"
    assert archivo.read_text(encoding="utf-8") == "estado=tres\n"

    resultado = rollback_todas_desde_evidencias(evidencias, target)

    assert resultado["revertidas"] == 2
    assert resultado["conflictos_hash"] == 0
    assert resultado["errores"] == 0
    assert archivo.read_text(encoding="utf-8") == "estado=uno\n"


def test_revertir_todas_no_sobrescribe_cambios_ajenos(tmp_path):
    target = tmp_path / "target"
    archivo = target / "config" / "app.properties"
    archivo.parent.mkdir(parents=True)
    archivo.write_text("estado=uno\n", encoding="utf-8")
    evidencias = tmp_path / "evidencias"

    cfg = _config_cadena()
    resultado_correccion = ciclo_correctivo(
        cfg,
        "P2-PASO-1",
        target,
        evidence_base=evidencias,
    )
    assert resultado_correccion["estado_final"] == "CORREGIDO"

    archivo.write_text("estado=cambio-manual\n", encoding="utf-8")

    resultado = rollback_todas_desde_evidencias(evidencias, target)

    assert resultado["revertidas"] == 0
    assert resultado["conflictos_hash"] == 1
    assert archivo.read_text(encoding="utf-8") == "estado=cambio-manual\n"
