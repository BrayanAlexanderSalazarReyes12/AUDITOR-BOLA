from pathlib import Path

import auditor_bola.cycle as cycle
from auditor_bola.config import ConfigObjetivo, Correccion
from auditor_bola.corrective import CorrectionResult
from auditor_bola.language_detection import (
    detect_language_context,
    detect_source_language,
)
from auditor_bola.project_validation import (
    ProjectValidationReport,
    ValidationStep,
)


def test_detecta_python_y_flask_por_archivo_y_contenido():
    source = (
        "from flask import Flask, request\n"
        "app = Flask(__name__)\n"
        "@app.get('/api/orders')\n"
        "def orders():\n"
        "    return {'ok': True}\n"
    )

    detected = detect_source_language("tramitia/audit.py", source)

    assert detected.language == "Python"
    assert detected.confidence == "alta"
    assert "Flask" in detected.frameworks


def test_contexto_detecta_lenguajes_de_archivos_relacionados():
    context = detect_language_context(
        "src/controller.py",
        "from flask import request\ndef controller(): pass\n",
        {
            "src/service.py": "def load():\n    return True\n",
            "web/client.js": "const value = fetch('/api/x');\n",
        },
    )

    assert context["principal"]["language"] == "Python"
    assert context["archivos_relacionados"]["src/service.py"]["language"] == "Python"
    assert context["archivos_relacionados"]["web/client.js"]["language"] == "JavaScript"


def test_parche_seguridad_reinicia_reescanea_y_no_se_revierte_por_test_legacy(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "project"
    root.mkdir()
    source = root / "app.py"
    source.write_text("ALLOW = True\n", encoding="utf-8")

    baseline = {
        "filas": [
            {
                "id": "P1-X",
                "tipo_control": "acceso",
                "metodo": "GET",
                "ruta": "/api/admin/auditoria",
                "cuenta": "ana",
                "estado": "HALLAZGO",
            }
        ]
    }
    verification = {
        "filas": [
            {
                "id": "P1-X",
                "tipo_control": "acceso",
                "metodo": "GET",
                "ruta": "/api/admin/auditoria",
                "cuenta": "ana",
                "estado": "SIN_HALLAZGO",
            }
        ]
    }
    scans = iter([baseline, verification])
    events = []

    def fake_diagnose(cfg, target):
        value = next(scans)
        events.append(
            "baseline"
            if value is baseline
            else "security_rescan"
        )
        return value

    monkeypatch.setattr(cycle, "diagnosticar", fake_diagnose)
    monkeypatch.setattr(
        cycle,
        "filas_gui",
        lambda result: result["filas"],
    )
    monkeypatch.setattr(
        cycle,
        "correction_available",
        lambda *args: True,
    )

    backup = tmp_path / "backup.py"
    backup.write_text("ALLOW = True\n", encoding="utf-8")

    def fake_apply(*args, **kwargs):
        source.write_text("ALLOW = False\n", encoding="utf-8")
        events.append("patch")
        return CorrectionResult(
            control_id="P1-X",
            archivo="app.py",
            applied=True,
            before_hash="a",
            after_hash="b",
            backup=str(backup),
            diff="- ALLOW = True\n+ ALLOW = False\n",
            operaciones_aplicadas=1,
            mensaje="patched",
        )

    monkeypatch.setattr(cycle, "apply_correction", fake_apply)

    validation_calls = []

    def fake_validation(
        target_root,
        relative_file,
        *,
        build_timeout=180,
        test_timeout=240,
        run_build=True,
        run_tests=True,
    ):
        validation_calls.append(
            {
                "run_build": run_build,
                "run_tests": run_tests,
            }
        )
        if not run_tests:
            events.append("pre_validation")
            return ProjectValidationReport(
                archivo="app.py",
                archivos=["app.py"],
                sintaxis=ValidationStep(
                    "sintaxis",
                    "OK",
                    detalle=".py válido",
                ),
                sintaxis_archivos=[],
                build=ValidationStep(
                    "build",
                    "NO_APLICA",
                    detalle="sin build",
                ),
                tests=ValidationStep(
                    "tests",
                    "NO_APLICA",
                    detalle="diferidos",
                ),
                tecnico_ok=True,
                build_aplicable=False,
                tests_aplicables=True,
            )

        events.append("post_security_tests")
        return ProjectValidationReport(
            archivo="app.py",
            archivos=["app.py"],
            sintaxis=ValidationStep(
                "sintaxis",
                "OK",
                detalle=".py válido",
            ),
            sintaxis_archivos=[],
            build=ValidationStep(
                "build",
                "NO_APLICA",
                detalle="ya validado",
            ),
            tests=ValidationStep(
                "tests",
                "FAILED",
                detalle=(
                    "test legacy todavía esperaba HTTP 200 "
                    "para el acceso ahora bloqueado"
                ),
                returncode=1,
            ),
            tecnico_ok=False,
            build_aplicable=False,
            tests_aplicables=True,
        )

    monkeypatch.setattr(
        cycle,
        "validate_project_after_patch",
        fake_validation,
    )

    rollback_called = {"value": False}

    def fake_rollback(*args, **kwargs):
        rollback_called["value"] = True

    monkeypatch.setattr(
        cycle,
        "_rollback_seguro",
        fake_rollback,
    )

    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5000",
        cuentas=[],
        endpoints=[],
        correcciones=[
            Correccion(
                control_id="P1-X",
                archivo="app.py",
                operaciones=[
                    {
                        "estrategia": "replace_exact",
                        "buscar": "ALLOW = True",
                        "reemplazar": "ALLOW = False",
                    }
                ],
                requiere_reinicio=True,
            )
        ],
    )

    def restart():
        events.append("restart")

    result = cycle.ciclo_correctivo(
        cfg,
        "P1-X",
        root,
        evidence_base=tmp_path / "evidence",
        reiniciar=restart,
        selector={
            "tipo_control": "acceso",
            "metodo": "GET",
            "ruta": "/api/admin/auditoria",
            "cuenta": "ana",
        },
    )

    assert events.index("patch") < events.index("restart")
    assert events.index("restart") < events.index("security_rescan")
    assert events.index("security_rescan") < events.index("post_security_tests")
    assert validation_calls[0]["run_tests"] is False
    assert validation_calls[1]["run_tests"] is True
    assert result["reescaneo_seguridad"] == {
        "ejecutado": True,
        "estado": "SIN_HALLAZGO",
    }
    assert result["reinicio_servicio"]["intentado"] is True
    assert result["reinicio_servicio"]["exitoso"] is True
    assert result["estado_patch"] == "PATCH_VERIFIED_WITH_WARNINGS"
    assert result["estado_final"] == "CORREGIDO_CON_ADVERTENCIAS"
    assert rollback_called["value"] is False
    assert source.read_text(encoding="utf-8") == "ALLOW = False\n"
