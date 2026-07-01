"""
Main window. The shell that hosts every module page. Owns:
  - The AppContext object passed into every module
  - Sidebar navigation (grouped by SECTION)
  - Global search bar (top of window) with results popup
  - System tray icon for background notifications
  - Stacked pages — one widget per enabled module
"""
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QLineEdit, QListWidget, QListWidgetItem,
    QSystemTrayIcon, QMenu, QApplication, QToolButton, QSizePolicy, QSpacerItem,
)
from PyQt6.QtCore import Qt, QSize, QPoint, QRect, pyqtSignal, QEvent, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QBrush, QColor, QFont, QAction, QKeySequence, QShortcut

from core.search import SearchRegistry, SearchResult
from modules import MODULE_CLASSES


# ----------------------------------------------------------------------------
# AppContext — passed into every module so they can interact with the host
# ----------------------------------------------------------------------------
class AppContext:
    def __init__(self, storage, theme, search, main_window):
        self.storage = storage
        self.theme = theme
        self.search = search
        self._main = main_window

    def notify(self, title: str, body: str = "", sound: str = "notify",
               source: str = "App", user_initiated: bool = False):
        """Show a notification and log it.

        Args:
            title, body: the notification content
            sound: which UI sound to play (or "" for silence)
            source: short module-friendly source label (e.g. "Health is Wealth",
                    "Tasks"). Appears in the in-app notifications log.
            user_initiated: if True, the entry is marked as already read in the
                    in-app log — useful for things the user actively triggered
                    like "Password copied" which shouldn't add to the unread badge.
        """
        prefs = self.storage.load("preferences", {}) or {}
        mode = prefs.get("notifications_mode", "full")  # full | titles_only | off

        # Always log (even when surfacing is off, so the log captures everything)
        self.notifications_log({
            "title": title,
            "body": body,
            "source": source,
            "read": user_initiated,  # auto-mark user-triggered notifs as read
        })

        if mode == "off":
            return

        # Map sound to toast color kind
        kind_map = {"error": "error", "success": "success", "warning": "warning"}
        kind = kind_map.get(sound, "info")

        if mode == "titles_only":
            self._main.show_notification(title, "", kind=kind)
        else:
            self._main.show_notification(title, body, kind=kind)
        if sound:
            self.play_sound(sound)

    def on_music_state_changed(self):
        """Called by Focus Music when playback starts/stops/pauses.
        Notifies dashboard (or any other module) to refresh its widget."""
        dash = self.get_module("dashboard")
        if dash and hasattr(dash, "refresh_music_widget"):
            try:
                dash.refresh_music_widget()
            except Exception:
                pass

    def play_sound(self, name: str):
        """Play a UI sound (click/notify/timer/reminder/error/success)."""
        try:
            from core.sounds import sound_player
            sound_player.play(name)
        except Exception:
            pass

    def status(self, text: str, icon: str = "▶", auto_hide: bool = True):
        """Show a live status message in the bottom strip — for in-progress
        operations like multi-step launchers. Multiple calls update the
        same strip in place rather than stacking like toasts do."""
        strip = getattr(self._main, "status_strip", None)
        if strip is not None:
            try:
                strip.show_message(text, icon=icon, auto_hide=auto_hide)
            except Exception:
                pass

    def status_clear(self):
        strip = getattr(self._main, "status_strip", None)
        if strip is not None:
            try:
                strip.hide_strip()
            except Exception:
                pass

    def notifications_log(self, entry: dict):
        """Append a notification record to the persistent log."""
        log = self.storage.load("notifications_log", [])
        entry.setdefault("read", False)
        entry.setdefault("at", datetime.now().isoformat(timespec="seconds"))
        entry.setdefault("source", "App")
        log.append(entry)
        # Cap size
        if len(log) > 500:
            log = log[-500:]
        self.storage.save("notifications_log", log)
        # Refresh bell badge on every log write
        try:
            self._main._update_bell_badge()
        except Exception:
            pass

    def navigate(self, module_id: str):
        self._main.navigate_to(module_id)

    def all_module_classes(self):
        return list(MODULE_CLASSES)

    def get_module(self, module_id: str):
        """Return a live module instance by id, or None if not loaded."""
        return self._main._modules.get(module_id)

    def copy_password_with_restore(self, vault_entry_name: str, restore_after: int = 60,
                                   on_done=None, on_error=None):
        """
        Copy the named vault entry's password to clipboard, restoring the previous
        clipboard contents after `restore_after` seconds. Prompts to unlock the
        vault if it's locked. Used by the Launchers module.
        """
        passwords = self.get_module("passwords")
        if not passwords:
            if on_error: on_error("Password module not loaded.")
            self.notify("Passwords disabled", "Enable the Passwords module in Settings to use this.")
            return
        passwords.copy_named_password(vault_entry_name, restore_after,
                                      on_done=on_done, on_error=on_error)


