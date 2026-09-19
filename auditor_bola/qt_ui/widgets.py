"""Componentes visuales Qt reutilizables."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..app_paths import resource_path
from .theme import COLORS


def add_shadow(widget: QWidget, blur: int = 24, y: int = 6) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y)
    effect.setColor(Qt.GlobalColor.black)
    widget.setGraphicsEffect(effect)


def brand_icon() -> QIcon:
    """Icono compacto para ventana, taskbar y estados pequeños."""
    return QIcon(str(resource_path("assets", "aegis-shield.svg")))


def brand_logo_pixmap(width: int = 190) -> QPixmap:
    """Logo completo oficial para superficies de branding amplias."""
    source = resource_path("assets", "aegis-auditor-logo.png")
    pixmap = QPixmap(str(source))
    if pixmap.isNull():
        return QPixmap()
    return pixmap.scaledToWidth(
        width,
        Qt.TransformationMode.SmoothTransformation,
    )


class Card(QFrame):
    def __init__(self, parent=None, *, elevated: bool = False):
        super().__init__(parent)
        self.setObjectName("CardElevated" if elevated else "Card")


class SectionHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        layout.addWidget(title_label)

        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("Subheading")
            subtitle_label.setWordWrap(True)
            layout.addWidget(subtitle_label)


class MetricCard(Card):
    def __init__(
        self,
        title: str,
        value: str = "—",
        subtitle: str = "",
        parent=None,
    ):
        super().__init__(parent, elevated=True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(1)

        self.title_label = QLabel(title.upper())
        self.title_label.setObjectName("KpiTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("KpiValue")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("KpiSub")

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.subtitle_label)

    def set_value(self, value: str, subtitle: str | None = None) -> None:
        self.value_label.setText(value)
        if subtitle is not None:
            self.subtitle_label.setText(subtitle)


class StageRow(QWidget):
    clicked = Signal()

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(10)

        self.dot = QLabel("○")
        self.dot.setFixedWidth(24)
        self.dot.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight:700;color:#F4F8FB;")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("Muted")
        self.subtitle.setWordWrap(True)
        text_box.addWidget(self.title)
        text_box.addWidget(self.subtitle)

        self.status = QLabel("Pendiente")
        self.status.setObjectName("Muted")
        self.status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.status.setFixedWidth(90)

        layout.addWidget(self.dot)
        layout.addLayout(text_box, 1)
        layout.addWidget(self.status)

    def set_state(self, state: str, detail: str | None = None) -> None:
        mapping = {
            "done": ("✓", COLORS["success"], "Completado"),
            "active": ("●", COLORS["accent"], "En curso"),
            "error": ("!", COLORS["danger"], "Atención"),
            "pending": ("○", COLORS["muted"], "Pendiente"),
        }
        glyph, color, status = mapping.get(state, mapping["pending"])
        self.dot.setText(glyph)
        self.dot.setStyleSheet(
            f"font-size:16px;font-weight:700;color:{color};"
        )
        self.status.setText(status)
        self.status.setStyleSheet(f"font-size:9px;color:{color};")
        if detail is not None:
            self.subtitle.setText(detail)


class Stepper(QWidget):
    def __init__(self, steps: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.steps = steps
        self.badges: list[QLabel] = []
        self.titles: list[QLabel] = []
        self.lines: list[QFrame] = []
        self._active = 0

        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 0, 10, 0)
        outer.setSpacing(0)

        for index, (title, subtitle) in enumerate(steps):
            item = QWidget()
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(4, 0, 4, 0)
            item_layout.setSpacing(2)

            badge = QLabel(str(index + 1))
            badge.setFixedSize(32, 32)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                "background:#17384F;border:1px solid #2A5874;"
                "border-radius:16px;font-weight:700;color:#8FA9BC;"
            )

            title_label = QLabel(title)
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_label.setStyleSheet(
                "font-size:9px;font-weight:700;color:#8FA9BC;"
            )

            subtitle_label = QLabel(subtitle)
            subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            subtitle_label.setStyleSheet(
                "font-size:8px;color:#68859A;"
            )

            item_layout.addWidget(
                badge,
                0,
                Qt.AlignmentFlag.AlignCenter,
            )
            item_layout.addWidget(title_label)
            item_layout.addWidget(subtitle_label)

            outer.addWidget(item, 1)
            self.badges.append(badge)
            self.titles.append(title_label)

            if index < len(steps) - 1:
                line = QFrame()
                line.setFixedHeight(3)
                line.setMinimumWidth(35)
                line.setStyleSheet(
                    "background:#254255;border-radius:1px;"
                )
                outer.addWidget(
                    line,
                    1,
                    Qt.AlignmentFlag.AlignVCenter,
                )
                self.lines.append(line)

        self.set_step(0)

    def set_step(self, step: int) -> None:
        self._active = max(0, min(step, len(self.steps)))

        for index, badge in enumerate(self.badges):
            if index < self._active:
                badge.setText("✓")
                badge.setStyleSheet(
                    "background:#169BFF;border:1px solid #38C8FF;"
                    "border-radius:16px;font-weight:700;color:#FFFFFF;"
                )
                self.titles[index].setStyleSheet(
                    "font-size:9px;font-weight:700;color:#F4F8FB;"
                )
            elif index == self._active and self._active < len(self.steps):
                badge.setText(str(index + 1))
                badge.setStyleSheet(
                    "background:#169BFF;border:1px solid #38C8FF;"
                    "border-radius:16px;font-weight:700;color:#FFFFFF;"
                )
                self.titles[index].setStyleSheet(
                    "font-size:9px;font-weight:700;color:#FFFFFF;"
                )
            else:
                badge.setText(str(index + 1))
                badge.setStyleSheet(
                    "background:#17384F;border:1px solid #2A5874;"
                    "border-radius:16px;font-weight:700;color:#8FA9BC;"
                )
                self.titles[index].setStyleSheet(
                    "font-size:9px;font-weight:700;color:#8FA9BC;"
                )

        for index, line in enumerate(self.lines):
            line.setStyleSheet(
                "background:#169BFF;border-radius:1px;"
                if index < self._active
                else "background:#254255;border-radius:1px;"
            )


class NavButton(QPushButton):
    def __init__(self, icon_text: str, label: str, parent=None):
        super().__init__(f"{icon_text}    {label}", parent)
        self.icon_text = icon_text
        self.label_text = label
        self.setObjectName("NavButton")
        self.setProperty("active", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_compact(self, compact: bool) -> None:
        if compact:
            self.setText(self.icon_text)
            self.setToolTip(self.label_text)
            self.setStyleSheet("text-align:center;padding-left:0;")
        else:
            self.setText(f"{self.icon_text}    {self.label_text}")
            self.setToolTip("")
            self.setStyleSheet("")


class PrimaryButton(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("PrimaryButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
