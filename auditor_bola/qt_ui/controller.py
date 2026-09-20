"""Controlador Qt que conecta la interfaz profesional con el motor Aegis."""

from __future__ import annotations

import hashlib
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
    generalizar_correccion_exitosa,
    propuesta_a_correccion,
)
from ..app_paths import default_config_dir, default_evidence_dir
from ..config import (
    ChequeoAcceso,
    ChequeoAgente,
    ChequeoPilar2,
    ConfigObjetivo,
    Endpoint,
    RuntimeConfig,
    cargar_config,
    construir_registro_pilar1,
)
from ..cycle import (
    ciclo_correctivo,
    controles_hallazgo,
    corregir_controles,
    verificar_control,
)
from ..language_detection import (
    detect_language_context,
    detect_source_language,
)
from ..process_manager import LocalTargetProcess
from ..p1_resolver import resolve_live_bola_candidates
from ..profile_builder import (
    build_profile_draft,
    detect_project,
    detect_runtime_profile,
    save_profile_draft,
)
from ..recipe_library import guardar_receta_biblioteca
from ..remediation_knowledge import (
    buscar_conocimiento,
    crear_conocimiento_respaldo_verificado,
    guardar_conocimiento,
)
from ..runner import diagnosticar, filas_gui
from ..source_locator import (
    resolver_archivo_fuente,
    resolver_contexto_fuente,
)


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
        # Estado real del runtime seleccionado en esta ejecución. Puede ser
        # distinto al runtime principal declarado en el JSON cuando se usa un
        # fallback (por ejemplo Docker -> Python).
        self.active_runtime_status: dict[str, Any] = {}

        self.ai_provider = None
        self.ai_proposals: list[AIRecipeProposal] = []
        self.ai_session_dir: Path | None = None
        self.ai_source_relative: str | None = None
        self.ai_source_hash: str | None = None
        self.ai_source_hashes: dict[str, str] = {}
        self.ai_source_resolution: dict[str, Any] | None = None
        self.ai_diagnosis: dict[str, Any] | None = None
        self.ai_target_row: dict | None = None
        self.ai_failed_attempts: dict[str, list[dict[str, Any]]] = {}
        self.ai_auto_regenerations: dict[str, int] = {}

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

        # Los perfiles auto-generados antiguos podían dejar Docker Compose
        # como runtime principal aunque el equipo no tuviera Docker. Si la
        # detección actual del mismo proyecto ya eligió explícitamente un
        # runtime local, promovemos ese runtime a principal en lugar de
        # conservar Docker y depender siempre del fallback.
        profile_payload = self.profile_dict()
        metadata_payload = dict(
            profile_payload.get("metadata_detectada") or {}
        )
        auto_generated = bool(
            metadata_payload.get("perfil_generado_automaticamente")
        )

        current_origin = str(current.origen or "").lower()
        current_name = str(current.nombre or "").lower()
        current_is_compose = (
            "docker" in current_name
            or current_origin in {
                "compose.yml",
                "compose.yaml",
                "docker-compose.yml",
                "docker-compose.yaml",
            }
        )

        detected_preference = str(
            detected_raw.get("preferencia_arranque") or ""
        ).lower()
        detected_mode = str(
            detected_raw.get("modo") or "process"
        ).lower()
        detected_origin = str(
            detected_raw.get("origen") or ""
        ).lower()
        detected_is_local = (
            detected_preference == "local"
            and detected_mode != "external"
            and "docker" not in detected_origin
            and "compose" not in detected_origin
        )

        if auto_generated and current_is_compose and detected_is_local:
            promoted = dict(detected_raw)
            alternatives = [
                dict(item)
                for item in (promoted.get("alternativas") or [])
                if isinstance(item, dict)
            ]
            current_as_alt = asdict(current)
            current_as_alt["alternativas"] = []
            current_key_before = self._runtime_key(current_as_alt)
            alt_keys = {
                self._runtime_key(item)
                for item in alternatives
            }
            if current_key_before not in alt_keys:
                alternatives.append(current_as_alt)
            promoted["alternativas"] = alternatives

            self.cfg.runtime = RuntimeConfig(**promoted)
            current = self.cfg.runtime

            detected_base = str(
                promoted.get("base_url")
                or detected_url
                or ""
            ).strip().rstrip("/")
            previous_base = str(
                self.cfg.base_url or ""
            ).strip().rstrip("/")

            # En un perfil generado automáticamente, una URL genérica del
            # runtime Docker antiguo no debe imponerse al runtime local
            # recién detectado. Si el runtime local tiene evidencia de URL,
            # la promovemos también.
            if detected_base:
                self.cfg.base_url = detected_base

            self.log_message.emit(
                "Runtime principal actualizado por entorno local: "
                f"{current_name or 'Docker/servicio'} → "
                f"{current.nombre or current.modo}"
                + (
                    f" · Base URL {previous_base or '-'} → "
                    f"{self.cfg.base_url or '-'}"
                    if previous_base != str(self.cfg.base_url or "")
                    else ""
                )
            )
            self._persist_runtime_plan()

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

                    # La base_url del JSON de config es la autoridad de
                    # IP/puerto permitidos para el objetivo. La detección del
                    # código puede decidir *cómo* arrancar, pero nunca cambiar
                    # esa IP/puerto cuando el perfil ya la declaró.
                    authorized = str(
                        self.cfg.base_url or ""
                    ).strip().rstrip("/")

                    if authorized:
                        if previous_base != authorized:
                            self.log_message.emit(
                                "Base URL del runtime sincronizada con config: "
                                f"{previous_base or '-'} → {authorized}"
                            )
                        current.base_url = authorized
                    elif (
                        detected_base
                        and origin in auto_origins
                        and detected_base != previous_base
                    ):
                        self.cfg.base_url = detected_base
                        current.base_url = detected_base
                        self.log_message.emit(
                            "Base URL detectada para perfil sin URL declarada: "
                            f"{detected_base}"
                        )
                    elif not current.base_url:
                        current.base_url = detected_base or ""
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

        self._enforce_profile_base_url()
        self._persist_runtime_plan()

    def _augment_controls_from_target(self) -> None:
        """Completa perfiles antiguos con controles P1/P2 inferibles.

        P1 se reconstruye desde rutas + contratos expresados en tests,
        fixtures y datos semilla. P2 conserva las inferencias estáticas de
        alta confianza. Nunca se eliminan controles manuales existentes.
        """
        if not self.cfg or not self.target_root:
            return

        try:
            draft = build_profile_draft(
                detect_project(self.target_root)
            )
        except Exception as exc:
            self.log_message.emit(
                "No se pudieron inferir controles del proyecto: "
                f"{exc}"
            )
            return

        added_p1: list[str] = []
        added_p2: list[str] = []

        # --------------------------------------------------------------
        # Pilar 1: materializar las vistas ejecutables legacy y mantener
        # chequeos_pilar1 como registro canónico visible en el JSON.
        # --------------------------------------------------------------
        endpoint_keys = {
            (
                item.id_control or "P1-BOLA",
                item.metodo.upper(),
                item.ruta,
                str(item.id_prueba),
                item.propietario_esperado,
            )
            for item in self.cfg.endpoints
        }
        for raw in draft.get("endpoints") or []:
            if not isinstance(raw, dict):
                continue
            try:
                item = dict(raw)
                if "codigos_permitidos" in item:
                    item["codigos_permitidos"] = tuple(
                        item["codigos_permitidos"]
                    )
                endpoint = Endpoint(**item)
            except (TypeError, ValueError):
                continue
            key = (
                endpoint.id_control or "P1-BOLA",
                endpoint.metodo.upper(),
                endpoint.ruta,
                str(endpoint.id_prueba),
                endpoint.propietario_esperado,
            )
            if key in endpoint_keys:
                continue
            self.cfg.endpoints.append(endpoint)
            endpoint_keys.add(key)
            added_p1.append(
                endpoint.id_control or "P1-BOLA"
            )

        access_keys = {
            (
                item.id_control,
                item.cuenta,
                item.metodo.upper(),
                item.ruta,
            )
            for item in self.cfg.chequeos_acceso
        }
        for raw in draft.get("chequeos_acceso") or []:
            if not isinstance(raw, dict):
                continue
            try:
                item = dict(raw)
                if "codigos_permitidos" in item:
                    item["codigos_permitidos"] = tuple(
                        item["codigos_permitidos"]
                    )
                check = ChequeoAcceso(**item)
            except (TypeError, ValueError):
                continue
            key = (
                check.id_control,
                check.cuenta,
                check.metodo.upper(),
                check.ruta,
            )
            if key in access_keys:
                continue
            self.cfg.chequeos_acceso.append(check)
            access_keys.add(key)
            added_p1.append(check.id_control)

        agent_keys = {
            (
                item.id_control,
                item.cuenta,
                item.direct_ruta,
                item.agent_ruta,
            )
            for item in self.cfg.chequeos_agente
        }
        for raw in draft.get("chequeos_agente") or []:
            if not isinstance(raw, dict):
                continue
            try:
                check = ChequeoAgente(**dict(raw))
            except (TypeError, ValueError):
                continue
            key = (
                check.id_control,
                check.cuenta,
                check.direct_ruta,
                check.agent_ruta,
            )
            if key in agent_keys:
                continue
            self.cfg.chequeos_agente.append(check)
            agent_keys.add(key)
            added_p1.append(check.id_control)

        registry = list(self.cfg.chequeos_pilar1 or [])
        registry_keys = {
            (
                str(item.get("tipo") or ""),
                str(item.get("id_control") or ""),
                str(
                    item.get("ruta")
                    or item.get("direct_ruta")
                    or ""
                ),
                str(item.get("cuenta") or ""),
                str(item.get("metodo") or ""),
            )
            for item in registry
            if isinstance(item, dict)
        }
        for raw in draft.get("chequeos_pilar1") or []:
            if not isinstance(raw, dict):
                continue
            key = (
                str(raw.get("tipo") or ""),
                str(raw.get("id_control") or ""),
                str(
                    raw.get("ruta")
                    or raw.get("direct_ruta")
                    or ""
                ),
                str(raw.get("cuenta") or ""),
                str(raw.get("metodo") or ""),
            )
            if key in registry_keys:
                continue
            registry.append(dict(raw))
            registry_keys.add(key)

        if not registry:
            registry = construir_registro_pilar1(
                self.cfg.endpoints,
                self.cfg.chequeos_acceso,
                self.cfg.chequeos_agente,
            )
        self.cfg.chequeos_pilar1 = registry

        # --------------------------------------------------------------
        # Pilar 2.
        # --------------------------------------------------------------
        existing_p2 = {
            item.id_control
            for item in self.cfg.chequeos_pilar2
        }
        for raw in draft.get("chequeos_pilar2") or []:
            if not isinstance(raw, dict):
                continue
            control_id = str(raw.get("id_control") or "").strip()
            if not control_id or control_id in existing_p2:
                continue
            try:
                check = ChequeoPilar2(**raw)
            except TypeError as exc:
                self.log_message.emit(
                    f"Control inferido descartado {control_id}: {exc}"
                )
                continue
            self.cfg.chequeos_pilar2.append(check)
            existing_p2.add(control_id)
            added_p2.append(control_id)

        # Persistir también cuando no hubo controles nuevos: así un perfil
        # legacy obtiene chequeos_pilar1 como registro canónico.
        if self.config_path and self.config_path.exists():
            try:
                payload = json.loads(
                    self.config_path.read_text(encoding="utf-8")
                )
                if isinstance(payload, dict):
                    payload["chequeos_pilar1"] = list(
                        self.cfg.chequeos_pilar1
                    )
                    payload["endpoints"] = [
                        asdict(item)
                        for item in self.cfg.endpoints
                    ]
                    payload["chequeos_acceso"] = [
                        asdict(item)
                        for item in self.cfg.chequeos_acceso
                    ]
                    payload["chequeos_agente"] = [
                        asdict(item)
                        for item in self.cfg.chequeos_agente
                    ]
                    payload["chequeos_pilar2"] = [
                        asdict(item)
                        for item in self.cfg.chequeos_pilar2
                    ]

                    metadata = dict(
                        payload.get("metadata_detectada") or {}
                    )
                    draft_meta = dict(
                        draft.get("metadata_detectada") or {}
                    )
                    metadata["candidatos_pilar1"] = list(
                        draft_meta.get("candidatos_pilar1") or []
                    )
                    metadata["total_candidatos_pilar1"] = len(
                        metadata["candidatos_pilar1"]
                    )
                    metadata[
                        "controles_pilar1_inferidos_automaticamente"
                    ] = [
                        item
                        for item in (
                            draft_meta.get(
                                "controles_pilar1_inferidos_automaticamente"
                            )
                            or []
                        )
                    ]
                    metadata["total_controles_pilar1_activos"] = (
                        len(self.cfg.endpoints)
                        + len(self.cfg.chequeos_acceso)
                        + len(self.cfg.chequeos_agente)
                    )
                    metadata["total_controles_pilar2_activos"] = len(
                        self.cfg.chequeos_pilar2
                    )
                    metadata["total_controles_activos"] = (
                        metadata["total_controles_pilar1_activos"]
                        + metadata["total_controles_pilar2_activos"]
                    )
                    payload["metadata_detectada"] = metadata

                    self.config_path.write_text(
                        json.dumps(
                            payload,
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
            except (OSError, json.JSONDecodeError) as exc:
                self.log_message.emit(
                    "No se pudieron guardar los controles inferidos: "
                    f"{exc}"
                )

        if added_p1:
            self.log_message.emit(
                "Pilar 1 reconstruido automáticamente: "
                + ", ".join(dict.fromkeys(added_p1))
            )
        if added_p2:
            self.log_message.emit(
                "Pilar 2 inferido automáticamente: "
                + ", ".join(added_p2)
            )

    def _resolve_live_p1_candidates(self) -> int:
        """Resuelve candidatos P1 que requieren evidencia del servicio vivo."""
        if not self.cfg or not self.process_running():
            return 0

        metadata = self.detected_metadata()
        if not (metadata.get("candidatos_pilar1") or []):
            return 0

        active_url = str(
            self.active_runtime_status.get("base_url")
            or self.cfg.base_url
            or ""
        ).strip().rstrip("/")
        if not active_url:
            return 0

        try:
            resolved = resolve_live_bola_candidates(
                self.cfg,
                metadata,
                base_url=active_url,
            )
        except Exception as exc:
            self.log_message.emit(
                "No se pudieron resolver candidatos P1 con el objetivo vivo: "
                f"{exc}"
            )
            return 0

        if not resolved:
            return 0

        self.cfg.endpoints.extend(resolved)
        self.cfg.chequeos_pilar1 = construir_registro_pilar1(
            self.cfg.endpoints,
            self.cfg.chequeos_acceso,
            self.cfg.chequeos_agente,
        )

        if self.config_path and self.config_path.exists():
            try:
                payload = json.loads(
                    self.config_path.read_text(encoding="utf-8")
                )
                if isinstance(payload, dict):
                    payload["endpoints"] = [
                        asdict(item)
                        for item in self.cfg.endpoints
                    ]
                    payload["chequeos_pilar1"] = list(
                        self.cfg.chequeos_pilar1
                    )
                    meta = dict(
                        payload.get("metadata_detectada") or {}
                    )
                    live_items = list(
                        meta.get(
                            "controles_pilar1_resueltos_en_vivo"
                        )
                        or []
                    )
                    known_ids = {
                        str(item.get("id_control") or "")
                        for item in live_items
                        if isinstance(item, dict)
                    }
                    for endpoint in resolved:
                        if endpoint.id_control in known_ids:
                            continue
                        live_items.append(
                            {
                                "id_control": endpoint.id_control,
                                "tipo": "bola",
                                "metodo": endpoint.metodo,
                                "ruta": endpoint.ruta,
                                "id_prueba": endpoint.id_prueba,
                                "propietario_esperado": (
                                    endpoint.propietario_esperado
                                ),
                                "fuente": "objetivo-vivo-solo-lectura",
                            }
                        )
                    meta["controles_pilar1_resueltos_en_vivo"] = (
                        live_items
                    )
                    meta["total_controles_pilar1_activos"] = (
                        len(self.cfg.endpoints)
                        + len(self.cfg.chequeos_acceso)
                        + len(self.cfg.chequeos_agente)
                    )
                    meta["total_controles_activos"] = (
                        meta["total_controles_pilar1_activos"]
                        + len(self.cfg.chequeos_pilar2)
                    )
                    payload["metadata_detectada"] = meta
                    self.config_path.write_text(
                        json.dumps(
                            payload,
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
            except (OSError, json.JSONDecodeError) as exc:
                self.log_message.emit(
                    "No se pudo persistir el Pilar 1 resuelto en vivo: "
                    f"{exc}"
                )

        self.log_message.emit(
            "Pilar 1 resuelto con evidencia de solo lectura del objetivo: "
            + ", ".join(
                endpoint.id_control or "P1-BOLA"
                for endpoint in resolved
            )
        )
        return len(resolved)

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

    def detect_source_language_info(
        self,
        relative_path: str,
    ) -> dict:
        """Detecta lenguaje/framework del archivo cargado para la UI y la IA."""
        if not self.target_root or not relative_path:
            return {}
        root = self.target_root.resolve()
        path = (root / relative_path).resolve()
        if path == root or root not in path.parents or not path.is_file():
            return {}
        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            text = ""
        return detect_source_language(
            relative_path,
            text,
        ).as_dict()

    # ------------------------------------------------------------------
    # Carga y perfiles
    # ------------------------------------------------------------------
    def load_profile(self, path: str | Path) -> None:
        profile = Path(path).expanduser().resolve()
        cfg = cargar_config(profile)
        self.config_path = profile
        self.cfg = cfg
        self.ai_failed_attempts.clear()
        self.ai_auto_regenerations.clear()
        self.ai_source_hashes.clear()
        self.ai_diagnosis = None
        self.proceso = None
        self.active_runtime_status = {}
        self.log_message.emit(f"Perfil cargado: {profile}")
        if self.target_root:
            self._augment_runtime_from_target()
            self._augment_controls_from_target()
        else:
            self._enforce_profile_base_url()
            self._persist_runtime_plan()
        self._refresh_ai_provider(silent=True)
        self.state_changed.emit()

    def load_target(self, path: str | Path) -> None:
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(root)
        self.target_root = root
        self.ai_failed_attempts.clear()
        self.ai_auto_regenerations.clear()
        self.ai_source_hashes.clear()
        self.ai_diagnosis = None
        self.proceso = None
        self.active_runtime_status = {}
        self.log_message.emit(f"Aplicación cargada: {root}")
        if self.cfg:
            self._augment_runtime_from_target()
            self._augment_controls_from_target()
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

        self.active_runtime_status = dict(status or {})

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

        def success(_result):
            self.active_runtime_status = {}
            self.log_message.emit("Objetivo detenido.")

        self._run_async(
            "Deteniendo aplicación objetivo…",
            work,
            success,
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
    def _promote_matrix_rbac_findings(
        self,
        result: dict[str, Any],
    ) -> int:
        """Promueve hallazgos probables de matriz a controles RBAC activos.

        Solo se promociona cuando:
        - la matriz tenía una expectativa de denegación derivada de un
          candidato RBAC;
        - la cuenta de bajo privilegio obtuvo acceso real;
        - la prueba produjo una respuesta concluyente.
        """
        if not self.cfg:
            return 0

        matrix_rows = (
            result.get("pilar1", {}).get("matriz_acceso", [])
            if isinstance(result, dict)
            else []
        )
        if not isinstance(matrix_rows, list):
            return 0

        existing = {
            (
                check.cuenta,
                check.metodo.upper(),
                check.ruta,
            )
            for check in self.cfg.chequeos_acceso
        }
        added: list[ChequeoAcceso] = []

        for row in matrix_rows:
            if not isinstance(row, dict):
                continue
            if row.get("clasificacion") != "POSIBLE_HALLAZGO":
                continue
            if row.get("fuente_politica") != "candidato_rbac":
                continue
            if row.get("vulnerable") is not True:
                continue

            username = str(row.get("cuenta") or "").strip()
            method = str(row.get("metodo") or "").upper().strip()
            route = str(row.get("endpoint_detectado") or "").strip()
            if not username or not method or not route:
                continue

            key = (username, method, route)
            if key in existing:
                continue

            digest = hashlib.sha1(
                f"{method}|{route}|{username}".encode("utf-8")
            ).hexdigest()[:8].upper()

            source_files: list[str] = []
            evidence_notes = [
                "promovido desde matriz endpoint × usuario",
                (
                    f"HTTP {row.get('http_status')} permitió acceso a "
                    f"{username}"
                ),
                "expectativa RBAC inferida: acceso denegado",
            ]
            for candidate in self.cfg.candidatos_pilar1:
                if not isinstance(candidate, dict):
                    continue
                if str(candidate.get("familia") or "").upper() != "RBAC_ABAC":
                    continue
                if str(candidate.get("metodo") or "").upper() != method:
                    continue
                if str(candidate.get("ruta_detectada") or "") != route:
                    continue
                source_files = list(
                    candidate.get("archivos_fuente") or []
                )
                motive = str(candidate.get("motivo") or "").strip()
                if motive:
                    evidence_notes.append(motive)
                break

            check = ChequeoAcceso(
                id_control=f"P1-AUTO-MATRIX-RBAC-{digest}",
                nombre=(
                    "Acceso de bajo privilegio permitido por "
                    f"{method} {route}"
                ),
                cuenta=username,
                metodo=method,
                ruta=route,
                acceso_esperado=False,
                cuerpo=(
                    {}
                    if method in {"POST", "PUT", "PATCH"}
                    else None
                ),
                archivos_fuente=source_files,
                pistas_codigo=evidence_notes,
            )
            self.cfg.chequeos_acceso.append(check)
            added.append(check)
            existing.add(key)

        if not added:
            return 0

        self.cfg.chequeos_pilar1 = construir_registro_pilar1(
            self.cfg.endpoints,
            self.cfg.chequeos_acceso,
            self.cfg.chequeos_agente,
        )

        if self.config_path and self.config_path.exists():
            try:
                payload = json.loads(
                    self.config_path.read_text(encoding="utf-8")
                )
                if isinstance(payload, dict):
                    payload["chequeos_acceso"] = [
                        asdict(item)
                        for item in self.cfg.chequeos_acceso
                    ]
                    payload["chequeos_pilar1"] = list(
                        self.cfg.chequeos_pilar1
                    )
                    meta = dict(
                        payload.get("metadata_detectada") or {}
                    )
                    promoted = list(
                        meta.get(
                            "controles_pilar1_promovidos_desde_matriz"
                        )
                        or []
                    )
                    known = {
                        str(item.get("id_control") or "")
                        for item in promoted
                        if isinstance(item, dict)
                    }
                    for check in added:
                        if check.id_control in known:
                            continue
                        promoted.append(
                            {
                                "id_control": check.id_control,
                                "tipo": "acceso",
                                "cuenta": check.cuenta,
                                "metodo": check.metodo,
                                "ruta": check.ruta,
                                "fuente": "matriz-endpoint-usuario",
                                "confianza": "media",
                            }
                        )
                    meta[
                        "controles_pilar1_promovidos_desde_matriz"
                    ] = promoted
                    meta["total_controles_pilar1_activos"] = (
                        len(self.cfg.endpoints)
                        + len(self.cfg.chequeos_acceso)
                        + len(self.cfg.chequeos_agente)
                    )
                    meta["total_controles_activos"] = (
                        meta["total_controles_pilar1_activos"]
                        + len(self.cfg.chequeos_pilar2)
                    )
                    payload["metadata_detectada"] = meta
                    self.config_path.write_text(
                        json.dumps(
                            payload,
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
            except (OSError, json.JSONDecodeError) as exc:
                self.log_message.emit(
                    "No se pudieron persistir los controles promovidos "
                    f"desde la matriz: {exc}"
                )

        self.log_message.emit(
            "Matriz endpoint × usuario promovió "
            f"{len(added)} candidato(s) RBAC a controles P1 activos."
        )
        return len(added)

    def diagnose(self) -> None:
        if not self.cfg:
            self.error_message.emit(
                "Falta el perfil",
                "Carga o genera primero el perfil JSON.",
            )
            return

        if self.target_root:
            self._augment_controls_from_target()

        p1_total = (
            len(self.cfg.endpoints) * len(self.cfg.cuentas)
            + len(self.cfg.chequeos_acceso)
            + len(self.cfg.chequeos_agente)
        )
        p2_total = len(self.cfg.chequeos_pilar2)

        if p1_total == 0:
            self._resolve_live_p1_candidates()
            p1_total = (
                len(self.cfg.endpoints) * len(self.cfg.cuentas)
                + len(self.cfg.chequeos_acceso)
                + len(self.cfg.chequeos_agente)
            )

        missing: list[str] = []
        if p1_total == 0:
            missing.append("Pilar 1")
        if p2_total == 0:
            missing.append("Pilar 2")

        if missing:
            meta = self.detected_metadata()
            p1_candidates = int(
                meta.get("total_candidatos_pilar1") or 0
            )
            message = (
                "No se iniciará una auditoría P1 + P2 incompleta. "
                f"Falta cobertura ejecutable en {', '.join(missing)}. "
                f"P1 activos={p1_total}; P2 activos={p2_total}."
            )
            if p1_total == 0 and p1_candidates:
                message += (
                    f" Se detectaron {p1_candidates} candidato(s) de "
                    "Pilar 1, pero todavía no tienen evidencia suficiente "
                    "para ejecutarse automáticamente."
                )
            self.log_message.emit("Auditoría bloqueada: " + message)
            self.error_message.emit(
                "Cobertura de auditoría incompleta",
                message,
            )
            self.state_changed.emit()
            return

        def work():
            return diagnosticar(
                self.cfg,
                self.target_root,
                progress_callback=lambda value, message: (
                    self.task_progress.emit(value, message)
                ),
                require_both_pillars=True,
            )

        def success(result):
            promoted = self._promote_matrix_rbac_findings(result)
            self.resultado = result
            self.rows = filas_gui(result)
            self.results_changed.emit(self.rows)
            findings = sum(
                row.get("estado") == "HALLAZGO"
                for row in self.rows
            )
            matrix_vulnerable = sum(
                row.get("estado") == "VULNERABLE"
                for row in self.rows
            )
            message = (
                f"Diagnóstico completado: {findings} hallazgo(s)"
            )
            if matrix_vulnerable:
                message += (
                    f" + {matrix_vulnerable} vulnerabilidad(es) "
                    "señalada(s) por la matriz"
                )
            if promoted:
                message += (
                    f"; {promoted} candidato(s) promovido(s) a P1 activo"
                )
            self.log_message.emit(message + ".")

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

    @staticmethod
    def _candidate_file_from_component(value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        # Componentes P2 pueden representarse como "archivo:VARIABLE".
        # Solo se toma la parte izquierda cuando parece una ruta de archivo.
        head = text.split(":", 1)[0].strip()
        suffix = Path(head).suffix.lower()
        if suffix or Path(head).name.lower().startswith("dockerfile"):
            return head
        return None

    def resolve_ai_source(self, row: dict) -> dict[str, Any]:
        """Resuelve y valida el archivo que originó el hallazgo.

        La IA nunca debe generar un parche a ciegas. Primero se intenta usar
        el archivo explícito del hallazgo/evidencia y luego el localizador
        semántico del perfil. La selección manual queda únicamente como
        fallback cuando no existe evidencia suficiente.
        """
        if not self.cfg or not self.target_root:
            return {
                "archivo": None,
                "path": None,
                "confianza": "ninguna",
                "origen": "sin perfil/proyecto",
                "candidatos": [],
                "tiene_receta": False,
            }

        root = self.target_root.resolve()
        control_id = str(row.get("id") or "").strip()
        recipe = (
            self.cfg.correccion_por_control(control_id)
            if control_id
            else None
        )

        explicit: list[tuple[str, str]] = []

        def add_explicit(value: Any, origin: str) -> None:
            if not value:
                return
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    add_explicit(item, origin)
                return
            rel = str(value).replace("\\", "/").lstrip("./").strip()
            if rel and (rel, origin) not in explicit:
                explicit.append((rel, origin))

        add_explicit(row.get("archivo"), "hallazgo")
        add_explicit(row.get("archivos_fuente"), "hallazgo")
        add_explicit(
            self._candidate_file_from_component(row.get("componente")),
            "componente del hallazgo",
        )
        for evidence in row.get("evidencia") or []:
            if isinstance(evidence, dict):
                add_explicit(
                    evidence.get("archivo"),
                    "evidencia del hallazgo",
                )

        for relative, origin in explicit:
            candidate = (root / relative).resolve()
            if (
                candidate.is_file()
                and candidate != root
                and root in candidate.parents
            ):
                return {
                    "archivo": candidate.relative_to(root).as_posix(),
                    "path": str(candidate),
                    "confianza": "alta",
                    "origen": origin,
                    "candidatos": [
                        {
                            "archivo": candidate.relative_to(root).as_posix(),
                            "score": 1000,
                            "razones": ["archivo asociado al hallazgo"],
                        }
                    ],
                    "tiene_receta": bool(
                        recipe and recipe.operaciones
                    ),
                }

        resolution = resolver_archivo_fuente(
            self.cfg,
            root,
            control_id=control_id,
            metodo=row.get("metodo"),
            ruta=row.get("ruta"),
            descripcion=row.get("control"),
        )
        if not resolution.archivo:
            return {
                "archivo": None,
                "path": None,
                "confianza": resolution.confianza,
                "origen": resolution.origen,
                "candidatos": [
                    {
                        "archivo": item.archivo,
                        "score": item.score,
                        "razones": list(item.razones),
                    }
                    for item in resolution.candidatos
                ],
                "tiene_receta": bool(
                    recipe and recipe.operaciones
                ),
            }

        source = (root / resolution.archivo).resolve()
        if (
            not source.is_file()
            or source == root
            or root not in source.parents
        ):
            return {
                "archivo": None,
                "path": None,
                "confianza": "ninguna",
                "origen": "resolución inválida",
                "candidatos": [],
                "tiene_receta": bool(
                    recipe and recipe.operaciones
                ),
            }

        return {
            "archivo": source.relative_to(root).as_posix(),
            "path": str(source),
            "confianza": resolution.confianza,
            "origen": resolution.origen,
            "candidatos": [
                {
                    "archivo": item.archivo,
                    "score": item.score,
                    "razones": list(item.razones),
                }
                for item in resolution.candidatos
            ],
            "tiene_receta": bool(
                recipe and recipe.operaciones
            ),
        }

    def generate_ai(
        self,
        row: dict,
        source_path: str | Path | None = None,
    ) -> None:
        if not self.cfg or not self.target_root:
            self.error_message.emit(
                "Faltan datos",
                "Carga el perfil y el código fuente.",
            )
            return

        resolution: dict[str, Any] | None = None
        if source_path is None:
            resolution = self.resolve_ai_source(row)
            if not resolution.get("path"):
                self.error_message.emit(
                    "Archivo del hallazgo no localizado",
                    (
                        "Aegis no encontró con suficiente evidencia el "
                        "archivo responsable de la vulnerabilidad. "
                        "Selecciona el archivo manualmente para continuar."
                    ),
                )
                return
            source = Path(str(resolution["path"])).resolve()
        else:
            source = Path(source_path).expanduser().resolve()

        root = self.target_root.resolve()
        try:
            relative = source.relative_to(root).as_posix()
        except ValueError:
            self.error_message.emit(
                "Archivo fuera del proyecto",
                "El archivo seleccionado debe pertenecer al proyecto objetivo.",
            )
            return

        if not source.is_file():
            self.error_message.emit(
                "Archivo no disponible",
                f"No se puede cargar el archivo asociado: {relative}",
            )
            return

        source_bytes = source.read_bytes()
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        source_text = source_bytes.decode("utf-8", errors="replace")

        self._refresh_ai_provider(silent=False)
        if not self.ai_provider:
            return

        if resolution is None:
            resolution = {
                "archivo": relative,
                "path": str(source),
                "confianza": "alta",
                "origen": "selección manual",
                "candidatos": [],
                "tiene_receta": bool(
                    self.cfg.correccion_por_control(row["id"])
                ),
            }

        related_sources: dict[str, str] = {}
        hashes: dict[str, str] = {relative: source_hash}
        try:
            context_resolution = resolver_contexto_fuente(
                self.cfg,
                root,
                control_id=row["id"],
                metodo=row.get("metodo"),
                ruta=row.get("ruta"),
                descripcion=row.get("control"),
                max_relacionados=10,
            )
            for item in context_resolution.relacionados:
                candidate = (root / item.archivo).resolve()
                if (
                    not candidate.is_file()
                    or candidate == root
                    or root not in candidate.parents
                    or item.archivo == relative
                ):
                    continue
                try:
                    data = candidate.read_bytes()
                except OSError:
                    continue
                if len(data) > 1_500_000:
                    continue
                related_sources[item.archivo] = data.decode(
                    "utf-8",
                    errors="replace",
                )
                hashes[item.archivo] = hashlib.sha256(data).hexdigest()
        except Exception as exc:
            self.log_message.emit(
                "No se pudo ampliar el contexto de código: "
                f"{exc}"
            )

        language_context = detect_language_context(
            relative,
            source_text,
            related_sources,
        )
        principal_language = (
            language_context.get("principal") or {}
        )
        frameworks = language_context.get(
            "frameworks_contexto"
        ) or []
        self.log_message.emit(
            "Lenguaje detectado para el parche: "
            f"{principal_language.get('language') or 'desconocido'} "
            f"(confianza={principal_language.get('confidence') or 'baja'})"
            + (
                " · framework/contexto=" + ", ".join(frameworks)
                if frameworks
                else ""
            )
        )

        failures = list(
            self.ai_failed_attempts.get(row["id"], [])
        )
        strategy_reset = len(failures) >= 2
        if strategy_reset:
            self.log_message.emit(
                "STRATEGY_RESET activado para "
                f"{row['id']}: dos o más intentos fallaron. "
                "Se reanalizará causa raíz y flujo completo."
            )

        self.log_message.emit(
            "Contexto de remediación cargado: "
            f"{relative} + {len(related_sources)} archivo(s) relacionado(s). "
            f"confianza={resolution.get('confianza')} · "
            f"origen={resolution.get('origen')}"
        )

        knowledge = buscar_conocimiento(
            control_id=row["id"],
            descripcion=row.get("control"),
            tipo_control=row.get("tipo_control"),
            source_text=source_text,
            extension=source.suffix.lower(),
        )
        reusable = knowledge[0].public_dict() if knowledge else None

        metadata = dict(row)
        metadata["lenguaje_detectado"] = language_context
        metadata["archivo_cargado_ia"] = {
            "archivo": relative,
            "sha256": source_hash,
            "confianza_resolucion": resolution.get("confianza"),
            "origen_resolucion": resolution.get("origen"),
            "tiene_receta_previa": bool(
                resolution.get("tiene_receta")
            ),
            "archivos_relacionados": list(related_sources),
        }

        def work():
            proposals, context, provider = generar_tres_recetas(
                self.cfg,
                control_id=row["id"],
                descripcion=row.get("control") or row["id"],
                detalle=row.get("detalle") or "",
                source_relative=relative,
                source_text=source_text,
                provider=self.ai_provider,
                metadata_hallazgo=metadata,
                matriz_pruebas=[
                    item
                    for item in self.rows
                    if item.get("id") == row.get("id")
                ],
                intento_anterior=failures,
                conocimiento_reutilizable=reusable,
                archivos_relacionados=related_sources,
                strategy_reset=strategy_reset,
            )
            session = guardar_sesion_ia(
                self.evidence_base,
                contexto=context,
                propuestas=proposals,
                provider=provider,
            )
            return proposals, session, context

        def success(payload):
            proposals, session, context = payload
            self.ai_proposals = list(proposals)
            self.ai_session_dir = Path(session)
            self.ai_source_relative = relative
            self.ai_source_hash = source_hash
            self.ai_source_hashes = dict(hashes)
            self.ai_source_resolution = dict(resolution or {})
            diagnosis = context.get("diagnostico_causa_raiz")
            self.ai_diagnosis = (
                dict(diagnosis)
                if isinstance(diagnosis, dict)
                else None
            )
            self.ai_target_row = dict(row)
            self.ai_proposals_changed.emit(
                [proposal.as_dict() for proposal in proposals]
            )
            valid_count = sum(
                proposal.validacion_ok
                for proposal in proposals
            )
            root_file = (
                (self.ai_diagnosis or {}).get("archivo_causa_raiz")
                or relative
            )
            self.log_message.emit(
                "IA completó diagnóstico + tres estrategias para "
                f"{row['id']}. Causa raíz propuesta en {root_file}. "
                f"Propuestas aplicables={valid_count}/3."
            )
            if strategy_reset:
                self.info_message.emit(
                    "Strategy Reset",
                    (
                        f"{row['id']}: los intentos anteriores fallaron. "
                        "Aegis reanalizó el flujo completo y exigió "
                        "estrategias sustancialmente diferentes."
                    ),
                )
            if valid_count == 0:
                self.error_message.emit(
                    "Ninguna receta es aplicable",
                    (
                        "Las tres propuestas fueron rechazadas por "
                        "validación local. Regenera las recetas; Aegis "
                        "conservará diagnóstico y fallos como contexto."
                    ),
                )

        self._run_async(
            (
                f"Reanalizando causa raíz y generando recetas para {row['id']}…"
                if strategy_reset
                else f"Diagnosticando causa raíz y generando recetas para {row['id']}…"
            ),
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

        if not proposal.validacion_ok:
            self.error_message.emit(
                "Receta IA no aplicable",
                (
                    f"{proposal.id} fue descartada por la validación local:\n- "
                    + "\n- ".join(proposal.errores_validacion)
                ),
            )
            return

        changes = [
            dict(item)
            for item in (proposal.cambios or [])
            if isinstance(item, dict)
        ]
        target_relatives = list(dict.fromkeys(
            [
                str(item.get("archivo") or "").replace("\\", "/").strip()
                for item in changes
                if str(item.get("archivo") or "").strip()
            ]
            or [
                str(
                    proposal.archivo_objetivo
                    or self.ai_source_relative
                )
            ]
        ))
        target_relative = target_relatives[0]
        root = self.target_root.resolve()

        for relative in target_relatives:
            source = (root / relative).resolve()
            if (
                not source.is_file()
                or source == root
                or root not in source.parents
            ):
                self.error_message.emit(
                    "Archivo del hallazgo no disponible",
                    (
                        f"{relative} no existe dentro del proyecto. "
                        "Regenera la receta con el código actual."
                    ),
                )
                return

            current_hash = hashlib.sha256(
                source.read_bytes()
            ).hexdigest()
            expected_hash = self.ai_source_hashes.get(relative)
            if (
                expected_hash is None
                and relative == self.ai_source_relative
            ):
                expected_hash = self.ai_source_hash
            if expected_hash and current_hash != expected_hash:
                self.error_message.emit(
                    "El archivo cambió",
                    (
                        f"{relative} cambió después de que la IA lo cargó. "
                        "Aegis no aplicará un plan generado sobre una versión "
                        "distinta. Regenera las propuestas."
                    ),
                )
                return

        correction = propuesta_a_correccion(
            proposal,
            control_id=row["id"],
            source_relative=target_relative,
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
            # Segunda comprobación inmediatamente antes del parcheo.
            for relative in target_relatives:
                live_source = (
                    self.target_root / relative
                ).resolve()
                expected_live_hash = self.ai_source_hashes.get(
                    relative
                )
                if (
                    expected_live_hash is None
                    and relative == self.ai_source_relative
                ):
                    expected_live_hash = self.ai_source_hash
                if expected_live_hash:
                    live_hash = hashlib.sha256(
                        live_source.read_bytes()
                    ).hexdigest()
                    if live_hash != expected_live_hash:
                        raise RuntimeError(
                            f"{relative} cambió antes del parcheo; "
                            "regenera las recetas IA sobre la versión actual."
                        )

            history = self.ai_failed_attempts.get(
                row["id"],
                [],
            )
            result = ciclo_correctivo(
                self.cfg,
                row["id"],
                self.target_root,
                evidence_base=self.evidence_base,
                reiniciar=self.restart_callback(),
                selector=selector,
                attempt_number=len(history) + 1,
                proposal_id=proposal.id,
                estrategia=(
                    proposal.estrategia_conceptual
                    or proposal.enfoque
                ),
                hipotesis=proposal.hipotesis_id or None,
            )

            if self.ai_session_dir:
                guardar_seleccion_ia(
                    self.ai_session_dir,
                    propuesta=proposal,
                    correccion=correction,
                    resultado=result,
                )

            if result.get("estado_patch") in {
                "PATCH_VERIFIED",
                "PATCH_VERIFIED_WITH_WARNINGS",
            }:
                provider = self.ai_provider
                saved_recipe = guardar_receta_biblioteca(
                    correction,
                    sistema=self.cfg.sistema,
                    version_objetivo=self.cfg.version_objetivo,
                    metodo=row.get("metodo"),
                    ruta=row.get("ruta"),
                    tipo_control=row.get("tipo_control"),
                    titulo=proposal.titulo,
                    fuente="ia-verificada",
                    proveedor=(
                        provider.provider_name
                        if provider
                        else None
                    ),
                    modelo=(
                        provider.model_id
                        if provider
                        else None
                    ),
                    verificada=True,
                )
                result["receta_guardada"] = str(saved_recipe)
                self.log_message.emit(
                    "Medicina verificada guardada: "
                    f"{saved_recipe}"
                )

                knowledge = None
                applied = result.get("correccion_aplicada") or {}
                backup_path = str(applied.get("backup") or "").strip()
                try:
                    before_text = (
                        Path(backup_path).read_text(
                            encoding="utf-8",
                            errors="replace",
                        )
                        if backup_path
                        else ""
                    )
                    after_text = (
                        self.target_root / target_relative
                    ).read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                    if provider and before_text:
                        knowledge, _context, _provider = (
                            generalizar_correccion_exitosa(
                                self.cfg,
                                control_id=row["id"],
                                descripcion=(
                                    row.get("control")
                                    or row["id"]
                                ),
                                detalle=row.get("detalle") or "",
                                metadata_hallazgo=row,
                                matriz_pruebas=[
                                    item
                                    for item in self.rows
                                    if item.get("id") == row.get("id")
                                ],
                                source_relative=target_relative,
                                codigo_antes=before_text,
                                codigo_despues=after_text,
                                diff=str(applied.get("diff") or ""),
                                propuesta=proposal,
                                provider=provider,
                            )
                        )
                except Exception as exc:
                    self.log_message.emit(
                        "El parche fue verificado, pero la generalización "
                        f"enriquecida falló: {exc}. Se guardará respaldo "
                        "semántico verificado."
                    )

                if knowledge is None:
                    knowledge = crear_conocimiento_respaldo_verificado(
                        control_id=row["id"],
                        descripcion=row.get("control"),
                        tipo_control=row.get("tipo_control"),
                        extension=Path(
                            target_relative
                        ).suffix.lower(),
                    )

                guardar_conocimiento(
                    knowledge,
                    caso_exitoso={
                        "control_id": row["id"],
                        "tipo_control": row.get("tipo_control"),
                        "familia": row.get("familia"),
                        "archivo_extension": Path(
                            target_relative
                        ).suffix.lower(),
                        "resultado": str(result.get("estado_patch")),
                        "estado_patch": str(result.get("estado_patch")),
                    },
                )
            return result

        def success(result):
            legacy_state = result.get("estado_final") or "DESCONOCIDO"
            patch_state = result.get("estado_patch") or legacy_state
            verified = patch_state in {
                "PATCH_VERIFIED",
                "PATCH_VERIFIED_WITH_WARNINGS",
            }

            if verified:
                self.ai_source_hash = None
                self.ai_source_hashes.clear()
                self.ai_failed_attempts.pop(row["id"], None)
                self.ai_auto_regenerations.pop(row["id"], None)
                saved_recipe_path = str(
                    result.get("receta_guardada") or ""
                ).strip()
                if saved_recipe_path:
                    self.log_message.emit(
                        "Receta de corrección persistida en biblioteca: "
                        + saved_recipe_path
                    )

                if patch_state == "PATCH_VERIFIED_WITH_WARNINGS":
                    warnings = result.get("qa_advertencias") or []
                    warning_detail = ""
                    if warnings:
                        warning_detail = str(
                            warnings[0].get("detalle") or ""
                        ).strip()
                    message = (
                        f"{row['id']}: PATCH_VERIFIED_WITH_WARNINGS\n\n"
                        "Aegis modificó el código y la prueba de seguridad "
                        "confirmó que el fallo ya no se reproduce. El parche "
                        "se conserva.\n\n"
                        "La suite funcional reportó fallos posteriores. "
                        "Esto puede ocurrir cuando una prueba antigua todavía "
                        "espera el comportamiento vulnerable; revísala antes "
                        "de actualizar esas pruebas."
                    )
                    if warning_detail:
                        message += "\n\nQA: " + warning_detail[:3500]
                    self.info_message.emit(
                        "Parche de seguridad aplicado con advertencias",
                        message,
                    )
                else:
                    self.info_message.emit(
                        "Parche verificado",
                        (
                            f"{row['id']}: PATCH_VERIFIED\n\n"
                            "Aegis modificó el código y la prueba de seguridad "
                            "confirmó que el fallo ya no se reproduce. "
                            "Las validaciones posteriores finalizaron "
                            "sin advertencias."
                        ),
                    )
            else:
                history = self.ai_failed_attempts.setdefault(
                    row["id"],
                    [],
                )
                attempt_record = {
                    "attempt": len(history) + 1,
                    "propuesta": proposal.as_dict(),
                    "archivo": target_relative,
                    "diagnostico": self.ai_diagnosis,
                    "resultado": dict(result),
                    "failure_analysis": result.get(
                        "failure_analysis"
                    ),
                }
                history.append(attempt_record)
                del history[:-12]

                # Nunca dejamos una receta fallida activa en el perfil en
                # memoria: podría ser reutilizada accidentalmente por otro flujo.
                self.cfg.correcciones = [
                    item
                    for item in self.cfg.correcciones
                    if item.control_id != row["id"]
                ]

                proposal.validacion_ok = False
                runtime_error = (
                    f"falló en ejecución/verificación: {patch_state}"
                )
                if runtime_error not in proposal.errores_validacion:
                    proposal.errores_validacion.append(runtime_error)
                self.ai_proposals_changed.emit(
                    [item.as_dict() for item in self.ai_proposals]
                )

                motive = str(result.get("motivo") or "").strip()
                error = str(result.get("error") or "").strip()
                rollback_state = (
                    "Sí"
                    if result.get("rollback")
                    else "No / no fue necesario"
                )
                details = [
                    f"{row['id']}: {patch_state}",
                    motive or "La receta no superó la verificación.",
                ]

                technical = result.get("validacion_tecnica") or {}
                if technical:
                    syntax = technical.get("sintaxis") or {}
                    build = technical.get("build") or {}
                    tests = technical.get("tests") or {}
                    for label, item in (
                        ("Sintaxis", syntax),
                        ("Build", build),
                        ("Tests", tests),
                    ):
                        if item.get("estado"):
                            line = f"{label}: {item.get('estado')}"
                            detail = str(item.get("detalle") or "").strip()
                            if detail:
                                line += f" · {detail}"
                            details.append(line)

                if error:
                    details.append(f"Error: {error}")

                failure = result.get("failure_analysis") or {}
                if failure.get("categoria_error"):
                    details.append(
                        "Análisis del fallo: "
                        f"{failure.get('categoria_error')} · "
                        f"{failure.get('por_que_no_resolvio') or ''}"
                    )

                verification_errors = result.get(
                    "errores_verificacion"
                ) or []
                for item in verification_errors[:3]:
                    detail = str(item.get("detalle") or "").strip()
                    if detail:
                        details.append(f"Verificación: {detail}")

                regressions = result.get(
                    "regresiones_globales"
                ) or []
                if regressions:
                    details.append(
                        "Regresiones detectadas: "
                        f"{len(regressions)}"
                    )

                details.append(
                    f"Rollback automático: {rollback_state}"
                )
                evidence = str(result.get("evidencia") or "").strip()
                if evidence:
                    details.append(f"Evidencia: {evidence}")

                auto_count = self.ai_auto_regenerations.get(
                    row["id"],
                    0,
                )
                auto_regenerate = (
                    len(history) >= 2
                    and len(history) % 2 == 0
                    and auto_count < 3
                )
                if auto_regenerate:
                    details.append(
                        "STRATEGY_RESET: dos intentos consecutivos fallaron. "
                        "Al cerrar este mensaje Aegis reanalizará "
                        "automáticamente la causa raíz y generará estrategias "
                        "nuevas; no reutilizará estas medicinas."
                    )
                elif len(history) >= 8:
                    details.append(
                        "MANUAL_REVIEW_REQUIRED: se agotaron varios ciclos "
                        "adaptativos sin verificar una corrección."
                    )
                else:
                    details.append(
                        "Puedes seleccionar otra alternativa válida. "
                        "Este intento quedó descartado y se usará como "
                        "retroalimentación."
                    )

                self.error_message.emit(
                    "La receta no pudo corregir el hallazgo",
                    "\n\n".join(details),
                )
                self.log_message.emit(
                    f"PATCH_ATTEMPT_{len(history)} {row['id']}: "
                    f"{patch_state}"
                    + (f" · {motive}" if motive else "")
                    + (f" · {error}" if error else "")
                )

            self.evidence_changed.emit()
            if not verified and 'auto_regenerate' in locals() and auto_regenerate:
                self.ai_auto_regenerations[row["id"]] = (
                    self.ai_auto_regenerations.get(row["id"], 0) + 1
                )
                source_for_retry = (
                    self.target_root / self.ai_source_relative
                )
                self.generate_ai(
                    row,
                    source_for_retry,
                )
            else:
                self.diagnose()

        self._run_async(
            f"Aplicando receta {proposal.enfoque} y verificando…",
            work,
            success,
        )