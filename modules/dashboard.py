"""
Dashboard. The "home" page. Shows pinned launchers/links/apps/docs as a grid,
plus an at-a-glance summary (today's todos, upcoming reminders, active timers,
and active-time tracker).

PinnedTile is now a real composed widget (icon + name + kind QLabels) instead
of HTML inside a button — that fixes the bug where some Qt builds rendered the
raw HTML markup instead of the styled tile.
"""
import os
import subprocess
import webbrowser
from datetime import datetime, date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, QPushButton,
    QSizePolicy, QMenu, QApplication, QScrollArea,
)
from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QCursor, QAction

from modules.base import Module
from ui.widgets import Card, SectionHeader, ScrollContainer, EmptyState
from core.activity import ActivityTracker


class PinnedTile(QFrame):
    """
    A real composed tile (no HTML) so the icon/name/kind always render as a UI,
    not raw text. Click runs the open action; right-click offers Unpin.
    """
    def __init__(self, item: dict, on_open, on_remove, parent=None):
        super().__init__(parent)
        self.setObjectName("PinTile")
        self.item = item
        self.on_open = on_open
        self.on_remove = on_remove
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(82)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        icon_lbl = QLabel(item.get("icon", "📌"))
        icon_lbl.setObjectName("PinTileIcon")

        name_lbl = QLabel(item.get("name", "Untitled"))
        name_lbl.setObjectName("PinTileName")

        kind_lbl = QLabel(item.get("kind", "link").upper())
        kind_lbl.setObjectName("PinTileKind")

        layout.addWidget(icon_lbl)
        layout.addWidget(name_lbl)
        layout.addWidget(kind_lbl)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_open(self.item)
        super().mousePressEvent(event)

    def _show_menu(self, _pos):
        menu = QMenu(self)
        unpin = QAction("Unpin from dashboard", self)
        unpin.triggered.connect(lambda: self.on_remove(self.item))
        menu.addAction(unpin)
        menu.exec(QCursor.pos())


