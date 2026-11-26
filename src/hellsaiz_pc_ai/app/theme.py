from __future__ import annotations


# Акцентный градиент приложен к навигации, главной кнопке страницы и выделениям.
# Панели полупрозрачные: обои читаются сквозь интерфейс, текст остаётся контрастным.
ACCENT = "rgba(232, 194, 158"
ACCENT_LIGHT = "rgba(217, 168, 124"

# Frosted-glass tokens (wave 7). Alphas are 0-255 because Qt QSS has no floats.
GLASS_BG = "rgba(255, 255, 255, 14)"            # 0.055 base tint
GLASS_BG_STRONG = "rgba(255, 255, 255, 20)"     # 0.08 for inputs and chips
GLASS_BORDER = "rgba(255, 255, 255, 26)"        # 0.10 hairline
GLASS_HIGHLIGHT = "rgba(255, 255, 255, 20)"     # 0.08 top highlight
GLASS_RADIUS = "14px"

GLASS_QSS = f"""
/* --- frosted glass surfaces (wave 7) ------------------------------- */
QFrame#glassPanel, QWidget#glassPanel,
QFrame#dashboardCard, QFrame#skillCard,
QFrame#profilePanel, QFrame#chatToast {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {GLASS_HIGHLIGHT},
        stop:0.42 {GLASS_BG},
        stop:1 rgba(255, 255, 255, 10));
    border: 1px solid {GLASS_BORDER};
    border-radius: {GLASS_RADIUS};
}}
/* Nested blocks inside a glass card stay transparent: no double frost. */
QWidget#glassPanelInset, QFrame#glassPanelInset {{
    background: transparent;
    border: 0;
}}
QTextEdit#chatComposer, QWidget#chatQuickCommandsBody {{
    background: {GLASS_BG_STRONG};
    border: 1px solid {GLASS_BORDER};
    border-radius: 12px;
}}
QPushButton#secondaryButton {{
    background: {GLASS_BG_STRONG};
    border: 1px solid {GLASS_BORDER};
    border-radius: 12px;
}}
QPushButton#secondaryButton:hover {{
    background: rgba(255, 255, 255, 30);
    border-color: rgba(255, 255, 255, 60);
}}
QPushButton#ghostButton:hover, QPushButton#navPill:hover {{
    border: 1px solid {GLASS_BORDER};
}}
"""

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background: #0B0B0B;
    color: #F2EFEA;
    font-family: "Segoe UI";
}
QFrame#contentFrame {
    background: transparent;
    border: 0;
    border-radius: 14px;
}
QWidget#wallpaperDim {
    background: rgba(11, 11, 11, 190);
    border: 0;
}
QFrame#wallpaperPreview, QFrame#profilePanel {
    background: #171716;
    border: 0;
    border-radius: 14px;
}
QFrame#softDivider {
    background: rgba(255,255,255,12);
    border: 0;
    max-height: 1px;
}
QLabel#brandMark {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #E8C29E, stop:1 #D9A87C);
    color: #1A140F;
    border-radius: 12px;
    font-size: 23px;
    font-weight: 800;
}
QTextEdit, QLineEdit, QPlainTextEdit, QComboBox, QListWidget {
    background: #171716;
    color: #F2EFEA;
    border: 1px solid rgba(255,255,255,15);
    border-radius: 11px;
    padding: 9px 12px;
    selection-background-color: rgba(232, 194, 158, 120);
}
QTextEdit {
    background: #121211;
    border: 1px solid rgba(255,255,255,12);
    padding: 14px;
}
QLineEdit {
    min-height: 26px;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 1px solid rgba(232, 194, 158, 140);
    background: #1C1C1A;
}
QComboBox QAbstractItemView {
    background: #171716;
    color: #F2EFEA;
    selection-background-color: rgba(232, 194, 158, 120);
    border-radius: 10px;
}
QPushButton {
    background: #171716;
    color: #F2EFEA;
    border: 0;
    border-radius: 12px;
    padding: 9px 16px;
    min-height: 36px;
    font-weight: 600;
}
QPushButton:hover {
    background: #1F1F1D;
    border-color: transparent;
}
QPushButton:focus {
    border: 1px solid rgba(232, 194, 158, 140);
    background: #1F1F1D;
}
QPushButton:pressed {
    background: #121211;
    border-color: transparent;
}
QPushButton:disabled {
    color: #6E6A64;
    background: #131312;
    border-color: transparent;
}
QPushButton#sendButton, QPushButton#primaryButton {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #E8C29E, stop:1 #D9A87C);
    color: #1A140F;
    border: 0;
    font-weight: 650;
}
QPushButton#sendButton:hover, QPushButton#primaryButton:hover {
    background: #F2D2B0;
}
QPushButton#sendButton:pressed, QPushButton#primaryButton:pressed {
    background: #D9A87C;
}
QPushButton#sendButton:disabled, QPushButton#primaryButton:disabled {
    background: rgba(232, 194, 158, 90);
    color: rgba(26, 20, 15, 150);
}
QPushButton#profileButton, QPushButton#voiceButton {
    background: #171716;
    color: #F2EFEA;
    border: 0;
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
    background: rgba(232, 194, 158, 120);
    color: #1A140F;
}
QLabel {
    color: #F2EFEA;
    background: transparent;
    font-size: 14px;
}
QCheckBox {
    color: #F2EFEA;
    spacing: 8px;
}
QCheckBox:focus {
    color: #F2EFEA;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid rgba(255,255,255,45);
    border-radius: 5px;
    background: #1C1C1A;
}
QCheckBox::indicator:checked {
    background: #E8C29E;
    border-color: #E8C29E;
}
QSplitter::handle {
    background: rgba(255,255,255,45);
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
    background: rgba(255,255,255,45);
    min-height: 28px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(255,255,255,80);
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
    background: rgba(255,255,255,45);
    min-width: 28px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: rgba(255,255,255,80);
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
    color: #A6A29C;
    padding: 8px 14px;
    border-radius: 9px;
    margin: 2px 4px 2px 0;
    font-weight: 600;
}
QTabBar::tab:!selected {
    background: #141413;
}
QTabBar::tab:hover {
    background: rgba(232, 194, 158, 42);
    color: #F2EFEA;
}
QTabBar::tab:selected {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #E8C29E, stop:1 #D9A87C);
    color: #1A140F;
    border: 1px solid rgba(232, 194, 158, 130);
}
QTabWidget::pane > QWidget {
    background: transparent;
}
QFrame#dashboardCard {
    background: #171716;
    border: 0;
    border-radius: 14px;
}
QLabel#dashboardCardTitle {
    color: #A6A29C;
    font-size: 13px;
    letter-spacing: 1.2px;
    font-weight: 600;
}
QLabel#dashboardCardValue {
    color: #F2EFEA;
    font-size: 19px;
    font-weight: 700;
}
QLabel#dashboardCardNote {
    color: #A6A29C;
    font-size: 13px;
}
QLabel#dashboardGreeting {
    color: #F2EFEA;
    font-size: 28px;
    font-weight: 600;
}
QLabel#privacyNote {
    color: #bfe8c7;
    background: rgba(125, 212, 135, 20);
    border: 1px solid rgba(125, 212, 135, 45);
    border-radius: 10px;
    padding: 10px 12px;
    font-size: 13px;
}
QLabel#statChipOk {
    color: #7dd487;
    background: rgba(125, 212, 135, 20);
    border: 1px solid rgba(125, 212, 135, 60);
    border-radius: 9px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#statChipWarn {
    color: #f5c04a;
    background: rgba(245, 192, 74, 20);
    border: 1px solid rgba(245, 192, 74, 60);
    border-radius: 9px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#statChipErr {
    color: #ff7b72;
    background: rgba(255, 123, 114, 20);
    border: 1px solid rgba(255, 123, 114, 60);
    border-radius: 9px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}
