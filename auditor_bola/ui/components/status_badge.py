"""Badges de estado."""

from __future__ import annotations

import customtkinter as ctk

from ..theme import COLORS, FONT_FAMILY


class StatusBadge(ctk.CTkLabel):
    def __init__(self, master, text: str = "Sin estado", status: str = "neutral"):
        super().__init__(
            master,
            text=text,
            height=28,
            corner_radius=14,
            padx=12,
            font=(FONT_FAMILY, 10, "bold"),
        )
        self.set_status(text, status)

    def set_status(self, text: str, status: str):
        colors = {
            "success": (COLORS["success"], "#06241B"),
            "danger": (COLORS["danger"], "#2A0C12"),
            "warning": (COLORS["warning"], "#2B210B"),
            "info": (COLORS["accent"], "#071D2E"),
            "neutral": (COLORS["surface_3"], COLORS["text"]),
        }
        fg, text_color = colors.get(status, colors["neutral"])
        self.configure(text=text, fg_color=fg, text_color=text_color)
