"""Página de biblioteca de conocimiento correctivo."""

from __future__ import annotations

import json

import customtkinter as ctk

from ...recipe_library import biblioteca_por_defecto
from ...remediation_knowledge import knowledge_root
from ..components.cards import ActionButton, MetricCard, SectionCard
from ..theme import COLORS, FONT_FAMILY


class KnowledgePage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=COLORS["bg"])
        self.app = app
        self.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(
            self,
            text="Recetas y conocimiento",
            text_color=COLORS["text"],
            font=(FONT_FAMILY, 24, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(2, 12))

        self.knowledge_card = MetricCard(
            self,
            "Medicinas semánticas",
            "0",
            "Verificadas y reutilizables",
        )
        self.knowledge_card.grid(row=1, column=0, sticky="ew", padx=(0, 5))

        self.recipe_card = MetricCard(
            self,
            "Parches concretos",
            "0",
            "Recetas exactas",
        )
        self.recipe_card.grid(row=1, column=1, sticky="ew", padx=5)

        self.success_card = MetricCard(
            self,
            "Reutilización",
            "0",
            "Usos exitosos acumulados",
        )
        self.success_card.grid(row=1, column=2, sticky="ew", padx=(5, 0))

        actions = SectionCard(
            self,
            "Bibliotecas",
            "La medicina describe la propiedad de seguridad; el parche exacto conserva una implementación concreta.",
        )
        actions.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        actions.grid_columnconfigure((0, 1, 2), weight=1)

        ActionButton(
            actions,
            "Ver medicinas compatibles",
            app._open_knowledge_window,
            "primary",
        ).grid(row=2, column=0, sticky="ew", padx=(16, 5), pady=(10, 16))

        ActionButton(
            actions,
            "Ver parches exactos",
            app._open_recipe_library_window,
        ).grid(row=2, column=1, sticky="ew", padx=5, pady=(10, 16))

        ActionButton(
            actions,
            "Importar recetas / medicinas",
            app._import_recipes,
        ).grid(row=2, column=2, sticky="ew", padx=(5, 16), pady=(10, 16))

    def refresh(self):
        knowledge_files = list(knowledge_root().glob("*/*.json")) if knowledge_root().exists() else []
        recipe_root = biblioteca_por_defecto()
        recipe_files = []
        if recipe_root.exists():
            for path in recipe_root.glob("*/*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if data.get("tipo") == "conocimiento_correctivo_semantico":
                    continue
                recipe_files.append((path, data))

        usages = 0
        for path in knowledge_files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                usages += int(data.get("usos_exitosos", 0))
            except Exception:
                pass

        self.knowledge_card.set(str(len(knowledge_files)), "Medicinas almacenadas")
        self.recipe_card.set(str(len(recipe_files)), "Parches concretos")
        self.success_card.set(str(usages), "Usos exitosos")
