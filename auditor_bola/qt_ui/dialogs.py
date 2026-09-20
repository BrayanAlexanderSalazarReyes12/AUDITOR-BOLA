"""Diálogos profesionales de carga y auto-configuración."""

from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QListView,
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QLineEdit,
    QHeaderView,
    QComboBox,
    QCheckBox,
    QMessageBox,
    QPlainTextEdit,
    QTabWidget,
    QListWidget,
    QPushButton,
    QProgressBar,
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
        self._open_maximized = True
        self.setModal(True)

    def configure_dialog_size(
        self,
        preferred: tuple[int, int],
        minimum: tuple[int, int],
        margin: int = 22,
        *,
        maximized: bool = True,
    ) -> None:
        self._preferred_size = preferred
        self._minimum_dialog_size = minimum
        self._screen_margin = margin
        self._open_maximized = maximized
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
        if self._open_maximized and not self.isMaximized():
            QTimer.singleShot(0, self.showMaximized)

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




class PatchReviewWindow(AegisDialog):
    """Ventana dedicada para revisar una medicina/parche antes de aplicarlo."""

    def __init__(
        self,
        proposal: dict,
        *,
        target_root: str | Path | None = None,
        source_path: str | Path | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.proposal = dict(proposal or {})
        self.target_root = Path(target_root).resolve() if target_root else None
        self.source_path = Path(source_path).resolve() if source_path else None
        self.configure_dialog_size((1420, 860), (980, 620), maximized=False)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        header = QFrame()
        header_l = QHBoxLayout(header)
        header_l.setContentsMargins(14, 10, 14, 10)
        title_box = QVBoxLayout()
        title = QLabel(str(self.proposal.get("titulo") or "Revisión de parche"))
        title.setObjectName("SectionTitle")
        title.setWordWrap(True)
        title_box.addWidget(title)
        self.status = QLabel()
        self.status.setObjectName("Muted")
        title_box.addWidget(self.status)
        header_l.addLayout(title_box, 1)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.close)
        header_l.addWidget(close)
        root.addWidget(header)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)

        left = QFrame()
        left_l = QVBoxLayout(left)
        left_l.addWidget(SectionHeader(
            "Archivos del parche",
            "Selecciona el archivo para revisar su cambio completo.",
        ))
        self.files = QListWidget()
        self.files.setWordWrap(True)
        self.files.currentRowChanged.connect(self._show_file)
        left_l.addWidget(self.files, 1)

        right = QFrame()
        right_l = QVBoxLayout(right)
        right_l.addWidget(SectionHeader(
            "Información de la medicina",
            "Framework, estrategia, riesgo y validación de la propuesta.",
        ))
        meta = QPlainTextEdit()
        meta.setReadOnly(True)
        meta.setMaximumHeight(190)
        meta.setPlainText(json.dumps(
            {k: v for k, v in self.proposal.items() if k != "preview_cambios"},
            ensure_ascii=False,
            indent=2,
        ))
        right_l.addWidget(meta)

        self.tabs = QTabWidget()
        self.diff = QPlainTextEdit()
        self.diff.setReadOnly(True)
        self.diff.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.code = QPlainTextEdit()
        self.code.setReadOnly(True)
        self.code.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.code.setObjectName("PatchCodeView")
        self.tabs.addTab(self.diff, "Parche / Diff")
        self.tabs.addTab(self.code, "Código actual")
        right_l.addWidget(self.tabs, 1)

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([350, 1050])
        root.addWidget(split, 1)

        self._previews = [
            item for item in self.proposal.get("preview_cambios") or []
            if isinstance(item, dict)
        ]
        self._populate_files()
        self._update_status()

    def _populate_files(self):
        self.files.clear()
        for preview in self._previews:
            self.files.addItem(
                f"{preview.get('archivo') or 'archivo'}\n"
                f"{preview.get('lenguaje') or 'desconocido'}"
            )
        if not self._previews:
            self.files.addItem("No hay preview determinista disponible")
        self.files.setCurrentRow(0)

    def _update_status(self):
        valid = bool(self.proposal.get("validacion_ok", True))
        risk = str(self.proposal.get("riesgo") or "NO DEFINIDO").upper()
        enfoque = str(self.proposal.get("enfoque") or "PROPUESTA").upper()
        self.status.setText(
            f"{enfoque}  ·  Riesgo {risk}  ·  "
            + ("✓ validación local OK" if valid else "✕ propuesta no aplicable")
        )

    def _show_file(self, index: int):
        if index < 0 or index >= len(self._previews):
            self.diff.setPlainText("Esta propuesta no contiene una vista previa determinista.")
            self.code.clear()
            return
        preview = self._previews[index]
        self.diff.setPlainText(str(preview.get("diff") or "Sin diff disponible."))
        relative = Path(str(preview.get("archivo") or ""))
        candidate = (
            relative if relative.is_absolute()
            else ((self.target_root / relative) if self.target_root else self.source_path)
        )
        if candidate and candidate.is_file():
            try:
                self.code.setPlainText(candidate.read_text(encoding="utf-8", errors="replace"))
            except OSError as exc:
                self.code.setPlainText(f"No se pudo leer el archivo:\n{exc}")
        else:
            self.code.setPlainText("El archivo objetivo no está disponible en el proyecto cargado.")


