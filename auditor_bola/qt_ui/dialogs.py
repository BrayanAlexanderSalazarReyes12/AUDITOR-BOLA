"""Diálogos profesionales de carga y auto-configuración."""

from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
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
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..app_paths import default_config_dir
from ..profile_builder import build_profile_draft, detect_project
from .theme import COLORS
from .widgets import Card, PrimaryButton, SectionHeader, Stepper, brand_icon


def calculate_dialog_size(
    available_width: int,
    available_height: int,
    preferred_width: int,
    preferred_height: int,
    minimum_width: int,
    minimum_height: int,
    margin: int = 24,
) -> tuple[int, int, int, int]:
    """Calcula tamaño lógico sin salir del área útil de la pantalla."""
    usable_width = max(1, available_width - (margin * 2))
    usable_height = max(1, available_height - (margin * 2))

    width = max(1, min(preferred_width, usable_width))
    height = max(1, min(preferred_height, usable_height))

    min_width = min(minimum_width, width)
    min_height = min(minimum_height, height)

    return width, height, min_width, min_height


class AegisDialog(QDialog):
    """Diálogo base responsive con lienzo Aegis."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AegisDialog")
        self.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )
        self._preferred_size = (980, 650)
        self._minimum_dialog_size = (760, 500)
        self._screen_margin = 22

    def configure_dialog_size(
        self,
        preferred: tuple[int, int],
        minimum: tuple[int, int],
        margin: int = 22,
    ) -> None:
        self._preferred_size = preferred
        self._minimum_dialog_size = minimum
        self._screen_margin = margin
        self._fit_to_available_screen()

    def _target_screen(self):
        parent = self.parentWidget()
        if parent is not None and parent.screen() is not None:
            return parent.screen()
        if self.screen() is not None:
            return self.screen()
        return QApplication.primaryScreen()

    def _fit_to_available_screen(self) -> None:
        screen = self._target_screen()
        if screen is None:
            return

        available = screen.availableGeometry()
        width, height, min_width, min_height = calculate_dialog_size(
            available.width(),
            available.height(),
            self._preferred_size[0],
            self._preferred_size[1],
            self._minimum_dialog_size[0],
            self._minimum_dialog_size[1],
            self._screen_margin,
        )

        self.setMinimumSize(min_width, min_height)
        self.resize(width, height)

        x = available.x() + max(
            0,
            (available.width() - width) // 2,
        )
        y = available.y() + max(
            0,
            (available.height() - height) // 2,
        )
        self.move(x, y)

    def is_short_screen(self) -> bool:
        screen = self._target_screen()
        if screen is None:
            return False
        return screen.availableGeometry().height() < 700

    def showEvent(self, event):
        self._fit_to_available_screen()
        super().showEvent(event)
        self._apply_windows_dark_titlebar()

    def _apply_windows_dark_titlebar(self) -> None:
        if os.name != "nt":
            return
        try:
            import ctypes

            hwnd = int(self.winId())
            value = ctypes.c_int(1)
            dwm = ctypes.windll.dwmapi
            for attribute in (20, 19):
                result = dwm.DwmSetWindowAttribute(
                    hwnd,
                    attribute,
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
                if result == 0:
                    break
        except Exception:
            pass




class LoadCard(QFrame):
    """Tarjeta clicable del Centro de Carga."""

    clicked = Signal()

    def __init__(
        self,
        icon_text: str,
        title: str,
        description: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("LoadCard")
        self.setAttribute(
            Qt.WidgetAttribute.WA_Hover,
            True,
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(96)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setToolTip(description)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        icon = QLabel(icon_text)
        icon.setObjectName("LoadCardIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(38, 38)
        layout.addWidget(icon)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(3)

        title_label = QLabel(title)
        title_label.setObjectName("LoadCardTitle")
        title_label.setWordWrap(False)
        text.addWidget(title_label)

        description_label = QLabel(description)
        description_label.setObjectName("LoadCardDescription")
        description_label.setWordWrap(True)
        text.addWidget(description_label)

        layout.addLayout(text, 1)

        arrow = QLabel("›")
        arrow.setObjectName("LoadCardArrow")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow.setFixedWidth(20)
        layout.addWidget(arrow)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)




class LoadCenterDialog(AegisDialog):
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
        self.configure_dialog_size(
            preferred=(980, 650),
            minimum=(720, 500),
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.dialog_root = QWidget()
        self.dialog_root.setObjectName("DialogRoot")
        self.dialog_root.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )
        outer.addWidget(self.dialog_root)

        root = QVBoxLayout(self.dialog_root)
        if self.is_short_screen():
            root.setContentsMargins(14, 12, 14, 12)
            root.setSpacing(9)
        else:
            root.setContentsMargins(22, 20, 22, 18)
            root.setSpacing(14)

        hero = Card(elevated=True)
        hero.setObjectName("DialogHero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(18, 14, 18, 14)
        hero_layout.setSpacing(14)

        logo = QLabel()
        logo.setObjectName("DialogBrandIcon")
        logo.setPixmap(brand_icon().pixmap(48, 48))
        logo.setFixedSize(52, 52)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(logo)

        titles = QVBoxLayout()
        titles.setSpacing(2)

        title = QLabel("Centro de carga")
        title.setObjectName("DialogTitle")
        titles.addWidget(title)

        subtitle = QLabel(
            "Incorpora los puntos de entrada que Aegis necesita para "
            "analizar, ejecutar, corregir y conservar evidencia."
        )
        subtitle.setObjectName("DialogSubtitle")
        subtitle.setWordWrap(True)
        titles.addWidget(subtitle)

        hero_layout.addLayout(titles, 1)

        status = QLabel("8 fuentes compatibles")
        status.setObjectName("DialogPill")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setMinimumWidth(132)
        hero_layout.addWidget(status)

        root.addWidget(hero)

        scroll = QScrollArea()
        scroll.setObjectName("DialogScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        holder = QWidget()
        holder.setObjectName("DialogCanvas")
        holder.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )
        grid = QGridLayout(holder)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

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

        for index, (icon, title_text, description, key) in enumerate(
            self.ITEMS
        ):
            card = LoadCard(
                icon,
                title_text,
                description,
            )
            signal = signal_map[key]
            card.clicked.connect(
                lambda s=signal: self._emit_and_close(s)
            )
            grid.addWidget(
                card,
                index // 2,
                index % 2,
            )

        scroll.setWidget(holder)
        root.addWidget(scroll, 1)

        self.footer_frame = QFrame()
        self.footer_frame.setObjectName("DialogFooter")
        self.footer_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        footer_frame = self.footer_frame
        footer = QHBoxLayout(footer_frame)
        footer.setContentsMargins(12, 7, 12, 7)

        hint = QLabel(
            "Selecciona únicamente los recursos necesarios para el objetivo."
        )
        hint.setObjectName("DialogHint")
        footer.addWidget(hint, 1)

        close = QPushButton("Cerrar")
        close.setObjectName("DialogSecondaryButton")
        close.setMinimumWidth(98)
        close.clicked.connect(self.reject)
        footer.addWidget(close)

        root.addWidget(footer_frame)

    def _emit_and_close(self, signal):
        self.accept()
        signal.emit()


class AutoProfileDialog(AegisDialog):
    profile_ready = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aegis Auditor — Nuevo proyecto")
        self.setWindowIcon(brand_icon())
        self.configure_dialog_size(
            preferred=(1120, 690),
            minimum=(760, 500),
        )

        self.project_root: Path | None = None
        self.detection = None
        self.draft: dict | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.dialog_root = QWidget()
        self.dialog_root.setObjectName("DialogRoot")
        self.dialog_root.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )
        outer.addWidget(self.dialog_root)

        root = QVBoxLayout(self.dialog_root)
        if self.is_short_screen():
            root.setContentsMargins(14, 12, 14, 12)
            root.setSpacing(8)
        else:
            root.setContentsMargins(22, 20, 22, 18)
            root.setSpacing(12)

        header = Card(elevated=True)
        header.setObjectName("DialogHero")
        header_layout = QHBoxLayout(header)
        if self.is_short_screen():
            header_layout.setContentsMargins(14, 9, 14, 9)
            header_layout.setSpacing(10)
            header.setMaximumHeight(82)
        else:
            header_layout.setContentsMargins(18, 14, 18, 14)
            header_layout.setSpacing(14)

        logo = QLabel()
        logo.setObjectName("DialogBrandIcon")
        logo.setPixmap(brand_icon().pixmap(48, 48))
        logo.setFixedSize(52, 52)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(logo)

        titles = QVBoxLayout()
        titles.setSpacing(2)

        title = QLabel("Incorporar aplicación")
        title.setObjectName("DialogTitle")
        subtitle = QLabel(
            "Aegis detecta stack, runtime, manifiestos y endpoints "
            "candidatos para construir el perfil inicial."
        )
        subtitle.setObjectName("DialogSubtitle")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)

        choose = PrimaryButton("Seleccionar aplicación")
        choose.setMinimumWidth(176)
        choose.clicked.connect(self._select_project)

        header_layout.addLayout(titles, 1)
        header_layout.addWidget(choose)
        root.addWidget(header)

        step_card = Card()
        step_card.setObjectName("DialogStepperCard")
        step_layout = QVBoxLayout(step_card)
        if self.is_short_screen():
            step_layout.setContentsMargins(12, 5, 12, 5)
            step_card.setMaximumHeight(82)
        else:
            step_layout.setContentsMargins(16, 10, 16, 10)

        self.stepper = Stepper(
            [
                ("Seleccionar", "Proyecto"),
                ("Analizar", "Stack"),
                ("Generar", "Perfil"),
                ("Validar", "P1 + P2"),
                ("Listo", "Auditar"),
            ]
        )
        step_layout.addWidget(self.stepper)
        root.addWidget(step_card)

        self.content_splitter = QSplitter(
            Qt.Orientation.Horizontal
        )
        self.content_splitter.setObjectName(
            "DialogContentSplitter"
        )
        self.content_splitter.setChildrenCollapsible(False)
        content = self.content_splitter

        left = Card()
        left.setObjectName("DialogContentCard")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 14, 16, 14)
        left_layout.setSpacing(10)
        left_layout.addWidget(
            SectionHeader(
                "Análisis del proyecto",
                "Información detectada automáticamente.",
            )
        )

        empty_state = QFrame()
        empty_state.setObjectName("DialogEmptyState")
        empty_layout = QVBoxLayout(empty_state)
        empty_layout.setContentsMargins(18, 18, 18, 18)
        empty_layout.setSpacing(8)

        empty_icon = QLabel("◇")
        empty_icon.setObjectName("DialogEmptyIcon")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)

        self.summary = QLabel(
            "Selecciona una carpeta de proyecto para comenzar.\n\n"
            "Aegis inspeccionará estructura, lenguajes, frameworks, "
            "manifiestos y endpoints candidatos."
        )
        self.summary.setObjectName("DialogBodyText")
        self.summary.setWordWrap(True)
        self.summary.setAlignment(
            Qt.AlignmentFlag.AlignTop
            | Qt.AlignmentFlag.AlignHCenter
        )
        empty_layout.addWidget(self.summary, 1)

        left_layout.addWidget(empty_state, 1)

        right = Card()
        right.setObjectName("DialogContentCard")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 14, 16, 14)
        right_layout.setSpacing(10)
        right_layout.addWidget(
            SectionHeader(
                "Vista previa del perfil",
                "JSON que quedará disponible para la auditoría.",
            )
        )

        self.preview = QPlainTextEdit()
        self.preview.setObjectName("DialogCodePreview")
        self.preview.setReadOnly(True)
        self.preview.setPlainText(
            '{\n  "perfil": "pendiente"\n}'
        )
        right_layout.addWidget(self.preview, 1)

        content.addWidget(left)
        content.addWidget(right)
        content.setStretchFactor(0, 4)
        content.setStretchFactor(1, 6)
        content.setSizes([420, 640])
        root.addWidget(content, 1)

        self.footer_frame = QFrame()
        self.footer_frame.setObjectName("DialogFooter")
        self.footer_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        footer_frame = self.footer_frame
        footer = QHBoxLayout(footer_frame)
        footer.setContentsMargins(12, 7, 12, 7)
        footer.setSpacing(8)

        self.path_label = QLabel(
            "Sin proyecto seleccionado"
        )
        self.path_label.setObjectName("DialogHint")
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        cancel = QPushButton("Cancelar")
        cancel.setObjectName("DialogSecondaryButton")
        cancel.setMinimumWidth(96)
        cancel.clicked.connect(self.reject)

        self.save = PrimaryButton(
            "Guardar perfil y continuar"
        )
        self.save.setMinimumWidth(184)
        self.save.setEnabled(False)
        self.save.clicked.connect(self._save_profile)

        footer.addWidget(self.path_label, 1)
        footer.addWidget(cancel)
        footer.addWidget(self.save)
        root.addWidget(footer_frame)

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
