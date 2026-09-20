import json
from pathlib import Path

import auditor_bola.ai_recipes as ai
import auditor_bola.cycle as cycle
from auditor_bola.config import ConfigObjetivo, Correccion
from auditor_bola.corrective import CorrectionResult
from auditor_bola.project_validation import (
    ProjectValidationReport,
    ValidationStep,
    validate_project_after_patch,
)
from auditor_bola.source_locator import resolver_contexto_fuente


def _cfg():
    return ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
    )


def test_contexto_fuente_encuentra_capa_relacionada(tmp_path):
    root = tmp_path / "project"
    controller = root / "src" / "orders_controller.py"
    service = root / "src" / "orders_service.py"
    repository = root / "src" / "orders_repository.py"
    controller.parent.mkdir(parents=True)
    controller.write_text(
        'from orders_service import load_order\n'
        '@app.get("/orders/{id}")\n'
        'def get_order(id):\n'
        '    return load_order(id)\n',
        encoding="utf-8",
    )
    service.write_text(
        'from orders_repository import find_order\n'
        'def load_order(id):\n'
        '    return find_order(id)\n',
        encoding="utf-8",
    )
    repository.write_text(
        'def find_order(id):\n'
        '    return db.query(id)\n',
        encoding="utf-8",
    )

    resolution = resolver_contexto_fuente(
        _cfg(),
        root,
        control_id="P1-X",
        metodo="GET",
        ruta="/orders/{id}",
        descripcion="Order access control",
    )

    assert resolution.principal.archivo == "src/orders_controller.py"
    related = {item.archivo for item in resolution.relacionados}
    assert "src/orders_service.py" in related


