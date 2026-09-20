"""Páginas Qt premium de Aegis Auditor."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QSizePolicy,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..app_paths import (
    default_ai_config_path,
    default_article_dir,
    default_config_dir,
    default_evidence_dir,
    default_recipe_dir,
)
from ..article_evidence import export_article_package
from ..recipe_library import biblioteca_por_defecto
from ..remediation_knowledge import knowledge_root
from .dialogs import styled_existing_directory, styled_open_file
from .theme import COLORS
from .widgets import (
    Card,
    MetricCard,
    PrimaryButton,
    SectionHeader,
    StageRow,
    Stepper,
)


class HomePage(QWidget):
    request_new = Signal()
    request_load = Signal()
    request_audit = Signal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._compact = False

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(9)
        self.grid.setVerticalSpacing(8)
        self.grid.setColumnStretch(0, 7)
        self.grid.setColumnStretch(1, 3)
        self.grid.setRowStretch(2, 0)

        self.step_card = Card()
        step_layout = QVBoxLayout(self.step_card)
        step_layout.setContentsMargins(12, 8, 12, 8)
        self.stepper = Stepper(
            [
                ("Seleccionar", "Proyecto"),
                ("Generar", "Perfil"),
                ("Analizar", "P1 + P2"),
                ("Corregir", "Remediación"),
                ("Validar", "Evidencia"),
            ]
        )
        step_layout.addWidget(self.stepper)
        self.grid.addWidget(self.step_card, 0, 0, 1, 2)

        self.operation = Card()
        op = QVBoxLayout(self.operation)
        op.setContentsMargins(14, 10, 14, 10)
        op.setSpacing(5)
        op.addWidget(
            SectionHeader(
                "Ejecución y diagnóstico",
                "Ciclo operativo del proyecto objetivo.",
            )
        )

        self.stages = {
            "project": StageRow(
                "Aplicación",
                "Selecciona o carga el código fuente.",
            ),
            "profile": StageRow(
                "Perfil de configuración",
                "Genera o carga config/*.json.",
            ),
            "audit": StageRow(
                "Auditoría Pilar 1 + Pilar 2",
                "Ejecuta la línea base de seguridad.",
            ),
            "remediation": StageRow(
                "Corrección y verificación",
                "Aplica la receta y comprueba el resultado.",
            ),
        }
        for row in self.stages.values():
            op.addWidget(row)

        self.operation_progress = QProgressBar()
        self.operation_progress.setRange(0, 100)
        self.operation_progress.setTextVisible(False)
        op.addWidget(self.operation_progress)

        actions = QHBoxLayout()
        self.start_btn = QPushButton("▶  Iniciar")
        self.start_btn.setObjectName("SuccessButton")
        self.stop_btn = QPushButton("■  Detener")
        self.stop_btn.setObjectName("DangerButton")
        self.restart_btn = QPushButton("↻  Reiniciar")
        self.audit_btn = PrimaryButton("◈  Diagnosticar P1 + P2")

        self.start_btn.clicked.connect(controller.start_target)
        self.stop_btn.clicked.connect(controller.stop_target)
        self.restart_btn.clicked.connect(controller.restart_target)
        self.audit_btn.clicked.connect(controller.diagnose)

        actions.addWidget(self.start_btn)
        actions.addWidget(self.stop_btn)
        actions.addWidget(self.restart_btn)
        actions.addWidget(self.audit_btn)
        op.addLayout(actions)

        self.operation.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        self.grid.addWidget(self.operation, 1, 0)

        self.console_card = Card()
        console_layout = QVBoxLayout(self.console_card)
        console_layout.setContentsMargins(12, 9, 12, 10)
        console_layout.addWidget(
            SectionHeader(
                "Consola en tiempo real",
                "Runtime, auditoría, IA y verificación.",
            )
        )
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(96)
        self.console.setMaximumHeight(132)
        console_layout.addWidget(self.console, 1)
        self.console_card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        self.grid.addWidget(self.console_card, 2, 0)

        self.metrics = QWidget()
        metrics_layout = QHBoxLayout(self.metrics)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(7)

        self.project_metric = MetricCard(
            "Proyecto",
            "Sin cargar",
            "Código objetivo",
        )
        self.profile_metric = MetricCard(
            "Perfil",
            "Sin perfil",
            "Configuración",
        )
        self.process_metric = MetricCard(
            "Proceso",
            "No administrado",
            "Runtime",
        )
        self.findings_metric = MetricCard(
            "Hallazgos",
            "0",
            "P1 0 · P2 0",
        )
        for card in (
            self.project_metric,
            self.profile_metric,
            self.process_metric,
            self.findings_metric,
        ):
            metrics_layout.addWidget(card, 1)
        self.metrics.setMaximumHeight(78)
        self.grid.addWidget(self.metrics, 3, 0)

        self.right_rail = QWidget()
        rail = QVBoxLayout(self.right_rail)
        rail.setContentsMargins(0, 0, 0, 0)
        rail.setSpacing(8)

        info_card = Card()
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(13, 10, 13, 10)
        info_layout.addWidget(
            SectionHeader(
                "Información del proyecto",
                "Datos del objetivo activo.",
            )
        )
        self.project_info = QLabel("No hay una aplicación cargada.")
        self.project_info.setObjectName("Muted")
        self.project_info.setWordWrap(True)
        self.project_info.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        info_layout.addWidget(self.project_info)
        rail.addWidget(info_card)

        task_card = Card()
        task_layout = QVBoxLayout(task_card)
        task_layout.setContentsMargins(13, 10, 13, 10)
        task_layout.addWidget(
            SectionHeader(
                "Tarea actual",
                "Próximo paso recomendado por el flujo.",
            )
        )
        self.task_title = QLabel("Selecciona una aplicación")
        self.task_title.setObjectName("SectionTitle")
        self.task_detail = QLabel(
            "Usa Nuevo proyecto o Cargar / Importar para comenzar."
        )
        self.task_detail.setObjectName("Muted")
        self.task_detail.setWordWrap(True)
        self.task_progress = QProgressBar()
        self.task_progress.setRange(0, 100)
        self.task_progress.setTextVisible(False)
        task_layout.addWidget(self.task_title)
        task_layout.addWidget(self.task_detail)
        task_layout.addWidget(self.task_progress)
        rail.addWidget(task_card)

        profile_card = Card()
        profile_layout = QVBoxLayout(profile_card)
        profile_layout.setContentsMargins(13, 10, 13, 10)
        profile_layout.addWidget(
            SectionHeader(
                "Vista previa del perfil",
                "Configuración declarativa cargada.",
            )
        )
        self.profile_preview = QPlainTextEdit()
        self.profile_preview.setReadOnly(True)
        self.profile_preview.setMinimumHeight(108)
        self.profile_preview.setMaximumHeight(170)
        self.profile_preview.setPlainText(
            '{\n  "perfil": "sin cargar"\n}'
        )
        profile_layout.addWidget(self.profile_preview, 1)
        rail.addWidget(profile_card, 1)

        self.grid.addWidget(self.right_rail, 1, 1, 3, 1)

    def append_log(self, text: str) -> None:
        self.console.appendPlainText(text)
        bar = self.console.verticalScrollBar()
        bar.setValue(bar.maximum())

    def set_compact(self, compact: bool) -> None:
        if compact == self._compact:
            return
        self._compact = compact

        self.grid.removeWidget(self.right_rail)
        if compact:
            self.grid.addWidget(self.right_rail, 4, 0, 1, 2)
            self.grid.setColumnStretch(0, 1)
            self.grid.setColumnStretch(1, 0)
        else:
            self.grid.addWidget(self.right_rail, 1, 1, 3, 1)
            self.grid.setColumnStretch(0, 7)
            self.grid.setColumnStretch(1, 3)

    def refresh(self) -> None:
        c = self.controller
        project = c.target_root.name if c.target_root else "Sin cargar"
        profile = c.cfg.sistema if c.cfg else "Sin perfil"
        running = c.process_running()

        rows = c.rows
        p1 = sum(
            row.get("pilar") == "P1"
            and row.get("estado") == "HALLAZGO"
            for row in rows
        )
        p2 = sum(
            row.get("pilar") == "P2"
            and row.get("estado") == "HALLAZGO"
            for row in rows
        )
        matrix_vulnerable = sum(
            row.get("pilar") == "P1"
            and row.get("estado") == "VULNERABLE"
            for row in rows
        )

        self.project_metric.set_value(project, "Código objetivo")
        self.profile_metric.set_value(
            profile,
            c.config_path.name if c.config_path else "Configuración",
        )
        active_runtime = (
            c.active_runtime_status
            if running and c.active_runtime_status
            else {}
        )
        active_mode = str(
            active_runtime.get("modo")
            or (c.cfg.runtime.modo if c.cfg else "Runtime")
        )
        self.process_metric.set_value(
            "En ejecución"
            if running
            else ("Detenido" if c.proceso else "No administrado"),
            active_mode,
        )
        self.findings_metric.set_value(
            str(p1 + p2),
            (
                f"P1 {p1} · P2 {p2}"
                + (
                    f" · Matriz {matrix_vulnerable} vulnerable(s)"
                    if matrix_vulnerable
                    else ""
                )
            ),
        )

        meta = c.detected_metadata()
        languages = ", ".join(meta.get("lenguajes") or []) or "-"
        frameworks = ", ".join(meta.get("frameworks") or []) or "-"

        runtime_name = "-"
        runtime_mode = "-"
        start_text = "-"
        fallback_text = "-"
        policy_text = "-"

        if c.cfg:
            runtime = c.cfg.runtime
            active = (
                c.active_runtime_status
                if running and c.active_runtime_status
                else {}
            )
            runtime_name = str(
                active.get("nombre")
                or runtime.nombre
                or runtime.modo
            )
            runtime_mode = str(
                active.get("modo")
                or runtime.modo
            )

            platform_key = (
                "windows"
                if os.name == "nt"
                else ("macos" if sys.platform == "darwin" else "linux")
            )
            command = (
                active.get("comando_inicio")
                or runtime.comando_inicio_por_so.get(platform_key)
                or runtime.comando_inicio_por_so.get("default")
                or runtime.comando_inicio
                or []
            )
            start_text = " ".join(str(item) for item in command) or "-"

            alternatives = []
            for item in runtime.alternativas or []:
                if not isinstance(item, dict):
                    continue
                alt_command = (
                    (item.get("comando_inicio_por_so") or {}).get(
                        platform_key
                    )
                    or (item.get("comando_inicio_por_so") or {}).get(
                        "default"
                    )
                    or item.get("comando_inicio")
                    or []
                )
                alternatives.append(
                    f"{item.get('nombre') or item.get('modo') or 'local'}"
                    + (
                        " → " + " ".join(str(part) for part in alt_command)
                        if alt_command
                        else ""
                    )
                )
            fallback_text = (
                " | ".join(alternatives)
                if alternatives
                else "Sin alternativa declarada"
            )
            policy_text = (
                f"{runtime.preferencia_arranque or 'auto'} · "
                + (
                    "fallback local habilitado"
                    if runtime.permitir_fallback_local
                    else "fallback local deshabilitado"
                )
            )

        self.project_info.setText(
            "\n".join(
                [
                    f"Nombre        {profile}",
                    f"Ruta          {c.target_root or '-'}",
                    f"Lenguaje      {languages}",
                    f"Framework     {frameworks}",
                    (
                        "Base URL      "
                        + str(
                            (
                                c.active_runtime_status.get("base_url")
                                if running and c.active_runtime_status
                                else None
                            )
                            or (c.cfg.base_url if c.cfg else "-")
                            or "-"
                        )
                    ),
                    f"Runtime       {runtime_name} ({runtime_mode})",
                    f"Inicio        {start_text}",
                    f"Política      {policy_text}",
                    f"Alternativas  {fallback_text}",
                ]
            )
        )

        has_evidence = False
        corrected = False
        try:
            sessions = list(c.evidence_base.iterdir())
            has_evidence = bool(sessions)
            for session in sessions:
                manifest = session / "manifest.json"
                if not manifest.exists():
                    continue
                try:
                    payload = json.loads(
                        manifest.read_text(encoding="utf-8")
                    )
                except Exception:
                    continue
                if payload.get("estado_final") == "CORREGIDO":
                    corrected = True
                    break
        except OSError:
            pass

        step = 0
        if c.target_root:
            step = 1
        if c.cfg:
            step = 2
        if c.resultado:
            step = 3
        if has_evidence:
            step = 4
        if corrected:
            step = 5

        self.stepper.set_step(step)
        self.operation_progress.setValue(int(step / 5 * 100))
        self.task_progress.setValue(int(step / 5 * 100))

        self.stages["project"].set_state(
            "done" if c.target_root else "active",
            str(c.target_root)
            if c.target_root
            else "Selecciona o importa una aplicación.",
        )
        self.stages["profile"].set_state(
            "done"
            if c.cfg
            else ("active" if c.target_root else "pending"),
            str(c.config_path)
            if c.config_path
            else "Aegis generará config/*.json.",
        )
        self.stages["audit"].set_state(
            "done"
            if c.resultado
            else ("active" if c.cfg else "pending"),
            f"{len(rows)} control(es) evaluados · P1 {p1} / P2 {p2}"
            if c.resultado
            else "Esperando diagnóstico P1 + P2.",
        )
        self.stages["remediation"].set_state(
            "done"
            if corrected
            else (
                "active"
                if c.resultado and p1 + p2
                else "pending"
            ),
            "Existe evidencia CORREGIDO."
            if corrected
            else (
                f"{p1 + p2} hallazgo(s) para corregir."
                if c.resultado and p1 + p2
                else "Esperando un hallazgo verificable."
            ),
        )

        if not c.target_root:
            title = "Selecciona una aplicación"
            detail = (
                "Usa Nuevo proyecto o Cargar / Importar para comenzar."
            )
        elif not c.cfg:
            title = "Generar perfil de configuración"
            detail = (
                "Detecta stack, runtime, endpoints y puntos de entrada."
            )
        elif not c.resultado:
            title = "Diagnosticar Pilar 1 + Pilar 2"
            detail = (
                "El perfil está listo. Ejecuta la línea base."
            )
        elif p1 + p2 and not corrected:
            title = "Corregir y verificar hallazgos"
            detail = f"P1 {p1} · P2 {p2}"
        else:
            title = "Consolidar evidencia"
            detail = (
                "El ciclo está listo para documentar y reutilizar conocimiento."
            )
        self.task_title.setText(title)
        self.task_detail.setText(detail)

        self.profile_preview.setPlainText(
            json.dumps(
                c.profile_dict() or {"perfil": "sin cargar"},
                ensure_ascii=False,
                indent=2,
            )
        )


class ProjectPage(QWidget):
    request_new = Signal()
    request_load_profile = Signal()
    request_load_source = Signal()
    request_load_evidence = Signal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("Proyecto y auto-configuración")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Administra los puntos de entrada de la aplicación objetivo "
            "sin mezclar datos específicos con el motor del auditor."
        )
        subtitle.setObjectName("Subheading")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        cards = QGridLayout()
        cards.setSpacing(10)

        load = Card()
        load_l = QVBoxLayout(load)
        load_l.setContentsMargins(16, 14, 16, 14)
        load_l.addWidget(
            SectionHeader(
                "Recursos del objetivo",
                "Código, perfil y evidencias.",
            )
        )
        for text, signal in (
            ("＋ Nuevo proyecto / Auto-configurar", self.request_new),
            ("▣ Cargar perfil JSON", self.request_load_profile),
            ("⌂ Cargar código fuente", self.request_load_source),
            ("▧ Seleccionar evidencias", self.request_load_evidence),
        ):
            button = QPushButton(text)
            if text.startswith("＋"):
                button.setObjectName("PrimaryButton")
            button.clicked.connect(signal.emit)
            load_l.addWidget(button)
        load_l.addStretch(1)
        cards.addWidget(load, 0, 0)

        info = Card()
        info_l = QVBoxLayout(info)
        info_l.setContentsMargins(16, 14, 16, 14)
        info_l.addWidget(
            SectionHeader(
                "Perfil activo",
                "Resumen técnico de la configuración actual.",
            )
        )
        self.info = QPlainTextEdit()
        self.info.setReadOnly(True)
        info_l.addWidget(self.info, 1)
        cards.addWidget(info, 0, 1)

        cards.setColumnStretch(0, 2)
        cards.setColumnStretch(1, 3)
        layout.addLayout(cards, 1)

    def refresh(self):
        c = self.controller
        meta = c.detected_metadata()
        payload = {
            "sistema": c.cfg.sistema if c.cfg else None,
            "version": c.cfg.version_objetivo if c.cfg else None,
            "base_url": c.cfg.base_url if c.cfg else None,
            "runtime": c.cfg.runtime.modo if c.cfg else None,
            "codigo": str(c.target_root) if c.target_root else None,
            "perfil": str(c.config_path) if c.config_path else None,
            "evidencias": str(c.evidence_base),
            "metadata_detectada": meta,
        }
        self.info.setPlainText(
            json.dumps(payload, ensure_ascii=False, indent=2)
        )


class AuditPage(QWidget):
    request_ai = Signal(dict)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.rows: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Auditoría de seguridad")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Resultados normalizados de Pilar 1 y Pilar 2."
        )
        subtitle.setObjectName("Subheading")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)

        diagnose = PrimaryButton("◈  Diagnosticar P1 + P2")
        diagnose.clicked.connect(controller.diagnose)
        header.addWidget(diagnose)
        layout.addLayout(header)

        metrics = QHBoxLayout()
        self.p1 = MetricCard(
            "Pilar 1",
            "0 hallazgos",
            "Identidad y Control de Acceso",
        )
        self.p2 = MetricCard(
            "Pilar 2",
            "0 hallazgos",
            "Arquitectura y Configuración",
        )
        self.total = MetricCard(
            "Estado global",
            "Sin diagnóstico",
            "P1 + P2",
        )
        metrics.addWidget(self.p1)
        metrics.addWidget(self.p2)
        metrics.addWidget(self.total)
        layout.addLayout(metrics)

        actions = QHBoxLayout()
        verify = QPushButton("✓  Verificar")
        correct = PrimaryButton("✦  Corregir seleccionado")
        correct_all = QPushButton("⚡  Corregir hallazgos")
        ai = QPushButton("✦  Abrir en IA")
        verify.clicked.connect(self._verify)
        correct.clicked.connect(self._correct)
        correct_all.clicked.connect(controller.correct_all)
        ai.clicked.connect(self._ai)
        actions.addWidget(verify)
        actions.addWidget(correct)
        actions.addWidget(correct_all)
        actions.addWidget(ai)
        layout.addLayout(actions)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "Pilar",
                "Control",
                "Descripción",
                "Cuenta",
                "Estado",
                "Tipo",
                "Detalle",
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.Stretch,
        )
        header_view.setSectionResizeMode(
            6,
            QHeaderView.ResizeMode.Stretch,
        )
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

    def selected_row(self) -> dict | None:
        index = self.table.currentRow()
        if index < 0 or index >= len(self.rows):
            return None
        return self.rows[index]

    def _verify(self):
        row = self.selected_row()
        if row:
            self.controller.verify_row(row)

    def _correct(self):
        row = self.selected_row()
        if row:
            self.controller.correct_row(row)

    def _ai(self):
        row = self.selected_row()
        if row:
            self.request_ai.emit(row)

    def set_rows(self, rows: list[dict]) -> None:
        self.rows = list(rows)
        self.table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            values = [
                row.get("pilar"),
                row.get("id"),
                row.get("control"),
                row.get("cuenta"),
                row.get("estado"),
                row.get("tipo_control"),
                row.get("detalle"),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                if row.get("estado") == "HALLAZGO":
                    item.setForeground(QColor("#FFB1BC"))
                elif row.get("estado") == "SIN_HALLAZGO":
                    item.setForeground(QColor("#8DE9CE"))
                elif row.get("estado") == "ERROR":
                    item.setForeground(QColor("#FFD68E"))
                elif row.get("estado") == "VULNERABLE":
                    item.setForeground(QColor("#FFCF8E"))
                elif row.get("estado") == "CONFIRMADO":
                    item.setForeground(QColor("#D9B8FF"))
                self.table.setItem(row_index, col, item)

        p1 = sum(
            row.get("pilar") == "P1"
            and row.get("estado") == "HALLAZGO"
            for row in rows
        )
        p2 = sum(
            row.get("pilar") == "P2"
            and row.get("estado") == "HALLAZGO"
            for row in rows
        )
        matrix_vulnerable = sum(
            row.get("pilar") == "P1"
            and row.get("estado") == "VULNERABLE"
            for row in rows
        )
        self.p1.set_value(
            f"{p1} hallazgo(s)"
            + (
                f" · matriz {matrix_vulnerable} vulnerable(s)"
                if matrix_vulnerable
                else ""
            )
        )
        self.p2.set_value(f"{p2} hallazgo(s)")
        self.total.set_value(
            (
                "Seguro"
                if rows and p1 + p2 == 0 and matrix_vulnerable == 0
                else (
                    f"{p1 + p2} hallazgo(s)"
                    if rows
                    else "Sin diagnóstico"
                )
            ),
            (
                f"{len(rows)} control(es)"
                + (
                    f" · {matrix_vulnerable} vulnerable(s) en matriz"
                    if matrix_vulnerable
                    else ""
                )
                if rows
                else "P1 + P2"
            ),
        )


class AIPage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.target_row: dict | None = None
        self.source_path: Path | None = None
        self.proposals: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("Correcciones con IA")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Gemma propone; Aegis aplica con backup, verifica y revierte si no funciona."
        )
        subtitle.setObjectName("Subheading")
        layout.addWidget(subtitle)

        context = Card()
        context_l = QGridLayout(context)
        context_l.setContentsMargins(16, 14, 16, 14)
        context_l.setHorizontalSpacing(12)
        context_l.setVerticalSpacing(7)

        self.control_label = QLabel("Ningún hallazgo seleccionado")
        self.control_label.setObjectName("SectionTitle")
        self.source_label = QLabel("Archivo: no seleccionado")
        self.source_label.setObjectName("Muted")
        self.provider_label = QLabel("IA: comprobando…")
        self.provider_label.setObjectName("Muted")

        choose = QPushButton("Elegir archivo")
        choose.clicked.connect(self._choose_source)
        generate = PrimaryButton("Generar 3 recetas")
        generate.clicked.connect(self._generate)

        context_l.addWidget(self.control_label, 0, 0, 1, 2)
        context_l.addWidget(self.source_label, 1, 0, 1, 2)
        context_l.addWidget(self.provider_label, 2, 0)
        context_l.addWidget(choose, 2, 1)
        context_l.addWidget(generate, 3, 0, 1, 2)
        layout.addWidget(context)

        split = QSplitter()
        split.setOrientation(Qt.Orientation.Horizontal)

        left = Card()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(14, 12, 14, 12)
        left_l.addWidget(
            SectionHeader(
                "Alternativas",
                "Mínima, estructural y alternativa.",
            )
        )
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._show_proposal)
        left_l.addWidget(self.list, 1)

        apply_btn = PrimaryButton("Aplicar propuesta y verificar")
        apply_btn.clicked.connect(self._apply)
        left_l.addWidget(apply_btn)

        right = Card()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(14, 12, 14, 12)
        right_l.addWidget(
            SectionHeader(
                "Detalle de la receta",
                "La propuesta todavía no modifica el código.",
            )
        )
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        right_l.addWidget(self.detail, 1)

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([380, 720])
        layout.addWidget(split, 1)

        self.refresh_provider()

    def refresh_provider(self):
        enabled, name = self.controller.ai_status()
        self.provider_label.setText(
            f"● IA conectada · {name}"
            if enabled
            else "○ IA no configurada"
        )
        self.provider_label.setStyleSheet(
            f"color:{COLORS['success'] if enabled else COLORS['muted']};"
        )

    def set_target(self, row: dict):
        self.target_row = dict(row)
        self.control_label.setText(
            f"{row.get('id')} · {row.get('control')}"
        )

    def _choose_source(self):
        initial = (
            str(self.controller.target_root)
            if self.controller.target_root
            else ""
        )
        selected, _filter = styled_open_file(
            self,
            "Selecciona el archivo fuente del hallazgo",
            initial,
        )
        if selected:
            self.source_path = Path(selected)
            self.source_label.setText(f"Archivo: {selected}")

    def _generate(self):
        if self.target_row and self.source_path:
            self.controller.generate_ai(
                self.target_row,
                self.source_path,
            )

    def set_proposals(self, proposals: list[dict]) -> None:
        self.proposals = list(proposals)
        self.list.clear()
        for proposal in proposals:
            item = QListWidgetItem(
                f"{proposal.get('enfoque')} · "
                f"{proposal.get('titulo')} · "
                f"riesgo {proposal.get('riesgo')}"
            )
            self.list.addItem(item)
        if proposals:
            self.list.setCurrentRow(0)

    def _show_proposal(self, index: int):
        if index < 0 or index >= len(self.proposals):
            self.detail.clear()
            return
        self.detail.setPlainText(
            json.dumps(
                self.proposals[index],
                ensure_ascii=False,
                indent=2,
            )
        )

    def _apply(self):
        index = self.list.currentRow()
        if index >= 0:
            self.controller.apply_ai_proposal(index)


class KnowledgePage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("Recetas y conocimiento")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Separa el parche concreto de la medicina semántica reusable."
        )
        subtitle.setObjectName("Subheading")
        layout.addWidget(subtitle)

        metrics = QHBoxLayout()
        self.knowledge = MetricCard(
            "Medicinas semánticas",
            "0",
            "Conocimiento reutilizable",
        )
        self.recipes = MetricCard(
            "Parches concretos",
            "0",
            "Implementaciones exactas",
        )
        self.evidence = MetricCard(
            "Evidencias",
            "0",
            "Sesiones guardadas",
        )
        metrics.addWidget(self.knowledge)
        metrics.addWidget(self.recipes)
        metrics.addWidget(self.evidence)
        layout.addLayout(metrics)

        card = Card()
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(16, 14, 16, 14)
        card_l.addWidget(
            SectionHeader(
                "Modelo de aprendizaje",
                "Una corrección verificada puede producir conocimiento "
                "generalizable sin amarrarse al código origen.",
            )
        )
        self.details = QLabel()
        self.details.setObjectName("Muted")
        self.details.setWordWrap(True)
        card_l.addWidget(self.details)
        card_l.addStretch(1)
        layout.addWidget(card, 1)

    def refresh(self):
        knowledge_files = (
            list(knowledge_root().glob("*/*.json"))
            if knowledge_root().exists()
            else []
        )
        recipe_root = biblioteca_por_defecto()
        recipe_files = (
            list(recipe_root.glob("*/*.json"))
            if recipe_root.exists()
            else []
        )
        evidence_dirs = (
            [p for p in self.controller.evidence_base.iterdir() if p.is_dir()]
            if self.controller.evidence_base.exists()
            else []
        )
        self.knowledge.set_value(str(len(knowledge_files)))
        self.recipes.set_value(str(len(recipe_files)))
        self.evidence.set_value(str(len(evidence_dirs)))
        self.details.setText(
            f"Medicinas: {knowledge_root()}\n"
            f"Recetas: {recipe_root}\n"
            f"Evidencias: {self.controller.evidence_base}"
        )


class EvidencePage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Evidencias")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Sesiones verificables de diagnóstico, corrección y rollback."
        )
        subtitle.setObjectName("Subheading")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)

        refresh = QPushButton("Actualizar")
        refresh.clicked.connect(self.refresh)
        export = PrimaryButton("Exportar para artículo")
        export.clicked.connect(self._export)
        header.addWidget(refresh)
        header.addWidget(export)
        layout.addLayout(header)

        split = QSplitter()
        split.setOrientation(Qt.Orientation.Horizontal)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._preview)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)

        split.addWidget(self.list)
        split.addWidget(self.preview)
        split.setSizes([320, 780])
        layout.addWidget(split, 1)
        self.sessions: list[Path] = []

    def refresh(self):
        self.sessions = []
        self.list.clear()
        base = self.controller.evidence_base
        if base.exists():
            self.sessions = sorted(
                [path for path in base.iterdir() if path.is_dir()],
                key=lambda path: path.name,
                reverse=True,
            )
        for session in self.sessions:
            manifest = session / "manifest.json"
            state = "SESIÓN"
            if manifest.exists():
                try:
                    state = json.loads(
                        manifest.read_text(encoding="utf-8")
                    ).get("estado_final") or "SESIÓN"
                except Exception:
                    pass
            self.list.addItem(f"{session.name}   ·   {state}")
        if self.sessions:
            self.list.setCurrentRow(0)
        else:
            self.preview.setPlainText("No hay evidencias disponibles.")

    def _preview(self, index: int):
        if index < 0 or index >= len(self.sessions):
            return
        session = self.sessions[index]
        manifest = session / "manifest.json"
        if manifest.exists():
            self.preview.setPlainText(
                manifest.read_text(encoding="utf-8", errors="replace")
            )
        else:
            files = [
                str(path.relative_to(session))
                for path in session.rglob("*")
                if path.is_file()
            ]
            self.preview.setPlainText("\n".join(files))

    def _export(self):
        index = self.list.currentRow()
        if index < 0 or index >= len(self.sessions):
            return
        destination = styled_existing_directory(
            self,
            "Selecciona la carpeta de salida",
            str(default_article_dir()),
        )
        if destination:
            out = export_article_package(
                self.sessions[index],
                destination,
            )
            self.preview.appendPlainText(
                f"\n\nExportado a:\n{out}"
            )


class ReportsPage(QWidget):
    save_requested = Signal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("Reportes")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Resumen ejecutivo y trazabilidad del ciclo correctivo."
        )
        subtitle.setObjectName("Subheading")
        layout.addWidget(subtitle)

        metrics = QHBoxLayout()
        self.controls = MetricCard("Controles", "0", "Evaluados")
        self.findings = MetricCard("Hallazgos", "0", "P1 + P2")
        self.corrected = MetricCard("Corregidos", "0", "Evidencia CORREGIDO")
        metrics.addWidget(self.controls)
        metrics.addWidget(self.findings)
        metrics.addWidget(self.corrected)
        layout.addLayout(metrics)

        card = Card()
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(16, 14, 16, 14)
        card_l.addWidget(
            SectionHeader(
                "Exportación",
                "Conserva un reporte técnico independiente de la interfaz.",
            )
        )
        save = PrimaryButton("Guardar reporte JSON")
        save.clicked.connect(self.save_requested.emit)
        card_l.addWidget(save)
        card_l.addStretch(1)
        layout.addWidget(card, 1)

    def refresh(self):
        rows = self.controller.rows
        findings = sum(
            row.get("estado") == "HALLAZGO"
            for row in rows
        )
        corrected = 0
        if self.controller.evidence_base.exists():
            for session in self.controller.evidence_base.iterdir():
                manifest = session / "manifest.json"
                if not manifest.exists():
                    continue
                try:
                    payload = json.loads(
                        manifest.read_text(encoding="utf-8")
                    )
                except Exception:
                    continue
                corrected += payload.get("estado_final") == "CORREGIDO"
        self.controls.set_value(str(len(rows)))
        self.findings.set_value(str(findings))
        self.corrected.set_value(str(corrected))


class SettingsPage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._editing_profile_id: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("Configuración")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        card = Card()
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(16, 14, 16, 14)
        card_l.addWidget(
            SectionHeader(
                "Datos persistentes",
                "Ubicaciones utilizadas por Aegis Auditor.",
            )
        )
        self.paths = QLabel()
        self.paths.setObjectName("Muted")
        self.paths.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        card_l.addWidget(self.paths)
        layout.addWidget(card)

        ia = Card()
        ia_l = QVBoxLayout(ia)
        ia_l.setContentsMargins(16, 14, 16, 14)
        ia_l.setSpacing(10)
        ia_l.addWidget(
            SectionHeader(
                "Inteligencia artificial",
                "Guarda varios proveedores y modelos, cambia el activo cuando "
                "quieras e importa OpenCode solo si lo necesitas.",
            )
        )

        self.ai = QLabel()
        self.ai.setObjectName("Muted")
        self.ai.setWordWrap(True)
        ia_l.addWidget(self.ai)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Perfil IA"))
        self.ai_profiles = QComboBox()
        self.ai_profiles.setMinimumWidth(280)
        self.ai_profiles.currentIndexChanged.connect(
            self._profile_changed
        )
        profile_row.addWidget(self.ai_profiles, 1)

        activate_ai = QPushButton("Usar seleccionado")
        activate_ai.clicked.connect(self._activate_ai)
        profile_row.addWidget(activate_ai)

        new_ai = QPushButton("Nuevo")
        new_ai.clicked.connect(self._new_ai)
        profile_row.addWidget(new_ai)

        duplicate_ai = QPushButton("Duplicar")
        duplicate_ai.clicked.connect(self._duplicate_ai)
        profile_row.addWidget(duplicate_ai)

        delete_ai = QPushButton("Eliminar")
        delete_ai.clicked.connect(self._delete_ai)
        profile_row.addWidget(delete_ai)
        ia_l.addLayout(profile_row)

        ai_grid = QGridLayout()
        ai_grid.setHorizontalSpacing(10)
        ai_grid.setVerticalSpacing(8)

        ai_grid.addWidget(QLabel("Nombre"), 0, 0)
        self.ai_profile_name = QLineEdit()
        self.ai_profile_name.setPlaceholderText(
            "Ej. UTB - Gemma, Ollama local, LM Studio"
        )
        ai_grid.addWidget(self.ai_profile_name, 0, 1)

        ai_grid.addWidget(QLabel("URL base"), 1, 0)
        self.ai_base_url = QLineEdit()
        self.ai_base_url.setPlaceholderText(
            "https://servidor-ejemplo/v1"
        )
        ai_grid.addWidget(self.ai_base_url, 1, 1)

        ai_grid.addWidget(QLabel("Modelo"), 2, 0)
        self.ai_model = QLineEdit()
        self.ai_model.setPlaceholderText("lab-coder")
        ai_grid.addWidget(self.ai_model, 2, 1)

        ai_grid.addWidget(QLabel("API key"), 3, 0)
        self.ai_key = QLineEdit()
        self.ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_key.setPlaceholderText(
            "Vacía conserva la clave guardada; puede ser opcional"
        )
        ai_grid.addWidget(self.ai_key, 3, 1)

        ia_l.addLayout(ai_grid)

        ai_actions = QHBoxLayout()
        save_ai = PrimaryButton("Guardar perfil IA")
        save_ai.clicked.connect(self._save_ai)
        ai_actions.addWidget(save_ai)

        import_ai = QPushButton("Importar desde OpenCode")
        import_ai.clicked.connect(self._import_ai)
        ai_actions.addWidget(import_ai)
        ai_actions.addStretch(1)
        ia_l.addLayout(ai_actions)

        self.ai_path = QLabel()
        self.ai_path.setObjectName("Muted")
        self.ai_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.ai_path.setWordWrap(True)
        ia_l.addWidget(self.ai_path)

        layout.addWidget(ia)
        layout.addStretch(1)

    def _selected_profile_id(self) -> str | None:
        value = self.ai_profiles.currentData()
        return str(value) if value else None

    def _load_profile_fields(self, profile_id: str | None) -> None:
        if not profile_id:
            return
        settings = self.controller.ai_profile_settings(profile_id)
        if not settings:
            return
        self._editing_profile_id = profile_id
        self.ai_profile_name.setText(
            str(settings.get("profile_name") or "")
        )
        self.ai_base_url.setText(str(settings.get("base_url") or ""))
        self.ai_model.setText(
            str(settings.get("model_id") or "lab-coder")
        )
        self.ai_key.clear()

    def _profile_changed(self, _index: int) -> None:
        self._load_profile_fields(self._selected_profile_id())

    def _new_ai(self) -> None:
        self._editing_profile_id = None
        self.ai_profiles.setCurrentIndex(-1)
        self.ai_profile_name.clear()
        self.ai_base_url.clear()
        self.ai_model.setText("lab-coder")
        self.ai_key.clear()
        self.ai_profile_name.setFocus()

    def _save_ai(self) -> None:
        self.controller.save_ai_settings(
            profile_id=self._editing_profile_id,
            profile_name=self.ai_profile_name.text().strip(),
            base_url=self.ai_base_url.text().strip(),
            model_id=self.ai_model.text().strip() or "lab-coder",
            api_key=self.ai_key.text().strip() or None,
        )
        self.ai_key.clear()

    def _activate_ai(self) -> None:
        profile_id = self._selected_profile_id()
        if profile_id:
            self.controller.select_ai_profile(profile_id)

    def _duplicate_ai(self) -> None:
        profile_id = self._selected_profile_id()
        if profile_id:
            self._editing_profile_id = None
            self.controller.duplicate_ai_profile(profile_id)

    def _delete_ai(self) -> None:
        profile_id = self._selected_profile_id()
        if not profile_id:
            return
        name = self.ai_profiles.currentText().replace(" ✓ activo", "")
        answer = QMessageBox.question(
            self,
            "Eliminar perfil IA",
            f"¿Eliminar el perfil '{name}'?\n\n"
            "La configuración y su clave local dejarán de estar disponibles.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._editing_profile_id = None
            self.controller.delete_ai_profile(profile_id)

    def _import_ai(self) -> None:
        self._editing_profile_id = None
        self.controller.import_ai_from_opencode()
        self.ai_key.clear()

    def refresh(self) -> None:
        enabled, active_label = self.controller.ai_status()
        settings = self.controller.ai_settings()
        profiles = self.controller.ai_profiles()

        self.paths.setText(
            f"Config: {default_config_dir()}\n"
            f"Evidencias: {default_evidence_dir()}\n"
            f"Recetas: {default_recipe_dir()}\n"
            f"Artículo: {default_article_dir()}"
        )
        self.ai.setText(
            f"● IA activa · {active_label}"
            if enabled
            else (
                "○ No configurada · crea un perfil IA o importa OpenCode. "
                "Puedes conservar varios proveedores y alternar entre ellos."
            )
        )
        self.ai.setStyleSheet(
            f"color:{COLORS['success'] if enabled else COLORS['muted']};"
        )

        previous = (
            self._editing_profile_id
            or self._selected_profile_id()
            or str(settings.get("profile_id") or "")
        )

        self.ai_profiles.blockSignals(True)
        self.ai_profiles.clear()
        selected_index = -1
        for index, item in enumerate(profiles):
            label = str(item.get("name") or item.get("id") or "Perfil IA")
            if item.get("active"):
                label += " ✓ activo"
            profile_id = str(item.get("id") or "")
            self.ai_profiles.addItem(label, profile_id)
            if profile_id == previous:
                selected_index = index
            elif (
                selected_index < 0
                and profile_id == str(settings.get("profile_id") or "")
            ):
                selected_index = index

        if selected_index < 0 and self.ai_profiles.count():
            selected_index = 0
        self.ai_profiles.setCurrentIndex(selected_index)
        self.ai_profiles.blockSignals(False)

        selected_id = self._selected_profile_id()
        if selected_id:
            self._load_profile_fields(selected_id)
        elif not profiles:
            self._editing_profile_id = None
            if not self.ai_model.text():
                self.ai_model.setText("lab-coder")

        config_path = (
            settings.get("config_path")
            or str(default_ai_config_path())
        )
        self.ai_path.setText(
            f"Perfiles guardados: {len(profiles)} · "
            f"Configuración local: {config_path}\n"
            "La API key de cada perfil se guarda localmente y nunca se "
            "muestra en pantalla ni se incorpora a evidencias o releases."
        )

