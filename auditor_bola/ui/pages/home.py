"""Página de Inicio de la interfaz moderna."""

from __future__ import annotations

import customtkinter as ctk

from ..components.cards import ActionButton, MetricCard, SectionCard
from ..components.console import LiveConsole
from ..components.progress_steps import ProgressSteps
from ..theme import COLORS, FONT_FAMILY


class HomePage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=COLORS["bg"])
        self.app = app
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(
            self,
            text="Centro de operación",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 24, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=(2, 0))

        ctk.CTkLabel(
            self,
            text=(
                "Carga una aplicación, genera el perfil, audita P1 + P2, "
                "corrige y conserva evidencia verificable."
            ),
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 11),
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=(2, 12))

        metrics = ctk.CTkFrame(self, fg_color="transparent")
        metrics.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        for col in range(4):
            metrics.grid_columnconfigure(col, weight=1)

        self.project_card = MetricCard(metrics, "Proyecto", "Sin cargar", "Código objetivo")
        self.project_card.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.profile_card = MetricCard(metrics, "Perfil", "Sin perfil", "Configuración")
        self.profile_card.grid(row=0, column=1, sticky="ew", padx=5)

        self.process_card = MetricCard(metrics, "Proceso", "No administrado", "Runtime")
        self.process_card.grid(row=0, column=2, sticky="ew", padx=5)

        self.findings_card = MetricCard(metrics, "Hallazgos", "0", "P1 0 · P2 0")
        self.findings_card.grid(row=0, column=3, sticky="ew", padx=(5, 0))

        progress_card = SectionCard(
            self,
            "Flujo de auditoría",
            "Estado del ciclo completo de Aegis.",
        )
        progress_card.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self.progress_steps = ProgressSteps(progress_card)
        self.progress_steps.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 16))

        console_card = SectionCard(
            self,
            "Actividad en tiempo real",
            "Operaciones, runtime, diagnóstico y remediación.",
        )
        console_card.grid(row=4, column=0, sticky="nsew", padx=(0, 6))
        console_card.grid_rowconfigure(2, weight=1)
        self.console = LiveConsole(console_card, height=240)
        self.console.grid(row=2, column=0, sticky="nsew", padx=16, pady=(6, 16))

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=4, column=1, sticky="nsew", padx=(6, 0))
        right.grid_columnconfigure(0, weight=1)

        project_card = SectionCard(
            right,
            "Proyecto actual",
            "Información operativa del objetivo cargado.",
        )
        project_card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.project_info = ctk.CTkLabel(
            project_card,
            text="No hay una aplicación cargada.",
            justify="left",
            anchor="nw",
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 10),
        )
        self.project_info.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 16))

        runtime_card = SectionCard(
            right,
            "Runtime",
            "Control del proceso objetivo.",
        )
        runtime_card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        runtime_card.grid_columnconfigure((0, 1), weight=1)

        app.btn_start = ActionButton(
            runtime_card, "▶ Iniciar", app._start_target, "success"
        )
        app.btn_start.grid(row=2, column=0, sticky="ew", padx=(16, 5), pady=(8, 5))

        app.btn_stop = ActionButton(
            runtime_card, "■ Detener", app._stop_target, "danger"
        )
        app.btn_stop.grid(row=2, column=1, sticky="ew", padx=(5, 16), pady=(8, 5))

        app.btn_restart = ActionButton(
            runtime_card, "↻ Reiniciar", app._restart_target
        )
        app.btn_restart.grid(row=3, column=0, sticky="ew", padx=(16, 5), pady=(5, 8))

        app.btn_diagnose = ActionButton(
            runtime_card, "◈ Diagnosticar P1 + P2", app._diagnose, "primary"
        )
        app.btn_diagnose.grid(row=3, column=1, sticky="ew", padx=(5, 16), pady=(5, 8))

        app.lbl_process = ctk.CTkLabel(
            runtime_card,
            text="Proceso: no administrado",
            text_color=COLORS["muted"],
            anchor="w",
            font=(FONT_FAMILY, 9),
        )
        app.lbl_process.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 4))

        app.chk_auto_manage = ctk.CTkCheckBox(
            runtime_card,
            text="Gestionar reinicio al corregir",
            variable=app.auto_manage_var,
            command=app._refresh_state,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 9),
        )
        app.chk_auto_manage.grid(row=5, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 14))

        quick = SectionCard(
            right,
            "Acciones rápidas",
            "Atajos al flujo principal.",
        )
        quick.grid(row=2, column=0, sticky="ew")
        quick.grid_columnconfigure(0, weight=1)

        ActionButton(
            quick,
            "＋ Cargar / Importar",
            app._open_load_center,
            "primary",
        ).grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 5))

        ActionButton(
            quick,
            "✦ Correcciones con IA",
            lambda: app._route("remediation"),
        ).grid(row=3, column=0, sticky="ew", padx=16, pady=5)

        ActionButton(
            quick,
            "▧ Evidencias",
            lambda: app._route("evidence"),
        ).grid(row=4, column=0, sticky="ew", padx=16, pady=(5, 14))
