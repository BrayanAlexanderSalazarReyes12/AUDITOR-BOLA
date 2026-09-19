"""Interfaz moderna de Aegis Auditor.

Mantiene el motor probado de AuditorGUI y sustituye la composición visual
por una experiencia CustomTkinter orientada a producto.
"""

from __future__ import annotations

import csv
import json
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from ..app_paths import default_evidence_dir
from ..config import cargar_config
from ..gui import AuditorGUI
from ..recipe_library import biblioteca_por_defecto
from ..remediation_knowledge import knowledge_root
from ..runner import filas_gui
from .adapters import TextProxy
from .components.load_center import LoadCenter
from .components.sidebar import Sidebar
from .components.topbar import Topbar
from .pages.audit import AuditPage
from .pages.home import HomePage
from .pages.knowledge import KnowledgePage
from .pages.project import ProjectPage
from .pages.reports import ReportsPage
from .pages.settings import SettingsPage
from .project_wizard import ModernProfileWizard
from .router import PageRouter
from .theme import COLORS, FONT_FAMILY


class ModernAuditorGUI(AuditorGUI):
    """Nueva capa visual manteniendo los contratos del motor existente."""

    def _configure_theme(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.colors = dict(COLORS)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            ".",
            font=(FONT_FAMILY, 9),
            background=COLORS["surface"],
            foreground=COLORS["text"],
        )
        style.configure("TFrame", background=COLORS["surface"])
        style.configure(
            "TLabel",
            background=COLORS["surface"],
            foreground=COLORS["text"],
        )
        style.configure(
            "TLabelframe",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border_soft"],
            relief="solid",
            borderwidth=1,
        )
        style.configure(
            "TLabelframe.Label",
            background=COLORS["surface"],
            foreground="#C7DCEB",
            font=(FONT_FAMILY, 9, "bold"),
        )
        style.configure(
            "TButton",
            background=COLORS["surface_3"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
            padding=(10, 6),
        )
        style.map(
            "TButton",
            background=[("active", "#16405E"), ("disabled", "#132331")],
            foreground=[("disabled", "#577083")],
        )
        style.configure(
            "Treeview",
            background="#071724",
            fieldbackground="#071724",
            foreground=COLORS["text"],
            bordercolor=COLORS["border_soft"],
            rowheight=30,
        )
        style.map(
            "Treeview",
            background=[("selected", "#124E75")],
            foreground=[("selected", "#FFFFFF")],
        )
        style.configure(
            "Treeview.Heading",
            background="#0E2A40",
            foreground="#C8DDEB",
            bordercolor=COLORS["border"],
            font=(FONT_FAMILY, 9, "bold"),
        )
        style.map(
            "Treeview.Heading",
            background=[("active", "#123A57")],
        )
        style.configure(
            "TScrollbar",
            background="#12384F",
            troughcolor="#071724",
            bordercolor="#071724",
            arrowcolor="#9BB6C8",
        )
        style.configure(
            "TEntry",
            fieldbackground="#071724",
            foreground=COLORS["text"],
            insertcolor="#FFFFFF",
            bordercolor=COLORS["border"],
        )
        style.configure(
            "TCombobox",
            fieldbackground="#071724",
            foreground=COLORS["text"],
            background=COLORS["surface_3"],
            arrowcolor=COLORS["text"],
            bordercolor=COLORS["border"],
        )
        style.configure(
            "TCheckbutton",
            background=COLORS["surface"],
            foreground=COLORS["text"],
        )

    def _build_menu(self):
        """La navegación vive dentro de la aplicación; no usa el menú nativo."""
        try:
            self.config(menu="")
        except tk.TclError:
            pass

        self.bind_all(
            "<Control-l>",
            lambda _event: self._open_load_center(),
        )
        self.bind_all(
            "<Control-n>",
            lambda _event: self._new_project_wizard(),
        )
        self.bind_all(
            "<Control-o>",
            lambda _event: self._choose_config(),
        )
        self.bind_all(
            "<F5>",
            lambda _event: self._diagnose(),
        )

    def _build_shell(self):
        self.shell = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg"],
            corner_radius=0,
        )
        self.shell.pack(fill="both", expand=True)

        self.sidebar = Sidebar(
            self.shell,
            on_navigate=self._route,
            on_new_project=self._new_project_wizard,
            on_load_center=self._open_load_center,
        )
        self.sidebar.pack(side="left", fill="y")

        self.content = ctk.CTkFrame(
            self.shell,
            fg_color=COLORS["bg"],
            corner_radius=0,
        )
        self.content.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(8, 10),
            pady=8,
        )

    def _build_brand_header(self):
        self.topbar = Topbar(
            self.content,
            on_load=self._open_load_center,
            on_new_project=self._new_project_wizard,
        )
        self.topbar.pack(fill="x", pady=(0, 8))

        self.brand_header_frame = self.topbar
        self.brand_header_subtitle = self.topbar.subtitle_label
        self.brand_new_project_button = self.topbar.load_button

    def _build_header(self):
        self.lbl_config = TextProxy("Sin perfil seleccionado")
        self.lbl_target = TextProxy("Sin carpeta")
        self.lbl_evidence = TextProxy(str(self.evidence_base))

    def _build_runtime_bar(self):
        return None

    def _build_actions(self):
        return None

    def _page(self):
        return ctk.CTkFrame(
            self.page_container,
            fg_color=COLORS["bg"],
            corner_radius=0,
        )

    def _build_detail_tab(self):
        card = ctk.CTkFrame(
            self.tab_detail,
            fg_color=COLORS["surface"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        card.pack(fill="both", expand=True, pady=(0, 2))
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)

        self.detail_text = tk.Text(
            card,
            wrap="none",
            font=("Consolas", 10),
            undo=False,
            background="#04101A",
            foreground="#CBE0EC",
            insertbackground="#FFFFFF",
            selectbackground="#124E75",
            selectforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
        )
        scroll_y = ttk.Scrollbar(
            card,
            orient="vertical",
            command=self.detail_text.yview,
        )
        scroll_x = ttk.Scrollbar(
            card,
            orient="horizontal",
            command=self.detail_text.xview,
        )
        self.detail_text.configure(
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
        )
        self.detail_text.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(12, 0),
            pady=(12, 0),
        )
        scroll_y.grid(
            row=0,
            column=1,
            sticky="ns",
            pady=(12, 0),
        )
        scroll_x.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(12, 0),
            pady=(0, 12),
        )

    def _build_ai_tab(self):
        self.ai_source_relative = None
        self.ai_proposals = []
        self.ai_session_dir = None
        self.ai_current_recipe = None
        self.ai_provider = None
        self.ai_proposals_window = None
        self.ai_proposals_notebook = None
        self.ai_library_candidates = []
        self.ai_library_window = None
        self.ai_selected_library_candidate = None
        self.ai_knowledge_candidates = []
        self.ai_active_knowledge_candidate = None
        self.ai_knowledge_window = None

        header = ctk.CTkFrame(
            self.tab_ai,
            fg_color=COLORS["surface"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        header.pack(fill="x", pady=(0, 8))
        header.grid_columnconfigure(1, weight=1)

        rows = (
            ("Control seleccionado", "lbl_ai_control", "Ninguno"),
            ("Archivo a analizar", "lbl_ai_source", "No seleccionado"),
            ("Proveedor", "lbl_ai_provider", "Buscando configuración…"),
            ("Modelo", "lbl_ai_model", "lab-coder"),
            ("OpenCode", "lbl_ai_config", "No cargado"),
            ("Medicinas conocidas", "lbl_ai_knowledge", f"0 conocidas — {knowledge_root()}"),
            ("Parches concretos", "lbl_ai_library", f"0 compatibles — {biblioteca_por_defecto()}"),
        )

        for row, (label, attr, value) in enumerate(rows):
            ctk.CTkLabel(
                header,
                text=label,
                text_color=COLORS["muted"],
                font=(FONT_FAMILY, 9),
                anchor="w",
            ).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(16, 10),
                pady=5,
            )
            widget = ctk.CTkLabel(
                header,
                text=value,
                text_color=COLORS["text"],
                font=(FONT_FAMILY, 9),
                anchor="w",
                justify="left",
                wraplength=650,
            )
            widget.grid(
                row=row,
                column=1,
                sticky="ew",
                padx=(0, 8),
                pady=5,
            )
            setattr(self, attr, widget)

        source_actions = ctk.CTkFrame(header, fg_color="transparent")
        source_actions.grid(
            row=0,
            column=2,
            rowspan=7,
            sticky="ns",
            padx=(6, 14),
            pady=10,
        )

        ctk.CTkButton(
            source_actions,
            text="Elegir archivo",
            command=self._choose_ai_source,
            width=145,
            fg_color=COLORS["surface_3"],
            hover_color="#16405E",
        ).pack(fill="x", pady=3)

        self.btn_ai_reload = ctk.CTkButton(
            source_actions,
            text="Recargar IA",
            command=self._reload_ai_provider,
            width=145,
            fg_color=COLORS["surface_3"],
            hover_color="#16405E",
        )
        self.btn_ai_reload.pack(fill="x", pady=3)

        self.btn_ai_knowledge = ctk.CTkButton(
            source_actions,
            text="Ver medicinas",
            command=self._open_knowledge_window,
            width=145,
            fg_color=COLORS["surface_3"],
            hover_color="#16405E",
        )
        self.btn_ai_knowledge.pack(fill="x", pady=3)

        self.btn_ai_library = ctk.CTkButton(
            source_actions,
            text="Ver parches exactos",
            command=self._open_recipe_library_window,
            width=145,
            fg_color=COLORS["surface_3"],
            hover_color="#16405E",
        )
        self.btn_ai_library.pack(fill="x", pady=3)

        actions = ctk.CTkFrame(
            self.tab_ai,
            fg_color="transparent",
        )
        actions.pack(fill="x", pady=(0, 8))
        for col in range(4):
            actions.grid_columnconfigure(col, weight=1)

        self.btn_ai_generate = ctk.CTkButton(
            actions,
            text="Generar 3 recetas con Gemma",
            command=self._generate_ai_recipes,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=(FONT_FAMILY, 10, "bold"),
        )
        self.btn_ai_generate.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 4),
        )

        self.btn_ai_apply = ctk.CTkButton(
            actions,
            text="Aplicar y verificar",
            command=self._apply_ai_recipe,
            fg_color=COLORS["success"],
            hover_color="#27B989",
            text_color="#06111D",
            font=(FONT_FAMILY, 10, "bold"),
        )
        self.btn_ai_apply.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=4,
        )

        self.btn_ai_save = ctk.CTkButton(
            actions,
            text="Guardar en perfil",
            command=self._save_ai_recipe_to_profile,
            fg_color=COLORS["surface_3"],
            hover_color="#16405E",
        )
        self.btn_ai_save.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=4,
        )

        self.btn_ai_window = ctk.CTkButton(
            actions,
            text="Abrir propuestas",
            command=self._open_ai_proposals_window,
            fg_color=COLORS["surface_3"],
            hover_color="#16405E",
        )
        self.btn_ai_window.grid(
            row=0,
            column=3,
            sticky="ew",
            padx=(4, 0),
        )

        body = ctk.CTkFrame(
            self.tab_ai,
            fg_color="transparent",
        )
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(
            body,
            fg_color=COLORS["surface"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        left.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 5),
        )
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            left,
            text="Alternativas",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 13, "bold"),
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=12,
            pady=(12, 6),
        )

        columns = ("id", "enfoque", "riesgo", "titulo")
        self.ai_table = ttk.Treeview(
            left,
            columns=columns,
            show="headings",
            height=10,
        )
        for col, title, width in (
            ("id", "ID", 55),
            ("enfoque", "Enfoque", 95),
            ("riesgo", "Riesgo", 70),
            ("titulo", "Título", 260),
        ):
            self.ai_table.heading(col, text=title)
            self.ai_table.column(
                col,
                width=width,
                anchor="w",
            )
        self.ai_table.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(12, 0),
            pady=(0, 12),
        )
        ai_scroll = ttk.Scrollbar(
            left,
            orient="vertical",
            command=self.ai_table.yview,
        )
        self.ai_table.configure(
            yscrollcommand=ai_scroll.set
        )
        ai_scroll.grid(
            row=1,
            column=1,
            sticky="ns",
            pady=(0, 12),
        )
        self.ai_table.bind(
            "<<TreeviewSelect>>",
            self._on_ai_proposal_selected,
        )

        right = ctk.CTkFrame(
            body,
            fg_color=COLORS["surface"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        right.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(5, 0),
        )
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right,
            text="Detalle y vista previa del diff",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 13, "bold"),
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=12,
            pady=(12, 6),
        )

        self.ai_detail_text = tk.Text(
            right,
            wrap="none",
            font=("Consolas", 10),
            background="#04101A",
            foreground="#CBE0EC",
            insertbackground="#FFFFFF",
            selectbackground="#124E75",
            selectforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
        )
        yscroll = ttk.Scrollbar(
            right,
            orient="vertical",
            command=self.ai_detail_text.yview,
        )
        xscroll = ttk.Scrollbar(
            right,
            orient="horizontal",
            command=self.ai_detail_text.xview,
        )
        self.ai_detail_text.configure(
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
        )
        self.ai_detail_text.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(12, 0),
            pady=(0, 4),
        )
        yscroll.grid(
            row=1,
            column=1,
            sticky="ns",
            pady=(0, 4),
        )
        xscroll.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=(12, 0),
            pady=(0, 12),
        )

        self._reload_ai_provider(silent=True)
        self._refresh_ai_state()

    def _build_evidence_tab(self):
        body = ctk.CTkFrame(
            self.tab_evidence,
            fg_color="transparent",
        )
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(
            body,
            fg_color=COLORS["surface"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        left.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 5),
        )
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            left,
            text="Sesiones",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 13, "bold"),
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=12,
            pady=(12, 6),
        )

        self.evidence_list = tk.Listbox(
            left,
            exportselection=False,
            background="#071724",
            foreground="#CBE0EC",
            selectbackground="#124E75",
            selectforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
            font=(FONT_FAMILY, 9),
        )
        list_scroll = ttk.Scrollbar(
            left,
            orient="vertical",
            command=self.evidence_list.yview,
        )
        self.evidence_list.configure(
            yscrollcommand=list_scroll.set
        )
        self.evidence_list.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(12, 0),
        )
        list_scroll.grid(
            row=1,
            column=1,
            sticky="ns",
        )
        self.evidence_list.bind(
            "<<ListboxSelect>>",
            lambda _event:
            self._preview_selected_evidence(),
        )

        buttons = ctk.CTkFrame(
            left,
            fg_color="transparent",
        )
        buttons.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=12,
            pady=12,
        )
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            buttons,
            text="Actualizar",
            command=self._refresh_evidence_list,
            fg_color=COLORS["surface_3"],
            hover_color="#16405E",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 4),
        )
        ctk.CTkButton(
            buttons,
            text="Abrir carpeta",
            command=self._open_selected_evidence,
            fg_color=COLORS["surface_3"],
            hover_color="#16405E",
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(4, 0),
        )

        self.btn_rollback = ctk.CTkButton(
            buttons,
            text="Revertir esta corrección",
            command=self._rollback_selected_evidence,
            fg_color=COLORS["warning"],
            hover_color="#D39B42",
            text_color="#201704",
        )
        self.btn_rollback.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(7, 0),
        )

        self.btn_rollback_all = ctk.CTkButton(
            buttons,
            text="Revertir todas las correcciones",
            command=self._rollback_all_evidence,
            fg_color=COLORS["danger"],
            hover_color="#D94F61",
        )
        self.btn_rollback_all.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(7, 0),
        )

        right = ctk.CTkFrame(
            body,
            fg_color=COLORS["surface"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        right.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(5, 0),
        )
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right,
            text="Vista previa verificable",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 13, "bold"),
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=12,
            pady=(12, 6),
        )

        self.evidence_text = tk.Text(
            right,
            wrap="none",
            font=("Consolas", 10),
            background="#04101A",
            foreground="#CBE0EC",
            insertbackground="#FFFFFF",
            selectbackground="#124E75",
            selectforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
        )
        scroll_y = ttk.Scrollbar(
            right,
            orient="vertical",
            command=self.evidence_text.yview,
        )
        scroll_x = ttk.Scrollbar(
            right,
            orient="horizontal",
            command=self.evidence_text.xview,
        )
        self.evidence_text.configure(
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
        )
        self.evidence_text.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(12, 0),
            pady=(0, 4),
        )
        scroll_y.grid(
            row=1,
            column=1,
            sticky="ns",
            pady=(0, 4),
        )
        scroll_x.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=(12, 0),
            pady=(0, 12),
        )

    def _build_log_tab(self):
        self.log_text = tk.Text(
            self.tab_log,
            wrap="none",
            font=("Consolas", 10),
            state="disabled",
            background="#04101A",
            foreground="#CBE0EC",
            insertbackground="#FFFFFF",
            selectbackground="#124E75",
            selectforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
        )
        self.log_text.pack(
            fill="both",
            expand=True,
            pady=(0, 2),
        )

    def _build_notebook(self):
        self.page_container = ctk.CTkFrame(
            self.content,
            fg_color=COLORS["bg"],
            corner_radius=0,
        )
        self.page_container.pack(fill="both", expand=True)

        self.notebook = PageRouter()
        self.notebook.on_change = self._on_page_change

        self.tab_dashboard = HomePage(
            self.page_container,
            self,
        )
        self.home_page = self.tab_dashboard
        self.notebook.register("home", self.tab_dashboard)

        self.tab_project = ProjectPage(
            self.page_container,
            self,
        )
        self.project_page = self.tab_project
        self.notebook.register("project", self.tab_project)

        self.tab_results = AuditPage(
            self.page_container,
            self,
        )
        self.audit_page = self.tab_results
        self.notebook.register("audit", self.tab_results)

        self.tab_detail = self._page()
        ctk.CTkLabel(
            self.tab_detail,
            text="Detalle / Corrección",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 22, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(2, 8))
        self._build_detail_tab()
        self.notebook.register("detail", self.tab_detail)

        self.tab_ai = self._page()
        ctk.CTkLabel(
            self.tab_ai,
            text="Correcciones con IA",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 22, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(2, 6))
        self._build_ai_tab()
        self.notebook.register("remediation", self.tab_ai)

        self.tab_knowledge = KnowledgePage(
            self.page_container,
            self,
        )
        self.knowledge_page = self.tab_knowledge
        self.notebook.register("knowledge", self.tab_knowledge)

        self.tab_evidence = self._page()
        ctk.CTkLabel(
            self.tab_evidence,
            text="Evidencias",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 22, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(2, 6))
        self._build_evidence_tab()
        self.notebook.register("evidence", self.tab_evidence)

        self.tab_reports = ReportsPage(
            self.page_container,
            self,
        )
        self.reports_page = self.tab_reports
        self.notebook.register("reports", self.tab_reports)

        self.tab_log = self._page()
        ctk.CTkLabel(
            self.tab_log,
            text="Registro de actividad",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 22, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(2, 6))
        self._build_log_tab()
        self.notebook.register("log", self.tab_log)

        self.tab_settings = SettingsPage(
            self.page_container,
            self,
        )
        self.settings_page = self.tab_settings
        self.notebook.register("settings", self.tab_settings)

        self.btn_show_profile = ctk.CTkButton(
            self.tab_project,
            text="Ver perfil JSON",
            command=self._show_profile,
        )

        self.notebook.select("home")

    def _build_status(self):
        self.status_bar = ctk.CTkFrame(
            self.content,
            height=42,
            fg_color="#071724",
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        self.status_bar.pack(fill="x", pady=(8, 0))
        self.status_bar.pack_propagate(False)
        self.status_bar.grid_columnconfigure(0, weight=1)

        self.lbl_summary = ctk.CTkLabel(
            self.status_bar,
            text="Sin diagnóstico.",
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 9),
            anchor="w",
        )
        self.lbl_summary.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=12,
        )

        self.lbl_status = ctk.CTkLabel(
            self.status_bar,
            text="Listo.",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 9, "bold"),
            anchor="e",
        )
        self.lbl_status.grid(
            row=0,
            column=1,
            sticky="e",
            padx=8,
        )

        self.progress = ctk.CTkProgressBar(
            self.status_bar,
            width=160,
            height=7,
            mode="indeterminate",
            fg_color="#183246",
            progress_color=COLORS["accent"],
        )
        self.progress.grid(
            row=0,
            column=2,
            sticky="e",
            padx=(4, 12),
        )
        self.progress.stop()
        self.progress.set(0)

    def _route(self, name: str):
        aliases = {
            "dashboard": "home",
            "results": "audit",
            "ai": "remediation",
        }
        name = aliases.get(name, name)
        if hasattr(self, "notebook"):
            self.notebook.select(name)

    def _on_page_change(self, name: str):
        if hasattr(self, "sidebar"):
            self.sidebar.set_active(name)

        if name == "reports" and hasattr(self, "reports_page"):
            self.reports_page.refresh()
        if name == "knowledge" and hasattr(self, "knowledge_page"):
            self.knowledge_page.refresh()
        if name == "project":
            self._refresh_project_page()

    def _new_project_wizard(self):
        initial = self.target_root if self.target_root else None
        ModernProfileWizard(
            self,
            initial_project=initial,
            on_saved=self._profile_wizard_saved,
        )

    def _open_load_center(self):
        old = getattr(self, "_load_center_window", None)
        if old is not None:
            try:
                if old.winfo_exists():
                    old.lift()
                    return
            except tk.TclError:
                pass

        callbacks = {
            "new_project": self._new_project_wizard,
            "profile": self._choose_config,
            "source": self._choose_target,
            "package": self._import_auditor_package,
            "accounts": self._import_accounts_roles,
            "evidence": self._load_evidence_from_center,
            "recipes": self._import_recipes,
            "ai": self._configure_ai_from_load_center,
        }
        self._load_center_window = LoadCenter(
            self,
            callbacks,
        )

    def _import_auditor_package(self):
        path = filedialog.askopenfilename(
            title="Selecciona auditor-package.json",
            filetypes=[
                ("auditor-package.json", "auditor-package.json"),
                ("JSON", "*.json"),
            ],
        )
        if not path:
            return

        package = Path(path).resolve()
        try:
            data = json.loads(
                package.read_text(encoding="utf-8")
            )
        except Exception as exc:
            messagebox.showerror(
                "auditor-package.json inválido",
                str(exc),
            )
            return

        if not isinstance(data, dict):
            messagebox.showerror(
                "auditor-package.json inválido",
                "El documento debe ser un objeto JSON.",
            )
            return

        if self.proceso and self.proceso.is_running():
            self.proceso.stop()

        self.proceso = None
        self.target_root = package.parent

        if hasattr(self.lbl_target, "configure"):
            self.lbl_target.configure(
                text=str(self.target_root)
            )

        self._log(
            f"auditor-package.json importado: {package}"
        )
        self._refresh_state()

        ModernProfileWizard(
            self,
            initial_project=self.target_root,
            on_saved=self._profile_wizard_saved,
        )

    def _import_accounts_roles(self):
        if not self.config_path:
            messagebox.showinfo(
                "Cuentas y roles",
                (
                    "Carga o genera primero un perfil JSON "
                    "para poder incorporar las cuentas."
                ),
            )
            return

        path = filedialog.askopenfilename(
            title="Importar cuentas y roles",
            filetypes=[
                ("JSON o CSV", "*.json *.csv"),
                ("JSON", "*.json"),
                ("CSV", "*.csv"),
            ],
        )
        if not path:
            return

        source = Path(path)
        accounts = []
        roles = []

        try:
            if source.suffix.lower() == ".csv":
                with source.open(
                    "r",
                    encoding="utf-8-sig",
                    newline="",
                ) as handle:
                    for row in csv.DictReader(handle):
                        username = (
                            row.get("username")
                            or row.get("usuario")
                            or ""
                        ).strip()
                        role = (
                            row.get("role")
                            or row.get("rol")
                            or "USER"
                        ).strip()
                        if not username:
                            continue
                        accounts.append(
                            {
                                "username": username,
                                "password": (
                                    row.get("password")
                                    or row.get("contraseña")
                                    or None
                                ),
                                "role": role,
                                "auth_type": (
                                    row.get("auth_type")
                                    or "none"
                                ).strip(),
                                "token": row.get("token") or None,
                                "headers": {},
                            }
                        )
                        privileged = str(
                            row.get("privileged")
                            or row.get("privilegiado")
                            or ""
                        ).lower()
                        if privileged in {
                            "1",
                            "true",
                            "si",
                            "sí",
                            "yes",
                        }:
                            roles.append(role)
            else:
                raw = json.loads(
                    source.read_text(encoding="utf-8")
                )
                if isinstance(raw, list):
                    accounts = raw
                elif isinstance(raw, dict):
                    accounts = list(
                        raw.get("cuentas")
                        or raw.get("accounts")
                        or []
                    )
                    roles = list(
                        raw.get("roles_privilegiados")
                        or raw.get("privileged_roles")
                        or []
                    )
                else:
                    raise ValueError(
                        "El JSON debe ser una lista o un objeto."
                    )
        except Exception as exc:
            messagebox.showerror(
                "No se pudieron importar las cuentas",
                str(exc),
            )
            return

        try:
            profile = json.loads(
                self.config_path.read_text(encoding="utf-8")
            )
            existing = {
                str(item.get("username")): item
                for item in profile.get("cuentas", [])
                if item.get("username")
            }

            for account in accounts:
                username = str(
                    account.get("username")
                    or ""
                ).strip()
                if username:
                    existing[username] = account

            profile["cuentas"] = list(existing.values())

            merged_roles = list(
                profile.get("roles_privilegiados")
                or []
            )
            for role in roles:
                if role and role not in merged_roles:
                    merged_roles.append(role)

            profile["roles_privilegiados"] = merged_roles

            self.config_path.write_text(
                json.dumps(
                    profile,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            self.cfg = cargar_config(
                self.config_path
            )
        except Exception as exc:
            messagebox.showerror(
                "No se pudo actualizar el perfil",
                str(exc),
            )
            return

        self._log(
            f"Cuentas/roles importados: {len(accounts)} cuenta(s)."
        )
        self._refresh_state()
        self._refresh_project_page()

        messagebox.showinfo(
            "Importación completada",
            (
                f"Se incorporaron {len(accounts)} cuenta(s) "
                f"y {len(set(roles))} rol(es) privilegiados."
            ),
        )

    def _load_evidence_from_center(self):
        path = filedialog.askdirectory(
            title="Selecciona una carpeta o sesión de evidencias",
            initialdir=str(default_evidence_dir()),
        )
        if not path:
            return

        selected = Path(path).resolve()

        if (selected / "manifest.json").exists():
            self.evidence_base = selected.parent
            self.lbl_evidence.configure(
                text=str(self.evidence_base)
            )
            self._refresh_evidence_list(
                select_path=selected
            )
        else:
            self.evidence_base = selected
            self.lbl_evidence.configure(
                text=str(self.evidence_base)
            )
            self._refresh_evidence_list()

        self._route("evidence")
        self._log(
            f"Evidencias cargadas desde: {selected}"
        )

    def _import_recipes(self):
        source_dir = filedialog.askdirectory(
            title="Selecciona carpeta de recetas o medicinas",
        )
        if not source_dir:
            return

        source = Path(source_dir).resolve()
        recipe_root = biblioteca_por_defecto()
        knowledge_base = knowledge_root()
        imported_recipes = 0
        imported_knowledge = 0
        skipped = 0

        for path in source.rglob("*.json"):
            try:
                data = json.loads(
                    path.read_text(encoding="utf-8")
                )
            except Exception:
                skipped += 1
                continue

            if (
                data.get("tipo")
                == "conocimiento_correctivo_semantico"
            ):
                family = str(
                    data.get("familia_control")
                    or data.get("control_id")
                    or "conocimiento"
                )
                safe_family = (
                    family.replace("/", "-")
                    .replace("\\", "-")
                )
                folder = knowledge_base / safe_family
                folder.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                shutil.copy2(
                    path,
                    folder / path.name,
                )
                imported_knowledge += 1
            elif data.get("control_id") and (
                data.get("operaciones") is not None
                or data.get("recipe_id")
            ):
                safe_control = (
                    str(data["control_id"])
                    .replace("/", "-")
                    .replace("\\", "-")
                )
                folder = recipe_root / safe_control
                folder.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                shutil.copy2(
                    path,
                    folder / path.name,
                )
                imported_recipes += 1
            else:
                skipped += 1

        self._log(
            "Importación de conocimiento: "
            f"recetas={imported_recipes}, "
            f"medicinas={imported_knowledge}, "
            f"omitidos={skipped}"
        )
        self._refresh_ai_state()

        if hasattr(self, "knowledge_page"):
            self.knowledge_page.refresh()

        messagebox.showinfo(
            "Importación completada",
            (
                f"Parches concretos: {imported_recipes}\n"
                f"Medicinas semánticas: {imported_knowledge}\n"
                f"Omitidos: {skipped}"
            ),
        )

    def _configure_ai_from_load_center(self):
        self._route("remediation")
        self.after(
            120,
            lambda: self._reload_ai_provider(
                silent=False
            ),
        )

    def _refresh_ai_state(self):
        super()._refresh_ai_state()

        if not hasattr(self, "sidebar"):
            return

        provider = getattr(self, "ai_provider", None)
        if provider is None:
            self.sidebar.ai_label.configure(
                text="IA: no configurada",
                text_color=COLORS["muted"],
            )
        else:
            model = getattr(provider, "model_name", None) or getattr(
                provider,
                "model_id",
                "Gemma",
            )
            self.sidebar.ai_label.configure(
                text=f"IA: conectada · {model}",
                text_color=COLORS["success"],
            )

    def _refresh_project_page(self):
        if not hasattr(self, "project_page"):
            return

        lines = []

        if self.cfg:
            lines.extend(
                [
                    f"Sistema: {self.cfg.sistema}",
                    (
                        "Versión: "
                        f"{self.cfg.version_objetivo or '-'}"
                    ),
                    f"Base URL: {self.cfg.base_url or '-'}",
                    f"Cuentas: {len(self.cfg.cuentas)}",
                    (
                        "Roles privilegiados: "
                        f"{', '.join(self.cfg.roles_privilegiados) or '-'}"
                    ),
                    (
                        "Controles P1: "
                        f"{len(self.cfg.endpoints) + len(self.cfg.chequeos_acceso) + len(self.cfg.chequeos_agente)}"
                    ),
                    (
                        "Controles P2: "
                        f"{len(self.cfg.chequeos_pilar2)}"
                    ),
                    f"Runtime: {self.cfg.runtime.modo}",
                ]
            )
        else:
            lines.append("Sin perfil cargado.")

        if self.target_root:
            lines.append(
                f"Código: {self.target_root}"
            )

        self.project_page.set_info(
            "\n".join(lines)
        )

    def _refresh_dashboard(self):
        if not hasattr(self, "home_page"):
            return

        project = (
            self.target_root.name
            if self.target_root
            else "Sin cargar"
        )
        profile = (
            self.cfg.sistema
            if self.cfg
            else "Sin perfil"
        )
        running = self._process_running()

        p1 = 0
        p2 = 0
        rows = []

        if self.resultado:
            rows = filas_gui(self.resultado)
            p1 = sum(
                1
                for row in rows
                if row["pilar"] == "P1"
                and row["estado"] == "HALLAZGO"
            )
            p2 = sum(
                1
                for row in rows
                if row["pilar"] == "P2"
                and row["estado"] == "HALLAZGO"
            )

        self.home_page.project_card.set(
            project,
            "Código objetivo",
        )
        self.home_page.profile_card.set(
            profile,
            (
                self.config_path.name
                if self.config_path
                else "Configuración"
            ),
        )
        self.home_page.process_card.set(
            (
                "En ejecución"
                if running
                else (
                    "Detenido"
                    if self.proceso
                    else "No administrado"
                )
            ),
            (
                self.cfg.runtime.modo
                if self.cfg
                else "Runtime"
            ),
        )
        self.home_page.findings_card.set(
            str(p1 + p2),
            f"P1 {p1} · P2 {p2}",
        )

        project_lines = [
            f"Nombre      {profile}",
            f"Ruta        {self.target_root or '-'}",
            (
                "Base URL    "
                f"{self.cfg.base_url if self.cfg else '-'}"
            ),
            (
                "Runtime     "
                f"{self.cfg.runtime.modo if self.cfg else '-'}"
            ),
            f"Pilar 1     {p1} hallazgo(s)",
            f"Pilar 2     {p2} hallazgo(s)",
        ]
        self.home_page.project_info.configure(
            text="\n".join(project_lines)
        )

        corrected = False
        has_evidence = False
        if self.evidence_base.exists():
            try:
                sessions = list(self.evidence_base.iterdir())
            except OSError:
                sessions = []

            has_evidence = bool(sessions)

            for session in sessions:
                manifest = session / "manifest.json"
                if not manifest.exists():
                    continue
                try:
                    payload = json.loads(
                        manifest.read_text(
                            encoding="utf-8"
                        )
                    )
                    if (
                        payload.get("estado_final")
                        == "CORREGIDO"
                    ):
                        corrected = True
                        break
                except Exception:
                    pass

        step = 0
        if self.target_root:
            step = 1
        if self.cfg:
            step = 2
        if self.resultado:
            step = 3
        if has_evidence:
            step = 4
        if corrected:
            step = 5

        self.home_page.progress_steps.set_step(step)
        self.home_page.task_progress.set(
            min(1.0, step / 5.0)
        )
        self.home_page.current_task_progress.set(
            min(1.0, step / 5.0)
        )

        # Estado de cada fase del ciclo.
        self.home_page.set_stage(
            "project",
            "done" if self.target_root else "active",
            (
                str(self.target_root)
                if self.target_root
                else "Selecciona o importa una aplicación."
            ),
        )
        self.home_page.set_stage(
            "profile",
            (
                "done"
                if self.cfg
                else (
                    "active"
                    if self.target_root
                    else "pending"
                )
            ),
            (
                str(self.config_path)
                if self.config_path
                else "Aegis generará config/*.json."
            ),
        )
        self.home_page.set_stage(
            "audit",
            (
                "done"
                if self.resultado
                else (
                    "active"
                    if self.cfg
                    else "pending"
                )
            ),
            (
                f"{len(rows)} control(es) evaluados · P1 {p1} / P2 {p2}"
                if self.resultado
                else "Esperando diagnóstico P1 + P2."
            ),
        )
        self.home_page.set_stage(
            "remediation",
            (
                "done"
                if corrected
                else (
                    "active"
                    if self.resultado and (p1 + p2) > 0
                    else "pending"
                )
            ),
            (
                "Existe evidencia CORREGIDO."
                if corrected
                else (
                    f"{p1 + p2} hallazgo(s) disponible(s) para corregir."
                    if self.resultado and (p1 + p2) > 0
                    else "Esperando un hallazgo verificable."
                )
            ),
        )

        if not self.target_root:
            task_title = "Selecciona una aplicación"
            task_detail = (
                "Usa Nuevo proyecto o Cargar / Importar "
                "para iniciar el flujo."
            )
        elif not self.cfg:
            task_title = "Generar perfil de configuración"
            task_detail = (
                "Aegis puede detectar stack, runtime, "
                "endpoints y puntos de entrada."
            )
        elif not self.resultado:
            task_title = "Diagnosticar Pilar 1 + Pilar 2"
            task_detail = (
                "El perfil está listo. Ejecuta la auditoría "
                "para establecer la línea base."
            )
        elif (p1 + p2) > 0 and not corrected:
            task_title = "Corregir y verificar hallazgos"
            task_detail = (
                f"Hay {p1 + p2} hallazgo(s): "
                f"P1 {p1} · P2 {p2}."
            )
        else:
            task_title = "Validación y evidencia"
            task_detail = (
                "El ciclo está listo para consolidar "
                "evidencia y conocimiento reusable."
            )

        self.home_page.current_task_label.configure(
            text=task_title
        )
        self.home_page.current_task_detail.configure(
            text=task_detail
        )

        # Vista previa real del perfil cargado.
        preview = {"perfil": "sin cargar"}
        if self.config_path and self.config_path.exists():
            try:
                preview = json.loads(
                    self.config_path.read_text(
                        encoding="utf-8"
                    )
                )
            except Exception:
                preview = {
                    "sistema": profile,
                    "base_url": (
                        self.cfg.base_url
                        if self.cfg
                        else ""
                    ),
                }

        self.home_page.set_profile_preview(
            json.dumps(
                preview,
                ensure_ascii=False,
                indent=2,
            )
        )

        if hasattr(self, "audit_page"):
            self.audit_page.p1_card.set(
                f"{p1} hallazgo(s)",
                "Identidad y Control de Acceso",
            )
            self.audit_page.p2_card.set(
                f"{p2} hallazgo(s)",
                "Arquitectura y Configuración",
            )
            state = (
                "Seguro"
                if self.resultado
                and p1 + p2 == 0
                else (
                    f"{p1 + p2} hallazgo(s)"
                    if self.resultado
                    else "Sin diagnóstico"
                )
            )
            self.audit_page.total_card.set(
                state,
                (
                    f"{len(rows)} controles"
                    if rows
                    else "P1 + P2"
                ),
            )

        if hasattr(self, "reports_page"):
            self.reports_page.refresh()

        if hasattr(self, "knowledge_page"):
            self.knowledge_page.refresh()

        self._refresh_project_page()

        if hasattr(self, "topbar"):
            self.topbar.set_project(profile)
            self.topbar.set_process(
                running,
                self.proceso is not None,
            )

    def _refresh_state(self):
        super()._refresh_state()
        self._refresh_dashboard()

    def _refresh_process_state(self):
        running = self._process_running()

        if hasattr(self, "lbl_process"):
            if running:
                self.lbl_process.configure(
                    text="Proceso: EN EJECUCIÓN",
                    text_color=COLORS["success"],
                )
            elif self.proceso:
                self.lbl_process.configure(
                    text="Proceso: DETENIDO",
                    text_color=COLORS["warning"],
                )
            else:
                self.lbl_process.configure(
                    text="Proceso: no administrado",
                    text_color=COLORS["muted"],
                )

        if hasattr(self, "topbar"):
            self.topbar.set_process(
                running,
                self.proceso is not None,
            )

    def _set_busy(self, busy: bool, status: str):
        self.busy = busy

        if hasattr(self, "lbl_status"):
            self.lbl_status.configure(
                text=status
            )

        if hasattr(self, "progress"):
            if busy:
                self.progress.start()
            else:
                self.progress.stop()
                self.progress.set(0)

        self._refresh_state()

    def _log(self, text: str):
        if hasattr(self, "log_text"):
            self.log_text.configure(
                state="normal"
            )
            self.log_text.insert(
                "end",
                text.rstrip() + "\n",
            )
            self.log_text.see("end")
            self.log_text.configure(
                state="disabled"
            )

        if hasattr(self, "home_page"):
            self.home_page.console.append(
                text
            )

    def _apply_dark_native_widgets(self, widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Text):
                child.configure(
                    background="#04101A",
                    foreground="#CBE0EC",
                    insertbackground="#FFFFFF",
                    selectbackground="#124E75",
                    selectforeground="#FFFFFF",
                    relief="flat",
                    borderwidth=0,
                    highlightbackground=COLORS["border_soft"],
                    highlightcolor=COLORS["accent"],
                )
            elif isinstance(child, tk.Listbox):
                child.configure(
                    background="#071724",
                    foreground="#CBE0EC",
                    selectbackground="#124E75",
                    selectforeground="#FFFFFF",
                    borderwidth=0,
                    highlightbackground=COLORS["border_soft"],
                    highlightcolor=COLORS["accent"],
                )

            self._apply_dark_native_widgets(
                child
            )

    def _apply_responsive_layout(self):
        if not hasattr(self, "sidebar"):
            return

        width = max(
            800,
            self.winfo_width(),
        )
        height = max(
            500,
            self.winfo_height(),
        )

        ultra = (
            width < 1050
            or height < 650
        )
        compact = (
            ultra
            or width < 1380
            or height < 780
        )

        self.compact_mode = compact
        self.ultra_compact_mode = ultra

        self.sidebar.set_compact(
            compact,
            ultra,
        )

        if hasattr(self, "topbar"):
            self.topbar.set_compact(
                compact,
                ultra,
            )

        if (
            hasattr(self, "home_page")
            and hasattr(
                self.home_page,
                "set_compact",
            )
        ):
            self.home_page.set_compact(
                compact,
                ultra,
            )

        if (
            hasattr(self, "audit_page")
            and hasattr(
                self.audit_page,
                "set_compact",
            )
        ):
            self.audit_page.set_compact(
                compact,
                ultra,
            )

    def _choose_config(self):
        super()._choose_config()
        self._refresh_dashboard()

    def _choose_target(self):
        super()._choose_target()
        self._refresh_dashboard()

    def _choose_evidence_base(self):
        super()._choose_evidence_base()
        self._refresh_dashboard()

    def _profile_wizard_saved(
        self,
        profile_path: Path,
        project_root: Path,
    ):
        super()._profile_wizard_saved(
            profile_path,
            project_root,
        )
        self._refresh_dashboard()
        self._route("home")


def main():
    ModernAuditorGUI().mainloop()


if __name__ == "__main__":
    main()
