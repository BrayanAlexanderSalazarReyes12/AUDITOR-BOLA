"""Sidebar moderna de navegación."""

from __future__ import annotations

import customtkinter as ctk

from ..theme import COLORS, FONT_FAMILY


class Sidebar(ctk.CTkFrame):
    def __init__(self, master, *, on_navigate, on_new_project, on_load_center):
        super().__init__(
            master,
            width=238,
            fg_color=COLORS["sidebar"],
            corner_radius=0,
            border_width=0,
        )
        self.pack_propagate(False)
        self.on_navigate = on_navigate
        self.buttons = {}
        self.active = None

        brand = ctk.CTkFrame(self, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(20, 14))

        shield = ctk.CTkLabel(
            brand,
            text="◆",
            width=48,
            height=48,
            corner_radius=12,
            fg_color="#0D4D78",
            text_color=COLORS["teal"],
            font=(FONT_FAMILY, 24, "bold"),
        )
        shield.pack(anchor="w")

        ctk.CTkLabel(
            brand,
            text="AEGIS AUDITOR",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 18, "bold"),
            anchor="w",
        ).pack(anchor="w", pady=(8, 0))

        ctk.CTkLabel(
            brand,
            text="SECURITY REMEDIATION STUDIO",
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 8, "bold"),
            anchor="w",
        ).pack(anchor="w")

        self.nav = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color="#12384F",
            scrollbar_button_hover_color="#1A526F",
        )
        self.nav.pack(fill="both", expand=True, padx=(8, 4), pady=(6, 8))

        self._add_nav("home", "⌂   Inicio")
        self._add_action("new", "＋   Nuevo proyecto", on_new_project)
        self._add_action("load", "▣   Cargar / Importar", on_load_center)
        self._add_nav("project", "⚙   Auto-configuración")
        self._separator()
        self._add_nav("audit", "◈   Auditoría P1 + P2")
        self._add_nav("remediation", "✦   Correcciones con IA")
        self._add_nav("knowledge", "▤   Recetas y conocimiento")
        self._separator()
        self._add_nav("evidence", "▧   Evidencias")
        self._add_nav("reports", "▦   Reportes")
        self._add_nav("log", "▥   Registro")
        self._separator()
        self._add_nav("settings", "⚙   Configuración")

        footer = ctk.CTkFrame(
            self,
            fg_color="#081A28",
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        footer.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            footer,
            text="P1 + P2 · MULTIPLATAFORMA",
            text_color=COLORS["teal"],
            font=(FONT_FAMILY, 9, "bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 2))

        self.ai_label = ctk.CTkLabel(
            footer,
            text="IA: comprobando…",
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 9),
            anchor="w",
        )
        self.ai_label.pack(fill="x", padx=12, pady=(0, 10))

        self.set_active("home")

    def _separator(self):
        ctk.CTkFrame(
            self.nav,
            height=1,
            fg_color=COLORS["border_soft"],
        ).pack(fill="x", padx=12, pady=8)

    def _button(self, text, command):
        button = ctk.CTkButton(
            self.nav,
            text=text,
            command=command,
            anchor="w",
            fg_color="transparent",
            hover_color="#0E3550",
            text_color="#C8D9E5",
            corner_radius=9,
            height=40,
            font=(FONT_FAMILY, 11),
        )
        button.pack(fill="x", padx=3, pady=2)
        return button

    def _add_nav(self, key: str, text: str):
        button = self._button(text, lambda k=key: self.on_navigate(k))
        self.buttons[key] = button

    def _add_action(self, key: str, text: str, command):
        self.buttons[key] = self._button(text, command)

    def set_active(self, key: str):
        self.active = key
        for name, button in self.buttons.items():
            if name == key:
                button.configure(
                    fg_color="#0E4E7A",
                    text_color="#FFFFFF",
                    font=(FONT_FAMILY, 11, "bold"),
                )
            elif name not in {"new", "load"}:
                button.configure(
                    fg_color="transparent",
                    text_color="#C8D9E5",
                    font=(FONT_FAMILY, 11),
                )

    def set_compact(self, compact: bool, ultra: bool = False):
        width = 154 if ultra else (192 if compact else 238)
        self.configure(width=width)

        if ultra:
            for key, button in self.buttons.items():
                current = button.cget("text")
                if "   " in current:
                    icon, label = current.split("   ", 1)
                    short = label[:14]
                    button.configure(text=f"{icon}   {short}")
