"""
Tasks — unified to-do list + reminders.

Replaces the separate ToDo and Reminders modules. Everything is a task:
  • Open-ended tasks have no due time (acts like the old ToDo)
  • Tasks with a `due_at` fire as reminders when their time comes
  • Tasks can recur — daily, weekdays-only, weekly, or "every N hours/days/weeks"
  • Tasks can carry a URL that auto-opens when fired or completed

Defaults include the Time Entry reminder (every 3 weekdays, opens the SAP
NetWeaver portal).
"""
import uuid
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QLineEdit, QComboBox,
    QDateTimeEdit, QSpinBox, QPlainTextEdit, QFrame, QListWidget, QListWidgetItem,
    QDialog, QDialogButtonBox, QFormLayout, QCheckBox, QMessageBox, QInputDialog,
    QMenu, QWidget,
)
from PyQt6.QtCore import Qt, QTimer, QDateTime
from PyQt6.QtGui import QAction

from modules.base import Module
from ui.widgets import SectionHeader, Card, EmptyState, ScrollContainer
from core.search import SearchResult, fuzzy_score


# Recurrence options. "None" = one-off task. The "every N" type uses interval_n
# and interval_unit (hours/days/weeks).
RECUR_NONE       = "None"
RECUR_DAILY      = "Daily"
RECUR_WEEKDAYS   = "Weekdays only"
RECUR_WEEKLY     = "Weekly"
RECUR_EVERY      = "Every N…"
RECUR_OPTIONS    = [RECUR_NONE, RECUR_DAILY, RECUR_WEEKDAYS, RECUR_WEEKLY, RECUR_EVERY]

UNIT_HOURS = "hours"
UNIT_DAYS  = "days"
UNIT_WEEKS = "weeks"
UNIT_WORKDAYS = "working days"
UNITS = [UNIT_HOURS, UNIT_DAYS, UNIT_WORKDAYS, UNIT_WEEKS]


# ----------------------------------------------------------------------------
# Default tasks — seeded on first launch and re-seeded if user removed them
# ----------------------------------------------------------------------------
DEFAULT_TASKS = [
    {
        "id":              "time-entry-friday",
        "title":           "🚨 Submit time entry (Friday)",
        "notes":           "Don't lose track of billable hours. Log everything in the SAP NetWeaver portal before the weekend.",
        "url":             "https://zsap.zs.local/irj/portal",
        "priority":        "High",
        "recurrence":      RECUR_WEEKLY,
        "interval_n":      1,
        "interval_unit":   UNIT_WEEKS,
        "due_at":          None,  # set to next Friday 17:00 in _ensure_defaults
        "completed":       False,
        "fired_at":        None,
        "from_defaults":   True,
    },
    {
        "id":              "cab-book-tomorrow",
        "title":           "🚕 Book office cab for tomorrow",
        "notes":           "Lock in your morning ride. Book your office cab for tomorrow now.",
        "url":             "",
        "priority":        "High",
        "recurrence":      RECUR_WEEKDAYS,
        "interval_n":      1,
        "interval_unit":   UNIT_DAYS,
        "due_at":          None,  # set to next weekday 18:00 in _ensure_defaults
        "completed":       False,
        "fired_at":        None,
        "from_defaults":   True,
    },
    {
        "id":              "cab-logout",
        "title":           "🚕 Logout cab time",
        "notes":           "Office cab leaves in a few minutes. Wrap up and head out.",
        "url":             "",
        "priority":        "High",
        "recurrence":      RECUR_WEEKDAYS,
        "interval_n":      1,
        "interval_unit":   UNIT_DAYS,
        "due_at":          None,  # set to next weekday 18:55 in _ensure_defaults
        "completed":       False,
        "fired_at":        None,
        "from_defaults":   True,
    },
    {
        "id":              "los-trainings",
        "title":           "📚 Complete LOS trainings",
        "notes":           "Monthly compliance check — finish any pending Lines-of-Service trainings.",
        "url":             "https://myworkspace-am.boehringer-ingelheim.com/Citrix/BIStore4Web",
        "priority":        "High",
        "recurrence":      RECUR_EVERY,
        "interval_n":      30,
        "interval_unit":   UNIT_DAYS,
        "due_at":          None,  # set to ~30 days from first run
        "completed":       False,
        "fired_at":        None,
        "from_defaults":   True,
    },
]


