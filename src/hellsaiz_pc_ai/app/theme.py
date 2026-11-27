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

# knice tokens for the main dashboard: denser surface, 22px cards, layered
# shadow (applied as a QGraphicsDropShadowEffect) and an inset top highlight.
DASHBOARD_SURFACE = "#212226"
DASHBOARD_HOVER = "#2a2b30"
DASHBOARD_BACKDROP = "#17181b"
CARD_RADIUS = "22px"
CARD_EDGE = "rgba(255, 255, 255, 18)"
CARD_SHADOW_BLUR = 20
CARD_SHADOW_OFFSET_Y = 6
CARD_SHADOW_ALPHA = 120

# Wave-8 dashboard geometry: one gap for the grid, one padding for cards and
# margins that leave room for the card shadow (it must not be clipped).
GRID_GAP = 20
CARD_PADDING = 18
DASHBOARD_MARGIN_TOP = 36
DASHBOARD_MARGIN_SIDE = 28
DASHBOARD_MARGIN_BOTTOM = 24
GRID_BREAKPOINTS = ((900, 1), (1150, 2), (10**9, 3))
TEXT_MUTED = "#A6A29C"
TEXT_PRIMARY = "#F2EFEA"

# Wave 9E tokens: surfaces, states, radii and the chat bubble contract.
SURFACE_RAISED = "#2A2B30"
SURFACE_INPUT = "#1C1C1A"
STATE_HOVER = "#1F1F1D"
STATE_PRESSED = "#121211"
STATE_DISABLED = "#131312"
STATUS_OK = "#7dd487"
STATUS_WARN = "#f5c04a"
STATUS_ERROR = "#ff7b72"
TAB_BG = "#141413"
TAB_ACTIVE = "#E8C29E"
RADIUS_CARD = "22px"
RADIUS_INPUT = "16px"
RADIUS_CHIP = "16px"
SURFACE_RAISED = "#2A2B30"
SURFACE_BUTTON = "#171716"
STATE_HOVER = "#1F1F1D"
STATE_PRESSED = "#121211"
STATE_DISABLED = "#131312"
STATUS_OK = "#7dd487"
STATUS_WARN = "#f5c04a"
STATUS_ERROR = "#ff7b72"
TAB_BG = "#141413"
TAB_ACTIVE = "#E8C29E"
RADIUS_CARD = "22px"
RADIUS_INPUT = "16px"
RADIUS_CHIP = "16px"
SPACING = (4, 8, 12, 16, 24)
FONT_CAPTION = "12px"
FONT_BODY = "13px"
FONT_EMPHASIS = "15px"
FONT_PAGE_TITLE = "19px"
FONT_SCREEN_TITLE = "22px"

CHAT_BUBBLE_RADIUS = "16px"
ACCENT_SOLID = "#E8C29E"
CHAT_BUBBLE_USER_BG = ACCENT_SOLID
CHAT_BUBBLE_ASSISTANT_BG = DASHBOARD_SURFACE
CHAT_BUBBLE_SYSTEM_BG = DASHBOARD_BACKDROP
SPACING = (4, 8, 12, 16, 24)
FONT_CAPTION = "12px"
FONT_BODY = "13px"
FONT_EMPHASIS = "15px"
FONT_PAGE_TITLE = "19px"
FONT_SCREEN_TITLE = "22px"

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
    border-radius: 16px;
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

