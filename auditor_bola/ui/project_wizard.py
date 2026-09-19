"""Asistente moderno para incorporar aplicaciones a Aegis Auditor."""

from __future__ import annotations

import json
import shlex
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from ..app_paths import default_config_dir
from ..profile_builder import (
    ProjectDetection,
    build_profile_draft,
    detect_project,
    save_profile_draft,
)
from ..responsive import calculate_wizard_geometry
from .components.cards import ActionButton, SectionCard
from .components.progress_steps import ProgressSteps
from .theme import COLORS, FONT_FAMILY, MONO_FAMILY


AUTH_TYPES = ("none", "basic", "bearer", "header")


class ModernProfileWizard(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        *,
        initial_project: str | Path | None = None,
        on_saved=None,
    ):
        super().__init__(master)
        self.title("Aegis Auditor — Nuevo proyecto")
        self.configure(fg_color=COLORS["bg"])

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width, height, compact = calculate_wizard_geometry(
            screen_w,
            screen_h,
        )
        self.geometry(f"{min(width, 1180)}x{min(height, 820)}")
        self.minsize(min(780, width), min(560, height))
        self.compact_mode = compact

        self.transient(master)
        self.grab_set()

        self.on_saved = on_saved
        self.project_root: Path | None = None
        self.detection: ProjectDetection | None = None
        self.profile: dict | None = None
        self.busy = False

        self.system_var = ctk.StringVar()
        self.version_var = ctk.StringVar(value="1.0.0")
        self.base_url_var = ctk.StringVar()
        self.mode_var = ctk.StringVar(value="process")
        self.start_var = ctk.StringVar()
        self.workdir_var = ctk.StringVar(value=".")
        self.auto_prepare_var = ctk.BooleanVar(value=False)

        self._build_ui()

        if initial_project:
            self.after(
                120,
                lambda: self._analyze_project(
                    Path(initial_project)
                ),
            )

    def _build_ui(self):
        header = ctk.CTkFrame(
            self,
            fg_color=COLORS["topbar"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        header.pack(fill="x", padx=18, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Incorporar aplicación",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 23, "bold"),
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=18,
            pady=(14, 2),
        )

        ctk.CTkLabel(
            header,
            text=(
                "Analiza el proyecto y construye un perfil operativo "
                "para Pilar 1 y Pilar 2."
            ),
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 10),
            anchor="w",
        ).grid(
            row=1,
            column=0,
            sticky="ew",
            padx=18,
            pady=(0, 14),
        )

        ActionButton(
            header,
            "Seleccionar aplicación",
            self._choose_project,
            "primary",
        ).grid(
            row=0,
            column=1,
            rowspan=2,
            padx=18,
            pady=14,
        )

        self.steps = ProgressSteps(self)
        self.steps.pack(
            fill="x",
            padx=26,
            pady=(2, 10),
        )
        self.steps.set_step(0)

        self.status_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS["surface"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        self.status_frame.pack(
            fill="x",
            padx=18,
            pady=(0, 10),
        )
        self.status_frame.grid_columnconfigure(0, weight=1)

        self.project_label = ctk.CTkLabel(
            self.status_frame,
            text="Selecciona una carpeta de aplicación para comenzar.",
            text_color=COLORS["muted"],
            anchor="w",
            font=(FONT_FAMILY, 10),
        )
        self.project_label.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=14,
            pady=10,
        )

        self.scan_progress = ctk.CTkProgressBar(
            self.status_frame,
            width=180,
            height=7,
            mode="indeterminate",
            fg_color="#183246",
            progress_color=COLORS["accent"],
        )
        self.scan_progress.grid(
            row=0,
            column=1,
            padx=14,
        )
        self.scan_progress.stop()
        self.scan_progress.set(0)

        self.tabs = ctk.CTkTabview(
            self,
            fg_color=COLORS["surface"],
            segmented_button_fg_color="#0A1A28",
            segmented_button_selected_color=COLORS["accent"],
            segmented_button_selected_hover_color=COLORS["accent_hover"],
            segmented_button_unselected_color="#0A1A28",
            segmented_button_unselected_hover_color="#12384F",
            text_color=COLORS["text"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border_soft"],
        )
        self.tabs.pack(
            fill="both",
            expand=True,
            padx=18,
            pady=(0, 10),
        )

        for name in (
            "Proyecto",
            "Runtime",
            "Pilar 1",
            "Pilar 2",
            "Perfil JSON",
        ):
            self.tabs.add(name)

        self._build_project_tab()
        self._build_runtime_tab()
        self._build_p1_tab()
        self._build_p2_tab()
        self._build_json_tab()

        footer = ctk.CTkFrame(
            self,
            fg_color="transparent",
        )
        footer.pack(
            fill="x",
            padx=18,
            pady=(0, 18),
        )
        footer.grid_columnconfigure(0, weight=1)

        self.footer_status = ctk.CTkLabel(
            footer,
            text=(
                "Confirma los datos semánticos que Aegis no puede "
                "inferir automáticamente."
            ),
            text_color=COLORS["muted"],
            font=(FONT_FAMILY, 9),
            anchor="w",
        )
        self.footer_status.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        ActionButton(
            footer,
            "Cancelar",
            self.destroy,
        ).grid(
            row=0,
            column=1,
            padx=(8, 6),
        )

        self.save_button = ActionButton(
            footer,
            "Guardar perfil y cargarlo",
            self._save,
            "primary",
        )
        self.save_button.grid(
            row=0,
            column=2,
        )

    def _build_project_tab(self):
        tab = self.tabs.tab("Proyecto")
        tab.grid_columnconfigure(1, weight=1)

        fields = (
            ("Nombre del sistema", self.system_var),
            ("Versión objetivo", self.version_var),
            ("Base URL", self.base_url_var),
        )

        for row, (label, variable) in enumerate(fields):
            ctk.CTkLabel(
                tab,
                text=label,
                text_color=COLORS["muted"],
                anchor="w",
                font=(FONT_FAMILY, 10),
            ).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(18, 12),
                pady=8,
            )
            ctk.CTkEntry(
                tab,
                textvariable=variable,
                fg_color="#071724",
                border_color=COLORS["border"],
                text_color=COLORS["text"],
            ).grid(
                row=row,
                column=1,
                sticky="ew",
                padx=(0, 18),
                pady=8,
            )

        summary = SectionCard(
            tab,
            "Detección del proyecto",
            "Lenguajes, frameworks, manifiestos y puntos de entrada.",
        )
        summary.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="nsew",
            padx=18,
            pady=(14, 18),
        )
        tab.grid_rowconfigure(3, weight=1)

        self.detection_text = ctk.CTkTextbox(
            summary,
            fg_color="#04101A",
            border_width=1,
            border_color=COLORS["border_soft"],
            text_color="#BFD8E8",
            font=(MONO_FAMILY, 10),
        )
        self.detection_text.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=16,
            pady=(8, 16),
        )
        summary.grid_rowconfigure(2, weight=1)
        self.detection_text.insert(
            "1.0",
            "Esperando selección de proyecto.",
        )
        self.detection_text.configure(
            state="disabled"
        )

    def _build_runtime_tab(self):
        tab = self.tabs.tab("Runtime")
        tab.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            tab,
            text="Modo",
            text_color=COLORS["muted"],
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(18, 12),
            pady=8,
        )
        ctk.CTkOptionMenu(
            tab,
            variable=self.mode_var,
            values=["process", "service", "external"],
            fg_color=COLORS["surface_3"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(0, 18),
            pady=8,
        )

        for row, (label, variable) in enumerate(
            (
                ("Comando de inicio", self.start_var),
                ("Directorio de trabajo", self.workdir_var),
            ),
            start=1,
        ):
            ctk.CTkLabel(
                tab,
                text=label,
                text_color=COLORS["muted"],
                anchor="w",
            ).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(18, 12),
                pady=8,
            )
            ctk.CTkEntry(
                tab,
                textvariable=variable,
                fg_color="#071724",
                border_color=COLORS["border"],
                text_color=COLORS["text"],
            ).grid(
                row=row,
                column=1,
                sticky="ew",
                padx=(0, 18),
                pady=8,
            )

        ctk.CTkCheckBox(
            tab,
            text="Preparar dependencias automáticamente",
            variable=self.auto_prepare_var,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
        ).grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="w",
            padx=18,
            pady=12,
        )

        self.runtime_note = ctk.CTkLabel(
            tab,
            text=(
                "Aegis conservará los overrides multiplataforma "
                "detectados para Windows, Linux y macOS."
            ),
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
        )
        self.runtime_note.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(8, 18),
        )

    def _build_p1_tab(self):
        tab = self.tabs.tab("Pilar 1")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        actions = ctk.CTkFrame(
            tab,
            fg_color="transparent",
        )
        actions.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=12,
            pady=(10, 8),
        )

        ActionButton(
            actions,
            "＋ Agregar cuenta",
            self._add_account,
            "primary",
        ).pack(side="left", padx=(0, 6))

        ActionButton(
            actions,
            "BOLA desde endpoint",
            self._add_bola_check,
        ).pack(side="left", padx=6)

        ActionButton(
            actions,
            "RBAC desde endpoint",
            self._add_rbac_check,
        ).pack(side="left", padx=6)

        pane = ctk.CTkFrame(
            tab,
            fg_color="transparent",
        )
        pane.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=12,
            pady=(0, 12),
        )
        pane.grid_columnconfigure(0, weight=1)
        pane.grid_columnconfigure(1, weight=2)
        pane.grid_rowconfigure(0, weight=1)

        accounts_card = SectionCard(
            pane,
            "Cuentas y roles",
            "Identidades utilizadas por los controles.",
        )
        accounts_card.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 6),
        )
        accounts_card.grid_rowconfigure(2, weight=1)

        self.accounts_text = ctk.CTkTextbox(
            accounts_card,
            fg_color="#04101A",
            text_color="#BFD8E8",
            font=(MONO_FAMILY, 10),
        )
        self.accounts_text.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=16,
            pady=(8, 16),
        )

        routes_card = SectionCard(
            pane,
            "Endpoints candidatos",
            "Selecciona una ruta antes de crear BOLA/RBAC.",
        )
        routes_card.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(6, 0),
        )
        routes_card.grid_rowconfigure(2, weight=1)

        columns = ("method", "route", "source")
        self.routes = ttk.Treeview(
            routes_card,
            columns=columns,
            show="headings",
            height=12,
        )
        self.routes.heading(
            "method",
            text="Método",
        )
        self.routes.heading(
            "route",
            text="Ruta",
        )
        self.routes.heading(
            "source",
            text="Archivo",
        )
        self.routes.column(
            "method",
            width=80,
            anchor="center",
        )
        self.routes.column(
            "route",
            width=260,
        )
        self.routes.column(
            "source",
            width=340,
        )
        self.routes.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=16,
            pady=(8, 16),
        )

    def _build_p2_tab(self):
        tab = self.tabs.tab("Pilar 2")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        actions = ctk.CTkFrame(
            tab,
            fg_color="transparent",
        )
        actions.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=12,
            pady=(10, 8),
        )

        for text, command in (
            ("Docker no-root", self._add_p2_docker),
            ("Patrón de fuente", self._add_p2_source),
            ("CORS", self._add_p2_cors),
            ("Política HTTP", self._add_p2_http),
        ):
            ActionButton(
                actions,
                text,
                command,
            ).pack(
                side="left",
                padx=5,
            )

        self.p2_text = ctk.CTkTextbox(
            tab,
            fg_color="#04101A",
            border_width=1,
            border_color=COLORS["border_soft"],
            text_color="#BFD8E8",
            font=(MONO_FAMILY, 10),
        )
        self.p2_text.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=18,
            pady=(0, 18),
        )

    def _build_json_tab(self):
        tab = self.tabs.tab("Perfil JSON")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        self.json_text = ctk.CTkTextbox(
            tab,
            fg_color="#04101A",
            border_width=1,
            border_color=COLORS["border_soft"],
            text_color="#BFD8E8",
            font=(MONO_FAMILY, 10),
            wrap="none",
        )
        self.json_text.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=18,
            pady=(16, 8),
        )

        ActionButton(
            tab,
            "Actualizar vista previa",
            self._refresh_profile_preview,
        ).grid(
            row=1,
            column=0,
            sticky="e",
            padx=18,
            pady=(0, 16),
        )

    def _choose_project(self):
        selected = filedialog.askdirectory(
            parent=self,
            title="Selecciona la carpeta raíz de la aplicación",
        )
        if selected:
            self._analyze_project(
                Path(selected)
            )

    def _analyze_project(self, path: Path):
        if self.busy:
            return

        self.busy = True
        self.project_label.configure(
            text=f"Analizando {path}…",
            text_color=COLORS["accent"],
        )
        self.scan_progress.start()
        self.save_button.configure(
            state="disabled"
        )
        self.steps.set_step(1)

        def worker():
            try:
                result = detect_project(
                    path
                )
            except Exception as exc:
                self.after(
                    0,
                    lambda error=exc:
                    self._analysis_failed(error),
                )
                return

            self.after(
                0,
                lambda value=result:
                self._analysis_complete(value),
            )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    def _analysis_failed(self, exc: Exception):
        self.busy = False
        self.scan_progress.stop()
        self.scan_progress.set(0)
        self.save_button.configure(
            state="normal"
        )
        self.project_label.configure(
            text="No se pudo analizar el proyecto.",
            text_color=COLORS["danger"],
        )
        messagebox.showerror(
            "No se pudo analizar",
            str(exc),
            parent=self,
        )

    def _analysis_complete(
        self,
        detection: ProjectDetection,
    ):
        self.busy = False
        self.scan_progress.stop()
        self.scan_progress.set(1)
        self.save_button.configure(
            state="normal"
        )

        self.project_root = detection.root
        self.detection = detection
        self.profile = build_profile_draft(
            detection
        )

        self.project_label.configure(
            text=str(self.project_root),
            text_color=COLORS["success"],
        )

        self.system_var.set(
            self.profile["sistema"]
        )
        self.version_var.set(
            self.profile["version_objetivo"]
        )
        self.base_url_var.set(
            self.profile["base_url"]
        )

        runtime = (
            self.profile.get("runtime")
            or {}
        )
        self.mode_var.set(
            runtime.get("modo")
            or "process"
        )
        self.start_var.set(
            self._command_to_text(
                runtime.get("comando_inicio")
                or []
            )
        )
        self.workdir_var.set(
            runtime.get(
                "directorio_trabajo"
            )
            or "."
        )
        self.auto_prepare_var.set(
            bool(
                runtime.get(
                    "preparar_automaticamente"
                )
            )
        )

        self._populate_detection()
        self._populate_routes()
        self._refresh_accounts()
        self._refresh_p2()
        self._refresh_profile_preview()

        self.steps.set_step(2)
        self.tabs.set("Proyecto")

    def _populate_detection(self):
        if not self.detection:
            return

        lines = [
            f"Proyecto: {self.detection.name}",
            (
                "Lenguajes: "
                + (
                    ", ".join(
                        self.detection.languages
                    )
                    or "No determinado"
                )
            ),
            (
                "Frameworks: "
                + (
                    ", ".join(
                        self.detection.frameworks
                    )
                    or "No determinado"
                )
            ),
            (
                "Manifiestos: "
                + (
                    ", ".join(
                        self.detection.manifests
                    )
                    or "Ninguno"
                )
            ),
            (
                "Raíces de código: "
                + ", ".join(
                    self.detection.source_roots
                )
            ),
            (
                "Endpoints candidatos: "
                f"{len(self.detection.routes)}"
            ),
            (
                "auditor-package.json: "
                + (
                    "detectado"
                    if self.detection.package_descriptor
                    else "no detectado"
                )
            ),
        ]

        self.detection_text.configure(
            state="normal"
        )
        self.detection_text.delete(
            "1.0",
            "end",
        )
        self.detection_text.insert(
            "1.0",
            "\n".join(lines),
        )
        self.detection_text.configure(
            state="disabled"
        )

    def _populate_routes(self):
        for item in self.routes.get_children():
            self.routes.delete(
                item
            )

        if not self.detection:
            return

        for index, route in enumerate(
            self.detection.routes
        ):
            self.routes.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    route.method,
                    route.path,
                    route.source,
                ),
            )

    def _command_to_text(
        self,
        command: list[str],
    ) -> str:
        return " ".join(
            shlex.quote(
                str(item)
            )
            for item in command
        )

    def _text_to_command(
        self,
        value: str,
    ) -> list[str]:
        value = value.strip()
        if not value:
            return []

        try:
            return shlex.split(
                value,
                posix=False,
            )
        except ValueError:
            return value.split()

    def _compose_profile(self) -> dict:
        if not self.detection:
            raise RuntimeError(
                "Primero selecciona una aplicación."
            )

        profile = dict(
            self.profile
            or build_profile_draft(
                self.detection
            )
        )

        profile["sistema"] = (
            self.system_var.get().strip()
            or self.detection.name
        )
        profile["version_objetivo"] = (
            self.version_var.get().strip()
            or "1.0.0"
        )
        profile["base_url"] = (
            self.base_url_var.get()
            .strip()
            .rstrip("/")
        )

        runtime = dict(
            profile.get("runtime")
            or {}
        )
        runtime["modo"] = (
            self.mode_var.get().strip()
            or "process"
        )
        runtime["directorio_trabajo"] = (
            self.workdir_var.get().strip()
            or "."
        )
        runtime[
            "preparar_automaticamente"
        ] = bool(
            self.auto_prepare_var.get()
        )

        command = self._text_to_command(
            self.start_var.get()
        )
        if command:
            runtime[
                "comando_inicio"
            ] = command

        profile["runtime"] = runtime
        return profile

    def _refresh_profile_preview(self):
        if not self.detection:
            return

        try:
            self.profile = (
                self._compose_profile()
            )
        except Exception:
            return

        self.json_text.delete(
            "1.0",
            "end",
        )
        self.json_text.insert(
            "1.0",
            json.dumps(
                self.profile,
                ensure_ascii=False,
                indent=2,
            ),
        )

        self.steps.set_step(3)

    def _selected_route(self):
        selected = self.routes.selection()
        if not selected:
            messagebox.showinfo(
                "Selecciona un endpoint",
                "Selecciona primero una ruta detectada.",
                parent=self,
            )
            return None

        values = self.routes.item(
            selected[0],
            "values",
        )
        if len(values) < 3:
            return None

        return (
            str(values[0]),
            str(values[1]),
            str(values[2]),
        )

    def _ask(self, title: str, text: str):
        dialog = ctk.CTkInputDialog(
            text=text,
            title=title,
        )
        return dialog.get_input()

    def _add_account(self):
        username = self._ask(
            "Pilar 1",
            "Usuario de prueba:",
        )
        if not username:
            return

        role = self._ask(
            "Pilar 1",
            "Rol de la cuenta:",
        )
        if not role:
            return

        auth = self._ask(
            "Pilar 1",
            (
                "Tipo de autenticación "
                "(none/basic/bearer/header):"
            ),
        )
        auth = (
            auth
            if auth in AUTH_TYPES
            else "none"
        )

        password = self._ask(
            "Pilar 1",
            "Contraseña opcional:",
        )

        if self.profile is None:
            self.profile = {}

        self.profile.setdefault(
            "cuentas",
            [],
        ).append(
            {
                "username": username.strip(),
                "password": password or None,
                "role": role.strip(),
                "auth_type": auth,
                "headers": {},
            }
        )

        self._refresh_accounts()
        self._refresh_profile_preview()

    def _refresh_accounts(self):
        accounts = (
            (self.profile or {})
            .get("cuentas")
            or []
        )

        lines = []
        for item in accounts:
            lines.append(
                f"{item.get('username')}  |  "
                f"{item.get('role')}  |  "
                f"{item.get('auth_type', 'none')}"
            )

        self.accounts_text.delete(
            "1.0",
            "end",
        )
        self.accounts_text.insert(
            "1.0",
            "\n".join(lines)
            if lines
            else "Sin cuentas configuradas.",
        )

    def _add_bola_check(self):
        route = self._selected_route()
        if not route:
            return

        method, path, source = route

        object_id = self._ask(
            "Pilar 1 — BOLA",
            "ID de objeto de prueba:",
        )
        if not object_id:
            return

        owner = self._ask(
            "Pilar 1 — BOLA",
            "Usuario propietario esperado:",
        )
        if not owner:
            return

        profile = self.profile or {}
        endpoints = profile.setdefault(
            "endpoints",
            [],
        )
        control_id = (
            "P1-BOLA-AUTO-"
            f"{len(endpoints) + 1:03d}"
        )

        endpoints.append(
            {
                "id_control": control_id,
                "descripcion": (
                    "Validar autorización "
                    f"a nivel de objeto en {method} {path}"
                ),
                "metodo": (
                    method
                    if method != "ANY"
                    else "GET"
                ),
                "ruta": path,
                "id_prueba": object_id.strip(),
                "propietario_esperado": owner.strip(),
                "codigos_permitidos": [
                    200,
                    201,
                    204,
                ],
                "archivos_fuente": [source],
                "pistas_codigo": [
                    "authorization",
                    "owner",
                    "id",
                ],
            }
        )

        self.profile = profile
        self._refresh_profile_preview()

    def _add_rbac_check(self):
        route = self._selected_route()
        if not route:
            return

        method, path, source = route
        accounts = (
            (self.profile or {})
            .get("cuentas")
            or []
        )

        if not accounts:
            messagebox.showwarning(
                "Faltan cuentas",
                "Agrega al menos una cuenta.",
                parent=self,
            )
            return

        username = self._ask(
            "Pilar 1 — RBAC",
            (
                "Cuenta que ejecutará la prueba:\n"
                + ", ".join(
                    str(item.get("username"))
                    for item in accounts
                )
            ),
        )

        known = {
            str(item.get("username"))
            for item in accounts
        }

        if username not in known:
            return

        allowed = messagebox.askyesno(
            "Pilar 1 — RBAC",
            (
                f"¿{username} DEBE tener acceso a "
                f"{method} {path}?"
            ),
            parent=self,
        )

        profile = self.profile or {}
        checks = profile.setdefault(
            "chequeos_acceso",
            [],
        )
        control_id = (
            "P1-RBAC-AUTO-"
            f"{len(checks) + 1:03d}"
        )

        checks.append(
            {
                "id_control": control_id,
                "nombre": (
                    f"Control de acceso {method} {path}"
                ),
                "cuenta": username,
                "metodo": (
                    method
                    if method != "ANY"
                    else "GET"
                ),
                "ruta": path,
                "cuerpo": None,
                "acceso_esperado": allowed,
                "codigos_permitidos": [
                    200,
                    201,
                    204,
                ],
                "archivos_fuente": [source],
                "pistas_codigo": [
                    "role",
                    "authorization",
                    "access",
                ],
            }
        )

        self.profile = profile
        self._refresh_profile_preview()

    def _next_p2_id(self) -> str:
        checks = (
            (self.profile or {})
            .get("chequeos_pilar2")
            or []
        )
        return (
            "P2-AUTO-"
            f"{len(checks) + 1:03d}"
        )

    def _append_p2(self, item: dict):
        if self.profile is None:
            self.profile = {}

        self.profile.setdefault(
            "chequeos_pilar2",
            [],
        ).append(item)

        self._refresh_p2()
        self._refresh_profile_preview()

    def _add_p2_docker(self):
        filename = self._ask(
            "Pilar 2",
            "Archivo Docker a revisar:",
        )
        if not filename:
            return

        self._append_p2(
            {
                "id_control": self._next_p2_id(),
                "nombre": (
                    "El contenedor debe ejecutar "
                    "con usuario no root"
                ),
                "tipo": "docker_non_root",
                "archivo": filename.strip(),
                "archivos_fuente": [
                    filename.strip()
                ],
                "pistas_codigo": [
                    "USER",
                    "Dockerfile",
                    "non-root",
                ],
            }
        )

    def _add_p2_source(self):
        filename = self._ask(
            "Pilar 2",
            "Archivo relativo al proyecto:",
        )
        if not filename:
            return

        pattern = self._ask(
            "Pilar 2",
            "Patrón inseguro:",
        )
        if not pattern:
            return

        safe = self._ask(
            "Pilar 2",
            "Patrón seguro opcional:",
        )

        item = {
            "id_control": self._next_p2_id(),
            "nombre": (
                "Revisar configuración insegura "
                f"en {filename.strip()}"
            ),
            "tipo": "source_contains",
            "archivo": filename.strip(),
            "patron_inseguro": pattern,
            "archivos_fuente": [
                filename.strip()
            ],
            "pistas_codigo": [
                pattern[:80]
            ],
        }

        if safe:
            item[
                "patron_seguro"
            ] = safe

        self._append_p2(item)

    def _add_p2_cors(self):
        route = self._ask(
            "Pilar 2 — CORS",
            "Ruta HTTP:",
        )
        if route is None:
            return

        self._append_p2(
            {
                "id_control": self._next_p2_id(),
                "nombre": (
                    "No reflejar orígenes "
                    "no autorizados con credenciales"
                ),
                "tipo": "cors_reflection",
                "metodo": "GET",
                "ruta": route.strip() or "/",
                "headers": {},
            }
        )

    def _add_p2_http(self):
        route = self._ask(
            "Pilar 2 — HTTP",
            "Ruta HTTP:",
        )
        if route is None:
            return

        codes = self._ask(
            "Pilar 2 — HTTP",
            (
                "Códigos seguros separados por coma "
                "(ej. 400,401,403,429):"
            ),
        )
        if codes is None:
            return

        try:
            parsed = [
                int(value.strip())
                for value in codes.split(",")
                if value.strip()
            ]
        except ValueError:
            messagebox.showerror(
                "Códigos inválidos",
                "Usa números separados por coma.",
                parent=self,
            )
            return

        self._append_p2(
            {
                "id_control": self._next_p2_id(),
                "nombre": (
                    "Política HTTP para "
                    f"GET {route.strip() or '/'}"
                ),
                "tipo": "http_status_policy",
                "metodo": "GET",
                "ruta": route.strip() or "/",
                "codigos_seguros": (
                    parsed
                    or [
                        400,
                        401,
                        403,
                        429,
                    ]
                ),
            }
        )

    def _refresh_p2(self):
        checks = (
            (self.profile or {})
            .get("chequeos_pilar2")
            or []
        )

        self.p2_text.delete(
            "1.0",
            "end",
        )
        self.p2_text.insert(
            "1.0",
            json.dumps(
                checks,
                ensure_ascii=False,
                indent=2,
            ),
        )

    def _save(self):
        if not self.detection or not self.project_root:
            messagebox.showwarning(
                "Falta la aplicación",
                "Selecciona primero una aplicación.",
                parent=self,
            )
            return

        try:
            profile = self._compose_profile()
        except Exception as exc:
            messagebox.showerror(
                "Perfil inválido",
                str(exc),
                parent=self,
            )
            return

        selected = filedialog.asksaveasfilename(
            parent=self,
            title="Guardar perfil de aplicación",
            initialdir=str(
                default_config_dir()
            ),
            initialfile=(
                f"{profile['sistema']}.json"
            ),
            defaultextension=".json",
            filetypes=[
                ("Perfil JSON", "*.json")
            ],
        )

        if not selected:
            return

        try:
            path = save_profile_draft(
                profile,
                selected,
            )
        except Exception as exc:
            messagebox.showerror(
                "No se pudo guardar",
                str(exc),
                parent=self,
            )
            return

        self.steps.set_step(5)
        self.footer_status.configure(
            text=f"Perfil listo: {path}",
            text_color=COLORS["success"],
        )

        if self.on_saved:
            self.on_saved(
                path,
                self.project_root,
            )

        messagebox.showinfo(
            "Aplicación incorporada",
            (
                "El perfil fue creado y cargado.\n\n"
                f"{path}"
            ),
            parent=self,
        )
        self.destroy()