QFrame#skillCard {
    background: #171716;
    border: 0;
    border-radius: 14px;
}
QLabel#skillCardTitle {
    color: #F2EFEA;
    font-size: 14px;
    font-weight: 650;
}
QLabel#skillCardNote {
    color: #A6A29C;
    font-size: 13px;
}
QFrame#emptyState {
    background: transparent;
    border: 0;
}
QLabel#emptyStateGlyph {
    color: #A6A29C;
    font-size: 28px;
}
QLabel#emptyStateTitle {
    color: #F2EFEA;
    font-size: 14px;
    font-weight: 600;
}
QLabel#emptyStateHint {
    color: #A6A29C;
    font-size: 13px;
}
QPushButton#secondaryButton {
    background: #171716;
    color: #F2EFEA;
}
QToolTip {
    background: #1C1C1A;
    color: #F2EFEA;
    border: 1px solid rgba(232, 194, 158, 140);
    border-radius: 7px;
    padding: 6px 8px;
}
QWidget#topBar {
    background: transparent;
}
QPushButton#navPill {
    background: transparent;
    color: #A6A29C;
    border: 0;
    border-radius: 12px;
    padding: 8px 16px;
    min-height: 0;
    font-weight: 600;
}
QPushButton#navPill:hover {
    background: rgba(255, 255, 255, 12);
    color: #F2EFEA;
}
QPushButton#navPill:checked {
    background: #E8C29E;
    color: #1A140F;
}
QPushButton#ghostButton {
    background: transparent;
    border: 0;
    border-radius: 12px;
    color: #A6A29C;
    padding: 8px 14px;
    min-height: 0;
    font-weight: 600;
}
QPushButton#ghostButton:hover {
    background: rgba(255, 255, 255, 12);
    color: #F2EFEA;
}
QLabel#topBarMeta {
    color: #A6A29C;
    font-size: 12px;
    padding: 0 4px 0 8px;
}

