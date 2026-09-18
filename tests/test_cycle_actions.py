from auditor_bola.config import (
    ChequeoPilar2,
    ConfigObjetivo,
    Correccion,
)
from auditor_bola.cycle import (
    ciclo_correctivo,
    rollback_desde_evidencia,
    verificar_control,
)
from auditor_bola.evidence import EvidenceSession


def _config_estatica():
    return ConfigObjetivo(
        sistema="demo-estatico",
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


def test_ciclo_correctivo_completo_y_rollback_manual(tmp_path):
    target = tmp_path / "target"
    config_file = target / "config" / "app.properties"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("debug=true\n", encoding="utf-8")

    cfg = _config_estatica()
    manifest = ciclo_correctivo(
        cfg,
        "P2-CONFIG-001",
        target,
        evidence_base=tmp_path / "evidencias",
    )

    assert manifest["estado_final"] == "CORREGIDO"
    assert config_file.read_text(encoding="utf-8") == "debug=false\n"

    evidence_dir = manifest["evidencia"]
    rollback = rollback_desde_evidencia(evidence_dir, target)
    assert rollback["restauracion_ok"] is True
    assert config_file.read_text(encoding="utf-8") == "debug=true\n"


def test_verificacion_manual_genera_evidencia(tmp_path):
    target = tmp_path / "target"
    config_file = target / "config" / "app.properties"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("debug=true\n", encoding="utf-8")

    payload = verificar_control(
        _config_estatica(),
        "P2-CONFIG-001",
        target,
        evidence_base=tmp_path / "evidencias",
    )

    assert payload["estado"] == "HALLAZGO"
    evidence = payload["evidencia"]
    assert (tmp_path / "evidencias").exists()
    assert evidence


def test_sesiones_de_evidencia_no_colisionan(tmp_path):
    first = EvidenceSession.create(tmp_path / "evidencias")
    second = EvidenceSession.create(tmp_path / "evidencias")
    assert first.root != second.root
