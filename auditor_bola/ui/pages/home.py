"""Dashboard principal premium de Aegis Auditor."""

from __future__ import annotations

import customtkinter as ctk

from ..components.cards import ActionButton, MetricCard, SectionCard
from ..components.console import LiveConsole
from ..components.progress_steps import ProgressSteps
from ..theme import COLORS, FONT_FAMILY, MONO_FAMILY


class HomePage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=COLORS["bg"])
        self.app = app

        self.grid_columnconfigure(0, weight=7)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(2, weight=3)
        self.grid_rowconfigure(3, weight=2)

        # ----------------------------------------------------------
        # Flujo superior
        # ----------------------------------------------------------
        self.flow_card = ctk.CTkFrame(
            self,
            fg_color=COLORS["surface"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
        )
        self.flow_card.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 10),
        )
        self.flow_card.grid_columnconfigure(0, weight=1)

        self.progress_steps = ProgressSteps(self.flow_card)
        self.progress_steps.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=22,
            pady=14,
        )

        # ----------------------------------------------------------
        # Panel principal de operación
        # ----------------------------------------------------------
        self.operation_card = SectionCard(
            self,
            "Ejecución y diagnóstico",
            "Sigue el ciclo completo sin perder trazabilidad del objetivo.",
        )
        self.operation_card.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 6),
            pady=(0, 10),
        )
        self.operation_card.grid_columnconfigure(0, weight=1)

        self.operation_rows = ctk.CTkFrame(
            self.operation_card,
            fg_color="transparent",
        )
        self.operation_rows.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=16,
            pady=(4, 6),
        )
        self.operation_rows.grid_columnconfigure(1, weight=1)

        self.stage_widgets = {}
        stages = (
            ("project", "Aplicación", "Selecciona o carga el proyecto objetivo."),
            ("profile", "Perfil de configuración", "Genera o carga el perfil JSON."),
            ("audit", "Auditoría P1 + P2", "Ejecuta los controles de ambos pilares."),
            ("remediation", "Corrección y verificación", "Aplica una receta y comprueba el resultado."),
        )
        for row, (key, title, subtitle) in enumerate(stages):
            icon = ctk.CTkLabel(
                self.operation_rows,
                text="○",
                width=30,
                text_color=COLORS["muted"],
                font=(FONT_FAMILY, 16, "bold"),
            )
            icon.grid(row=row, column=0, sticky="n", padx=(0, 6), pady=5)

            text_holder = ctk.CTkFrame(
                self.operation_rows,
                fg_color="transparent",
            )
            text_holder.grid(row=row, column=1, sticky="ew", pady=5)

            title_label = ctk.CTkLabel(
                text_holder,
                text=title,
                text_color=COLORS["text"],
                font=(FONT_FAMILY, 10, "bold"),
                anchor="w",
            )
            title_label.pack(anchor="w")

            subtitle_label = ctk.CTkLabel(
                text_holder,
                text=subtitle,
                text_color=COLORS["muted"],
                font=(FONT_FAMILY, 9),
                anchor="w",
            )
            subtitle_label.pack(anchor="w")

            status = ctk.CTkLabel(
                self.operation_rows,
                text="Pendiente",
                text_color=COLORS["muted"],
                font=(FONT_FAMILY, 9),
                anchor="e",
            )
            status.grid(row=row, column=2, sticky="e", padx=(10, 0), pady=5)

            self.stage_widgets[key] = (icon, title_label, subtitle_label, status)

        self.task_progress = ctk.CTkProgressBar(
            self.operation_card,
            height=7,
            fg_color="#19364A",
            progress_color=COLORS["accent"],
            corner_radius=4,
        )
        self.task_progress.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=16,
            pady=(5, 10),
        )
        self.task_progress.set(0)

        actions = ctk.CTkFrame(
            self.operation_card,
            fg_color="transparent",
        )
        actions.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=16,
            pady=(0, 15),
        )
        for column in range(4):
            actions.grid_columnconfigure(column, weight=1)

        app.btn_start = ActionButton(
            actions,
            "▶ Iniciar",
            app._start_target,
            "success",
        )
        app.btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        app.btn_stop = ActionButton(
            actions,
            "■ Detener",
            app._stop_target,
            "danger",
        )
        app.btn_stop.grid(row=0, column=1, sticky="ew", padx=4)

        app.btn_restart = ActionButton(
            actions,
            "↻ Reiniciar",
            app._restart_target,
        )
        app.btn_restart.grid(row=0, column=2, sticky="ew", padx=4)

        app.btn_diagnose = ActionButton(
            actions,
            "◈ Diagnosticar P1 + P2",
            app._diagnose,
            "primary",
        )
        app.btn_diagnose.grid(row=0, column=3, sticky="ew", padx=(4, 0))

        app.lbl_process = ctk.CTkLabel(
            self.operation_card,
            text="Proceso: no administrado",
            text_color=COLORS["muted"],
            anchor="w",
            font=(FONT_FAMILY, 9),
        )
        app.lbl_process.grid(
            row=5,
            column=0,
            sticky="w",
            padx=16,
            pady=(0, 4),
        )

        app.chk_auto_manage = ctk.CTkCheckBox(
            self.operation_card,
            text="Gestionar reinicio automáticamente al corregir",
            variable=app.auto_manage_var,
            command=app._refresh_state,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 9),
        )
        app.chk_auto_manage.grid(
            row=6,
            column=0,
            sticky="w",
            padx=16,
            pady=(0, 14),
        )

        # ----------------------------------------------------------
        # Rail derecho: proyecto
        # ----------------------------------------------------------
        self.right_rail = ctk.CTkFrame(self, fg_color="transparent")
        self.right_rail.grid(
            row=1,
            column=1,
            rowspan=3,
            sticky="nsew",
            padx=(6, 0),
            pady=(0, 0),
        )
        self.right_rail.grid_columnconfigure(0, weight=1)
        self.right_rail.grid_rowconfigure(2, weight=1)

        project_card = SectionCard(
            self.right_rail,
            "Información del proyecto",
            "Resumen técnico del objetivo activo.",
        )
        project_card.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.project_info = ctk.CTkLabel(
            project_card,
            text="No hay una aplicación cargada.",
            justify="left",
            anchor="nw",
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 9),
        )
        self.project_info.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=16,
            pady=(4, 14),
        )

        task_card = SectionCard(
            self.right_rail,
            "Tarea actual",
            "Estado de la operación en curso.",
        )
        task_card.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        self.current_task_label = ctk.CTkLabel(
            task_card,
            text="Esperando una aplicación",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 10, "bold"),
            anchor="w",
        )
        self.current_task_label.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=16,
            pady=(6, 2),
        )

        self.current_task_detail = ctk.CTkLabel(
            task_card,
            text="Usa Nuevo proyecto o Cargar / Importar para comenzar.",
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 9),
            anchor="w",
            justify="left",
            wraplength=300,
        )
        self.current_task_detail.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=16,
            pady=(0, 8),
        )

        self.current_task_progress = ctk.CTkProgressBar(
            task_card,
            height=7,
            fg_color="#19364A",
            progress_color=COLORS["accent"],
        )
        self.current_task_progress.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=16,
            pady=(0, 14),
        )
        self.current_task_progress.set(0)

        profile_card = SectionCard(
            self.right_rail,
            "Vista previa del perfil",
            "JSON operativo de la aplicación.",
        )
        profile_card.grid(row=2, column=0, sticky="nsew")
        profile_card.grid_rowconfigure(2, weight=1)

        self.profile_preview = ctk.CTkTextbox(
            profile_card,
            fg_color="#06131E",
            border_width=1,
            border_color=COLORS["border_soft"],
            text_color="#C7DDEC",
            font=(MONO_FAMILY, 9),
            wrap="none",
            height=170,
        )
        self.profile_preview.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=14,
            pady=(6, 14),
        )
        self.profile_preview.insert("1.0", "{\n  \"perfil\": \"sin cargar\"\n}")
        self.profile_preview.configure(state="disabled")

        # ----------------------------------------------------------
        # Consola
        # ----------------------------------------------------------
        self.console_card = SectionCard(
            self,
            "Consola en tiempo real",
            "Actividad del runtime, diagnóstico, IA y verificación.",
        )
        self.console_card.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=(0, 6),
            pady=(0, 10),
        )
        self.console_card.grid_rowconfigure(2, weight=1)
        self.console = LiveConsole(self.console_card, height=190)
        self.console.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=14,
            pady=(5, 14),
        )

        # ----------------------------------------------------------
        # Métricas compactas al pie
        # ----------------------------------------------------------
        self.metrics = ctk.CTkFrame(self, fg_color="transparent")
        self.metrics.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=(0, 6),
        )
        for col in range(4):
            self.metrics.grid_columnconfigure(col, weight=1)

        self.project_card = MetricCard(
            self.metrics,
            "Proyecto",
            "Sin cargar",
            "Código objetivo",
        )
        self.project_card.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.profile_card = MetricCard(
            self.metrics,
            "Perfil",
            "Sin perfil",
            "Configuración",
        )
        self.profile_card.grid(row=0, column=1, sticky="ew", padx=4)

        self.process_card = MetricCard(
            self.metrics,
            "Proceso",
            "No administrado",
            "Runtime",
        )
        self.process_card.grid(row=0, column=2, sticky="ew", padx=4)

        self.findings_card = MetricCard(
            self.metrics,
            "Hallazgos",
            "0",
            "P1 0 · P2 0",
        )
        self.findings_card.grid(row=0, column=3, sticky="ew", padx=(4, 0))

    def set_stage(self, key: str, state: str, detail: str | None = None):
        item = self.stage_widgets.get(key)
        if not item:
            return
        icon, _title, subtitle, status = item

        if state == "done":
            icon.configure(text="✓", text_color=COLORS["success"])
            status.configure(text="Completado", text_color=COLORS["success"])
        elif state == "active":
            icon.configure(text="●", text_color=COLORS["accent"])
            status.configure(text="En curso", text_color=COLORS["accent"])
        elif state == "error":
            icon.configure(text="!", text_color=COLORS["danger"])
            status.configure(text="Atención", text_color=COLORS["danger"])
        else:
            icon.configure(text="○", text_color=COLORS["muted"])
            status.configure(text="Pendiente", text_color=COLORS["muted"])

        if detail:
            subtitle.configure(text=detail)

    def set_profile_preview(self, text: str):
        self.profile_preview.configure(state="normal")
        self.profile_preview.delete("1.0", "end")
        self.profile_preview.insert("1.0", text)
        self.profile_preview.configure(state="disabled")

    def set_compact(self, compact: bool, ultra: bool = False):
        if ultra:
            self.grid_columnconfigure(0, weight=1)
            self.grid_columnconfigure(1, weight=0)

            self.operation_card.grid(
                row=1,
                column=0,
                columnspan=2,
                sticky="ew",
                padx=0,
                pady=(0, 8),
            )
            self.console_card.grid(
                row=2,
                column=0,
                columnspan=2,
                sticky="nsew",
                padx=0,
                pady=(0, 8),
            )
            self.metrics.grid(
                row=3,
                column=0,
                columnspan=2,
                sticky="ew",
                padx=0,
                pady=(0, 8),
            )
            self.right_rail.grid(
                row=4,
                column=0,
                columnspan=2,
                sticky="ew",
                padx=0,
            )
        else:
            self.grid_columnconfigure(0, weight=7)
            self.grid_columnconfigure(1, weight=3)

            self.operation_card.grid(
                row=1,
                column=0,
                columnspan=1,
                sticky="nsew",
                padx=(0, 6),
                pady=(0, 10),
            )
            self.console_card.grid(
                row=2,
                column=0,
                columnspan=1,
                sticky="nsew",
                padx=(0, 6),
                pady=(0, 10),
            )
            self.metrics.grid(
                row=3,
                column=0,
                columnspan=1,
                sticky="ew",
                padx=(0, 6),
                pady=0,
            )
            self.right_rail.grid(
                row=1,
                column=1,
                rowspan=3,
                columnspan=1,
                sticky="nsew",
                padx=(6, 0),
            )
