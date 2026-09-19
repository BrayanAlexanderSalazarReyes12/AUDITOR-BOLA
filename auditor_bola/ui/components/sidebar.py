"""Sidebar premium de navegación de Aegis Auditor."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ..theme import COLORS, FONT_FAMILY


class Sidebar(ctk.CTkFrame):
    def __init__(self, master, *, on_navigate, on_new_project, on_load_center):
        super().__init__(
            master,
            width=268,
            fg_color=COLORS["sidebar"],
            corner_radius=0,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        self.pack_propagate(False)
        self.on_navigate = on_navigate
        self.buttons = {}
        self.active = None

        self.brand = ctk.CTkFrame(self, fg_color="transparent")
        self.brand.pack(fill="x", padx=18, pady=(18, 10))

        shield = tk.Canvas(
            self.brand,
            width=92,
            height=92,
            background=COLORS["sidebar"],
            highlightthickness=0,
            bd=0,
        )
        shield.pack(anchor="center")
        shield.create_polygon(
            46, 4,
            82, 20,
            77, 61,
            46, 87,
            15, 61,
            10, 20,
            fill="#0C88D3",
            outline=COLORS["cyan"],
            width=2,
        )
        shield.create_polygon(
            46, 14,
            70, 25,
            67, 55,
            46, 75,
            25, 55,
            22, 25,
            fill="#0B2031",
            outline="",
        )
        shield.create_line(
            30, 45,
            41, 56,
            63, 32,
            fill="#FFFFFF",
            width=6,
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND,
        )
        shield.create_text(
            68,
            68,
            text="AI",
            fill=COLORS["cyan"],
            font=(FONT_FAMILY, 10, "bold"),
        )

        ctk.CTkLabel(
            self.brand,
            text="AEGIS AUDITOR",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 23, "bold"),
        ).pack(anchor="center", pady=(10, 0))

        ctk.CTkLabel(
            self.brand,
            text="AUDITORÍA · CORRECCIÓN · APRENDIZAJE",
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 8, "bold"),
        ).pack(anchor="center", pady=(2, 2))

        ctk.CTkLabel(
            self.brand,
            text="Seguridad correctiva para cualquier aplicación",
            text_color=COLORS["muted_2"],
            font=(FONT_FAMILY, 8),
        ).pack(anchor="center", pady=(0, 8))

        self.nav = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color="#12384F",
            scrollbar_button_hover_color="#1A526F",
            corner_radius=0,
        )
        self.nav.pack(fill="both", expand=True, padx=(10, 7), pady=(2, 6))

        self._add_nav("home", "⌂", "Inicio")
        self._add_action("new", "＋", "Nuevo proyecto", on_new_project)
        self._add_action("load", "▣", "Cargar / Importar", on_load_center)
        self._add_nav("project", "⚙", "Auto-configuración")

        self._separator()

        self._add_nav("audit", "◈", "Auditoría P1 + P2")
        self._add_nav("remediation", "✦", "Correcciones con IA")
        self._add_nav("knowledge", "▤", "Recetas y conocimiento")

        self._separator()

        self._add_nav("evidence", "▧", "Evidencias")
        self._add_nav("reports", "▦", "Reportes")
        self._add_nav("log", "▥", "Registro")
        self._add_nav("settings", "⚙", "Configuración")

        self.footer = ctk.CTkFrame(
            self,
            fg_color="#0A1D2B",
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        self.footer.pack(fill="x", padx=12, pady=(6, 12))

        ctk.CTkLabel(
            self.footer,
            text="AEGIS AUDITOR",
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 8, "bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 1))

        self.ai_label = ctk.CTkLabel(
            self.footer,
            text="● IA: comprobando…",
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 9),
            anchor="w",
        )
        self.ai_label.pack(fill="x", padx=12, pady=(0, 3))

        ctk.CTkLabel(
            self.footer,
            text="Pilar 1 + Pilar 2 · v1.0.0",
            text_color=COLORS["muted_2"],
            font=(FONT_FAMILY, 8),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 10))

        self.set_active("home")

    def _separator(self):
        ctk.CTkFrame(
            self.nav,
            height=1,
            fg_color=COLORS["border_soft"],
        ).pack(fill="x", padx=10, pady=8)

    def _button(self, icon: str, text: str, command):
        button = ctk.CTkButton(
            self.nav,
            text=f"{icon}   {text}",
            command=command,
            anchor="w",
            fg_color="transparent",
            hover_color="#103A57",
            text_color="#C9D9E4",
            corner_radius=9,
            height=42,
            border_width=0,
            font=(FONT_FAMILY, 11),
        )
        button.pack(fill="x", padx=2, pady=2)
        button._aegis_icon = icon
        button._aegis_label = text
        return button

    def _add_nav(self, key: str, icon: str, text: str):
        self.buttons[key] = self._button(
            icon,
            text,
            lambda k=key: self.on_navigate(k),
        )

    def _add_action(self, key: str, icon: str, text: str, command):
        self.buttons[key] = self._button(icon, text, command)

    def set_active(self, key: str):
        self.active = key
        for name, button in self.buttons.items():
            if name == key:
                button.configure(
                    fg_color="#114D78",
                    text_color="#FFFFFF",
                    font=(FONT_FAMILY, 11, "bold"),
                )
            elif name not in {"new", "load"}:
                button.configure(
                    fg_color="transparent",
                    text_color="#C9D9E4",
                    font=(FONT_FAMILY, 11),
                )

    def set_compact(self, compact: bool, ultra: bool = False):
        if ultra:
            self.configure(width=76)
            if self.brand.winfo_manager():
                self.brand.pack_forget()
            if self.footer.winfo_manager():
                self.footer.pack_forget()
            for button in self.buttons.values():
                button.configure(
                    text=button._aegis_icon,
                    anchor="center",
                    width=52,
                )
        else:
            self.configure(width=228 if compact else 268)
            if not self.brand.winfo_manager():
                self.brand.pack(fill="x", padx=18, pady=(14, 8), before=self.nav)
            if not self.footer.winfo_manager():
                self.footer.pack(fill="x", padx=12, pady=(6, 12))
            for button in self.buttons.values():
                button.configure(
                    text=f"{button._aegis_icon}   {button._aegis_label}",
                    anchor="w",
                )
