"""
Builds a Qt stylesheet from a palette dict.
We keep all the styling in one place so themes Just Work.
"""


def build_stylesheet(p: dict, theme_name: str = "") -> str:
    base = _base_stylesheet(p)
    if theme_name == "JARVIS HUD":
        base += _hud_overrides(p)
    return base


def _hud_overrides(p: dict) -> str:
    """Extra QSS applied only for JARVIS HUD — glassmorphism, neon glow, etc."""
    return f"""
/* ---------- JARVIS HUD overrides ---------- */

/* Make the stage area transparent so the neural background bleeds through */
QStackedWidget {{
    background-color: transparent;
}}
QScrollArea {{
    background-color: transparent;
}}
QScrollArea > QWidget {{
    background-color: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}

/* Cards get glassmorphism feel: semi-transparent surface + cyan neon edge */
QFrame#Card,
QFrame#GroupCard,
QFrame#PinTile {{
    background-color: rgba(10, 22, 38, 0.78);
    border: 1px solid rgba(57, 199, 255, 0.28);
    border-radius: 10px;
}}
QFrame#GroupCard:hover,
QFrame#PinTile:hover {{
    border: 1px solid rgba(57, 199, 255, 0.55);
}}

/* Headline rows: faint surface tint + cyan left edge */
QFrame#HeadlineRow {{
    background-color: rgba(15, 31, 54, 0.50);
    border-left: 2px solid rgba(57, 199, 255, 0.40);
    border-radius: 4px;
}}
QFrame#HeadlineRow:hover {{
    background-color: rgba(31, 78, 132, 0.45);
    border-left: 2px solid {p['accent']};
}}

/* Item rows in lists — subtle translucent */
QFrame#ItemRow {{
    background-color: rgba(10, 22, 38, 0.55);
}}

/* Top bar — translucent so the neural pattern continues underneath */
QFrame#TopBar {{
    background-color: rgba(4, 10, 20, 0.85);
    border-bottom: 1px solid rgba(57, 199, 255, 0.25);
}}
"""


