"""Asistente visual para incorporar una aplicación al Auditor."""

from __future__ import annotations

import json
import shlex
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from .profile_builder import (
    ProjectDetection,
    build_profile_draft,
    detect_project,
    save_profile_draft,
)


AUTH_TYPES = ("none", "basic", "bearer", "header")


class ProfileWizard(tk.Toplevel):
    """Construye un perfil config/*.json a partir de una carpeta de proyecto."""

    def __init__(
        self,
        master,
        *,
        initial_project: str | Path | None = None,
        on_saved: Callable[[Path, Path], None] | None = None,
    ):
        super().__init__(master)
        self.title("Aegis Auditor — Incorporar aplicación")
        self.geometry("1040x720")
        self.minsize(860, 620)
        self.transient(master)
        self.on_saved = on_saved
        self.project_root: Path | None = None
        self.detection: ProjectDetection | None = None
        self.profile: dict | None = None

        self.system_var = tk.StringVar()
        self.version_var = tk.StringVar(value="1.0.0")
        self.base_url_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="process")
        self.start_var = tk.StringVar()
        self.workdir_var = tk.StringVar(value=".")
        self.auto_prepare_var = tk.BooleanVar(value=False)

        self._build_ui()

        if initial_project:
            self.after(80, lambda: self._load_project(Path(initial_project)))

        self.grab_set()

    def _build_ui(self):
        header = ttk.Frame(self, padding=(18, 14))
        header.pack(fill="x")
        header.columnconfigure(1, weight=1)

        logo = tk.Canvas(
            header,
            width=48,
            height=48,
            highlightthickness=0,
            background="#0b1f33",
        )
        logo.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        logo.create_polygon(
            24, 4, 42, 12, 39, 33, 24, 45, 9, 33, 6, 12,
            fill="#24b6a6",
            outline="",
        )
        logo.create_line(
            15, 24, 22, 31, 34, 17,
            fill="white",
            width=4,
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND,
        )

        ttk.Label(
            header,
            text="Incorporar una aplicación",
            style="Aegis.H1.TLabel",
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(
            header,
            text=(
                "Detecta tecnología, runtime y endpoints; luego genera un "
                "perfil compatible con la carpeta config."
            ),
            style="Aegis.Muted.TLabel",
        ).grid(row=1, column=1, sticky="w", pady=(2, 0))

        controls = ttk.Frame(self, padding=(18, 0, 18, 12))
        controls.pack(fill="x")
        controls.columnconfigure(1, weight=1)
        ttk.Button(
            controls,
            text="Seleccionar carpeta de aplicación",
            command=self._choose_project,
            style="Aegis.Primary.TButton",
        ).grid(row=0, column=0, padx=(0, 10))
        self.lbl_project = ttk.Label(
            controls,
            text="No se ha seleccionado una aplicación.",
            style="Aegis.Muted.TLabel",
        )
        self.lbl_project.grid(row=0, column=1, sticky="ew")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=18, pady=(0, 12))

        self.tab_summary = ttk.Frame(self.notebook, padding=14)
        self.tab_runtime = ttk.Frame(self.notebook, padding=14)
        self.tab_accounts = ttk.Frame(self.notebook, padding=14)
        self.tab_routes = ttk.Frame(self.notebook, padding=14)
        self.tab_json = ttk.Frame(self.notebook, padding=14)

        self.notebook.add(self.tab_summary, text="1. Proyecto")
        self.notebook.add(self.tab_runtime, text="2. Runtime")
        self.notebook.add(self.tab_accounts, text="3. Cuentas")
        self.notebook.add(self.tab_routes, text="4. Endpoints")
        self.notebook.add(self.tab_json, text="5. Perfil JSON")

        self._build_summary()
        self._build_runtime()
        self._build_accounts()
        self._build_routes()
        self._build_json()

        footer = ttk.Frame(self, padding=(18, 0, 18, 18))
        footer.pack(fill="x")
        footer.columnconfigure(0, weight=1)
        ttk.Label(
            footer,
            text=(
                "La detección automática crea un borrador. Las credenciales, "
                "propiedad de objetos y expectativas de autorización deben "
                "confirmarse antes de una auditoría real."
            ),
            style="Aegis.Muted.TLabel",
            wraplength=650,
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            footer,
            text="Guardar perfil y cargarlo",
            command=self._save,
            style="Aegis.Primary.TButton",
        ).grid(row=0, column=1, padx=(12, 0))
        ttk.Button(
            footer,
            text="Cancelar",
            command=self.destroy,
        ).grid(row=0, column=2, padx=(8, 0))

    def _build_summary(self):
        self.tab_summary.columnconfigure(1, weight=1)
        fields = (
            ("Nombre del sistema", self.system_var),
            ("Versión objetivo", self.version_var),
            ("Base URL", self.base_url_var),
        )
        for row, (label, variable) in enumerate(fields):
            ttk.Label(self.tab_summary, text=label).grid(
                row=row, column=0, sticky="w", pady=6, padx=(0, 10)
            )
            ttk.Entry(self.tab_summary, textvariable=variable).grid(
                row=row, column=1, sticky="ew", pady=6
            )

        ttk.Separator(self.tab_summary).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=12
        )

        self.lbl_detection = ttk.Label(
            self.tab_summary,
            text="Selecciona una carpeta para comenzar.",
            justify="left",
            anchor="nw",
            wraplength=760,
        )
        self.lbl_detection.grid(
            row=4, column=0, columnspan=2, sticky="nsew"
        )
        self.tab_summary.rowconfigure(4, weight=1)

    def _build_runtime(self):
        self.tab_runtime.columnconfigure(1, weight=1)

        ttk.Label(self.tab_runtime, text="Modo").grid(
            row=0, column=0, sticky="w", pady=6
        )
        ttk.Combobox(
            self.tab_runtime,
            textvariable=self.mode_var,
            values=("process", "service", "external"),
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(self.tab_runtime, text="Comando de inicio").grid(
            row=1, column=0, sticky="w", pady=6
        )
        ttk.Entry(self.tab_runtime, textvariable=self.start_var).grid(
            row=1, column=1, sticky="ew", pady=6
        )

        ttk.Label(self.tab_runtime, text="Directorio de trabajo").grid(
            row=2, column=0, sticky="w", pady=6
        )
        ttk.Entry(self.tab_runtime, textvariable=self.workdir_var).grid(
            row=2, column=1, sticky="ew", pady=6
        )

        ttk.Checkbutton(
            self.tab_runtime,
            text="Preparar dependencias automáticamente antes del arranque",
            variable=self.auto_prepare_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 4))

        ttk.Label(
            self.tab_runtime,
            text=(
                "Aegis conserva la configuración multiplataforma detectada. "
                "Este campo de comando modifica únicamente el comando general."
            ),
            style="Aegis.Muted.TLabel",
            wraplength=760,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def _build_accounts(self):
        self.tab_accounts.rowconfigure(0, weight=1)
        self.tab_accounts.columnconfigure(0, weight=1)

        columns = ("username", "role", "auth")
        self.accounts = ttk.Treeview(
            self.tab_accounts,
            columns=columns,
            show="headings",
        )
        self.accounts.heading("username", text="Usuario")
        self.accounts.heading("role", text="Rol")
        self.accounts.heading("auth", text="Autenticación")
        self.accounts.column("username", width=220)
        self.accounts.column("role", width=180)
        self.accounts.column("auth", width=160)
        self.accounts.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(
            self.tab_accounts,
            orient="vertical",
            command=self.accounts.yview,
        )
        self.accounts.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")

        buttons = ttk.Frame(self.tab_accounts)
        buttons.grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(
            buttons,
            text="Agregar cuenta",
            command=self._add_account,
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="Eliminar seleccionada",
            command=self._remove_account,
        ).pack(side="left", padx=(8, 0))

    def _build_routes(self):
        self.tab_routes.rowconfigure(0, weight=1)
        self.tab_routes.columnconfigure(0, weight=1)

        columns = ("method", "route", "source")
        self.routes = ttk.Treeview(
            self.tab_routes,
            columns=columns,
            show="headings",
        )
        self.routes.heading("method", text="Método")
        self.routes.heading("route", text="Ruta")
        self.routes.heading("source", text="Archivo detectado")
        self.routes.column("method", width=90, anchor="center")
        self.routes.column("route", width=300)
        self.routes.column("source", width=460)
        self.routes.grid(row=0, column=0, sticky="nsew")

        sy = ttk.Scrollbar(
            self.tab_routes,
            orient="vertical",
            command=self.routes.yview,
        )
        self.routes.configure(yscrollcommand=sy.set)
        sy.grid(row=0, column=1, sticky="ns")

        ttk.Label(
            self.tab_routes,
            text=(
                "Estos son candidatos detectados estáticamente. No se crean "
                "pruebas BOLA/RBAC sin confirmar propietario, cuenta y acceso "
                "esperado."
            ),
            style="Aegis.Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(10, 0))

    def _build_json(self):
        self.tab_json.rowconfigure(0, weight=1)
        self.tab_json.columnconfigure(0, weight=1)
        self.json_text = tk.Text(
            self.tab_json,
            wrap="none",
            font=("Consolas", 10),
        )
        self.json_text.grid(row=0, column=0, sticky="nsew")
        sy = ttk.Scrollbar(
            self.tab_json,
            orient="vertical",
            command=self.json_text.yview,
        )
        sx = ttk.Scrollbar(
            self.tab_json,
            orient="horizontal",
            command=self.json_text.xview,
        )
        self.json_text.configure(
            yscrollcommand=sy.set,
            xscrollcommand=sx.set,
        )
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")

        ttk.Button(
            self.tab_json,
            text="Actualizar vista previa",
            command=self._refresh_profile_preview,
        ).grid(row=2, column=0, sticky="e", pady=(10, 0))

    def _choose_project(self):
        selected = filedialog.askdirectory(
            parent=self,
            title="Selecciona la carpeta raíz de la aplicación",
        )
        if selected:
            self._load_project(Path(selected))

    def _load_project(self, path: Path):
        try:
            detection = detect_project(path)
        except Exception as exc:
            messagebox.showerror(
                "No se pudo analizar el proyecto",
                str(exc),
                parent=self,
            )
            return

        self.project_root = path.resolve()
        self.detection = detection
        self.profile = build_profile_draft(detection)

        self.lbl_project.configure(text=str(self.project_root))
        self.system_var.set(self.profile["sistema"])
        self.version_var.set(self.profile["version_objetivo"])
        self.base_url_var.set(self.profile["base_url"])

        runtime = self.profile.get("runtime") or {}
        self.mode_var.set(runtime.get("modo") or "process")
        self.start_var.set(
            self._command_to_text(runtime.get("comando_inicio") or [])
        )
        self.workdir_var.set(runtime.get("directorio_trabajo") or ".")
        self.auto_prepare_var.set(
            bool(runtime.get("preparar_automaticamente"))
        )

        summary = [
            f"Lenguajes: {', '.join(detection.languages) or 'No determinado'}",
            f"Frameworks: {', '.join(detection.frameworks) or 'No determinado'}",
            f"Manifiestos: {', '.join(detection.manifests) or 'Ninguno detectado'}",
            f"Raíces de código: {', '.join(detection.source_roots)}",
            f"Endpoints candidatos: {len(detection.routes)}",
        ]
        if detection.package_descriptor:
            summary.append("auditor-package.json: detectado y utilizado")
        self.lbl_detection.configure(text="\n".join(summary))

        for item in self.routes.get_children():
            self.routes.delete(item)
        for index, route in enumerate(detection.routes):
            self.routes.insert(
                "",
                "end",
                iid=str(index),
                values=(route.method, route.path, route.source),
            )

        self._refresh_profile_preview()

    @staticmethod
    def _command_to_text(command: list[str]) -> str:
        return " ".join(
            shlex.quote(str(item)) for item in command
        )

    @staticmethod
    def _text_to_command(text: str) -> list[str]:
        value = text.strip()
        if not value:
            return []
        try:
            return shlex.split(value, posix=False)
        except ValueError:
            return value.split()

    def _add_account(self):
        dialog = tk.Toplevel(self)
        dialog.title("Agregar cuenta")
        dialog.geometry("420x300")
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)

        username = tk.StringVar()
        password = tk.StringVar()
        role = tk.StringVar(value="USER")
        auth = tk.StringVar(value="none")

        fields = (
            ("Usuario", username, False),
            ("Contraseña", password, True),
            ("Rol", role, False),
        )
        for row, (label, var, secret) in enumerate(fields):
            ttk.Label(dialog, text=label).grid(
                row=row, column=0, sticky="w", padx=14, pady=8
            )
            ttk.Entry(
                dialog,
                textvariable=var,
                show="•" if secret else "",
            ).grid(row=row, column=1, sticky="ew", padx=(0, 14), pady=8)

        ttk.Label(dialog, text="Autenticación").grid(
            row=3, column=0, sticky="w", padx=14, pady=8
        )
        ttk.Combobox(
            dialog,
            textvariable=auth,
            values=AUTH_TYPES,
            state="readonly",
        ).grid(row=3, column=1, sticky="ew", padx=(0, 14), pady=8)

        def save():
            user = username.get().strip()
            user_role = role.get().strip()
            if not user or not user_role:
                messagebox.showwarning(
                    "Datos incompletos",
                    "Usuario y rol son obligatorios.",
                    parent=dialog,
                )
                return
            iid = str(len(self.accounts.get_children()))
            self.accounts.insert(
                "", "end", iid=iid, values=(user, user_role, auth.get())
            )
            if self.profile is None:
                self.profile = {}
            self.profile.setdefault("cuentas", []).append(
                {
                    "username": user,
                    "password": password.get() or None,
                    "role": user_role,
                    "auth_type": auth.get(),
                    "headers": {},
                }
            )
            dialog.destroy()
            self._refresh_profile_preview()

        ttk.Button(
            dialog,
            text="Agregar",
            command=save,
            style="Aegis.Primary.TButton",
        ).grid(row=4, column=1, sticky="e", padx=14, pady=14)

    def _remove_account(self):
        selected = self.accounts.selection()
        if not selected:
            return
        indexes = sorted(
            (self.accounts.index(iid) for iid in selected),
            reverse=True,
        )
        for iid in selected:
            self.accounts.delete(iid)
        if self.profile:
            accounts = self.profile.get("cuentas") or []
            for index in indexes:
                if 0 <= index < len(accounts):
                    accounts.pop(index)
        self._refresh_profile_preview()

    def _compose_profile(self) -> dict:
        if self.detection is None:
            raise RuntimeError("Primero selecciona una aplicación.")

        profile = dict(
            self.profile
            or build_profile_draft(self.detection)
        )
        profile["sistema"] = self.system_var.get().strip() or self.detection.name
        profile["version_objetivo"] = (
            self.version_var.get().strip() or "1.0.0"
        )
        profile["base_url"] = self.base_url_var.get().strip().rstrip("/")

        runtime = dict(profile.get("runtime") or {})
        runtime["modo"] = self.mode_var.get().strip() or "process"
        runtime["directorio_trabajo"] = self.workdir_var.get().strip() or "."
        runtime["preparar_automaticamente"] = bool(
            self.auto_prepare_var.get()
        )
        command = self._text_to_command(self.start_var.get())
        if command:
            runtime["comando_inicio"] = command
        profile["runtime"] = runtime

        return profile

    def _refresh_profile_preview(self):
        try:
            profile = self._compose_profile()
        except Exception:
            return
        self.profile = profile
        self.json_text.delete("1.0", "end")
        self.json_text.insert(
            "1.0",
            json.dumps(profile, ensure_ascii=False, indent=2),
        )

    def _save(self):
        if self.project_root is None or self.detection is None:
            messagebox.showwarning(
                "Falta la aplicación",
                "Selecciona una carpeta de aplicación.",
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

        default_name = f"{profile['sistema']}.json"
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="Guardar perfil de aplicación",
            initialdir=str(Path.cwd() / "config"),
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("Perfil JSON", "*.json")],
        )
        if not selected:
            return

        try:
            path = save_profile_draft(profile, selected)
        except Exception as exc:
            messagebox.showerror(
                "No se pudo guardar",
                str(exc),
                parent=self,
            )
            return

        project = self.project_root
        if self.on_saved:
            self.on_saved(path, project)

        messagebox.showinfo(
            "Aplicación incorporada",
            (
                "El perfil fue creado correctamente.\n\n"
                f"Perfil: {path}\n"
                f"Proyecto: {project}\n\n"
                "Revisa y completa cuentas, propiedad de objetos y controles "
                "específicos antes de ejecutar una auditoría real."
            ),
            parent=self,
        )
        self.destroy()