# Legacy IDs we want gone (these were earlier defaults that have been
# renamed, replaced, or removed). Migration sweeps them out on every launch.
LEGACY_TASK_IDS_TO_REMOVE = {
    "time-entry",         # replaced by time-entry-friday
}


# ============================================================================
# Edit dialog
# ============================================================================
class TaskDialog(QDialog):
    def __init__(self, parent=None, task: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit task" if task else "New task")
        self.setMinimumWidth(480)
        form = QFormLayout(self)

        self.title_in = QLineEdit(task.get("title", "") if task else "")
        self.title_in.setPlaceholderText("What needs doing?")

        self.notes_in = QPlainTextEdit(task.get("notes", "") if task else "")
        self.notes_in.setMaximumHeight(70)
        self.notes_in.setPlaceholderText("Optional details")

        self.url_in = QLineEdit(task.get("url", "") if task else "")
        self.url_in.setPlaceholderText("Optional — opens when fired or completed")

        self.priority_in = QComboBox()
        self.priority_in.addItems(["Low", "Normal", "High"])
        self.priority_in.setCurrentText(task.get("priority", "Normal") if task else "Normal")

        # Due time
        self.has_due_cb = QCheckBox("Has a due time")
        self.due_in = QDateTimeEdit()
        self.due_in.setCalendarPopup(True)
        self.due_in.setDisplayFormat("yyyy-MM-dd  HH:mm")
        self.due_in.setMinimumWidth(220)
        # Be explicit — defaults can drop the arrows depending on style
        self.due_in.setButtonSymbols(QDateTimeEdit.ButtonSymbols.UpDownArrows)
        # Replace Qt's prev/next month icons with high-contrast text arrows
        # so they're readable on every theme palette.
        try:
            cal = self.due_in.calendarWidget()
            prev_btn = cal.findChild(QWidget, "qt_calendar_prevmonth")
            next_btn = cal.findChild(QWidget, "qt_calendar_nextmonth")
            if prev_btn and hasattr(prev_btn, "setIcon"):
                from PyQt6.QtGui import QIcon
                prev_btn.setIcon(QIcon())  # clear default icon
                prev_btn.setText("◀")
            if next_btn and hasattr(next_btn, "setIcon"):
                from PyQt6.QtGui import QIcon
                next_btn.setIcon(QIcon())
                next_btn.setText("▶")
        except Exception:
            pass
        if task and task.get("due_at"):
            try:
                dt = datetime.fromisoformat(task["due_at"])
                self.due_in.setDateTime(QDateTime(dt))
                self.has_due_cb.setChecked(True)
            except Exception:
                self.due_in.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        else:
            self.due_in.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        self.has_due_cb.toggled.connect(self.due_in.setEnabled)
        self.due_in.setEnabled(self.has_due_cb.isChecked())

        # Recurrence
        self.recur_in = QComboBox()
        self.recur_in.addItems(RECUR_OPTIONS)
        self.recur_in.setCurrentText(task.get("recurrence", RECUR_NONE) if task else RECUR_NONE)
        self.recur_in.currentTextChanged.connect(self._on_recur_changed)
        self.recur_in.setMinimumWidth(180)

        # "Every N" row
        every_row = QHBoxLayout(); every_row.setSpacing(8)
        every_row.addWidget(QLabel("Every"))
        self.interval_n_in = QSpinBox()
        self.interval_n_in.setRange(1, 365)
        self.interval_n_in.setValue(int(task.get("interval_n", 1)) if task else 1)
        self.interval_n_in.setMinimumWidth(80)
        self.interval_n_in.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        every_row.addWidget(self.interval_n_in)
        self.interval_unit_in = QComboBox()
        self.interval_unit_in.addItems(UNITS)
        self.interval_unit_in.setCurrentText(task.get("interval_unit", UNIT_DAYS) if task else UNIT_DAYS)
        self.interval_unit_in.setMinimumWidth(120)
        every_row.addWidget(self.interval_unit_in)
        every_row.addStretch()
        self.every_host = QWidget(); self.every_host.setLayout(every_row)

        form.addRow("Title", self.title_in)
        form.addRow("Notes", self.notes_in)
        form.addRow("URL", self.url_in)
        form.addRow("Priority", self.priority_in)
        form.addRow(self.has_due_cb)
        form.addRow("Due", self.due_in)
        form.addRow("Repeat", self.recur_in)
        # Store the label widget so we can show/hide it together with the row
        self._interval_label = QLabel("Interval")
        form.addRow(self._interval_label, self.every_host)

        self._on_recur_changed(self.recur_in.currentText())

        # Action buttons — with icons so they don't look like blank boxes
        btn_row = QHBoxLayout(); btn_row.addStretch(1)
        self.ok_btn = QPushButton("✓  Save")
        self.ok_btn.setProperty("primary", True)
        self.ok_btn.setMinimumWidth(110)
        self.ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("✕  Cancel")
        self.cancel_btn.setMinimumWidth(110)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.ok_btn)
        btn_host = QWidget(); btn_host.setLayout(btn_row)
        form.addRow(btn_host)

    def _on_recur_changed(self, value: str):
        show_interval = (value == RECUR_EVERY)
        # Show/hide both the label and the input host
        self.every_host.setVisible(show_interval)
        self._interval_label.setVisible(show_interval)
        # Recurrence implies there must be a due time — auto-tick it
        if value != RECUR_NONE and not self.has_due_cb.isChecked():
            self.has_due_cb.setChecked(True)

    def keyPressEvent(self, event):
        """Ctrl+Enter (or Cmd+Enter on Mac) saves even when focus is in a
        multi-line text field. Plain Enter only saves from single-line inputs
        (Qt does that automatically via default button)."""
        from PyQt6.QtCore import Qt as _Qt
        if event.key() in (_Qt.Key.Key_Return, _Qt.Key.Key_Enter):
            if event.modifiers() & _Qt.KeyboardModifier.ControlModifier:
                self.accept()
                return
        super().keyPressEvent(event)

    def value(self) -> dict:
        url = self.url_in.text().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        return {
            "id":            uuid.uuid4().hex,
            "title":         self.title_in.text().strip() or "Untitled",
            "notes":         self.notes_in.toPlainText().strip(),
            "url":           url,
            "priority":      self.priority_in.currentText(),
            "recurrence":    self.recur_in.currentText(),
            "interval_n":    self.interval_n_in.value(),
            "interval_unit": self.interval_unit_in.currentText(),
            "due_at":        self.due_in.dateTime().toPyDateTime().isoformat(timespec="seconds")
                              if self.has_due_cb.isChecked() else None,
            "completed":     False,
            "fired_at":      None,
        }


