from auditor_bola.responsive import (
    calculate_responsive_layout,
    calculate_wizard_geometry,
)


def test_layout_1024x600_activa_ultra_compacto():
    layout = calculate_responsive_layout(1024, 600)

    assert layout.ultra_compact is True
    assert layout.compact is True
    assert layout.width <= 1024
    assert layout.height <= 600
    assert layout.sidebar_width <= 76


def test_layout_laptop_1366x768_es_compacto():
    layout = calculate_responsive_layout(1366, 768)

    assert layout.compact is True
    assert layout.ultra_compact is False
    assert layout.width <= 1366
    assert layout.height <= 768


def test_layout_full_hd_no_desborda():
    layout = calculate_responsive_layout(1920, 1080)

    assert layout.compact is False
    assert layout.width <= 1920
    assert layout.height <= 1080
    assert layout.sidebar_width == 268


def test_layout_4k_no_crece_sin_limite():
    layout = calculate_responsive_layout(3840, 2160)

    assert layout.width == 1540
    assert layout.height == 900
    assert layout.compact is False


def test_wizard_cabe_en_pantalla_pequena():
    width, height, compact = calculate_wizard_geometry(1024, 600)

    assert compact is True
    assert width <= 1024
    assert height <= 600


def test_wizard_full_hd_usa_tamano_comodo():
    width, height, compact = calculate_wizard_geometry(1920, 1080)

    assert compact is False
    assert width == 1180
    assert height == 900
