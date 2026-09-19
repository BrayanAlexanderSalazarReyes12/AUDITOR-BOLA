"""Consola visual reutilizable."""

from __future__ import annotations

import customtkinter as ctk

from ..theme import COLORS, MONO_FAMILY


class LiveConsole(ctk.CTkTextbox):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color="#04101A",
            border_width=1,
            border_color=COLORS["border_soft"],
            corner_radius=10,
            text_color="#BFD8E8",
            font=(MONO_FAMILY, 10),
            wrap="none",
            **kwargs,
        )
        self.configure(state="disabled")

    def append(self, text: str):
        self.configure(state="normal")
        self.insert("end", text.rstrip() + "\n")
        self.see("end")
        self.configure(state="disabled")

    def clear(self):
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")
