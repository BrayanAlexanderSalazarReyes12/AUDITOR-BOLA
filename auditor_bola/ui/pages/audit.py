"""Página moderna de resultados P1 + P2."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from ..components.cards import ActionButton, MetricCard
from ..theme import COLORS, FONT_FAMILY


class AuditPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=COLORS["bg"])
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(2, 10))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Auditoría de seguridad",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 24, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        ActionButton(
            header,
            "◈ Diagnosticar P1 + P2",
            app._diagnose,
            "primary",
            width=190,
        ).grid(row=0, column=1, sticky="e")

        self.metrics = ctk.CTkFrame(self, fg_color="transparent")
        self.metrics.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        metrics = self.metrics
        for column in range(3):
            metrics.grid_columnconfigure(column, weight=1)

        self.p1_card = MetricCard(metrics, "Pilar 1", "0 hallazgos", "Identidad y Control de Acceso")
        self.p1_card.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.p2_card = MetricCard(metrics, "Pilar 2", "0 hallazgos", "Arquitectura y Configuración")
        self.p2_card.grid(row=0, column=1, sticky="ew", padx=5)

        self.total_card = MetricCard(metrics, "Estado global", "Sin diagnóstico", "P1 + P2")
        self.total_card.grid(row=0, column=2, sticky="ew", padx=(5, 0))

        self.actions = ctk.CTkFrame(
            self,
            fg_color=COLORS["surface"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        self.actions.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        actions = self.actions
        for column in range(4):
            actions.grid_columnconfigure(column, weight=1)

        app.btn_verify = ActionButton(
            actions, "✓ Verificar seleccionado", app._verify_selected, "success"
        )
        app.btn_verify.grid(row=0, column=0, sticky="ew", padx=(12, 5), pady=10)

        app.btn_correct = ActionButton(
            actions, "✦ Corregir seleccionado", app._correct_selected, "primary"
        )
        app.btn_correct.grid(row=0, column=1, sticky="ew", padx=5, pady=10)

        app.btn_correct_all = ActionButton(
            actions, "⚡ Corregir hallazgos", app._correct_all
        )
        app.btn_correct_all.grid(row=0, column=2, sticky="ew", padx=5, pady=10)

        app.btn_ai_open = ActionButton(
            actions, "✦ Generar recetas IA", app._open_ai_for_selected
        )
        app.btn_ai_open.grid(row=0, column=3, sticky="ew", padx=(5, 12), pady=10)

        table_card = ctk.CTkFrame(
            self,
            fg_color=COLORS["surface"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        table_card.grid(row=3, column=0, sticky="nsew")
        table_card.grid_rowconfigure(0, weight=1)
        table_card.grid_columnconfigure(0, weight=1)

        columns = ("pilar","id","control","cuenta","estado","correccion","detalle")
        app.table = ttk.Treeview(
            table_card,
            columns=columns,
            show="headings",
            height=14,
        )
        titles = {
            "pilar": "Pilar",
            "id": "Control",
            "control": "Descripción",
            "cuenta": "Cuenta",
            "estado": "Estado",
            "correccion": "Receta",
            "detalle": "Detalle",
        }
        widths = {
            "pilar": 60,
            "id": 150,
            "control": 260,
            "cuenta": 110,
            "estado": 110,
            "correccion": 75,
            "detalle": 420,
        }
        for col in columns:
            app.table.heading(col, text=titles[col])
            app.table.column(col, width=widths[col], anchor="w")

        app.table.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        sy = ttk.Scrollbar(table_card, orient="vertical", command=app.table.yview)
        sx = ttk.Scrollbar(table_card, orient="horizontal", command=app.table.xview)
        app.table.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.grid(row=0, column=1, sticky="ns", pady=10)
        sx.grid(row=1, column=0, sticky="ew", padx=(10, 0))

        app.table.tag_configure("hallazgo", background="#472331", foreground="#FFDCE2")
        app.table.tag_configure("ok", background="#143A34", foreground="#C9FFF0")
        app.table.tag_configure("error", background="#46371D", foreground="#FFE7A5")
        app.table.bind("<<TreeviewSelect>>", app._on_result_selected)


    def set_compact(self, compact: bool, ultra: bool = False):
        cards = [self.p1_card, self.p2_card, self.total_card]

        if ultra:
            for index, card in enumerate(cards):
                card.grid(
                    row=index,
                    column=0,
                    columnspan=3,
                    sticky="ew",
                    padx=0,
                    pady=(0, 6 if index < 2 else 0),
                )
            for column in range(3):
                self.metrics.grid_columnconfigure(column, weight=1)

            buttons = [
                self.app.btn_verify,
                self.app.btn_correct,
                self.app.btn_correct_all,
                self.app.btn_ai_open,
            ]
            for index, button in enumerate(buttons):
                button.grid(
                    row=index // 2,
                    column=index % 2,
                    sticky="ew",
                    padx=(
                        12 if index % 2 == 0 else 5,
                        5 if index % 2 == 0 else 12,
                    ),
                    pady=5,
                )
            self.actions.grid_columnconfigure(0, weight=1)
            self.actions.grid_columnconfigure(1, weight=1)
            self.actions.grid_columnconfigure(2, weight=0)
            self.actions.grid_columnconfigure(3, weight=0)
        else:
            for index, card in enumerate(cards):
                card.grid(
                    row=0,
                    column=index,
                    columnspan=1,
                    sticky="ew",
                    padx=(
                        0 if index == 0 else 5,
                        0 if index == 2 else 5,
                    ),
                    pady=0,
                )
                self.metrics.grid_columnconfigure(index, weight=1)

            buttons = [
                self.app.btn_verify,
                self.app.btn_correct,
                self.app.btn_correct_all,
                self.app.btn_ai_open,
            ]
            for index, button in enumerate(buttons):
                button.grid(
                    row=0,
                    column=index,
                    sticky="ew",
                    padx=(
                        12 if index == 0 else 5,
                        12 if index == 3 else 5,
                    ),
                    pady=10,
                )
                self.actions.grid_columnconfigure(index, weight=1)