QLabel#weatherTemperature {
    color: #F2EFEA;
    font-size: 34px;
    font-weight: 700;
}
QLabel#weatherIcon {
    font-size: 26px;
    padding-top: 4px;
}
QLabel#weatherCondition {
    color: #F2EFEA;
    font-size: 15px;
    font-weight: 600;
}
QLabel#weatherForecast {
    color: #A6A29C;
    font-size: 13px;
}
QLineEdit#weatherCityEdit {
    background: #171716;
    color: #F2EFEA;
    border: 0;
    border-radius: 10px;
    padding: 7px 10px;
    min-height: 0;
}

QScrollArea#chatTranscript {
    background: transparent;
    border: 0;
}
QWidget#chatTranscriptBody {
    background: transparent;
}
QLabel#chatHeaderAvatar {
    background: #E8C29E;
    color: #1A140F;
    border-radius: 14px;
    font-size: 15px;
    font-weight: 800;
}
QLabel#chatHeaderName {
    color: #F2EFEA;
    font-size: 15px;
    font-weight: 650;
}
QLabel#chatStatusDot {
    color: #7dd487;
    font-size: 12px;
}
QLabel#chatHeaderStatus {
    color: #A6A29C;
    font-size: 12px;
}
QLabel#chatAvatarUser {
    background: #171716;
    color: #F2EFEA;
    border-radius: 14px;
    font-size: 12px;
    font-weight: 650;
}
QLabel#chatAvatarAssistant {
    background: #E8C29E;
    color: #1A140F;
    border-radius: 14px;
    font-size: 13px;
    font-weight: 800;
}
QScrollArea#chatQuickCommands {
    background: transparent;
    border: 0;
}
QWidget#chatQuickCommandsBody {
    background: transparent;
}
QFrame#chatBubbleUser {
    background: #E8C29E;
    border: 0;
    border-radius: 14px;
    border-bottom-right-radius: 4px;
}
QFrame#chatBubbleAssistant {
    background: #171716;
    border: 0;
    border-radius: 14px;
    border-bottom-left-radius: 4px;
}
QFrame#chatBubbleSystem {
    background: #101010;
    border: 0;
    border-radius: 12px;
}
QFrame#chatBubbleMeta {
    background: transparent;
    border: 0;
}
QFrame#chatBubbleError {
    background: rgba(255, 123, 114, 26);
    border: 0;
    border-radius: 12px;
}
QLabel#chatTextUser {
    color: #1A140F;
    font-size: 18px;
    line-height: 1.45;
}
QLabel#chatTextAssistant {
    color: #F2EFEA;
    font-size: 18px;
    line-height: 1.45;
}
QLabel#chatTextSystem {
    color: #A6A29C;
    font-size: 15px;
    line-height: 1.45;
}
QLabel#chatTextMeta {
    color: #A6A29C;
    font-size: 15px;
}
QLabel#chatTextError {
    color: #FFB4AE;
    font-size: 15px;
}
QLabel#pathLabel {
    color: #A6A29C;
    font-size: 12px;
    padding: 0 2px;
}
QFrame#errorNotice {
    background: rgba(232, 194, 158, 26);
    border: 1px solid rgba(232, 194, 158, 80);
    border-radius: 10px;
}
QLabel#errorNoticeText {
    color: #E8C29E;
    font-size: 13px;
}
QLabel#chatDayDivider {
    color: #A6A29C;
    font-size: 12px;
    padding: 6px 0 2px 0;
}
QWidget#chatDayDividerSpacer {
    background: transparent;
}
QPushButton#newMessagesButton {
    background: rgba(232, 194, 158, 230);
    color: #1A140F;
    border: 0;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
    padding: 6px 12px;
    min-height: 0;
}
QPushButton#newMessagesButton:hover {
    background: #F2D2B0;
}
QLabel#chatTimestamp {
    color: #6E6A64;
    font-size: 12px;
    padding: 0 4px;
}
QLabel#chatTyping {
    color: #A6A29C;
    font-size: 14px;
}
QPushButton#chatCopyButton {
    background: rgba(255, 255, 255, 12);
    border: 0;
    border-radius: 8px;
    color: #A6A29C;
    font-size: 12px;
    padding: 0;
    min-height: 0;
}
QPushButton#chatCopyButton:hover {
    background: rgba(255, 255, 255, 26);
    color: #F2EFEA;
}
QPushButton#chatClearButton {
    background: transparent;
    border: 0;
    border-radius: 10px;
    color: #A6A29C;
    font-size: 15px;
    padding: 0;
    min-height: 0;
}
QPushButton#chatClearButton:hover {
    background: rgba(255, 255, 255, 12);
    color: #F2EFEA;
}
QTextEdit#chatComposer {
    background: #171716;
    color: #F2EFEA;
    border: 0;
    border-radius: 12px;
    padding: 8px 12px;
    font-size: 16px;
    line-height: 1.45;
}
QFrame#chatToast {
    background: #1F1F1D;
    border: 0;
    border-radius: 12px;
}
QLabel#chatToastText {
    color: #F2EFEA;
    font-size: 13px;
}
QPushButton#chatToastAction {
    background: transparent;
    border: 0;
    color: #E8C29E;
    font-size: 13px;
    font-weight: 600;
    padding: 2px 6px;
    min-height: 0;
}
QPushButton#chatToastAction:hover {
    color: #F2D2B0;
}
QToolButton#collapsibleHeader {
    background: #171716;
    border: 0;
    border-radius: 12px;
    color: #F2EFEA;
    font-size: 14px;
    font-weight: 600;
    padding: 8px 14px;
    min-height: 32px;
}
QToolButton#collapsibleHeader:hover {
    background: #1F1F1D;
}
QPushButton#cardIconButton {
    background: transparent;
    border: 0;
    border-radius: 12px;
    color: #A6A29C;
    font-size: 14px;
    padding: 0;
    min-height: 0;
}
QPushButton#cardIconButton:hover {
    background: rgba(255, 255, 255, 20);
    color: #F2EFEA;
}

"""


def build_dark_stylesheet() -> str:
    """Return the dark accent-glass theme with visible keyboard focus states."""
    return DARK_STYLESHEET + GLASS_QSS
