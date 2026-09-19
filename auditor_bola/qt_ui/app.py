"""Aplicación Qt profesional de Aegis Auditor."""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..app_paths import (
    configure_packaged_environment,
    default_evidence_dir,
    default_recipe_dir,
    resource_path,
)
from ..config import cargar_config
from ..recipe_library import biblioteca_por_defecto
from ..remediation_knowledge import knowledge_root
from .controller import AuditorController
from .dialogs import AutoProfileDialog, LoadCenterDialog
from .pages import (
    AIPage,
    AuditPage,
    EvidencePage,
    HomePage,
    KnowledgePage,
    ProjectPage,
    ReportsPage,
    SettingsPage,
)
from .theme import COLORS, QSS
from .widgets import Card, NavButton, PrimaryButton, brand_icon


class Sidebar(QFrame):
    def __init__(self, navigate, new_project, load_center, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(258)
        self._compact = False
        self.buttons: dict[str, NavButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 15, 12, 12)
        layout.setSpacing(5)

        self.brand_box = QWidget()
        brand = QVBoxLayout(self.brand_box)
        brand.setContentsMargins(4, 0, 4, 8)
        brand.setSpacing(4)

        logo = QLabel()
        logo.setPixmap(brand_icon().pixmap(90, 90))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.addWidget(logo)

        name = QLabel("AEGIS AUDITOR")
        name.setObjectName("BrandTitle")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.addWidget(name)

        subtitle = QLabel("AUDITORÍA · CORRECCIÓN · APRENDIZAJE")
        subtitle.setObjectName("BrandSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.addWidget(subtitle)

        pillars = QLabel(
            "<span style='color:#39C7FF;font-weight:700'>Pilar 1:</span> "
            "Identidad y Control de Acceso<br>"
            "<span style='color:#39C7FF;font-weight:700'>Pilar 2:</span> "
            "Arquitectura y Configuración"
        )
        pillars.setObjectName("Muted")
        pillars.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pillars.setWordWrap(True)
        brand.addWidget(pillars)

        layout.addWidget(self.brand_box)

        nav_items = [
            ("home", "⌂", "Inicio", lambda: navigate("home")),
            ("new", "＋", "Nuevo proyecto", new_project),
            ("load", "▣", "Cargar / Importar", load_center),
            ("project", "⚙", "Auto-configuración", lambda: navigate("project")),
            ("audit", "◈", "Auditoría P1 + P2", lambda: navigate("audit")),
            ("ai", "✦", "Correcciones con IA", lambda: navigate("ai")),
            ("knowledge", "▤", "Recetas y conocimiento", lambda: navigate("knowledge")),
            ("evidence", "▧", "Evidencias", lambda: navigate("evidence")),
            ("reports", "▦", "Reportes", lambda: navigate("reports")),
            ("settings", "⚙", "Configuración", lambda: navigate("settings")),
        ]

        for key, icon, label, callback in nav_items:
            button = NavButton(icon, label)
            button.clicked.connect(callback)
            layout.addWidget(button)
            self.buttons[key] = button

        layout.addStretch(1)

        self.footer = QFrame()
        self.footer.setObjectName("SubtlePanel")
        footer_layout = QVBoxLayout(self.footer)
        footer_layout.setContentsMargins(11, 9, 11, 9)
        footer_layout.setSpacing(2)

        self.ai_status = QLabel("○ IA: comprobando…")
        self.ai_status.setObjectName("Muted")
        footer_layout.addWidget(self.ai_status)

        platform = QLabel("Windows · macOS · Linux")
        platform.setObjectName("Muted")
        footer_layout.addWidget(platform)

        version = QLabel("Aegis Auditor · v1.0.0")
        version.setObjectName("KpiSub")
        footer_layout.addWidget(version)

        layout.addWidget(self.footer)
        self.set_active("home")

    def set_active(self, key: str) -> None:
        for name, button in self.buttons.items():
            button.set_active(name == key)

    def set_ai(self, enabled: bool, model: str) -> None:
        if enabled:
            self.ai_status.setText(f"● IA conectada · {model}")
            self.ai_status.setStyleSheet(f"color:{COLORS['success']};")
        else:
            self.ai_status.setText("○ IA no configurada")
            self.ai_status.setStyleSheet(f"color:{COLORS['muted']};")

    def set_compact(self, compact: bool) -> None:
        if compact == self._compact:
            return
        self._compact = compact
        self.setFixedWidth(72 if compact else 258)
        self.brand_box.setVisible(not compact)
        self.footer.setVisible(not compact)
        for button in self.buttons.values():
            button.set_compact(compact)


class Topbar(QFrame):
    new_requested = None
    load_requested = None

    def __init__(self, new_project, load_center, parent=None):
        super().__init__(parent)
        self.setObjectName("Topbar")
        self.setMinimumHeight(82)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 12, 10)
        layout.setSpacing(14)

        icon = QLabel()
        icon.setPixmap(brand_icon().pixmap(54, 54))
        layout.addWidget(icon)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        welcome = QLabel("Bienvenido a Aegis Auditor")
        welcome.setObjectName("PageTitle")
        description = QLabel(
            "Analiza, corrige y aprende. Seguridad inteligente basada en dos pilares."
        )
        description.setObjectName("Subheading")
        titles.addWidget(welcome)
        titles.addWidget(description)
        layout.addLayout(titles, 1)

        self.quote = QLabel(
            "“ Detectar es importante; corregir y aprender lo hace extraordinario. ”"
        )
        self.quote.setObjectName("Muted")
        self.quote.setWordWrap(True)
        self.quote.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quote.setMaximumWidth(270)
        layout.addWidget(self.quote)

        account = QFrame()
        account.setObjectName("SubtlePanel")
        account_l = QHBoxLayout(account)
        account_l.setContentsMargins(10, 7, 10, 7)
        account_l.setSpacing(8)

        avatar = QLabel("●")
        avatar.setStyleSheet(
            f"font-size:20px;color:{COLORS['accent_2']};"
        )
        account_l.addWidget(avatar)

        info = QVBoxLayout()
        info.setSpacing(0)
        self.project = QLabel("Sin proyecto")
        self.project.setStyleSheet("font-weight:700;")
        self.process = QLabel("No administrado")
        self.process.setObjectName("Muted")
        info.addWidget(self.project)
        info.addWidget(self.process)
        account_l.addLayout(info)

        layout.addWidget(account)

        new_btn = QPushButton("＋ Nuevo")
        new_btn.clicked.connect(new_project)
        layout.addWidget(new_btn)

        load_btn = PrimaryButton("Cargar ▾")
        load_btn.clicked.connect(load_center)
        layout.addWidget(load_btn)

    def refresh(self, controller: AuditorController) -> None:
        self.project.setText(
            controller.cfg.sistema
            if controller.cfg
            else (
                controller.target_root.name
                if controller.target_root
                else "Sin proyecto"
            )
        )
        if controller.process_running():
            self.process.setText("● En ejecución")
            self.process.setStyleSheet(f"color:{COLORS['success']};")
        elif controller.proceso:
            self.process.setText("● Detenido")
            self.process.setStyleSheet(f"color:{COLORS['warning']};")
        else:
            self.process.setText("No administrado")
            self.process.setStyleSheet(f"color:{COLORS['muted']};")

    def set_compact(self, compact: bool) -> None:
        self.quote.setVisible(not compact)


class SimpleLogPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Registro")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text, 1)

    def append(self, text: str) -> None:
        self.text.appendPlainText(text)


class AegisMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        configure_packaged_environment()

        self.setWindowTitle(
            "Aegis Auditor — Security Remediation Studio"
        )
        self.setWindowIcon(brand_icon())
        self.resize(1540, 900)
        self.setMinimumSize(900, 620)

        self.controller = AuditorController(self)
        self.page_keys: dict[str, int] = {}
        self.current_page = "home"
        self._busy = False

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.sidebar = Sidebar(
            self.navigate,
            self.open_new_project,
            self.open_load_center,
        )
        shell.addWidget(self.sidebar)

        self.content = QWidget()
        content_l = QVBoxLayout(self.content)
        content_l.setContentsMargins(10, 8, 10, 8)
        content_l.setSpacing(8)
        shell.addWidget(self.content, 1)

        self.topbar = Topbar(
            self.open_new_project,
            self.open_load_center,
        )
        content_l.addWidget(self.topbar)

        self.stack = QStackedWidget()
        content_l.addWidget(self.stack, 1)

        self.home = HomePage(self.controller)
        self.project_page = ProjectPage(self.controller)
        self.audit = AuditPage(self.controller)
        self.ai_page = AIPage(self.controller)
        self.knowledge = KnowledgePage(self.controller)
        self.evidence = EvidencePage(self.controller)
        self.reports = ReportsPage(self.controller)
        self.log_page = SimpleLogPage()
        self.settings = SettingsPage(self.controller)

        self._add_page("home", self.home)
        self._add_page("project", self.project_page)
        self._add_page("audit", self.audit)
        self._add_page("ai", self.ai_page)
        self._add_page("knowledge", self.knowledge)
        self._add_page("evidence", self.evidence)
        self._add_page("reports", self.reports)
        self._add_page("log", self.log_page)
        self._add_page("settings", self.settings)

        self.footer = QFrame()
        self.footer.setObjectName("FooterBar")
        self.footer.setFixedHeight(32)
        footer_l = QHBoxLayout(self.footer)
        footer_l.setContentsMargins(10, 0, 10, 0)

        brand = QLabel("◈  AEGIS AUDITOR  |  Auditoría Correctiva de Seguridad")
        brand.setObjectName("KpiSub")
        footer_l.addWidget(brand)

        footer_l.addStretch(1)

        self.status = QLabel("Listo")
        self.status.setObjectName("Muted")
        footer_l.addWidget(self.status)

        self.busy_bar = QProgressBar()
        self.busy_bar.setFixedWidth(120)
        self.busy_bar.setRange(0, 1)
        self.busy_bar.setValue(0)
        self.busy_bar.setTextVisible(False)
        footer_l.addWidget(self.busy_bar)

        self.ai_footer = QLabel("○ IA")
        self.ai_footer.setObjectName("Muted")
        footer_l.addWidget(self.ai_footer)

        content_l.addWidget(self.footer)

        self._wire_pages()
        self._wire_controller()
        self.navigate("home")
        self.refresh_all()

    def _add_page(self, key: str, page: QWidget) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        holder = QWidget()
        holder.setObjectName("Root")
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(page)
        scroll.setWidget(holder)
        self.page_keys[key] = self.stack.addWidget(scroll)

    def _wire_pages(self):
        self.project_page.request_new.connect(self.open_new_project)
        self.project_page.request_load_profile.connect(self.choose_profile)
        self.project_page.request_load_source.connect(self.choose_source)
        self.project_page.request_load_evidence.connect(self.choose_evidence)

        self.audit.request_ai.connect(self.open_ai_for_row)
        self.reports.save_requested.connect(self.save_report)

    def _wire_controller(self):
        c = self.controller
        c.state_changed.connect(self.refresh_all)
        c.results_changed.connect(self.audit.set_rows)
        c.busy_changed.connect(self.set_busy)
        c.log_message.connect(self.append_log)
        c.error_message.connect(
            lambda title, body: QMessageBox.critical(
                self,
                title,
                body,
            )
        )
        c.info_message.connect(
            lambda title, body: QMessageBox.information(
                self,
                title,
                body,
            )
        )
        c.ai_proposals_changed.connect(
            self._ai_proposals_ready
        )
        c.evidence_changed.connect(self.evidence.refresh)

    # ------------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------------
    def navigate(self, key: str) -> None:
        if key not in self.page_keys:
            return
        self.current_page = key
        self.stack.setCurrentIndex(self.page_keys[key])
        self.sidebar.set_active(key)
        self._refresh_page(key)

    def _refresh_page(self, key: str):
        if key == "home":
            self.home.refresh()
        elif key == "project":
            self.project_page.refresh()
        elif key == "knowledge":
            self.knowledge.refresh()
        elif key == "evidence":
            self.evidence.refresh()
        elif key == "reports":
            self.reports.refresh()
        elif key == "settings":
            self.settings.refresh()

    # ------------------------------------------------------------------
    # Centro de carga
    # ------------------------------------------------------------------
    def open_load_center(self):
        dialog = LoadCenterDialog(self)
        dialog.request_new_project.connect(self.open_new_project)
        dialog.request_profile.connect(self.choose_profile)
        dialog.request_source.connect(self.choose_source)
        dialog.request_package.connect(self.import_package)
        dialog.request_accounts.connect(self.import_accounts)
        dialog.request_evidence.connect(self.choose_evidence)
        dialog.request_recipes.connect(self.import_recipes)
        dialog.request_ai.connect(lambda: self.navigate("settings"))
        dialog.exec()

    def open_new_project(self):
        dialog = AutoProfileDialog(self)

        def ready(profile: str, root: str):
            try:
                self.controller.load_target(root)
                self.controller.load_profile(profile)
                self.navigate("home")
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "No se pudo cargar el proyecto",
                    str(exc),
                )

        dialog.profile_ready.connect(ready)
        dialog.exec()

    def choose_profile(self):
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Cargar perfil JSON",
            str(default_recipe_dir().parent / "config"),
            "Perfil JSON (*.json)",
        )
        if selected:
            try:
                self.controller.load_profile(selected)
                self.navigate("home")
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Perfil inválido",
                    str(exc),
                )

    def choose_source(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            "Selecciona la carpeta de código",
            str(self.controller.target_root or Path.home()),
        )
        if selected:
            try:
                self.controller.load_target(selected)
                self.navigate("home")
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "No se pudo cargar",
                    str(exc),
                )

    def choose_evidence(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            "Selecciona carpeta de evidencias",
            str(self.controller.evidence_base),
        )
        if selected:
            self.controller.set_evidence_base(selected)
            self.navigate("evidence")

    def import_package(self):
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Importar auditor-package.json",
            str(Path.home()),
            "auditor-package.json (auditor-package.json);;JSON (*.json)",
        )
        if not selected:
            return

        path = Path(selected).resolve()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("El descriptor debe ser un objeto JSON.")
            saved = self.controller.auto_profile(path.parent)
            self.append_log(
                f"auditor-package.json incorporado; perfil: {saved}"
            )
            self.navigate("home")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "No se pudo importar",
                str(exc),
            )

    def import_accounts(self):
        if not self.controller.config_path:
            QMessageBox.information(
                self,
                "Cuentas y roles",
                "Carga o genera primero un perfil JSON.",
            )
            return

        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Importar cuentas y roles",
            str(Path.home()),
            "JSON/CSV (*.json *.csv)",
        )
        if not selected:
            return

        source = Path(selected)
        accounts: list[dict] = []
        privileged_roles: list[str] = []

        try:
            if source.suffix.lower() == ".csv":
                with source.open(
                    "r",
                    encoding="utf-8-sig",
                    newline="",
                ) as handle:
                    for row in csv.DictReader(handle):
                        username = (
                            row.get("username")
                            or row.get("usuario")
                            or ""
                        ).strip()
                        if not username:
                            continue
                        role = (
                            row.get("role")
                            or row.get("rol")
                            or "USER"
                        ).strip()
                        accounts.append(
                            {
                                "username": username,
                                "password": (
                                    row.get("password")
                                    or row.get("contraseña")
                                    or None
                                ),
                                "role": role,
                                "auth_type": (
                                    row.get("auth_type")
                                    or "none"
                                ),
                                "token": row.get("token") or None,
                                "headers": {},
                            }
                        )
                        flag = str(
                            row.get("privileged")
                            or row.get("privilegiado")
                            or ""
                        ).lower()
                        if flag in {"1", "true", "yes", "si", "sí"}:
                            privileged_roles.append(role)
            else:
                raw = json.loads(source.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    accounts = raw
                else:
                    accounts = list(
                        raw.get("cuentas")
                        or raw.get("accounts")
                        or []
                    )
                    privileged_roles = list(
                        raw.get("roles_privilegiados")
                        or raw.get("privileged_roles")
                        or []
                    )

            profile_path = self.controller.config_path
            profile = json.loads(
                profile_path.read_text(encoding="utf-8")
            )
            existing = {
                item.get("username"): item
                for item in profile.get("cuentas", [])
                if item.get("username")
            }
            for account in accounts:
                if account.get("username"):
                    existing[account["username"]] = account
            profile["cuentas"] = list(existing.values())

            roles = list(profile.get("roles_privilegiados") or [])
            for role in privileged_roles:
                if role and role not in roles:
                    roles.append(role)
            profile["roles_privilegiados"] = roles

            profile_path.write_text(
                json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self.controller.load_profile(profile_path)
            QMessageBox.information(
                self,
                "Importación completada",
                f"Se incorporaron {len(accounts)} cuenta(s).",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "No se pudieron importar",
                str(exc),
            )

    def import_recipes(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            "Selecciona carpeta de recetas o medicinas",
            str(Path.home()),
        )
        if not selected:
            return

        source = Path(selected)
        recipes = 0
        medicines = 0
        skipped = 0
        try:
            for path in source.rglob("*.json"):
                try:
                    data = json.loads(
                        path.read_text(encoding="utf-8")
                    )
                except Exception:
                    skipped += 1
                    continue

                if data.get("tipo") == "conocimiento_correctivo_semantico":
                    family = str(
                        data.get("familia_control")
                        or data.get("control_id")
                        or "conocimiento"
                    )
                    safe = (
                        family.replace("/", "-")
                        .replace("\\", "-")
                    )
                    folder = knowledge_root() / safe
                    folder.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, folder / path.name)
                    medicines += 1
                elif data.get("control_id"):
                    safe = (
                        str(data["control_id"])
                        .replace("/", "-")
                        .replace("\\", "-")
                    )
                    folder = biblioteca_por_defecto() / safe
                    folder.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, folder / path.name)
                    recipes += 1
                else:
                    skipped += 1

            self.knowledge.refresh()
            QMessageBox.information(
                self,
                "Conocimiento importado",
                f"Recetas: {recipes}\nMedicinas: {medicines}\nOmitidos: {skipped}",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "No se pudo importar",
                str(exc),
            )

    # ------------------------------------------------------------------
    # IA / reportes / estado
    # ------------------------------------------------------------------
    def open_ai_for_row(self, row: dict):
        self.ai_page.set_target(row)
        self.ai_page.refresh_provider()
        self.navigate("ai")

    def _ai_proposals_ready(self, proposals: list):
        self.ai_page.set_proposals(proposals)
        self.navigate("ai")

    def save_report(self):
        if not self.controller.resultado:
            QMessageBox.information(
                self,
                "Sin diagnóstico",
                "Ejecuta primero la auditoría.",
            )
            return

        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Guardar reporte",
            str(Path.cwd() / "reporte-aegis.json"),
            "JSON (*.json)",
        )
        if selected:
            Path(selected).write_text(
                json.dumps(
                    self.controller.resultado,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            QMessageBox.information(
                self,
                "Reporte guardado",
                selected,
            )

    def append_log(self, text: str):
        self.home.append_log(text)
        self.log_page.append(text)

    def set_busy(self, busy: bool, text: str):
        self._busy = busy
        self.status.setText(text)
        if busy:
            self.busy_bar.setRange(0, 0)
        else:
            self.busy_bar.setRange(0, 1)
            self.busy_bar.setValue(0)

    def refresh_all(self):
        self.topbar.refresh(self.controller)
        self.home.refresh()
        self.project_page.refresh()
        self.knowledge.refresh()
        self.reports.refresh()
        self.settings.refresh()

        enabled, model = self.controller.ai_status()
        self.sidebar.set_ai(enabled, model)
        self.ai_footer.setText(
            f"● IA · {model}"
            if enabled
            else "○ IA"
        )
        self.ai_footer.setStyleSheet(
            f"color:{COLORS['success'] if enabled else COLORS['muted']};"
        )

        self._refresh_page(self.current_page)

    # ------------------------------------------------------------------
    # Responsive / plataforma
    # ------------------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = event.size().width()
        sidebar_compact = width < 1040
        page_compact = width < 1220
        self.sidebar.set_compact(sidebar_compact)
        self.topbar.set_compact(page_compact)
        self.home.set_compact(page_compact)

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_windows_dark_titlebar()

    def _apply_windows_dark_titlebar(self):
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

    def closeEvent(self, event: QCloseEvent):
        if self.controller.proceso and self.controller.process_running():
            answer = QMessageBox.question(
                self,
                "Cerrar Aegis Auditor",
                "La aplicación objetivo está en ejecución. "
                "¿Deseas detenerla antes de cerrar?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.StandardButton.Yes:
                try:
                    self.controller.proceso.stop()
                except Exception:
                    pass
        event.accept()


def run_qt_app() -> int:
    configure_packaged_environment()

    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName("Aegis Auditor")
    app.setOrganizationName("Aegis Auditor")
    app.setWindowIcon(brand_icon())
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet(QSS)

    window = AegisMainWindow()
    window.show()

    if owns_app:
        return app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_qt_app())
