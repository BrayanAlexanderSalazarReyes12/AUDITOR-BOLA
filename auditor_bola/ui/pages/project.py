"""Página de proyecto y recursos cargados."""

from __future__ import annotations

import customtkinter as ctk

from ..components.cards import ActionButton, SectionCard
from ..theme import COLORS, FONT_FAMILY


class ProjectPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=COLORS["bg"])
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text="Proyecto y auto-configuración",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 24, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(2, 12))

        resources = SectionCard(
            self,
            "Recursos del objetivo",
            "Carga los puntos de entrada necesarios para trabajar con la aplicación.",
        )
        resources.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        resources.grid_columnconfigure(1, weight=1)

        rows = [
            ("Perfil JSON", app._choose_config, "lbl_config", "Sin perfil seleccionado"),
            ("Código fuente", app._choose_target, "lbl_target", "Sin carpeta"),
            ("Evidencias", app._choose_evidence_base, "lbl_evidence", str(app.evidence_base)),
        ]
        for row, (title, command, attr, value) in enumerate(rows, start=2):
            ActionButton(
                resources,
                title,
                command,
            ).grid(row=row, column=0, sticky="ew", padx=(16, 8), pady=6)

            label = ctk.CTkLabel(
                resources,
                text=value,
                text_color=COLORS["muted"],
                font=(FONT_FAMILY, 10),
                anchor="w",
                justify="left",
                wraplength=520,
            )
            label.grid(row=row, column=1, sticky="ew", padx=(8, 16), pady=6)
            setattr(app, attr, label)

        auto = SectionCard(
            self,
            "Incorporación automática",
            "Aegis detecta stack, runtime, endpoints y genera config/*.json.",
        )
        auto.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        auto.grid_columnconfigure(0, weight=1)

        ActionButton(
            auto,
            "＋ Nuevo proyecto / Auto-configurar",
            app._new_project_wizard,
            "primary",
        ).grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 5))

        ActionButton(
            auto,
            "◇ Importar auditor-package.json",
            app._import_auditor_package,
        ).grid(row=3, column=0, sticky="ew", padx=16, pady=5)

        ActionButton(
            auto,
            "👥 Cargar cuentas y roles",
            app._import_accounts_roles,
        ).grid(row=4, column=0, sticky="ew", padx=16, pady=5)

        ActionButton(
            auto,
            "▤ Importar recetas / medicinas",
            app._import_recipes,
        ).grid(row=5, column=0, sticky="ew", padx=16, pady=(5, 16))

        info = SectionCard(
            self,
            "Perfil detectado",
            "Resumen técnico y vista del sistema incorporado.",
        )
        info.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        self.info_text = ctk.CTkTextbox(
            info,
            height=240,
            fg_color="#04101A",
            border_width=1,
            border_color=COLORS["border_soft"],
            text_color="#BFD8E8",
            font=("Consolas", 10),
        )
        self.info_text.grid(row=2, column=0, sticky="nsew", padx=16, pady=(8, 16))
        self.info_text.insert("1.0", "Carga o genera un perfil para ver su información.")
        self.info_text.configure(state="disabled")

    def set_info(self, text: str):
        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", "end")
        self.info_text.insert("1.0", text)
        self.info_text.configure(state="disabled")
