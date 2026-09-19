"""Centro de carga e importación de Aegis Auditor."""

from __future__ import annotations

import customtkinter as ctk

from ..theme import COLORS, FONT_FAMILY


class LoadCenter(ctk.CTkToplevel):
    ITEMS = (
        ("new_project", "＋", "Nueva aplicación", "Seleccionar carpeta y generar un perfil automáticamente."),
        ("profile", "▣", "Cargar perfil JSON", "Abrir un perfil existente de config/*.json."),
        ("source", "⌂", "Cargar código fuente", "Seleccionar la copia local del proyecto objetivo."),
        ("package", "◇", "Importar auditor-package.json", "Usar metadata, entrypoints y build del proyecto."),
        ("accounts", "👥", "Cargar cuentas y roles", "Importar JSON o CSV para Pilar 1."),
        ("evidence", "▧", "Cargar evidencias", "Seleccionar carpeta o sesión de evidencias existente."),
        ("recipes", "▤", "Importar recetas / medicinas", "Incorporar conocimiento correctivo reutilizable."),
        ("ai", "✦", "Configurar proveedor IA", "Revisar OpenCode / Gemma y abrir el módulo IA."),
    )

    def __init__(self, master, callbacks: dict[str, callable]):
        super().__init__(master)
        self.title("Aegis Auditor — Cargar / Importar")
        self.geometry("920x650")
        self.minsize(760, 560)
        self.configure(fg_color=COLORS["bg"])
        self.transient(master)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text="Centro de carga",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 24, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(22, 2))

        ctk.CTkLabel(
            self,
            text=(
                "Incorpora todos los elementos que Aegis necesita para "
                "construir, ejecutar y verificar una auditoría."
            ),
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 11),
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=24, pady=(0, 16))

        for index, (key, icon, title, desc) in enumerate(self.ITEMS):
            row = 2 + index // 2
            col = index % 2

            card = ctk.CTkFrame(
                self,
                fg_color=COLORS["surface"],
                corner_radius=12,
                border_width=1,
                border_color=COLORS["border_soft"],
            )
            card.grid(
                row=row,
                column=col,
                sticky="nsew",
                padx=(24 if col == 0 else 8, 8 if col == 0 else 24),
                pady=7,
            )
            card.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                card,
                text=icon,
                width=44,
                height=44,
                corner_radius=10,
                fg_color=COLORS["surface_3"],
                text_color=COLORS["accent"],
                font=(FONT_FAMILY, 18, "bold"),
            ).grid(row=0, column=0, rowspan=2, padx=12, pady=12)

            ctk.CTkLabel(
                card,
                text=title,
                text_color=COLORS["text"],
                font=(FONT_FAMILY, 12, "bold"),
                anchor="w",
            ).grid(row=0, column=1, sticky="ew", pady=(12, 2))

            ctk.CTkLabel(
                card,
                text=desc,
                text_color=COLORS["muted"],
                font=(FONT_FAMILY, 9),
                anchor="w",
                justify="left",
                wraplength=260,
            ).grid(row=1, column=1, sticky="ew", pady=(0, 12))

            ctk.CTkButton(
                card,
                text="Abrir",
                width=72,
                command=self._wrap(callbacks.get(key)),
                fg_color=COLORS["surface_3"],
                hover_color="#16405E",
            ).grid(row=0, column=2, rowspan=2, padx=12)

        ctk.CTkButton(
            self,
            text="Cerrar",
            command=self.destroy,
            width=100,
            fg_color=COLORS["surface_3"],
            hover_color="#16405E",
        ).grid(row=7, column=1, sticky="e", padx=24, pady=(12, 20))

    def _wrap(self, callback):
        def invoke():
            if callback:
                self.destroy()
                self.after(50, callback)
        return invoke
