"""Página de configuración del producto."""

from __future__ import annotations

import customtkinter as ctk

from ...app_paths import (
    default_article_dir,
    default_config_dir,
    default_evidence_dir,
    default_recipe_dir,
)
from ..components.cards import ActionButton, SectionCard
from ..theme import COLORS, FONT_FAMILY


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=COLORS["bg"])
        self.app = app
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Configuración",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 24, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(2, 12))

        paths = SectionCard(
            self,
            "Datos de Aegis",
            "Rutas persistentes utilizadas por la aplicación.",
        )
        paths.grid(row=1, column=0, sticky="ew")
        text = (
            f"Config: {default_config_dir()}\n"
            f"Evidencias: {default_evidence_dir()}\n"
            f"Recetas: {default_recipe_dir()}\n"
            f"Artículo: {default_article_dir()}"
        )
        ctk.CTkLabel(
            paths,
            text=text,
            text_color=COLORS["muted"],
            justify="left",
            anchor="w",
            font=("Consolas", 10),
        ).grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 16))

        ia = SectionCard(
            self,
            "Proveedor IA",
            "Gemma / OpenCode se utiliza para generar y adaptar recetas.",
        )
        ia.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ActionButton(
            ia,
            "Recargar configuración de IA",
            lambda: app._configure_ai_from_load_center(),
            "primary",
        ).grid(row=2, column=0, sticky="w", padx=16, pady=(10, 16))
