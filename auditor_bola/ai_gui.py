"""Mixin de interfaz para generación y selección humana de recetas IA."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from .ai_preview import preview_recipe
from .ai_recipes import (
    AIRecipeProposal,
    DEFAULT_MODEL,
    generar_tres_recetas,
    guardar_seleccion_ia,
    guardar_sesion_ia,
    inferir_archivo_control,
    propuesta_a_correccion,
)
from .cycle import ciclo_correctivo


class AIAssistantMixin:
    """Añade a la GUI principal un flujo humano-en-el-bucle para recetas IA."""

    def _build_ai_tab(self):
        self.ai_source_relative: str | None = None
        self.ai_proposals: list[AIRecipeProposal] = []
        self.ai_session_dir: Path | None = None
        self.ai_current_recipe = None
        self.ai_model_var = tk.StringVar(
            value=os.getenv("AUDITOR_AI_MODEL", DEFAULT_MODEL)
        )

        outer = ttk.Frame(self.tab_ai, padding=8)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(2, weight=1)
        outer.columnconfigure(0, weight=1)

        header = ttk.LabelFrame(
            outer,
            text="Hallazgo y contexto para IA",
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

        ttk.Label(header, text="Modelo:").grid(
            row=2, column=0, sticky="w", padx=(0, 6), pady=(4, 0)
        )
        ttk.Entry(
            header, textvariable=self.ai_model_var, width=28
        ).grid(row=2, column=1, sticky="w", pady=(4, 0))

        self.lbl_ai_key = ttk.Label(
            header,
            text=(
                "OPENAI_API_KEY: configurada"
                if os.getenv("OPENAI_API_KEY")
                else "OPENAI_API_KEY: no configurada"
            ),
        )
        self.lbl_ai_key.grid(
            row=2, column=2, sticky="e", padx=(8, 0), pady=(4, 0)
        )

        buttons = ttk.Frame(outer)
        buttons.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        buttons.columnconfigure(2, weight=1)

        self.btn_ai_generate = ttk.Button(
            buttons,
            text="Generar 3 recetas con IA",
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
            text="Guardar receta en perfil",
            command=self._save_ai_recipe_to_profile,
        )
        self.btn_ai_save.grid(row=0, column=2, sticky="ew", padx=3)

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

        self._refresh_ai_state()

    def _refresh_ai_state(self):
        if not hasattr(self, "btn_ai_generate"):
            return

        has_control = bool(self._selected_control())
        has_target = self.target_root is not None
        has_source = bool(self.ai_source_relative)
        has_proposal = self.ai_current_recipe is not None
        api_key = bool(os.getenv("OPENAI_API_KEY"))
        enabled = lambda ok: "normal" if ok and not self.busy else "disabled"

        self.btn_ai_generate.configure(
            state=enabled(has_control and has_target and has_source and api_key)
        )
        self.btn_ai_apply.configure(
            state=enabled(has_proposal and has_target)
        )
        self.btn_ai_save.configure(
            state=enabled(has_proposal and self.config_path is not None)
        )
        if hasattr(self, "btn_ai_open"):
            self.btn_ai_open.configure(
                state=enabled(has_control and has_target)
            )

        self.lbl_ai_key.configure(
            text=(
                "OPENAI_API_KEY: configurada"
                if api_key
                else "OPENAI_API_KEY: no configurada"
            )
        )

    def _ai_sync_selected_control(self):
        if not hasattr(self, "lbl_ai_control"):
            return

        control = self._selected_control()
        self.lbl_ai_control.configure(text=control or "Ninguno")
        self.ai_current_recipe = None
        self.ai_proposals = []
        self.ai_session_dir = None

        for item in self.ai_table.get_children():
            self.ai_table.delete(item)
        self.ai_detail_text.delete("1.0", "end")

        if self.cfg and control and self.target_root:
            inferred = inferir_archivo_control(self.cfg, control)
            if inferred and (self.target_root / inferred).exists():
                self.ai_source_relative = inferred
                self.lbl_ai_source.configure(text=inferred)
            else:
                self.ai_source_relative = None
                self.lbl_ai_source.configure(
                    text="Seleccione el archivo relacionado con el hallazgo"
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
        self.lbl_ai_source.configure(text=self.ai_source_relative)
        self._refresh_ai_state()

    def _current_finding_data(self) -> tuple[str, str, str]:
        values = self._selected_values()
        if not values:
            raise RuntimeError("No hay un hallazgo seleccionado.")
        return str(values[1]), str(values[2]), str(values[6])

    def _generate_ai_recipes(self):
        if not self.cfg or not self.target_root or not self.ai_source_relative:
            return

        control, descripcion, detalle = self._current_finding_data()
        source_path = self.target_root / self.ai_source_relative
        model = self.ai_model_var.get().strip() or DEFAULT_MODEL

        def task():
            source_text = source_path.read_text(encoding="utf-8")
            proposals, context = generar_tres_recetas(
                self.cfg,
                control_id=control,
                descripcion=descripcion,
                detalle=detalle,
                source_relative=self.ai_source_relative,
                source_text=source_text,
                model=model,
            )
            session = guardar_sesion_ia(
                self.evidence_base,
                contexto=context,
                propuestas=proposals,
                model=model,
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

            self._log(
                f"IA: 3 propuestas generadas para {control}. "
                f"Evidencia: {session}"
            )
            self.notebook.select(self.tab_ai)
            self.ai_table.selection_set("0")
            self.ai_table.focus("0")
            self._on_ai_proposal_selected()
            self._refresh_ai_state()

        self._run_background(
            task,
            done,
            f"Generando 3 recetas IA para {control}…",
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

        if not messagebox.askyesno(
            "Aplicar receta generada por IA",
            (
                f"Control: {control}\n"
                f"Propuesta: {proposal.titulo}\n"
                f"Enfoque: {proposal.enfoque}\n"
                f"Riesgo declarado: {proposal.riesgo}\n\n"
                "La IA solo propuso la receta. El auditor hará backup, "
                "aplicación, verificación y rollback si corresponde.\n\n"
                "¿Deseas continuar?"
            ),
        ):
            return

        def task():
            selected_proposal, selected_control = self._install_ai_recipe_in_memory()

            if self.ai_session_dir:
                guardar_seleccion_ia(
                    self.ai_session_dir,
                    propuesta=selected_proposal,
                    correccion=self.ai_current_recipe,
                )

            reiniciar = self._prepare_restart_callback([selected_control])
            result = ciclo_correctivo(
                self.cfg,
                selected_control,
                self.target_root,
                evidence_base=self.evidence_base,
                reiniciar=reiniciar,
            )

            if self.ai_session_dir:
                guardar_seleccion_ia(
                    self.ai_session_dir,
                    propuesta=selected_proposal,
                    correccion=self.ai_current_recipe,
                    resultado=result,
                )
            return result

        def done(result):
            estado = result.get("estado_final")
            self._log(
                f"Receta IA {proposal.id} aplicada a {control}: {estado}"
            )
            messagebox.showinfo(
                "Resultado de receta IA",
                f"{control}: {estado}",
            )
            self._diagnose()

        self._run_background(
            task,
            done,
            f"Aplicando receta IA {proposal.id}…",
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
            "Guardar receta en perfil",
            (
                f"Se guardará la propuesta {proposal.id} como receta "
                f"persistente de {control} en:\n\n{self.config_path}\n\n"
                "¿Continuar?"
            ),
        ):
            return

        raw_text = self.config_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        corrections = [
            item
            for item in data.get("correcciones", [])
            if item.get("control_id") != control
        ]
        corrections.append(asdict(self.ai_current_recipe))
        data["correcciones"] = corrections

        if self.ai_session_dir:
            (self.ai_session_dir / "perfil_antes.json").write_text(
                raw_text, encoding="utf-8"
            )

        self.config_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        self._install_ai_recipe_in_memory()

        if self.ai_session_dir:
            (self.ai_session_dir / "perfil_despues.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        self._log(
            f"Receta IA {proposal.id} guardada en perfil para {control}."
        )
        messagebox.showinfo(
            "Perfil actualizado",
            f"La receta de {control} quedó guardada en el perfil.",
        )
        self._refresh_ai_state()