# ============================================================================
# Row widget
# ============================================================================
class TaskRow(QFrame):
    def __init__(self, task, on_toggle_complete, on_edit, on_delete, on_open_url, parent=None):
        super().__init__(parent)
        self.setObjectName("ItemRow")
        layout = QHBoxLayout(self); layout.setContentsMargins(10, 8, 10, 8); layout.setSpacing(10)

        cb = QCheckBox(); cb.setChecked(task.get("completed", False))
        cb.toggled.connect(lambda v: on_toggle_complete(task, v))
        layout.addWidget(cb)

        info_col = QVBoxLayout(); info_col.setSpacing(2)
        title_row = QHBoxLayout(); title_row.setSpacing(6)
        title = QLabel(task["title"])
        title.setObjectName("ItemName")
        if task.get("completed"):
            title.setStyleSheet("text-decoration: line-through; opacity: 0.6;")
        title_row.addWidget(title)
        prio = task.get("priority", "Normal")
        if prio == "High":
            pill = QLabel("HIGH"); pill.setStyleSheet(
                "background-color:#FEE2E2; color:#991B1B; padding:1px 6px; "
                "border-radius:3px; font-size:10px; font-weight:600;")
            title_row.addWidget(pill)
        elif prio == "Low":
            pill = QLabel("LOW"); pill.setStyleSheet(
                "background-color:#E5E7EB; color:#374151; padding:1px 6px; "
                "border-radius:3px; font-size:10px; font-weight:600;")
            title_row.addWidget(pill)
        title_row.addStretch()
        info_col.addLayout(title_row)

        meta_bits = []
        if task.get("due_at"):
            try:
                due = datetime.fromisoformat(task["due_at"])
                meta_bits.append(f"⏰ {due.strftime('%a %d %b · %H:%M')}")
            except Exception:
                pass
        recur = task.get("recurrence", RECUR_NONE)
        if recur == RECUR_EVERY:
            meta_bits.append(f"🔁 every {task.get('interval_n', 1)} {task.get('interval_unit', 'days')}")
        elif recur != RECUR_NONE:
            meta_bits.append(f"🔁 {recur.lower()}")
        if task.get("url"):
            meta_bits.append("🔗 link")
        if task.get("notes"):
            meta_bits.append(task["notes"][:60] + ("…" if len(task["notes"]) > 60 else ""))
        if meta_bits:
            meta = QLabel("  ·  ".join(meta_bits))
            meta.setProperty("class", "Muted")
            meta.setStyleSheet("font-size:11px;")
            info_col.addWidget(meta)
        layout.addLayout(info_col, 1)

        if task.get("url"):
            open_btn = QPushButton("↗  Open")
            open_btn.setProperty("ghost", True); open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            open_btn.clicked.connect(lambda: on_open_url(task))
            layout.addWidget(open_btn)

        more = QPushButton("⋯"); more.setProperty("ghost", True); more.setFixedWidth(28)
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self)
        a_edit = QAction("Edit…", self); a_edit.triggered.connect(lambda: on_edit(task))
        a_del  = QAction("Delete", self); a_del.triggered.connect(lambda: on_delete(task))
        menu.addAction(a_edit); menu.addSeparator(); menu.addAction(a_del)
        more.setMenu(menu)
        layout.addWidget(more)


