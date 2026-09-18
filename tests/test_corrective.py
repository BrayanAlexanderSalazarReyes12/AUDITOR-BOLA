from auditor_bola.config import ConfigObjetivo, Correccion
from auditor_bola.corrective import apply_correction, rollback
from auditor_bola.evidence import EvidenceSession


def test_corrector_generico_hace_backup_y_rollback(tmp_path):
    target = tmp_path / "target"
    source = target / "src" / "access.py"
    source.parent.mkdir(parents=True)
    original = "ALLOW_ALL = True\n"
    source.write_text(original, encoding="utf-8")

    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
        correcciones=[
            Correccion(
                control_id="P1-DEMO",
                archivo="src/access.py",
                operaciones=[
                    {
                        "estrategia": "replace_exact",
                        "buscar": "ALLOW_ALL = True",
                        "reemplazar": "ALLOW_ALL = False",
                    }
                ],
            )
        ],
    )

    evidence = EvidenceSession.create(tmp_path / "evidencias")
    result = apply_correction(cfg, "P1-DEMO", target, evidence)

    patched = source.read_text(encoding="utf-8")
    assert "ALLOW_ALL = False" in patched
    assert result.before_hash != result.after_hash
    assert result.operaciones_aplicadas == 1
    assert "@@" in result.diff

    rollback(result, target)
    assert source.read_text(encoding="utf-8") == original
