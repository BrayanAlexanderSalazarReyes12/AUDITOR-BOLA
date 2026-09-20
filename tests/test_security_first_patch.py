import auditor_bola.cycle as cycle
from auditor_bola.config import ConfigObjetivo, Correccion
from auditor_bola.corrective import CorrectionResult
from auditor_bola.project_validation import (
    ProjectValidationReport,
    ValidationStep,
)


def _row(state):
    return {
        "id": "P1-AUTO-ACCESS-001",
        "tipo_control": "acceso",
        "metodo": "GET",
        "ruta": "/api/admin/auditoria",
        "cuenta": "ana.vargas",
        "estado": state,
    }


def _report(*, tests_state, tests_applicable):
    return ProjectValidationReport(
        archivo="app.py",
        archivos=["app.py"],
        sintaxis=ValidationStep(
            nombre="sintaxis",
            estado="OK",
            detalle=".py válido",
        ),
        sintaxis_archivos=[],
        build=ValidationStep(
            nombre="build",
            estado="NO_APLICA",
            detalle="sin build",
        ),
        tests=ValidationStep(
            nombre="tests",
            estado=tests_state,
            detalle=(
                "test_registra_la_creacion_de_solicitudes falló porque "
                "ya no recibe el comportamiento vulnerable"
                if tests_state == "FAILED"
                else "ok"
            ),
        ),
        tecnico_ok=tests_state in {"OK", "NO_APLICA"},
        build_aplicable=False,
        tests_aplicables=tests_applicable,
    )


def test_exploit_se_verifica_antes_de_la_suite_y_parche_se_conserva(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "project"
    root.mkdir()
    source = root / "app.py"
    source.write_text(
        "def auditoria():\n    return sensitive_data()\n",
        encoding="utf-8",
    )

    baseline = {"filas": [_row("HALLAZGO")]}
    verification = {"filas": [_row("SIN_HALLAZGO")]}
    scans = iter([baseline, verification])

    monkeypatch.setattr(
        cycle,
        "diagnosticar",
        lambda cfg, target: next(scans),
    )
    monkeypatch.setattr(
        cycle,
        "filas_gui",
        lambda result: result["filas"],
    )
    monkeypatch.setattr(
        cycle,
        "correction_available",
        lambda cfg, control_id: True,
    )

    backup = tmp_path / "app.backup.py"
    backup.write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    def fake_apply(*args, **kwargs):
        source.write_text(
            "def auditoria():\n    return forbidden()\n",
            encoding="utf-8",
        )
        return CorrectionResult(
            control_id="P1-AUTO-ACCESS-001",
            archivo="app.py",
            applied=True,
            before_hash="before",
            after_hash="after",
            backup=str(backup),
            diff="- sensitive_data\n+ forbidden\n",
            operaciones_aplicadas=1,
            mensaje="patched",
        )

    monkeypatch.setattr(cycle, "apply_correction", fake_apply)

    validation_calls = []

    def fake_validation(
        target_root,
        files,
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
            return _report(
                tests_state="NO_APLICA",
                tests_applicable=True,
            )
        return _report(
            tests_state="FAILED",
            tests_applicable=True,
        )

    monkeypatch.setattr(
        cycle,
        "validate_project_after_patch",
        fake_validation,
    )

    rolled_back = {"value": False}

    def fake_rollback(*args, **kwargs):
        rolled_back["value"] = True

    monkeypatch.setattr(
        cycle,
        "_rollback_seguro",
        fake_rollback,
    )

    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
        correcciones=[
            Correccion(
                control_id="P1-AUTO-ACCESS-001",
                archivo="app.py",
                operaciones=[
                    {
                        "estrategia": "replace_exact",
                        "buscar": "sensitive_data",
                        "reemplazar": "forbidden",
                    }
                ],
            )
        ],
    )

    selector = {
        "tipo_control": "acceso",
        "metodo": "GET",
        "ruta": "/api/admin/auditoria",
        "cuenta": "ana.vargas",
    }

    result = cycle.ciclo_correctivo(
        cfg,
        "P1-AUTO-ACCESS-001",
        root,
        evidence_base=tmp_path / "evidence",
        selector=selector,
    )

    assert validation_calls == [
        {"run_build": True, "run_tests": False},
        {"run_build": False, "run_tests": True},
    ]
    assert result["estado_despues"] == "SIN_HALLAZGO"
    assert result["estado_patch"] == "PATCH_VERIFIED_WITH_WARNINGS"
    assert result["estado_final"] == "CORREGIDO_CON_ADVERTENCIAS"
    assert result["rollback"] is False
    assert rolled_back["value"] is False
    assert "forbidden" in source.read_text(encoding="utf-8")
    assert result["qa_advertencias"]
    assert (
        result["criterios_exito"]["security_test_success"]
        is True
    )


def test_suite_no_se_ejecuta_si_exploit_sigue_reproduciendose(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "project"
    root.mkdir()
    source = root / "app.py"
    source.write_text("value = 'inseguro'\n", encoding="utf-8")

    scans = iter([
        {"filas": [_row("HALLAZGO")]},
        {"filas": [_row("HALLAZGO")]},
        {"filas": [_row("HALLAZGO")]},
    ])
    monkeypatch.setattr(
        cycle,
        "diagnosticar",
        lambda cfg, target: next(scans),
    )
    monkeypatch.setattr(
        cycle,
        "filas_gui",
        lambda result: result["filas"],
    )
    monkeypatch.setattr(
        cycle,
        "correction_available",
        lambda cfg, control_id: True,
    )

    backup = tmp_path / "backup.py"
    backup.write_text("value = 'inseguro'\n", encoding="utf-8")

    monkeypatch.setattr(
        cycle,
        "apply_correction",
        lambda *args, **kwargs: CorrectionResult(
            control_id="P1-AUTO-ACCESS-001",
            archivo="app.py",
            applied=True,
            before_hash="a",
            after_hash="b",
            backup=str(backup),
            diff="-a\n+b\n",
            operaciones_aplicadas=1,
            mensaje="patched",
        ),
    )

    calls = []

    def fake_validation(
        target_root,
        files,
        *,
        build_timeout=180,
        test_timeout=240,
        run_build=True,
        run_tests=True,
    ):
        calls.append((run_build, run_tests))
        return _report(
            tests_state="NO_APLICA",
            tests_applicable=True,
        )

    monkeypatch.setattr(
        cycle,
        "validate_project_after_patch",
        fake_validation,
    )

    monkeypatch.setattr(
        cycle,
        "_rollback_seguro",
        lambda cfg, correction, target, evidence, restart, manifest:
            manifest.update({"rollback": True}),
    )

    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
        correcciones=[
            Correccion(
                control_id="P1-AUTO-ACCESS-001",
                archivo="app.py",
                operaciones=[{"estrategia": "replace_exact"}],
            )
        ],
    )

    result = cycle.ciclo_correctivo(
        cfg,
        "P1-AUTO-ACCESS-001",
        root,
        evidence_base=tmp_path / "evidence",
        selector={
            "tipo_control": "acceso",
            "metodo": "GET",
            "ruta": "/api/admin/auditoria",
            "cuenta": "ana.vargas",
        },
    )

    assert calls == [(True, False)]
    assert result["estado_patch"] == "PATCH_FAILED"
    assert result["rollback"] is True
