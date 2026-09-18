from auditor_bola.corrective import apply_correction, rollback
from auditor_bola.evidence import EvidenceSession


def test_corrector_bola_hace_backup_y_rollback(tmp_path):
    target = tmp_path / "target"
    api = target / "tramitia" / "api.py"
    api.parent.mkdir(parents=True)
    original = '''from .auth import COORDINADOR, current_user

def puede_acceder(row) -> bool:
    """Verifica que la identidad actual tenga sesion valida sobre la solicitud."""
    usuario = current_user()
    return usuario is not None
'''
    api.write_text(original, encoding="utf-8")

    evidence = EvidenceSession.create(tmp_path / "evidencias")
    result = apply_correction("P1-BOLA-001", target, evidence)

    patched = api.read_text(encoding="utf-8")
    assert 'row["propietario"] == usuario["username"]' in patched
    assert result.before_hash != result.after_hash
    assert "@@" in result.diff

    rollback(result, target)
    assert api.read_text(encoding="utf-8") == original
