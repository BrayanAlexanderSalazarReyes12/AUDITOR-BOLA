"""Mixin de interfaz para generación y selección humana de recetas IA."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from .ai_preview import preview_recipe
from .ai_recipes import (
    AIProviderConfig,
    AIRecipeProposal,
    cargar_configuracion_opencode,
    generar_tres_recetas,
    generalizar_correccion_exitosa,
    guardar_seleccion_ia,
    guardar_sesion_ia,
    propuesta_a_correccion,
)
from .cycle import ciclo_correctivo
from .source_locator import resolver_archivo_fuente
from .remediation_knowledge import (
    KnowledgeCandidate,
    buscar_conocimiento,
    crear_conocimiento_respaldo_verificado,
    guardar_conocimiento,
    knowledge_root,
    registrar_uso_conocimiento,
)
from .recipe_library import (
    RecipeLibraryCandidate,
    biblioteca_por_defecto,
    buscar_recetas_compatibles,
    guardar_receta_biblioteca,
    marcar_uso_receta,
)


class AIAssistantMixin:
    """Añade a la GUI principal un flujo humano-en-el-bucle para recetas IA."""

    def _build_ai_tab(self):
        self.ai_source_relative: str | None = None
        self.ai_proposals: list[AIRecipeProposal] = []
        self.ai_session_dir: Path | None = None
        self.ai_current_recipe = None
        self.ai_provider: AIProviderConfig | None = None
        self.ai_proposals_window = None
        self.ai_proposals_notebook = None
        self.ai_library_candidates: list[RecipeLibraryCandidate] = []
        self.ai_library_window = None
        self.ai_selected_library_candidate: RecipeLibraryCandidate | None = None
        self.ai_knowledge_candidates: list[KnowledgeCandidate] = []
        self.ai_active_knowledge_candidate: KnowledgeCandidate | None = None
        self.ai_knowledge_window = None

        outer = ttk.Frame(self.tab_ai, padding=8)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(2, weight=1)
        outer.columnconfigure(0, weight=1)

        header = ttk.LabelFrame(
            outer,
            text="Gemma — Laboratorio UTB",
            padding=8,
        )
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Control seleccionado:").grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        self.lbl_ai_control = ttk.Label(
            header, text="Ninguno", anchor="w"
        )
        self.lbl_ai_control.grid(row=0, column=1, sticky="ew")

        ttk.Label(header, text="Archivo a analizar:").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=(4, 0)
        )
        self.lbl_ai_source = ttk.Label(
            header, text="No seleccionado", anchor="w"
        )
        self.lbl_ai_source.grid(
            row=1, column=1, sticky="ew", pady=(4, 0)
        )
        ttk.Button(
            header,
            text="Elegir archivo",
            command=self._choose_ai_source,
        ).grid(row=1, column=2, padx=(8, 0), pady=(4, 0))

        ttk.Label(header, text="Proveedor:").grid(
            row=2, column=0, sticky="w", padx=(0, 6), pady=(4, 0)
        )
        self.lbl_ai_provider = ttk.Label(
            header,
            text="Buscando configuración de OpenCode...",
            anchor="w",
        )
        self.lbl_ai_provider.grid(
            row=2, column=1, sticky="ew", pady=(4, 0)
        )
        self.btn_ai_reload = ttk.Button(
            header,
            text="Recargar configuración",
            command=self._reload_ai_provider,
        )
        self.btn_ai_reload.grid(
            row=2, column=2, sticky="e", padx=(8, 0), pady=(4, 0)
        )

        ttk.Label(header, text="Modelo:").grid(
            row=3, column=0, sticky="w", padx=(0, 6), pady=(4, 0)
        )
        self.lbl_ai_model = ttk.Label(
            header, text="lab-coder", anchor="w"
        )
        self.lbl_ai_model.grid(
            row=3, column=1, sticky="ew", pady=(4, 0)
        )

        ttk.Label(header, text="OpenCode:").grid(
            row=4, column=0, sticky="w", padx=(0, 6), pady=(4, 0)
        )
        self.lbl_ai_config = ttk.Label(
            header, text="No cargado", anchor="w"
        )
        self.lbl_ai_config.grid(
            row=4, column=1, columnspan=2, sticky="ew", pady=(4, 0)
        )

        ttk.Label(header, text="Medicinas conocidas:").grid(
            row=5, column=0, sticky="w", padx=(0, 6), pady=(4, 0)
        )
        self.lbl_ai_knowledge = ttk.Label(
            header,
            text=f"0 conocidas — {knowledge_root()}",
            anchor="w",
        )
        self.lbl_ai_knowledge.grid(
            row=5, column=1, sticky="ew", pady=(4, 0)
        )
        self.btn_ai_knowledge = ttk.Button(
            header,
            text="Ver medicinas",
            command=self._open_knowledge_window,
        )
        self.btn_ai_knowledge.grid(
            row=5, column=2, sticky="e", padx=(8, 0), pady=(4, 0)
        )

        ttk.Label(header, text="Parches concretos:").grid(
            row=6, column=0, sticky="w", padx=(0, 6), pady=(4, 0)
        )
        self.lbl_ai_library = ttk.Label(
            header,
            text=f"0 compatibles — {biblioteca_por_defecto()}",
            anchor="w",
        )
        self.lbl_ai_library.grid(
            row=6, column=1, sticky="ew", pady=(4, 0)
        )
        self.btn_ai_library = ttk.Button(
            header,
            text="Ver parches exactos",
            command=self._open_recipe_library_window,
        )
        self.btn_ai_library.grid(
            row=6, column=2, sticky="e", padx=(8, 0), pady=(4, 0)
        )

        buttons = ttk.Frame(outer)
        buttons.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        buttons.columnconfigure(2, weight=1)
        buttons.columnconfigure(3, weight=1)

        self.btn_ai_generate = ttk.Button(
            buttons,
            text="Generar 3 recetas con Gemma",
            command=self._generate_ai_recipes,
        )
        self.btn_ai_generate.grid(row=0, column=0, sticky="ew", padx=3)

        self.btn_ai_apply = ttk.Button(
            buttons,
            text="Aplicar receta seleccionada",
            command=self._apply_ai_recipe,
        )
        self.btn_ai_apply.grid(row=0, column=1, sticky="ew", padx=3)

        self.btn_ai_save = ttk.Button(
            buttons,
            text="Guardar propuesta en perfil",
            command=self._save_ai_recipe_to_profile,
        )
        self.btn_ai_save.grid(row=0, column=2, sticky="ew", padx=3)

        self.btn_ai_window = ttk.Button(
            buttons,
            text="Ver propuestas en ventana",
            command=self._open_ai_proposals_window,
        )
        self.btn_ai_window.grid(row=0, column=3, sticky="ew", padx=3)

        orient = tk.VERTICAL if self.compact_mode else tk.HORIZONTAL
        pane = tk.PanedWindow(
            outer,
            orient=orient,
            sashwidth=6,
            relief="flat",
            bd=0,
        )
        pane.grid(row=2, column=0, sticky="nsew")

        left = ttk.Frame(pane, padding=4)
        right = ttk.Frame(pane, padding=4)
        pane.add(left, minsize=280, stretch="always")
        pane.add(right, minsize=360, stretch="always")

        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        ttk.Label(
            left,
            text="Tres alternativas: mínima, estructural y alternativa",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        columns = ("id", "enfoque", "riesgo", "titulo")
        self.ai_table = ttk.Treeview(
            left, columns=columns, show="headings", height=8
        )
        for col, title, width in (
            ("id", "ID", 55),
            ("enfoque", "Enfoque", 95),
            ("riesgo", "Riesgo", 70),
            ("titulo", "Título", 240),
        ):
            self.ai_table.heading(col, text=title)
            self.ai_table.column(col, width=width, anchor="w")
        self.ai_table.grid(row=1, column=0, sticky="nsew")
        self.ai_table.bind(
            "<<TreeviewSelect>>", self._on_ai_proposal_selected
        )

        ai_scroll = ttk.Scrollbar(
            left, orient="vertical", command=self.ai_table.yview
        )
        self.ai_table.configure(yscrollcommand=ai_scroll.set)
        ai_scroll.grid(row=1, column=1, sticky="ns")

        ttk.Label(
            right,
            text="Detalle y vista previa del diff",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.ai_detail_text = tk.Text(
            right, wrap="none", font=("Consolas", 10)
        )
        yscroll = ttk.Scrollbar(
            right, orient="vertical", command=self.ai_detail_text.yview
        )
        xscroll = ttk.Scrollbar(
            right, orient="horizontal", command=self.ai_detail_text.xview
        )
        self.ai_detail_text.configure(
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
        )
        self.ai_detail_text.grid(row=1, column=0, sticky="nsew")
        yscroll.grid(row=1, column=1, sticky="ns")
        xscroll.grid(row=2, column=0, sticky="ew")

        self._reload_ai_provider(silent=True)
        self._refresh_ai_state()

    def _reload_ai_provider(self, silent: bool = False):
        try:
            self.ai_provider = cargar_configuracion_opencode()
            self.lbl_ai_provider.configure(
                text=(
                    f"{self.ai_provider.provider_name} "
                    f"({self.ai_provider.provider_id})"
                )
            )
            self.lbl_ai_model.configure(
                text=(
                    f"{self.ai_provider.model_name} "
                    f"[{self.ai_provider.model_id}]"
                )
            )
            self.lbl_ai_config.configure(
                text=self.ai_provider.config_path
            )
            if not silent:
                messagebox.showinfo(
                    "Gemma configurada",
                    (
                        f"Proveedor: {self.ai_provider.provider_name}\n"
                        f"Modelo: {self.ai_provider.model_name}\n"
                        f"ID: {self.ai_provider.model_id}"
                    ),
                )
        except Exception as exc:
            self.ai_provider = None
            self.lbl_ai_provider.configure(
                text="Configuración no disponible"
            )
            self.lbl_ai_model.configure(text="lab-coder")
            self.lbl_ai_config.configure(text=str(exc))
            if not silent:
                messagebox.showerror(
                    "Configuración de Gemma",
                    str(exc),
                )
        self._refresh_ai_state()


    def _refresh_ai_state(self):
        if not hasattr(self, "btn_ai_generate"):
            return

        has_control = bool(self._selected_control())
        has_target = self.target_root is not None
        has_source = bool(self.ai_source_relative)
        has_proposal = self.ai_current_recipe is not None
        has_provider = self.ai_provider is not None
        enabled = lambda ok: "normal" if ok and not self.busy else "disabled"

        self.btn_ai_generate.configure(
            state=enabled(
                has_control and has_target and has_source and has_provider
            )
        )
        self.btn_ai_apply.configure(
            state=enabled(has_proposal and has_target)
        )
        self.btn_ai_save.configure(
            state=enabled(has_proposal and self.config_path is not None)
        )
        if hasattr(self, "btn_ai_window"):
            self.btn_ai_window.configure(
                state=enabled(bool(self.ai_proposals))
            )
        if hasattr(self, "btn_ai_open"):
            self.btn_ai_open.configure(
                state=enabled(has_control and has_target)
            )
        if hasattr(self, "btn_ai_reload"):
            self.btn_ai_reload.configure(
                state=enabled(True)
            )
        if hasattr(self, "btn_ai_library"):
            self.btn_ai_library.configure(
                state=enabled(bool(self.ai_library_candidates))
            )
        if hasattr(self, "btn_ai_knowledge"):
            self.btn_ai_knowledge.configure(
                state=enabled(bool(self.ai_knowledge_candidates))
            )


    def _ai_sync_selected_control(self):
        if not hasattr(self, "lbl_ai_control"):
            return

        control = self._selected_control()
        self.lbl_ai_control.configure(text=control or "Ninguno")
        self.ai_current_recipe = None
        self.ai_proposals = []
        self.ai_session_dir = None
        self.ai_library_candidates = []
        self.ai_selected_library_candidate = None
        self.ai_knowledge_candidates = []
        self.ai_active_knowledge_candidate = None
        self._close_ai_proposals_window()
        self._close_recipe_library_window()
        self._close_knowledge_window()

        for item in self.ai_table.get_children():
            self.ai_table.delete(item)
        self.ai_detail_text.delete("1.0", "end")

        if self.cfg and control and self.target_root:
            row = (
                self._selected_row_data()
                if hasattr(self, "_selected_row_data")
                else None
            ) or {}
            resolution = resolver_archivo_fuente(
                self.cfg,
                self.target_root,
                control_id=control,
                metodo=row.get("metodo"),
                ruta=row.get("ruta"),
                descripcion=row.get("control"),
            )

            if (
                resolution.archivo
                and (self.target_root / resolution.archivo).exists()
            ):
                self.ai_source_relative = resolution.archivo
                self.lbl_ai_source.configure(
                    text=(
                        f"{resolution.archivo}  "
                        f"[auto: {resolution.confianza}; {resolution.origen}]"
                    )
                )
                self._log(
                    "Archivo IA detectado automáticamente para "
                    f"{control}: {resolution.archivo} "
                    f"(confianza {resolution.confianza})"
                )
                self._refresh_recipe_library()
            else:
                self.ai_source_relative = None
                self.lbl_ai_source.configure(
                    text=(
                        "No fue posible resolver el archivo automáticamente; "
                        "puede seleccionarlo manualmente."
                    )
                )
        else:
            self.ai_source_relative = None
            self.lbl_ai_source.configure(text="No seleccionado")

        self._refresh_ai_state()

    def _open_ai_for_selected(self):
        if not self._selected_control():
            messagebox.showinfo(
                "Asistente IA",
                "Selecciona primero un hallazgo en la pestaña Resultados.",
            )
            return
        if not self.target_root:
            messagebox.showinfo(
                "Asistente IA",
                "Selecciona primero la carpeta de código local.",
            )
            return

        self._ai_sync_selected_control()
        self.notebook.select(self.tab_ai)

    def _choose_ai_source(self):
        if not self.target_root:
            messagebox.showinfo(
                "Asistente IA",
                "Selecciona primero la carpeta de código local.",
            )
            return

        path = filedialog.askopenfilename(
            title="Archivo de código a analizar con IA",
            initialdir=str(self.target_root),
        )
        if not path:
            return

        root = self.target_root.resolve()
        selected = Path(path).resolve()
        if selected != root and root not in selected.parents:
            messagebox.showerror(
                "Archivo no válido",
                "El archivo debe estar dentro de la carpeta de código local.",
            )
            return

        self.ai_source_relative = selected.relative_to(root).as_posix()
        self.lbl_ai_source.configure(
            text=f"{self.ai_source_relative}  [selección manual]"
        )
        self._log(
            f"Archivo IA seleccionado manualmente: {self.ai_source_relative}"
        )
        self._refresh_recipe_library()
        self._refresh_ai_state()

    def _close_knowledge_window(self):
        window = getattr(self, "ai_knowledge_window", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    window.destroy()
            except tk.TclError:
                pass
        self.ai_knowledge_window = None

    def _selected_knowledge_candidate(self):
        table = getattr(self, "ai_knowledge_table", None)
        if table is None:
            return self.ai_active_knowledge_candidate
        selected = table.selection()
        if not selected:
            return self.ai_active_knowledge_candidate
        try:
            index = int(selected[0])
        except (TypeError, ValueError):
            return None
        if index < 0 or index >= len(self.ai_knowledge_candidates):
            return None
        return self.ai_knowledge_candidates[index]

    def _render_knowledge_candidate(self, _event=None):
        candidate = self._selected_knowledge_candidate()
        if candidate is None:
            return
        text = getattr(self, "ai_knowledge_detail", None)
        if text is None:
            return
        payload = {
            "knowledge_id": candidate.knowledge.knowledge_id,
            "titulo": candidate.knowledge.titulo,
            "afinidad": candidate.score,
            "razones": candidate.razones,
            "causa_raiz": candidate.knowledge.causa_raiz,
            "invariante_seguridad": (
                candidate.knowledge.invariante_seguridad
            ),
            "estrategia_general": (
                candidate.knowledge.estrategia_general
            ),
            "señales_aplicabilidad": (
                candidate.knowledge.señales_aplicabilidad
            ),
            "requisitos_implementacion": (
                candidate.knowledge.requisitos_implementacion
            ),
            "anti_patrones": candidate.knowledge.anti_patrones,
            "contrato_verificacion": (
                candidate.knowledge.contrato_verificacion
            ),
            "casos_exitosos": candidate.knowledge.casos_exitosos,
            "usos_exitosos": candidate.knowledge.usos_exitosos,
        }
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert(
            "1.0",
            json.dumps(payload, ensure_ascii=False, indent=2),
        )
        text.configure(state="disabled")

    def _open_knowledge_window(self):
        if not self.ai_knowledge_candidates:
            messagebox.showinfo(
                "Medicinas conocidas",
                "No hay conocimiento correctivo verificado para este control.",
            )
            return

        old = getattr(self, "ai_knowledge_window", None)
        if old is not None:
            try:
                if old.winfo_exists():
                    old.lift()
                    old.focus_force()
                    return
            except tk.TclError:
                pass

        window = tk.Toplevel(self)
        self.ai_knowledge_window = window
        window.title("Medicinas correctivas reutilizables")
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        width = max(780, min(1300, screen_w - 100))
        height = max(560, min(820, screen_h - 140))
        window.geometry(f"{width}x{height}")
        window.minsize(min(780, width), min(560, height))
        window.protocol("WM_DELETE_WINDOW", self._close_knowledge_window)

        outer = ttk.Frame(window, padding=10)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        ttk.Label(
            outer,
            text=(
                "Estas medicinas describen la solución de seguridad, no un "
                "parche literal. Gemma las adapta al código actual."
            ),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        pane = tk.PanedWindow(
            outer,
            orient=tk.HORIZONTAL,
            sashwidth=6,
            relief="flat",
            bd=0,
        )
        pane.grid(row=1, column=0, sticky="nsew")

        left = ttk.Frame(pane, padding=4)
        right = ttk.Frame(pane, padding=4)
        pane.add(left, minsize=340, stretch="always")
        pane.add(right, minsize=440, stretch="always")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        table = ttk.Treeview(
            left,
            columns=("score", "casos", "titulo"),
            show="headings",
        )
        self.ai_knowledge_table = table
        table.heading("score", text="Afinidad")
        table.heading("casos", text="Éxitos")
        table.heading("titulo", text="Medicina")
        table.column("score", width=75, anchor="center")
        table.column("casos", width=65, anchor="center")
        table.column("titulo", width=250, anchor="w")
        table.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(
            left, orient="vertical", command=table.yview
        )
        table.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")

        for index, candidate in enumerate(self.ai_knowledge_candidates):
            table.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    candidate.score,
                    candidate.knowledge.usos_exitosos
                    or candidate.knowledge.casos_exitosos,
                    candidate.knowledge.titulo,
                ),
            )

        detail = tk.Text(
            right,
            wrap="none",
            font=("Consolas", 10),
        )
        self.ai_knowledge_detail = detail
        sy = ttk.Scrollbar(
            right, orient="vertical", command=detail.yview
        )
        sx = ttk.Scrollbar(
            right, orient="horizontal", command=detail.xview
        )
        detail.configure(
            yscrollcommand=sy.set,
            xscrollcommand=sx.set,
        )
        detail.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        detail.configure(state="disabled")

        footer = ttk.Frame(outer)
        footer.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            footer,
            text="Adaptar esta medicina al aplicativo",
            command=self._adapt_selected_knowledge,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            footer,
            text="Cerrar",
            command=self._close_knowledge_window,
        ).pack(side="right")

        table.bind(
            "<<TreeviewSelect>>",
            self._render_knowledge_candidate,
        )
        table.selection_set("0")
        table.focus("0")
        self._render_knowledge_candidate()

        window.transient(self)
        window.lift()
        window.focus_force()

    def _adapt_selected_knowledge(self):
        candidate = self._selected_knowledge_candidate()
        if candidate is None:
            return
        self.ai_active_knowledge_candidate = candidate
        self._close_knowledge_window()
        self._generate_ai_recipes(
            conocimiento=candidate
        )

    def _close_recipe_library_window(self):
        window = getattr(self, "ai_library_window", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    window.destroy()
            except tk.TclError:
                pass
        self.ai_library_window = None
        self.ai_selected_library_candidate = None

    def _refresh_recipe_library(self):
        self.ai_library_candidates = []
        self.ai_selected_library_candidate = None
        self.ai_knowledge_candidates = []
        self.ai_active_knowledge_candidate = None

        if (
            not self.cfg
            or not self.target_root
            or not self.ai_source_relative
            or not self._selected_control()
        ):
            if hasattr(self, "lbl_ai_library"):
                self.lbl_ai_library.configure(
                    text=f"0 compatibles — {biblioteca_por_defecto()}"
                )
            if hasattr(self, "lbl_ai_knowledge"):
                self.lbl_ai_knowledge.configure(
                    text=f"0 conocidas — {knowledge_root()}"
                )
            return

        row = (
            self._selected_row_data()
            if hasattr(self, "_selected_row_data")
            else None
        ) or {}
        source_path = self.target_root / self.ai_source_relative
        try:
            source_text = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            source_text = ""

        self.ai_knowledge_candidates = buscar_conocimiento(
            control_id=self._selected_control(),
            descripcion=row.get("control"),
            tipo_control=row.get("tipo_control"),
            source_text=source_text,
            extension=source_path.suffix.lower(),
        )

        self.ai_library_candidates = buscar_recetas_compatibles(
            control_id=self._selected_control(),
            target_root=self.target_root,
            archivo=self.ai_source_relative,
            metodo=row.get("metodo"),
            ruta=row.get("ruta"),
        )

        if hasattr(self, "lbl_ai_knowledge"):
            self.lbl_ai_knowledge.configure(
                text=(
                    f"{len(self.ai_knowledge_candidates)} conocida(s) — "
                    f"{knowledge_root()}"
                )
            )

        if hasattr(self, "lbl_ai_library"):
            count = len(self.ai_library_candidates)
            verificadas = sum(
                candidate.verificada
                for candidate in self.ai_library_candidates
            )
            self.lbl_ai_library.configure(
                text=(
                    f"{count} exacto(s), {verificadas} verificado(s) — "
                    f"{biblioteca_por_defecto()}"
                )
            )

        if self.ai_knowledge_candidates:
            self._log(
                "Conocimiento correctivo: "
                f"{len(self.ai_knowledge_candidates)} medicina(s) "
                f"para {self._selected_control()}."
            )
        if self.ai_library_candidates:
            self._log(
                "Parches concretos: "
                f"{len(self.ai_library_candidates)} coincidencia(s) exacta(s) "
                f"para {self._selected_control()}."
            )
        self._refresh_ai_state()

    def _selected_library_candidate(self):
        window = getattr(self, "ai_library_window", None)
        table = getattr(self, "ai_library_table", None)
        if window is None or table is None:
            return self.ai_selected_library_candidate
        selected = table.selection()
        if not selected:
            return self.ai_selected_library_candidate
        try:
            index = int(selected[0])
        except (TypeError, ValueError):
            return None
        if index < 0 or index >= len(self.ai_library_candidates):
            return None
        return self.ai_library_candidates[index]

    def _render_library_candidate(self, _event=None):
        candidate = self._selected_library_candidate()
        if candidate is None:
            return

        self.ai_selected_library_candidate = candidate
        text = getattr(self, "ai_library_detail", None)
        if text is None:
            return

        payload = {
            "recipe_id": candidate.recipe_id,
            "titulo": candidate.titulo,
            "verificada": candidate.verificada,
            "score": candidate.score,
            "archivo_actual": candidate.correccion.archivo,
            "descripcion": candidate.correccion.descripcion,
            "requiere_reinicio": candidate.correccion.requiere_reinicio,
            "operaciones": candidate.correccion.operaciones,
            "codigo_resultante": candidate.preview.get("codigo_despues"),
            "diff": candidate.preview.get("diff"),
            "origenes": candidate.metadata.get("origenes", []),
            "estadisticas": candidate.metadata.get("estadisticas", {}),
        }

        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert(
            "1.0",
            json.dumps(payload, ensure_ascii=False, indent=2),
        )
        text.configure(state="disabled")

    def _open_recipe_library_window(self):
        if not self.ai_library_candidates:
            messagebox.showinfo(
                "Biblioteca de recetas",
                "No hay recetas guardadas que pasen el preview para este archivo.",
            )
            return

        old = getattr(self, "ai_library_window", None)
        if old is not None:
            try:
                if old.winfo_exists():
                    old.lift()
                    old.focus_force()
                    return
            except tk.TclError:
                pass

        window = tk.Toplevel(self)
        self.ai_library_window = window
        window.title("Biblioteca de recetas reutilizables")
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        width = max(760, min(1300, screen_w - 100))
        height = max(560, min(820, screen_h - 140))
        window.geometry(f"{width}x{height}")
        window.minsize(min(760, width), min(560, height))
        window.protocol("WM_DELETE_WINDOW", self._close_recipe_library_window)

        outer = ttk.Frame(window, padding=10)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        ttk.Label(
            outer,
            text=(
                f"Control: {self._selected_control()}   |   "
                f"Archivo actual: {self.ai_source_relative}"
            ),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        pane = tk.PanedWindow(
            outer,
            orient=tk.HORIZONTAL,
            sashwidth=6,
            relief="flat",
            bd=0,
        )
        pane.grid(row=1, column=0, sticky="nsew")

        left = ttk.Frame(pane, padding=4)
        right = ttk.Frame(pane, padding=4)
        pane.add(left, minsize=340, stretch="always")
        pane.add(right, minsize=440, stretch="always")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        columns = ("verificada", "score", "titulo")
        table = ttk.Treeview(
            left,
            columns=columns,
            show="headings",
        )
        self.ai_library_table = table
        table.heading("verificada", text="Validada")
        table.heading("score", text="Afinidad")
        table.heading("titulo", text="Receta")
        table.column("verificada", width=75, anchor="center")
        table.column("score", width=70, anchor="center")
        table.column("titulo", width=240, anchor="w")
        table.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(
            left, orient="vertical", command=table.yview
        )
        table.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")

        for index, candidate in enumerate(self.ai_library_candidates):
            table.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    "Sí" if candidate.verificada else "No",
                    candidate.score,
                    candidate.titulo,
                ),
            )

        detail = tk.Text(
            right,
            wrap="none",
            font=("Consolas", 10),
        )
        self.ai_library_detail = detail
        sy = ttk.Scrollbar(
            right, orient="vertical", command=detail.yview
        )
        sx = ttk.Scrollbar(
            right, orient="horizontal", command=detail.xview
        )
        detail.configure(
            yscrollcommand=sy.set,
            xscrollcommand=sx.set,
        )
        detail.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        detail.configure(state="disabled")

        footer = ttk.Frame(outer)
        footer.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            footer,
            text="Aplicar receta reutilizable",
            command=self._apply_library_recipe,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            footer,
            text="Guardar esta receta en el perfil",
            command=self._save_library_recipe_to_profile,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            footer,
            text="Cerrar",
            command=self._close_recipe_library_window,
        ).pack(side="right")

        table.bind(
            "<<TreeviewSelect>>",
            self._render_library_candidate,
        )
        table.selection_set("0")
        table.focus("0")
        self.ai_selected_library_candidate = self.ai_library_candidates[0]
        self._render_library_candidate()

        window.transient(self)
        window.lift()
        window.focus_force()

    def _replace_recipe_in_memory(self, correccion):
        control = correccion.control_id
        self.cfg.correcciones = [
            item
            for item in self.cfg.correcciones
            if item.control_id != control
        ]
        self.cfg.correcciones.append(correccion)

    def _write_recipe_to_profile(self, correccion):
        if not self.config_path:
            raise RuntimeError("No hay perfil seleccionado.")

        raw_text = self.config_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        corrections = [
            item
            for item in data.get("correcciones", [])
            if item.get("control_id") != correccion.control_id
        ]
        corrections.append(asdict(correccion))
        data["correcciones"] = corrections
        self.config_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self._replace_recipe_in_memory(correccion)
        return raw_text, data

    def _apply_library_recipe(self):
        candidate = self._selected_library_candidate()
        if (
            candidate is None
            or not self.cfg
            or not self.target_root
        ):
            return

        control = candidate.correccion.control_id
        if not messagebox.askyesno(
            "Aplicar receta reutilizable",
            (
                f"Control: {control}\n"
                f"Receta: {candidate.titulo}\n"
                f"Verificada previamente: "
                f"{'Sí' if candidate.verificada else 'No'}\n\n"
                "Esta receta pasó el preview sobre el archivo actual. "
                "El auditor realizará backup, aplicación, verificación y "
                "rollback si corresponde.\n\n¿Deseas continuar?"
            ),
        ):
            return

        self._replace_recipe_in_memory(candidate.correccion)

        def task():
            reiniciar = self._prepare_restart_callback([control])
            selector = (
                self._selected_selector()
                if hasattr(self, "_selected_selector")
                else None
            )
            result = ciclo_correctivo(
                self.cfg,
                control,
                self.target_root,
                evidence_base=self.evidence_base,
                reiniciar=reiniciar,
                selector=selector,
            )
            marcar_uso_receta(
                candidate.path,
                exitoso=result.get("estado_final") == "CORREGIDO",
            )
            return result

        def done(result):
            estado = result.get("estado_final")
            self._log(
                f"Biblioteca: receta {candidate.recipe_id[:12]} "
                f"aplicada a {control}: {estado}"
            )
            messagebox.showinfo(
                "Resultado de receta reutilizable",
                f"{control}: {estado}",
            )
            self._close_recipe_library_window()
            self._diagnose()

        self._run_background(
            task,
            done,
            "Aplicando receta reutilizable…",
        )

    def _save_library_recipe_to_profile(self):
        candidate = self._selected_library_candidate()
        if candidate is None or not self.config_path or not self.cfg:
            return

        if not messagebox.askyesno(
            "Guardar receta en perfil",
            (
                f"Se añadirá la receta '{candidate.titulo}' al perfil "
                f"{self.config_path.name}.\n\n¿Continuar?"
            ),
        ):
            return

        self._write_recipe_to_profile(candidate.correccion)
        self._log(
            f"Biblioteca: receta {candidate.recipe_id[:12]} "
            f"guardada en perfil para {candidate.correccion.control_id}."
        )
        messagebox.showinfo(
            "Perfil actualizado",
            "La receta reutilizable quedó guardada en el perfil actual.",
        )
        self._refresh_state()

    def _ai_selected_metadata(self) -> dict:
        row = (
            self._selected_row_data()
            if hasattr(self, "_selected_row_data")
            else None
        ) or {}
        values = self._selected_values() or ()
        return {
            "control_id": row.get("id") or (str(values[1]) if len(values) > 1 else None),
            "descripcion": row.get("control") or (
                str(values[2]) if len(values) > 2 else None
            ),
            "cuenta": row.get("cuenta") or (
                str(values[3]) if len(values) > 3 else None
            ),
            "estado": row.get("estado") or (
                str(values[4]) if len(values) > 4 else None
            ),
            "detalle": row.get("detalle") or (
                str(values[6]) if len(values) > 6 else None
            ),
            "metodo": row.get("metodo"),
            "ruta": row.get("ruta"),
            "tipo_control": row.get("tipo_control"),
        }

    def _ai_test_matrix(self) -> list[dict]:
        control = self._selected_control()
        if not control:
            return []
        rows = getattr(self, "result_rows", {}) or {}
        matrix: list[dict] = []
        for row in rows.values():
            if row.get("id") != control:
                continue
            matrix.append(
                {
                    "cuenta": row.get("cuenta"),
                    "metodo": row.get("metodo"),
                    "ruta": row.get("ruta"),
                    "tipo_control": row.get("tipo_control"),
                    "estado": row.get("estado"),
                    "detalle": row.get("detalle"),
                    "descripcion": row.get("control"),
                }
            )
        return matrix

    def _current_finding_data(self) -> tuple[str, str, str]:
        values = self._selected_values()
        if not values:
            raise RuntimeError("No hay un hallazgo seleccionado.")
        return str(values[1]), str(values[2]), str(values[6])

    def _generate_ai_recipes(
        self,
        intento_anterior: dict | None = None,
        conocimiento: KnowledgeCandidate | None = None,
    ):
        if (
            not self.cfg
            or not self.target_root
            or not self.ai_source_relative
        ):
            return

        if not self.ai_provider:
            self._reload_ai_provider()
            if not self.ai_provider:
                return

        control, descripcion, detalle = self._current_finding_data()
        metadata = self._ai_selected_metadata()
        matriz = self._ai_test_matrix()
        source_path = self.target_root / self.ai_source_relative
        provider = self.ai_provider

        if (
            conocimiento is None
            and intento_anterior is None
            and self.ai_knowledge_candidates
        ):
            conocimiento = self.ai_knowledge_candidates[0]
            self._log(
                "Se reutilizará automáticamente la medicina con mayor "
                f"afinidad: {conocimiento.knowledge.titulo} "
                f"(score {conocimiento.score})."
            )

        if conocimiento is not None:
            self.ai_active_knowledge_candidate = conocimiento
        elif intento_anterior is None:
            self.ai_active_knowledge_candidate = None

        active_knowledge = self.ai_active_knowledge_candidate
        knowledge_payload = (
            asdict(active_knowledge.knowledge)
            if active_knowledge is not None
            else None
        )
        self._close_ai_proposals_window()

        def task():
            source_text = source_path.read_text(encoding="utf-8")
            proposals, context, used_provider = generar_tres_recetas(
                self.cfg,
                control_id=control,
                descripcion=descripcion,
                detalle=detalle,
                source_relative=self.ai_source_relative,
                source_text=source_text,
                provider=provider,
                metadata_hallazgo=metadata,
                matriz_pruebas=matriz,
                intento_anterior=intento_anterior,
                conocimiento_reutilizable=knowledge_payload,
            )
            session = guardar_sesion_ia(
                self.evidence_base,
                contexto=context,
                propuestas=proposals,
                provider=used_provider,
            )
            return proposals, session

        def done(payload):
            proposals, session = payload
            self.ai_proposals = proposals
            self.ai_session_dir = session
            self.ai_current_recipe = None

            for item in self.ai_table.get_children():
                self.ai_table.delete(item)

            for index, proposal in enumerate(proposals):
                self.ai_table.insert(
                    "",
                    "end",
                    iid=str(index),
                    values=(
                        proposal.id,
                        proposal.enfoque,
                        proposal.riesgo,
                        proposal.titulo,
                    ),
                )

            if active_knowledge is not None:
                ronda = (
                    "adaptadas desde medicina conocida "
                    f"{active_knowledge.knowledge.knowledge_id[:12]}"
                )
            elif intento_anterior:
                ronda = "reformuladas"
            else:
                ronda = "generadas desde cero"
            self._log(
                f"Gemma: 3 propuestas {ronda} para {control}. "
                f"Evidencia: {session}"
            )
            self.notebook.select(self.tab_ai)
            self.ai_table.selection_set("0")
            self.ai_table.focus("0")
            self._on_ai_proposal_selected()
            self._refresh_ai_state()
            self._open_ai_proposals_window()

        self._run_background(
            task,
            done,
            f"Generando 3 recetas con Gemma para {control}…",
        )

    def _selected_ai_proposal(self) -> AIRecipeProposal | None:
        selected = self.ai_table.selection()
        if not selected:
            return None
        try:
            index = int(selected[0])
        except (TypeError, ValueError):
            return None
        if index < 0 or index >= len(self.ai_proposals):
            return None
        return self.ai_proposals[index]

    def _on_ai_proposal_selected(self, _event=None):
        proposal = self._selected_ai_proposal()
        self.ai_detail_text.delete("1.0", "end")
        self.ai_current_recipe = None

        if (
            proposal is None
            or not self.cfg
            or not self.target_root
            or not self.ai_source_relative
        ):
            self._refresh_ai_state()
            return

        control = self._selected_control()
        if not control:
            self._refresh_ai_state()
            return

        recipe = propuesta_a_correccion(
            proposal,
            control_id=control,
            source_relative=self.ai_source_relative,
        )

        detail = {
            "propuesta": proposal.as_dict(),
            "receta_normalizada": asdict(recipe),
        }

        try:
            preview = preview_recipe(recipe, self.target_root)
            detail["preview"] = preview
            if preview["cambia_archivo"]:
                self.ai_current_recipe = recipe
            else:
                detail["advertencia"] = (
                    "La propuesta no cambia el archivo actual."
                )
        except Exception as exc:
            detail["preview_error"] = str(exc)

        self.ai_detail_text.insert(
            "1.0",
            json.dumps(detail, ensure_ascii=False, indent=2),
        )
        self._refresh_ai_state()

    def _close_ai_proposals_window(self):
        window = getattr(self, "ai_proposals_window", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    window.destroy()
            except tk.TclError:
                pass
        self.ai_proposals_window = None
        self.ai_proposals_notebook = None

    def _select_ai_proposal_index(self, index: int):
        if index < 0 or index >= len(self.ai_proposals):
            return
        iid = str(index)
        if iid in self.ai_table.get_children():
            self.ai_table.selection_set(iid)
            self.ai_table.focus(iid)
            self.ai_table.see(iid)
        self._on_ai_proposal_selected()

    def _copy_to_clipboard(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()

    def _proposal_preview_data(self, index: int) -> dict:
        proposal = self.ai_proposals[index]
        control = self._selected_control()
        if (
            not control
            or not self.target_root
            or not self.ai_source_relative
        ):
            return {
                "proposal": proposal,
                "recipe": None,
                "preview": None,
                "error": "No hay contexto suficiente para previsualizar.",
            }

        recipe = propuesta_a_correccion(
            proposal,
            control_id=control,
            source_relative=self.ai_source_relative,
        )
        try:
            preview = preview_recipe(recipe, self.target_root)
            error = None
        except Exception as exc:
            preview = None
            error = str(exc)

        return {
            "proposal": proposal,
            "recipe": recipe,
            "preview": preview,
            "error": error,
        }

    def _open_ai_proposals_window(self):
        if not self.ai_proposals:
            messagebox.showinfo(
                "Propuestas Gemma",
                "Primero genera las tres recetas con Gemma.",
            )
            return

        old = getattr(self, "ai_proposals_window", None)
        if old is not None:
            try:
                if old.winfo_exists():
                    old.lift()
                    old.focus_force()
                    return
            except tk.TclError:
                pass

        window = tk.Toplevel(self)
        self.ai_proposals_window = window
        window.title("Propuestas de corrección — Gemma / Laboratorio UTB")

        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        width = max(720, min(1500, screen_w - 80))
        height = max(560, min(900, screen_h - 120))
        window.geometry(f"{width}x{height}")
        window.minsize(min(820, width), min(600, height))
        window.protocol("WM_DELETE_WINDOW", self._close_ai_proposals_window)

        outer = ttk.Frame(window, padding=10)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(2, weight=1)
        outer.columnconfigure(0, weight=1)

        control = self._selected_control() or "-"
        ttk.Label(
            outer,
            text=(
                f"Control: {control}    |    "
                f"Archivo: {self.ai_source_relative or '-'}"
            ),
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        ttk.Label(
            outer,
            text=(
                "Compara las tres soluciones. Cambiar de pestaña selecciona "
                "esa receta también en la ventana principal."
            ),
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))

        notebook = ttk.Notebook(outer)
        self.ai_proposals_notebook = notebook
        notebook.grid(row=2, column=0, sticky="nsew")

        for index, proposal in enumerate(self.ai_proposals):
            data = self._proposal_preview_data(index)
            tab = ttk.Frame(notebook, padding=8)
            tab.rowconfigure(2, weight=1)
            tab.columnconfigure(0, weight=1)
            notebook.add(
                tab,
                text=f"{proposal.enfoque} — {proposal.id}",
            )

            summary = ttk.LabelFrame(
                tab,
                text=proposal.titulo,
                padding=8,
            )
            summary.grid(row=0, column=0, sticky="ew", pady=(0, 6))
            summary.columnconfigure(1, weight=1)

            ttk.Label(summary, text="Enfoque:").grid(
                row=0, column=0, sticky="nw", padx=(0, 8)
            )
            ttk.Label(summary, text=proposal.enfoque).grid(
                row=0, column=1, sticky="w"
            )
            ttk.Label(summary, text="Riesgo:").grid(
                row=0, column=2, sticky="nw", padx=(18, 8)
            )
            ttk.Label(summary, text=proposal.riesgo).grid(
                row=0, column=3, sticky="w"
            )
            ttk.Label(summary, text="Explicación:").grid(
                row=1, column=0, sticky="nw", padx=(0, 8), pady=(4, 0)
            )
            ttk.Label(
                summary,
                text=proposal.explicacion,
                wraplength=max(600, width - 340),
                justify="left",
            ).grid(
                row=1, column=1, columnspan=3, sticky="ew", pady=(4, 0)
            )
            ttk.Label(summary, text="Consideraciones:").grid(
                row=2, column=0, sticky="nw", padx=(0, 8), pady=(4, 0)
            )
            ttk.Label(
                summary,
                text=proposal.consideraciones,
                wraplength=max(600, width - 340),
                justify="left",
            ).grid(
                row=2, column=1, columnspan=3, sticky="ew", pady=(4, 0)
            )

            actions = ttk.Frame(tab)
            actions.grid(row=1, column=0, sticky="ew", pady=(0, 6))
            ttk.Button(
                actions,
                text="Seleccionar esta receta",
                command=lambda i=index: self._select_ai_proposal_index(i),
            ).pack(side="left", padx=(0, 6))
            code_result = (
                data["preview"].get("codigo_despues")
                if data["preview"] is not None
                else proposal.reemplazar
            )
            ttk.Button(
                actions,
                text="Copiar código resultante",
                command=lambda text=code_result: self._copy_to_clipboard(text),
            ).pack(side="left", padx=(0, 6))

            panes = tk.PanedWindow(
                tab,
                orient=tk.HORIZONTAL,
                sashwidth=6,
                relief="flat",
                bd=0,
            )
            panes.grid(row=2, column=0, sticky="nsew")

            code_frame = ttk.LabelFrame(
                panes, text="Código propuesto", padding=6
            )
            diff_frame = ttk.LabelFrame(
                panes, text="Diff / vista previa", padding=6
            )
            panes.add(code_frame, minsize=360, stretch="always")
            panes.add(diff_frame, minsize=420, stretch="always")

            for frame in (code_frame, diff_frame):
                frame.rowconfigure(0, weight=1)
                frame.columnconfigure(0, weight=1)

            code_text = tk.Text(
                code_frame,
                wrap="none",
                font=("Consolas", 10),
            )
            code_y = ttk.Scrollbar(
                code_frame,
                orient="vertical",
                command=code_text.yview,
            )
            code_x = ttk.Scrollbar(
                code_frame,
                orient="horizontal",
                command=code_text.xview,
            )
            code_text.configure(
                yscrollcommand=code_y.set,
                xscrollcommand=code_x.set,
            )
            code_text.grid(row=0, column=0, sticky="nsew")
            code_y.grid(row=0, column=1, sticky="ns")
            code_x.grid(row=1, column=0, sticky="ew")
            code_text.insert("1.0", code_result)
            code_text.configure(state="disabled")

            diff_text = tk.Text(
                diff_frame,
                wrap="none",
                font=("Consolas", 10),
            )
            diff_y = ttk.Scrollbar(
                diff_frame,
                orient="vertical",
                command=diff_text.yview,
            )
            diff_x = ttk.Scrollbar(
                diff_frame,
                orient="horizontal",
                command=diff_text.xview,
            )
            diff_text.configure(
                yscrollcommand=diff_y.set,
                xscrollcommand=diff_x.set,
            )
            diff_text.grid(row=0, column=0, sticky="nsew")
            diff_y.grid(row=0, column=1, sticky="ns")
            diff_x.grid(row=1, column=0, sticky="ew")

            if data["preview"] is not None:
                diff_content = data["preview"].get("diff") or (
                    "La propuesta es válida pero no produjo un diff visible."
                )
            else:
                diff_content = (
                    "PREVIEW NO DISPONIBLE\n\n"
                    + (data["error"] or "Error desconocido")
                    + "\n\n"
                    "Código propuesto por Gemma:\n"
                    + proposal.reemplazar
                )
            diff_text.insert("1.0", diff_content)
            diff_text.configure(state="disabled")

        footer = ttk.Frame(outer)
        footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            footer,
            text="Aplicar receta seleccionada",
            command=self._apply_ai_recipe,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            footer,
            text="Guardar receta en perfil + biblioteca",
            command=self._save_ai_recipe_to_profile,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            footer,
            text="Cerrar",
            command=self._close_ai_proposals_window,
        ).pack(side="right")

        def on_tab_changed(_event=None):
            current = notebook.index(notebook.select())
            self._select_ai_proposal_index(current)

        notebook.bind("<<NotebookTabChanged>>", on_tab_changed)

        selected = self.ai_table.selection()
        try:
            selected_index = int(selected[0]) if selected else 0
        except (TypeError, ValueError):
            selected_index = 0
        selected_index = max(0, min(selected_index, len(self.ai_proposals) - 1))
        notebook.select(selected_index)
        self._select_ai_proposal_index(selected_index)

        window.transient(self)
        window.lift()
        window.focus_force()

    def _install_ai_recipe_in_memory(self):
        proposal = self._selected_ai_proposal()
        control = self._selected_control()
        if not proposal or not control or not self.ai_current_recipe or not self.cfg:
            raise RuntimeError("No hay una receta IA válida seleccionada.")

        self.cfg.correcciones = [
            item
            for item in self.cfg.correcciones
            if item.control_id != control
        ]
        self.cfg.correcciones.append(self.ai_current_recipe)
        return proposal, control

    def _apply_ai_recipe(self):
        if not self.cfg or not self.target_root or not self.ai_current_recipe:
            return

        proposal = self._selected_ai_proposal()
        control = self._selected_control()
        if not proposal or not control:
            return

        row = (
            self._selected_row_data()
            if hasattr(self, "_selected_row_data")
            else None
        ) or {}
        _, descripcion, detalle = self._current_finding_data()
        metadata = self._ai_selected_metadata()
        matriz = self._ai_test_matrix()
        active_knowledge = self.ai_active_knowledge_candidate

        if not messagebox.askyesno(
            "Aplicar receta generada por Gemma",
            (
                f"Control: {control}\n"
                f"Propuesta: {proposal.titulo}\n"
                f"Enfoque: {proposal.enfoque}\n"
                f"Riesgo declarado: {proposal.riesgo}\n\n"
                "El auditor hará backup, aplicará la implementación y "
                "verificará la prueba exacta y sus regresiones. "
                "Si termina en CORREGIDO, conservará el parche concreto "
                "como evidencia y aprenderá/actualizará la medicina "
                "semántica reutilizable.\n\n"
                "¿Deseas continuar?"
            ),
        ):
            return

        def task():
            selected_proposal, selected_control = (
                self._install_ai_recipe_in_memory()
            )

            if self.ai_session_dir:
                guardar_seleccion_ia(
                    self.ai_session_dir,
                    propuesta=selected_proposal,
                    correccion=self.ai_current_recipe,
                )

            reiniciar = self._prepare_restart_callback([selected_control])
            selector = (
                self._selected_selector()
                if hasattr(self, "_selected_selector")
                else None
            )
            result = ciclo_correctivo(
                self.cfg,
                selected_control,
                self.target_root,
                evidence_base=self.evidence_base,
                reiniciar=reiniciar,
                selector=selector,
            )

            if self.ai_session_dir:
                guardar_seleccion_ia(
                    self.ai_session_dir,
                    propuesta=selected_proposal,
                    correccion=self.ai_current_recipe,
                    resultado=result,
                )

            estado = result.get("estado_final")
            source_rel = self.ai_current_recipe.archivo
            extension = Path(source_rel).suffix.lower()
            caso = {
                "sistema": self.cfg.sistema,
                "version": self.cfg.version_objetivo,
                "control_id": selected_control,
                "tipo_control": row.get("tipo_control"),
                "metodo": row.get("metodo"),
                "ruta": row.get("ruta"),
                "extension": extension,
                "enfoque": selected_proposal.enfoque,
            }

            if estado == "CORREGIDO":
                provider = self.ai_provider
                library_path = guardar_receta_biblioteca(
                    self.ai_current_recipe,
                    sistema=self.cfg.sistema,
                    version_objetivo=self.cfg.version_objetivo,
                    metodo=row.get("metodo"),
                    ruta=row.get("ruta"),
                    tipo_control=row.get("tipo_control"),
                    titulo=selected_proposal.titulo,
                    fuente="gemma",
                    proveedor=provider.provider_name if provider else None,
                    modelo=provider.model_id if provider else None,
                    verificada=True,
                )
                result["instancia_concreta"] = str(library_path)

                if active_knowledge is not None:
                    registrar_uso_conocimiento(
                        active_knowledge.path,
                        exitoso=True,
                        caso_exitoso=caso,
                    )
                    result["conocimiento_reutilizado"] = str(
                        active_knowledge.path
                    )
                else:
                    try:
                        correction_info = (
                            result.get("correccion_aplicada") or {}
                        )
                        backup = correction_info.get("backup")
                        archivo = correction_info.get(
                            "archivo",
                            source_rel,
                        )
                        if not backup:
                            raise RuntimeError(
                                "La evidencia no contiene el backup "
                                "necesario para generalizar la corrección."
                            )

                        codigo_antes = Path(backup).read_text(
                            encoding="utf-8"
                        )
                        codigo_despues = (
                            self.target_root / archivo
                        ).read_text(encoding="utf-8")
                        diff = correction_info.get("diff") or ""

                        knowledge, knowledge_context, _ = (
                            generalizar_correccion_exitosa(
                                self.cfg,
                                control_id=selected_control,
                                descripcion=descripcion,
                                detalle=detalle,
                                metadata_hallazgo=metadata,
                                matriz_pruebas=matriz,
                                source_relative=archivo,
                                codigo_antes=codigo_antes,
                                codigo_despues=codigo_despues,
                                diff=diff,
                                propuesta=selected_proposal,
                                provider=provider,
                            )
                        )
                        if (
                            extension
                            and extension
                            not in knowledge.lenguajes_observados
                        ):
                            knowledge.lenguajes_observados.append(
                                extension
                            )
                        knowledge_path = guardar_conocimiento(
                            knowledge,
                            caso_exitoso=caso,
                        )
                        result["conocimiento_aprendido"] = str(
                            knowledge_path
                        )

                        if self.ai_session_dir:
                            (
                                self.ai_session_dir
                                / "conocimiento_aprendido.json"
                            ).write_text(
                                json.dumps(
                                    {
                                        "path": str(knowledge_path),
                                        "knowledge": asdict(knowledge),
                                        "contexto_redactado": (
                                            knowledge_context
                                        ),
                                    },
                                    ensure_ascii=False,
                                    indent=2,
                                )
                                + "\n",
                                encoding="utf-8",
                            )
                    except Exception as exc:
                        # La corrección ya fue demostrada dinámicamente. Un
                        # fallo de la segunda llamada a Gemma no debe hacer que
                        # el Auditor pierda ese aprendizaje. Guardamos una
                        # medicina semántica mínima y verificada como respaldo.
                        try:
                            fallback = crear_conocimiento_respaldo_verificado(
                                control_id=selected_control,
                                descripcion=descripcion,
                                tipo_control=row.get("tipo_control"),
                                extension=extension,
                            )
                            fallback_path = guardar_conocimiento(
                                fallback,
                                caso_exitoso=caso,
                            )
                            result["conocimiento_aprendido"] = str(
                                fallback_path
                            )
                            result["conocimiento_fallback"] = str(exc)

                            if self.ai_session_dir:
                                (
                                    self.ai_session_dir
                                    / "conocimiento_aprendido.json"
                                ).write_text(
                                    json.dumps(
                                        {
                                            "path": str(fallback_path),
                                            "knowledge": asdict(fallback),
                                            "modo": "fallback_verificado",
                                            "motivo_fallback": str(exc),
                                        },
                                        ensure_ascii=False,
                                        indent=2,
                                    )
                                    + "\n",
                                    encoding="utf-8",
                                )
                        except Exception as fallback_exc:
                            result["conocimiento_error"] = (
                                "Falló la extracción semántica con IA: "
                                f"{exc}. También falló el guardado de respaldo: "
                                f"{fallback_exc}"
                            )
            elif active_knowledge is not None:
                try:
                    registrar_uso_conocimiento(
                        active_knowledge.path,
                        exitoso=False,
                    )
                except Exception:
                    pass

            return result

        def done(result):
            estado = result.get("estado_final")
            instance_path = result.get("instancia_concreta")
            knowledge_path = result.get("conocimiento_aprendido")
            reused_path = result.get("conocimiento_reutilizado")
            knowledge_error = result.get("conocimiento_error")
            knowledge_fallback = result.get("conocimiento_fallback")

            self._log(
                f"Receta Gemma {proposal.id} aplicada a {control}: {estado}"
            )
            if instance_path:
                self._log(
                    "Instancia concreta verificada guardada: "
                    f"{instance_path}"
                )
            if knowledge_path:
                self._log(
                    "Nueva medicina semántica aprendida: "
                    f"{knowledge_path}"
                )
            if reused_path:
                self._log(
                    "Medicina conocida validada también en este sistema: "
                    f"{reused_path}"
                )
            if knowledge_fallback:
                self._log(
                    "La corrección funcionó y se guardó una medicina "
                    "verificada de respaldo porque la extracción enriquecida "
                    f"con IA falló: {knowledge_fallback}"
                )
            if knowledge_error:
                self._log(
                    "La corrección funcionó, pero no se pudo "
                    f"guardar ninguna medicina: {knowledge_error}"
                )

            mensaje = f"{control}: {estado}"
            if knowledge_path:
                mensaje += (
                    "\n\nSe aprendió una medicina reutilizable en:\n"
                    f"{knowledge_path}"
                )
                if knowledge_fallback:
                    mensaje += (
                        "\n\nLa medicina se guardó en modo de respaldo "
                        "verificado porque la extracción semántica enriquecida "
                        "con IA no pudo completarse."
                    )
            elif reused_path:
                mensaje += (
                    "\n\nLa medicina conocida funcionó también en este "
                    "aplicativo y se actualizó su historial."
                )
            if knowledge_error:
                mensaje += (
                    "\n\nLa corrección sí fue válida, pero la extracción "
                    "del conocimiento reusable falló. El parche y la "
                    "evidencia se conservaron."
                )
            if estado == "NO_CORREGIDO":
                motivo = result.get("motivo") or (
                    "La verificación reprodujo nuevamente el hallazgo."
                )
                mensaje += f"\n\n{motivo}"

            messagebox.showinfo(
                "Resultado de receta Gemma",
                mensaje,
            )

            if estado == "NO_CORREGIDO":
                feedback = {
                    "propuesta_anterior": proposal.as_dict(),
                    "receta_anterior": asdict(self.ai_current_recipe),
                    "resultado": {
                        "estado_final": result.get("estado_final"),
                        "estado_despues": result.get("estado_despues"),
                        "estado_global_despues": result.get(
                            "estado_global_despues"
                        ),
                        "motivo": result.get("motivo"),
                        "regresiones": result.get("regresiones", []),
                    },
                    "correccion_aplicada": result.get(
                        "correccion_aplicada"
                    ),
                }
                if messagebox.askyesno(
                    "Reformular recetas",
                    (
                        "La implementación no solucionó el hallazgo y el "
                        "auditor hizo rollback.\n\n"
                        "¿Deseas generar 3 implementaciones nuevas usando "
                        "el fallo como retroalimentación?"
                    ),
                ):
                    self._generate_ai_recipes(
                        intento_anterior=feedback,
                        conocimiento=active_knowledge,
                    )
                    return

            self._refresh_recipe_library()
            self._diagnose()

        self._run_background(
            task,
            done,
            f"Aplicando receta Gemma {proposal.id}…",
        )

    def _save_ai_recipe_to_profile(self):
        if (
            not self.config_path
            or not self.cfg
            or not self.ai_current_recipe
        ):
            return

        proposal = self._selected_ai_proposal()
        control = self._selected_control()
        if not proposal or not control:
            return

        if not messagebox.askyesno(
            "Guardar propuesta en perfil",
            (
                f"Se guardará la propuesta {proposal.id} como receta "
                f"concreta de {control} únicamente en el perfil actual.\n\n"
                "La biblioteca de conocimiento reusable solo aprende una "
                "medicina después de que una implementación termina en "
                "CORREGIDO.\n\n"
                f"Perfil: {self.config_path}\n\n"
                "¿Continuar?"
            ),
        ):
            return

        raw_text, data = self._write_recipe_to_profile(
            self.ai_current_recipe
        )

        if self.ai_session_dir:
            (self.ai_session_dir / "perfil_antes.json").write_text(
                raw_text, encoding="utf-8"
            )
            (self.ai_session_dir / "perfil_despues.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        self._log(
            f"Propuesta Gemma {proposal.id} guardada en perfil para {control}."
        )
        messagebox.showinfo(
            "Perfil actualizado",
            (
                f"La propuesta de {control} quedó guardada en el perfil.\n\n"
                "Todavía no se considera conocimiento reusable: primero "
                "debe superar el ciclo correctivo y terminar en CORREGIDO."
            ),
        )
        self._refresh_ai_state()

