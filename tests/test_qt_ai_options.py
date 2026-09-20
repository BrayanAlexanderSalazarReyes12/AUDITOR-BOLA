import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from auditor_bola.qt_ui.controller import AuditorController
from auditor_bola.qt_ui.pages import AIPage
from auditor_bola.qt_ui.theme import QSS


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_ai_alternatives_are_readable_cards_without_horizontal_scroll():
    _app()
    controller = AuditorController()
    page = AIPage(controller)

    page.set_proposals([
        {
            "enfoque": "MINIMA",
            "titulo": "Validación inmediata del propietario",
            "riesgo": "BAJO",
            "explicacion": (
                "Comprueba la identidad antes de devolver el recurso "
                "y conserva el resto del flujo."
            ),
        },
        {
            "enfoque": "ESTRUCTURAL",
            "titulo": "Centralizar autorización",
            "riesgo": "MEDIO",
            "explicacion": "Mueve la autorización a una política reutilizable.",
        },
        {
            "enfoque": "ALTERNATIVA",
            "titulo": "Filtrar por propietario",
            "riesgo": "BAJO",
            "explicacion": "Acota la consulta al propietario autenticado.",
        },
    ])

    assert page.list.objectName() == "AIProposalList"
    assert page.list.count() == 3
    assert (
        page.list.horizontalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    assert "1. MINIMA" in page.list.item(0).text()
    assert "Riesgo BAJO" in page.list.item(0).text()
    assert "Validación inmediata" in page.list.item(0).text()
    assert page.list.item(0).sizeHint().height() >= 70
    assert page.list.currentRow() == 0


def test_ai_alternatives_theme_has_explicit_dark_and_selected_states():
    assert "QListWidget#AIProposalList {" in QSS
    assert "QListWidget#AIProposalList::item {" in QSS
    assert "QListWidget#AIProposalList::item:selected {" in QSS
    assert "background: #061722;" in QSS
    assert "color: #DDEBF3;" in QSS
    assert "border: 1px solid #39C7FF;" in QSS
