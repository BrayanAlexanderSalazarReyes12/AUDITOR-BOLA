"""Controlador Qt que conecta la interfaz profesional con el motor Aegis."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from ..ai_recipes import (
    AIRecipeProposal,
    cargar_configuracion_opencode,
    generar_tres_recetas,
    guardar_seleccion_ia,
    guardar_sesion_ia,
    propuesta_a_correccion,
)
from ..app_paths import default_config_dir, default_evidence_dir
from ..config import ConfigObjetivo, RuntimeConfig, cargar_config
from ..cycle import (
    ciclo_correctivo,
    controles_hallazgo,
    corregir_controles,
    verificar_control,
)
from ..process_manager import LocalTargetProcess
from ..profile_builder import (
    build_profile_draft,
    detect_project,
    detect_runtime_profile,
    save_profile_draft,
)
from ..remediation_knowledge import (
    buscar_conocimiento,
    crear_conocimiento_respaldo_verificado,
    guardar_conocimiento,
)
from ..runner import diagnosticar, filas_gui


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(object)


class Worker(QRunnable):
    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn()
        except Exception as exc:
            self.signals.error.emit(exc)
            return
        self.signals.finished.emit(result)


class AuditorController(QObject):
    state_changed = Signal()
    results_changed = Signal(list)
    busy_changed = Signal(bool, str)
    task_progress = Signal(int, str)
    log_message = Signal(str)
    error_message = Signal(str, str)
    info_message = Signal(str, str)
    ai_proposals_changed = Signal(list)
    evidence_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_path: Path | None = None
        self.target_root: Path | None = None
        self.evidence_base = default_evidence_dir().resolve()
        self.evidence_base.mkdir(parents=True, exist_ok=True)

        self.cfg: ConfigObjetivo | None = None
        self.resultado: dict | None = None
        self.rows: list[dict] = []
        self.proceso: LocalTargetProcess | None = None

        self.ai_provider = None
        self.ai_proposals: list[AIRecipeProposal] = []
        self.ai_session_dir: Path | None = None
        self.ai_source_relative: str | None = None
        self.ai_target_row: dict | None = None

        self.pool = QThreadPool.globalInstance()

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _run_async(
        self,
        label: str,
        fn: Callable[[], Any],
        on_success: Callable[[Any], None] | None = None,
    ) -> None:
        self.busy_changed.emit(True, label)
        self.log_message.emit(label)

        worker = Worker(fn)

        def finished(result):
            self.busy_changed.emit(False, "Listo")
            if on_success:
                on_success(result)
            self.state_changed.emit()

        def failed(exc):
            self.busy_changed.emit(False, "Error")
            self.log_message.emit(f"ERROR: {exc}")
            self.error_message.emit("Operación no completada", str(exc))
            self.state_changed.emit()

        worker.signals.finished.connect(finished)
        worker.signals.error.connect(failed)
        self.pool.start(worker)

    @staticmethod
    def _runtime_key(data: dict) -> str:
        return json.dumps(
            {
                "modo": data.get("modo"),
                "comando_inicio": data.get("comando_inicio") or [],
                "comando_inicio_por_so": (
                    data.get("comando_inicio_por_so") or {}
                ),
                "directorio_trabajo": (
                    data.get("directorio_trabajo") or "."
                ),
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    def _augment_runtime_from_target(self) -> None:
        """Complementa perfiles antiguos con runtimes detectados hoy."""
        if not self.cfg or not self.target_root:
            return

        current = self.cfg.runtime

        try:
            detected_raw, detected_url = detect_runtime_profile(
                self.target_root
            )
        except Exception as exc:
            self.log_message.emit(
                "No se pudo revalidar el runtime del proyecto: "
                f"{exc}"
            )
            return

        current_data = asdict(current)
        current_key = self._runtime_key(current_data)

        detected_primary = dict(detected_raw)
        detected_alternatives = list(
            detected_primary.pop("alternativas", []) or []
        )
        candidates = [
            detected_primary,
            *[
                dict(item)
                for item in detected_alternatives
                if isinstance(item, dict)
            ],
        ]

        known = {
            self._runtime_key(item)
            for item in (current.alternativas or [])
            if isinstance(item, dict)
        }
        known.add(current_key)

        added: list[str] = []

        for candidate in candidates:
            candidate.setdefault("alternativas", [])
            key = self._runtime_key(candidate)

            if key in known:
                if key == current_key:
                    if not current.nombre:
                        current.nombre = str(
                            candidate.get("nombre") or ""
                        )
                    if not current.origen:
                        current.origen = str(
                            candidate.get("origen") or ""
                        )
                    if not current.base_url:
                        current.base_url = str(
                            candidate.get("base_url")
                            or self.cfg.base_url
                            or detected_url
                            or ""
                        )
                continue

            mode = str(candidate.get("modo") or "process").lower()
            start = candidate.get("comando_inicio") or []
            per_os = candidate.get("comando_inicio_por_so") or {}

            if mode == "external" or (not start and not per_os):
                continue

            current.alternativas.append(candidate)
            known.add(key)
            added.append(
                str(
                    candidate.get("nombre")
                    or (start[0] if start else "runtime alternativo")
                )
            )

        if not current.base_url:
            current.base_url = (
                self.cfg.base_url
                or str(detected_url or "")
            )

        if added:
            self.log_message.emit(
                "Perfil de runtime complementado automáticamente: "
                + ", ".join(added)
            )

    def _ensure_process(self) -> LocalTargetProcess:
        if not self.cfg:
            raise RuntimeError("Carga primero un perfil JSON.")
        if not self.target_root:
            raise RuntimeError("Carga primero la carpeta de código fuente.")

        if self.proceso is None:
            self._augment_runtime_from_target()
            self.proceso = LocalTargetProcess(
                self.target_root,
                self.cfg.runtime,
            )
        return self.proceso

    def process_running(self) -> bool:
        return bool(self.proceso and self.proceso.is_running())

    def restart_callback(self):
        if not self.cfg:
            return None
        if self.cfg.runtime.modo == "external":
            return None
        process = self._ensure_process()
        return process.restart

    # ------------------------------------------------------------------
    # Carga y perfiles
    # ------------------------------------------------------------------
    def load_profile(self, path: str | Path) -> None:
        profile = Path(path).expanduser().resolve()
        cfg = cargar_config(profile)
        self.config_path = profile
        self.cfg = cfg
        self.proceso = None
        self.log_message.emit(f"Perfil cargado: {profile}")
        self._refresh_ai_provider(silent=True)
        self.state_changed.emit()

    def load_target(self, path: str | Path) -> None:
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(root)
        self.target_root = root
        self.proceso = None
        self.log_message.emit(f"Aplicación cargada: {root}")
        self.state_changed.emit()

    def set_evidence_base(self, path: str | Path) -> None:
        root = Path(path).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.evidence_base = root
        self.log_message.emit(f"Evidencias: {root}")
        self.evidence_changed.emit()
        self.state_changed.emit()

    def auto_profile(
        self,
        target_root: str | Path,
        destination: str | Path | None = None,
    ) -> Path:
        root = Path(target_root).expanduser().resolve()
        detection = detect_project(root)
        draft = build_profile_draft(detection)

        if destination is None:
            destination = default_config_dir() / f"{draft['sistema']}.json"

        saved = save_profile_draft(draft, destination)
        self.target_root = root
        self.load_profile(saved)
        self.log_message.emit(
            "Auto-configuración completada: "
            f"{len(detection.routes)} endpoint(s) candidato(s)."
        )
        return saved

    def profile_dict(self) -> dict:
        if not self.config_path or not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def detected_metadata(self) -> dict:
        return dict(self.profile_dict().get("metadata_detectada") or {})

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------
    def _apply_runtime_status(self, status: dict) -> None:
        if not self.cfg:
            return

        runtime_url = str(status.get("base_url") or "").rstrip("/")
        if runtime_url:
            self.cfg.base_url = runtime_url

        name = status.get("nombre") or "runtime detectado"
        origin = status.get("origen") or "-"
        command = status.get("comando_inicio") or []
        command_text = " ".join(str(item) for item in command)

        self.log_message.emit(
            f"Runtime seleccionado: {name} · origen={origin}"
            + (
                f" · comando={command_text}"
                if command_text
                else ""
            )
        )

        discarded = status.get("alternativas_descartadas") or []
        for item in discarded:
            self.log_message.emit(
                f"Runtime descartado: {item}"
            )

        cleanup = status.get("limpieza_previa") or []
        for item in cleanup:
            self.log_message.emit(
                f"Limpieza previa: {item}"
            )

        if runtime_url:
            self.log_message.emit(
                f"Base URL activa: {runtime_url}"
            )

    def start_target(self) -> None:
        def work():
            process = self._ensure_process()
            return process.start(
                progress_callback=lambda value, message: (
                    self.task_progress.emit(value, message)
                ),
            )

        def success(status):
            self._apply_runtime_status(status or {})
            self.log_message.emit("Objetivo iniciado.")

        self._run_async(
            "Iniciando aplicación objetivo…",
            work,
            success,
        )

    def stop_target(self) -> None:
        if not self.proceso or not self.proceso.has_started():
            self.log_message.emit(
                "No hay una aplicación iniciada por Aegis para detener."
            )
            self.state_changed.emit()
            return

        def work():
            self.proceso.stop()
            return True

        self._run_async(
            "Deteniendo aplicación objetivo…",
            work,
            lambda _result: self.log_message.emit("Objetivo detenido."),
        )

    def restart_target(self) -> None:
        def work():
            process = self._ensure_process()
            return process.restart()

        def success(status):
            self._apply_runtime_status(status or {})
            self.log_message.emit("Objetivo reiniciado.")

        self._run_async(
            "Reiniciando aplicación objetivo…",
            work,
            success,
        )

    # ------------------------------------------------------------------
    # Auditoría
    # ------------------------------------------------------------------
    def diagnose(self) -> None:
        if not self.cfg:
            self.error_message.emit(
                "Falta el perfil",
                "Carga o genera primero el perfil JSON.",
            )
            return

        def work():
            return diagnosticar(
                self.cfg,
                self.target_root,
                progress_callback=lambda value, message: (
                    self.task_progress.emit(value, message)
                ),
            )

        def success(result):
            self.resultado = result
            self.rows = filas_gui(result)
            self.results_changed.emit(self.rows)
            findings = sum(
                row.get("estado") == "HALLAZGO"
                for row in self.rows
            )
            self.log_message.emit(
                f"Diagnóstico completado: {findings} hallazgo(s)."
            )

        self._run_async(
            "Ejecutando auditoría Pilar 1 + Pilar 2…",
            work,
            success,
        )

    def verify_row(self, row: dict) -> None:
        if not self.cfg:
            return

        selector = {
            key: row.get(key)
            for key in ("cuenta", "metodo", "ruta", "tipo_control")
        }

        def work():
            return verificar_control(
                self.cfg,
                row["id"],
                self.target_root,
                evidence_base=self.evidence_base,
                selector=selector,
            )

        def success(payload):
            self.info_message.emit(
                "Verificación completada",
                f"{row['id']}: {payload.get('estado')}",
            )
            self.evidence_changed.emit()
            self.diagnose()

        self._run_async(
            f"Verificando {row['id']}…",
            work,
            success,
        )

    def correct_row(self, row: dict) -> None:
        if not self.cfg or not self.target_root:
            self.error_message.emit(
                "Faltan datos",
                "Carga el perfil y la carpeta del proyecto.",
            )
            return

        selector = {
            key: row.get(key)
            for key in ("cuenta", "metodo", "ruta", "tipo_control")
        }

        def work():
            return ciclo_correctivo(
                self.cfg,
                row["id"],
                self.target_root,
                evidence_base=self.evidence_base,
                reiniciar=self.restart_callback(),
                selector=selector,
            )

        def success(payload):
            state = payload.get("estado_final") or "DESCONOCIDO"
            self.info_message.emit(
                "Resultado de corrección",
                f"{row['id']}: {state}",
            )
            self.log_message.emit(
                f"Corrección {row['id']}: {state}"
            )
            self.evidence_changed.emit()
            self.diagnose()

        self._run_async(
            f"Corrigiendo y verificando {row['id']}…",
            work,
            success,
        )

    def correct_all(self) -> None:
        if not self.cfg or not self.target_root or not self.resultado:
            self.error_message.emit(
                "Sin diagnóstico",
                "Ejecuta primero la auditoría P1 + P2.",
            )
            return

        control_ids = controles_hallazgo(self.resultado)
        if not control_ids:
            self.info_message.emit(
                "Sin hallazgos",
                "No hay controles en HALLAZGO.",
            )
            return

        def work():
            return corregir_controles(
                self.cfg,
                control_ids,
                self.target_root,
                evidence_base=self.evidence_base,
                reiniciar=self.restart_callback(),
            )

        def success(items):
            corrected = sum(
                item.get("estado_final") == "CORREGIDO"
                for item in items
            )
            self.info_message.emit(
                "Corrección por lote",
                f"{corrected}/{len(items)} control(es) corregido(s).",
            )
            self.evidence_changed.emit()
            self.diagnose()

        self._run_async(
            f"Corrigiendo {len(control_ids)} control(es)…",
            work,
            success,
        )

    # ------------------------------------------------------------------
    # IA
    # ------------------------------------------------------------------
    def _refresh_ai_provider(self, silent: bool = False) -> None:
        try:
            self.ai_provider = cargar_configuracion_opencode()
        except Exception as exc:
            self.ai_provider = None
            if not silent:
                self.error_message.emit(
                    "Proveedor IA no disponible",
                    str(exc),
                )

    def ai_status(self) -> tuple[bool, str]:
        if self.ai_provider:
            return True, self.ai_provider.model_name
        return False, "No configurada"

    def generate_ai(
        self,
        row: dict,
        source_path: str | Path,
    ) -> None:
        if not self.cfg or not self.target_root:
            self.error_message.emit(
                "Faltan datos",
                "Carga el perfil y el código fuente.",
            )
            return

        source = Path(source_path).expanduser().resolve()
        try:
            relative = source.relative_to(self.target_root).as_posix()
        except ValueError:
            self.error_message.emit(
                "Archivo fuera del proyecto",
                "El archivo seleccionado debe pertenecer al proyecto objetivo.",
            )
            return

        source_text = source.read_text(encoding="utf-8", errors="replace")
        self._refresh_ai_provider(silent=False)
        if not self.ai_provider:
            return

        knowledge = buscar_conocimiento(
            control_id=row["id"],
            descripcion=row.get("control"),
            tipo_control=row.get("tipo_control"),
            source_text=source_text,
            extension=source.suffix.lower(),
        )
        reusable = (
            knowledge[0].public_dict()
            if knowledge
            else None
        )

        def work():
            proposals, context, provider = generar_tres_recetas(
                self.cfg,
                control_id=row["id"],
                descripcion=row.get("control") or row["id"],
                detalle=row.get("detalle") or "",
                source_relative=relative,
                source_text=source_text,
                provider=self.ai_provider,
                metadata_hallazgo=row,
                matriz_pruebas=[
                    item
                    for item in self.rows
                    if item.get("id") == row.get("id")
                ],
                conocimiento_reutilizable=reusable,
            )
            session = guardar_sesion_ia(
                self.evidence_base,
                contexto=context,
                propuestas=proposals,
                provider=provider,
            )
            return proposals, session

        def success(payload):
            proposals, session = payload
            self.ai_proposals = list(proposals)
            self.ai_session_dir = Path(session)
            self.ai_source_relative = relative
            self.ai_target_row = dict(row)
            self.ai_proposals_changed.emit(
                [proposal.as_dict() for proposal in proposals]
            )
            self.log_message.emit(
                "Gemma generó tres recetas para "
                f"{row['id']}."
            )

        self._run_async(
            f"Generando recetas IA para {row['id']}…",
            work,
            success,
        )

    def apply_ai_proposal(self, index: int) -> None:
        if (
            not self.cfg
            or not self.target_root
            or self.ai_target_row is None
            or self.ai_source_relative is None
            or index < 0
            or index >= len(self.ai_proposals)
        ):
            self.error_message.emit(
                "Propuesta no disponible",
                "Genera y selecciona primero una propuesta IA.",
            )
            return

        proposal = self.ai_proposals[index]
        row = self.ai_target_row
        correction = propuesta_a_correccion(
            proposal,
            control_id=row["id"],
            source_relative=self.ai_source_relative,
        )

        # Sustituir sólo la receta del control actual en memoria.
        self.cfg.correcciones = [
            item
            for item in self.cfg.correcciones
            if item.control_id != row["id"]
        ]
        self.cfg.correcciones.append(correction)

        selector = {
            key: row.get(key)
            for key in ("cuenta", "metodo", "ruta", "tipo_control")
        }

        def work():
            result = ciclo_correctivo(
                self.cfg,
                row["id"],
                self.target_root,
                evidence_base=self.evidence_base,
                reiniciar=self.restart_callback(),
                selector=selector,
            )

            if self.ai_session_dir:
                guardar_seleccion_ia(
                    self.ai_session_dir,
                    propuesta=proposal,
                    correccion=correction,
                    resultado=result,
                )

            if result.get("estado_final") == "CORREGIDO":
                knowledge = crear_conocimiento_respaldo_verificado(
                    control_id=row["id"],
                    descripcion=row.get("control"),
                    tipo_control=row.get("tipo_control"),
                    extension=Path(self.ai_source_relative).suffix.lower(),
                )
                guardar_conocimiento(
                    knowledge,
                    caso_exitoso={
                        "control_id": row["id"],
                        "tipo_control": row.get("tipo_control"),
                        "archivo_extension": Path(
                            self.ai_source_relative
                        ).suffix.lower(),
                        "resultado": "CORREGIDO",
                    },
                )
            return result

        def success(result):
            state = result.get("estado_final") or "DESCONOCIDO"
            self.info_message.emit(
                "Resultado de receta IA",
                f"{row['id']}: {state}",
            )
            self.evidence_changed.emit()
            self.diagnose()

        self._run_async(
            f"Aplicando receta {proposal.enfoque} y verificando…",
            work,
            success,
        )
