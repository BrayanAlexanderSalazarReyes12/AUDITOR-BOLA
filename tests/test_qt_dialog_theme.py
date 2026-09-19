import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from auditor_bola.qt_ui.dialogs import (
    AutoProfileDialog,
    LoadCenterDialog,
)
from auditor_bola.qt_ui.theme import QSS


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    return app


def test_load_center_uses_dark_aegis_dialog_canvas():
    app = _app()
    dialog = LoadCenterDialog()
    dialog.show()
    app.processEvents()

    assert dialog.objectName() == "AegisDialog"
    assert dialog.testAttribute(
        Qt.WidgetAttribute.WA_StyledBackground
    )
    assert dialog.dialog_root.objectName() == "DialogRoot"
    assert dialog.dialog_root.testAttribute(
        Qt.WidgetAttribute.WA_StyledBackground
    )

    cards = dialog.findChildren(
        QPushButton,
        "LoadCard",
    )
    assert len(cards) == 8
    assert all(card.minimumHeight() >= 100 for card in cards)

    titles = dialog.findChildren(
        QLabel,
        "DialogTitle",
    )
    assert any(label.text() == "Centro de carga" for label in titles)

    dialog.close()


def test_new_project_dialog_uses_dark_root_and_structured_cards():
    app = _app()
    dialog = AutoProfileDialog()
    dialog.show()
    app.processEvents()

    assert dialog.objectName() == "AegisDialog"
    assert dialog.dialog_root.objectName() == "DialogRoot"
    assert dialog.preview.objectName() == "DialogCodePreview"
    assert dialog.stepper is not None

    titles = dialog.findChildren(
        QLabel,
        "DialogTitle",
    )
    assert any(
        label.text() == "Incorporar aplicación"
        for label in titles
    )

    assert dialog.minimumWidth() >= 880
    assert dialog.minimumHeight() >= 600

    dialog.close()


def test_dialog_theme_contains_no_native_light_canvas_fallback():
    assert "QDialog#AegisDialog" in QSS
    assert "QWidget#DialogRoot" in QSS
    assert "background: #06121D;" in QSS
    assert "QPushButton#LoadCard" in QSS
    assert "QFrame#DialogHero" in QSS
