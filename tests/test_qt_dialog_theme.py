import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QFrame

from auditor_bola.qt_ui.dialogs import (
    AutoProfileDialog,
    LoadCenterDialog,
    calculate_dialog_size,
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
        QFrame,
        "LoadCard",
    )
    assert len(cards) == 8
    assert all(card.minimumHeight() >= 90 for card in cards)

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

    assert dialog.footer_frame.isVisible()
    assert dialog.content_splitter is not None

    dialog.close()


def test_dialog_theme_contains_no_native_light_canvas_fallback():
    assert "QDialog#AegisDialog" in QSS
    assert "QWidget#DialogRoot" in QSS
    assert "background: #06121D;" in QSS
    assert "QFrame#LoadCard" in QSS
    assert "QFrame#DialogHero" in QSS


def test_dialog_size_never_exceeds_high_dpi_available_geometry():
    width, height, min_width, min_height = calculate_dialog_size(
        available_width=905,
        available_height=548,
        preferred_width=1120,
        preferred_height=690,
        minimum_width=760,
        minimum_height=500,
        margin=22,
    )

    assert width <= 905 - 44
    assert height <= 548 - 44
    assert min_width <= width
    assert min_height <= height


def test_dialog_size_keeps_preferred_size_on_large_screen():
    width, height, min_width, min_height = calculate_dialog_size(
        available_width=1920,
        available_height=1040,
        preferred_width=1120,
        preferred_height=690,
        minimum_width=760,
        minimum_height=500,
        margin=22,
    )

    assert (width, height) == (1120, 690)
    assert (min_width, min_height) == (760, 500)
