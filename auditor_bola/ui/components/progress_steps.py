"""Indicador visual del flujo de trabajo."""

from __future__ import annotations

import customtkinter as ctk

from ..theme import COLORS, FONT_FAMILY


class ProgressSteps(ctk.CTkFrame):
    STEPS = (
        ("Cargar", "Aplicación"),
        ("Perfil", "Configuración"),
        ("Analizar", "P1 + P2"),
        ("Corregir", "Remediación"),
        ("Validar", "Evidencia"),
    )

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.active = 0
        self.items = []

        for index, (title, subtitle) in enumerate(self.STEPS):
            self.grid_columnconfigure(index * 2, weight=1)

            holder = ctk.CTkFrame(self, fg_color="transparent")
            holder.grid(row=0, column=index * 2, sticky="ew", padx=3)

            badge = ctk.CTkLabel(
                holder,
                text=str(index + 1),
                width=32,
                height=32,
                corner_radius=16,
                fg_color=COLORS["surface_3"],
                text_color=COLORS["muted"],
                font=(FONT_FAMILY, 12, "bold"),
            )
            badge.pack()

            title_label = ctk.CTkLabel(
                holder,
                text=title,
                text_color=COLORS["text"],
                font=(FONT_FAMILY, 10, "bold"),
            )
            title_label.pack(pady=(5, 0))

            subtitle_label = ctk.CTkLabel(
                holder,
                text=subtitle,
                text_color=COLORS["muted"],
                font=(FONT_FAMILY, 9),
            )
            subtitle_label.pack()

            self.items.append((badge, title_label, subtitle_label))

            if index < len(self.STEPS) - 1:
                line = ctk.CTkProgressBar(
                    self,
                    height=4,
                    corner_radius=2,
                    fg_color="#183246",
                    progress_color=COLORS["accent"],
                )
                line.grid(row=0, column=index * 2 + 1, sticky="ew", padx=5)
                line.set(0)
                self.items.append(line)

        self.set_step(0)

    def set_step(self, active: int):
        self.active = max(0, min(active, len(self.STEPS)))

        logical = 0
        for item in self.items:
            if isinstance(item, tuple):
                badge, title, subtitle = item
                if logical < self.active:
                    badge.configure(
                        text="✓",
                        fg_color=COLORS["success"],
                        text_color="#06111D",
                    )
                    title.configure(text_color="#D9FFF3")
                elif logical == self.active and self.active < len(self.STEPS):
                    badge.configure(
                        text=str(logical + 1),
                        fg_color=COLORS["accent"],
                        text_color="#FFFFFF",
                    )
                    title.configure(text_color="#FFFFFF")
                else:
                    badge.configure(
                        text=str(logical + 1),
                        fg_color=COLORS["surface_3"],
                        text_color=COLORS["muted"],
                    )
                    title.configure(text_color=COLORS["muted"])
                logical += 1
            else:
                completed_before = logical <= self.active
                item.set(1 if completed_before and logical > 0 else 0)