/* --- knice main-page tokens ----------------------------------------- */
QWidget#appShell, QWidget#contentFrame {{
    /* Transparent: the wallpaper layer sits behind the shell and must show. */
    background: transparent;
}}
QFrame#dashboardCard {{
    background: transparent;
    border: 0;
    border-radius: {CARD_RADIUS};
}}
QLabel#weatherTemperature {{
    font-family: "Consolas", "Courier New", monospace;
    font-size: 34px;
    font-weight: 800;
    padding: 2px 0;
}}
QLabel#dashboardCardValue {{
    font-family: "Consolas", "Courier New", monospace;
    font-weight: 700;
}}
QListWidget#dashboardRemindersList {{
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    background: transparent;
    border: 0;
}}
QLabel#dashboardCardNote {{
    color: #A6A29C;
    font-size: 13px;
}}
QPushButton#cityButton {{
    background: transparent;
    border: 0;
    color: #F2EFEA;
    font-size: 16px;
    font-weight: 700;
    padding: 0;
    min-height: 0;
    text-align: left;
}}
QPushButton#cityButton:hover {{
    color: #F2D2B0;
}}
QLabel#weatherCityDot {{
    color: {TEXT_MUTED};
    font-size: 14px;
    padding: 6px 0 0 2px;
}}
QLabel#mediaCover {{
    background: {GLASS_BG_STRONG};
    border: 1px solid {GLASS_BORDER};
    border-radius: 16px;
}}
QLabel#mediaTrack {{
    color: {TEXT_PRIMARY};
    font-size: 15px;
    font-weight: 600;
}}
QLabel#mediaArtist {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QLabel#mediaState {{
    color: {TEXT_MUTED};
    font-size: 13px;
}}
QWidget#weatherForecastRow {{
    background: transparent;
}}
QLabel#weatherForecastChip {{
    background: {GLASS_BG_STRONG};
    border: 1px solid {GLASS_BORDER};
    border-radius: 10px;
    color: {TEXT_PRIMARY};
    font-size: 12px;
    padding: 4px 10px;
}}
QLabel#weatherForecastDay {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QLabel#weatherForecastTemp {{
    color: {TEXT_PRIMARY};
    font-size: 14px;
    font-weight: 600;
}}
QLineEdit#weatherCityEdit {{
    background: {GLASS_BG_STRONG};
    color: #F2EFEA;
    border: 1px solid rgba(232, 194, 158, 140);
    border-radius: 10px;
    padding: 4px 10px;
    min-height: 0;
}}
QPushButton#mediaButton {{
    background: rgba(255, 255, 255, 12);
    border: 0;
    border-radius: 18px;
    padding: 0;
    min-height: 0;
}}
QPushButton#mediaButton:hover {{
    background: rgba(255, 255, 255, 26);
}}
QToolButton#quickChip {{
    background: rgba(255, 255, 255, 12);
    border: 1px solid rgba(255, 255, 255, 26);
    border-radius: 18px;
    color: #A6A29C;
    font-size: 12px;
    padding: 4px 12px;
    min-height: 0;
}}
QToolButton#quickChip:hover {{
    background: rgba(255, 255, 255, 26);
    color: #F2EFEA;
}}
QLineEdit#quickCommandInput {{
    background: {GLASS_BG_STRONG};
    color: #F2EFEA;
    border: 1px solid rgba(255, 255, 255, 26);
    border-radius: 16px;
    padding: 6px 14px;
    min-height: 34px;
    font-size: 14px;
}}
QLineEdit#quickCommandInput:focus {{
    border: 1px solid rgba(232, 194, 158, 140);
    background: rgba(255, 255, 255, 30);
}}
QProgressBar#systemBar {{
    background: rgba(255, 255, 255, 26);
    border: 0;
    border-radius: 3px;
    max-height: 6px;
    min-height: 6px;
    text-align: center;
    color: transparent;
    font-size: 1px;
}}
QProgressBar#systemBar::chunk {{
    background: #E8C29E;
    border-radius: 3px;
}}
QLabel#remindersCount {{
    color: #A6A29C;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}}
QLabel#systemBarValue {{
    color: #A6A29C;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}}
QLabel#lastReplyText {{
    color: #F2EFEA;
    font-size: 15px;
}}
QLabel#lastReplyText:hover {{
    color: #F2D2B0;
}}
QLabel#lastReplyTime {{
    color: #A6A29C;
    font-size: 12px;
}}
"""

DARK_STYLESHEET = """
QMainWindow {
    background: #0B0B0B;
}
/* Containers must not paint their own near-black fill: the window owns the
   backdrop, rounded cards and panels own their surfaces. */