def test_project_validation_rechaza_python_invalido(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    source = root / "app.py"
    source.write_text("def broken(:\n    pass\n", encoding="utf-8")

    result = validate_project_after_patch(root, "app.py")

    assert result.sintaxis.estado == "FAILED"
    assert result.tecnico_ok is False


def test_project_validation_config_sin_build_es_valida(tmp_path):
    root = tmp_path / "project"
    source = root / "config" / "app.properties"
    source.parent.mkdir(parents=True)
    source.write_text("debug=false\n", encoding="utf-8")

    result = validate_project_after_patch(root, "config/app.properties")

    assert result.sintaxis.estado == "NO_APLICA"
    assert result.build.estado == "NO_APLICA"
    assert result.tests.estado == "NO_APLICA"
    assert result.tecnico_ok is True


def test_diagnostico_activa_strategy_reset_tras_dos_fallos(monkeypatch):
    captured = {}

    provider = ai.AIProviderConfig(
        provider_id="test",
        provider_name="Test",
        model_id="model",
        model_name="Model",
        base_url="http://example.invalid/v1",
        api_key="",
        config_path="test",
    )

    diagnosis = {
        "hallazgo": "BOLA",
        "comportamiento_observado": "otro usuario obtiene 200",
        "comportamiento_esperado": "403",
        "entrada_reproduccion": "GET /orders/7",
        "componente_afectado": "orders.py",
        "archivo_causa_raiz": "orders.py",
        "simbolos_relevantes": ["get_order"],
        "archivos_relacionados": [],
        "flujo_ejecucion": ["route", "handler", "repository"],
        "hipotesis": [
            {
                "id": "H3",
                "descripcion": "consulta no limita propietario",
                "evidencia_a_favor": ["query por id"],
                "evidencia_en_contra": [],
                "estado": "CONFIRMADA",
            }
        ],
        "causa_raiz_probable": "consulta permisiva",
        "causa_raiz_confirmada": "consulta por id sin ownership",
        "condicion_explotacion": "id ajeno",
        "impacto": "lectura no autorizada",
        "riesgos_regresion": [],
        "pruebas_necesarias": ["owner ok", "other denied"],
        "supuestos_descartados": ["controller guard"],
        "strategy_reset": True,
    }

    def fake_request(provider_arg, *, system_prompt, user_payload, timeout):
        captured["system"] = system_prompt
        captured["payload"] = user_payload
        return diagnosis

    monkeypatch.setattr(ai, "_solicitar_json_gemma", fake_request)

    result, _provider = ai.diagnosticar_causa_raiz(
        _cfg(),
        control_id="P1-BOLA",
        descripcion="BOLA GET /orders/{id}",
        detalle="esperado=false real=true",
        source_relative="orders.py",
        source_text="def get_order(id): return repo.find(id)\n",
        provider=provider,
        intentos_fallidos=[
            {"propuesta": {"estrategia_conceptual": "controller guard"}},
            {"propuesta": {"estrategia_conceptual": "controller null guard"}},
        ],
    )

    assert result["strategy_reset"] is True
    assert captured["payload"]["strategy_reset"] is True
    assert "dos intentos ya fallaron" in captured["system"].lower()


def test_strategy_reset_rechaza_variacion_cosmetica():
    proposal = ai.AIRecipeProposal(
        id="IA-3",
        titulo="Otra validación en controller",
        enfoque="ALTERNATIVA",
        explicacion="controller authorization check",
        riesgo="MEDIO",
        estrategia="replace_exact",
        buscar="return order",
        reemplazar="return authorize(order)",
        requiere_reinicio=False,
        consideraciones="",
        estrategia_conceptual="controller authorization check",
    )

    validated = ai.validar_propuestas_contextuales(
        [proposal],
        source_relative="orders.py",
        source_text="def get_order():\n    return order\n",
        intentos_fallidos=[
            {
                "propuesta": {
                    "estrategia_conceptual": "controller authorization check",
                    "reemplazar": "return authorize(order)",
                }
            },
            {
                "propuesta": {
                    "estrategia_conceptual": "controller authorization guard",
                    "reemplazar": "return authorize(order)",
                }
            },
        ],
        strategy_reset=True,
    )

    assert validated[0].validacion_ok is False
    assert any(
        "demasiado similar" in item
        for item in validated[0].errores_validacion
    )


def test_cycle_build_failed_rolls_back_and_sets_patch_state(
    tmp_path,
    monkeypatch,
):
    baseline = {
        "filas": [
            {
                "id": "P1-X",
                "tipo_control": "acceso",
                "metodo": "GET",
                "ruta": "/x",
                "cuenta": "u",
                "estado": "HALLAZGO",
            }
        ]
    }
    monkeypatch.setattr(cycle, "diagnosticar", lambda *args, **kwargs: baseline)
    monkeypatch.setattr(
        cycle,
        "filas_gui",
        lambda result: result["filas"],
    )
    monkeypatch.setattr(cycle, "correction_available", lambda *args: True)

    target = tmp_path / "project"
    source = target / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('before')\n", encoding="utf-8")

    backup = tmp_path / "backup.py"
    backup.write_text("print('before')\n", encoding="utf-8")

    def fake_apply(*args, **kwargs):
        source.write_text("def broken(:\n", encoding="utf-8")
        return CorrectionResult(
            control_id="P1-X",
            archivo="app.py",
            applied=True,
            before_hash="before",
            after_hash="after",
            backup=str(backup),
            diff="- before\n+ broken\n",
            operaciones_aplicadas=1,
            mensaje="patched",
        )

    monkeypatch.setattr(cycle, "apply_correction", fake_apply)

    rolled_back = {"value": False}

    def fake_rollback(cfg, correction, target_root, evidence, restart, manifest):
        rolled_back["value"] = True
        source.write_text("print('before')\n", encoding="utf-8")
        manifest["rollback"] = True

    monkeypatch.setattr(cycle, "_rollback_seguro", fake_rollback)

    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
        correcciones=[
            Correccion(
                control_id="P1-X",
                archivo="app.py",
                operaciones=[{"estrategia": "replace_exact"}],
            )
        ],
    )

    result = cycle.ciclo_correctivo(
        cfg,
        "P1-X",
        target,
        evidence_base=tmp_path / "evidence",
    )

    assert result["estado_patch"] == "BUILD_FAILED"
    assert result["estado_final"] == "CORRECCION_FALLIDA"
    assert result["validacion_tecnica"]["sintaxis"]["estado"] == "FAILED"
    assert rolled_back["value"] is True
    assert result["failure_analysis"]["categoria_error"] == "syntax_error"


def test_global_regressions_are_recorded_but_target_contract_is_authoritative(
    monkeypatch,
):
    baseline = {
        "filas": [
            {
                "id": "P1-X",
                "tipo_control": "acceso",
                "metodo": "GET",
                "ruta": "/x",
                "cuenta": "u",
                "estado": "HALLAZGO",
            },
            {
                "id": "P2-OTHER",
                "tipo_control": "source_contains",
                "metodo": None,
                "ruta": None,
                "cuenta": "-",
                "estado": "SIN_HALLAZGO",
            },
        ]
    }
    after = {
        "filas": [
            {
                "id": "P1-X",
                "tipo_control": "acceso",
                "metodo": "GET",
                "ruta": "/x",
                "cuenta": "u",
                "estado": "SIN_HALLAZGO",
            },
            {
                "id": "P2-OTHER",
                "tipo_control": "source_contains",
                "metodo": None,
                "ruta": None,
                "cuenta": "-",
                "estado": "HALLAZGO",
            },
        ]
    }
    monkeypatch.setattr(
        cycle,
        "filas_gui",
        lambda result: result["filas"],
    )

    regressions = cycle.regresiones_globales(baseline, after)
    assert len(regressions) == 1
    assert regressions[0]["despues"]["id"] == "P2-OTHER"



