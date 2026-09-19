"""Asistente visual para incorporar una aplicación al Auditor."""

from __future__ import annotations

import json
import os
import shlex
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from .app_paths import default_config_dir, resource_path
from .responsive import calculate_wizard_geometry
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
        self.configure(background="#06111d")

        self._icon_image = None
        png_icon = resource_path("assets", "aegis-auditor.png")
        ico_icon = resource_path("assets", "aegis-auditor.ico")
        if png_icon.exists():
            try:
                self._icon_image = tk.PhotoImage(file=str(png_icon))
                self.iconphoto(True, self._icon_image)
            except tk.TclError:
                self._icon_image = None
        if os.name == "nt" and ico_icon.exists():
            try:
                self.iconbitmap(default=str(ico_icon))
            except tk.TclError:
                pass

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width, height, self.compact_mode = calculate_wizard_geometry(
            screen_w,
            screen_h,
        )
        self.geometry(f"{width}x{height}")
        self.minsize(min(760, width), min(520, height))
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
        self._apply_compact_layout()
        if hasattr(master, "_apply_dark_native_widgets"):
            master._apply_dark_native_widgets(self)

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
        self.tab_p2 = ttk.Frame(self.notebook, padding=14)
        self.tab_json = ttk.Frame(self.notebook, padding=14)

        self.notebook.add(self.tab_summary, text="1. Proyecto")
        self.notebook.add(self.tab_runtime, text="2. Runtime")
        self.notebook.add(self.tab_accounts, text="3. Cuentas")
        self.notebook.add(self.tab_routes, text="4. Pilar 1")
        self.notebook.add(self.tab_p2, text="5. Pilar 2")
        self.notebook.add(self.tab_json, text="6. Perfil JSON")

        self._build_summary()
        self._build_runtime()
        self._build_accounts()
        self._build_routes()
        self._build_p2()
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

        columns = ("username", "role", "auth", "privileged")
        self.accounts = ttk.Treeview(
            self.tab_accounts,
            columns=columns,
            show="headings",
        )
        self.accounts.heading("username", text="Usuario")
        self.accounts.heading("role", text="Rol")
        self.accounts.heading("auth", text="Autenticación")
        self.accounts.heading("privileged", text="Privilegiado")
        self.accounts.column("username", width=210)
        self.accounts.column("role", width=170)
        self.accounts.column("auth", width=150)
        self.accounts.column("privileged", width=100, anchor="center")
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

        route_actions = ttk.Frame(self.tab_routes)
        route_actions.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )
        ttk.Button(
            route_actions,
            text="Crear prueba BOLA desde seleccionado",
            command=self._add_bola_check,
        ).pack(side="left")
        ttk.Button(
            route_actions,
            text="Crear prueba RBAC desde seleccionado",
            command=self._add_rbac_check,
        ).pack(side="left", padx=(8, 0))

        ttk.Label(
            self.tab_routes,
            text=(
                "Los endpoints se detectan estáticamente, pero Aegis sólo "
                "crea pruebas cuando confirmas los datos de seguridad."
            ),
            style="Aegis.Muted.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))

    def _build_p2(self):
        self.tab_p2.rowconfigure(0, weight=1)
        self.tab_p2.columnconfigure(0, weight=1)

        columns = ("id", "type", "name", "target")
        self.p2_table = ttk.Treeview(
            self.tab_p2,
            columns=columns,
            show="headings",
        )
        self.p2_table.heading("id", text="Control")
        self.p2_table.heading("type", text="Tipo")
        self.p2_table.heading("name", text="Descripción")
        self.p2_table.heading("target", text="Ruta / archivo")
        self.p2_table.column("id", width=150)
        self.p2_table.column("type", width=160)
        self.p2_table.column("name", width=300)
        self.p2_table.column("target", width=280)
        self.p2_table.grid(row=0, column=0, sticky="nsew")

        sy = ttk.Scrollbar(
            self.tab_p2,
            orient="vertical",
            command=self.p2_table.yview,
        )
        self.p2_table.configure(yscrollcommand=sy.set)
        sy.grid(row=0, column=1, sticky="ns")

        actions = ttk.Frame(self.tab_p2)
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(
            actions,
            text="Docker no-root",
            command=self._add_p2_docker,
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Patrón de fuente",
            command=self._add_p2_source,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="CORS",
            command=self._add_p2_cors,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="Política HTTP",
            command=self._add_p2_http,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="Eliminar",
            command=self._remove_p2,
        ).pack(side="right")

        ttk.Label(
            self.tab_p2,
            text=(
                "Los controles del Pilar 2 se configuran de forma declarativa. "
                "Aegis no inventa una política segura específica del proyecto."
            ),
            style="Aegis.Muted.TLabel",
            wraplength=820,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

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

    def _apply_compact_layout(self):
        """Reduce densidad del asistente en laptops y pantallas pequeñas."""
        if not self.compact_mode:
            return

        try:
            self.notebook.tab(self.tab_summary, text="Proyecto")
            self.notebook.tab(self.tab_runtime, text="Runtime")
            self.notebook.tab(self.tab_accounts, text="Cuentas")
            self.notebook.tab(self.tab_routes, text="Pilar 1")
            self.notebook.tab(self.tab_p2, text="Pilar 2")
            self.notebook.tab(self.tab_json, text="JSON")
        except tk.TclError:
            pass

        if hasattr(self, "lbl_detection"):
            self.lbl_detection.configure(wraplength=620)

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

        self._refresh_p2_table()
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
        privileged = tk.BooleanVar(value=False)

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

        ttk.Checkbutton(
            dialog,
            text="Rol privilegiado",
            variable=privileged,
        ).grid(row=4, column=1, sticky="w", padx=(0, 14), pady=6)

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
                "",
                "end",
                iid=iid,
                values=(
                    user,
                    user_role,
                    auth.get(),
                    "Sí" if privileged.get() else "No",
                ),
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
            if privileged.get():
                roles = self.profile.setdefault("roles_privilegiados", [])
                if user_role not in roles:
                    roles.append(user_role)
            dialog.destroy()
            self._refresh_profile_preview()

        ttk.Button(
            dialog,
            text="Agregar",
            command=save,
            style="Aegis.Primary.TButton",
        ).grid(row=5, column=1, sticky="e", padx=14, pady=14)

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

    def _selected_route(self) -> tuple[str, str, str] | None:
        selected = self.routes.selection()
        if not selected:
            messagebox.showinfo(
                "Selecciona un endpoint",
                "Selecciona primero una ruta detectada.",
                parent=self,
            )
            return None
        values = self.routes.item(selected[0], "values")
        if len(values) < 3:
            return None
        return str(values[0]), str(values[1]), str(values[2])

    def _add_bola_check(self):
        route = self._selected_route()
        if route is None:
            return
        method, path, source = route

        object_id = simpledialog.askstring(
            "Prueba BOLA",
            "ID de objeto que se utilizará como caso de prueba:",
            parent=self,
        )
        if object_id is None or not object_id.strip():
            return

        owner = simpledialog.askstring(
            "Prueba BOLA",
            "Usuario propietario esperado de ese objeto:",
            parent=self,
        )
        if owner is None or not owner.strip():
            return

        profile = self.profile or {}
        endpoints = profile.setdefault("endpoints", [])
        control_id = f"P1-BOLA-AUTO-{len(endpoints) + 1:03d}"
        endpoints.append(
            {
                "id_control": control_id,
                "descripcion": (
                    "Validar autorización a nivel de objeto en "
                    f"{method} {path}"
                ),
                "metodo": method if method != "ANY" else "GET",
                "ruta": path,
                "id_prueba": object_id.strip(),
                "propietario_esperado": owner.strip(),
                "codigos_permitidos": [200, 201, 204],
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
        messagebox.showinfo(
            "Prueba agregada",
            f"Se agregó {control_id} al perfil.",
            parent=self,
        )

    def _add_rbac_check(self):
        route = self._selected_route()
        if route is None:
            return
        method, path, source = route

        accounts = (self.profile or {}).get("cuentas") or []
        if not accounts:
            messagebox.showwarning(
                "Faltan cuentas",
                "Agrega al menos una cuenta antes de crear una prueba RBAC.",
                parent=self,
            )
            self.notebook.select(self.tab_accounts)
            return

        usernames = [str(item.get("username")) for item in accounts]
        username = simpledialog.askstring(
            "Prueba RBAC",
            "Cuenta que ejecutará la prueba:\n\n"
            + ", ".join(usernames),
            parent=self,
        )
        if username is None or username.strip() not in usernames:
            return

        expected = messagebox.askyesno(
            "Prueba RBAC",
            (
                f"¿La cuenta '{username.strip()}' DEBE tener acceso a "
                f"{method} {path}?\n\n"
                "Sí = acceso esperado\nNo = acceso debe ser denegado"
            ),
            parent=self,
        )

        profile = self.profile or {}
        checks = profile.setdefault("chequeos_acceso", [])
        control_id = f"P1-RBAC-AUTO-{len(checks) + 1:03d}"
        checks.append(
            {
                "id_control": control_id,
                "nombre": f"Control de acceso {method} {path}",
                "cuenta": username.strip(),
                "metodo": method if method != "ANY" else "GET",
                "ruta": path,
                "cuerpo": None,
                "acceso_esperado": expected,
                "codigos_permitidos": [200, 201, 204],
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
        messagebox.showinfo(
            "Prueba agregada",
            f"Se agregó {control_id} al perfil.",
            parent=self,
        )

    def _next_p2_id(self) -> str:
        checks = (self.profile or {}).get("chequeos_pilar2") or []
        return f"P2-AUTO-{len(checks) + 1:03d}"

    def _refresh_p2_table(self):
        if not hasattr(self, "p2_table"):
            return
        for iid in self.p2_table.get_children():
            self.p2_table.delete(iid)

        for index, item in enumerate(
            (self.profile or {}).get("chequeos_pilar2") or []
        ):
            target = item.get("archivo") or item.get("ruta") or ""
            self.p2_table.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    item.get("id_control", ""),
                    item.get("tipo", ""),
                    item.get("nombre", ""),
                    target,
                ),
            )

    def _append_p2(self, item: dict):
        if self.profile is None:
            self.profile = {}
        self.profile.setdefault("chequeos_pilar2", []).append(item)
        self._refresh_p2_table()
        self._refresh_profile_preview()

    def _add_p2_docker(self):
        archivo = simpledialog.askstring(
            "Pilar 2 — Docker",
            "Archivo Docker a revisar:",
            initialvalue="Dockerfile",
            parent=self,
        )
        if not archivo:
            return
        self._append_p2(
            {
                "id_control": self._next_p2_id(),
                "nombre": "El contenedor debe ejecutar con usuario no root",
                "tipo": "docker_non_root",
                "archivo": archivo.strip(),
                "archivos_fuente": [archivo.strip()],
                "pistas_codigo": ["USER", "Dockerfile", "non-root"],
            }
        )

    def _add_p2_source(self):
        archivo = simpledialog.askstring(
            "Pilar 2 — Patrón de fuente",
            "Archivo relativo al proyecto:",
            parent=self,
        )
        if not archivo:
            return
        patron = simpledialog.askstring(
            "Pilar 2 — Patrón de fuente",
            "Patrón inseguro que debe detectarse:",
            parent=self,
        )
        if not patron:
            return
        seguro = simpledialog.askstring(
            "Pilar 2 — Patrón de fuente",
            "Patrón seguro opcional (Cancelar para omitir):",
            parent=self,
        )
        nombre = simpledialog.askstring(
            "Pilar 2 — Patrón de fuente",
            "Descripción del control:",
            initialvalue=f"Revisar configuración insegura en {archivo.strip()}",
            parent=self,
        )
        if nombre is None:
            return

        item = {
            "id_control": self._next_p2_id(),
            "nombre": nombre.strip() or "Control de configuración",
            "tipo": "source_contains",
            "archivo": archivo.strip(),
            "patron_inseguro": patron,
            "archivos_fuente": [archivo.strip()],
            "pistas_codigo": [patron[:80]],
        }
        if seguro:
            item["patron_seguro"] = seguro
        self._append_p2(item)

    def _add_p2_cors(self):
        ruta = simpledialog.askstring(
            "Pilar 2 — CORS",
            "Ruta HTTP que se probará:",
            initialvalue="/",
            parent=self,
        )
        if ruta is None:
            return
        metodo = simpledialog.askstring(
            "Pilar 2 — CORS",
            "Método HTTP:",
            initialvalue="GET",
            parent=self,
        )
        if metodo is None:
            return
        cuenta = simpledialog.askstring(
            "Pilar 2 — CORS",
            "Cuenta opcional (Cancelar para ninguna):",
            parent=self,
        )
        item = {
            "id_control": self._next_p2_id(),
            "nombre": "No reflejar orígenes no autorizados con credenciales",
            "tipo": "cors_reflection",
            "metodo": (metodo.strip() or "GET").upper(),
            "ruta": ruta.strip() or "/",
            "headers": {},
        }
        if cuenta:
            item["cuenta"] = cuenta.strip()
        self._append_p2(item)

    def _add_p2_http(self):
        ruta = simpledialog.askstring(
            "Pilar 2 — Política HTTP",
            "Ruta HTTP:",
            initialvalue="/",
            parent=self,
        )
        if ruta is None:
            return
        metodo = simpledialog.askstring(
            "Pilar 2 — Política HTTP",
            "Método HTTP:",
            initialvalue="GET",
            parent=self,
        )
        if metodo is None:
            return
        codes = simpledialog.askstring(
            "Pilar 2 — Política HTTP",
            "Códigos considerados seguros, separados por coma:",
            initialvalue="400,401,403,429",
            parent=self,
        )
        if codes is None:
            return
        try:
            parsed = [int(value.strip()) for value in codes.split(",") if value.strip()]
        except ValueError:
            messagebox.showerror(
                "Códigos inválidos",
                "Usa números separados por coma.",
                parent=self,
            )
            return
        cuenta = simpledialog.askstring(
            "Pilar 2 — Política HTTP",
            "Cuenta opcional (Cancelar para ninguna):",
            parent=self,
        )
        item = {
            "id_control": self._next_p2_id(),
            "nombre": f"Política HTTP para {(metodo.strip() or 'GET').upper()} {ruta.strip() or '/'}",
            "tipo": "http_status_policy",
            "metodo": (metodo.strip() or "GET").upper(),
            "ruta": ruta.strip() or "/",
            "codigos_seguros": parsed or [400, 401, 403, 429],
        }
        if cuenta:
            item["cuenta"] = cuenta.strip()
        self._append_p2(item)

    def _remove_p2(self):
        selected = self.p2_table.selection()
        if not selected or not self.profile:
            return
        indexes = sorted(
            (self.p2_table.index(iid) for iid in selected),
            reverse=True,
        )
        checks = self.profile.get("chequeos_pilar2") or []
        for index in indexes:
            if 0 <= index < len(checks):
                checks.pop(index)
        self._refresh_p2_table()
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
            initialdir=str(default_config_dir()),
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
