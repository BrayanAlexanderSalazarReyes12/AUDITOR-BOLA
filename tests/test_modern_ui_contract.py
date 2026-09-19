from auditor_bola.ui.components.load_center import LoadCenter
from auditor_bola.ui.router import PageRouter
from auditor_bola.ui.theme import COLORS


class DummyPage:
    def __init__(self):
        self.visible = False

    def pack(self, **_kwargs):
        self.visible = True

    def pack_forget(self):
        self.visible = False


def test_router_cambia_paginas_sin_notebook_tk():
    router = PageRouter()
    home = DummyPage()
    audit = DummyPage()

    router.register("home", home)
    router.register("audit", audit)

    assert router.select("home") == "home"
    assert home.visible is True
    assert audit.visible is False

    assert router.select(audit) == "audit"
    assert home.visible is False
    assert audit.visible is True


def test_centro_carga_cubre_todos_los_puntos_de_entrada():
    keys = {item[0] for item in LoadCenter.ITEMS}

    assert keys == {
        "new_project",
        "profile",
        "source",
        "package",
        "accounts",
        "evidence",
        "recipes",
        "ai",
    }


def test_tema_moderno_define_jerarquia_visual():
    assert COLORS["bg"] != COLORS["surface"]
    assert COLORS["surface"] != COLORS["surface_2"]
    assert COLORS["accent"]
    assert COLORS["success"]
    assert COLORS["danger"]


def test_app_moderna_se_puede_importar_sin_crear_ventana():
    from auditor_bola.ui.app import ModernAuditorGUI

    assert ModernAuditorGUI.__name__ == "ModernAuditorGUI"
