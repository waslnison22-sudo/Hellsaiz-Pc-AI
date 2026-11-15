from __future__ import annotations


DARK_STYLESHEET = """
QMainWindow, QWidget {
    background: transparent;
    color: #e8edf4;
    font-family: "Segoe UI";
}
QFrame#sidebar {
    background: rgba(10, 14, 20, 224);
    border: 1px solid rgba(218, 230, 246, 42);
    border-radius: 20px;
}
QFrame#contentFrame {
    background: rgba(7, 10, 15, 190);
    border: 1px solid rgba(218, 230, 246, 35);
    border-radius: 20px;
}
QFrame#wallpaperPreview, QFrame#profilePanel {
    background: rgba(24, 30, 39, 196);
    border: 1px solid rgba(215, 228, 245, 55);
    border-radius: 16px;
}
QFrame#softDivider {
    background: rgba(210, 225, 245, 30);
    border: 0;
    max-height: 1px;
}
QLabel#brandMark {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 rgba(248,251,255,245), stop:1 rgba(126,139,158,200));
    color: #111722;
    border-radius: 12px;
    font-size: 23px;
    font-weight: 800;
}
QListWidget#mainNavigation {
    background: transparent;
    border: 1px solid transparent;
    padding: 2px;
}
QListWidget#mainNavigation::item {
    color: #aab4c1;
    padding: 12px 12px;
    border-radius: 11px;
    margin: 2px 0;
}
QListWidget#mainNavigation::item:hover {
    background: rgba(218, 230, 246, 24);
    color: #f4f7fb;
}
QListWidget#mainNavigation::item:selected {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 rgba(215,228,245,50), stop:1 rgba(145,159,180,28));
    color: #f5f8fc;
    border: 1px solid rgba(221, 233, 250, 70);
}
QListWidget#mainNavigation:focus {
    border: 1px solid rgba(220, 232, 248, 100);
    border-radius: 13px;
}
QTextEdit, QLineEdit, QPlainTextEdit, QComboBox, QListWidget {
    background: rgba(15, 20, 28, 224);
    color: #edf2f8;
    border: 1px solid rgba(204, 219, 239, 48);
    border-radius: 12px;
    padding: 10px;
    selection-background-color: #465265;
}
QTextEdit {
    background: rgba(9, 13, 19, 155);
    border: 1px solid rgba(211, 225, 244, 25);
    padding: 14px;
}
QLineEdit {
    min-height: 24px;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 1px solid rgba(225, 237, 252, 150);
    background: rgba(18, 24, 34, 238);
}
QPushButton {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(48,57,70,224), stop:1 rgba(27,34,44,238));
    color: #e8edf4;
    border: 1px solid rgba(211, 225, 244, 55);
    border-radius: 11px;
    padding: 10px 15px;
    font-weight: 550;
}
QPushButton:hover {
    background: rgba(91, 105, 126, 210);
    border-color: rgba(233, 241, 251, 120);
}
QPushButton:focus {
    border: 1px solid #f7f9fc;
    background: rgba(75, 88, 106, 245);
}
QPushButton:pressed {
    background: rgba(22, 28, 37, 245);
    border-color: rgba(233, 241, 251, 150);
}
QPushButton:disabled {
    color: #6f7a89;
    background: rgba(28, 34, 43, 150);
    border-color: rgba(155, 169, 188, 25);
}
QPushButton#sendButton, QPushButton#primaryButton {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #f7f9fc, stop:1 #c8d1de);
    color: #101721;
    border: 1px solid #ffffff;
    font-weight: 700;
}
QPushButton#sendButton:hover, QPushButton#primaryButton:hover {
    background: #ffffff;
}
QPushButton#profileButton, QPushButton#voiceButton {
    background: rgba(24, 30, 39, 222);
    color: #d5deea;
    border: 1px solid rgba(213, 226, 244, 54);
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
    background: rgba(207, 222, 243, 42);
    color: #ffffff;
}
QLabel {
    color: #d7e0eb;
    background: transparent;
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
    background: rgba(16, 21, 29, 230);
}
QCheckBox::indicator:checked {
    background: #e7edf5;
    border-color: #e7edf5;
}
QSplitter::handle {
    background: rgba(190, 207, 229, 70);
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
QToolTip {
    background: #161c26;
    color: #f0f4fa;
    border: 1px solid rgba(211, 225, 244, 80);
    border-radius: 7px;
    padding: 6px 8px;
}
"""


def build_dark_stylesheet() -> str:
    """Return the shared monochrome theme with visible keyboard focus states."""
    return DARK_STYLESHEET
