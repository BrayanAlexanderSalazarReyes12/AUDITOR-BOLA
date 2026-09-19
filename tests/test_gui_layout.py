from auditor_bola.gui import calcular_layout


def test_layout_1280x720_activa_modo_compacto():
    width, height, compact = calcular_layout(1280, 720)
    assert compact is True
    assert width <= 1240
    assert height <= 640


def test_layout_escritorio_grande_no_es_compacto():
    width, height, compact = calcular_layout(1920, 1080)
    assert compact is False
    assert width == 1540
    assert height == 900


def test_layout_pequeno_no_supera_area_disponible_normal():
    width, height, compact = calcular_layout(1024, 600)
    assert compact is True
    assert width == 984
    assert height == 520
