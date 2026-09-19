"""Cálculos de diseño responsivo independientes de Tk."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResponsiveLayout:
    width: int
    height: int
    compact: bool
    ultra_compact: bool
    sidebar_width: int
    content_padding: int
    font_delta: int


def calculate_responsive_layout(
    screen_w: int,
    screen_h: int,
    *,
    preferred_w: int = 1360,
    preferred_h: int = 820,
) -> ResponsiveLayout:
    """Calcula geometría segura para pantallas desde 1024×600 hasta 4K.

    No intenta forzar una resolución mínima física: mantiene márgenes,
    limita el tamaño inicial y activa densidades más compactas cuando el
    espacio disponible es reducido.
    """
    screen_w = max(800, int(screen_w or 0))
    screen_h = max(500, int(screen_h or 0))

    margin_x = 40
    margin_y = 80

    width = min(preferred_w, max(760, screen_w - margin_x))
    height = min(preferred_h, max(520, screen_h - margin_y))

    ultra = screen_w < 1100 or screen_h < 650
    compact = ultra or screen_w < 1450 or screen_h < 800

    if ultra:
        sidebar = 154
        padding = 5
        font_delta = -1
    elif compact:
        sidebar = 190
        padding = 7
        font_delta = 0
    else:
        sidebar = 236
        padding = 10
        font_delta = 0

    return ResponsiveLayout(
        width=width,
        height=height,
        compact=compact,
        ultra_compact=ultra,
        sidebar_width=sidebar,
        content_padding=padding,
        font_delta=font_delta,
    )


def calculate_wizard_geometry(
    screen_w: int,
    screen_h: int,
) -> tuple[int, int, bool]:
    """Tamaño del asistente sin salirse de pantallas pequeñas."""
    screen_w = max(800, int(screen_w or 0))
    screen_h = max(500, int(screen_h or 0))

    compact = screen_w < 1280 or screen_h < 760
    width = min(1180, max(760, screen_w - 36))
    height = min(820, max(520, screen_h - 72))
    return width, height, compact
