"""Diálogos profesionales de carga y auto-configuración."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..app_paths import default_config_dir
from ..profile_builder import build_profile_draft, detect_project
from .theme import COLORS
from .widgets import Card, PrimaryButton, SectionHeader, Stepper, brand_icon


class LoadCard(QPushButton):
    def __init__(
        self,
        icon_text: str,
        title: str,
        description: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(92)
        self.setStyleSheet(
            """
            QPushButton {
                background:#0E293D;
                border:1px solid #1A5274;
                border-radius:12px;
                text-align:left;
                padding:12px 14px;
                color:#F4F8FB;
                font-size:11px;
                font-weight:700;
            }
            QPushButton:hover {
                background:#12354E;
                border-color:#38C8FF;
            }
            """
        )
        self.setText(
            f"{icon_text}   {title}\n"
            f"      {description}"
        )


class LoadCenterDialog(QDialog):
    request_new_project = Signal()
    request_profile = Signal()
    request_source = Signal()
    request_package = Signal()
    request_accounts = Signal()
    request_evidence = Signal()
    request_recipes = Signal()
    request_ai = Signal()

    ITEMS = (
        (
            "＋",
            "Nueva aplicación",
            "Seleccionar carpeta y generar el perfil automáticamente.",
            "new",
        ),
        (
            "▣",
            "Perfil JSON",
            "Cargar un perfil existente de config/*.json.",
            "profile",
        ),
        (
            "⌂",
            "Código fuente",
            "Seleccionar la carpeta local del proyecto.",
            "source",
        ),
        (
            "◇",
            "auditor-package.json",
            "Importar metadata, runtime y puntos de entrada.",
            "package",
        ),
        (
            "👥",
            "Cuentas y roles",
            "Importar identidades de prueba para Pilar 1.",
            "accounts",
        ),
        (
            "▧",
            "Evidencias",
            "Seleccionar una carpeta o sesión existente.",
            "evidence",
        ),
        (
            "▤",
            "Recetas y medicinas",
            "Incorporar conocimiento correctivo reusable.",
            "recipes",
        ),
        (
            "✦",
            "Proveedor IA",
            "Revisar OpenCode / Gemma y el modelo activo.",
            "ai",
        ),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aegis Auditor — Cargar / Importar")
        self.setWindowIcon(brand_icon())
        self.resize(920, 640)
        self.setMinimumSize(760, 540)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        title = QLabel("Centro de carga")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Incorpora de forma controlada todos los puntos de entrada "
            "que Aegis necesita para analizar, ejecutar y corregir."
        )
        subtitle.setObjectName("Subheading")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setSpacing(10)

        signal_map = {
            "new": self.request_new_project,
            "profile": self.request_profile,
            "source": self.request_source,
            "package": self.request_package,
            "accounts": self.request_accounts,
            "evidence": self.request_evidence,
            "recipes": self.request_recipes,
            "ai": self.request_ai,
        }

        for index, (icon, title_text, description, key) in enumerate(self.ITEMS):
            card = LoadCard(icon, title_text, description)
            signal = signal_map[key]
            card.clicked.connect(lambda _checked=False, s=signal: self._emit_and_close(s))
            grid.addWidget(card, index // 2, index % 2)

        scroll.setWidget(holder)
        root.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.reject)
        footer.addWidget(close)
        root.addLayout(footer)

    def _emit_and_close(self, signal):
        self.accept()
        signal.emit()


class AutoProfileDialog(QDialog):
    profile_ready = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aegis Auditor — Nuevo proyecto")
        self.setWindowIcon(brand_icon())
        self.resize(1080, 720)
        self.setMinimumSize(820, 560)

        self.project_root: Path | None = None
        self.detection = None
        self.draft: dict | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        header = Card(elevated=True)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 14, 18, 14)

        titles = QVBoxLayout()
        title = QLabel("Incorporar aplicación")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Aegis detecta stack, runtime, manifiestos y endpoints candidatos."
        )
        subtitle.setObjectName("Subheading")
        titles.addWidget(title)
        titles.addWidget(subtitle)

        choose = PrimaryButton("Seleccionar aplicación")
        choose.clicked.connect(self._select_project)

        header_layout.addLayout(titles, 1)
        header_layout.addWidget(choose)
        root.addWidget(header)

        self.stepper = Stepper(
            [
                ("Seleccionar", "Proyecto"),
                ("Analizar", "Stack"),
                ("Generar", "Perfil"),
                ("Validar", "P1 + P2"),
                ("Listo", "Auditar"),
            ]
        )
        root.addWidget(self.stepper)

        content = QHBoxLayout()
        content.setSpacing(10)

        left = Card()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 14, 16, 14)
        left_layout.addWidget(
            SectionHeader(
                "Análisis del proyecto",
                "Información detectada automáticamente.",
            )
        )

        self.summary = QLabel(
            "Selecciona una carpeta de proyecto para comenzar."
        )
        self.summary.setObjectName("Muted")
        self.summary.setWordWrap(True)
        self.summary.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        left_layout.addWidget(self.summary, 1)

        right = Card()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 14, 16, 14)
        right_layout.addWidget(
            SectionHeader(
                "Vista previa del perfil",
                "JSON que quedará disponible para la auditoría.",
            )
        )

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlainText('{\n  "perfil": "pendiente"\n}')
        right_layout.addWidget(self.preview, 1)

        content.addWidget(left, 4)
        content.addWidget(right, 6)
        root.addLayout(content, 1)

        footer = QHBoxLayout()
        self.path_label = QLabel("Sin proyecto seleccionado")
        self.path_label.setObjectName("Muted")
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)

        self.save = PrimaryButton("Guardar perfil y continuar")
        self.save.setEnabled(False)
        self.save.clicked.connect(self._save_profile)

        footer.addWidget(self.path_label, 1)
        footer.addWidget(cancel)
        footer.addWidget(self.save)
        root.addLayout(footer)

    def _select_project(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            "Selecciona la carpeta raíz de la aplicación",
        )
        if not selected:
            return

        try:
            root = Path(selected).resolve()
            self.project_root = root
            self.stepper.set_step(1)

            self.detection = detect_project(root)
            self.stepper.set_step(2)

            self.draft = build_profile_draft(self.detection)
            self.stepper.set_step(3)

            meta = self.draft.get("metadata_detectada") or {}
            lines = [
                f"Proyecto: {meta.get('nombre_proyecto') or root.name}",
                f"Ruta: {root}",
                f"Lenguajes: {', '.join(meta.get('lenguajes') or []) or '-'}",
                f"Frameworks: {', '.join(meta.get('frameworks') or []) or '-'}",
                f"Manifiestos: {', '.join(meta.get('manifiestos') or []) or '-'}",
                f"Endpoints candidatos: {len(meta.get('endpoints_candidatos') or [])}",
                "",
                "El perfil generado queda abierto para completar cuentas, "
                "roles y controles específicos antes de una auditoría productiva.",
            ]
            self.summary.setText("\n".join(lines))
            self.preview.setPlainText(
                json.dumps(
                    self.draft,
                    ensure_ascii=False,
                    indent=2,
                )
            )
            self.path_label.setText(str(root))
            self.save.setEnabled(True)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "No se pudo analizar",
                str(exc),
            )

    def _save_profile(self):
        if not self.project_root or not self.draft:
            return

        default_path = (
            default_config_dir()
            / f"{self.draft['sistema']}.json"
        )
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Guardar perfil de aplicación",
            str(default_path),
            "Perfil JSON (*.json)",
        )
        if not selected:
            return

        path = Path(selected).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                self.draft,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.stepper.set_step(5)
        self.profile_ready.emit(
            str(path),
            str(self.project_root),
        )
        self.accept()
