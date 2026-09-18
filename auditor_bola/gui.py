"""Interfaz gráfica completa del Auditor Correctivo de Seguridad de Dos Pilares."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import ConfigObjetivo, cargar_config
from .corrective import correction_available
from .cycle import (
    ciclo_correctivo,
    corregir_controles,
    rollback_desde_evidencia,
    verificar_control,
)
from .process_manager import LocalTargetProcess
from .runner import diagnosticar, filas_gui


class AuditorGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Auditor Correctivo de Seguridad — Dos Pilares")
        self.geometry("1360x820")
        self.minsize(1100, 680)

        self.config_path: Path | None = None
        self.cfg: ConfigObjetivo | None = None
        self.target_root: Path | None = None
        self.evidence_base = (Path.cwd() / "evidencias").resolve()
        self.resultado: dict | None = None
        self.proceso: LocalTargetProcess | None = None
        self.busy = False
        self.evidence_paths: list[Path] = []

        self.auto_manage_var = tk.BooleanVar(value=False)

        self._build_header()
        self._build_runtime_bar()
        self._build_notebook()
        self._build_actions()
        self._build_status()
        self._refresh_evidence_list()
        self._refresh_state()

    # ------------------------------------------------------------------
    # Construcción de interfaz
    # ------------------------------------------------------------------
    def _build_header(self):
        frame = ttk.LabelFrame(self, text="Objetivo", padding=10)
        frame.pack(fill="x", padx=10, pady=(10, 5))

        ttk.Button(
            frame,
            text="Perfil de aplicación (.json)",
            command=self._choose_config,
        ).grid(row=0, column=0, sticky="w")
        self.lbl_config = ttk.Label(frame, text="Sin perfil seleccionado")
        self.lbl_config.grid(row=0, column=1, sticky="w", padx=(8, 22))

        ttk.Button(
            frame,
            text="Carpeta de código local",
            command=self._choose_target,
        ).grid(row=0, column=2, sticky="w")
        self.lbl_target = ttk.Label(frame, text="Sin carpeta")
        self.lbl_target.grid(row=0, column=3, sticky="w", padx=(8, 22))

        ttk.Button(
            frame,
            text="Carpeta de evidencias",
            command=self._choose_evidence_base,
        ).grid(row=0, column=4, sticky="w")
        self.lbl_evidence = ttk.Label(frame, text=str(self.evidence_base))
        self.lbl_evidence.grid(row=0, column=5, sticky="w", padx=(8, 0))

        frame.columnconfigure(5, weight=1)

    def _build_runtime_bar(self):
        frame = ttk.LabelFrame(self, text="Ejecución y diagnóstico", padding=8)
        frame.pack(fill="x", padx=10, pady=5)

        self.btn_start = ttk.Button(
            frame, text="Iniciar objetivo", command=self._start_target
        )
        self.btn_start.pack(side="left")

        self.btn_stop = ttk.Button(
            frame, text="Detener", command=self._stop_target
        )
        self.btn_stop.pack(side="left", padx=(6, 0))

        self.btn_restart = ttk.Button(
            frame, text="Reiniciar", command=self._restart_target
        )
        self.btn_restart.pack(side="left", padx=(6, 16))

        ttk.Checkbutton(
            frame,
            text="Gestionar reinicio automáticamente al corregir",
            variable=self.auto_manage_var,
            command=self._refresh_state,
        ).pack(side="left")

        self.lbl_process = ttk.Label(frame, text="Proceso: no administrado")
        self.lbl_process.pack(side="left", padx=16)

        self.btn_diagnose = ttk.Button(
            frame, text="Diagnosticar P1 + P2", command=self._diagnose
        )
        self.btn_diagnose.pack(side="right")

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_results = ttk.Frame(self.notebook)
        self.tab_detail = ttk.Frame(self.notebook)
        self.tab_evidence = ttk.Frame(self.notebook)
        self.tab_log = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_results, text="Resultados")
        self.notebook.add(self.tab_detail, text="Detalle / Corrección")
        self.notebook.add(self.tab_evidence, text="Evidencias")
        self.notebook.add(self.tab_log, text="Registro")

        self._build_results_tab()
        self._build_detail_tab()
        self._build_evidence_tab()
        self._build_log_tab()

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
        self.table = ttk.Treeview(
            self.tab_results, columns=columns, show="headings", height=20
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
        widths = {
            "pilar": 55,
            "id": 125,
            "control": 300,
            "cuenta": 120,
            "estado": 120,
            "correccion": 100,
            "detalle": 440,
        }
        for col in columns:
            self.table.heading(col, text=titles[col])
            self.table.column(col, width=widths[col], anchor="w")

        self.table.tag_configure("hallazgo", background="#f8d7da")
        self.table.tag_configure("ok", background="#d4edda")
        self.table.tag_configure("error", background="#fff3cd")
        self.table.bind("<<TreeviewSelect>>", self._on_result_selected)

        holder = ttk.Frame(self.tab_results)
        holder.pack(fill="both", expand=True)
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
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

    def _build_detail_tab(self):
        self.detail_text = tk.Text(
            self.tab_detail, wrap="word", font=("Consolas", 10)
        )
        scroll = ttk.Scrollbar(
            self.tab_detail,
            orient="vertical",
            command=self.detail_text.yview,
        )
        self.detail_text.configure(yscrollcommand=scroll.set)
        self.detail_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _build_evidence_tab(self):
        left = ttk.Frame(self.tab_evidence, padding=6)
        left.pack(side="left", fill="y")
        right = ttk.Frame(self.tab_evidence, padding=6)
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(left, text="Sesiones").pack(anchor="w")
        self.evidence_list = tk.Listbox(left, width=34, height=20)
        self.evidence_list.pack(fill="y", expand=True, pady=(4, 8))
        self.evidence_list.bind(
            "<<ListboxSelect>>", lambda _e: self._preview_selected_evidence()
        )

        ttk.Button(
            left, text="Actualizar", command=self._refresh_evidence_list
        ).pack(fill="x")
        ttk.Button(
            left, text="Abrir carpeta", command=self._open_selected_evidence
        ).pack(fill="x", pady=(5, 0))
        self.btn_rollback = ttk.Button(
            left,
            text="Revertir esta corrección",
            command=self._rollback_selected_evidence,
        )
        self.btn_rollback.pack(fill="x", pady=(5, 0))

        self.evidence_text = tk.Text(
            right, wrap="word", font=("Consolas", 10)
        )
        scroll = ttk.Scrollbar(
            right, orient="vertical", command=self.evidence_text.yview
        )
        self.evidence_text.configure(yscrollcommand=scroll.set)
        self.evidence_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _build_log_tab(self):
        self.log_text = tk.Text(
            self.tab_log, wrap="word", font=("Consolas", 10), state="disabled"
        )
        scroll = ttk.Scrollbar(
            self.tab_log, orient="vertical", command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _build_actions(self):
        frame = ttk.LabelFrame(self, text="Acciones correctivas", padding=8)
        frame.pack(fill="x", padx=10, pady=5)

        self.btn_verify = ttk.Button(
            frame,
            text="Verificar seleccionado",
            command=self._verify_selected,
        )
        self.btn_verify.pack(side="left")

        self.btn_correct = ttk.Button(
            frame,
            text="Corregir seleccionado",
            command=self._correct_selected,
        )
        self.btn_correct.pack(side="left", padx=(6, 0))

        self.btn_correct_all = ttk.Button(
            frame,
            text="Corregir todos los hallazgos corregibles",
            command=self._correct_all,
        )
        self.btn_correct_all.pack(side="left", padx=(6, 0))

        self.btn_save = ttk.Button(
            frame,
            text="Guardar reporte actual",
            command=self._save_report,
        )
        self.btn_save.pack(side="right")

        ttk.Button(
            frame,
            text="Ver perfil JSON",
            command=self._show_profile,
        ).pack(side="right", padx=(0, 6))

    def _build_status(self):
        frame = ttk.Frame(self, padding=(10, 4))
        frame.pack(fill="x")
        self.lbl_summary = ttk.Label(frame, text="Sin diagnóstico.")
        self.lbl_summary.pack(side="left")
        self.lbl_status = ttk.Label(frame, text="Listo.")
        self.lbl_status.pack(side="right")

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
                self.after(0, lambda: self._background_error(exc))
                return
            self.after(0, lambda: self._background_success(result, on_success))

        threading.Thread(target=worker, daemon=True).start()

    def _background_success(self, result, callback):
        self._set_busy(False, "Listo.")
        self._refresh_process_state()
        callback(result)

    def _background_error(self, exc: Exception):
        self._set_busy(False, "Error.")
        self._refresh_process_state()
        self._log(f"ERROR: {exc}")
        messagebox.showerror("Operación no completada", str(exc))

    def _set_busy(self, busy: bool, status: str):
        self.busy = busy
        self.lbl_status.configure(text=status)
        self._refresh_state()

    def _selected_values(self):
        selected = self.table.selection()
        if not selected:
            return None
        return self.table.item(selected[0], "values")

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

    def _reiniciar_callback(self, auto_manage: bool):
        if not self.cfg or not self.target_root:
            return None

        if auto_manage:
            if not self.cfg.runtime.comando_inicio:
                return None
            if self.proceso is None:
                self.proceso = LocalTargetProcess(
                    self.target_root, self.cfg.runtime
                )
            if not self.proceso.is_running():
                self.proceso.start()
            return self.proceso.restart

        if self.proceso and self.proceso.is_running():
            return self.proceso.restart
        return None

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
        corregibles = self._correctable_findings()

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
            state=normal_or_disabled(bool(corregibles and has_target))
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

        self._refresh_process_state()

    def _refresh_process_state(self):
        if self._process_running():
            self.lbl_process.configure(text="Proceso: EN EJECUCIÓN")
        elif self.proceso:
            self.lbl_process.configure(text="Proceso: DETENIDO")
        else:
            self.lbl_process.configure(text="Proceso: no administrado")

    def _correctable_findings(self) -> list[str]:
        if not self.resultado or not self.cfg:
            return []
        controls: list[str] = []
        for row in filas_gui(self.resultado):
            control_id = row["id"]
            if (
                row["estado"] == "HALLAZGO"
                and correction_available(self.cfg, control_id)
                and control_id not in controls
            ):
                controls.append(control_id)
        return controls

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
            self.proceso.start()
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

            self.table.insert(
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

        r = result["resumen"]
        total = (
            r["bola_confirmados"]
            + r["acceso_vulnerable"]
            + r["agente_vulnerable"]
            + r["pilar2_hallazgos"]
        )
        self.lbl_summary.configure(
            text=(
                f"Sistema: {result['sistema']} | "
                f"Hallazgos: {total} | Errores: {r['errores']} | "
                f"Corregibles: {len(self._correctable_findings())}"
            )
        )
        self.lbl_status.configure(text="Diagnóstico completo.")
        self._log(
            f"Diagnóstico: {total} hallazgo(s), "
            f"{r['errores']} error(es)."
        )
        self._refresh_state()

    def _verify_selected(self):
        control = self._selected_control()
        if not control or not self.cfg:
            return

        def task():
            return verificar_control(
                self.cfg,
                control,
                self.target_root,
                evidence_base=self.evidence_base,
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

        auto_manage = self.auto_manage_var.get()

        def task():
            reiniciar = self._reiniciar_callback(auto_manage)
            return ciclo_correctivo(
                self.cfg,
                control,
                self.target_root,
                evidence_base=self.evidence_base,
                reiniciar=reiniciar,
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
            messagebox.showinfo(
                "Ciclo correctivo",
                f"{control}: {estado}",
            )
            self._diagnose()

        self._run_background(
            task, done, f"Corrigiendo y verificando {control}…"
        )

    def _correct_all(self):
        if not self.cfg or not self.target_root:
            return
        controls = self._correctable_findings()
        if not controls:
            messagebox.showinfo(
                "Correcciones",
                "No hay hallazgos con receta correctiva disponible.",
            )
            return

        if not messagebox.askyesno(
            "Corregir todos",
            (
                f"Se ejecutarán {len(controls)} ciclo(s) correctivo(s):\n\n"
                + "\n".join(f"• {item}" for item in controls)
                + "\n\nCada cambio tendrá backup, verificación y rollback "
                  "automático si falla. ¿Continuar?"
            ),
        ):
            return

        auto_manage = self.auto_manage_var.get()

        def task():
            reiniciar = self._reiniciar_callback(auto_manage)
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
                lines.append(f"{control}: {estado}")
                if item.get("evidencia"):
                    last_evidence = Path(item["evidencia"])
                if item.get("error"):
                    self._log(f"{control}: ERROR - {item['error']}")
                else:
                    self._log(f"{control}: {estado}")
            self._refresh_evidence_list(select_path=last_evidence)
            messagebox.showinfo(
                "Corrección múltiple",
                "\n".join(lines),
            )
            self._diagnose()

        self._run_background(
            task,
            done,
            f"Corrigiendo {len(controls)} control(es)…",
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
        window.geometry("900x650")
        widget = tk.Text(window, wrap="none", font=("Consolas", 10))
        widget.insert("1.0", text)
        widget.configure(state="disabled")
        widget.pack(fill="both", expand=True)

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
