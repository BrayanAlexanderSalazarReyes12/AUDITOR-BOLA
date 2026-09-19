"""Interfaz gráfica completa del Auditor Correctivo de Seguridad de Dos Pilares."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
import time
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import requests

from .ai_gui import AIAssistantMixin
from .article_evidence import export_article_package
from .config import ConfigObjetivo, cargar_config
from .corrective import correction_available
from .cycle import (
    ciclo_correctivo,
    controles_desde_evidencias,
    corregir_controles,
    rollback_desde_evidencia,
    rollback_todas_desde_evidencias,
    verificar_control,
)
from .process_manager import LocalTargetProcess
from .profile_wizard import ProfileWizard
from .remediation_knowledge import knowledge_root
from .runner import diagnosticar, filas_gui


def calcular_layout(screen_w: int, screen_h: int) -> tuple[int, int, bool]:
    """Calcula tamaño inicial y modo compacto sin depender de Tk."""
    compact_mode = screen_w < 1280 or screen_h < 760

    margen_w = 40
    margen_h = 80
    max_w = 1360
    max_h = 820

    disponible_w = max(640, screen_w - margen_w)
    disponible_h = max(500, screen_h - margen_h)

    width = min(max_w, disponible_w)
    height = min(max_h, disponible_h)
    return width, height, compact_mode


class AuditorGUI(AIAssistantMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Aegis Auditor — Security Remediation Studio")
        self.configure(background="#f4f7fb")

        # Inicializar el modo responsivo ANTES de construir cualquier
        # sección que lo consulte.
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width, height, self.compact_mode = calcular_layout(screen_w, screen_h)

        self.geometry(f"{width}x{height}")
        self.minsize(min(760, width), min(520, height))

        self.config_path: Path | None = None
        self.cfg: ConfigObjetivo | None = None
        self.target_root: Path | None = None
        self.evidence_base = (Path.cwd() / "evidencias").resolve()
        self.resultado: dict | None = None
        self.proceso: LocalTargetProcess | None = None
        self.busy = False
        self.evidence_paths: list[Path] = []
        self.result_rows: dict[str, dict] = {}

        self.auto_manage_var = tk.BooleanVar(value=False)

        self._configure_theme()
        self._build_menu()
        self._build_brand_header()
        self._build_header()
        self._build_runtime_bar()

        # Las acciones correctivas quedan visibles antes del área central.
        self._build_actions()
        self._build_notebook()
        self._build_status()
        self._refresh_evidence_list()
        self._refresh_state()

    # ------------------------------------------------------------------
    # Construcción de interfaz
    # ------------------------------------------------------------------
    def _configure_theme(self):
        """Tema visual propio sin dependencias externas."""
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", font=("Segoe UI", 9))
        style.configure(
            "TFrame",
            background="#f4f7fb",
        )
        style.configure(
            "TLabelframe",
            background="#ffffff",
            bordercolor="#d8e1eb",
            relief="solid",
            borderwidth=1,
        )
        style.configure(
            "TLabelframe.Label",
            background="#f4f7fb",
            foreground="#24364b",
            font=("Segoe UI Semibold", 9),
        )
        style.configure(
            "TLabel",
            background="#f4f7fb",
            foreground="#24364b",
        )
        style.configure(
            "Aegis.H1.TLabel",
            font=("Segoe UI Semibold", 17),
            foreground="#0b1f33",
            background="#f4f7fb",
        )
        style.configure(
            "Aegis.Brand.TLabel",
            font=("Segoe UI Semibold", 18),
            foreground="#ffffff",
            background="#0b1f33",
        )
        style.configure(
            "Aegis.BrandSub.TLabel",
            font=("Segoe UI", 9),
            foreground="#b9c9d8",
            background="#0b1f33",
        )
        style.configure(
            "Aegis.Muted.TLabel",
            foreground="#6b7c8f",
            background="#f4f7fb",
        )
        style.configure(
            "Aegis.KpiTitle.TLabel",
            font=("Segoe UI", 8),
            foreground="#718096",
            background="#ffffff",
        )
        style.configure(
            "Aegis.KpiValue.TLabel",
            font=("Segoe UI Semibold", 13),
            foreground="#0b1f33",
            background="#ffffff",
        )
        style.configure(
            "Aegis.Primary.TButton",
            font=("Segoe UI Semibold", 9),
            foreground="#ffffff",
            background="#147d73",
            bordercolor="#147d73",
            padding=(12, 7),
        )
        style.map(
            "Aegis.Primary.TButton",
            background=[
                ("active", "#0f6b63"),
                ("disabled", "#91aaa7"),
            ],
        )
        style.configure(
            "Aegis.Secondary.TButton",
            padding=(10, 6),
        )
        style.configure(
            "Aegis.Horizontal.TProgressbar",
            troughcolor="#e5ebf1",
            background="#24b6a6",
            bordercolor="#e5ebf1",
            lightcolor="#24b6a6",
            darkcolor="#24b6a6",
        )

    def _build_menu(self):
        menubar = tk.Menu(self)

        archivo = tk.Menu(menubar, tearoff=False)
        archivo.add_command(
            label="Nuevo proyecto / Auto-configurar…",
            command=self._new_project_wizard,
            accelerator="Ctrl+N",
        )
        archivo.add_separator()
        archivo.add_command(
            label="Cargar perfil JSON…",
            command=self._choose_config,
            accelerator="Ctrl+O",
        )
        archivo.add_command(
            label="Seleccionar carpeta de código…",
            command=self._choose_target,
        )
        archivo.add_command(
            label="Seleccionar carpeta de evidencias…",
            command=self._choose_evidence_base,
        )
        archivo.add_separator()
        archivo.add_command(
            label="Guardar reporte actual…",
            command=self._save_report,
        )
        archivo.add_command(
            label="Exportar evidencia para artículo…",
            command=self._export_article_evidence,
        )
        archivo.add_separator()
        archivo.add_command(label="Salir", command=self.destroy)
        menubar.add_cascade(label="Archivo", menu=archivo)

        proyecto = tk.Menu(menubar, tearoff=False)
        proyecto.add_command(
            label="Asistente de perfil…",
            command=self._new_project_wizard,
        )
        proyecto.add_command(
            label="Ver perfil actual",
            command=self._show_profile,
        )
        proyecto.add_separator()
        proyecto.add_command(label="Iniciar objetivo", command=self._start_target)
        proyecto.add_command(label="Detener objetivo", command=self._stop_target)
        proyecto.add_command(label="Reiniciar objetivo", command=self._restart_target)
        menubar.add_cascade(label="Proyecto", menu=proyecto)

        auditoria = tk.Menu(menubar, tearoff=False)
        auditoria.add_command(
            label="Diagnosticar P1 + P2",
            command=self._diagnose,
            accelerator="F5",
        )
        auditoria.add_command(
            label="Verificar seleccionado",
            command=self._verify_selected,
        )
        auditoria.add_separator()
        auditoria.add_command(
            label="Corregir seleccionado",
            command=self._correct_selected,
        )
        auditoria.add_command(
            label="Corregir todos los hallazgos",
            command=self._correct_all,
        )
        menubar.add_cascade(label="Auditoría", menu=auditoria)

        inteligencia = tk.Menu(menubar, tearoff=False)
        inteligencia.add_command(
            label="Generar recetas con IA",
            command=self._open_ai_for_selected,
        )
        inteligencia.add_command(
            label="Medicinas conocidas",
            command=self._open_knowledge_window,
        )
        inteligencia.add_command(
            label="Parches exactos",
            command=self._open_recipe_library_window,
        )
        menubar.add_cascade(label="Conocimiento", menu=inteligencia)

        ayuda = tk.Menu(menubar, tearoff=False)
        ayuda.add_command(label="Acerca de Aegis Auditor", command=self._show_about)
        menubar.add_cascade(label="Ayuda", menu=ayuda)

        self.config(menu=menubar)
        self.bind_all("<Control-n>", lambda _event: self._new_project_wizard())
        self.bind_all("<Control-o>", lambda _event: self._choose_config())
        self.bind_all("<F5>", lambda _event: self._diagnose())

    def _build_brand_header(self):
        frame = tk.Frame(self, background="#0b1f33", height=72)
        frame.pack(fill="x")
        frame.pack_propagate(False)

        logo = tk.Canvas(
            frame,
            width=48,
            height=48,
            highlightthickness=0,
            background="#0b1f33",
        )
        logo.pack(side="left", padx=(18, 10), pady=12)
        logo.create_polygon(
            24, 3, 43, 11, 40, 33, 24, 46, 8, 33, 5, 11,
            fill="#24b6a6",
            outline="",
        )
        logo.create_line(
            14, 24, 21, 31, 35, 16,
            fill="#ffffff",
            width=4,
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND,
        )

        titles = tk.Frame(frame, background="#0b1f33")
        titles.pack(side="left", fill="y", pady=11)
        ttk.Label(
            titles,
            text="AEGIS AUDITOR",
            style="Aegis.Brand.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            titles,
            text="Security Remediation Studio · Diagnóstico, corrección y aprendizaje verificable",
            style="Aegis.BrandSub.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        ttk.Button(
            frame,
            text="＋ Nuevo proyecto",
            command=self._new_project_wizard,
            style="Aegis.Primary.TButton",
        ).pack(side="right", padx=18, pady=18)

    def _new_project_wizard(self):
        initial = self.target_root if self.target_root else None
        ProfileWizard(
            self,
            initial_project=initial,
            on_saved=self._profile_wizard_saved,
        )

    def _profile_wizard_saved(self, profile_path: Path, project_root: Path):
        try:
            cfg = cargar_config(profile_path)
        except Exception as exc:
            messagebox.showerror("Perfil inválido", str(exc))
            return

        if self.proceso and self.proceso.is_running():
            self.proceso.stop()

        self.proceso = None
        self.config_path = Path(profile_path).resolve()
        self.cfg = cfg
        self.target_root = Path(project_root).resolve()
        self.auto_manage_var.set(bool(cfg.runtime.comando_inicio))
        self.lbl_config.configure(
            text=f"{cfg.sistema} {cfg.version_objetivo or ''}".strip()
        )
        self.lbl_target.configure(text=str(self.target_root))
        self._log(
            f"Aplicación incorporada: {cfg.sistema} | "
            f"perfil={self.config_path} | código={self.target_root}"
        )
        self._refresh_state()
        self._ai_sync_selected_control()
        self.notebook.select(self.tab_dashboard)

    def _export_article_evidence(self):
        session = filedialog.askdirectory(
            parent=self,
            title="Selecciona una sesión de evidencias",
            initialdir=str(self.evidence_base),
        )
        if not session:
            return

        destination = filedialog.askdirectory(
            parent=self,
            title="Selecciona la carpeta donde crear el paquete del artículo",
            initialdir=str(Path.cwd() / "docs" / "articulo"),
        )
        if not destination:
            return

        try:
            exported = export_article_package(session, destination)
        except Exception as exc:
            messagebox.showerror(
                "No se pudo exportar la evidencia",
                str(exc),
                parent=self,
            )
            return

        self._log(f"Evidencia para artículo exportada en: {exported}")
        messagebox.showinfo(
            "Paquete para artículo creado",
            (
                "Se creó una copia redactada para documentación.\n\n"
                f"{exported}\n\n"
                "La evidencia original no fue modificada."
            ),
            parent=self,
        )

    def _show_about(self):
        messagebox.showinfo(
            "Aegis Auditor",
            (
                "AEGIS AUDITOR — Security Remediation Studio\n\n"
                "Auditor correctivo de seguridad con diagnóstico de dos "
                "pilares, remediación verificable, rollback, evidencias y "
                "aprendizaje de medicinas semánticas reutilizables.\n\n"
                "Una corrección sólo se considera válida cuando la prueba "
                "dinámica confirma que el hallazgo desapareció sin regresiones."
            ),
        )

    def _build_header(self):
        frame = ttk.LabelFrame(self, text="Objetivo", padding=8)
        frame.pack(fill="x", padx=8, pady=(8, 4))

        items = [
            (
                "Perfil de aplicación (.json)",
                self._choose_config,
                "config",
                "Sin perfil seleccionado",
            ),
            (
                "Carpeta de código local",
                self._choose_target,
                "target",
                "Sin carpeta",
            ),
            (
                "Carpeta de evidencias",
                self._choose_evidence_base,
                "evidence",
                str(self.evidence_base),
            ),
        ]

        if self.compact_mode:
            for row, (text, command, key, value) in enumerate(items):
                ttk.Button(frame, text=text, command=command).grid(
                    row=row, column=0, sticky="ew", padx=(0, 8), pady=2
                )
                label = ttk.Label(
                    frame,
                    text=value,
                    anchor="w",
                    wraplength=max(300, self.winfo_screenwidth() - 320),
                )
                label.grid(row=row, column=1, sticky="ew", pady=2)
                setattr(self, f"lbl_{key}", label)
            frame.columnconfigure(0, weight=0)
            frame.columnconfigure(1, weight=1)
        else:
            for index, (text, command, key, value) in enumerate(items):
                col = index * 2
                ttk.Button(frame, text=text, command=command).grid(
                    row=0, column=col, sticky="w", padx=(0, 6)
                )
                label = ttk.Label(
                    frame, text=value, anchor="w", wraplength=260
                )
                label.grid(
                    row=0,
                    column=col + 1,
                    sticky="ew",
                    padx=(0, 14),
                )
                setattr(self, f"lbl_{key}", label)
                frame.columnconfigure(col + 1, weight=1)

    def _build_runtime_bar(self):
        frame = ttk.LabelFrame(self, text="Ejecución y diagnóstico", padding=8)
        frame.pack(fill="x", padx=8, pady=4)

        self.btn_start = ttk.Button(
            frame, text="Iniciar objetivo", command=self._start_target
        )
        self.btn_stop = ttk.Button(
            frame, text="Detener", command=self._stop_target
        )
        self.btn_restart = ttk.Button(
            frame, text="Reiniciar", command=self._restart_target
        )
        self.btn_diagnose = ttk.Button(
            frame, text="Diagnosticar P1 + P2", command=self._diagnose
        )
        self.chk_auto_manage = ttk.Checkbutton(
            frame,
            text="Gestionar reinicio automáticamente al corregir",
            variable=self.auto_manage_var,
            command=self._refresh_state,
        )
        self.lbl_process = ttk.Label(
            frame, text="Proceso: no administrado", anchor="w"
        )

        if self.compact_mode:
            widgets = [
                (self.btn_start, 0, 0),
                (self.btn_stop, 0, 1),
                (self.btn_restart, 0, 2),
                (self.btn_diagnose, 0, 3),
            ]
            for widget, row, col in widgets:
                widget.grid(
                    row=row, column=col, sticky="ew", padx=3, pady=2
                )
                frame.columnconfigure(col, weight=1)

            self.chk_auto_manage.grid(
                row=1, column=0, columnspan=3, sticky="w", padx=3, pady=2
            )
            self.lbl_process.grid(
                row=1, column=3, sticky="e", padx=3, pady=2
            )
        else:
            self.btn_start.grid(row=0, column=0, padx=3, pady=2, sticky="ew")
            self.btn_stop.grid(row=0, column=1, padx=3, pady=2, sticky="ew")
            self.btn_restart.grid(row=0, column=2, padx=3, pady=2, sticky="ew")
            self.chk_auto_manage.grid(
                row=0, column=3, padx=12, pady=2, sticky="w"
            )
            self.lbl_process.grid(
                row=0, column=4, padx=10, pady=2, sticky="ew"
            )
            self.btn_diagnose.grid(
                row=0, column=5, padx=3, pady=2, sticky="ew"
            )
            frame.columnconfigure(4, weight=1)

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_dashboard = ttk.Frame(self.notebook)
        self.tab_results = ttk.Frame(self.notebook)
        self.tab_detail = ttk.Frame(self.notebook)
        self.tab_ai = ttk.Frame(self.notebook)
        self.tab_evidence = ttk.Frame(self.notebook)
        self.tab_log = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_dashboard, text="Inicio")
        self.notebook.add(self.tab_results, text="Hallazgos")
        self.notebook.add(self.tab_detail, text="Detalle / Corrección")
        self.notebook.add(self.tab_ai, text="IA / Medicinas")
        self.notebook.add(self.tab_evidence, text="Evidencias")
        self.notebook.add(self.tab_log, text="Registro")

        self._build_dashboard_tab()
        self._build_results_tab()
        self._build_detail_tab()
        self._build_ai_tab()
        self._build_evidence_tab()
        self._build_log_tab()

    def _build_dashboard_tab(self):
        outer = ttk.Frame(self.tab_dashboard, padding=18)
        outer.pack(fill="both", expand=True)
        for column in range(4):
            outer.columnconfigure(column, weight=1)
        outer.rowconfigure(2, weight=1)

        ttk.Label(
            outer,
            text="Centro de operación",
            style="Aegis.H1.TLabel",
        ).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(
            outer,
            text=(
                "Carga una aplicación, genera o revisa su perfil, inicia el "
                "objetivo y sigue el ciclo completo de auditoría."
            ),
            style="Aegis.Muted.TLabel",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(3, 14))

        cards = [
            ("Proyecto", "dashboard_project_value"),
            ("Perfil", "dashboard_profile_value"),
            ("Proceso", "dashboard_process_value"),
            ("Hallazgos", "dashboard_findings_value"),
        ]
        for index, (title, attr) in enumerate(cards):
            card = tk.Frame(
                outer,
                background="#ffffff",
                highlightbackground="#d8e1eb",
                highlightthickness=1,
                padx=14,
                pady=12,
            )
            card.grid(
                row=2,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 5, 0 if index == 3 else 5),
                pady=(0, 14),
            )
            ttk.Label(
                card,
                text=title.upper(),
                style="Aegis.KpiTitle.TLabel",
            ).pack(anchor="w")
            value = ttk.Label(
                card,
                text="—",
                style="Aegis.KpiValue.TLabel",
                wraplength=230,
            )
            value.pack(anchor="w", pady=(5, 0))
            setattr(self, attr, value)

        flow = ttk.LabelFrame(
            outer,
            text="Flujo recomendado",
            padding=14,
        )
        flow.grid(row=3, column=0, columnspan=4, sticky="nsew")
        for col in range(5):
            flow.columnconfigure(col, weight=1)

        steps = [
            ("1", "Incorporar", self._new_project_wizard),
            ("2", "Iniciar", self._start_target),
            ("3", "Diagnosticar", self._diagnose),
            ("4", "Remediar", self._open_ai_for_selected),
            ("5", "Evidencias", lambda: self.notebook.select(self.tab_evidence)),
        ]
        for col, (number, label, command) in enumerate(steps):
            box = ttk.Frame(flow, padding=8)
            box.grid(row=0, column=col, sticky="nsew", padx=4)
            tk.Label(
                box,
                text=number,
                width=3,
                height=1,
                background="#24b6a6",
                foreground="#ffffff",
                font=("Segoe UI Semibold", 11),
            ).pack(anchor="center", pady=(0, 7))
            ttk.Button(
                box,
                text=label,
                command=command,
                style=(
                    "Aegis.Primary.TButton"
                    if col == 0
                    else "Aegis.Secondary.TButton"
                ),
            ).pack(fill="x")
        ttk.Label(
            flow,
            text=(
                "Aegis conserva línea base, backups, diff, re-verificación, "
                "rollback y medicinas aprendidas durante el proceso."
            ),
            style="Aegis.Muted.TLabel",
            wraplength=800,
        ).grid(row=1, column=0, columnspan=5, sticky="w", pady=(14, 0))

    def _refresh_dashboard(self):
        if not hasattr(self, "dashboard_project_value"):
            return

        self.dashboard_project_value.configure(
            text=(self.target_root.name if self.target_root else "Sin cargar")
        )
        self.dashboard_profile_value.configure(
            text=(self.cfg.sistema if self.cfg else "Sin perfil")
        )
        self.dashboard_process_value.configure(
            text=("En ejecución" if self._process_running() else "Detenido")
        )

        findings = 0
        p1_findings = 0
        p2_findings = 0
        if self.resultado:
            for row in filas_gui(self.resultado):
                if row.get("estado") != "HALLAZGO":
                    continue
                findings += 1
                pillar = str(row.get("pilar") or "").upper()
                if pillar in {"1", "P1", "PILAR 1"}:
                    p1_findings += 1
                elif pillar in {"2", "P2", "PILAR 2"}:
                    p2_findings += 1

        self.dashboard_findings_value.configure(
            text=f"{findings} · P1 {p1_findings} / P2 {p2_findings}"
        )

    def _build_results_tab(self):
        columns = (
            "pilar",
            "id",
            "control",
            "cuenta",
            "estado",
            "correccion",
            "detalle",
        )

        holder = ttk.Frame(self.tab_results)
        holder.pack(fill="both", expand=True)
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

        self.table = ttk.Treeview(
            holder, columns=columns, show="headings", height=12
        )
        titles = {
            "pilar": "Pilar",
            "id": "Control",
            "control": "Descripción",
            "cuenta": "Cuenta",
            "estado": "Estado",
            "correccion": "Corrección",
            "detalle": "Detalle",
        }
        base_widths = {
            "pilar": 55,
            "id": 120,
            "control": 240,
            "cuenta": 115,
            "estado": 115,
            "correccion": 95,
            "detalle": 360,
        }
        for col in columns:
            self.table.heading(col, text=titles[col])
            self.table.column(
                col,
                width=base_widths[col],
                minwidth=55 if col == "pilar" else 80,
                stretch=col in {"control", "detalle"},
                anchor="w",
            )

        self.table.tag_configure("hallazgo", background="#f8d7da")
        self.table.tag_configure("ok", background="#d4edda")
        self.table.tag_configure("error", background="#fff3cd")
        self.table.bind("<<TreeviewSelect>>", self._on_result_selected)

        scroll_y = ttk.Scrollbar(
            holder, orient="vertical", command=self.table.yview
        )
        scroll_x = ttk.Scrollbar(
            holder, orient="horizontal", command=self.table.xview
        )
        self.table.configure(
            yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set
        )
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

        holder.bind("<Configure>", self._resize_results_columns)

    def _resize_results_columns(self, event=None):
        if not hasattr(self, "table"):
            return
        width = max(
            600,
            (event.width if event is not None else self.table.winfo_width()) - 28,
        )

        fixed = {
            "pilar": 55,
            "id": 120,
            "cuenta": 110,
            "estado": 110,
            "correccion": 90,
        }
        fixed_total = sum(fixed.values())
        flexible = max(260, width - fixed_total)
        control_width = max(150, int(flexible * 0.38))
        detail_width = max(210, flexible - control_width)

        for col, col_width in fixed.items():
            self.table.column(col, width=col_width)
        self.table.column("control", width=control_width)
        self.table.column("detalle", width=detail_width)

    def _build_detail_tab(self):
        self.tab_detail.rowconfigure(0, weight=1)
        self.tab_detail.columnconfigure(0, weight=1)

        self.detail_text = tk.Text(
            self.tab_detail,
            wrap="none",
            font=("Consolas", 10),
            undo=False,
        )
        scroll_y = ttk.Scrollbar(
            self.tab_detail,
            orient="vertical",
            command=self.detail_text.yview,
        )
        scroll_x = ttk.Scrollbar(
            self.tab_detail,
            orient="horizontal",
            command=self.detail_text.xview,
        )
        self.detail_text.configure(
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
        )
        self.detail_text.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

    def _build_evidence_tab(self):
        orient = tk.VERTICAL if self.compact_mode else tk.HORIZONTAL
        pane = tk.PanedWindow(
            self.tab_evidence,
            orient=orient,
            sashwidth=6,
            relief="flat",
            bd=0,
        )
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane, padding=6)
        right = ttk.Frame(pane, padding=6)
        pane.add(left, minsize=180, stretch="always")
        pane.add(right, minsize=260, stretch="always")

        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        ttk.Label(left, text="Sesiones").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self.evidence_list = tk.Listbox(
            left,
            height=7 if self.compact_mode else 14,
            exportselection=False,
        )
        list_scroll = ttk.Scrollbar(
            left, orient="vertical", command=self.evidence_list.yview
        )
        self.evidence_list.configure(yscrollcommand=list_scroll.set)
        self.evidence_list.grid(row=1, column=0, sticky="nsew")
        list_scroll.grid(row=1, column=1, sticky="ns")
        self.evidence_list.bind(
            "<<ListboxSelect>>", lambda _e: self._preview_selected_evidence()
        )

        buttons = ttk.Frame(left)
        buttons.grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        ttk.Button(
            buttons, text="Actualizar", command=self._refresh_evidence_list
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(
            buttons, text="Abrir carpeta", command=self._open_selected_evidence
        ).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        self.btn_rollback = ttk.Button(
            buttons,
            text="Revertir esta corrección",
            command=self._rollback_selected_evidence,
        )
        self.btn_rollback.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0)
        )

        self.btn_rollback_all = ttk.Button(
            buttons,
            text="Revertir todas las correcciones",
            command=self._rollback_all_evidence,
        )
        self.btn_rollback_all.grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0)
        )

        self.evidence_text = tk.Text(
            right, wrap="none", font=("Consolas", 10)
        )
        scroll_y = ttk.Scrollbar(
            right, orient="vertical", command=self.evidence_text.yview
        )
        scroll_x = ttk.Scrollbar(
            right, orient="horizontal", command=self.evidence_text.xview
        )
        self.evidence_text.configure(
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
        )
        self.evidence_text.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

    def _build_log_tab(self):
        self.tab_log.rowconfigure(0, weight=1)
        self.tab_log.columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            self.tab_log,
            wrap="none",
            font=("Consolas", 10),
            state="disabled",
        )
        scroll_y = ttk.Scrollbar(
            self.tab_log, orient="vertical", command=self.log_text.yview
        )
        scroll_x = ttk.Scrollbar(
            self.tab_log, orient="horizontal", command=self.log_text.xview
        )
        self.log_text.configure(
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

    def _build_actions(self):
        frame = ttk.LabelFrame(self, text="Acciones correctivas", padding=8)
        frame.pack(fill="x", padx=8, pady=4)

        self.btn_verify = ttk.Button(
            frame,
            text="Verificar seleccionado",
            command=self._verify_selected,
        )
        self.btn_correct = ttk.Button(
            frame,
            text="Corregir seleccionado",
            command=self._correct_selected,
        )
        self.btn_correct_all = ttk.Button(
            frame,
            text="Corregir todos los hallazgos",
            command=self._correct_all,
        )
        self.btn_ai_open = ttk.Button(
            frame,
            text="Generar recetas con IA",
            command=self._open_ai_for_selected,
        )
        self.btn_show_profile = ttk.Button(
            frame,
            text="Ver perfil JSON",
            command=self._show_profile,
        )
        self.btn_save = ttk.Button(
            frame,
            text="Guardar reporte actual",
            command=self._save_report,
        )

        widgets = [
            self.btn_verify,
            self.btn_correct,
            self.btn_correct_all,
            self.btn_ai_open,
            self.btn_show_profile,
            self.btn_save,
        ]
        columns = 2 if self.compact_mode else 6

        for index, widget in enumerate(widgets):
            row = index // columns
            col = index % columns
            widget.grid(
                row=row,
                column=col,
                sticky="ew",
                padx=3,
                pady=2,
            )

        for col in range(columns):
            frame.columnconfigure(col, weight=1)

    def _build_status(self):
        frame = ttk.Frame(self, padding=(8, 4))
        frame.pack(fill="x")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        self.lbl_summary = ttk.Label(
            frame,
            text="Sin diagnóstico.",
            anchor="w",
            wraplength=520 if not self.compact_mode else 340,
        )
        self.lbl_summary.grid(row=0, column=0, sticky="ew")

        right = ttk.Frame(frame)
        right.grid(row=0, column=1, sticky="ew")
        right.columnconfigure(0, weight=1)

        self.lbl_status = ttk.Label(
            right,
            text="Listo.",
            anchor="e",
            wraplength=420 if not self.compact_mode else 260,
        )
        self.lbl_status.grid(row=0, column=0, sticky="ew")

        self.progress = ttk.Progressbar(
            right,
            mode="indeterminate",
            length=180,
            style="Aegis.Horizontal.TProgressbar",
        )
        self.progress.grid(row=1, column=0, sticky="e", pady=(3, 0))

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _run_background(self, task, on_success, label: str):
        if self.busy:
            return
        self._set_busy(True, label)

        def worker():
            try:
                result = task()
            except Exception as exc:
                # Python elimina la variable del except al salir del bloque.
                # Capturarla como argumento por defecto conserva el error
                # hasta que Tkinter ejecute el callback diferido.
                self.after(
                    0,
                    lambda error=exc: self._background_error(error),
                )
                return

            self.after(
                0,
                lambda value=result, callback=on_success:
                    self._background_success(value, callback),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _background_success(self, result, callback):
        self._set_busy(False, "Listo.")
        self._refresh_process_state()
        self._refresh_dashboard()
        self._refresh_ai_state()
        callback(result)

    def _background_error(self, exc: Exception):
        self._set_busy(False, "Error.")
        self._refresh_process_state()
        self._log(f"ERROR: {exc}")
        messagebox.showerror("Operación no completada", str(exc))

    def _set_busy(self, busy: bool, status: str):
        self.busy = busy
        self.lbl_status.configure(text=status)
        if hasattr(self, "progress"):
            if busy:
                self.progress.start(12)
            else:
                self.progress.stop()
        self._refresh_state()

    def _selected_values(self):
        selected = self.table.selection()
        if not selected:
            return None
        return self.table.item(selected[0], "values")

    def _selected_row_data(self) -> dict | None:
        selected = self.table.selection()
        if not selected:
            return None
        return self.result_rows.get(selected[0])

    def _selected_selector(self) -> dict | None:
        row = self._selected_row_data()
        if not row:
            return None
        return {
            "cuenta": row.get("cuenta"),
            "metodo": row.get("metodo"),
            "ruta": row.get("ruta"),
            "tipo_control": row.get("tipo_control"),
        }

    def _selected_control(self) -> str | None:
        values = self._selected_values()
        return values[1] if values else None

    def _selected_state(self) -> str | None:
        values = self._selected_values()
        return values[4] if values else None

    def _selected_evidence_path(self) -> Path | None:
        selection = self.evidence_list.curselection()
        if not selection:
            return None
        index = selection[0]
        if index >= len(self.evidence_paths):
            return None
        return self.evidence_paths[index]

    def _process_running(self) -> bool:
        return bool(self.proceso and self.proceso.is_running())

    def _runtime_available(self) -> bool:
        return bool(
            self.cfg
            and self.target_root
            and self.cfg.runtime.comando_inicio
        )

    def _target_reachable(self, timeout: float = 0.6) -> bool:
        if not self.cfg or not self.cfg.base_url:
            return False
        try:
            requests.get(self.cfg.base_url, timeout=timeout)
            return True
        except requests.RequestException:
            return False

    def _wait_target_ready(self, timeout: float = 8.0) -> None:
        if not self.cfg or not self.cfg.base_url:
            return
        limite = time.time() + timeout
        while time.time() < limite:
            if self._target_reachable(timeout=0.5):
                return
            time.sleep(0.25)
        raise RuntimeError(
            f"El objetivo no respondió en {self.cfg.base_url} después del reinicio."
        )

    def _controls_require_restart(self, controls: list[str]) -> list[str]:
        if not self.cfg:
            return []
        requeridos: list[str] = []
        for control_id in controls:
            receta = self.cfg.correccion_por_control(control_id)
            if receta and receta.requiere_reinicio:
                requeridos.append(control_id)
        return requeridos

    def _prepare_restart_callback(self, controls: list[str]):
        """Prepara un reinicio verificable para controles dinámicos."""
        if not self.cfg or not self.target_root:
            return None

        requieren = self._controls_require_restart(controls)

        # Nunca verificar una corrección de código contra una instancia que
        # responde en base_url pero no pertenece al proceso administrado por
        # esta GUI. Eso puede hacer que la verificación golpee código viejo y
        # marque falsamente todas las recetas como NO_CORREGIDO.
        if (
            (self.proceso is None or not self.proceso.is_running())
            and self._target_reachable()
        ):
            raise RuntimeError(
                f"Hay una instancia activa en {self.cfg.base_url} que no fue "
                "iniciada por el auditor o quedó huérfana de un arranque "
                "anterior. Detén esa instancia y vuelve a ejecutar la "
                "corrección; el Auditor debe controlar el proceso que verifica."
            )

        # Si ningún control exige reinicio explícito, un proceso administrado
        # sí se reinicia de todos modos para asegurar que la verificación lea
        # el código recién modificado.
        if not requieren:
            if self.proceso and self.proceso.is_running():
                def restart_existing():
                    self.proceso.restart()
                    self._wait_target_ready()
                return restart_existing
            return None

        if not self.cfg.runtime.comando_inicio:
            raise RuntimeError(
                "Los controles "
                + ", ".join(requieren)
                + " requieren reiniciar la aplicación, pero el perfil no "
                  "declara runtime.comando_inicio."
            )

        if self.proceso is None:
            self.proceso = LocalTargetProcess(
                self.target_root, self.cfg.runtime
            )

        if not self.proceso.is_running():
            self.proceso.start()
            self._wait_target_ready()

        def restart_and_wait():
            self.proceso.restart()
            self._wait_target_ready()

        return restart_and_wait

    def _refresh_state(self):
        has_profile = self.cfg is not None
        has_target = self.target_root is not None
        runtime = self._runtime_available()
        running = self._process_running()
        selected = self._selected_control()
        selected_state = self._selected_state()
        can_correct = bool(
            selected
            and selected_state == "HALLAZGO"
            and has_target
            and self.cfg
            and correction_available(self.cfg, selected)
        )
        hallazgos = self._all_findings()

        normal_or_disabled = lambda ok: "normal" if ok and not self.busy else "disabled"

        self.btn_diagnose.configure(
            state=normal_or_disabled(has_profile)
        )
        self.btn_start.configure(
            state=normal_or_disabled(runtime and not running)
        )
        self.btn_stop.configure(
            state=normal_or_disabled(running)
        )
        self.btn_restart.configure(
            state=normal_or_disabled(runtime and running)
        )
        self.btn_verify.configure(
            state=normal_or_disabled(bool(selected and has_profile))
        )
        self.btn_correct.configure(
            state=normal_or_disabled(can_correct)
        )
        self.btn_correct_all.configure(
            state=normal_or_disabled(bool(hallazgos and has_target))
        )
        self.btn_save.configure(
            state=normal_or_disabled(self.resultado is not None)
        )

        evidence_path = self._selected_evidence_path()
        rollback_ok = bool(
            evidence_path
            and has_target
            and (evidence_path / "cambios" / "correccion.json").exists()
        )
        self.btn_rollback.configure(
            state=normal_or_disabled(rollback_ok)
        )

        rollback_all_ok = bool(
            has_target
            and self.evidence_base.exists()
            and any(
                path.is_dir()
                and (path / "cambios" / "correccion.json").exists()
                for path in self.evidence_base.iterdir()
            )
        )
        self.btn_rollback_all.configure(
            state=normal_or_disabled(rollback_all_ok)
        )

        self._refresh_process_state()
        self._refresh_ai_state()

    def _refresh_process_state(self):
        if self._process_running():
            self.lbl_process.configure(text="Proceso: EN EJECUCIÓN")
        elif self.proceso:
            self.lbl_process.configure(text="Proceso: DETENIDO")
        else:
            self.lbl_process.configure(text="Proceso: no administrado")

    def _all_findings(self) -> list[str]:
        if not self.resultado:
            return []
        controls: list[str] = []
        for row in filas_gui(self.resultado):
            control_id = row["id"]
            if row["estado"] == "HALLAZGO" and control_id not in controls:
                controls.append(control_id)
        return controls

    def _correctable_findings(self) -> list[str]:
        if not self.cfg:
            return []
        return [
            control_id
            for control_id in self._all_findings()
            if correction_available(self.cfg, control_id)
        ]

    # ------------------------------------------------------------------
    # Selección de archivos / carpetas
    # ------------------------------------------------------------------
    def _choose_config(self):
        path = filedialog.askopenfilename(
            title="Seleccione el perfil de la aplicación",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            cfg = cargar_config(path)
        except Exception as exc:
            messagebox.showerror("Perfil inválido", str(exc))
            return

        self.config_path = Path(path)
        self.cfg = cfg
        self.auto_manage_var.set(bool(cfg.runtime.comando_inicio))
        self.lbl_config.configure(
            text=f"{cfg.sistema} {cfg.version_objetivo or ''}".strip()
        )
        self._log(f"Perfil cargado: {path}")
        self._refresh_state()

    def _choose_target(self):
        path = filedialog.askdirectory(
            title="Seleccione la copia local del código objetivo"
        )
        if not path:
            return
        if self.proceso and self.proceso.is_running():
            self.proceso.stop()
        self.proceso = None
        self.target_root = Path(path).resolve()
        self.lbl_target.configure(text=str(self.target_root))
        self._log(f"Código objetivo: {self.target_root}")
        self._refresh_state()
        self._ai_sync_selected_control()

    def _choose_evidence_base(self):
        path = filedialog.askdirectory(
            title="Seleccione la carpeta donde guardar evidencias"
        )
        if not path:
            return
        self.evidence_base = Path(path).resolve()
        self.lbl_evidence.configure(text=str(self.evidence_base))
        self._log(f"Carpeta de evidencias: {self.evidence_base}")
        self._refresh_evidence_list()

    # ------------------------------------------------------------------
    # Proceso local
    # ------------------------------------------------------------------
    def _start_target(self):
        if not self.cfg or not self.target_root:
            return

        def task():
            if self.proceso is None:
                self.proceso = LocalTargetProcess(
                    self.target_root, self.cfg.runtime
                )
            # No bloquear el arranque únicamente porque base_url ya
            # responda. Puede tratarse de otro servicio usando el mismo puerto.
            # El gestor de procesos intentará iniciar el objetivo y, si existe
            # una colisión real (por ejemplo EADDRINUSE), mostrará la salida
            # concreta del runtime en lugar de asumir que es esta aplicación.
            self.proceso.start()
            self._wait_target_ready()
            return True

        def done(_):
            self._log(f"{self.cfg.sistema} iniciado.")
            self.lbl_status.configure(text="Objetivo iniciado.")
            self._refresh_state()

        self._run_background(task, done, "Iniciando objetivo…")

    def _stop_target(self):
        if not self.proceso:
            return

        def task():
            self.proceso.stop()
            return True

        def done(_):
            self._log("Objetivo detenido.")
            self.lbl_status.configure(text="Objetivo detenido.")
            self._refresh_state()

        self._run_background(task, done, "Deteniendo objetivo…")

    def _restart_target(self):
        if not self.proceso:
            return

        def task():
            self.proceso.restart()
            return True

        def done(_):
            self._log("Objetivo reiniciado.")
            self.lbl_status.configure(text="Objetivo reiniciado.")
            self._refresh_state()

        self._run_background(task, done, "Reiniciando objetivo…")

    # ------------------------------------------------------------------
    # Diagnóstico / verificación
    # ------------------------------------------------------------------
    def _diagnose(self):
        if not self.cfg:
            return

        def task():
            return diagnosticar(self.cfg, self.target_root)

        self._run_background(
            task,
            self._show_result,
            "Diagnosticando los dos pilares…",
        )

    def _show_result(self, result: dict):
        self.resultado = result
        for item in self.table.get_children():
            self.table.delete(item)
        self.result_rows = {}

        for row in filas_gui(result):
            corregible = bool(
                self.cfg and correction_available(self.cfg, row["id"])
            )
            if row["estado"] == "HALLAZGO":
                tag = "hallazgo"
            elif row["estado"] == "ERROR":
                tag = "error"
            else:
                tag = "ok"

            iid = self.table.insert(
                "",
                "end",
                values=(
                    row["pilar"],
                    row["id"],
                    row["control"],
                    row["cuenta"],
                    row["estado"],
                    "Sí" if corregible else "No",
                    row["detalle"],
                ),
                tags=(tag,),
            )
            self.result_rows[iid] = row

        r = result["resumen"]
        total = (
            r["bola_confirmados"]
            + r["acceso_vulnerable"]
            + r["agente_vulnerable"]
            + r["pilar2_hallazgos"]
        )
        corregibles = len(self._correctable_findings())
        sin_receta = max(0, len(self._all_findings()) - corregibles)
        self.lbl_summary.configure(
            text=(
                f"Sistema: {result['sistema']} | "
                f"Hallazgos: {total} | Errores: {r['errores']} | "
                f"Con receta: {corregibles} | Sin receta: {sin_receta}"
            )
        )
        self.lbl_status.configure(text="Diagnóstico completo.")
        self.notebook.select(self.tab_results)
        self._log(
            f"Diagnóstico: {total} hallazgo(s), "
            f"{r['errores']} error(es)."
        )
        self._refresh_state()

    def _verify_selected(self):
        control = self._selected_control()
        if not control or not self.cfg:
            return

        selector = self._selected_selector()

        def task():
            return verificar_control(
                self.cfg,
                control,
                self.target_root,
                evidence_base=self.evidence_base,
                selector=selector,
            )

        def done(payload):
            self._log(
                f"Verificación {control}: {payload['estado']} "
                f"({payload['evidencia']})"
            )
            self._refresh_evidence_list(select_path=Path(payload["evidencia"]))
            messagebox.showinfo(
                "Verificación",
                f"{control}: {payload['estado']}",
            )
            self._diagnose()

        self._run_background(task, done, f"Verificando {control}…")

    # ------------------------------------------------------------------
    # Correcciones
    # ------------------------------------------------------------------
    def _correct_selected(self):
        control = self._selected_control()
        if (
            not control
            or not self.cfg
            or not self.target_root
            or not correction_available(self.cfg, control)
        ):
            return

        receta = self.cfg.correccion_por_control(control)
        archivo = receta.archivo if receta else "archivo configurado"
        selector = self._selected_selector()
        if not messagebox.askyesno(
            "Aplicar corrección",
            (
                f"Se modificará la copia local:\n\n"
                f"Control: {control}\n"
                f"Archivo: {archivo}\n\n"
                "Se creará backup y, si la verificación falla, "
                "el auditor hará rollback automático.\n\n"
                "¿Continuar?"
            ),
        ):
            return

        def task():
            reiniciar = self._prepare_restart_callback([control])
            return ciclo_correctivo(
                self.cfg,
                control,
                self.target_root,
                evidence_base=self.evidence_base,
                reiniciar=reiniciar,
                selector=selector,
            )

        def done(manifest):
            estado = manifest["estado_final"]
            self._log(
                f"Corrección {control}: {estado} "
                f"({manifest.get('evidencia')})"
            )
            evidence = manifest.get("evidencia")
            if evidence:
                self._refresh_evidence_list(select_path=Path(evidence))
            detalle = manifest.get("error") or manifest.get("motivo")
            mensaje = f"{control}: {estado}"
            if detalle:
                mensaje += f"\n\n{detalle}"
            messagebox.showinfo(
                "Ciclo correctivo",
                mensaje,
            )
            self._diagnose()

        self._run_background(
            task, done, f"Corrigiendo y verificando {control}…"
        )

    def _correct_all(self):
        if not self.cfg or not self.target_root:
            return

        controls = self._all_findings()
        if not controls:
            messagebox.showinfo(
                "Correcciones",
                "No hay hallazgos pendientes.",
            )
            return

        corregibles = [
            control_id
            for control_id in controls
            if correction_available(self.cfg, control_id)
        ]
        sin_receta = [
            control_id
            for control_id in controls
            if not correction_available(self.cfg, control_id)
        ]

        resumen = (
            f"Hallazgos detectados: {len(controls)}\n"
            f"Con receta automática: {len(corregibles)}\n"
            f"Sin receta automática: {len(sin_receta)}\n\n"
            + "\n".join(f"• {item}" for item in controls)
        )
        if sin_receta:
            resumen += (
                "\n\nLos controles sin receta también serán registrados "
                "como PENDIENTE_SIN_RECETA; no se omitirán."
            )
        resumen += (
            "\n\nCada corrección automática tendrá backup, verificación "
            "y rollback si falla. ¿Continuar?"
        )

        if not messagebox.askyesno("Corregir todos", resumen):
            return

        def task():
            reiniciar = self._prepare_restart_callback(controls)
            return corregir_controles(
                self.cfg,
                controls,
                self.target_root,
                evidence_base=self.evidence_base,
                reiniciar=reiniciar,
            )

        def done(manifests):
            lines = []
            last_evidence = None
            for item in manifests:
                control = item.get("control")
                estado = item.get("estado_final")
                linea = f"{control}: {estado}"
                detalle = item.get("error") or item.get("motivo")
                if detalle:
                    linea += f" — {detalle}"
                lines.append(linea)
                if item.get("evidencia"):
                    last_evidence = Path(item["evidencia"])
                if item.get("error"):
                    self._log(f"{control}: {estado} - {item['error']}")
                elif item.get("motivo"):
                    self._log(f"{control}: {estado} - {item['motivo']}")
                else:
                    self._log(f"{control}: {estado}")

            self._refresh_evidence_list(select_path=last_evidence)
            messagebox.showinfo(
                "Resultado del procesamiento",
                "\n".join(lines),
            )
            self._diagnose()

        self._run_background(
            task,
            done,
            f"Procesando {len(controls)} hallazgo(s)…",
        )

    # ------------------------------------------------------------------
    # Evidencias / rollback
    # ------------------------------------------------------------------
    def _refresh_evidence_list(self, select_path: Path | None = None):
        self.evidence_base.mkdir(parents=True, exist_ok=True)
        paths = [
            p for p in self.evidence_base.iterdir()
            if p.is_dir()
        ]
        self.evidence_paths = sorted(paths, key=lambda p: p.name, reverse=True)

        self.evidence_list.delete(0, "end")
        selected_index = None
        for index, path in enumerate(self.evidence_paths):
            label = path.name
            manifest_path = path / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(
                        manifest_path.read_text(encoding="utf-8")
                    )
                    control = manifest.get("control", "-")
                    estado = manifest.get("estado_final", "-")
                    label = f"{path.name} | {control} | {estado}"
                except Exception:
                    pass
            self.evidence_list.insert("end", label)
            if select_path and path.resolve() == select_path.resolve():
                selected_index = index

        if selected_index is not None:
            self.evidence_list.selection_set(selected_index)
            self.evidence_list.see(selected_index)
            self._preview_selected_evidence()
        self._refresh_state()

    def _preview_selected_evidence(self):
        path = self._selected_evidence_path()
        self.evidence_text.delete("1.0", "end")
        if not path:
            self._refresh_state()
            return

        parts = []
        for relative in (
            "manifest.json",
            "cambios/correccion.json",
            "verification/manual_rollback.json",
        ):
            file_path = path / relative
            if file_path.exists():
                parts.append(f"===== {relative} =====")
                try:
                    payload = json.loads(
                        file_path.read_text(encoding="utf-8")
                    )
                    parts.append(
                        json.dumps(payload, ensure_ascii=False, indent=2)
                    )
                except Exception:
                    parts.append(file_path.read_text(encoding="utf-8"))

        diff_files = sorted((path / "cambios").glob("*.diff"))
        for diff_file in diff_files:
            parts.append(f"===== cambios/{diff_file.name} =====")
            parts.append(diff_file.read_text(encoding="utf-8"))

        self.evidence_text.insert("1.0", "\n\n".join(parts))
        self._refresh_state()

    def _rollback_selected_evidence(self):
        path = self._selected_evidence_path()
        if not path or not self.target_root:
            return

        if not messagebox.askyesno(
            "Rollback manual",
            (
                "Se restaurará el archivo desde el backup guardado en:\n\n"
                f"{path}\n\n¿Continuar?"
            ),
        ):
            return

        auto_manage = self.auto_manage_var.get()

        def task():
            reiniciar = self._reiniciar_callback(auto_manage)
            return rollback_desde_evidencia(
                path,
                self.target_root,
                reiniciar=reiniciar,
            )

        def done(payload):
            estado = (
                "RESTAURADO"
                if payload["restauracion_ok"]
                else "HASH NO COINCIDE"
            )
            self._log(
                f"Rollback {payload['control']}: {estado}"
            )
            self._preview_selected_evidence()
            messagebox.showinfo(
                "Rollback",
                (
                    f"{payload['control']}: {estado}\n"
                    f"Archivo: {payload['archivo']}"
                ),
            )
            self._diagnose()

        self._run_background(task, done, "Revirtiendo corrección…")

    def _rollback_all_evidence(self):
        if not self.target_root:
            return

        sessions = (
            [
                path
                for path in self.evidence_base.iterdir()
                if path.is_dir()
                and (path / "cambios" / "correccion.json").exists()
            ]
            if self.evidence_base.exists()
            else []
        )

        if not sessions:
            messagebox.showinfo(
                "Revertir todas",
                "No hay sesiones correctivas para revertir.",
            )
            return

        if not messagebox.askyesno(
            "Revertir todas las correcciones",
            (
                f"Se revisarán {len(sessions)} sesión(es) correctiva(s) "
                "desde la más reciente hasta la más antigua.\n\n"
                "Solo se restaurará un archivo cuando su SHA-256 actual "
                "coincida con el estado corregido guardado. Los archivos "
                "modificados por fuera del auditor no serán sobrescritos.\n\n"
                "¿Deseas continuar?"
            ),
        ):
            return

        controls = controles_desde_evidencias(self.evidence_base)

        def task():
            reiniciar = self._prepare_restart_callback(controls)
            return rollback_todas_desde_evidencias(
                self.evidence_base,
                self.target_root,
                reiniciar=reiniciar,
            )

        def done(payload):
            self._refresh_evidence_list()
            self._log(
                "Rollback total: "
                f"revertidas={payload['revertidas']}, "
                f"ya_revertidas={payload['ya_revertidas']}, "
                f"conflictos={payload['conflictos_hash']}, "
                f"errores={payload['errores']}"
            )

            mensaje = (
                f"Sesiones encontradas: {payload['sesiones_encontradas']}\n"
                f"Revertidas: {payload['revertidas']}\n"
                f"Ya revertidas: {payload['ya_revertidas']}\n"
                f"Conflictos de hash: {payload['conflictos_hash']}\n"
                f"Errores: {payload['errores']}"
            )
            if payload.get("reinicio_error"):
                mensaje += (
                    "\n\nEl código fue procesado, pero hubo un error "
                    f"al reiniciar: {payload['reinicio_error']}"
                )

            messagebox.showinfo(
                "Resultado de revertir todas",
                mensaje,
            )
            if self.cfg:
                self._diagnose()

        self._run_background(
            task,
            done,
            "Revirtiendo todas las correcciones…",
        )

    def _open_selected_evidence(self):
        path = self._selected_evidence_path()
        if not path:
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("Abrir carpeta", str(exc))

    # ------------------------------------------------------------------
    # Detalles y reportes
    # ------------------------------------------------------------------
    def _on_result_selected(self, _event=None):
        values = self._selected_values()
        self.detail_text.delete("1.0", "end")
        if not values:
            self._refresh_state()
            self._ai_sync_selected_control()
            return

        control = values[1]
        detail = {
            "pilar": values[0],
            "control": control,
            "descripcion": values[2],
            "cuenta": values[3],
            "estado": values[4],
            "correccion_disponible": values[5],
            "detalle": values[6],
        }

        if self.cfg:
            receta = self.cfg.correccion_por_control(control)
            if receta:
                detail["receta_correctiva"] = asdict(receta)

        self.detail_text.insert(
            "1.0",
            json.dumps(detail, ensure_ascii=False, indent=2),
        )
        self._refresh_state()
        self._ai_sync_selected_control()

    def _show_profile(self):
        if not self.config_path:
            messagebox.showinfo(
                "Perfil", "Primero seleccione un perfil JSON."
            )
            return
        try:
            raw = json.loads(
                self.config_path.read_text(encoding="utf-8")
            )
            text = json.dumps(raw, ensure_ascii=False, indent=2)
        except Exception as exc:
            messagebox.showerror("Perfil", str(exc))
            return

        window = tk.Toplevel(self)
        window.title(f"Perfil — {self.config_path.name}")
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        width = min(900, max(640, screen_w - 120))
        height = min(650, max(460, screen_h - 160))
        window.geometry(f"{width}x{height}")

        holder = ttk.Frame(window)
        holder.pack(fill="both", expand=True)
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

        widget = tk.Text(holder, wrap="none", font=("Consolas", 10))
        scroll_y = ttk.Scrollbar(
            holder, orient="vertical", command=widget.yview
        )
        scroll_x = ttk.Scrollbar(
            holder, orient="horizontal", command=widget.xview
        )
        widget.configure(
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
        )
        widget.insert("1.0", text)
        widget.configure(state="disabled")
        widget.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

    def _save_report(self):
        if not self.resultado:
            return
        path = filedialog.asksaveasfilename(
            title="Guardar reporte",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        Path(path).write_text(
            json.dumps(self.resultado, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.lbl_status.configure(text=f"Reporte guardado: {path}")
        self._log(f"Reporte guardado: {path}")

    def destroy(self):
        if self.proceso:
            self.proceso.stop()
        super().destroy()


def main():
    AuditorGUI().mainloop()


if __name__ == "__main__":
    main()
