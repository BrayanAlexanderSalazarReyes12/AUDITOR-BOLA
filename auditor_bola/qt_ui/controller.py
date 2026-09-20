"""Controlador Qt que conecta la interfaz profesional con el motor Aegis."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from ..ai_recipes import (
    AIRecipeProposal,
    cargar_configuracion_ia,
    cargar_perfil_ia,
    duplicar_perfil_ia,
    eliminar_perfil_ia,
    guardar_perfil_ia,
    importar_configuracion_opencode_a_aegis,
    listar_perfiles_ia,
    seleccionar_perfil_ia,
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
        # Mantiene vivos QRunnable/WorkerSignals hasta recibir finished/error.
        # Sin esta referencia, algunas ejecuciones largas podían llegar al
        # último progreso pero perder la señal final y dejar el overlay en 100%.
        self._active_workers: list[Worker] = []

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
        self._active_workers.append(worker)

        def release_worker() -> None:
            try:
                self._active_workers.remove(worker)
            except ValueError:
                pass

        def finished(result):
            try:
                if on_success:
                    on_success(result)
                # El 100% pertenece a la finalización real del Worker, no al
                # motor en segundo plano. Así 100% implica que la UI ya puede
                # cerrar el overlay.
                self.task_progress.emit(100, "Operación completada.")
                self.busy_changed.emit(False, "Listo")
            except Exception as exc:
                self.busy_changed.emit(False, "Error")
                self.log_message.emit(
                    f"ERROR al finalizar la operación: {exc}"
                )
                self.error_message.emit(
                    "Operación no completada",
                    str(exc),
                )
            finally:
                release_worker()
                self.state_changed.emit()

        def failed(exc):
            try:
                self.busy_changed.emit(False, "Error")
                self.log_message.emit(f"ERROR: {exc}")
                self.error_message.emit(
                    "Operación no completada",
                    str(exc),
                )
            finally:
                release_worker()
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

    @staticmethod
    def _runtime_plan_payload(runtime: RuntimeConfig) -> dict:
        primary = asdict(runtime)
        alternatives = list(primary.pop("alternativas", []) or [])
        return {
            "preferencia": runtime.preferencia_arranque or "auto",
            "fallback_local": bool(runtime.permitir_fallback_local),
            "principal": {
                "nombre": primary.get("nombre"),
                "modo": primary.get("modo"),
                "origen": primary.get("origen"),
                "descripcion": primary.get("descripcion_ejecucion"),
                "comando_inicio": primary.get("comando_inicio"),
                "comando_inicio_por_so": primary.get(
                    "comando_inicio_por_so"
                ),
                "comandos_preparacion": primary.get(
                    "comandos_preparacion"
                ),
                "directorio_trabajo": primary.get(
                    "directorio_trabajo"
                ),
                "base_url": primary.get("base_url"),
            },
            "alternativas": [
                {
                    "nombre": item.get("nombre"),
                    "modo": item.get("modo"),
                    "origen": item.get("origen"),
                    "descripcion": item.get("descripcion_ejecucion"),
                    "comando_inicio": item.get("comando_inicio"),
                    "comando_inicio_por_so": item.get(
                        "comando_inicio_por_so"
                    ),
                    "comandos_preparacion": item.get(
                        "comandos_preparacion"
                    ),
                    "directorio_trabajo": item.get(
                        "directorio_trabajo"
                    ),
                    "base_url": item.get("base_url"),
                }
                for item in alternatives
                if isinstance(item, dict)
            ],
        }

    def _persist_runtime_plan(self) -> None:
        """Mantiene config/*.json alineado con el plan real de ejecución."""
        if (
            not self.cfg
            or not self.config_path
            or not self.config_path.exists()
        ):
            return

        try:
            payload = json.loads(
                self.config_path.read_text(encoding="utf-8")
            )
            if not isinstance(payload, dict):
                return

            payload["runtime"] = asdict(self.cfg.runtime)
            payload["base_url"] = self.cfg.base_url
            metadata = dict(payload.get("metadata_detectada") or {})
            metadata["plan_ejecucion"] = self._runtime_plan_payload(
                self.cfg.runtime
            )
            payload["metadata_detectada"] = metadata
            self.config_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except (OSError, json.JSONDecodeError) as exc:
            self.log_message.emit(
                "No se pudo actualizar el plan de ejecución del perfil: "
                f"{exc}"
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

                    detected_base = str(
                        candidate.get("base_url")
                        or detected_url
                        or ""
                    ).rstrip("/")
                    previous_base = str(current.base_url or "").rstrip("/")
                    auto_origins = {
                        "python-project",
                        "package.json",
                        "java-project",
                        "dotnet-project",
                        "composer.json",
                        "Cargo.toml",
                        "go.mod",
                        "mix.exs",
                        "Package.swift",
                        "compose.yml",
                        "compose.yaml",
                        "docker-compose.yml",
                        "docker-compose.yaml",
                    }
                    origin = str(
                        current.origen
                        or candidate.get("origen")
                        or ""
                    )

                    # Perfiles antiguos podían guardar 127.0.0.1:8080 de forma
                    # genérica para Docker aunque el proyecto publicara otro
                    # puerto. Si el runtime fue autodetectado y sigue siendo la
                    # misma estrategia, refrescamos esa URL sin obligar al
                    # usuario a regenerar el perfil.
                    if (
                        detected_base
                        and origin in auto_origins
                        and detected_base != previous_base
                    ):
                        if (
                            not self.cfg.base_url
                            or str(self.cfg.base_url).rstrip("/")
                            == previous_base
                        ):
                            self.cfg.base_url = detected_base
                        current.base_url = detected_base
                        self.log_message.emit(
                            "Base URL del runtime actualizada por detección: "
                            f"{previous_base or '-'} → {detected_base}"
                        )
                    elif not current.base_url:
                        current.base_url = (
                            detected_base
                            or self.cfg.base_url
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

        self._persist_runtime_plan()

    def _enforce_profile_base_url(self) -> None:
        """Sincroniza runtimes con la IP/puerto autorizados por config JSON."""
        if not self.cfg:
            return

        authorized = str(
            self.cfg.base_url or ""
        ).strip().rstrip("/")
        if not authorized:
            return

        runtime = self.cfg.runtime
        runtime.base_url = authorized

        for item in runtime.alternativas or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("modo") or "process").lower() == "external":
                continue
            item["base_url"] = authorized

    def _ensure_process(self) -> LocalTargetProcess:
        if not self.cfg:
            raise RuntimeError("Carga primero un perfil JSON.")
        if not self.target_root:
            raise RuntimeError("Carga primero la carpeta de código fuente.")

        if self.proceso is None:
            self._augment_runtime_from_target()
            self._enforce_profile_base_url()
            self._persist_runtime_plan()
            self.proceso = LocalTargetProcess(
                self.target_root,
                self.cfg.runtime,
                authorized_base_url=self.cfg.base_url,
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
        if self.target_root:
            self._augment_runtime_from_target()
        self._refresh_ai_provider(silent=True)
        self.state_changed.emit()

    def load_target(self, path: str | Path) -> None:
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(root)
        self.target_root = root
        self.proceso = None
        self.log_message.emit(f"Aplicación cargada: {root}")
        if self.cfg:
            self._augment_runtime_from_target()
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
        name = status.get("nombre") or "runtime detectado"
        origin = status.get("origen") or "-"
        mode = str(status.get("modo") or "")
        command = status.get("comando_inicio") or []

        authorized_profile_url = str(
            self.cfg.base_url or ""
        ).strip().rstrip("/")

        if runtime_url and not authorized_profile_url:
            self.cfg.base_url = runtime_url
            authorized_profile_url = runtime_url

            # Si no había URL autorizada, el runtime descubierto se convierte
            # en la URL del perfil.
            # un puerto real distinto (ej. 5000 -> 5050), guardar ese valor en
            # el perfil para no repetir la detección equivocada en el próximo
            # arranque de Aegis.
        if authorized_profile_url:
            current = self.cfg.runtime
            current.base_url = authorized_profile_url
            for item in current.alternativas or []:
                if not isinstance(item, dict):
                    continue
                if str(item.get("modo") or "process").lower() == "external":
                    continue
                item["base_url"] = authorized_profile_url
            self._persist_runtime_plan()

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
            self.ai_provider = cargar_configuracion_ia()
        except Exception as exc:
            self.ai_provider = None
            if not silent:
                self.error_message.emit(
                    "Proveedor IA no disponible",
                    str(exc),
                )

    def ai_status(self) -> tuple[bool, str]:
        if self.ai_provider is None:
            self._refresh_ai_provider(silent=True)
        if self.ai_provider:
            label = (
                self.ai_provider.profile_name
                or self.ai_provider.model_name
            )
            return True, label
        return False, "No configurada"

    def ai_profiles(self) -> list[dict]:
        try:
            return listar_perfiles_ia()
        except Exception as exc:
            self.log_message.emit(
                f"No fue posible listar perfiles IA: {exc}"
            )
            return []

    def ai_settings(self) -> dict:
        if not self.ai_provider:
            self._refresh_ai_provider(silent=True)
        if not self.ai_provider:
            return {
                "enabled": False,
                "profile_id": "",
                "profile_name": "",
                "provider_name": "",
                "model_id": "lab-coder",
                "model_name": "",
                "base_url": "",
                "config_path": "",
            }
        data = self.ai_provider.public_dict()
        data["enabled"] = True
        return data

    def ai_profile_settings(self, profile_id: str) -> dict:
        for item in self.ai_profiles():
            if str(item.get("id") or "") == str(profile_id):
                return {
                    "enabled": True,
                    "profile_id": item.get("id"),
                    "profile_name": item.get("name"),
                    "provider_id": item.get("provider_id"),
                    "provider_name": item.get("provider_name"),
                    "model_id": item.get("model_id"),
                    "model_name": item.get("model_name"),
                    "base_url": item.get("base_url"),
                    "config_path": item.get("config_path"),
                    "has_api_key": item.get("has_api_key"),
                    "active": item.get("active"),
                }
        return {}

    def save_ai_settings(
        self,
        *,
        profile_name: str,
        base_url: str,
        model_id: str,
        api_key: str | None = None,
        profile_id: str | None = None,
    ) -> None:
        try:
            self.ai_provider = guardar_perfil_ia(
                profile_id=profile_id or None,
                profile_name=profile_name,
                base_url=base_url,
                model_id=model_id,
                api_key=api_key,
                provider_name=profile_name,
                set_active=True,
            )
        except Exception as exc:
            self.error_message.emit(
                "No se pudo guardar la IA",
                str(exc),
            )
            return

        self.info_message.emit(
            "Perfil IA guardado",
            f"'{self.ai_provider.profile_name}' quedó como proveedor IA activo.",
        )
        self.state_changed.emit()

    def select_ai_profile(self, profile_id: str) -> None:
        try:
            self.ai_provider = seleccionar_perfil_ia(profile_id)
        except Exception as exc:
            self.error_message.emit(
                "No se pudo activar el perfil IA",
                str(exc),
            )
            return
        self.log_message.emit(
            "Perfil IA activo: "
            f"{self.ai_provider.profile_name} · {self.ai_provider.model_id}"
        )
        self.state_changed.emit()

    def duplicate_ai_profile(self, profile_id: str) -> None:
        try:
            self.ai_provider = duplicar_perfil_ia(profile_id)
        except Exception as exc:
            self.error_message.emit(
                "No se pudo duplicar el perfil IA",
                str(exc),
            )
            return
        self.info_message.emit(
            "Perfil IA duplicado",
            f"Se creó '{self.ai_provider.profile_name}' y quedó activo.",
        )
        self.state_changed.emit()

    def delete_ai_profile(self, profile_id: str) -> None:
        try:
            active_id = eliminar_perfil_ia(profile_id)
            self.ai_provider = (
                cargar_perfil_ia(active_id)
                if active_id
                else None
            )
        except Exception as exc:
            self.error_message.emit(
                "No se pudo eliminar el perfil IA",
                str(exc),
            )
            return
        self.info_message.emit(
            "Perfil IA eliminado",
            (
                "Se activó automáticamente otro perfil."
                if self.ai_provider
                else "Ya no quedan perfiles IA locales configurados."
            ),
        )
        self.state_changed.emit()

    def import_ai_from_opencode(self) -> None:
        try:
            self.ai_provider = importar_configuracion_opencode_a_aegis()
        except Exception as exc:
            self.error_message.emit(
                "No se pudo importar OpenCode",
                str(exc),
            )
            return

        self.info_message.emit(
            "Proveedor IA importado",
            "La configuración de OpenCode se guardó como un perfil IA "
            "independiente y quedó activa.",
        )
        self.state_changed.emit()

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
