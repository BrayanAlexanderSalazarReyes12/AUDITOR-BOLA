import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from auditor_bola.qt_ui.loading import StartupSplash, TaskProgressOverlay
from auditor_bola.qt_ui.theme import QSS
from auditor_bola.version import __version__


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    return app


def test_version_is_1_1_1():
    assert __version__ == "1.1.1"


def test_startup_splash_reports_percentage():
    app = _app()
    splash = StartupSplash()
    splash.set_progress(67, "Cargando módulos…")
    app.processEvents()
    assert splash.progress.value() == 67
    assert splash.percent.text() == "67%"


def test_task_overlay_reports_progress_and_completion():
    app = _app()
    host = QWidget()
    host.resize(1000, 700)
    host.show()
    overlay = TaskProgressOverlay(host)
    overlay.setGeometry(host.rect())
    overlay.start("Ejecutando auditoría…")
    app.processEvents()
    assert overlay.isVisible()
    assert overlay.progress.value() >= 4
    overlay.finish()
    app.processEvents()
    assert overlay.progress.value() == 100
    assert overlay.percent.text() == "100%"


def test_loading_theme_is_available():
    assert "QWidget#StartupSplash" in QSS
    assert "QFrame#TaskOverlay" in QSS
    assert "QFrame#InlineTaskProgress" in QSS
