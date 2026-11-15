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
QFrame#workflowCard, QGroupBox#workflowCard {
    background: rgba(19, 24, 32, 220);
    border: 1px solid rgba(211, 225, 244, 42);
    border-radius: 15px;
}
QFrame#workflowActionCard {
    background: rgba(25, 31, 40, 225);
    border: 1px solid rgba(205, 219, 238, 54);
    border-radius: 13px;
}
QLabel#sectionEyebrow {
    color: #9ca9ba;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.3px;
}
QLabel#workflowHint {
    color: #98a4b3;
    font-size: 11px;
}
QScrollArea {
    background: transparent;
    border: 0;
}
QTimeEdit, QSpinBox, QDoubleSpinBox {
    background: rgba(15, 20, 28, 224);
    color: #edf2f8;
    border: 1px solid rgba(204, 219, 239, 48);
    border-radius: 10px;
    min-height: 24px;
    padding: 7px 9px;
}
QTimeEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid rgba(225, 237, 252, 150);
}
QSlider::groove:horizontal {
    background: rgba(170, 185, 205, 65);
    height: 5px;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: rgba(230, 237, 247, 190);
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #f1f4f8;
    border: 1px solid #ffffff;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QToolButton {
    background: rgba(31, 38, 49, 220);
    color: #dfe6ef;
    border: 1px solid rgba(204, 219, 239, 42);
    border-radius: 8px;
    padding: 5px 8px;
}
QToolButton:hover {
    background: rgba(75, 88, 106, 220);
    border-color: rgba(233, 241, 251, 110);
}
QPushButton#dangerButton {
    background: rgba(39, 42, 48, 215);
    color: #e1e4e9;
    border-color: rgba(185, 193, 204, 48);
}
QPushButton#dangerButton:hover {
    background: rgba(72, 76, 84, 225);
    border-color: rgba(220, 227, 238, 110);
}
QPushButton#secondaryButton {
    background: rgba(19, 24, 32, 190);
    color: #dce4ee;
    border-color: rgba(202, 216, 236, 44);
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
    """Return the shared monochrome theme with visible keyboard focus states.
QFrame#studioPanel {
    background: rgba(14, 19, 27, 222);
    border: 1px solid rgba(211, 225, 244, 48);
    border-radius: 16px;
}
QGroupBox#scenarioCard, QGroupBox#scenarioBranchCard {
    background: rgba(20, 26, 35, 218);
    border: 1px solid rgba(211, 225, 244, 48);
    border-radius: 14px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
    font-weight: 650;
    color: #edf2f8;
}
QGroupBox#scenarioCard::title, QGroupBox#scenarioBranchCard::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #dce4ee;
}
QGroupBox#scenarioBranchCard {
    background: rgba(16, 21, 29, 220);
}
QFrame#scenarioActionCard {
    background: rgba(26, 32, 42, 224);
    border: 1px solid rgba(205, 219, 238, 54);
    border-radius: 12px;
}
QLabel#pageTitle {
    color: #f2f5f9;
    font-size: 20px;
    font-weight: 700;
}
QLabel#sectionTitle {
    color: #f0f4f9;
    font-size: 15px;
    font-weight: 700;
}
QLabel#cardTitle {
    color: #eff3f8;
    font-size: 13px;
    font-weight: 650;
}
QLabel#secondaryText, QLabel#scenarioStatus, QLabel#sectionEyebrow {
    color: #9da9b8;
}
QLabel#warningText {
    background: rgba(45, 48, 55, 170);
    color: #e3e7ed;
    border: 1px solid rgba(200, 210, 224, 52);
    border-radius: 10px;
    padding: 9px 11px;
}
QTabWidget::pane {
    background: rgba(10, 14, 20, 170);
    border: 1px solid rgba(210, 224, 243, 36);
    border-radius: 12px;
    top: -1px;
}
QTabBar::tab {
    background: rgba(20, 26, 35, 190);
    color: #aeb8c6;
    border: 1px solid rgba(210, 224, 243, 38);
    border-bottom: 0;
    padding: 8px 13px;
    margin-right: 4px;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
}
QTabBar::tab:selected {
    background: rgba(54, 63, 76, 220);
    color: #f2f5f9;
    border-color: rgba(222, 233, 248, 95);
}
QTabBar::tab:focus {
    border: 1px solid #f4f7fb;
}
QPushButton#toolbarButton {
    background: rgba(27, 34, 44, 218);
    padding: 7px 10px;
    border-radius: 9px;
    font-size: 11px;
}
QPushButton#dangerButton {
    background: rgba(39, 42, 48, 215);
    color: #e1e4e9;
    border-color: rgba(185, 193, 204, 48);
}
QPushButton#dangerButton:hover {
    background: rgba(72, 76, 84, 225);
    border-color: rgba(220, 227, 238, 110);
}
QCheckBox#animationToggle {
    color: #bfc9d6;
}
"""
    return DARK_STYLESHEET
