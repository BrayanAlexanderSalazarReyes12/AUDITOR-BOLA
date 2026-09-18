"""Interfaz gráfica de escritorio del auditor genérico de BOLA.

Recibe la configuración de CUALQUIER sistema (un archivo YAML, ver
config/*.json para ejemplos), lo audita, y muestra los resultados en una
tabla. No conoce ningún sistema en particular: todo llega por el YAML
que el usuario selecciona.

Uso:
    python -m auditor_bola.gui
"""

from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import cargar_config
from .engine import auditar


class AuditorGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Auditor genérico de BOLA — recibe cualquier sistema")
        self.geometry("980x620")
        self.minsize(820, 480)

        self.config_path: Path | None = None
        self.hallazgos: list[dict] = []

        self._construir_barra_superior()
        self._construir_resumen()
        self._construir_tabla()
        self._construir_barra_inferior()

    # ------------------------------------------------------------------
    def _construir_barra_superior(self):
        marco = ttk.Frame(self, padding=10)
        marco.pack(fill="x")

        ttk.Button(
            marco, text="1. Elegir configuración (.json)", command=self._elegir_config
        ).pack(side="left")

        self.lbl_config = ttk.Label(marco, text="ningún archivo seleccionado", foreground="#666")
        self.lbl_config.pack(side="left", padx=10)

        self.btn_auditar = ttk.Button(
            marco, text="2. Ejecutar auditoría", command=self._ejecutar_auditoria, state="disabled"
        )
        self.btn_auditar.pack(side="right")

    def _construir_resumen(self):
        self.lbl_resumen = ttk.Label(self, text="", font=("TkDefaultFont", 11, "bold"), padding=(10, 4))
        self.lbl_resumen.pack(fill="x")

    def _construir_tabla(self):
        columnas = ("endpoint", "metodo", "cuenta", "rol", "esperado", "real", "http", "bola")
        self.tabla = ttk.Treeview(self, columns=columnas, show="headings", height=16)
        titulos = {
            "endpoint": "Endpoint", "metodo": "Método", "cuenta": "Cuenta", "rol": "Rol",
            "esperado": "Acceso esperado", "real": "Acceso real", "http": "HTTP",
            "bola": "¿BOLA confirmado?",
        }
        anchos = {"endpoint": 220, "metodo": 70, "cuenta": 120, "rol": 90,
                  "esperado": 110, "real": 90, "http": 60, "bola": 130}
        for c in columnas:
            self.tabla.heading(c, text=titulos[c])
            self.tabla.column(c, width=anchos[c], anchor="center" if c != "endpoint" else "w")

        self.tabla.tag_configure("bola", background="#f8d7da")
        self.tabla.tag_configure("ok", background="#d4edda")

        cont = ttk.Frame(self)
        cont.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        scroll = ttk.Scrollbar(cont, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _construir_barra_inferior(self):
        marco = ttk.Frame(self, padding=10)
        marco.pack(fill="x")
        self.btn_guardar = ttk.Button(
            marco, text="Guardar evidencia (.json)", command=self._guardar_evidencia, state="disabled"
        )
        self.btn_guardar.pack(side="right")
        self.lbl_estado = ttk.Label(marco, text="Listo.", foreground="#666")
        self.lbl_estado.pack(side="left")

    # ------------------------------------------------------------------
    def _elegir_config(self):
        ruta = filedialog.askopenfilename(
            title="Elegir configuración del sistema a auditar",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
        )
        if not ruta:
            return
        try:
            cfg = cargar_config(ruta)
        except Exception as exc:  # noqa: BLE001 - mostramos cualquier error de config al usuario
            messagebox.showerror("Configuración inválida", str(exc))
            return

        self.config_path = Path(ruta)
        self.lbl_config.configure(
            text=f"{self.config_path.name} — sistema: {cfg.sistema} "
                 f"({len(cfg.cuentas)} cuentas, {len(cfg.endpoints)} endpoints)"
        )
        self.btn_auditar.configure(state="normal")
        self.lbl_estado.configure(text="Configuración cargada. Lista para auditar.")

    def _ejecutar_auditoria(self):
        self.btn_auditar.configure(state="disabled")
        self.lbl_estado.configure(text="Auditando… (puede tardar unos segundos)")
        for fila in self.tabla.get_children():
            self.tabla.delete(fila)
        threading.Thread(target=self._auditar_en_hilo, daemon=True).start()

    def _auditar_en_hilo(self):
        try:
            cfg = cargar_config(self.config_path)
            hallazgos = auditar(cfg)
        except Exception as exc:  # noqa: BLE001
            self.after(0, lambda: self._mostrar_error_auditoria(exc))
            return
        self.after(0, lambda: self._mostrar_resultados(cfg.sistema, hallazgos))

    def _mostrar_error_auditoria(self, exc: Exception):
        self.btn_auditar.configure(state="normal")
        self.lbl_estado.configure(text="Error durante la auditoría.")
        messagebox.showerror(
            "No se pudo completar la auditoría",
            f"{exc}\n\n¿El sistema objetivo está corriendo y accesible en la base_url del YAML?",
        )

    def _mostrar_resultados(self, sistema: str, hallazgos: list):
        self.hallazgos = [h.as_dict() for h in hallazgos]
        confirmados = [h for h in self.hallazgos if h["confirmado_bola"]]

        for h in self.hallazgos:
            tag = "bola" if h["confirmado_bola"] else "ok"
            self.tabla.insert("", "end", values=(
                h["endpoint"], h["metodo"], h["cuenta"], h["rol"],
                "sí" if h["acceso_esperado"] else "no",
                "sí" if h["acceso_real"] else "no",
                h["http_status"],
                "SÍ — BOLA" if h["confirmado_bola"] else "no",
            ), tags=(tag,))

        color = "#c0392b" if confirmados else "#1e7d32"
        self.lbl_resumen.configure(
            text=f"Sistema: {sistema}  |  Pruebas: {len(self.hallazgos)}  |  "
                 f"BOLA confirmados: {len(confirmados)}",
            foreground=color,
        )
        self.btn_auditar.configure(state="normal")
        self.btn_guardar.configure(state="normal" if self.hallazgos else "disabled")
        self.lbl_estado.configure(text="Auditoría completa.")

    def _guardar_evidencia(self):
        ruta = filedialog.asksaveasfilename(
            title="Guardar evidencia", defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not ruta:
            return
        confirmados = [h for h in self.hallazgos if h["confirmado_bola"]]
        salida = {
            "total_pruebas": len(self.hallazgos),
            "bola_confirmados": len(confirmados),
            "hallazgos": self.hallazgos,
        }
        Path(ruta).write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
        self.lbl_estado.configure(text=f"Evidencia guardada en {ruta}")


def main():
    AuditorGUI().mainloop()


if __name__ == "__main__":
    main()