QWidget {
    background: transparent;
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
    font-size: 20px;
    font-weight: 700;
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
    padding: 7px 14px;
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
    background: SURFACE_INPUT;
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
/* ---------- Scenarios studio: cards instead of default form boxes ---------- */
QPushButton#aiToggle {
    background: STATE_HOVER;
    border: 1px solid GLASS_BORDER;
    border-radius: 17px;
    color: TEXT_MUTED;
    font-size: 12px;
    font-weight: 600;
    padding: 0 10px;
}
QPushButton#aiToggle:checked {
    background: ACCENT_SOLID;
    border: 1px solid ACCENT_SOLID;
    color: #1B1B19;
}
QPushButton#aiToggle:hover {
    border: 1px solid ACCENT_SOLID;
}
QLabel#pageTitle {
    color: TEXT_PRIMARY;
    font-size: 22px;
    font-weight: 700;
}
QLabel#sectionTitle {
    color: TEXT_PRIMARY;
    font-size: 19px;
    font-weight: 650;
}
QLabel#cardTitle {
    color: TEXT_PRIMARY;
    font-size: 15px;
    font-weight: 600;
}
QLabel#sectionEyebrow {
    color: TEXT_MUTED;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}
QLabel#scenarioStatus {
    color: TEXT_MUTED;
    font-size: 12px;
}
QLabel#secondaryText {
    color: TEXT_MUTED;
    font-size: 13px;
}
QLabel#warningText {
    color: STATUS_WARN;
    font-size: 12px;
}
QGroupBox#scenarioCard, QGroupBox#scenarioBranchCard {
    background: DASHBOARD_SURFACE;
    border: 1px solid CARD_EDGE;
    border-radius: 16px;
    margin-top: 22px;
    padding: 16px 14px 14px 14px;
    font-size: 13px;
    color: TEXT_PRIMARY;
}
QGroupBox#scenarioCard::title, QGroupBox#scenarioBranchCard::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    color: TEXT_MUTED;
    font-size: 12px;
}
QWidget#studioPanel {
    background: DASHBOARD_BACKDROP;
    border: 1px solid CARD_EDGE;
    border-radius: 16px;
}
QWidget#scenarioActionCard {
    background: GLASS_BG_STRONG;
    border: 1px solid GLASS_BORDER;
    border-radius: 12px;
}
QPushButton#toolbarButton {
    background: GLASS_BG_STRONG;
    border: 1px solid GLASS_BORDER;
    border-radius: 10px;
    color: TEXT_PRIMARY;
    font-size: 12px;
    padding: 4px 10px;
    min-height: 0;
}
QPushButton#toolbarButton:hover {
    background: STATE_HOVER;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 4px 2px 4px 0;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 40);
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(255, 255, 255, 70);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
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
    background: CHAT_BUBBLE_USER_BG;
    border: 0;
    border-radius: CHAT_BUBBLE_RADIUS;
}
QFrame#chatBubbleAssistant {
    background: CHAT_BUBBLE_ASSISTANT_BG;
    border: 0;
    border-radius: CHAT_BUBBLE_RADIUS;
}
QFrame#chatBubbleSystem {
    background: CHAT_BUBBLE_SYSTEM_BG;
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
    font-size: 16px;
    line-height: 1.55;
}
QLabel#chatTextAssistant {
    color: #F2EFEA;
    font-size: 16px;
    line-height: 1.55;
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
QLabel#chatGreetingPrompt {
    color: #A6A29C;
    font-size: 15px;
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
    background: transparent;
    color: #F2EFEA;
    border: 0;
    border-radius: 16px;
    padding: 10px 16px;
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
    sheet = DARK_STYLESHEET + GLASS_QSS
    # DARK_STYLESHEET is a plain (non f-) string: resolve the design tokens here.
    for name in (
        "CHAT_BUBBLE_USER_BG",
        "CHAT_BUBBLE_ASSISTANT_BG",
        "CHAT_BUBBLE_SYSTEM_BG",
        "CHAT_BUBBLE_RADIUS",
        "SURFACE_INPUT",
        "SURFACE_BUTTON",
        "STATE_HOVER",
        "STATE_PRESSED",
        "STATE_DISABLED",
        "ACCENT_SOLID",
        "TAB_BG",
        "TAB_ACTIVE",
        "DASHBOARD_SURFACE",
        "DASHBOARD_BACKDROP",
        "CARD_EDGE",
        "GLASS_BG_STRONG",
        "GLASS_BORDER",
        "TEXT_PRIMARY",
        "TEXT_MUTED",
        "STATUS_OK",
        "STATUS_WARN",
        "STATUS_ERROR",
    ):
        sheet = sheet.replace(name, str(globals()[name]))
    return sheet
