from __future__ import annotations


# Акцентный градиент приложен к навигации, главной кнопке страницы и выделениям.
# Панели полупрозрачные: обои читаются сквозь интерфейс, текст остаётся контрастным.
ACCENT = "rgba(109, 93, 246"
ACCENT_LIGHT = "rgba(153, 102, 255"

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background: transparent;
    color: #e8edf4;
    font-family: "Segoe UI";
}
QFrame#sidebar {
    background: rgba(10, 13, 20, 168);
    border: 1px solid rgba(218, 230, 246, 38);
    border-radius: 20px;
}
QFrame#contentFrame {
    background: rgba(7, 10, 15, 122);
    border: 1px solid rgba(218, 230, 246, 28);
    border-radius: 20px;
}
QWidget#wallpaperDim {
    background: rgba(4, 6, 10, 120);
    border: 0;
}
QFrame#wallpaperPreview, QFrame#profilePanel {
    background: rgba(12, 16, 25, 150);
    border: 1px solid rgba(215, 228, 245, 45);
    border-radius: 16px;
}
QFrame#softDivider {
    background: rgba(210, 225, 245, 26);
    border: 0;
    max-height: 1px;
}
QLabel#brandMark {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 rgba(109,93,246,255), stop:1 rgba(153,102,255,230));
    color: #ffffff;
    border-radius: 12px;
    font-size: 23px;
    font-weight: 800;
}
QListWidget#mainNavigation {
    background: transparent;
    border: 1px solid transparent;
    padding: 2px;
    outline: 0;
}
QListWidget#mainNavigation::item {
    color: #b6bfcc;
    padding: 11px 14px;
    border-radius: 11px;
    margin: 2px 0;
}
QListWidget#mainNavigation::item:hover {
    background: rgba(109, 93, 246, 42);
    color: #f4f7fb;
}
QListWidget#mainNavigation::item:selected {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(109,93,246,235), stop:1 rgba(153,102,255,200));
    color: #ffffff;
    font-weight: 600;
    border: 0;
}
QListWidget#mainNavigation:focus {
    border: 1px solid rgba(139, 118, 255, 110);
    border-radius: 13px;
}
QTextEdit, QLineEdit, QPlainTextEdit, QComboBox, QListWidget {
    background: rgba(12, 17, 26, 168);
    color: #edf2f8;
    border: 1px solid rgba(204, 219, 239, 42);
    border-radius: 11px;
    padding: 9px 12px;
    selection-background-color: rgba(109, 93, 246, 170);
}
QTextEdit {
    background: rgba(8, 12, 18, 112);
    border: 1px solid rgba(211, 225, 244, 26);
    padding: 14px;
}
QLineEdit {
    min-height: 26px;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 1px solid rgba(139, 118, 255, 200);
    background: rgba(16, 22, 32, 210);
}
QComboBox QAbstractItemView {
    background: rgba(16, 21, 31, 242);
    color: #edf2f8;
    selection-background-color: rgba(109, 93, 246, 170);
    border-radius: 10px;
}
QPushButton {
    background: rgba(28, 34, 46, 208);
    color: #e8edf4;
    border: 1px solid rgba(211, 225, 244, 46);
    border-radius: 10px;
    padding: 9px 16px;
    min-height: 36px;
    font-weight: 600;
}
QPushButton:hover {
    background: rgba(48, 56, 74, 235);
    border-color: rgba(139, 118, 255, 130);
}
QPushButton:focus {
    border: 2px solid rgba(139, 118, 255, 220);
    background: rgba(38, 44, 58, 240);
}
QPushButton:pressed {
    background: rgba(20, 25, 34, 245);
    border-color: rgba(139, 118, 255, 180);
}
QPushButton:disabled {
    color: #6f7a89;
    background: rgba(28, 34, 43, 140);
    border-color: rgba(155, 169, 188, 22);
}
QPushButton#sendButton, QPushButton#primaryButton {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 rgba(109,93,246,255), stop:1 rgba(153,102,255,235));
    color: #ffffff;
    border: 0;
    font-weight: 650;
}
QPushButton#sendButton:hover, QPushButton#primaryButton:hover {
    background: rgba(129, 112, 255, 255);
}
QPushButton#sendButton:pressed, QPushButton#primaryButton:pressed {
    background: rgba(94, 78, 218, 255);
}
QPushButton#sendButton:disabled, QPushButton#primaryButton:disabled {
    background: rgba(74, 68, 138, 120);
    color: rgba(238, 240, 250, 160);
}
QPushButton#profileButton, QPushButton#voiceButton {
    background: rgba(22, 28, 38, 220);
    color: #d5deea;
    border: 1px solid rgba(213, 226, 244, 46);
}
QLabel#statusError {
    color: #ff7b72;
}
QLabel#statusWarn {
    color: #f5c04a;
}
QLabel#statusOk {
    color: #7dd487;
}
QComboBox::drop-down {
    border: 0;
    width: 24px;
}
QListWidget::item {
    padding: 9px 10px;
    border-radius: 9px;
}
QListWidget::item:selected {
    background: rgba(109, 93, 246, 92);
    color: #ffffff;
}
QLabel {
    color: #d7e0eb;
    background: transparent;
    font-size: 13px;
}
QCheckBox {
    color: #d2dbe7;
    spacing: 8px;
}
QCheckBox:focus {
    color: #ffffff;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #8793a3;
    border-radius: 5px;
    background: rgba(16, 21, 29, 220);
}
QCheckBox::indicator:checked {
    background: rgba(109, 93, 246, 235);
    border-color: rgba(139, 118, 255, 235);
}
QSplitter::handle {
    background: rgba(190, 207, 229, 70);
}
QScrollArea {
    background: transparent;
    border: 0;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QTabWidget::pane {
    border: 0;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px 1px 2px 1px;
}
QScrollBar::handle:vertical {
    background: rgba(160, 176, 198, 82);
    min-height: 28px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(205, 218, 237, 140);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    border: 0;
    background: transparent;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 1px 2px 1px 2px;
}
QScrollBar::handle:horizontal {
    background: rgba(160, 176, 198, 82);
    min-width: 28px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: rgba(205, 218, 237, 140);
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    border: 0;
    background: transparent;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}
QTabBar::tab {
    background: transparent;
    color: #b6bfcc;
    padding: 8px 14px;
    border-radius: 9px;
    margin: 2px 4px 2px 0;
    font-weight: 600;
}
QTabBar::tab:hover {
    background: rgba(109, 93, 246, 42);
    color: #f4f7fb;
}
QTabBar::tab:selected {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(109,93,246,235), stop:1 rgba(153,102,255,200));
    color: #ffffff;
    border: 0;
}
QTabWidget::pane > QWidget {
    background: transparent;
}
QFrame#dashboardCard {
    background: rgba(12, 16, 25, 150);
    border: 1px solid rgba(215, 228, 245, 45);
    border-radius: 16px;
}
QLabel#dashboardCardTitle {
    color: #b9c2cf;
    font-size: 11px;
    letter-spacing: 1.2px;
    font-weight: 600;
}
QLabel#dashboardCardValue {
    color: #f4f7fb;
    font-size: 19px;
    font-weight: 700;
}
QLabel#dashboardCardNote {
    color: #9aa4b2;
    font-size: 12px;
}
QPushButton#secondaryButton {
    background: rgba(28, 34, 46, 208);
    color: #d5deea;
}
QToolTip {
    background: #161c26;
    color: #f0f4fa;
    border: 1px solid rgba(139, 118, 255, 110);
    border-radius: 7px;
    padding: 6px 8px;
}
"""


def build_dark_stylesheet() -> str:
    """Return the dark accent-glass theme with visible keyboard focus states."""
    return DARK_STYLESHEET