def test_ciclo_ia_aplica_reinicia_reescanea_y_luego_ejecuta_qa(
    tmp_path,
    monkeypatch,
):
    events = []
    baseline = {
        "filas": [
            {
                "id": "P1-X",
                "tipo_control": "acceso",
                "metodo": "GET",
                "ruta": "/admin",
                "cuenta": "ana",
                "estado": "HALLAZGO",
            }
        ]
    }
    secure = {
        "filas": [
            {
                "id": "P1-X",
                "tipo_control": "acceso",
                "metodo": "GET",
                "ruta": "/admin",
                "cuenta": "ana",
                "estado": "SIN_HALLAZGO",
            }
        ]
    }

    diagnoses = iter([baseline, secure])

    def fake_diagnose(*args, **kwargs):
        result = next(diagnoses)
        events.append(
            "diagnose_before"
            if result is baseline
            else "diagnose_after_restart"
        )
        return result

    monkeypatch.setattr(cycle, "diagnosticar", fake_diagnose)
    monkeypatch.setattr(
        cycle,
        "filas_gui",
        lambda result: result["filas"],
    )
    monkeypatch.setattr(cycle, "correction_available", lambda *args: True)

    target = tmp_path / "project"
    source = target / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("ALLOW = True\n", encoding="utf-8")
    backup = tmp_path / "app.before.py"
    backup.write_text("ALLOW = True\n", encoding="utf-8")

    def fake_apply(*args, **kwargs):
        events.append("apply_patch")
        source.write_text("ALLOW = False\n", encoding="utf-8")
        return CorrectionResult(
            control_id="P1-X",
            archivo="app.py",
            applied=True,
            before_hash="before",
            after_hash="after",
            backup=str(backup),
            diff="- ALLOW = True\n+ ALLOW = False\n",
            operaciones_aplicadas=1,
            mensaje="patched",
        )

    monkeypatch.setattr(cycle, "apply_correction", fake_apply)

    def fake_validation(
        target_root,
        relative_file,
        *,
        build_timeout=180,
        test_timeout=240,
        run_build=True,
        run_tests=True,
    ):
        events.append(
            "validate_pre_security"
            if not run_tests
            else "validate_post_security"
        )
        return ProjectValidationReport(
            archivo="app.py",
            sintaxis=ValidationStep(
                nombre="sintaxis",
                estado="OK",
                detalle="ok",
            ),
            build=ValidationStep(
                nombre="build",
                estado="NO_APLICA",
                detalle="",
            ),
            tests=ValidationStep(
                nombre="tests",
                estado="OK" if run_tests else "NO_APLICA",
                detalle="",
            ),
            tecnico_ok=True,
            build_aplicable=False,
            tests_aplicables=run_tests,
        )

    monkeypatch.setattr(
        cycle,
        "validate_project_after_patch",
        fake_validation,
    )

    def restart():
        events.append("restart_service")

    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:5000",
        cuentas=[],
        endpoints=[],
        correcciones=[
            Correccion(
                control_id="P1-X",
                archivo="app.py",
                requiere_reinicio=True,
                operaciones=[
                    {
                        "estrategia": "replace_exact",
                        "buscar": "ALLOW = True",
                        "reemplazar": "ALLOW = False",
                    }
                ],
            )
        ],
    )

    result = cycle.ciclo_correctivo(
        cfg,
        "P1-X",
        target,
        evidence_base=tmp_path / "evidence",
        reiniciar=restart,
        selector={
            "cuenta": "ana",
            "metodo": "GET",
            "ruta": "/admin",
            "tipo_control": "acceso",
        },
    )

    assert result["estado_patch"] == "PATCH_VERIFIED"
    assert result["reinicio_servicio"]["exitoso"] is True
    assert result["reescaneo_seguridad"]["estado"] == "SIN_HALLAZGO"
    assert events == [
        "diagnose_before",
        "apply_patch",
        "validate_pre_security",
        "restart_service",
        "diagnose_after_restart",
        "validate_post_security",
    ]
    assert source.read_text(encoding="utf-8") == "ALLOW = False\n"


def test_propuesta_ia_fuerza_reinicio_antes_del_reescaneo():
    proposal = ai.AIRecipeProposal(
        id="IA-1",
        titulo="Parche",
        enfoque="MINIMA",
        explicacion="Corrige autorización",
        riesgo="BAJO",
        estrategia="replace_exact",
        buscar="return data",
        reemplazar="return secure_data",
        requiere_reinicio=False,
        consideraciones="",
        archivo_objetivo="app.py",
    )

    correction = ai.propuesta_a_correccion(
        proposal,
        control_id="P1-X",
        source_relative="app.py",
    )

    assert correction.requiere_reinicio is True