# ============================================================================
# Module
# ============================================================================
class TasksModule(Module):
    MODULE_ID = "tasks"
    NAME = "Tasks"
    ICON = "✓"
    SECTION = "Tools"
    DESCRIPTION = "Unified to-do list + reminders. Recurring tasks supported."

    def setup_ui(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollContainer(self)

        header = SectionHeader(
            "Tasks",
            "Open-ended to-dos and time-based reminders in one place. "
            "Recurring tasks can repeat daily, weekly, or every N hours/days/weeks.",
            action_text="+  New task",
        )
        header.action_clicked.connect(self.add_task)
        scroll.add(header)

        # Filter & view toggles
        filter_card = Card()
        fl = QHBoxLayout(filter_card); fl.setContentsMargins(14, 10, 14, 10); fl.setSpacing(8)
        self.filter_in = QLineEdit(); self.filter_in.setPlaceholderText("Filter tasks…")
        self.filter_in.textChanged.connect(self._refresh)
        fl.addWidget(self.filter_in, 1)
        self.show_done_cb = QCheckBox("Show completed")
        self.show_done_cb.toggled.connect(self._refresh)
        fl.addWidget(self.show_done_cb)
        scroll.add(filter_card)

        # Pending list
        self.pending_card = Card()
        self.pending_layout = QVBoxLayout(self.pending_card)
        self.pending_layout.setContentsMargins(16, 12, 16, 12); self.pending_layout.setSpacing(4)
        scroll.add(self.pending_card)

        # Done list
        self.done_card = Card()
        self.done_layout = QVBoxLayout(self.done_card)
        self.done_layout.setContentsMargins(16, 12, 16, 12); self.done_layout.setSpacing(4)
        scroll.add(self.done_card)

        scroll.add_stretch()
        outer.addWidget(scroll)

        self._ensure_defaults()
        self._refresh()

        # Tick every 30s — same as Health
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(30_000)
        # Tick once immediately to fire anything that's overdue
        QTimer.singleShot(1500, self._tick)

    # ---------- Data ----------
    def _data(self) -> list[dict]:
        return self.ctx.storage.load("module_tasks", [])

    def _save(self, tasks):
        self.ctx.storage.save("module_tasks", tasks)

    def _ensure_defaults(self):
        existing = self._data()
        now = datetime.now()
        dirty = False

        # 1. Remove legacy IDs (replaced or no longer wanted as defaults)
        before = len(existing)
        existing = [t for t in existing if t.get("id") not in LEGACY_TASK_IDS_TO_REMOVE]
        if len(existing) != before:
            dirty = True

        # 2. Migrate old cab-logout title from "Book cab home" → "Logout cab time"
        # Also: backfill LOS task URL for installs that predate the URL default
        LOS_URL = "https://myworkspace-am.boehringer-ingelheim.com/Citrix/BIStore4Web"
        for t in existing:
            if t.get("id") == "cab-logout" and "Book cab home" in t.get("title", ""):
                t["title"] = "🚕 Logout cab time"
                t["notes"] = "Office cab leaves in a few minutes. Wrap up and head out."
                dirty = True
            if t.get("id") == "los-trainings" and not t.get("url"):
                # Only backfill if user hasn't customized this default
                if t.get("from_defaults") is not False:
                    t["url"] = LOS_URL
                    dirty = True

        # 3. Add any missing defaults (preserves the user's edits to existing ones)
        existing_ids = {t.get("id") for t in existing}
        for d in DEFAULT_TASKS:
            if d["id"] in existing_ids:
                continue
            t = dict(d)
            if t["id"] == "time-entry-friday":
                # Next Friday 17:00
                days_ahead = (4 - now.weekday()) % 7
                target = now + timedelta(days=days_ahead)
                target = target.replace(hour=17, minute=0, second=0, microsecond=0)
                if target <= now:
                    target = target + timedelta(days=7)
                t["due_at"] = target.isoformat(timespec="seconds")
            elif t["id"] == "cab-book-tomorrow":
                # Next weekday at 18:00
                target = now.replace(hour=18, minute=0, second=0, microsecond=0)
                while target.weekday() >= 5 or target <= now:
                    target = target + timedelta(days=1)
                    target = target.replace(hour=18, minute=0, second=0, microsecond=0)
                t["due_at"] = target.isoformat(timespec="seconds")
            elif t["id"] == "cab-logout":
                # Next weekday at 18:55
                target = now.replace(hour=18, minute=55, second=0, microsecond=0)
                while target.weekday() >= 5 or target <= now:
                    target = target + timedelta(days=1)
                    target = target.replace(hour=18, minute=55, second=0, microsecond=0)
                t["due_at"] = target.isoformat(timespec="seconds")
            elif t["id"] == "los-trainings":
                target = (now + timedelta(days=30)).replace(hour=10, minute=0, second=0, microsecond=0)
                t["due_at"] = target.isoformat(timespec="seconds")
            existing.append(t)
            dirty = True

        if dirty:
            self._save(existing)

    # ---------- Render ----------
    def _refresh(self):
        while self.pending_layout.count():
            it = self.pending_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        while self.done_layout.count():
            it = self.done_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()

        q = self.filter_in.text().lower().strip()
        all_tasks = self._data()

        def matches(t):
            if not q: return True
            return q in t.get("title", "").lower() or q in t.get("notes", "").lower()

        pending = [t for t in all_tasks if not t.get("completed") and matches(t)]
        done    = [t for t in all_tasks if t.get("completed") and matches(t)]

        # Sort pending: overdue first, then by due time (no-due last), then by priority
        def sort_key(t):
            prio_rank = {"High": 0, "Normal": 1, "Low": 2}.get(t.get("priority", "Normal"), 1)
            due = t.get("due_at")
            if due:
                try:
                    return (0, datetime.fromisoformat(due), prio_rank)
                except Exception:
                    pass
            return (1, datetime.max, prio_rank)
        pending.sort(key=sort_key)

        # Pending header
        h_lbl = QLabel(f"Pending  ·  {len(pending)}")
        h_lbl.setStyleSheet("font-size:13px; font-weight:600;")
        self.pending_layout.addWidget(h_lbl)

        if not pending:
            self.pending_layout.addWidget(EmptyState(
                "✓", "Nothing pending",
                "Click ‘+ New task’ to add one. Tasks with a due time will alert you when they're due."))
        else:
            for t in pending:
                self.pending_layout.addWidget(TaskRow(
                    t, self._on_toggle_complete, self.edit_task, self.delete_task, self._open_url))

        # Done section — visible only when show_done is on or there are some
        if self.show_done_cb.isChecked() and done:
            h2 = QLabel(f"Completed  ·  {len(done)}")
            h2.setStyleSheet("font-size:13px; font-weight:600; margin-top:8px;")
            self.done_layout.addWidget(h2)
            for t in done:
                self.done_layout.addWidget(TaskRow(
                    t, self._on_toggle_complete, self.edit_task, self.delete_task, self._open_url))
            self.done_card.show()
        else:
            self.done_card.hide()

    # ---------- Actions ----------
    def add_task(self):
        dlg = TaskDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            tasks = self._data(); tasks.append(dlg.value()); self._save(tasks); self._refresh()

    def edit_task(self, task):
        dlg = TaskDialog(self, task=task)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            tasks = self._data()
            for i, t in enumerate(tasks):
                if t.get("id") == task.get("id"):
                    new = dlg.value()
                    new["id"] = task["id"]
                    new["completed"] = t.get("completed", False)
                    new["fired_at"] = t.get("fired_at")
                    if t.get("from_defaults"):
                        new["from_defaults"] = True
                    tasks[i] = new; break
            self._save(tasks); self._refresh()

    def delete_task(self, task):
        if QMessageBox.question(self, "Delete task", f"Delete '{task['title']}'?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                == QMessageBox.StandardButton.Yes:
            tasks = [t for t in self._data() if t.get("id") != task.get("id")]
            self._save(tasks); self._refresh()

    def _on_toggle_complete(self, task, completed):
        tasks = self._data()
        for t in tasks:
            if t.get("id") == task.get("id"):
                t["completed"] = completed
                if completed:
                    # On completion of a recurring task, schedule the next due
                    if t.get("recurrence", RECUR_NONE) != RECUR_NONE:
                        next_due = self._next_due(t, base=datetime.now())
                        if next_due:
                            t["due_at"] = next_due.isoformat(timespec="seconds")
                            t["completed"] = False  # comes back to pending
                break
        self._save(tasks); self._refresh()

    def _open_url(self, task):
        url = task.get("url", "")
        if url:
            webbrowser.open(url)
            self.ctx.play_sound("click")

    # ---------- Recurrence math ----------
    def _next_due(self, task: dict, base: datetime) -> datetime | None:
        """Compute the next due_at after `base`, given recurrence rules."""
        recur = task.get("recurrence", RECUR_NONE)
        if recur == RECUR_NONE:
            return None
        try:
            prev = datetime.fromisoformat(task["due_at"]) if task.get("due_at") else base
        except Exception:
            prev = base
        anchor = max(prev, base)

        if recur == RECUR_DAILY:
            nxt = anchor + timedelta(days=1)
            return nxt.replace(hour=prev.hour, minute=prev.minute, second=0, microsecond=0)

        if recur == RECUR_WEEKDAYS:
            nxt = anchor + timedelta(days=1)
            while nxt.weekday() >= 5:  # skip Sat/Sun
                nxt += timedelta(days=1)
            return nxt.replace(hour=prev.hour, minute=prev.minute, second=0, microsecond=0)

        if recur == RECUR_WEEKLY:
            nxt = anchor + timedelta(weeks=1)
            return nxt.replace(hour=prev.hour, minute=prev.minute, second=0, microsecond=0)

        if recur == RECUR_EVERY:
            n = max(1, int(task.get("interval_n", 1)))
            unit = task.get("interval_unit", UNIT_DAYS)
            if unit == UNIT_HOURS:
                return anchor + timedelta(hours=n)
            if unit == UNIT_DAYS:
                nxt = anchor + timedelta(days=n)
                return nxt.replace(hour=prev.hour, minute=prev.minute, second=0, microsecond=0)
            if unit == UNIT_WORKDAYS:
                nxt = anchor
                added = 0
                while added < n:
                    nxt += timedelta(days=1)
                    if nxt.weekday() < 5:
                        added += 1
                return nxt.replace(hour=prev.hour, minute=prev.minute, second=0, microsecond=0)
            if unit == UNIT_WEEKS:
                nxt = anchor + timedelta(weeks=n)
                return nxt.replace(hour=prev.hour, minute=prev.minute, second=0, microsecond=0)
        return None

    # ---------- Tick — fire any task whose due time has passed ----------
    def _tick(self):
        now = datetime.now()
        tasks = self._data()
        dirty = False
        for t in tasks:
            if t.get("completed"): continue
            due_at = t.get("due_at")
            if not due_at: continue
            try:
                due = datetime.fromisoformat(due_at)
            except Exception:
                continue
            if now < due: continue

            # Have we already fired for this exact due time?
            already = t.get("fired_at")
            if already == due_at:
                continue

            # Fire — high priority reminders are more attention-grabbing
            is_high = t.get("priority", "Normal") == "High"
            title = f"📌 {t['title']}"
            if is_high:
                title = f"🔔🔔  {t['title']}"  # double-bell prefix for visual emphasis

            self.ctx.notify(title,
                            t.get("notes", "") or "Reminder.",
                            sound="reminder",
                            source="Tasks")

            # For high-priority, also flash the taskbar and play sound twice
            if is_high:
                try:
                    from PyQt6.QtWidgets import QApplication
                    main_win = QApplication.activeWindow()
                    if main_win:
                        main_win.activateWindow()
                        # Try to flash taskbar on Windows
                        if hasattr(main_win, "windowHandle"):
                            try:
                                main_win.show()
                                main_win.raise_()
                            except Exception:
                                pass
                except Exception:
                    pass
                # Replay sound after a short delay for emphasis
                try:
                    QTimer.singleShot(800, lambda: self.ctx.play_sound("reminder"))
                except Exception:
                    pass

            # If there's a URL, open it (skip for High — they often interrupt)
            # Actually keep it: URL is the action target.
            if t.get("url"):
                try: webbrowser.open(t["url"])
                except Exception: pass

            t["fired_at"] = due_at
            # If recurring, schedule next due
            if t.get("recurrence", RECUR_NONE) != RECUR_NONE:
                nxt = self._next_due(t, base=now)
                if nxt:
                    t["due_at"] = nxt.isoformat(timespec="seconds")
            dirty = True

        if dirty:
            self._save(tasks)
            self._refresh()

    # ---------- Search ----------
    def register_search(self):
        def provider(query: str):
            results = []
            for t in self._data():
                if t.get("completed"): continue
                score = fuzzy_score(query, t.get("title", ""))
                if score > 0.3:
                    tid = t["id"]
                    results.append(SearchResult(
                        title=t["title"], subtitle="Task", category="Tasks",
                        icon="✓",
                        action=lambda x=tid: self.ctx.navigate("tasks"),
                        score=score,
                    ))
            return results
        self.ctx.search.register("tasks", provider)

    def on_show(self):
        self._refresh()