# ----------------------------------------------------------------------------
# Resolve the bundled logo path, supports PyInstaller bundling.
# ----------------------------------------------------------------------------
def _logo_path() -> Path | None:
    """Return the bundled JARVIS logo path if present, else None."""
    import sys
    candidates = []
    # PyInstaller frozen exe
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "defaults" / "assets" / "jarvis_logo.png")
    # Dev / source run — relative to this file
    here = Path(__file__).resolve().parent
    candidates.append(here.parent / "defaults" / "assets" / "jarvis_logo.png")
    candidates.append(Path.cwd() / "defaults" / "assets" / "jarvis_logo.png")
    for c in candidates:
        if c.is_file():
            return c
    return None


# ----------------------------------------------------------------------------
# App icon. Prefers the bundled JARVIS logo PNG, falls back to procedural
# arc-reactor drawing if the asset is missing.
# ----------------------------------------------------------------------------
def make_icon(glyph: str = "", color: str = "#39C7FF", size: int = 64) -> QIcon:
    # Prefer the bundled logo
    p = _logo_path()
    if p is not None:
        pix = QPixmap(str(p))
        if not pix.isNull():
            scaled = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            return QIcon(scaled)

    # Fallback: procedural arc-reactor
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QRadialGradient, QPen
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    cx = cy = size / 2
    accent = QColor(color)
    dark = QColor("#0A1626")

    painter.setBrush(QBrush(dark))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(cx, cy), size * 0.48, size * 0.48)

    pen = QPen(accent); pen.setWidthF(size * 0.07)
    painter.setPen(pen); painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(cx, cy), size * 0.36, size * 0.36)

    grad = QRadialGradient(QPointF(cx, cy), size * 0.28)
    bright = QColor(accent); bright.setAlphaF(1.0)
    fade   = QColor(accent); fade.setAlphaF(0.0)
    grad.setColorAt(0.0, bright)
    grad.setColorAt(1.0, fade)
    painter.setBrush(QBrush(grad)); painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(cx, cy), size * 0.26, size * 0.26)

    painter.setBrush(QBrush(QColor("white")))
    painter.drawEllipse(QPointF(cx, cy), size * 0.06, size * 0.06)

    painter.end()
    return QIcon(pix)


# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------
class Sidebar(QFrame):
    module_selected = pyqtSignal(str)

    def __init__(self, storage=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(230)
        self._buttons: dict[str, QPushButton] = {}
        self._storage = storage
        self._section_collapsed: dict[str, bool] = {}
        self._section_items: dict[str, list] = {}
        self._section_headers: dict[str, QPushButton] = {}

        # Sidebar = brand row (fixed) + scroll area with the rest
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        self._brand_host = QWidget()
        self._brand_layout = QVBoxLayout(self._brand_host)
        self._brand_layout.setContentsMargins(0, 0, 0, 0); self._brand_layout.setSpacing(0)
        root.addWidget(self._brand_host)

        from PyQt6.QtWidgets import QScrollArea
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("SidebarScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_host = QWidget()
        self._scroll_host.setObjectName("SidebarScrollHost")
        self._layout = QVBoxLayout(self._scroll_host)
        self._layout.setContentsMargins(0, 4, 0, 12); self._layout.setSpacing(2)
        self._scroll.setWidget(self._scroll_host)
        root.addWidget(self._scroll, 1)

    def populate(self, modules_by_section: dict[str, list]):
        # Clear brand and scroll
        while self._brand_layout.count():
            it = self._brand_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._buttons.clear()
        self._section_collapsed.clear()
        self._section_items.clear()
        self._section_headers.clear()

        # Brand header (outside scroll, always visible)
        brand_row = QWidget()
        br = QHBoxLayout(brand_row); br.setContentsMargins(16, 12, 16, 10); br.setSpacing(10)
        brand_icon = QLabel()
        brand_icon.setStyleSheet("background:transparent;")
        brand_icon.setFixedSize(32, 32)
        # Load the bundled JARVIS logo PNG
        from ui.main_window import _logo_path
        _lp = _logo_path()
        if _lp:
            from PyQt6.QtGui import QPixmap
            pix = QPixmap(str(_lp))
            if not pix.isNull():
                scaled = pix.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                brand_icon.setPixmap(scaled)
            else:
                brand_icon.setText("🤖"); brand_icon.setStyleSheet("font-size:22px; background:transparent;")
        else:
            brand_icon.setText("🤖"); brand_icon.setStyleSheet("font-size:22px; background:transparent;")
        brand_text = QLabel("JARVIS"); brand_text.setObjectName("SidebarHeader")
        # No color in inline style — let QSS theme it (so light themes get dark text)
        brand_text.setStyleSheet("font-size:18px; font-weight:700; letter-spacing:1px; background:transparent;")
        br.addWidget(brand_icon); br.addWidget(brand_text); br.addStretch()
        self._brand_layout.addWidget(brand_row)

        # Load saved collapse state from prefs
        prefs = self._storage.load("preferences", {}) if self._storage else {}
        collapsed_initial = set(prefs.get("sidebar_collapsed", []))

        # Sections in fixed order
        for section in ("Workspace", "Tools", "System"):
            mods = modules_by_section.get(section, [])
            if not mods:
                continue

            is_collapsed = section in collapsed_initial
            self._section_collapsed[section] = is_collapsed

            # Collapsible header button
            header = QPushButton()
            header.setObjectName("SidebarSection")
            header.setCursor(Qt.CursorShape.PointingHandCursor)
            header.setMinimumHeight(28)  # avoid clipping
            arrow = "▸" if is_collapsed else "▾"
            header.setText(f"  {arrow}  {section.upper()}")
            self._layout.addWidget(header)
            self._section_headers[section] = header

            # Item buttons
            item_widgets: list[QWidget] = []
            for cls, instance in mods:
                # QPushButton treats `&` as a mnemonic prefix → escape with &&
                name_safe = cls.NAME.replace("&", "&&")
                btn = QPushButton(f"  {cls.ICON}    {name_safe}")
                btn.setObjectName("SidebarButton")
                btn.setCheckable(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setMinimumHeight(34)  # was clipping before — bump it
                # Tooltip = module name + description
                desc = getattr(cls, "DESCRIPTION", "") or ""
                btn.setToolTip(f"{cls.NAME}\n{desc}" if desc else cls.NAME)
                btn.clicked.connect(lambda _checked=False, mid=cls.MODULE_ID:
                                    self.module_selected.emit(mid))
                container = QWidget()
                pad = QHBoxLayout(container)
                pad.setContentsMargins(6, 0, 6, 0)
                pad.addWidget(btn)
                self._layout.addWidget(container)
                container.setVisible(not is_collapsed)
                item_widgets.append(container)
                self._buttons[cls.MODULE_ID] = btn

            self._section_items[section] = item_widgets

            # Wire header click — capture section in default arg
            header.clicked.connect(lambda _=False, sec=section: self._toggle_section(sec))

        self._layout.addStretch()

        # Footer hint — keep inside scroll so it doesn't clip the last section
        hint = QLabel("  Ctrl+K  to search")
        hint.setObjectName("SidebarHint")
        self._layout.addWidget(hint)

    def _toggle_section(self, section: str):
        """Toggle the visibility of a section's items."""
        currently_collapsed = self._section_collapsed.get(section, False)
        new_collapsed = not currently_collapsed
        self._section_collapsed[section] = new_collapsed

        # Show/hide items
        for w in self._section_items.get(section, []):
            w.setVisible(not new_collapsed)

        # Update arrow on header
        header = self._section_headers.get(section)
        if header:
            arrow = "▸" if new_collapsed else "▾"
            header.setText(f"  {arrow}  {section.upper()}")

        # Persist
        if self._storage:
            p = self._storage.load("preferences", {}) or {}
            c = set(p.get("sidebar_collapsed", []))
            if new_collapsed: c.add(section)
            else: c.discard(section)
            p["sidebar_collapsed"] = sorted(c)
            self._storage.save("preferences", p)

    def select(self, module_id: str):
        for mid, btn in self._buttons.items():
            btn.setChecked(mid == module_id)


# ----------------------------------------------------------------------------
# Search results popup
# ----------------------------------------------------------------------------
class SearchResultsPopup(QFrame):
    chosen = pyqtSignal(object)  # SearchResult

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SearchResults")
        # IMPORTANT: this is a regular child widget of the main window, NOT a
        # Qt.WindowType.Popup. The Popup flag would grab the keyboard and steal
        # focus from the search bar on every keystroke, breaking continuous typing.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.list = QListWidget()
        self.list.setObjectName("SearchResultsList")
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Keep focus on search bar
        self.list.itemActivated.connect(self._activate)
        self.list.itemClicked.connect(self._activate)
        layout.addWidget(self.list)
        self._results: list[SearchResult] = []

    def set_results(self, results: list[SearchResult]):
        self._results = results
        self.list.clear()
        for r in results:
            li = QListWidgetItem(f"  {r.icon or '•'}    {r.title}    "
                                 f"·   {r.subtitle}    "
                                 f"·   {r.category}")
            li.setData(Qt.ItemDataRole.UserRole, r)
            self.list.addItem(li)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _activate(self, item: QListWidgetItem):
        r = item.data(Qt.ItemDataRole.UserRole)
        if r:
            self.chosen.emit(r)

    def move_selection(self, delta: int):
        if not self.list.count():
            return
        cur = self.list.currentRow()
        new = max(0, min(self.list.count() - 1, cur + delta))
        self.list.setCurrentRow(new)

    def activate_current(self):
        cur = self.list.currentItem()
        if cur:
            self._activate(cur)


# ----------------------------------------------------------------------------
# Top bar with the search input
# ----------------------------------------------------------------------------
class TopBar(QFrame):
    search_changed = pyqtSignal(str)
    search_navigate = pyqtSignal(int)   # +1 / -1
    search_activate = pyqtSignal()
    search_dismiss = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(58)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(12)

        self.search = QLineEdit()
        self.search.setObjectName("SearchBar")
        self.search.setPlaceholderText("🔍   Search launchers, links, notes, agents, credentials… (Ctrl+K)")
        self.search.setMinimumWidth(420)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.search_changed.emit)
        self.search.installEventFilter(self)
        layout.addWidget(self.search, 1)

        # Right-side quick action: notifications bell with unread count
        self.bell_btn = QToolButton()
        self.bell_btn.setText("🔔")
        self.bell_btn.setStyleSheet("font-size: 20px; padding: 4px 12px; border: none; background: transparent;")
        self.bell_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bell_btn.setToolTip("Notifications — click to view history")
        layout.addWidget(self.bell_btn)

    def eventFilter(self, obj, event):
        if obj is self.search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                self.search_navigate.emit(1); return True
            if key == Qt.Key.Key_Up:
                self.search_navigate.emit(-1); return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.search_activate.emit(); return True
            if key == Qt.Key.Key_Escape:
                self.search_dismiss.emit(); return True
        return super().eventFilter(obj, event)


# ----------------------------------------------------------------------------
# MainWindow
# ----------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, storage, theme):
        super().__init__()
        self.storage = storage
        self.theme = theme
        self.search_registry = SearchRegistry()
        self.context = AppContext(storage, theme, self.search_registry, self)

        self.setWindowTitle("JARVIS")
        self.resize(1180, 760)
        self.setMinimumSize(940, 600)

        # Build app icon
        self._app_icon = make_icon(color=theme.palette["accent"])
        self.setWindowIcon(self._app_icon)

        # Central layout: animated edge / sidebar | main column
        central = QWidget()
        central_v = QVBoxLayout(central)
        central_v.setContentsMargins(0, 0, 0, 0)
        central_v.setSpacing(0)

        # JARVIS-style animated gradient bar at the very top
        from ui.widgets import AnimatedEdge
        self.edge = AnimatedEdge(
            color_a=theme.palette["accent"],
            color_b=theme.palette.get("accent_hover", theme.palette["accent"]),
            color_c=theme.palette.get("sidebar_accent", theme.palette["accent"]),
        )
        central_v.addWidget(self.edge)

        body = QWidget()
        outer = QHBoxLayout(body)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        central_v.addWidget(body, 1)

        self.sidebar = Sidebar(storage=storage)
        self.sidebar.module_selected.connect(self.navigate_to)
        outer.addWidget(self.sidebar)

        # Right column = topbar + stacked pages
        right_col = QWidget()
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.topbar = TopBar()
        self.topbar.search_changed.connect(self._on_search_text)
        self.topbar.search_navigate.connect(self._on_search_navigate)
        self.topbar.search_activate.connect(self._on_search_activate)
        self.topbar.search_dismiss.connect(self._dismiss_search)
        self.topbar.bell_btn.clicked.connect(lambda: self.navigate_to("notifications"))
        right_layout.addWidget(self.topbar)

        # Stack lives inside a "stage" widget. The stage also hosts the neural
        # background, sized to fill, kept behind the stack with stackUnder().
        self.stage = QWidget()
        from ui.neural_bg import NeuralBackground
        self.neural_bg = NeuralBackground(self.stage, palette=self.theme.palette)
        self.neural_bg.setGeometry(0, 0, 100, 100)
        self.stack = QStackedWidget(self.stage)
        # Stack itself must be transparent so the neural pattern shows through.
        self.stack.setStyleSheet("QStackedWidget { background: transparent; }")
        # The pages inside the stack inherit the standard QSS background. To
        # let the neural pattern bleed through, we'll set a per-theme override
        # on the stage and make modules use transparent backgrounds via QSS.
        right_layout.addWidget(self.stage, 1)

        # Live status strip — shown during long-running operations
        from ui.status_strip import StatusStrip
        self.status_strip = StatusStrip(self)
        right_layout.addWidget(self.status_strip)
        # Stage uses an overlay layout via resizeEvent — bind below
        self.stage.installEventFilter(self)

        outer.addWidget(right_col, 1)
        self.setCentralWidget(central)

        # Search popup — child of topbar so it positions correctly
        self.search_popup = SearchResultsPopup(self)
        self.search_popup.chosen.connect(self._on_search_result_chosen)
        self.search_popup.hide()

        # Instantiate modules (only enabled ones; honor saved order)
        self._modules: dict[str, object] = {}
        self._build_modules()

        # System tray
        self._build_tray()

        # In-app toast manager (themed, slides in from bottom-right)
        from ui.toast import ToastManager
        self.toasts = ToastManager(self)

        # Theme change repaints app icon's accent color
        self.theme.theme_changed.connect(self._on_theme_changed)

        # Global Ctrl+K shortcut focuses search
        sc = QShortcut(QKeySequence("Ctrl+K"), self)
        sc.activated.connect(self._focus_search)

        # Update bell badge periodically
        self._bell_timer = QTimer(self)
        self._bell_timer.timeout.connect(self._update_bell_badge)
        self._bell_timer.start(5_000)
        QTimer.singleShot(500, self._update_bell_badge)

        # Apply initial neural background state based on saved theme
        QTimer.singleShot(100, self._apply_neural_bg_for_theme)

        # Default page
        self.navigate_to("dashboard")

        # Application-level event filter: hide search popup when user clicks
        # anywhere outside the popup or the search bar. We use the QApplication
        # filter (not just self) so we catch clicks no matter which child widget
        # they land on.
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        # Handle stage resize — sync neural_bg + stack geometry
        if obj is getattr(self, "stage", None) and event.type() == QEvent.Type.Resize:
            w = self.stage.width()
            h = self.stage.height()
            if hasattr(self, "neural_bg"):
                self.neural_bg.setGeometry(0, 0, w, h)
                self.neural_bg.lower()  # keep behind the stack
            if hasattr(self, "stack"):
                self.stack.setGeometry(0, 0, w, h)
                self.stack.raise_()
            return False  # propagate
        # Click-outside dismissal of search popup
        try:
            sp = getattr(self, "search_popup", None)
            tb = getattr(self, "topbar", None)
            if sp is None or tb is None:
                return super().eventFilter(obj, event)
            if event.type() == QEvent.Type.MouseButtonPress and sp.isVisible():
                gp = event.globalPosition().toPoint()
                popup_rect = QRect(sp.mapToGlobal(QPoint(0, 0)), sp.size())
                bar = tb.search
                bar_rect = QRect(bar.mapToGlobal(QPoint(0, 0)), bar.size())
                if not popup_rect.contains(gp) and not bar_rect.contains(gp):
                    sp.hide()
        except Exception:
            pass
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Module loading
    # ------------------------------------------------------------------
    def _build_modules(self):
        # Clear existing — supports live rebuild from Settings
        for mid, inst in list(self._modules.items()):
            try:
                self.stack.removeWidget(inst)
                inst.deleteLater()
            except Exception:
                pass
        self._modules.clear()

        prefs = self.storage.load("preferences", {})
        all_classes = {cls.MODULE_ID: cls for cls in MODULE_CLASSES}
        enabled = set(prefs.get("enabled_modules", list(all_classes.keys())))
        # Always-on modules can never be disabled
        for cls in MODULE_CLASSES:
            if cls.ALWAYS_ON:
                enabled.add(cls.MODULE_ID)
        order = prefs.get("module_order", list(all_classes.keys()))
        # Append any new modules not yet in saved order
        for mid in all_classes:
            if mid not in order:
                order.append(mid)

        modules_by_section: dict[str, list] = {"Workspace": [], "Tools": [], "System": []}

        for mid in order:
            cls = all_classes.get(mid)
            if not cls or mid not in enabled:
                continue
            try:
                instance = cls(self.context)
            except Exception as e:
                # If a module fails to construct, skip it but stay running
                print(f"[WorkBench] Failed to load module '{mid}': {e}")
                continue
            self._modules[mid] = instance
            self.stack.addWidget(instance)
            modules_by_section.setdefault(cls.SECTION, []).append((cls, instance))

        self.sidebar.populate(modules_by_section)
        self._cached_sections = modules_by_section

    def _refresh_sidebar(self):
        """Rebuild only the sidebar entries (preserves the loaded modules)."""
        sections = getattr(self, "_cached_sections", None)
        if sections is None:
            return
        self.sidebar.populate(sections)

    def live_rebuild_sidebar(self):
        """
        Soft rebuild safe to call while the user is interacting with the app:
        - Adds newly-enabled modules
        - Removes newly-disabled modules ONLY if they're not the visible one
        - Updates the sidebar with the new module list

        The visible widget is never deleted, so the user's current page
        stays open even if they just disabled it. They'll need to navigate
        away for it to disappear from the stack.
        """
        prefs = self.storage.load("preferences", {})
        all_classes = {cls.MODULE_ID: cls for cls in MODULE_CLASSES}
        enabled = set(prefs.get("enabled_modules", list(all_classes.keys())))
        for cls in MODULE_CLASSES:
            if cls.ALWAYS_ON:
                enabled.add(cls.MODULE_ID)
        order = prefs.get("module_order", list(all_classes.keys()))
        for mid in all_classes:
            if mid not in order:
                order.append(mid)

        # Currently visible module — never destroy this one
        current_widget = self.stack.currentWidget()
        current_mid = None
        for mid, inst in self._modules.items():
            if inst is current_widget:
                current_mid = mid
                break

        # Remove modules that are no longer enabled (except current visible)
        for mid in list(self._modules.keys()):
            if mid not in enabled and mid != current_mid:
                inst = self._modules.pop(mid)
                try:
                    self.stack.removeWidget(inst)
                    inst.deleteLater()
                except Exception:
                    pass

        # Add modules that are enabled but not loaded yet
        for mid in order:
            if mid in enabled and mid not in self._modules:
                cls = all_classes.get(mid)
                if not cls:
                    continue
                try:
                    instance = cls(self.context)
                except Exception as e:
                    print(f"[JARVIS] Failed to load module '{mid}': {e}")
                    continue
                self._modules[mid] = instance
                self.stack.addWidget(instance)

        # Rebuild the sections snapshot in saved order, with only enabled modules
        modules_by_section: dict[str, list] = {"Workspace": [], "Tools": [], "System": []}
        for mid in order:
            cls = all_classes.get(mid)
            if not cls:
                continue
            if mid not in enabled and mid != current_mid:
                continue
            inst = self._modules.get(mid)
            if inst is None:
                continue
            modules_by_section.setdefault(cls.SECTION, []).append((cls, inst))

        self._cached_sections = modules_by_section
        self.sidebar.populate(modules_by_section)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def navigate_to(self, module_id: str):
        instance = self._modules.get(module_id)
        if not instance:
            # Fall back to dashboard
            instance = self._modules.get("dashboard")
            module_id = "dashboard"
        if not instance:
            return
        # Notify the module being hidden, then shown
        current = self.stack.currentWidget()
        if current and current is not instance and hasattr(current, "on_hide"):
            try: current.on_hide()
            except Exception: pass
        self.stack.setCurrentWidget(instance)
        self.sidebar.select(module_id)
        if hasattr(instance, "on_show"):
            try: instance.on_show()
            except Exception: pass
        self._dismiss_search()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def _focus_search(self):
        self.topbar.search.setFocus()
        self.topbar.search.selectAll()

    def _on_search_text(self, text: str):
        text = text.strip()
        if not text:
            self._dismiss_search()
            return
        results = self.search_registry.search(text, limit=15)
        # Add module navigation results too
        for cls in MODULE_CLASSES:
            if cls.MODULE_ID not in self._modules:
                continue
            from core.search import fuzzy_score
            score = fuzzy_score(text, cls.NAME)
            if score > 0.4:
                results.append(SearchResult(
                    title=f"Open {cls.NAME}",
                    subtitle=cls.DESCRIPTION,
                    category="Navigate",
                    icon=cls.ICON,
                    action=lambda mid=cls.MODULE_ID: self.navigate_to(mid),
                    score=score,
                ))
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:15]

        if not results:
            self._dismiss_search()
            return

        self.search_popup.set_results(results)
        # Position popup right below the search bar, in MAIN WINDOW coordinates
        # (popup is a child of MainWindow now, not a top-level Qt.Popup).
        bar = self.topbar.search
        pos = bar.mapTo(self, QPoint(0, bar.height() + 4))
        width = max(bar.width(), 480)
        # Don't extend past the right edge of the window
        max_width = self.width() - pos.x() - 16
        if max_width > 200:
            width = min(width, max_width)
        height = min(360, 56 + 36 * len(results))
        self.search_popup.setGeometry(pos.x(), pos.y(), width, height)
        self.search_popup.raise_()
        self.search_popup.show()

    def _on_search_navigate(self, delta: int):
        if self.search_popup.isVisible():
            self.search_popup.move_selection(delta)

    def _on_search_activate(self):
        if self.search_popup.isVisible():
            self.search_popup.activate_current()

    def _on_search_result_chosen(self, result: SearchResult):
        self._dismiss_search()
        try:
            result.action()
        except Exception as e:
            print(f"[WorkBench] Search action failed: {e}")

    def _dismiss_search(self):
        self.search_popup.hide()

    # ------------------------------------------------------------------
    # System tray + notifications
    # ------------------------------------------------------------------
    def _build_tray(self):
        self.tray = QSystemTrayIcon(self._app_icon, self)
        self.tray.setToolTip("JARVIS")
        menu = QMenu()
        show_act = QAction("Open JARVIS", self); show_act.triggered.connect(self._show_and_raise)
        notif_act = QAction("Notifications", self); notif_act.triggered.connect(lambda: (self._show_and_raise(), self.navigate_to("notifications")))
        quit_act = QAction("Quit", self); quit_act.triggered.connect(QApplication.instance().quit)
        menu.addAction(show_act); menu.addAction(notif_act); menu.addSeparator(); menu.addAction(quit_act)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_and_raise()

    def _show_and_raise(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def show_notification(self, title: str, body: str = "", kind: str = "info"):
        """Show a tray balloon. Doesn't log — the caller's ctx.notify() does that.
        Note: in-app themed toast was removed to avoid double-notify (tray + toast)."""
        try:
            self.tray.showMessage(title, body or " ", QSystemTrayIcon.MessageIcon.Information, 4000)
        except Exception:
            pass

    def _update_bell_badge(self):
        log = self.storage.load("notifications_log", [])
        unread = sum(1 for n in log if not n.get("read"))
        if unread:
            self.topbar.bell_btn.setText(f"🔔  {unread}")
        else:
            self.topbar.bell_btn.setText("🔔")

    # ------------------------------------------------------------------
    # Theme handling
    # ------------------------------------------------------------------
    def _on_theme_changed(self, _name: str):
        # Refresh app icon to use the new accent
        self._app_icon = make_icon(color=self.theme.palette["accent"])
        self.setWindowIcon(self._app_icon)
        self.tray.setIcon(self._app_icon)
        # Update animated edge to match new accent
        if hasattr(self, "edge"):
            self.edge.set_colors(
                self.theme.palette["accent"],
                self.theme.palette.get("accent_hover", self.theme.palette["accent"]),
                self.theme.palette.get("sidebar_accent", self.theme.palette["accent"]),
            )
        # Apply / remove the JARVIS HUD neural backdrop
        self._apply_neural_bg_for_theme()

    def _apply_neural_bg_for_theme(self):
        is_hud = (self.theme.current_name == "JARVIS HUD")
        if hasattr(self, "neural_bg"):
            self.neural_bg.setVisible(is_hud)
            if is_hud:
                self.neural_bg.set_palette(self.theme.palette)

    # ------------------------------------------------------------------
    # Close / minimize behavior — stay alive in tray
    # ------------------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Reposition any active toasts so they stay in the corner
        if hasattr(self, "toasts"):
            try:
                self.toasts._reposition()
            except Exception:
                pass

    def closeEvent(self, event):
        # Hide to tray instead of quitting. Quit only via tray menu.
        if self.tray.isVisible():
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "JARVIS is still running",
                "Reminders and timers continue in the tray. Right-click the icon to quit.",
                QSystemTrayIcon.MessageIcon.Information, 3000,
            )
        else:
            event.accept()
