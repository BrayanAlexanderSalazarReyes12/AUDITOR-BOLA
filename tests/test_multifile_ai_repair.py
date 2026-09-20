import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from auditor_bola.ai_recipes import (
    AIRecipeProposal,
    propuesta_a_correccion,
    validar_propuestas_contextuales,
)
from auditor_bola.config import ConfigObjetivo
from auditor_bola.corrective import apply_correction, rollback
from auditor_bola.evidence import EvidenceSession
from auditor_bola.project_validation import validate_project_after_patch


def _cfg(correction):
    return ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
        correcciones=[correction],
    )


def test_propuesta_multifile_se_convierte_a_plan_transaccional(tmp_path):
    proposal = AIRecipeProposal(
        id="IA-2",
        titulo="Autorización por servicio",
        enfoque="ESTRUCTURAL",
        explicacion="Corrige controller y service.",
        riesgo="MEDIO",
        requiere_reinicio=True,
        consideraciones="demo",
        archivo_objetivo="controller.py",
        hipotesis_id="H2",
        estrategia_conceptual="mover autorización al service",
        cambios=[
            {
                "archivo": "controller.py",
                "estrategia": "replace_exact",
                "buscar": "return service.get(id)",
                "reemplazar": "return service.get(id, current_user)",
            },
            {
                "archivo": "service.py",
                "estrategia": "replace_exact",
                "buscar": "def get(id):",
                "reemplazar": "def get(id, current_user):",
            },
        ],
    )

    correction = propuesta_a_correccion(
        proposal,
        control_id="P1-X",
        source_relative="controller.py",
    )

    assert correction.archivo == "controller.py"
    assert len(correction.cambios) == 2
    assert correction.cambios[1]["archivo"] == "service.py"
    assert (
        correction.cambios[1]["operaciones"][0]["estrategia"]
        == "replace_exact"
    )


def test_aplicacion_multifile_es_atomica_y_rollback_restaura_todo(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    controller = root / "controller.py"
    service = root / "service.py"
    controller.write_text(
        "def route(id):\n    return service.get(id)\n",
        encoding="utf-8",
    )
    service.write_text(
        "def get(id):\n    return repo.find(id)\n",
        encoding="utf-8",
    )

    proposal = AIRecipeProposal(
        id="IA-2",
        titulo="multi",
        enfoque="ESTRUCTURAL",
        explicacion="multi",
        riesgo="MEDIO",
        cambios=[
            {
                "archivo": "controller.py",
                "estrategia": "replace_exact",
                "buscar": "return service.get(id)",
                "reemplazar": "return service.get(id, current_user)",
            },
            {
                "archivo": "service.py",
                "estrategia": "replace_exact",
                "buscar": "def get(id):",
                "reemplazar": "def get(id, current_user):",
            },
        ],
    )
    correction = propuesta_a_correccion(
        proposal,
        control_id="P1-X",
        source_relative="controller.py",
    )
    evidence = EvidenceSession.create(tmp_path / "evidence")

    result = apply_correction(
        _cfg(correction),
        "P1-X",
        root,
        evidence,
    )

    assert len(result.archivos) == 2
    assert "current_user" in controller.read_text(encoding="utf-8")
    assert "current_user" in service.read_text(encoding="utf-8")

    rollback(result, root)

    assert "current_user" not in controller.read_text(encoding="utf-8")
    assert "current_user" not in service.read_text(encoding="utf-8")


def test_plan_multifile_no_escribe_nada_si_un_cambio_no_coincide(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    one = root / "one.py"
    two = root / "two.py"
    one.write_text("VALUE = 1\n", encoding="utf-8")
    two.write_text("VALUE = 2\n", encoding="utf-8")

    proposal = AIRecipeProposal(
        id="IA-1",
        titulo="atomic",
        enfoque="MINIMA",
        explicacion="atomic",
        riesgo="BAJO",
        cambios=[
            {
                "archivo": "one.py",
                "estrategia": "replace_exact",
                "buscar": "VALUE = 1",
                "reemplazar": "VALUE = 10",
            },
            {
                "archivo": "two.py",
                "estrategia": "replace_exact",
                "buscar": "NO_EXISTE",
                "reemplazar": "VALUE = 20",
            },
        ],
    )
    correction = propuesta_a_correccion(
        proposal,
        control_id="P1-X",
        source_relative="one.py",
    )
    evidence = EvidenceSession.create(tmp_path / "evidence")

    try:
        apply_correction(
            _cfg(correction),
            "P1-X",
            root,
            evidence,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("la receta debía fallar")

    assert one.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert two.read_text(encoding="utf-8") == "VALUE = 2\n"


def test_validacion_local_multifile_detecta_regex_invalida():
    proposal = AIRecipeProposal(
        id="IA-3",
        titulo="regex",
        enfoque="ALTERNATIVA",
        explicacion="demo",
        riesgo="MEDIO",
        cambios=[
            {
                "archivo": "controller.py",
                "estrategia": "replace_exact",
                "buscar": "return ok",
                "reemplazar": "return secure_ok",
            },
            {
                "archivo": "service.py",
                "estrategia": "regex_replace",
                "buscar": "(unbalanced",
                "reemplazar": "x",
            },
        ],
    )

    result = validar_propuestas_contextuales(
        [proposal],
        source_relative="controller.py",
        source_text="def route():\n    return ok\n",
        source_files={
            "service.py": "def load():\n    return value\n",
        },
    )[0]

    assert result.validacion_ok is False
    assert any(
        "regex inválida" in error
        for error in result.errores_validacion
    )


def test_validacion_tecnica_multifile_informa_archivo_roto(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "good.py").write_text(
        "def ok():\n    return True\n",
        encoding="utf-8",
    )
    (root / "bad.py").write_text(
        "def broken(:\n    return False\n",
        encoding="utf-8",
    )

    report = validate_project_after_patch(
        root,
        ["good.py", "bad.py"],
    )

    assert report.sintaxis.estado == "FAILED"
    assert report.archivos == ["good.py", "bad.py"]
    assert any(
        item["archivo"] == "bad.py"
        and item["estado"] == "FAILED"
        for item in report.sintaxis_archivos
    )