def _base_stylesheet(p: dict) -> str:
    return f"""
/* ---------- Global ---------- */
QWidget {{
    background-color: {p['bg']};
    color: {p['text']};
    font-family: "Segoe UI", "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}}

QToolTip {{
    background-color: {p['surface']};
    color: {p['text']};
    border: 1px solid {p['border']};
    padding: 4px 8px;
    border-radius: 4px;
}}

/* ---------- Sidebar ---------- */
QFrame#Sidebar,
QFrame#Sidebar > QWidget {{
    background-color: {p['sidebar_bg']};
    border: none;
}}
QFrame#Sidebar QLabel {{
    color: {p['sidebar_text']};
    background-color: transparent;
}}
QScrollArea#SidebarScroll {{
    background-color: {p['sidebar_bg']};
    border: none;
}}
QWidget#SidebarScrollHost,
QWidget#SidebarScrollHost > QWidget {{
    background-color: {p['sidebar_bg']};
}}
QScrollArea#SidebarScroll QScrollBar:vertical {{
    background-color: transparent;
    width: 6px;
    margin: 4px 0;
}}
QScrollArea#SidebarScroll QScrollBar::handle:vertical {{
    background-color: rgba(127, 127, 127, 0.35);
    border-radius: 3px;
    min-height: 30px;
}}
QScrollArea#SidebarScroll QScrollBar::handle:vertical:hover {{
    background-color: rgba(127, 127, 127, 0.55);
}}
QScrollArea#SidebarScroll QScrollBar::add-line:vertical,
QScrollArea#SidebarScroll QScrollBar::sub-line:vertical {{
    height: 0;
}}

QPushButton#SidebarButton {{
    background-color: transparent;
    color: {p['sidebar_text']};
    border: none;
    text-align: left;
    padding: 8px 12px;
    margin: 0;
    border-radius: 6px;
    font-size: 13px;
    min-height: 22px;
}}

QPushButton#SidebarButton:hover {{
    background-color: rgba(127, 127, 127, 0.18);
}}

QPushButton#SidebarButton:checked {{
    background-color: {p['sidebar_accent']};
    color: white;
    font-weight: 600;
}}

QLabel#SidebarHeader {{
    color: {p['sidebar_text']};
    font-size: 17px;
    font-weight: 700;
    padding: 18px 16px 10px 16px;
}}

QPushButton#SidebarSection,
QLabel#SidebarSection {{
    color: {p['sidebar_text']};
    background-color: transparent;
    border: none;
    text-align: left;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
    padding: 12px 12px 6px 12px;
    margin: 0;
    min-height: 22px;
}}
QPushButton#SidebarSection:hover {{
    color: {p['sidebar_accent']};
    background-color: rgba(127, 127, 127, 0.10);
}}

/* ---------- Top bar ---------- */
QFrame#TopBar {{
    background-color: {p['surface']};
    border-bottom: 1px solid {p['border']};
}}

QLineEdit#SearchBar {{
    background-color: {p['surface_alt']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13.5px;
    selection-background-color: {p['accent']};
    selection-color: {p['accent_text']};
}}

QLineEdit#SearchBar:focus {{
    border: 1px solid {p['accent']};
    background-color: {p['surface']};
}}

/* ---------- Cards / panels ---------- */
QFrame.Card {{
    background-color: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 10px;
}}

QLabel.CardTitle {{
    font-size: 15px;
    font-weight: 600;
    color: {p['text']};
}}

QLabel.CardSubtitle {{
    color: {p['text_muted']};
    font-size: 12px;
}}

QLabel.SectionHeader {{
    font-size: 22px;
    font-weight: 700;
    color: {p['text']};
}}

QLabel.SectionSub {{
    color: {p['text_muted']};
    font-size: 13px;
}}

QLabel.Muted {{ color: {p['text_muted']}; }}

/* ---------- Buttons ---------- */
QPushButton {{
    background-color: {p['surface_alt']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 500;
}}

QPushButton:hover  {{ background-color: {p['border']}; }}
QPushButton:disabled {{ color: {p['text_muted']}; background-color: {p['surface']}; }}

QPushButton[primary="true"] {{
    background-color: {p['accent']};
    color: {p['accent_text']};
    border: 1px solid {p['accent']};
}}
QPushButton[primary="true"]:hover {{ background-color: {p['accent_hover']}; }}

QPushButton[danger="true"] {{
    background-color: transparent;
    color: {p['danger']};
    border: 1px solid {p['border']};
}}
QPushButton[danger="true"]:hover {{
    background-color: {p['danger']};
    color: white;
    border-color: {p['danger']};
}}

QPushButton[ghost="true"] {{
    background-color: transparent;
    border: none;
    color: {p['text_muted']};
    padding: 4px 8px;
}}
QPushButton[ghost="true"]:hover {{ color: {p['accent']}; }}

/* ---------- Inputs ---------- */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDateTimeEdit, QTimeEdit, QDateEdit {{
    background-color: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 6px;
    padding: 7px 10px;
    selection-background-color: {p['accent']};
    selection-color: {p['accent_text']};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDateTimeEdit:focus, QTimeEdit:focus, QDateEdit:focus {{
    border: 1px solid {p['accent']};
}}

/* ===== QSpinBox up/down arrows ===== */
QSpinBox {{
    padding-right: 22px;
}}
QSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    height: 14px;
    border-left: 1px solid {p['border']};
    border-bottom: 1px solid {p['border']};
    border-top-right-radius: 6px;
    background-color: {p['surface_alt']};
}}
QSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    height: 14px;
    border-left: 1px solid {p['border']};
    border-bottom-right-radius: 6px;
    background-color: {p['surface_alt']};
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background-color: {p['border']};
}}
QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
    background-color: {p['accent']};
}}
QSpinBox::up-arrow {{
    image: none;
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {p['text']};
}}
QSpinBox::down-arrow {{
    image: none;
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p['text']};
}}

/* ===== QDateTimeEdit/QTimeEdit/QDateEdit with calendarPopup=true =====
   Qt replaces the up/down buttons with a single drop-down arrow. We give it
   proper visual treatment so clicking it actually opens the calendar. */
QDateTimeEdit, QTimeEdit, QDateEdit {{
    padding-right: 28px;
}}
QDateTimeEdit::drop-down,
QDateEdit::drop-down,
QTimeEdit::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border-left: 1px solid {p['border']};
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background-color: {p['surface_alt']};
}}
QDateTimeEdit::drop-down:hover,
QDateEdit::drop-down:hover,
QTimeEdit::drop-down:hover {{
    background-color: {p['border']};
}}
QDateTimeEdit::drop-down:pressed,
QDateEdit::drop-down:pressed,
QTimeEdit::drop-down:pressed {{
    background-color: {p['accent']};
}}
QDateTimeEdit::down-arrow,
QDateEdit::down-arrow,
QTimeEdit::down-arrow {{
    image: none;
    width: 0; height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {p['text']};
}}

/* When QDateTimeEdit doesn't have calendarPopup, Qt uses up/down buttons */
QDateTimeEdit::up-button, QDateEdit::up-button, QTimeEdit::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    height: 14px;
    border-left: 1px solid {p['border']};
    border-bottom: 1px solid {p['border']};
    border-top-right-radius: 6px;
    background-color: {p['surface_alt']};
}}
QDateTimeEdit::down-button, QDateEdit::down-button, QTimeEdit::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    height: 14px;
    border-left: 1px solid {p['border']};
    border-bottom-right-radius: 6px;
    background-color: {p['surface_alt']};
}}
QDateTimeEdit::up-arrow, QDateEdit::up-arrow, QTimeEdit::up-arrow {{
    image: none;
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {p['text']};
}}
QDateTimeEdit::down-arrow, QDateEdit::down-arrow, QTimeEdit::down-arrow {{
    image: none;
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p['text']};
}}

/* QComboBox drop-down arrow — without this, native arrow may look mismatched */
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid {p['border']};
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background-color: {p['surface_alt']};
}}
QComboBox::drop-down:hover {{
    background-color: {p['border']};
}}
QComboBox::down-arrow {{
    image: none;
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p['text']};
}}

/* Calendar popup widget styling so the calendar that appears looks themed */
QCalendarWidget {{
    background-color: {p['surface']};
    color: {p['text']};
}}
QCalendarWidget QToolButton {{
    background-color: transparent;
    color: {p['text']};
    border: none;
    padding: 4px 8px;
    font-weight: 600;
}}
QCalendarWidget QToolButton:hover {{
    background-color: {p['surface']};
    color: {p['accent']};
}}
/* Prev/Next month arrow buttons — Qt names them qt_calendar_prevmonth,
   qt_calendar_nextmonth. Force the icon area to contrast with the navbar. */
QCalendarWidget QToolButton#qt_calendar_prevmonth,
QCalendarWidget QToolButton#qt_calendar_nextmonth {{
    qproperty-icon: none;        /* drop the default Qt arrow icon */
    background-color: transparent;
    color: {p['text']};
    font-size: 16px;
    font-weight: 700;
    min-width: 28px;
    min-height: 24px;
    padding: 2px 6px;
    border-radius: 4px;
}}
QCalendarWidget QToolButton#qt_calendar_prevmonth:hover,
QCalendarWidget QToolButton#qt_calendar_nextmonth:hover {{
    background-color: {p['border']};
    color: {p['accent']};
}}
QCalendarWidget QMenu {{
    background-color: {p['surface']};
    color: {p['text']};
}}
QCalendarWidget QSpinBox {{
    background-color: {p['surface_alt']};
    color: {p['text']};
}}
QCalendarWidget QAbstractItemView:enabled {{
    background-color: {p['surface']};
    color: {p['text']};
    selection-background-color: {p['accent']};
    selection-color: {p['accent_text']};
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: {p['surface_alt']};
}}

QComboBox QAbstractItemView {{
    background-color: {p['surface']};
    color: {p['text']};
    border: 1px solid {p['border']};
    selection-background-color: {p['accent']};
    selection-color: {p['accent_text']};
    outline: none;
    padding: 4px 0;
}}
QComboBox QAbstractItemView::item {{
    background-color: {p['surface']};
    color: {p['text']};
    min-height: 28px;
    padding: 4px 12px;
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: {p['surface_alt']};
    color: {p['text']};
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: {p['accent']};
    color: {p['accent_text']};
}}

/* ---------- Lists / tables ---------- */
QListWidget, QTreeWidget, QTableWidget {{
    background-color: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    outline: none;
}}

QListWidget::item, QTreeWidget::item, QTableWidget::item {{
    padding: 8px;
    border-bottom: 1px solid {p['border']};
}}

QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{
    background-color: {p['accent']};
    color: {p['accent_text']};
}}

QHeaderView::section {{
    background-color: {p['surface_alt']};
    color: {p['text']};
    border: none;
    border-bottom: 1px solid {p['border']};
    padding: 8px;
    font-weight: 600;
}}

/* ---------- Scrollbars ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {p['border']};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {p['text_muted']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {p['border']};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {p['text_muted']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ---------- Tabs ---------- */
QTabWidget::pane {{
    border: 1px solid {p['border']};
    border-radius: 8px;
    background-color: {p['surface']};
    top: -1px;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {p['text_muted']};
    padding: 8px 16px;
    border: none;
    margin-right: 4px;
}}
QTabBar::tab:selected {{
    color: {p['accent']};
    border-bottom: 2px solid {p['accent']};
    font-weight: 600;
}}
QTabBar::tab:hover {{ color: {p['text']}; }}

/* ---------- Checkbox ---------- */
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {p['border']};
    border-radius: 3px;
    background: {p['surface']};
}}
QCheckBox::indicator:checked {{
    background: {p['accent']};
    border: 1px solid {p['accent']};
    image: none;
}}

/* ---------- Menu ---------- */
QMenu {{
    background-color: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 24px 6px 16px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p['accent']}; color: {p['accent_text']}; }}

/* ---------- Dialog ---------- */
QDialog {{ background-color: {p['bg']}; }}

/* ---------- Search results popup ---------- */
QFrame#SearchResults {{
    background-color: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 8px;
}}
QListWidget#SearchResultsList {{
    border: none;
    background: transparent;
}}
QListWidget#SearchResultsList::item {{
    padding: 10px 12px;
    border: none;
}}
QListWidget#SearchResultsList::item:selected {{
    background: {p['surface_alt']};
    color: {p['text']};
}}

/* ---------- Notification chip ---------- */
QFrame.Chip {{
    background-color: {p['accent']};
    color: {p['accent_text']};
    border-radius: 9px;
    min-width: 18px;
    max-height: 18px;
}}

/* ---------- Tag / pill ---------- */
QLabel.Tag {{
    background-color: {p['surface_alt']};
    color: {p['text_muted']};
    border: 1px solid {p['border']};
    border-radius: 9px;
    padding: 1px 8px;
    font-size: 11px;
}}

/* ---------- Pinned tile (theme-aware, replaces inline HTML) ---------- */
QFrame#PinTile {{
    background-color: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 8px;
}}
QFrame#PinTile:hover {{
    background-color: {p['surface_alt']};
    border-color: {p['accent']};
}}
QLabel#PinTileIcon  {{ font-size: 22px; background: transparent; }}
QLabel#PinTileName  {{ font-weight: 600; font-size: 13px; background: transparent; color: {p['text']}; }}
QLabel#PinTileKind  {{ font-size: 10px; color: {p['text_muted']}; background: transparent; }}

/* ---------- Group card (used in Links / Documents / Templates) ---------- */
QFrame#GroupCard {{
    background-color: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 10px;
}}
QLabel#GroupTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {p['text']};
}}
QLabel#GroupCount {{
    color: {p['text_muted']};
    font-size: 12px;
}}

/* ---------- Item row inside a group card ---------- */
QFrame#ItemRow {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
}}
QFrame#ItemRow:hover {{
    background-color: {p['surface_alt']};
}}
QLabel#ItemIcon {{ font-size: 16px; background: transparent; }}
QLabel#ItemName {{ font-weight: 500; background: transparent; color: {p['text']}; }}

/* ---------- Sidebar hint (theme-aware) ---------- */
QLabel#SidebarHint {{
    color: {p['sidebar_text_muted']};
    font-size: 11px;
    padding: 8px 16px;
}}

/* ---------- Axis button row (≤3 options as buttons) ---------- */
QPushButton[axisbtn="true"] {{
    background-color: {p['surface_alt']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 6px;
    padding: 6px 12px;
}}
QPushButton[axisbtn="true"]:hover {{
    background-color: {p['surface']};
    border-color: {p['accent']};
}}
QPushButton[axisbtn="true"][selected="true"] {{
    background-color: {p['accent']};
    color: {p['accent_text']};
    border-color: {p['accent']};
}}
"""
