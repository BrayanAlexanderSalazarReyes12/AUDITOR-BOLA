"""Tarjetas reutilizables de la interfaz moderna."""

from __future__ import annotations

import customtkinter as ctk

from ..theme import COLORS, FONT_FAMILY, RADIUS


class MetricCard(ctk.CTkFrame):
    def __init__(self, master, title: str, value: str = "—", subtitle: str = ""):
        super().__init__(
            master,
            fg_color=COLORS["surface_2"],
            corner_radius=RADIUS,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text=title.upper(),
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 11),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 3))

        self.value_label = ctk.CTkLabel(
            self,
            text=value,
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 20, "bold"),
            anchor="w",
        )
        self.value_label.grid(row=1, column=0, sticky="ew", padx=16)

        self.subtitle_label = ctk.CTkLabel(
            self,
            text=subtitle,
            text_color=COLORS["muted_2"],
            font=(FONT_FAMILY, 10),
            anchor="w",
        )
        self.subtitle_label.grid(row=2, column=0, sticky="ew", padx=16, pady=(2, 14))

    def set(self, value: str, subtitle: str | None = None):
        self.value_label.configure(text=value)
        if subtitle is not None:
            self.subtitle_label.configure(text=subtitle)


class SectionCard(ctk.CTkFrame):
    def __init__(self, master, title: str, subtitle: str = ""):
        super().__init__(
            master,
            fg_color=COLORS["surface"],
            corner_radius=RADIUS,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text=title,
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 15, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 0))

        if subtitle:
            ctk.CTkLabel(
                self,
                text=subtitle,
                text_color=COLORS["muted"],
                font=(FONT_FAMILY, 10),
                anchor="w",
                justify="left",
            ).grid(row=1, column=0, sticky="ew", padx=16, pady=(3, 8))


class ActionButton(ctk.CTkButton):
    def __init__(self, master, text: str, command=None, kind: str = "secondary", **kwargs):
        palette = {
            "primary": (COLORS["accent"], COLORS["accent_hover"]),
            "success": (COLORS["success"], "#27B989"),
            "danger": (COLORS["danger"], "#D94F61"),
            "secondary": (COLORS["surface_3"], "#16405E"),
        }
        fg, hover = palette.get(kind, palette["secondary"])
        super().__init__(
            master,
            text=text,
            command=command,
            fg_color=fg,
            hover_color=hover,
            text_color="#FFFFFF",
            corner_radius=9,
            height=38,
            font=(FONT_FAMILY, 11, "bold" if kind == "primary" else "normal"),
            **kwargs,
        )