class LibraryBrowserWindow(AegisDialog):
    """Explorador visual de medicinas, parches y sus archivos guardados."""

    def __init__(self, *, parent=None):
        super().__init__(parent)
        self.configure_dialog_size((1380, 820), (960, 600), maximized=False)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Biblioteca de medicinas y parches")
        title.setObjectName("PageTitle")
        title_box.addWidget(title)
        subtitle = QLabel(
            "Revisa qué archivos están guardados, su verificación, estadísticas y contenido."
        )
        subtitle.setObjectName("Subheading")
        subtitle.setWordWrap(True)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        refresh = QPushButton("Actualizar")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        root.addLayout(header)

        self.summary = QLabel()
        self.summary.setObjectName("Muted")
        root.addWidget(self.summary)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        left = QFrame()
        left_l = QVBoxLayout(left)
        left_l.addWidget(SectionHeader(
            "Archivos guardados",
            "Medicinas y parches encontrados en la biblioteca local.",
        ))
        self.tabs = QTabWidget()
        self.recipe_list = QListWidget()
        self.knowledge_list = QListWidget()
        self.tabs.addTab(self.recipe_list, "Parches")
        self.tabs.addTab(self.knowledge_list, "Medicinas")
        left_l.addWidget(self.tabs, 1)

        right = QFrame()
        right_l = QVBoxLayout(right)
        self.path_label = QLabel("Archivo: —")
        self.path_label.setObjectName("Muted")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right_l.addWidget(self.path_label)
        actions = QHBoxLayout()
        self.open_file_btn = QPushButton("Abrir JSON")
        self.open_file_btn.clicked.connect(self._open_selected_file)
        self.open_folder_btn = QPushButton("Abrir carpeta")
        self.open_folder_btn.clicked.connect(self._open_selected_folder)
        self.validate_btn = QPushButton("Validar archivo")
        self.validate_btn.clicked.connect(self._validate_selected)
        actions.addWidget(self.open_file_btn)
        actions.addWidget(self.open_folder_btn)
        actions.addWidget(self.validate_btn)
        actions.addStretch(1)
        right_l.addLayout(actions)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.preview.setObjectName("PatchCodeView")
        right_l.addWidget(self.preview, 1)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([410, 970])
        root.addWidget(split, 1)

        self._recipe_files = []
        self._knowledge_files = []
        self.recipe_list.currentRowChanged.connect(self._preview_recipe)
        self.knowledge_list.currentRowChanged.connect(self._preview_knowledge)
        self.tabs.currentChanged.connect(lambda _: self._render_file(self._current_path()))
        self.refresh()

    @staticmethod
    def _load_json(path: Path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return (data, "OK") if isinstance(data, dict) else (None, "El JSON no contiene un objeto.")
        except Exception as exc:
            return None, str(exc)

    def refresh(self):
        from ..recipe_library import biblioteca_por_defecto
        from ..remediation_knowledge import knowledge_root
        recipe_root = biblioteca_por_defecto()
        knowledge_root_path = knowledge_root()
        self._recipe_files = sorted(recipe_root.glob("*/*.json")) if recipe_root.exists() else []
        self._knowledge_files = sorted(knowledge_root_path.glob("*/*.json")) if knowledge_root_path.exists() else []
        self.recipe_list.clear()
        self.knowledge_list.clear()
        valid_recipes = 0
        for path in self._recipe_files:
            data, _ = self._load_json(path)
            valid_recipes += int(data is not None)
            verified = "✓ VERIFICADO" if data and data.get("verificada") else "○ PENDIENTE"
            title = str(data.get("titulo") if data else path.stem)
            self.recipe_list.addItem(f"{verified}  ·  {title}\n{path.name}")
        valid_knowledge = 0
        for path in self._knowledge_files:
            data, _ = self._load_json(path)
            valid_knowledge += int(data is not None)
            verified = "✓ VERIFICADA" if data and data.get("verificada") else "○ PENDIENTE"
            title = str(data.get("titulo") if data else path.stem)
            self.knowledge_list.addItem(f"{verified}  ·  {title}\n{path.name}")
        self.summary.setText(
            f"Parches: {len(self._recipe_files)} ({valid_recipes} JSON válidos)  ·  "
            f"Medicinas: {len(self._knowledge_files)} ({valid_knowledge} JSON válidos)"
        )
        current = self.recipe_list if self.tabs.currentIndex() == 0 else self.knowledge_list
        if current.count():
            current.setCurrentRow(0)
        else:
            self.preview.setPlainText("No hay archivos guardados en esta biblioteca.")

    def _current_path(self):
        files = self._recipe_files if self.tabs.currentIndex() == 0 else self._knowledge_files
        row = self.recipe_list.currentRow() if self.tabs.currentIndex() == 0 else self.knowledge_list.currentRow()
        return files[row] if 0 <= row < len(files) else None

    def _render_file(self, path):
        if path is None:
            self.path_label.setText("Archivo: —")
            self.preview.setPlainText("No hay archivo seleccionado.")
            return
        data, state = self._load_json(path)
        self.path_label.setText(f"Archivo: {path}")
        if data is None:
            self.preview.setPlainText(f"ERROR DE JSON\n\n{state}\n\n{path}")
            return
        stats = data.get("estadisticas") or {}
        report = {
            "archivo_biblioteca": str(path),
            "estado": ("VERIFICADO" if data.get("verificada") else "PENDIENTE"),
            "id": data.get("recipe_id") or data.get("knowledge_id"),
            "control_id": data.get("control_id"),
            "titulo": data.get("titulo"),
            "estadisticas": stats,
            "origenes": data.get("origenes") or [],
            "archivos_del_parche": data.get("cambios") or [],
            "operaciones": data.get("operaciones") or [],
            "familia_control": data.get("familia_control"),
            "causa_raiz": data.get("causa_raiz"),
            "invariante_seguridad": data.get("invariante_seguridad"),
            "lenguajes": data.get("lenguajes_observados") or [],
            "frameworks": data.get("frameworks_observados") or [],
            "casos_exitosos": data.get("casos_exitosos", 0),
            "ejemplos_verificados": data.get("ejemplos_verificados") or [],
        }
        report["json_completo"] = data
        self.preview.setPlainText(json.dumps(report, ensure_ascii=False, indent=2))

    def _preview_recipe(self, index):
        if self.tabs.currentIndex() == 0:
            self._render_file(self._recipe_files[index] if 0 <= index < len(self._recipe_files) else None)

    def _preview_knowledge(self, index):
        if self.tabs.currentIndex() == 1:
            self._render_file(self._knowledge_files[index] if 0 <= index < len(self._knowledge_files) else None)

    def _open_selected_file(self):
        path = self._current_path()
        if path and path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_selected_folder(self):
        path = self._current_path()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def _validate_selected(self):
        path = self._current_path()
        if path is None:
            return
        data, state = self._load_json(path)
        if data is None:
            QMessageBox.critical(self, "Archivo inválido", state)
            return
        required = (
            ("Parches", ("recipe_id", "control_id", "operaciones")),
            ("Medicinas", ("knowledge_id", "control_id", "invariante_seguridad")),
        )
        group = required[self.tabs.currentIndex()]
        missing = [key for key in group[1] if key not in data]
        if missing:
            QMessageBox.warning(self, "Archivo incompleto", "Faltan campos: " + ", ".join(missing))
            return
        QMessageBox.information(self, "Archivo válido", f"Archivo correctamente estructurado.\n\n{path}")


def styled_open_file(
    parent,
    caption: str,
    directory: str = "",
    file_filter: str = "",
) -> tuple[str, str]:
    return QFileDialog.getOpenFileName(
        parent,
        caption,
        directory,
        file_filter,
        options=QFileDialog.Option.DontUseNativeDialog,
    )


def styled_save_file(
    parent,
    caption: str,
    directory: str = "",
    file_filter: str = "",
) -> tuple[str, str]:
    return QFileDialog.getSaveFileName(
        parent,
        caption,
        directory,
        file_filter,
        options=QFileDialog.Option.DontUseNativeDialog,
    )


def styled_existing_directory(
    parent,
    caption: str,
    directory: str = "",
) -> str:
    return QFileDialog.getExistingDirectory(
        parent,
        caption,
        directory,
        options=(
            QFileDialog.Option.ShowDirsOnly
            | QFileDialog.Option.DontUseNativeDialog
        ),
    )


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
        screen = self._target_screen()
        available_width = (
            screen.availableGeometry().width()
            if screen is not None
            else 1200
        )
        self.load_columns = 4 if available_width >= 1400 else 2
        for column in range(self.load_columns):
            grid.setColumnStretch(column, 1)

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
                index // self.load_columns,
                index % self.load_columns,
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


class AccountManagerDialog(AegisDialog):
    """Editor de cuentas de prueba y roles del perfil."""

    AUTH_TYPES = ("basic", "bearer", "header", "none")

    def __init__(
        self,
        accounts: list[dict] | None = None,
        privileged_roles: list[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Aegis Auditor — Cuentas y roles")
        self.setWindowIcon(brand_icon())
        self.configure_dialog_size(
            preferred=(1040, 620),
            minimum=(780, 500),
        )
        self._privileged_roles = set(privileged_roles or [])

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        hero = Card(elevated=True)
        hero.setObjectName("AccountsHero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(16, 12, 16, 12)
        hero_layout.setSpacing(12)

        icon = QLabel("♙")
        icon.setObjectName("AccountsHeroIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(42, 42)
        hero_layout.addWidget(icon)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Cuentas de prueba")
        title.setObjectName("DialogTitle")
        subtitle = QLabel(
            "Revisa las cuentas encontradas automáticamente y agrega las "
            "que sólo existan en BD, LDAP, SSO u otros servicios."
        )
        subtitle.setObjectName("DialogSubtitle")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        hero_layout.addLayout(titles, 1)

        self.account_count = QLabel("0 cuentas")
        self.account_count.setObjectName("DialogPill")
        self.account_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.account_count.setMinimumWidth(92)
        hero_layout.addWidget(self.account_count)

        root.addWidget(hero)

        toolbar = QFrame()
        toolbar.setObjectName("AccountsToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 8, 12, 8)
        toolbar_layout.setSpacing(8)

        hint = QLabel(
            "Autenticación: basic = usuario/clave · bearer = token · "
            "header = cabecera personalizada · none = sin autenticación."
        )
        hint.setObjectName("DialogHint")
        hint.setWordWrap(True)
        toolbar_layout.addWidget(hint, 1)

        self.show_passwords = QCheckBox("Mostrar contraseñas")
        self.show_passwords.setObjectName("AccountsShowPasswords")
        self.show_passwords.toggled.connect(
            self._toggle_password_visibility
        )
        toolbar_layout.addWidget(self.show_passwords)

        root.addWidget(toolbar)

        self.table = QTableWidget(0, 5)
        self.table.setObjectName("AccountsTable")
        self.table.setHorizontalHeaderLabels(
            [
                "Usuario",
                "Contraseña",
                "Rol",
                "Autenticación",
                "Privilegiado",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Stretch,
        )
        header.setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.Stretch,
        )
        header.setSectionResizeMode(
            3,
            QHeaderView.ResizeMode.Fixed,
        )
        header.setSectionResizeMode(
            4,
            QHeaderView.ResizeMode.Fixed,
        )
        self.table.setColumnWidth(3, 154)
        self.table.setColumnWidth(4, 116)
        root.addWidget(self.table, 1)

        for account in accounts or []:
            self._append_account(account)

        footer = QFrame()
        footer.setObjectName("DialogFooter")
        actions = QHBoxLayout(footer)
        actions.setContentsMargins(10, 8, 10, 8)
        actions.setSpacing(8)

        add = QPushButton("＋ Añadir cuenta")
        add.setObjectName("AccountsAddButton")
        add.clicked.connect(lambda: self._append_account({}))

        remove = QPushButton("− Eliminar seleccionada")
        remove.setObjectName("DialogSecondaryButton")
        remove.clicked.connect(self._remove_selected)

        actions.addWidget(add)
        actions.addWidget(remove)
        actions.addStretch(1)

        cancel = QPushButton("Cancelar")
        cancel.setObjectName("DialogSecondaryButton")
        cancel.clicked.connect(self.reject)

        save = PrimaryButton("Guardar cuentas")
        save.setMinimumWidth(144)
        save.clicked.connect(self.accept)

        actions.addWidget(cancel)
        actions.addWidget(save)
        root.addWidget(footer)

        self._refresh_count()

    def _append_account(self, account: dict) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 48)

        username = QLineEdit(
            str(account.get("username") or "")
        )
        username.setObjectName("AccountsCellEditor")
        username.setPlaceholderText("usuario o correo")
        self.table.setCellWidget(row, 0, username)

        password = QLineEdit(
            str(account.get("password") or "")
        )
        password.setObjectName("AccountsCellEditor")
        password.setPlaceholderText("opcional")
        password.setEchoMode(
            QLineEdit.EchoMode.Normal
            if self.show_passwords.isChecked()
            else QLineEdit.EchoMode.Password
        )
        self.table.setCellWidget(row, 1, password)

        role = QLineEdit(
            str(account.get("role") or "USER")
        )
        role.setObjectName("AccountsCellEditor")
        role.setPlaceholderText("USER")
        self.table.setCellWidget(row, 2, role)

        auth = QComboBox()
        auth.setObjectName("AccountsAuthCombo")
        auth.setMinimumWidth(136)
        auth_view = QListView()
        auth_view.setObjectName("AccountsComboPopup")
        auth.setView(auth_view)
        auth.addItems(self.AUTH_TYPES)

        default_auth = str(account.get("auth_type") or "").strip()
        if not default_auth:
            default_auth = (
                "basic"
                if account.get("password")
                else "none"
            )
        index = auth.findText(default_auth)
        auth.setCurrentIndex(index if index >= 0 else 0)
        self.table.setCellWidget(row, 3, auth)

        privileged = QCheckBox()
        privileged.setObjectName("AccountsPrivilegeCheck")
        privileged.setToolTip(
            "Marca este rol como privilegiado para pruebas RBAC."
        )
        privileged.setChecked(
            str(account.get("role") or "")
            in self._privileged_roles
        )
        wrapper = QWidget()
        wrapper.setObjectName("AccountsCheckWrapper")
        box = QHBoxLayout(wrapper)
        box.setContentsMargins(0, 0, 0, 0)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(privileged)
        self.table.setCellWidget(row, 4, wrapper)

        self.table.selectRow(row)
        self._refresh_count()

    def _toggle_password_visibility(
        self,
        visible: bool,
    ) -> None:
        mode = (
            QLineEdit.EchoMode.Normal
            if visible
            else QLineEdit.EchoMode.Password
        )
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 1)
            if isinstance(widget, QLineEdit):
                widget.setEchoMode(mode)

    def _refresh_count(self) -> None:
        count = self.table.rowCount()
        self.account_count.setText(
            f"{count} cuenta"
            if count == 1
            else f"{count} cuentas"
        )

    def _remove_selected(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self._refresh_count()
            if self.table.rowCount():
                self.table.selectRow(
                    min(row, self.table.rowCount() - 1)
                )

    def data(self) -> tuple[list[dict], list[str]]:
        accounts: list[dict] = []
        privileged_roles: list[str] = []

        for row in range(self.table.rowCount()):
            username_widget = self.table.cellWidget(row, 0)
            password_widget = self.table.cellWidget(row, 1)
            role_widget = self.table.cellWidget(row, 2)
            auth_widget = self.table.cellWidget(row, 3)

            username = username_widget.text().strip()
            if not username:
                continue

            password_text = password_widget.text()
            role = role_widget.text().strip() or "USER"
            auth = auth_widget.currentText()

            wrapper = self.table.cellWidget(row, 4)
            checkbox = wrapper.findChild(QCheckBox)
            if (
                checkbox
                and checkbox.isChecked()
                and role not in privileged_roles
            ):
                privileged_roles.append(role)

            accounts.append(
                {
                    "username": username,
                    "password": password_text or None,
                    "role": role,
                    "auth_type": auth,
                    "token": None,
                    "headers": {},
                }
            )

        return accounts, privileged_roles


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
        self.manual_accounts: list[dict] = []
        self.manual_privileged_roles: list[str] = []

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

        self.accounts_button = QPushButton("Cuentas (0)")
        self.accounts_button.setObjectName("AccountsButton")
        self.accounts_button.setMinimumWidth(116)
        self.accounts_button.clicked.connect(
            self._open_account_manager
        )

        choose = PrimaryButton("Seleccionar aplicación")
        choose.setMinimumWidth(176)
        choose.clicked.connect(self._select_project)

        header_layout.addLayout(titles, 1)
        header_layout.addWidget(self.accounts_button)
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
        content.setStretchFactor(0, 5)
        content.setStretchFactor(1, 7)
        content.setSizes([520, 720])
        root.addWidget(content, 1)

        self.analysis_progress_frame = QFrame()
        self.analysis_progress_frame.setObjectName("InlineTaskProgress")
        progress_layout = QHBoxLayout(self.analysis_progress_frame)
        progress_layout.setContentsMargins(12, 8, 12, 8)
        progress_layout.setSpacing(10)

        self.analysis_progress_label = QLabel("Preparando análisis…")
        self.analysis_progress_label.setObjectName("InlineTaskLabel")
        progress_layout.addWidget(self.analysis_progress_label, 1)

        self.analysis_progress_bar = QProgressBar()
        self.analysis_progress_bar.setObjectName("InlineTaskBar")
        self.analysis_progress_bar.setRange(0, 100)
        self.analysis_progress_bar.setValue(0)
        self.analysis_progress_bar.setMinimumWidth(180)
        self.analysis_progress_bar.setMaximumWidth(320)
        self.analysis_progress_bar.setTextVisible(False)
        progress_layout.addWidget(self.analysis_progress_bar)

        self.analysis_progress_percent = QLabel("0%")
        self.analysis_progress_percent.setObjectName("InlineTaskPercent")
        self.analysis_progress_percent.setFixedWidth(44)
        self.analysis_progress_percent.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )
        progress_layout.addWidget(self.analysis_progress_percent)

        self.analysis_progress_frame.hide()
        root.addWidget(self.analysis_progress_frame)

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

    def _refresh_accounts_button(self) -> None:
        accounts = (
            self.draft.get("cuentas", [])
            if self.draft
            else self.manual_accounts
        )
        self.accounts_button.setText(
            f"Cuentas ({len(accounts)})"
        )

    def _merge_manual_accounts(self) -> None:
        if not self.draft:
            return
        existing = {
            item.get("username"): dict(item)
            for item in self.draft.get("cuentas", [])
            if item.get("username")
        }
        for item in self.manual_accounts:
            if item.get("username"):
                existing[item["username"]] = dict(item)
        self.draft["cuentas"] = list(existing.values())

        roles = list(self.draft.get("roles_privilegiados") or [])
        for role in self.manual_privileged_roles:
            if role and role not in roles:
                roles.append(role)
        self.draft["roles_privilegiados"] = roles

    def _open_account_manager(self) -> None:
        accounts = (
            list(self.draft.get("cuentas", []))
            if self.draft
            else list(self.manual_accounts)
        )
        roles = (
            list(self.draft.get("roles_privilegiados", []))
            if self.draft
            else list(self.manual_privileged_roles)
        )
        dialog = AccountManagerDialog(
            accounts,
            roles,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        accounts, roles = dialog.data()
        self.manual_accounts = accounts
        self.manual_privileged_roles = roles

        if self.draft is not None:
            self.draft["cuentas"] = list(accounts)
            self.draft["roles_privilegiados"] = list(roles)
            self.preview.setPlainText(
                json.dumps(
                    self.draft,
                    ensure_ascii=False,
                    indent=2,
                )
            )
        self._refresh_accounts_button()

    def _set_analysis_progress(
        self,
        value: int,
        text: str,
        *,
        visible: bool = True,
    ) -> None:
        value = max(0, min(100, int(value)))
        self.analysis_progress_label.setText(text)
        self.analysis_progress_bar.setValue(value)
        self.analysis_progress_percent.setText(f"{value}%")
        self.analysis_progress_frame.setVisible(visible)
        if visible:
            self.analysis_progress_frame.raise_()
        QApplication.processEvents()

    def _select_project(self):
        selected = styled_existing_directory(
            self,
            "Selecciona la carpeta raíz de la aplicación",
        )
        if not selected:
            return

        self._set_analysis_progress(
            8,
            "Preparando análisis del proyecto…",
        )

        try:
            root = Path(selected).resolve()
            self.project_root = root
            self.stepper.set_step(1)
            self._set_analysis_progress(
                22,
                "Detectando lenguajes, runtime y manifiestos…",
            )

            self.detection = detect_project(root)
            self.stepper.set_step(2)
            self._set_analysis_progress(
                58,
                "Analizando stack y endpoints candidatos…",
            )

            self.draft = build_profile_draft(self.detection)
            self._merge_manual_accounts()
            self._refresh_accounts_button()
            self.stepper.set_step(3)
            self._set_analysis_progress(
                82,
                "Construyendo perfil de configuración…",
            )

            meta = self.draft.get("metadata_detectada") or {}
            lines = [
                f"Proyecto: {meta.get('nombre_proyecto') or root.name}",
                (
                    "Versión: "
                    + str(
                        meta.get("version_detectada")
                        or self.draft.get("version_objetivo")
                        or "desconocida"
                    )
                    + (
                        f"  ·  fuente: {meta.get('version_fuente')}"
                        if meta.get("version_fuente")
                        else ""
                    )
                ),
                f"Ruta: {root}",
                f"Lenguajes: {', '.join(meta.get('lenguajes') or []) or '-'}",
                f"Frameworks: {', '.join(meta.get('frameworks') or []) or '-'}",
                f"Manifiestos: {', '.join(meta.get('manifiestos') or []) or '-'}",
                f"Endpoints candidatos: {len(meta.get('endpoints_candidatos') or [])}",
                f"Cuentas detectadas/configuradas: {len(self.draft.get('cuentas') or [])}",
                (
                    "Pilar 1 activos: "
                    + str(
                        len(self.draft.get("endpoints") or [])
                        * len(self.draft.get("cuentas") or [])
                        + len(self.draft.get("chequeos_acceso") or [])
                        + len(self.draft.get("chequeos_agente") or [])
                    )
                ),
                (
                    "Pilar 1 candidatos por confirmar: "
                    + str(meta.get("total_candidatos_pilar1") or 0)
                ),
                (
                    "Pilar 2 activos inferidos: "
                    + str(len(self.draft.get("chequeos_pilar2") or []))
                ),
                "",
                (
                    "Diagnosticar P1 + P2 requiere cobertura activa en ambos "
                    "pilares. Aegis puede activar automáticamente controles P2 "
                    "de alta confianza; los candidatos BOLA/RBAC/alcance de "
                    "agente necesitan confirmar propietario, rol o contrato "
                    "esperado antes de ejecutarse."
                ),
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
            self._set_analysis_progress(100, "Análisis completado")
            QTimer.singleShot(
                650,
                self.analysis_progress_frame.hide,
            )
        except Exception as exc:
            self.analysis_progress_frame.hide()
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
        selected, _filter = styled_save_file(
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
