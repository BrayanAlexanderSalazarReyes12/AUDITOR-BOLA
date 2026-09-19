"""Topbar moderna con estado de proyecto y centro de carga."""

from __future__ import annotations

import customtkinter as ctk

from ..theme import COLORS, FONT_FAMILY
from .status_badge import StatusBadge


class Topbar(ctk.CTkFrame):
    def __init__(self, master, *, on_load, on_new_project):
        super().__init__(
            master,
            height=86,
            fg_color=COLORS["topbar"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        self.pack_propagate(False)
        self.grid_columnconfigure(0, weight=1)

        self.left = ctk.CTkFrame(self, fg_color="transparent")
        self.left.grid(row=0, column=0, sticky="nsew", padx=18, pady=12)
        left = self.left

        self.title_label = ctk.CTkLabel(
            left,
            text="Bienvenido a Aegis Auditor",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 18, "bold"),
            anchor="w",
        )
        self.title_label.pack(anchor="w")

        self.subtitle_label = ctk.CTkLabel(
            left,
            text=(
                "Analiza, corrige y aprende · Seguridad correctiva "
                "basada en Pilar 1 y Pilar 2"
            ),
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 10),
            anchor="w",
        )
        self.subtitle_label.pack(anchor="w", pady=(3, 0))

        self.right = ctk.CTkFrame(self, fg_color="transparent")
        self.right.grid(row=0, column=1, sticky="e", padx=14, pady=10)
        right = self.right

        self.project_label = ctk.CTkLabel(
            right,
            text="Sin proyecto",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 10, "bold"),
        )
        self.project_label.grid(row=0, column=0, padx=(0, 10))

        self.process_badge = StatusBadge(
            right,
            text="No administrado",
            status="neutral",
        )
        self.process_badge.grid(row=0, column=1, padx=(0, 10))

        ctk.CTkButton(
            right,
            text="＋ Nuevo",
            width=95,
            height=36,
            command=on_new_project,
            fg_color=COLORS["surface_3"],
            hover_color="#16405E",
            border_width=1,
            border_color=COLORS["border"],
        ).grid(row=0, column=2, padx=(0, 8))

        self.load_button = ctk.CTkButton(
            right,
            text="Cargar / Importar ▾",
            width=150,
            height=36,
            command=on_load,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=(FONT_FAMILY, 10, "bold"),
        )
        self.load_button.grid(row=0, column=3)

    def set_project(self, name: str | None, subtitle: str | None = None):
        self.project_label.configure(text=name or "Sin proyecto")
        if subtitle:
            self.subtitle_label.configure(text=subtitle)

    def set_process(self, running: bool, managed: bool):
        if running:
            self.process_badge.set_status("En ejecución", "success")
        elif managed:
            self.process_badge.set_status("Detenido", "warning")
        else:
            self.process_badge.set_status("No administrado", "neutral")

    def set_compact(self, compact: bool, ultra: bool = False):
        self.configure(height=66 if compact else 86)
        if ultra:
            if self.subtitle_label.winfo_manager():
                self.subtitle_label.pack_forget()
            self.project_label.grid_remove()
            self.load_button.configure(text="Cargar ▾", width=95)
        else:
            if not self.subtitle_label.winfo_manager():
                self.subtitle_label.pack(anchor="w", pady=(3, 0))
            self.project_label.grid()
            self.load_button.configure(
                text="Cargar / Importar ▾",
                width=125 if compact else 150,
            )
