"""Página de reportes y métricas."""

from __future__ import annotations

import customtkinter as ctk

from ..components.cards import ActionButton, MetricCard, SectionCard
from ..theme import COLORS, FONT_FAMILY


class ReportsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=COLORS["bg"])
        self.app = app
        for column in range(3):
            self.grid_columnconfigure(column, weight=1)

        ctk.CTkLabel(
            self,
            text="Reportes y resultados",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 24, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(2, 12))

        self.controls = MetricCard(self, "Controles", "0", "Evaluados")
        self.controls.grid(row=1, column=0, sticky="ew", padx=(0, 5))
        self.findings = MetricCard(self, "Hallazgos", "0", "P1 + P2")
        self.findings.grid(row=1, column=1, sticky="ew", padx=5)
        self.corrected = MetricCard(self, "Correcciones", "0", "Verificadas")
        self.corrected.grid(row=1, column=2, sticky="ew", padx=(5, 0))

        actions = SectionCard(
            self,
            "Exportación",
            "Guarda resultados técnicos o genera material redactado para el artículo.",
        )
        actions.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)

        app.btn_save = ActionButton(
            actions,
            "Guardar reporte JSON",
            app._save_report,
            "primary",
        )
        app.btn_save.grid(row=2, column=0, sticky="ew", padx=(16, 5), pady=(10, 16))

        ActionButton(
            actions,
            "Exportar evidencia para artículo",
            app._export_article_evidence,
        ).grid(row=2, column=1, sticky="ew", padx=(5, 16), pady=(10, 16))

    def refresh(self):
        result = self.app.resultado
        if not result:
            self.controls.set("0", "Sin diagnóstico")
            self.findings.set("0", "P1 0 · P2 0")
            self.corrected.set("0", "Sin evidencia")
            return

        from ...runner import filas_gui

        rows = filas_gui(result)
        p1 = sum(1 for row in rows if row["pilar"] == "P1" and row["estado"] == "HALLAZGO")
        p2 = sum(1 for row in rows if row["pilar"] == "P2" and row["estado"] == "HALLAZGO")
        self.controls.set(str(len(rows)), "Controles normalizados")
        self.findings.set(str(p1 + p2), f"P1 {p1} · P2 {p2}")

        corrected = 0
        if self.app.evidence_base.exists():
            for session in self.app.evidence_base.iterdir():
                manifest = session / "manifest.json"
                if not manifest.exists():
                    continue
                try:
                    import json
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    if data.get("estado_final") == "CORREGIDO":
                        corrected += 1
                except Exception:
                    pass
        self.corrected.set(str(corrected), "Sesiones CORREGIDO")
