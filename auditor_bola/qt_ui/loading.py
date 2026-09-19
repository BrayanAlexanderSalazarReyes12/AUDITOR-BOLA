"""Componentes visuales de carga y progreso de Aegis Auditor."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..version import __version__
from .widgets import brand_icon


class StartupSplash(QWidget):
    """Pantalla de arranque fullscreen con progreso explícito."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StartupSplash")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.addStretch(1)

        panel = QFrame()
        panel.setObjectName("SplashPanel")
        panel.setMaximumWidth(680)
        panel.setMinimumWidth(460)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(44, 38, 44, 36)
        layout.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(brand_icon().pixmap(118, 118))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        title = QLabel("AEGIS AUDITOR")
        title.setObjectName("SplashTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(f"Security Remediation Studio  ·  v{__version__}")
        subtitle.setObjectName("SplashSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        row = QHBoxLayout()
        self.status = QLabel("Inicializando…")
        self.status.setObjectName("SplashStatus")
        row.addWidget(self.status, 1)
        self.percent = QLabel("0%")
        self.percent.setObjectName("SplashPercent")
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(self.percent)
        layout.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setObjectName("SplashProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        root.addWidget(panel, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addStretch(1)

    def set_progress(self, value: int, text: str) -> None:
        value = max(0, min(100, int(value)))
        self.progress.setValue(value)
        self.percent.setText(f"{value}%")
        self.status.setText(text)


class TaskProgressOverlay(QFrame):
    """Bloquea la UI durante tareas y muestra avance estimado."""

    progress_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TaskOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()
        self._value = 0
        self._active = False
        self._run_id = 0
        self._external_progress = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.addStretch(1)

        panel = QFrame()
        panel.setObjectName("TaskProgressPanel")
        panel.setMaximumWidth(540)
        panel.setMinimumWidth(420)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(10)

        logo = QLabel()
        logo.setPixmap(brand_icon().pixmap(62, 62))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        title = QLabel("Procesando")
        title.setObjectName("TaskProgressTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.status = QLabel("Preparando tarea…")
        self.status.setObjectName("TaskProgressStatus")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.percent = QLabel("0%")
        self.percent.setObjectName("TaskProgressPercent")
        self.percent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.percent)

        self.progress = QProgressBar()
        self.progress.setObjectName("TaskProgressBar")
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        hint = QLabel("Aegis mantendrá esta pantalla hasta completar la operación.")
        hint.setObjectName("TaskProgressStatus")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        root.addWidget(panel, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addStretch(1)

        self.timer = QTimer(self)
        self.timer.setInterval(220)
        self.timer.timeout.connect(self._tick)

    def start(self, text: str) -> None:
        self._run_id += 1
        self._active = True
        self._external_progress = False
        self._value = 4
        self.status.setText(text or "Procesando…")
        self._render()
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self.timer.start()

    def _tick(self) -> None:
        if not self._active or self._external_progress:
            return
        if self._value < 38:
            self._value += 4
        elif self._value < 68:
            self._value += 2
        elif self._value < 92:
            self._value += 1
        self._value = min(self._value, 92)
        self._render()

    def set_progress(self, value: int, text: str | None = None) -> None:
        """Actualiza el avance real informado por la tarea en segundo plano."""
        if not self._active:
            return
        self._external_progress = True
        self._value = max(0, min(99, int(value)))
        if text:
            self.status.setText(text)
        self._render()

    def finish(self, text: str = "Tarea completada") -> None:
        token = self._run_id
        self._active = False
        self.timer.stop()
        self._value = 100
        self.status.setText(text or "Tarea completada")
        self._render()
        def hide_if_current() -> None:
            if token == self._run_id and not self._active:
                self.hide()
        QTimer.singleShot(420, hide_if_current)

    def _render(self) -> None:
        self.progress.setValue(self._value)
        self.percent.setText(f"{self._value}%")
        self.progress_changed.emit(self._value)
