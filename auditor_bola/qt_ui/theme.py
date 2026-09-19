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
QWidget#StartupSplash {
    background: qradialgradient(cx:0.5, cy:0.42, radius:0.9, fx:0.5, fy:0.42, stop:0 #0D2D43, stop:0.48 #071B29, stop:1 #040B12);
}
QFrame#SplashPanel {
    background: rgba(7, 25, 37, 235);
    border: 1px solid #1E638B;
    border-radius: 22px;
}
QLabel#SplashTitle { color:#FFFFFF; font-size:30px; font-weight:800; }
QLabel#SplashSubtitle { color:#8FA9BC; font-size:12px; }
QLabel#SplashPercent { color:#39C7FF; font-size:24px; font-weight:800; }
QLabel#SplashStatus { color:#B7CFDD; font-size:10px; }
QProgressBar#SplashProgress, QProgressBar#TaskProgressBar, QProgressBar#InlineTaskBar {
    background:#173448; border:none; border-radius:4px;
}
QProgressBar#SplashProgress { min-height:10px; max-height:10px; border-radius:5px; }
QProgressBar#TaskProgressBar { min-height:9px; max-height:9px; }
QProgressBar#InlineTaskBar { min-height:8px; max-height:8px; }
QProgressBar#SplashProgress::chunk, QProgressBar#TaskProgressBar::chunk {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #31D3A2,stop:1 #169BFF);
    border-radius:4px;
}
QProgressBar#InlineTaskBar::chunk { background:#169BFF; border-radius:4px; }
QFrame#TaskOverlay { background:rgba(2,10,16,205); border:none; }
QFrame#TaskProgressPanel {
    background:#0B2030; border:1px solid #1E638B; border-radius:18px;
}
QLabel#TaskProgressTitle { color:#FFFFFF; font-size:18px; font-weight:800; }
QLabel#TaskProgressStatus { color:#9BB4C5; font-size:10px; }
QLabel#TaskProgressPercent { color:#39C7FF; font-size:30px; font-weight:800; }
QFrame#InlineTaskProgress {
    background:#081824; border:1px solid #1A5274; border-radius:10px;
}
QLabel#InlineTaskLabel { color:#C6DBE7; font-size:9px; font-weight:600; }
QLabel#InlineTaskPercent { color:#39C7FF; font-size:11px; font-weight:800; }
QDialog#AegisDialog {
    background: #06121D;
    color: #F4F8FB;
}
QWidget#DialogRoot {
    background: #06121D;
    border: none;
}
QWidget#DialogCanvas {
    background: #06121D;
    border: none;
}
QScrollArea#DialogScroll {
    background: #06121D;
    border: none;
}
QScrollArea#DialogScroll > QWidget > QWidget {
    background: #06121D;
}
QFrame#DialogHero {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #0D2B40,
        stop:1 #0A1D2B
    );
    border: 1px solid #1E638B;
    border-radius: 14px;
}
QLabel#DialogBrandIcon {
    background: transparent;
    border: none;
}
QLabel#DialogTitle {
    background: transparent;
    border: none;
    color: #FFFFFF;
    font-size: 21px;
    font-weight: 800;
}
QLabel#DialogSubtitle {
    background: transparent;
    border: none;
    color: #8FA9BC;
    font-size: 10px;
}
QLabel#DialogPill {
    background: #0B3A56;
    border: 1px solid #1A6D9C;
    border-radius: 11px;
    color: #8EDBFF;
    font-size: 9px;
    font-weight: 700;
    padding: 5px 10px;
}
QFrame#DialogStepperCard {
    background: #0A1D2B;
    border: 1px solid #173E58;
    border-radius: 12px;
}
QFrame#DialogContentCard {
    background: #0B2030;
    border: 1px solid #173E58;
    border-radius: 12px;
}
QFrame#DialogEmptyState {
    background: #081824;
    border: 1px dashed #245E82;
    border-radius: 10px;
}
QLabel#DialogEmptyIcon {
    background: transparent;
    border: none;
    color: #39C7FF;
    font-size: 28px;
    font-weight: 700;
}
QLabel#DialogBodyText {
    background: transparent;
    border: none;
    color: #9BB4C5;
    font-size: 10px;
}
QPlainTextEdit#DialogCodePreview {
    background: #05121C;
    border: 1px solid #173E58;
    border-radius: 10px;
    color: #CFE5F1;
    selection-background-color: #16577F;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 10px;
}
QSplitter#DialogContentSplitter::handle {
    background: #0A1823;
    width: 6px;
    border-radius: 3px;
}
QSplitter#DialogContentSplitter::handle:hover {
    background: #1A5274;
}
QFrame#DialogFooter {
    background: #081824;
    border: 1px solid #14384F;
    border-radius: 10px;
}
QLabel#DialogHint {
    background: transparent;
    border: none;
    color: #7896AA;
    font-size: 9px;
}
QPushButton#DialogSecondaryButton {
    background: #0F2D43;
    border: 1px solid #1A5274;
    border-radius: 8px;
    color: #DDEBF3;
    min-height: 34px;
    padding: 0 14px;
    font-size: 10px;
}
QPushButton#DialogSecondaryButton:hover {
    background: #16405E;
    border-color: #2B7FAE;
}
QFrame#LoadCard {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #0D2A3D,
        stop:1 #0C2435
    );
    border: 1px solid #1B587D;
    border-radius: 12px;
}
QFrame#LoadCard:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #123B55,
        stop:1 #0F3046
    );
    border-color: #39C7FF;
}
QLabel#LoadCardIcon {
    background: #0B3A56;
    border: 1px solid #1A6D9C;
    border-radius: 9px;
    color: #7DDAFF;
    font-size: 16px;
    font-weight: 700;
}
QLabel#LoadCardTitle {
    background: transparent;
    border: none;
    color: #F4F8FB;
    font-size: 11px;
    font-weight: 700;
}
QLabel#LoadCardDescription {
    background: transparent;
    border: none;
    color: #87A6B9;
    font-size: 9px;
}
QLabel#LoadCardArrow {
    background: transparent;
    border: none;
    color: #5FCBFF;
    font-size: 21px;
    font-weight: 700;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QFrame#Sidebar {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #081C2A,
        stop:1 #06131E
    );
    border-right: 1px solid #14384F;
}
QFrame#NavigationBox {
    background: transparent;
    border: none;
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
QFrame#Topbar {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #0D273A,
        stop:1 #091B29
    );
    border: 1px solid #1A5274;
    border-radius: 12px;
}
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
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #18A6FF,
        stop:1 #1187DF
    );
    border: 1px solid #27B4FF;
    color: #FFFFFF;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #29B4FF,
        stop:1 #1594EB
    );
}
QPushButton#ExitButton {
    background: #3A1720;
    border: 1px solid #6E2D3B;
    color: #FFC1CB;
    font-weight: 700;
}
QPushButton#ExitButton:hover {
    background: #58212E;
    border-color: #B94B62;
    color: #FFFFFF;
}
QPushButton#AccountsButton {
    background: #0F3046;
    border: 1px solid #1A5C82;
    color: #B9E9FF;
    font-weight: 700;
}
QPushButton#AccountsButton:hover {
    background: #15405C;
    border-color: #39C7FF;
}
QTableWidget#AccountsTable {
    background: #071824;
    border: 1px solid #173E58;
    border-radius: 10px;
    gridline-color: #14384F;
    color: #DDEBF3;
}
QFrame#AccountsHero {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #0D2B40,
        stop:1 #091D2B
    );
    border: 1px solid #1E638B;
    border-radius: 14px;
}
QLabel#AccountsHeroIcon {
    background: #0B3A56;
    border: 1px solid #1A6D9C;
    border-radius: 10px;
    color: #78D7FF;
    font-size: 20px;
    font-weight: 800;
}
QFrame#AccountsToolbar {
    background: #081824;
    border: 1px solid #14384F;
    border-radius: 10px;
}
QLineEdit#AccountsCellEditor {
    background: #061722;
    border: 1px solid #145072;
    border-radius: 8px;
    min-height: 34px;
    padding: 0 10px;
    color: #F4F8FB;
}
QLineEdit#AccountsCellEditor:focus {
    border-color: #28B8FF;
    background: #071D2A;
}
QComboBox#AccountsAuthCombo {
    background: #061722;
    border: 1px solid #145072;
    border-radius: 8px;
    min-height: 34px;
    padding: 0 26px 0 10px;
    color: #F4F8FB;
}
QComboBox#AccountsAuthCombo:hover,
QComboBox#AccountsAuthCombo:focus {
    border-color: #28B8FF;
}
QComboBox#AccountsAuthCombo::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border: none;
    background: #0D2C40;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
}
QListView#AccountsComboPopup,
QComboBox#AccountsAuthCombo QAbstractItemView {
    background: #081824;
    color: #EAF5FB;
    border: 1px solid #1A5274;
    outline: 0;
    selection-background-color: #145B8C;
    selection-color: #FFFFFF;
    padding: 4px;
}
QListView#AccountsComboPopup::item {
    min-height: 30px;
    padding: 4px 8px;
    border-radius: 5px;
}
QListView#AccountsComboPopup::item:hover {
    background: #103B59;
}
QListView#AccountsComboPopup::item:selected {
    background: #145B8C;
    color: #FFFFFF;
}
QWidget#AccountsCheckWrapper {
    background: transparent;
}
QCheckBox#AccountsPrivilegeCheck {
    spacing: 0;
}
QCheckBox#AccountsPrivilegeCheck::indicator {
    width: 18px;
    height: 18px;
    background: #061722;
    border: 1px solid #2A6688;
    border-radius: 4px;
}
QCheckBox#AccountsPrivilegeCheck::indicator:checked {
    background: #169BFF;
    border-color: #39C7FF;
}
QCheckBox#AccountsShowPasswords {
    color: #B7CFDD;
    font-size: 9px;
    spacing: 7px;
}
QCheckBox#AccountsShowPasswords::indicator {
    width: 16px;
    height: 16px;
    background: #061722;
    border: 1px solid #2A6688;
    border-radius: 4px;
}
QCheckBox#AccountsShowPasswords::indicator:checked {
    background: #169BFF;
    border-color: #39C7FF;
}
QPushButton#AccountsAddButton {
    background: #0F3A51;
    border: 1px solid #1A668C;
    color: #C9ECFF;
    font-weight: 700;
}
QPushButton#AccountsAddButton:hover {
    background: #14506F;
    border-color: #39C7FF;
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
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #145B8C,
        stop:1 #103B59
    );
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


QMessageBox {
    background: #081824;
}
QMessageBox QLabel {
    background: transparent;
    color: #DDEBF3;
    font-size: 10px;
    min-width: 360px;
}
QMessageBox QPushButton {
    background: #0F3A51;
    border: 1px solid #1A668C;
    color: #EAF6FC;
    border-radius: 8px;
    min-width: 84px;
    min-height: 34px;
    padding: 0 14px;
    font-weight: 700;
}
QMessageBox QPushButton:hover {
    background: #14506F;
    border-color: #39C7FF;
}