class DashboardModule(Module):
    MODULE_ID = "dashboard"
    NAME = "Dashboard"
    ICON = "🏠"
    SECTION = "Workspace"
    DESCRIPTION = "Pinned shortcuts and at-a-glance summary."
    ALWAYS_ON = True

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = ScrollContainer(self)

        header = SectionHeader(
            "Welcome back",
            "Your pinned shortcuts and a quick read on today.",
        )
        scroll.add(header)

        # Greeting card with date/time
        self.greeting_card = self._build_greeting_card()
        scroll.add(self.greeting_card)

        # Music control (only shows when something is playing)
        self.music_card = self._build_music_card()
        scroll.add(self.music_card)

        # Pinned grid
        scroll.add(self._build_pinned_section())

        # Today snapshot row
        scroll.add(self._build_snapshot_row())

        scroll.add_stretch()
        outer.addWidget(scroll)

        # Activity tracker — system-wide on Windows, in-app fallback elsewhere
        self.tracker = ActivityTracker()
        # Restore today's accumulated time across app restarts
        saved = self.ctx.storage.load("activity_today", {})
        if saved.get("date") == date.today().isoformat():
            self.tracker.session_active = float(saved.get("seconds", 0.0))

        self._activity_timer = QTimer(self)
        self._activity_timer.timeout.connect(self._on_activity_tick)
        self._activity_timer.start(5000)  # every 5s

        # Live clock refresher
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._refresh_greeting)
        self._clock_timer.start(30_000)

    def on_show(self):
        self._refresh_greeting()
        self._refresh_pinned()
        self._refresh_snapshot()
        self.refresh_music_widget()

    # ---------- Greeting ----------
    def _build_greeting_card(self) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        self.greet_lbl = QLabel()
        self.greet_lbl.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.date_lbl = QLabel()
        self.date_lbl.setProperty("class", "Muted")
        layout.addWidget(self.greet_lbl)
        layout.addWidget(self.date_lbl)
        self._refresh_greeting()
        return card

    def _refresh_greeting(self):
        now = datetime.now()
        h = now.hour
        if   h < 5:  greet = "Working late"
        elif h < 12: greet = "Good morning"
        elif h < 17: greet = "Good afternoon"
        elif h < 21: greet = "Good evening"
        else:        greet = "Burning the midnight oil"
        self.greet_lbl.setText(f"{greet}.")
        self.date_lbl.setText(now.strftime("%A, %d %B %Y · %H:%M"))

    # ---------- Music control ----------
    def _build_music_card(self) -> Card:
        card = Card()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(12)

        self._music_icon = QLabel("🎵")
        self._music_icon.setStyleSheet("font-size:20px;")
        layout.addWidget(self._music_icon)

        text_col = QVBoxLayout(); text_col.setSpacing(0)
        self._music_status = QLabel("Now playing")
        self._music_status.setStyleSheet("font-size:11px; font-weight:600;")
        self._music_status.setProperty("class", "Muted")
        self._music_title = QLabel("—")
        self._music_title.setStyleSheet("font-size:14px; font-weight:600;")
        text_col.addWidget(self._music_status)
        text_col.addWidget(self._music_title)
        layout.addLayout(text_col, 1)

        self._music_pause_btn = QPushButton("⏸  Pause")
        self._music_pause_btn.setProperty("ghost", True)
        self._music_pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._music_pause_btn.clicked.connect(self._on_pause_resume)
        layout.addWidget(self._music_pause_btn)

        self._music_stop_btn = QPushButton("⏹  Stop")
        self._music_stop_btn.setProperty("ghost", True)
        self._music_stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._music_stop_btn.clicked.connect(self._on_stop)
        layout.addWidget(self._music_stop_btn)

        open_btn = QPushButton("🎧  Open Focus Music")
        open_btn.setProperty("ghost", True)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(lambda: self.ctx.navigate("focus_music"))
        layout.addWidget(open_btn)

        card.hide()  # only show when playing
        return card

    def refresh_music_widget(self):
        fm = self.ctx.get_module("focus_music")
        if fm is None:
            self.music_card.hide(); return
        if fm.is_playing() or fm.is_paused():
            self.music_card.show()
            name = fm.current_display_name() or "Focus track"
            if fm.is_paused():
                self._music_status.setText("Paused")
                self._music_pause_btn.setText("▶  Resume")
            else:
                self._music_status.setText("Now playing")
                self._music_pause_btn.setText("⏸  Pause")
            self._music_title.setText(name)
        else:
            self.music_card.hide()

    def _on_pause_resume(self):
        fm = self.ctx.get_module("focus_music")
        if fm: fm.pause_resume()

    def _on_stop(self):
        fm = self.ctx.get_module("focus_music")
        if fm: fm.stop_external()

    # ---------- Pinned grid ----------
    def _build_pinned_section(self) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 20)

        head_row = QHBoxLayout()
        title = QLabel("Pinned")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        head_row.addWidget(title)
        head_row.addStretch()
        hint = QLabel("Pin items from Launchers, Links, Documents or Templates")
        hint.setProperty("class", "Muted")
        head_row.addWidget(hint)
        layout.addLayout(head_row)

        self.pinned_grid_host = QWidget()
        self.pinned_grid = QGridLayout(self.pinned_grid_host)
        self.pinned_grid.setSpacing(10)
        self.pinned_grid.setContentsMargins(0, 8, 4, 0)

        # Scroll the pins when more than ~2 rows fit. Max height holds 2 rows
        # comfortably (~140px each + spacing); beyond that, vertical scroll.
        pinned_scroll = QScrollArea()
        pinned_scroll.setWidget(self.pinned_grid_host)
        pinned_scroll.setWidgetResizable(True)
        pinned_scroll.setFrameShape(QFrame.Shape.NoFrame)
        pinned_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        pinned_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        pinned_scroll.setMaximumHeight(320)
        pinned_scroll.setStyleSheet("QScrollArea { background: transparent; }")
        layout.addWidget(pinned_scroll)

        self._refresh_pinned()
        return card

    def _refresh_pinned(self):
        # Clear existing
        while self.pinned_grid.count():
            item = self.pinned_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # Reset row constraints from previous frames
        for r in range(8):
            self.pinned_grid.setRowMinimumHeight(r, 0)

        pins = self.ctx.storage.load("pinned_items", [])
        if not pins:
            empty = EmptyState(
                "📌", "Nothing pinned yet",
                "Right-click items in Launchers, Links, Documents or Templates and pick "
                "“Pin to dashboard” to build a one-click launcher you'll actually use."
            )
            # Force the row to honor the EmptyState's preferred height
            self.pinned_grid.setRowMinimumHeight(0, 220)
            self.pinned_grid.addWidget(empty, 0, 0, 1, 4)
            return

        cols = 4
        for i, item in enumerate(pins):
            tile = PinnedTile(item, self._open_pinned, self._unpin)
            self.pinned_grid.addWidget(tile, i // cols, i % cols)

    def _unpin(self, item: dict):
        pins = self.ctx.storage.load("pinned_items", [])
        pins = [p for p in pins
                if not (p.get("kind") == item.get("kind") and p.get("ref") == item.get("ref"))]
        self.ctx.storage.save("pinned_items", pins)
        self._refresh_pinned()

    def _open_pinned(self, item: dict):
        self.ctx.play_sound("click")
        kind = item.get("kind")
        ref = item.get("ref", "")
        try:
            if kind == "link":
                webbrowser.open(ref)
            elif kind == "document":
                if os.path.exists(ref):
                    if os.name == "nt":
                        os.startfile(ref)  # type: ignore[attr-defined]
                    else:
                        subprocess.Popen(["xdg-open", ref])
            elif kind == "app":
                if os.name == "nt":
                    os.startfile(ref)  # type: ignore[attr-defined]
                else:
                    subprocess.Popen([ref])
            elif kind == "template":
                QApplication.clipboard().setText(ref)
                self.ctx.notify("Template copied", item.get("name", ""), sound="success")
            elif kind == "launcher":
                launchers = self.ctx.get_module("launchers")
                if launchers and launchers.run_launcher_by_id(ref):
                    return
                self.ctx.notify("Launcher not found",
                                "It may have been deleted — unpin from the dashboard.",
                                sound="error")
        except Exception as e:
            self.ctx.notify("Couldn't open", str(e), sound="error")

    # ---------- Snapshot row ----------
    def _build_snapshot_row(self) -> QWidget:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        self.todo_card     = self._mini_card("✓",  "Open tasks",          "—")
        self.rem_card      = self._mini_card("⏰", "Due in 24h",          "—")
        self.timer_card    = self._mini_card("⏳", "Active timers",       "—")
        self.activity_card = self._mini_card("⚡", "Active today",        "0s")

        row.addWidget(self.todo_card)
        row.addWidget(self.rem_card)
        row.addWidget(self.timer_card)
        row.addWidget(self.activity_card)
        return host

    def _mini_card(self, icon: str, title: str, value: str) -> Card:
        card = Card()
        l = QVBoxLayout(card)
        l.setContentsMargins(18, 16, 18, 16)
        head = QLabel(f"{icon}  {title}")
        head.setProperty("class", "Muted")
        head.setStyleSheet("font-size: 13px;")
        val  = QLabel(value)
        val.setStyleSheet("font-size: 24px; font-weight: 700;")
        val.setObjectName("mini_value")
        l.addWidget(head)
        l.addWidget(val)
        return card

    def _set_mini(self, card: Card, value: str):
        lbl = card.findChild(QLabel, "mini_value")
        if lbl is not None:
            lbl.setText(value)

    def _refresh_snapshot(self):
        # Unified tasks (was: todos + reminders)
        tasks = self.ctx.storage.load("module_tasks", [])
        now = datetime.now()

        # Open tasks (not completed)
        open_tasks = [t for t in tasks if not t.get("completed")]
        self._set_mini(self.todo_card, str(len(open_tasks)))

        # Tasks due within 24h
        upcoming = 0
        for t in open_tasks:
            due_at = t.get("due_at")
            if not due_at: continue
            try:
                when = datetime.fromisoformat(due_at)
                if 0 <= (when - now).total_seconds() <= 86400:
                    upcoming += 1
            except (ValueError, TypeError):
                pass
        self._set_mini(self.rem_card, str(upcoming))

        # Active timers
        timers = self.ctx.storage.load("module_timers_state", {"running": []})
        self._set_mini(self.timer_card, str(len(timers.get("running", []))))

        # Activity
        self._set_mini(self.activity_card, ActivityTracker.format_duration(self.tracker.session_active))

    # ---------- Activity ----------
    def _on_activity_tick(self):
        self.tracker.tick()
        self.ctx.storage.save("activity_today", {
            "date": date.today().isoformat(),
            "seconds": self.tracker.session_active,
        })
        self._set_mini(self.activity_card,
                       ActivityTracker.format_duration(self.tracker.session_active))
