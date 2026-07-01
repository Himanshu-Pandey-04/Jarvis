"""
Timers. Multiple named countdown timers running concurrently, plus
Pomodoro presets (25/5, 50/10). Notifies on completion.
"""
import uuid
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QListWidget,
    QListWidgetItem, QDialog, QDialogButtonBox, QSpinBox, QFormLayout, QFrame,
    QWidget, QMessageBox, QMenu, QGridLayout, QDateEdit, QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QDate
from PyQt6.QtGui import QAction, QCursor

from modules.base import Module
from ui.widgets import SectionHeader, Card
from core.search import SearchResult, fuzzy_score


def fmt_seconds(secs: int) -> str:
    if secs < 0:
        secs = 0
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


class TimerEditDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New timer")
        self.setMinimumWidth(360)
        form = QFormLayout(self)
        self.name_in = QLineEdit("Focus")
        self.h_in = QSpinBox(); self.h_in.setRange(0, 12); self.h_in.setSuffix("  h")
        self.m_in = QSpinBox(); self.m_in.setRange(0, 59); self.m_in.setValue(25); self.m_in.setSuffix("  m")
        self.s_in = QSpinBox(); self.s_in.setRange(0, 59); self.s_in.setSuffix("  s")
        time_row = QHBoxLayout()
        for w in (self.h_in, self.m_in, self.s_in): time_row.addWidget(w)
        form.addRow("Label", self.name_in)
        form.addRow("Duration", time_row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def value(self):
        secs = self.h_in.value() * 3600 + self.m_in.value() * 60 + self.s_in.value()
        return self.name_in.text().strip() or "Timer", max(secs, 1)


class TimersModule(Module):
    MODULE_ID = "timers"
    NAME = "Timers"
    ICON = "⏳"
    SECTION = "Tools"
    DESCRIPTION = "Named countdowns, Pomodoro presets."

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        header = SectionHeader(
            "Timers",
            "Multiple named countdowns. Notifies when done.",
            action_text="+  Custom timer",
        )
        header.action_clicked.connect(self.new_custom_timer)
        outer.addWidget(header)

        # Presets
        presets_card = Card()
        pl = QGridLayout(presets_card); pl.setContentsMargins(14, 14, 14, 14); pl.setSpacing(10)
        presets_lbl = QLabel("Presets")
        presets_lbl.setStyleSheet("font-weight:600;")
        pl.addWidget(presets_lbl, 0, 0, 1, 4)
        self._add_preset_button(pl, "🍅 Pomodoro", "Pomodoro", 25 * 60, row=1, col=0)
        self._add_preset_button(pl, "☕ Short break", "Short break", 5 * 60, row=1, col=1)
        self._add_preset_button(pl, "🛌 Long break", "Long break", 15 * 60, row=1, col=2)
        self._add_preset_button(pl, "🎯 Deep focus", "Deep focus", 50 * 60, row=1, col=3)
        outer.addWidget(presets_card)

        # Active timers list
        self.list_widget = QListWidget()
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.setMinimumHeight(150)
        self.list_widget.setMaximumHeight(220)
        outer.addWidget(self.list_widget)

        # === Daily history ===
        hist_card = Card()
        hl = QVBoxLayout(hist_card); hl.setContentsMargins(14, 12, 14, 12); hl.setSpacing(8)
        head_row = QHBoxLayout()
        h_title = QLabel("📒  Timer history")
        h_title.setStyleSheet("font-weight:600; font-size:14px;")
        head_row.addWidget(h_title); head_row.addStretch()
        head_row.addWidget(QLabel("Date:"))
        self.hist_date = QDateEdit()
        self.hist_date.setCalendarPopup(True)
        self.hist_date.setDate(QDate.currentDate())
        self.hist_date.setDisplayFormat("yyyy-MM-dd")
        self.hist_date.dateChanged.connect(self._refresh_history)
        head_row.addWidget(self.hist_date)
        today_btn = QPushButton("Today")
        today_btn.setProperty("ghost", True)
        today_btn.clicked.connect(lambda: self.hist_date.setDate(QDate.currentDate()))
        head_row.addWidget(today_btn)
        clear_btn = QPushButton("🗑  Clear all history")
        clear_btn.setProperty("ghost", True)
        clear_btn.clicked.connect(self._clear_history)
        head_row.addWidget(clear_btn)
        hl.addLayout(head_row)

        self.hist_summary_lbl = QLabel("")
        self.hist_summary_lbl.setProperty("class", "Muted")
        self.hist_summary_lbl.setStyleSheet("padding: 2px 0 6px 0;")
        hl.addWidget(self.hist_summary_lbl)

        self.hist_list = QListWidget()
        self.hist_list.setMinimumHeight(150)
        hl.addWidget(self.hist_list)
        outer.addWidget(hist_card, 1)

        # Tick every second to update displayed countdowns
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._refresh)
        self._tick.start(1000)

        self._refresh()
        self._refresh_history()

    def _refresh_history(self):
        """Show timer log filtered to selected date."""
        if not hasattr(self, "hist_list"):
            return
        sel_date = self.hist_date.date().toPyDate()
        entries = self._log()
        # Filter to selected date by started_at
        today_entries = []
        for e in entries:
            try:
                started = datetime.fromisoformat(e.get("started_at", ""))
                if started.date() == sel_date:
                    today_entries.append(e)
            except Exception:
                continue
        # Sort newest first
        today_entries.sort(key=lambda e: e.get("started_at", ""), reverse=True)

        # Summary
        total_secs = sum(e.get("duration", 0) for e in today_entries
                         if e.get("status") == "completed")
        completed = sum(1 for e in today_entries if e.get("status") == "completed")
        stopped = sum(1 for e in today_entries if e.get("status") == "stopped")
        if today_entries:
            self.hist_summary_lbl.setText(
                f"{completed} completed · {stopped} stopped · "
                f"{self._duration_str(total_secs)} of focused time")
        else:
            self.hist_summary_lbl.setText("No timers on this day yet.")

        self.hist_list.clear()
        if not today_entries:
            li = QListWidgetItem("Nothing logged for this date.")
            li.setFlags(Qt.ItemFlag.NoItemFlags)
            self.hist_list.addItem(li)
            return
        for e in today_entries:
            icon = "✓" if e.get("status") == "completed" else "✗"
            try:
                started = datetime.fromisoformat(e["started_at"]).strftime("%H:%M")
                ended = datetime.fromisoformat(e["ended_at"]).strftime("%H:%M")
            except Exception:
                started = ended = "?"
            dur = self._duration_str(int(e.get("duration", 0)))
            li = QListWidgetItem(
                f"  {icon}   {e.get('name', 'Timer')}    ·   "
                f"{started}–{ended}   ·   {dur}   ·   {e.get('status', 'completed')}"
            )
            self.hist_list.addItem(li)

    def _clear_history(self):
        if not self._log():
            return
        if QMessageBox.question(self, "Clear timer history",
                                 "Permanently delete all timer log entries?"
                                 ) != QMessageBox.StandardButton.Yes:
            return
        self._save_log([])
        self.ctx.notify("Timer history cleared", "All log entries removed.",
                        sound="success", source="Timers", user_initiated=True)
        self._refresh_history()

    def _add_preset_button(self, grid, label, name, seconds, row, col):
        btn = QPushButton(label)
        btn.setMinimumHeight(48)
        btn.clicked.connect(lambda _=False, n=name, s=seconds: self.start_timer(n, s))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        grid.addWidget(btn, row, col)

    def _state(self) -> dict:
        # {"running": [{"id","name","ends_at","duration"}]}
        return self.ctx.storage.load("module_timers_state", {"running": []})

    def _save_state(self, st: dict):
        self.ctx.storage.save("module_timers_state", st)

    def _log(self) -> list[dict]:
        """Returns past timer sessions. Each entry: {id, name, started_at,
        ended_at, duration_secs, status: 'completed'|'stopped'}"""
        return self.ctx.storage.load("module_timers_log", []) or []

    def _save_log(self, entries: list[dict]):
        # Cap at 2000 entries (~plenty for many months of use)
        if len(entries) > 2000:
            entries = entries[-2000:]
        self.ctx.storage.save("module_timers_log", entries)

    def _log_session(self, timer: dict, status: str):
        """Append a completed/stopped timer to the log."""
        try:
            duration = int(timer.get("duration", 0))
            ends = datetime.fromisoformat(timer["ends_at"])
            started = ends - timedelta(seconds=duration)
            log = self._log()
            log.append({
                "id":          timer.get("id", ""),
                "name":        timer.get("name", "Timer"),
                "started_at":  started.isoformat(timespec="seconds"),
                "ended_at":    datetime.now().isoformat(timespec="seconds"),
                "duration":    duration,
                "status":      status,  # 'completed' | 'stopped'
            })
            self._save_log(log)
        except Exception:
            pass

    def start_timer(self, name: str, seconds: int):
        st = self._state()
        st.setdefault("running", []).append({
            "id":       uuid.uuid4().hex,
            "name":     name,
            "ends_at":  (datetime.now() + timedelta(seconds=seconds)).isoformat(timespec="seconds"),
            "duration": seconds,
        })
        self._save_state(st)
        self._refresh()

    def new_custom_timer(self):
        dlg = TimerEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, secs = dlg.value()
            self.start_timer(name, secs)

    def _stop(self, t):
        st = self._state()
        st["running"] = [x for x in st.get("running", []) if x.get("id") != t.get("id")]
        self._save_state(st)
        self._log_session(t, "stopped")
        self._refresh()
        if hasattr(self, "hist_list"):
            self._refresh_history()

    def _refresh(self):
        st = self._state()
        running = st.get("running", [])
        now = datetime.now()
        finished = []
        active = []
        for t in running:
            try:
                ends = datetime.fromisoformat(t["ends_at"])
            except (ValueError, TypeError, KeyError):
                continue
            if ends <= now:
                finished.append(t)
            else:
                active.append((t, int((ends - now).total_seconds())))

        # Fire completion notifications and remove finished
        if finished:
            for t in finished:
                self.ctx.notify(f"⏳ Timer ‘{t.get('name','Timer')}’ done", "Time's up.",
                                sound="timer", source="Timers")
                self._log_session(t, "completed")
            st["running"] = [x for x in running if x not in finished]
            self._save_state(st)
            # Refresh history pane if it exists
            if hasattr(self, "hist_list"):
                self._refresh_history()

        self.list_widget.clear()
        if not active:
            li = QListWidgetItem("No timers running. Pick a preset or create a custom timer above.")
            li.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(li)
            return
        for t, remaining in active:
            li = QListWidgetItem(f"  ⏳   {t['name']}    "
                                 f"·   {fmt_seconds(remaining)} remaining    "
                                 f"·   started {self._duration_str(t.get('duration', 0))}")
            li.setData(Qt.ItemDataRole.UserRole, t)
            self.list_widget.addItem(li)

    def _duration_str(self, secs: int) -> str:
        if secs >= 3600:
            return f"{secs // 3600}h {(secs % 3600) // 60}m"
        return f"{secs // 60}m"

    def _show_context_menu(self, _pos):
        cur = self.list_widget.currentItem()
        if not cur: return
        t = cur.data(Qt.ItemDataRole.UserRole)
        if not t: return
        menu = QMenu(self)
        stop_act = QAction("Stop timer", self); stop_act.triggered.connect(lambda: self._stop(t))
        add5 = QAction("Add 5 minutes", self);  add5.triggered.connect(lambda: self._extend(t, 5))
        menu.addAction(add5); menu.addAction(stop_act)
        menu.exec(QCursor.pos())

    def _extend(self, t, minutes: int):
        st = self._state()
        for x in st.get("running", []):
            if x.get("id") == t.get("id"):
                try:
                    ends = datetime.fromisoformat(x["ends_at"])
                except (ValueError, TypeError):
                    continue
                x["ends_at"] = (ends + timedelta(minutes=minutes)).isoformat(timespec="seconds")
                x["duration"] = x.get("duration", 0) + minutes * 60
        self._save_state(st)
        self._refresh()

    def register_search(self):
        # Search lets you launch a preset by typing its name
        def provider(query: str) -> list[SearchResult]:
            presets = [
                ("Start Pomodoro (25m)",    "Pomodoro",    25 * 60),
                ("Start Short break (5m)",  "Short break", 5 * 60),
                ("Start Long break (15m)",  "Long break",  15 * 60),
                ("Start Deep focus (50m)",  "Deep focus",  50 * 60),
            ]
            results = []
            for label, name, secs in presets:
                score = fuzzy_score(query, label)
                if score > 0.25:
                    results.append(SearchResult(
                        title=label, subtitle="Timer preset",
                        category="Timer", icon="⏳",
                        action=lambda n=name, s=secs: self.start_timer(n, s),
                        score=score,
                    ))
            return results
        self.ctx.search.register("timers", provider)

    def on_show(self):
        self._refresh()
