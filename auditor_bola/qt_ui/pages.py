                else ""
            )
        )
        self.p2.set_value(f"{p2} hallazgo(s)")
        self.total.set_value(
            (
                "Seguro"
                if rows and p1 + p2 == 0 and matrix_vulnerable == 0
                else (
                    f"{p1 + p2} hallazgo(s)"
                    if rows
                    else "Sin diagnóstico"
                )
            ),
            (
                f"{len(rows)} control(es)"
                + (
                    f" · {matrix_vulnerable} vulnerable(s) en matriz"
                    if matrix_vulnerable
                    else ""
                )
                if rows
                else "P1 + P2"
            ),
        )


class AIPage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.target_row: dict | None = None
        self.source_path: Path | None = None
        self.proposals: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("Correcciones con IA")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Gemma propone; Aegis aplica con backup, verifica y revierte si no funciona."
        )
        subtitle.setObjectName("Subheading")
        layout.addWidget(subtitle)

        context = Card()
        context_l = QGridLayout(context)
        context_l.setContentsMargins(16, 14, 16, 14)
        context_l.setHorizontalSpacing(12)
        context_l.setVerticalSpacing(7)

        self.control_label = QLabel("Ningún hallazgo seleccionado")
        self.control_label.setObjectName("SectionTitle")
        self.source_label = QLabel("Archivo: no seleccionado")
        self.source_label.setObjectName("Muted")
        self.provider_label = QLabel("IA: comprobando…")
        self.provider_label.setObjectName("Muted")

        choose = QPushButton("Cambiar archivo")
        choose.clicked.connect(self._choose_source)
        generate = PrimaryButton("Generar 3 recetas")
        generate.clicked.connect(self._generate)

        context_l.addWidget(self.control_label, 0, 0, 1, 2)
        context_l.addWidget(self.source_label, 1, 0, 1, 2)
        context_l.addWidget(self.provider_label, 2, 0)
        context_l.addWidget(choose, 2, 1)
        context_l.addWidget(generate, 3, 0, 1, 2)
        layout.addWidget(context)

        split = QSplitter()
        split.setOrientation(Qt.Orientation.Horizontal)

        left = Card()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(14, 12, 14, 12)
        left_l.addWidget(
            SectionHeader(
                "Alternativas",
                "Mínima, estructural y alternativa.",
            )
        )
        self.list = QListWidget()
        self.list.setObjectName("AIProposalList")
        self.list.setWordWrap(True)
        self.list.setSpacing(8)
        self.list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.list.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.list.currentRowChanged.connect(self._show_proposal)
        left_l.addWidget(self.list, 1)

        self.apply_btn = PrimaryButton("Aplicar propuesta y verificar")
        self.apply_btn.clicked.connect(self._apply)
        self.apply_btn.setEnabled(False)
        left_l.addWidget(self.apply_btn)

        right = Card()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(14, 12, 14, 12)
        right_l.addWidget(
            SectionHeader(
                "Detalle de la receta",
                "La propuesta todavía no modifica el código.",
            )
        )
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        right_l.addWidget(self.detail, 1)

        split.addWidget(left)
        split.addWidget(right)
        left.setMinimumWidth(410)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 7)
        split.setSizes([500, 700])
        layout.addWidget(split, 1)

        self.refresh_provider()

    def refresh_provider(self):
        enabled, name = self.controller.ai_status()
        self.provider_label.setText(
            f"● IA conectada · {name}"
            if enabled
            else "○ IA no configurada"
        )
        self.provider_label.setStyleSheet(
            f"color:{COLORS['success'] if enabled else COLORS['muted']};"
        )

    def set_target(self, row: dict):
        self.target_row = dict(row)
        self.source_path = None
        self.proposals = []
        self.list.clear()
        self.detail.clear()
        self.control_label.setText(
            f"{row.get('id')} · {row.get('control')}"
        )

        resolution = self.controller.resolve_ai_source(row)
        resolved = resolution.get("path")
        if resolved:
            self.source_path = Path(str(resolved))
            recipe_state = (
                "receta existente"
                if resolution.get("tiene_receta")
                else "sin receta local; listo para buscar con IA"
            )
            self.source_label.setText(
                "Archivo cargado automáticamente: "
                f"{resolution.get('archivo')} · "
                f"{recipe_state} · "
                f"confianza {resolution.get('confianza')} · "
                f"{resolution.get('origen')}"
            )
        else:
            candidates = resolution.get("candidatos") or []
            hint = ""
            if candidates:
                hint = (
                    " · candidato: "
                    f"{candidates[0].get('archivo')}"
                )
            self.source_label.setText(
                "Archivo: no localizado automáticamente"
                + hint
                + " · usa Cambiar archivo"
            )

    def _choose_source(self):
        initial = (
            str(self.controller.target_root)
            if self.controller.target_root
            else ""
        )
        selected, _filter = styled_open_file(
            self,
            "Selecciona el archivo fuente del hallazgo",
            initial,
        )
        if selected:
            self.source_path = Path(selected)
            self.source_label.setText(f"Archivo: {selected}")

    def _generate(self):
        if not self.target_row:
            return
        # Si el archivo ya fue resuelto al seleccionar el hallazgo se envía
        # directamente. Si no, el controlador vuelve a intentar resolverlo y
        # solo entonces solicita selección manual.
        self.controller.generate_ai(
            self.target_row,
            self.source_path,
        )

    def set_proposals(self, proposals: list[dict]) -> None:
        self.proposals = list(proposals)
        self.list.clear()

        for index, proposal in enumerate(proposals, start=1):
            enfoque = str(
                proposal.get("enfoque") or f"OPCIÓN {index}"
            ).upper()
            titulo = str(
                proposal.get("titulo") or "Propuesta sin título"
            ).strip()
            riesgo = str(
                proposal.get("riesgo") or "NO DEFINIDO"
            ).upper()
            explicacion = str(
                proposal.get("explicacion") or ""
            ).strip()

            # La lista funciona como selector visual, no como volcado JSON.
            # Se muestran las tres propuestas con jerarquía clara y sin
            # obligar al usuario a desplazarse horizontalmente.
            preview = explicacion
            if len(preview) > 115:
                preview = preview[:112].rstrip() + "…"

            valid = bool(proposal.get("validacion_ok", True))
            validation_errors = [
                str(item)
                for item in proposal.get("errores_validacion") or []
            ]

            lines = [
                (
                    f"{index}. {enfoque}    •    Riesgo {riesgo}"
                    + ("" if valid else "    •    NO APLICABLE")
                ),
                titulo,
            ]
            if preview:
                lines.append(preview)
            if validation_errors:
                lines.append(
                    "Validación: " + validation_errors[0]
                )

            item = QListWidgetItem("\n".join(lines))
            tooltip = (
                f"{enfoque} · Riesgo {riesgo}\n{titulo}"
                + (f"\n\n{explicacion}" if explicacion else "")
            )
            if validation_errors:
                tooltip += (
                    "\n\nNo aplicable:\n- "
                    + "\n- ".join(validation_errors)
                )
                item.setForeground(QColor("#FF9DA8"))
            item.setToolTip(tooltip)
            item.setSizeHint(
                QSize(
                    0,
                    112 if validation_errors
                    else (92 if preview else 70),
                )
            )
            self.list.addItem(item)

        if proposals:
            first_valid = next(
                (
                    index
                    for index, proposal in enumerate(proposals)
                    if proposal.get("validacion_ok", True)
                ),
                0,
            )
            self.list.setCurrentRow(first_valid)

    def _show_proposal(self, index: int):
        if index < 0 or index >= len(self.proposals):
            self.detail.clear()
            self.apply_btn.setEnabled(False)
            self.apply_btn.setText("Aplicar propuesta y verificar")
            return
        proposal = self.proposals[index]
        valid = bool(proposal.get("validacion_ok", True))
        self.apply_btn.setEnabled(valid)
        self.apply_btn.setText(
            "Aplicar propuesta y verificar"
            if valid
            else "Propuesta no aplicable"
        )
        self.detail.setPlainText(
            json.dumps(
                proposal,
                ensure_ascii=False,
                indent=2,
            )
        )

    def _apply(self):
        index = self.list.currentRow()
        if index >= 0:
            self.controller.apply_ai_proposal(index)


class KnowledgePage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("Recetas y conocimiento")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Separa el parche concreto de la medicina semántica reusable."
        )
        subtitle.setObjectName("Subheading")
        layout.addWidget(subtitle)

        metrics = QHBoxLayout()
        self.knowledge = MetricCard(
            "Medicinas semánticas",
            "0",
            "Conocimiento reutilizable",
        )
        self.recipes = MetricCard(
            "Parches concretos",
            "0",
            "Implementaciones exactas",
        )
        self.evidence = MetricCard(
            "Evidencias",
            "0",
            "Sesiones guardadas",
        )
        metrics.addWidget(self.knowledge)
        metrics.addWidget(self.recipes)
        metrics.addWidget(self.evidence)
        layout.addLayout(metrics)

        card = Card()
        card_l = QVBoxLayout(card)