"""Interfaz gráfica del Auditor Correctivo de Seguridad de Dos Pilares."""

from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import ConfigObjetivo, cargar_config
from .corrective import correction_available
from .cycle import ciclo_correctivo
from .process_manager import LocalTargetProcess
from .runner import diagnosticar, filas_gui


class AuditorGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Auditor Correctivo de Seguridad — Dos Pilares")
        self.geometry("1180x720")
        self.minsize(980, 600)

        self.config_path: Path | None = None
        self.cfg: ConfigObjetivo | None = None
        self.target_root: Path | None = None
        self.resultado: dict | None = None
        self.proceso: LocalTargetProcess | None = None

        self._top()
        self._summary()
        self._table()
        self._bottom()

    def _top(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="x")

        ttk.Button(
            frame,
            text="1. Perfil de aplicación (.json)",
            command=self._choose_config,
        ).pack(side="left")
        self.lbl_config = ttk.Label(frame, text="Sin perfil")
        self.lbl_config.pack(side="left", padx=8)

        ttk.Button(
            frame,
            text="2. Carpeta de código local",
            command=self._choose_target,
        ).pack(side="left", padx=(16, 0))
        self.lbl_target = ttk.Label(frame, text="Sin carpeta")
        self.lbl_target.pack(side="left", padx=8)

        self.btn_run = ttk.Button(
            frame,
            text="3. Diagnosticar",
            command=self._run,
            state="disabled",
        )
        self.btn_run.pack(side="right")

    def _summary(self):
        self.lbl_summary = ttk.Label(
            self,
            text="",
            font=("TkDefaultFont", 11, "bold"),
            padding=(10, 4),
        )
        self.lbl_summary.pack(fill="x")

    def _table(self):
        columns = ("pilar", "id", "control", "cuenta", "estado", "detalle")
        self.table = ttk.Treeview(
            self, columns=columns, show="headings", height=20
        )
        titles = {
            "pilar": "Pilar",
            "id": "Control",
            "control": "Descripción",
            "cuenta": "Cuenta",
            "estado": "Estado",
            "detalle": "Detalle",
        }
        widths = {
            "pilar": 55,
            "id": 120,
            "control": 300,
            "cuenta": 130,
            "estado": 125,
            "detalle": 390,
        }
        for col in columns:
            self.table.heading(col, text=titles[col])
            self.table.column(col, width=widths[col], anchor="w")

        self.table.tag_configure("hallazgo", background="#f8d7da")
        self.table.tag_configure("ok", background="#d4edda")
        self.table.tag_configure("error", background="#fff3cd")
        self.table.bind(
            "<<TreeviewSelect>>", lambda _e: self._update_buttons()
        )

        holder = ttk.Frame(self)
        holder.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        scroll = ttk.Scrollbar(
            holder, orient="vertical", command=self.table.yview
        )
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _bottom(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="x")

        self.lbl_status = ttk.Label(frame, text="Listo.")
        self.lbl_status.pack(side="left")

        self.btn_save = ttk.Button(
            frame,
            text="Guardar evidencia JSON",
            command=self._save,
            state="disabled",
        )
        self.btn_save.pack(side="right")

        self.btn_correct = ttk.Button(
            frame,
            text="Corregir seleccionado",
            command=self._correct,
            state="disabled",
        )
        self.btn_correct.pack(side="right", padx=8)

        self.btn_start = ttk.Button(
            frame,
            text="Iniciar objetivo local",
            command=self._start_target,
            state="disabled",
        )
        self.btn_start.pack(side="right", padx=8)

    def _choose_config(self):
        path = filedialog.askopenfilename(
            title="Seleccione el perfil de la aplicación",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            cfg = cargar_config(path)
        except Exception as exc:
            messagebox.showerror("Configuración inválida", str(exc))
            return

        self.config_path = Path(path)
        self.cfg = cfg
        self.lbl_config.configure(
            text=f"{cfg.sistema} {cfg.version_objetivo or ''}".strip()
        )
        self._update_ready()

    def _choose_target(self):
        path = filedialog.askdirectory(
            title="Seleccione la copia local del código objetivo"
        )
        if not path:
            return
        self.target_root = Path(path)
        self.lbl_target.configure(text=self.target_root.name)
        self._update_ready()

    def _update_ready(self):
        self.btn_run.configure(
            state="normal" if self.cfg else "disabled"
        )
        puede_iniciar = bool(
            self.cfg
            and self.target_root
            and self.cfg.runtime.comando_inicio
        )
        self.btn_start.configure(
            state="normal" if puede_iniciar else "disabled"
        )
        self._update_buttons()

    def _start_target(self):
        if not self.target_root or not self.cfg:
            return
        try:
            if self.proceso:
                self.proceso.stop()
            self.proceso = LocalTargetProcess(
                self.target_root, self.cfg.runtime
            )
            self.proceso.start()
            self.lbl_status.configure(
                text=f"{self.cfg.sistema} iniciado por el auditor."
            )
        except Exception as exc:
            messagebox.showerror("No se pudo iniciar", str(exc))

    def _run(self):
        if not self.cfg:
            return
        self.btn_run.configure(state="disabled")
        self.lbl_status.configure(text="Diagnosticando…")
        threading.Thread(
            target=self._run_thread, daemon=True
        ).start()

    def _run_thread(self):
        try:
            result = diagnosticar(self.cfg, self.target_root)
        except Exception as exc:
            self.after(0, lambda: self._error(exc))
            return
        self.after(0, lambda: self._show(result))

    def _error(self, exc):
        self.btn_run.configure(state="normal")
        self.lbl_status.configure(text="Error.")
        messagebox.showerror("Auditoría", str(exc))

    def _show(self, result):
        self.resultado = result
        for item in self.table.get_children():
            self.table.delete(item)

        rows = filas_gui(result)
        for row in rows:
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
                f"Hallazgos confirmados: {total} | errores: {r['errores']}"
            )
        )
        self.lbl_status.configure(text="Diagnóstico completo.")
        self.btn_run.configure(state="normal")
        self.btn_save.configure(state="normal")
        self._update_buttons()

    def _selected_control(self):
        selected = self.table.selection()
        if not selected:
            return None
        values = self.table.item(selected[0], "values")
        return values[1] if values else None

    def _update_buttons(self):
        control = self._selected_control()
        enabled = bool(
            control
            and self.target_root
            and self.cfg
            and correction_available(self.cfg, control)
        )
        self.btn_correct.configure(
            state="normal" if enabled else "disabled"
        )

    def _correct(self):
        control = self._selected_control()
        if not control or not self.target_root or not self.cfg:
            return

        if not messagebox.askyesno(
            "Corrección controlada",
            (
                f"Aplicar y verificar {control} sobre la copia local "
                f"de {self.cfg.sistema}?"
            ),
        ):
            return

        try:
            reiniciar = self.proceso.restart if self.proceso else None
            manifest = ciclo_correctivo(
                self.cfg,
                control,
                self.target_root,
                reiniciar=reiniciar,
            )
            messagebox.showinfo(
                "Resultado",
                f"{control}: {manifest['estado_final']}",
            )
            self._run()
        except Exception as exc:
            messagebox.showerror("Corrección", str(exc))

    def _save(self):
        if not self.resultado:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        Path(path).write_text(
            json.dumps(self.resultado, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.lbl_status.configure(
            text=f"Evidencia guardada: {path}"
        )

    def destroy(self):
        if self.proceso:
            self.proceso.stop()
        super().destroy()


def main():
    AuditorGUI().mainloop()


if __name__ == "__main__":
    main()
