"""Stepper horizontal premium del flujo de auditoría."""

from __future__ import annotations

import customtkinter as ctk

from ..theme import COLORS, FONT_FAMILY


class ProgressSteps(ctk.CTkFrame):
    STEPS = (
        ("Seleccionar", "Aplicación"),
        ("Generar", "Perfil"),
        ("Analizar", "P1 + P2"),
        ("Corregir", "Remediación"),
        ("Validar", "Evidencia"),
    )

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.active = 0
        self.step_widgets = []
        self.connectors = []

        for i in range(len(self.STEPS) * 2 - 1):
            self.grid_columnconfigure(i, weight=1 if i % 2 == 0 else 2)

        for index, (title, subtitle) in enumerate(self.STEPS):
            holder = ctk.CTkFrame(self, fg_color="transparent")
            holder.grid(row=0, column=index * 2, sticky="nsew", padx=2)

            badge = ctk.CTkLabel(
                holder,
                text=str(index + 1),
                width=34,
                height=34,
                corner_radius=17,
                fg_color=COLORS["surface_3"],
                text_color=COLORS["muted"],
                font=(FONT_FAMILY, 11, "bold"),
            )
            badge.pack(anchor="center")

            title_label = ctk.CTkLabel(
                holder,
                text=title,
                text_color=COLORS["muted"],
                font=(FONT_FAMILY, 10, "bold"),
            )
            title_label.pack(anchor="center", pady=(6, 0))

            subtitle_label = ctk.CTkLabel(
                holder,
                text=subtitle,
                text_color=COLORS["muted_2"],
                font=(FONT_FAMILY, 8),
            )
            subtitle_label.pack(anchor="center", pady=(0, 1))

            self.step_widgets.append((badge, title_label, subtitle_label))

            if index < len(self.STEPS) - 1:
                connector_wrap = ctk.CTkFrame(self, fg_color="transparent", height=34)
                connector_wrap.grid(
                    row=0,
                    column=index * 2 + 1,
                    sticky="ew",
                    padx=0,
                )
                connector_wrap.grid_rowconfigure(0, weight=1)
                connector_wrap.grid_rowconfigure(2, weight=1)
                connector = ctk.CTkFrame(
                    connector_wrap,
                    height=3,
                    fg_color="#244052",
                    corner_radius=2,
                )
                connector.grid(row=1, column=0, sticky="ew", padx=4)
                connector_wrap.grid_columnconfigure(0, weight=1)
                self.connectors.append(connector)

        self.set_step(0)

    def set_step(self, active: int):
        self.active = max(0, min(active, len(self.STEPS)))

        for index, (badge, title, subtitle) in enumerate(self.step_widgets):
            if index < self.active:
                badge.configure(
                    text="✓",
                    fg_color=COLORS["accent"],
                    text_color="#FFFFFF",
                )
                title.configure(text_color=COLORS["text"])
                subtitle.configure(text_color=COLORS["muted"])
            elif index == self.active and self.active < len(self.STEPS):
                badge.configure(
                    text=str(index + 1),
                    fg_color=COLORS["accent"],
                    text_color="#FFFFFF",
                )
                title.configure(text_color="#FFFFFF")
                subtitle.configure(text_color=COLORS["muted"])
            else:
                badge.configure(
                    text=str(index + 1),
                    fg_color="#18364B",
                    text_color=COLORS["muted"],
                )
                title.configure(text_color=COLORS["muted"])
                subtitle.configure(text_color=COLORS["muted_2"])

        for index, connector in enumerate(self.connectors):
            connector.configure(
                fg_color=COLORS["accent"] if index < self.active else "#244052"
            )
