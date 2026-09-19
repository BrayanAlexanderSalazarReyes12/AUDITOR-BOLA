"""Tema Qt premium de Aegis Auditor."""

from __future__ import annotations

COLORS = {
    "bg": "#06121D",
    "sidebar": "#071925",
    "panel": "#0B2030",
    "panel_2": "#0E293D",
    "panel_3": "#12354E",
    "panel_4": "#081824",
    "border": "#1A5274",
    "border_soft": "#14384F",
    "text": "#F4F8FB",
    "muted": "#8FA9BC",
    "muted_2": "#68859A",
    "accent": "#169BFF",
    "accent_2": "#39C7FF",
    "teal": "#2FD3BD",
    "success": "#31D3A2",
    "warning": "#F2B75A",
    "danger": "#FF6577",
}

QSS = """
* {
    font-family: "Segoe UI", "Inter", sans-serif;
    color: #F4F8FB;
}
QMainWindow, QWidget#Root {
    background: #06121D;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QFrame#Sidebar {
    background: #071925;
    border-right: 1px solid #14384F;
}
QWidget#BrandBox, QFrame#BrandBox {
    background: transparent;
    border: none;
}
QLabel#BrandLogo {
    background: transparent;
    border: none;
}
QLabel#BrandName {
    background: transparent;
    border: none;
    font-size: 18px;
    font-weight: 800;
    color: #F4F8FB;
}
QLabel#BrandTagline {
    background: transparent;
    border: none;
    color: #86A6BA;
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#BrandPillars {
    background: transparent;
    border: none;
    color: #93AFC1;
    font-size: 9px;
    font-weight: 500;
}
QFrame#BrandDivider {
    background: #14384F;
    border: none;
}
QFrame#Topbar,
QFrame#Card,
QFrame#Panel,
QFrame#FooterBar {
    background: #0B2030;
    border: 1px solid #14384F;
    border-radius: 12px;
}
QFrame#CardElevated {
    background: #0E293D;
    border: 1px solid #1A5274;
    border-radius: 12px;
}
QFrame#SubtlePanel {
    background: #081824;
    border: 1px solid #14384F;
    border-radius: 10px;
}
QLabel#BrandTitle {
    font-size: 22px;
    font-weight: 700;
    color: #FFFFFF;
}
QLabel#BrandSubtitle {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    color: #8FA9BC;
}
QLabel#PageTitle {
    font-size: 22px;
    font-weight: 700;
    color: #FFFFFF;
}
QLabel#SectionTitle {
    font-size: 14px;
    font-weight: 700;
    color: #FFFFFF;
}
QLabel#Subheading {
    font-size: 11px;
    color: #8FA9BC;
}
QLabel#Muted {
    color: #8FA9BC;
}
QLabel#KpiTitle {
    font-size: 9px;
    font-weight: 700;
    color: #8FA9BC;
    letter-spacing: .6px;
}
QLabel#KpiValue {
    font-size: 19px;
    font-weight: 700;
    color: #FFFFFF;
}
QLabel#KpiSub {
    font-size: 9px;
    color: #68859A;
}
QLabel#PillSuccess {
    background: #0D3D34;
    color: #63E5C3;
    border: 1px solid #236D5D;
    border-radius: 12px;
    padding: 4px 10px;
    font-size: 9px;
    font-weight: 700;
}
QLabel#PillNeutral {
    background: #102E43;
    color: #B6CDDB;
    border: 1px solid #1A5274;
    border-radius: 12px;
    padding: 4px 10px;
    font-size: 9px;
    font-weight: 700;
}
QLabel#PillWarning {
    background: #44351B;
    color: #FFD68E;
    border: 1px solid #7B6030;
    border-radius: 12px;
    padding: 4px 10px;
    font-size: 9px;
    font-weight: 700;
}
QLabel#PillDanger {
    background: #45212B;
    color: #FFB1BC;
    border: 1px solid #743647;
    border-radius: 12px;
    padding: 4px 10px;
    font-size: 9px;
    font-weight: 700;
}
QPushButton {
    background: #12354E;
    border: 1px solid #1A5274;
    border-radius: 9px;
    min-height: 34px;
    padding: 0 12px;
    color: #EAF5FB;
    font-size: 10px;
}
QPushButton:hover {
    background: #174664;
    border-color: #2D78A4;
}
QPushButton:pressed {
    background: #0E2B40;
}
QPushButton#PrimaryButton {
    background: #169BFF;
    border-color: #169BFF;
    color: #FFFFFF;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover {
    background: #0E84DC;
}
QPushButton#SuccessButton {
    background: #31D3A2;
    border-color: #31D3A2;
    color: #05241B;
    font-weight: 700;
}
QPushButton#DangerButton {
    background: #A83D50;
    border-color: #C65065;
    color: #FFFFFF;
}
QPushButton#NavButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    color: #C4D5DF;
    text-align: left;
    padding-left: 14px;
    min-height: 38px;
    font-size: 10px;
}
QPushButton#NavButton:hover {
    background: #0D324B;
    color: #FFFFFF;
}
QPushButton#NavButton[active="true"] {
    background: #114E79;
    color: #FFFFFF;
    font-weight: 700;
    border-left: 3px solid #38C8FF;
}
QPushButton#IconButton {
    min-width: 34px;
    max-width: 34px;
    min-height: 34px;
    max-height: 34px;
    padding: 0;
}
QLineEdit, QComboBox, QSpinBox {
    background: #071824;
    border: 1px solid #1A5274;
    border-radius: 8px;
    min-height: 34px;
    padding: 0 10px;
    color: #F4F8FB;
}
QLineEdit:focus, QComboBox:focus {
    border-color: #169BFF;
}
QTextEdit, QPlainTextEdit {
    background: #05121C;
    border: 1px solid #14384F;
    border-radius: 9px;
    color: #C9DFEC;
    selection-background-color: #16577F;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 10px;
}
QTableWidget, QTreeWidget {
    background: #071824;
    alternate-background-color: #0A1D2B;
    border: 1px solid #14384F;
    border-radius: 9px;
    gridline-color: #14384F;
    color: #DDEBF3;
    selection-background-color: #114E79;
    selection-color: #FFFFFF;
}
QHeaderView::section {
    background: #0D2A3E;
    color: #BFD4E1;
    border: none;
    border-right: 1px solid #14384F;
    border-bottom: 1px solid #1A5274;
    padding: 8px 8px;
    font-size: 9px;
    font-weight: 700;
}
QTabWidget::pane {
    border: 1px solid #14384F;
    border-radius: 10px;
    background: #0B2030;
}
QTabBar::tab {
    background: #081824;
    color: #8FA9BC;
    border: 1px solid #14384F;
    padding: 8px 14px;
    min-width: 95px;
}
QTabBar::tab:selected {
    background: #10344D;
    color: #FFFFFF;
    border-bottom: 2px solid #169BFF;
}
QProgressBar {
    background: #183346;
    border: none;
    border-radius: 4px;
    height: 7px;
    text-align: center;
}
QProgressBar::chunk {
    background: #169BFF;
    border-radius: 4px;
}
QScrollBar:vertical {
    background: #071824;
    width: 9px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #1A5274;
    min-height: 28px;
    border-radius: 4px;
}
QScrollBar:horizontal {
    background: #071824;
    height: 9px;
}
QScrollBar::handle:horizontal {
    background: #1A5274;
    min-width: 28px;
    border-radius: 4px;
}
QSplitter::handle {
    background: #14384F;
}
QToolTip {
    background: #0D2A3E;
    color: #FFFFFF;
    border: 1px solid #1A5274;
    padding: 5px;
}
"""

def color(name: str) -> str:
    return COLORS[name]
