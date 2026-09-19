import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget

from auditor_bola.qt_ui.app import Sidebar, responsive_modes
from auditor_bola.qt_ui.theme import QSS


def _application():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setStyleSheet(QSS)
    return app


def _widget_top_in_sidebar(widget, sidebar):
    return widget.mapTo(sidebar, QPoint(0, 0)).y()


def _widget_bottom_in_sidebar(widget, sidebar):
    return (
        _widget_top_in_sidebar(widget, sidebar)
        + widget.height()
    )


def test_sidebar_branding_never_overlaps_first_navigation_button():
    app = _application()

    host = QWidget()
    host.resize(1680, 900)
    layout = QHBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)

    sidebar = Sidebar(
        lambda _key: None,
        lambda: None,
        lambda: None,
    )
    layout.addWidget(sidebar)

    host.show()
    app.processEvents()

    sidebar.set_compact(False)
    app.processEvents()

    brand_bottom = _widget_bottom_in_sidebar(
        sidebar.brand_box,
        sidebar,
    )
    home_top = _widget_top_in_sidebar(
        sidebar.buttons["home"],
        sidebar,
    )

    assert sidebar.brand_box.height() >= Sidebar.BRAND_MIN_HEIGHT
    assert home_top >= brand_bottom


def test_all_brand_children_fit_inside_brand_container():
    app = _application()

    host = QWidget()
    host.resize(1680, 900)
    layout = QHBoxLayout(host)
    sidebar = Sidebar(
        lambda _key: None,
        lambda: None,
        lambda: None,
    )
    layout.addWidget(sidebar)

    host.show()
    app.processEvents()

    for widget in (
        sidebar.brand_logo,
        sidebar.brand_name,
        sidebar.brand_tagline,
        sidebar.pillars,
        sidebar.brand_divider,
    ):
        child_bottom = (
            widget.mapTo(
                sidebar.brand_box,
                QPoint(0, 0),
            ).y()
            + widget.height()
        )
        assert child_bottom <= sidebar.brand_box.height()


def test_compact_sidebar_hides_brand_text_without_overlap():
    app = _application()

    host = QWidget()
    host.resize(900, 650)
    layout = QHBoxLayout(host)
    sidebar = Sidebar(
        lambda _key: None,
        lambda: None,
        lambda: None,
    )
    layout.addWidget(sidebar)

    host.show()
    sidebar.set_compact(True)
    app.processEvents()

    assert sidebar.width() == Sidebar.COMPACT_WIDTH
    assert not sidebar.brand_name.isVisible()
    assert not sidebar.brand_tagline.isVisible()
    assert not sidebar.pillars.isVisible()

    brand_bottom = _widget_bottom_in_sidebar(
        sidebar.brand_box,
        sidebar,
    )
    home_top = _widget_top_in_sidebar(
        sidebar.buttons["home"],
        sidebar,
    )
    assert home_top >= brand_bottom


def test_high_dpi_wide_screen_keeps_desktop_content_visible():
    # Aproxima una captura de ~1700x900 físicos a 175 % de Windows.
    logical_width = round(1700 / 1.75)
    logical_height = round(900 / 1.75)

    (
        sidebar_compact,
        sidebar_condensed,
        page_compact,
        topbar_compact,
    ) = responsive_modes(
        logical_width,
        logical_height,
        1.75,
    )

    assert sidebar_compact is False
    assert sidebar_condensed is True
    assert page_compact is False
    assert topbar_compact is False


def test_condensed_sidebar_preserves_navigation_labels():
    app = _application()

    host = QWidget()
    host.resize(980, 520)
    layout = QHBoxLayout(host)
    sidebar = Sidebar(
        lambda _key: None,
        lambda: None,
        lambda: None,
    )
    layout.addWidget(sidebar)

    host.show()
    sidebar.set_layout_mode(
        compact=False,
        condensed=True,
    )
    app.processEvents()

    assert sidebar.width() == Sidebar.CONDENSED_WIDTH
    assert sidebar.brand_name.isVisible()
    assert not sidebar.pillars.isVisible()
    assert "Inicio" in sidebar.buttons["home"].text()
    assert "Cargar / Importar" in sidebar.buttons["load"].text()
