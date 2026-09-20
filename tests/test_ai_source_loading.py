import hashlib
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from auditor_bola.ai_recipes import (
    AIProviderConfig,
    AIRecipeProposal,
)
from auditor_bola.config import ChequeoPilar2, ConfigObjetivo
from auditor_bola.qt_ui.controller import AuditorController


def _controller_with_p2(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    source = root / "config" / "security.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        'SECRET_KEY = "dev-secret"\n',
        encoding="utf-8",
    )
    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:1",
        cuentas=[],
        endpoints=[],
        chequeos_pilar2=[
            ChequeoPilar2(
                id_control="P2-SECRET-DEMO",
                nombre="Secret fallback",
                tipo="source_contains",
                archivo="config/security.py",
                patron_inseguro='"dev-secret"',
                familia="SECRET",
            )
        ],
    )
    controller = AuditorController()
    controller.cfg = cfg
    controller.target_root = root
    controller.evidence_base = tmp_path / "evidence"
    controller.evidence_base.mkdir()
    return controller, source


def test_resuelve_archivo_del_hallazgo_sin_receta(tmp_path):
    controller, source = _controller_with_p2(tmp_path)

    result = controller.resolve_ai_source({
        "id": "P2-SECRET-DEMO",
        "control": "Secret fallback",
        "tipo_control": "source_contains",
        "estado": "HALLAZGO",
    })

    assert result["archivo"] == "config/security.py"
    assert Path(result["path"]) == source
    assert result["confianza"] == "alta"
    assert result["tiene_receta"] is False


def test_prioriza_archivo_explicito_en_evidencia_del_hallazgo(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    source = root / "src" / "cors.py"
    source.parent.mkdir(parents=True)
    source.write_text("def cors(): pass\n", encoding="utf-8")

    controller = AuditorController()
    controller.cfg = ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
    )
    controller.target_root = root

    result = controller.resolve_ai_source({
        "id": "P2-CORS-DYNAMIC",
        "control": "CORS",
        "evidencia": [
            {
                "tipo": "fuente_estatica",
                "archivo": "src/cors.py",
            }
        ],
    })

    assert result["archivo"] == "src/cors.py"
    assert result["origen"] == "evidencia del hallazgo"
    assert Path(result["path"]) == source


def test_generate_ai_carga_automaticamente_el_archivo_del_hallazgo(
    tmp_path,
    monkeypatch,
):
    controller, source = _controller_with_p2(tmp_path)
    captured = {}

    provider = AIProviderConfig(
        provider_id="test",
        provider_name="Test",
        model_id="test-model",
        model_name="Test Model",
        base_url="http://127.0.0.1:9",
        api_key="x",
        config_path="test",
    )

    proposal = AIRecipeProposal(
        id="IA-1",
        titulo="Corregir secreto",
        enfoque="MINIMA",
        explicacion="Usar configuración segura.",
        riesgo="BAJO",
        estrategia="replace_exact",
        buscar='"dev-secret"',
        reemplazar='os.environ["APP_SECRET"]',
        requiere_reinicio=False,
        consideraciones="demo",
    )

    def fake_refresh(*, silent=False):
        controller.ai_provider = provider

    def fake_generate(cfg, **kwargs):
        captured.update(kwargs)
        return [proposal, proposal, proposal], {"ok": True}, provider

    session = tmp_path / "session"

    monkeypatch.setattr(controller, "_refresh_ai_provider", fake_refresh)
    monkeypatch.setattr(
        "auditor_bola.qt_ui.controller.buscar_conocimiento",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "auditor_bola.qt_ui.controller.generar_tres_recetas",
        fake_generate,
    )
    monkeypatch.setattr(
        "auditor_bola.qt_ui.controller.guardar_sesion_ia",
        lambda *args, **kwargs: session,
    )

    class ImmediatePool:
        def start(self, worker):
            worker.run()

    controller.pool = ImmediatePool()

    controller.generate_ai({
        "id": "P2-SECRET-DEMO",
        "control": "Secret fallback",
        "tipo_control": "source_contains",
        "estado": "HALLAZGO",
    })

    assert captured["source_relative"] == "config/security.py"
    assert '"dev-secret"' in captured["source_text"]
    assert (
        captured["metadata_hallazgo"]["archivo_cargado_ia"]["archivo"]
        == "config/security.py"
    )
    assert controller.ai_source_relative == "config/security.py"
    assert controller.ai_source_hash == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()


def test_no_aplica_receta_ia_si_archivo_cambio_despues_de_cargar(
    tmp_path,
):
    controller, source = _controller_with_p2(tmp_path)
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()

    controller.ai_target_row = {
        "id": "P2-SECRET-DEMO",
        "control": "Secret fallback",
        "tipo_control": "source_contains",
    }
    controller.ai_source_relative = "config/security.py"
    controller.ai_source_hash = original_hash
    controller.ai_proposals = [
        AIRecipeProposal(
            id="IA-1",
            titulo="Corregir secreto",
            enfoque="MINIMA",
            explicacion="demo",
            riesgo="BAJO",
            estrategia="replace_exact",
            buscar='"dev-secret"',
            reemplazar='"safe"',
            requiere_reinicio=False,
            consideraciones="demo",
        )
    ]

    source.write_text(
        'SECRET_KEY = "otro-valor"\n',
        encoding="utf-8",
    )

    errors = []
    controller.error_message.connect(
        lambda title, message: errors.append((title, message))
    )

    controller.apply_ai_proposal(0)

    assert errors
    assert errors[-1][0] == "El archivo cambió"
    assert "regener" in errors[-1][1].lower()
    assert controller.cfg.correcciones == []
