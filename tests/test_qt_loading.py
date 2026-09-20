import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from auditor_bola.qt_ui.controller import AuditorController
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


def test_version_is_1_1_15():
    assert __version__ == "1.1.15"


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
    overlay.set_progress(63, "Pilar 1 · BOLA · Control 7/12")
    app.processEvents()
    assert overlay.progress.value() == 63
    assert overlay.percent.text() == "63%"
    assert "Control 7/12" in overlay.status.text()
    overlay.finish()
    app.processEvents()
    assert overlay.progress.value() == 100
    assert overlay.percent.text() == "100%"


def test_loading_theme_is_available():
    assert "QWidget#StartupSplash" in QSS
    assert "QFrame#TaskOverlay" in QSS
    assert "QFrame#InlineTaskProgress" in QSS



def test_task_overlay_accepts_real_100_percent():
    app = _app()
    host = QWidget()
    host.resize(1000, 700)
    host.show()
    overlay = TaskProgressOverlay(host)
    overlay.setGeometry(host.rect())
    overlay.start("Iniciando aplicación objetivo…")
    overlay.set_progress(100, "Aplicación objetivo iniciada.")
    app.processEvents()
    assert overlay.progress.value() == 100
    assert overlay.percent.text() == "100%"
    assert "iniciada" in overlay.status.text().lower()



def test_async_worker_finaliza_busy_y_libera_overlay():
    _app()
    controller = AuditorController()
    busy_events = []
    progress_events = []
    controller.busy_changed.connect(
        lambda busy, text: busy_events.append((busy, text))
    )
    controller.task_progress.connect(
        lambda value, text: progress_events.append((value, text))
    )

    class ImmediatePool:
        def start(self, worker):
            assert worker in controller._active_workers
            worker.run()

    controller.pool = ImmediatePool()
    controller._run_async(
        "Iniciando aplicación objetivo…",
        lambda: {"ok": True},
    )

    assert busy_events[0][0] is True
    assert busy_events[-1] == (False, "Listo")
    assert progress_events[-1][0] == 100
    assert controller._active_workers == []
