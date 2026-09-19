"""Cabecera premium de Aegis Auditor."""

from __future__ import annotations

import customtkinter as ctk

from ..theme import COLORS, FONT_FAMILY
from .status_badge import StatusBadge


class Topbar(ctk.CTkFrame):
    def __init__(self, master, *, on_load, on_new_project):
        super().__init__(
            master,
            height=92,
            fg_color=COLORS["topbar"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
        )
        self.pack_propagate(False)
        self.grid_columnconfigure(0, weight=1)

        self.left = ctk.CTkFrame(self, fg_color="transparent")
        self.left.grid(row=0, column=0, sticky="nsew", padx=(18, 8), pady=13)

        ctk.CTkLabel(
            self.left,
            text="Bienvenido a Aegis Auditor",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 20, "bold"),
            anchor="w",
        ).pack(anchor="w")

        self.subtitle_label = ctk.CTkLabel(
            self.left,
            text="Analiza, corrige y aprende. Seguridad inteligente para cualquier aplicación.",
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 11),
            anchor="w",
        )
        self.subtitle_label.pack(anchor="w", pady=(3, 0))

        self.center = ctk.CTkFrame(self, fg_color="transparent")
        self.center.grid(row=0, column=1, sticky="e", padx=10, pady=12)

        self.quote_label = ctk.CTkLabel(
            self.center,
            text="“ Detectar es importante; corregir y aprender lo hace extraordinario. ”",
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 9, "italic"),
            justify="center",
        )
        self.quote_label.pack()

        self.right = ctk.CTkFrame(
            self,
            fg_color="#0D2A3E",
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        self.right.grid(row=0, column=2, sticky="e", padx=12, pady=11)

        self.user_badge = ctk.CTkLabel(
            self.right,
            text="●",
            width=34,
            text_color=COLORS["cyan"],
            font=(FONT_FAMILY, 18, "bold"),
        )
        self.user_badge.grid(row=0, column=0, rowspan=2, padx=(10, 6), pady=8)

        self.project_label = ctk.CTkLabel(
            self.right,
            text="Sin proyecto",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 10, "bold"),
            anchor="w",
        )
        self.project_label.grid(row=0, column=1, sticky="w", padx=(0, 10), pady=(8, 0))

        self.process_badge = StatusBadge(
            self.right,
            text="No administrado",
            status="neutral",
        )
        self.process_badge.grid(row=1, column=1, sticky="w", padx=(0, 10), pady=(0, 8))

        self.new_button = ctk.CTkButton(
            self.right,
            text="＋ Nuevo",
            width=92,
            height=34,
            command=on_new_project,
            fg_color=COLORS["surface_3"],
            hover_color="#16405E",
            border_width=1,
            border_color=COLORS["border"],
        )
        self.new_button.grid(row=0, column=2, rowspan=2, padx=(4, 6), pady=12)

        self.load_button = ctk.CTkButton(
            self.right,
            text="Cargar ▾",
            width=102,
            height=34,
            command=on_load,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=(FONT_FAMILY, 10, "bold"),
        )
        self.load_button.grid(row=0, column=3, rowspan=2, padx=(0, 10), pady=12)

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
        self.configure(height=74 if compact else 92)

        if ultra:
            self.center.grid_remove()
            self.user_badge.grid_remove()
            self.process_badge.grid_remove()
            self.project_label.grid_remove()
            self.new_button.configure(text="＋", width=44)
            self.load_button.configure(text="Cargar", width=80)
        elif compact:
            self.center.grid_remove()
            self.user_badge.grid()
            self.project_label.grid()
            self.process_badge.grid()
            self.new_button.configure(text="＋ Nuevo", width=86)
            self.load_button.configure(text="Cargar ▾", width=92)
        else:
            self.center.grid()
            self.user_badge.grid()
            self.project_label.grid()
            self.process_badge.grid()
            self.new_button.configure(text="＋ Nuevo", width=92)
            self.load_button.configure(text="Cargar ▾", width=102)
