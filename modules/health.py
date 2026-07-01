"""
Health is Wealth — periodic wellness reminders.

Defaults (gently motivational, never bossy):
  • Water every 45 min
  • Stand up / move / look away from screen every 60 min
  • Lunch at 13:00
  • Snacks at 11:00 and 16:30
  • Avoid caffeine reminder at 17:00
  • Sleep reminder if still working after 21:00
  • Custom user-added reminders

State: each rule has last_fired timestamp. Tick on a QTimer every 30s.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QFrame,
    QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QTimeEdit, QComboBox,
    QMessageBox, QInputDialog, QCheckBox, QWidget, QMenu,
)
from PyQt6.QtCore import Qt, QTimer, QTime
from PyQt6.QtGui import QAction

from modules.base import Module
from ui.widgets import SectionHeader, Card, EmptyState, ScrollContainer


# ----------------------------------------------------------------------------
# Default rule definitions. Each has either a period (minutes) or a clock time.
# ----------------------------------------------------------------------------
DEFAULT_RULES = [
    {
        "id": "water-45",
        "icon": "💧", "name": "Sip some water",
        "message": "A few sips of water now keeps you sharp through the next stretch. You've got this.",
        "kind": "periodic", "every_minutes": 45,
        "active_from": "09:00", "active_to": "20:00",
        "enabled": True, "from_defaults": True,
    },
    {
        "id": "move-60",
        "icon": "🚶", "name": "Stand up and move",
        "message": "Roll your shoulders, look at something 20 feet away for 20 seconds. Future-you will thank you.",
        "kind": "periodic", "every_minutes": 60,
        "active_from": "09:00", "active_to": "20:00",
        "enabled": True, "from_defaults": True,
    },
    {
        "id": "eye-90",
        "icon": "👁",  "name": "Rest your eyes",
        "message": "20-20-20 rule: every 20 minutes, 20 feet away, for 20 seconds. Try one now.",
        "kind": "periodic", "every_minutes": 90,
        "active_from": "10:00", "active_to": "20:00",
        "enabled": True, "from_defaults": True,
    },
    {
        "id": "snack-am",
        "icon": "🍎", "name": "Mid-morning snack",
        "message": "Fruit, nuts, anything — fuel matters. Don't ride caffeine alone.",
        "kind": "daily_at", "at": "11:00",
        "enabled": True, "from_defaults": True,
    },
    {
        "id": "lunch",
        "icon": "🍱", "name": "Lunch time",
        "message": "Step away from the screen. Real food, real break. The work will be there when you're back.",
        "kind": "daily_at", "at": "13:00",
        "enabled": True, "from_defaults": True,
    },
    {
        "id": "snack-pm",
        "icon": "🥜", "name": "Afternoon snack",
        "message": "Energy dipping? A small snack now beats a sugar crash later.",
        "kind": "daily_at", "at": "16:30",
        "enabled": True, "from_defaults": True,
    },
    {
        "id": "caffeine-cutoff",
        "icon": "☕", "name": "Caffeine cutoff",
        "message": "Caffeine after 5 PM lingers and steals tonight's sleep. Switch to water or herbal tea?",
        "kind": "daily_at", "at": "17:00",
        "enabled": True, "from_defaults": True,
    },
    {
        "id": "sleep-soon",
        "icon": "🌙", "name": "Wind down soon",
        "message": "Still going at this hour? Aim for 8 hours of sleep — tomorrow's clarity starts tonight.",
        "kind": "daily_at", "at": "21:00",
        "enabled": True, "from_defaults": True,
    },
]


# ============================================================================
# Edit dialog
# ============================================================================
class HealthRuleDialog(QDialog):
    def __init__(self, parent=None, rule: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit reminder" if rule else "Add reminder")
        self.setMinimumWidth(440)

        form = QFormLayout(self)
        self.name_in    = QLineEdit(rule.get("name", "") if rule else "")
        self.icon_in    = QLineEdit(rule.get("icon", "🌱") if rule else "🌱"); self.icon_in.setMaxLength(4)
        self.message_in = QLineEdit(rule.get("message", "") if rule else "")
        self.message_in.setPlaceholderText("Encouraging message shown in the notification")

        self.kind_in = QComboBox(); self.kind_in.addItems(["Periodic (every N minutes)", "Daily at fixed time"])
        if rule and rule.get("kind") == "daily_at":
            self.kind_in.setCurrentIndex(1)

        self.every_in = QSpinBox(); self.every_in.setRange(5, 480); self.every_in.setSuffix(" min")
        self.every_in.setValue(int(rule.get("every_minutes", 60)) if rule else 60)

        self.at_in = QTimeEdit()
        if rule and rule.get("at"):
            self.at_in.setTime(QTime.fromString(rule["at"], "HH:mm"))
        else:
            self.at_in.setTime(QTime(13, 0))
        self.at_in.setDisplayFormat("HH:mm")

        self.from_in = QTimeEdit()
        self.from_in.setTime(QTime.fromString(rule.get("active_from", "09:00"), "HH:mm") if rule
                              else QTime(9, 0))
        self.from_in.setDisplayFormat("HH:mm")
        self.to_in = QTimeEdit()
        self.to_in.setTime(QTime.fromString(rule.get("active_to", "20:00"), "HH:mm") if rule
                            else QTime(20, 0))
        self.to_in.setDisplayFormat("HH:mm")

        form.addRow("Icon", self.icon_in)
        form.addRow("Name", self.name_in)
        form.addRow("Message", self.message_in)
        form.addRow("Type", self.kind_in)
        form.addRow("Every", self.every_in)
        form.addRow("At time", self.at_in)
        form.addRow("Active from", self.from_in)
        form.addRow("Active to", self.to_in)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def value(self) -> dict:
        kind = "daily_at" if self.kind_in.currentIndex() == 1 else "periodic"
        return {
            "id":            uuid.uuid4().hex,
            "icon":          self.icon_in.text().strip() or "🌱",
            "name":          self.name_in.text().strip() or "Reminder",
            "message":       self.message_in.text().strip() or "Time for a break!",
            "kind":          kind,
            "every_minutes": self.every_in.value(),
            "at":            self.at_in.time().toString("HH:mm"),
            "active_from":   self.from_in.time().toString("HH:mm"),
            "active_to":     self.to_in.time().toString("HH:mm"),
            "enabled":       True,
        }


# ============================================================================
# Row widget
# ============================================================================
class HealthRow(QFrame):
    def __init__(self, rule, on_toggle, on_edit, on_delete, on_test, parent=None):
        super().__init__(parent)
        self.setObjectName("ItemRow")
        layout = QHBoxLayout(self); layout.setContentsMargins(10, 8, 10, 8); layout.setSpacing(10)

        cb = QCheckBox(); cb.setChecked(rule.get("enabled", True))
        cb.toggled.connect(lambda v: on_toggle(rule, v))
        layout.addWidget(cb)

        icon = QLabel(rule.get("icon", "🌱")); icon.setObjectName("ItemIcon")
        layout.addWidget(icon)

        info = QVBoxLayout(); info.setSpacing(1)
        name = QLabel(rule["name"]); name.setObjectName("ItemName")
        info.addWidget(name)
        if rule.get("kind") == "periodic":
            schedule = f"Every {rule.get('every_minutes', 60)} min  ·  {rule.get('active_from', '09:00')}–{rule.get('active_to', '20:00')}"
        else:
            schedule = f"Daily at {rule.get('at', '13:00')}"
        sub = QLabel(schedule); sub.setProperty("class", "Muted")
        sub.setStyleSheet("font-size:11px;")
        info.addWidget(sub)
        layout.addLayout(info, 1)

        test_btn = QPushButton("▶  Test")
        test_btn.setProperty("ghost", True); test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.clicked.connect(lambda: on_test(rule))
        layout.addWidget(test_btn)

        more = QPushButton("⋯"); more.setProperty("ghost", True); more.setFixedWidth(28)
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self)
        a_edit = QAction("Edit…", self); a_edit.triggered.connect(lambda: on_edit(rule))
        a_del  = QAction("Delete", self); a_del.triggered.connect(lambda: on_delete(rule))
        menu.addAction(a_edit); menu.addSeparator(); menu.addAction(a_del)
        more.setMenu(menu)
        layout.addWidget(more)


# ============================================================================
# Module
# ============================================================================
class HealthModule(Module):
    MODULE_ID = "health"
    NAME = "Health is Wealth"
    ICON = "🌿"
    SECTION = "Tools"
    DESCRIPTION = "Gentle reminders for water, movement, meals, and sleep."

    def setup_ui(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollContainer(self)

        header = SectionHeader(
            "Health is Wealth",
            "Gentle wellness nudges throughout the day. Edit times to fit your routine.",
            action_text="+  Add reminder",
        )
        header.action_clicked.connect(self.add_rule)
        scroll.add(header)

        # Master enable
        toggle_card = Card()
        tl = QHBoxLayout(toggle_card); tl.setContentsMargins(20, 12, 20, 12)
        self.master_cb = QCheckBox("Enable wellness reminders")
        prefs = self.ctx.storage.load("preferences", {})
        self.master_cb.setChecked(prefs.get("health_master_enabled", True))
        self.master_cb.toggled.connect(self._on_master_toggled)
        tl.addWidget(self.master_cb); tl.addStretch()
        info = QLabel("Daily reminders persist after midnight; periodic ones repeat all day.")
        info.setProperty("class", "Muted")
        tl.addWidget(info)
        scroll.add(toggle_card)

        # Rules list
        self.list_card = Card()
        self.list_layout = QVBoxLayout(self.list_card)
        self.list_layout.setContentsMargins(16, 12, 16, 12); self.list_layout.setSpacing(4)
        scroll.add(self.list_card)

        scroll.add_stretch()
        outer.addWidget(scroll)

        # Seed defaults on first run
        self._ensure_defaults()
        self._refresh()

        # Tick timer
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(30_000)  # 30s

    # ---------- Storage ----------
    def _data(self) -> list[dict]:
        return self.ctx.storage.load("module_health", [])

    def _save(self, rules): self.ctx.storage.save("module_health", rules)

    def _ensure_defaults(self):
        """Seed default rules on first run; merge updates on subsequent runs.
        User edits to default rules are preserved (matched by id)."""
        existing = self._data()
        existing_ids = {r.get("id") for r in existing}
        added = False
        for d in DEFAULT_RULES:
            if d["id"] not in existing_ids:
                existing.append(dict(d))
                added = True
        if added:
            self._save(existing)

    # ---------- Render ----------
    def _refresh(self):
        while self.list_layout.count():
            it = self.list_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()

        rules = self._data()
        if not rules:
            self.list_layout.addWidget(EmptyState(
                "🌿", "No reminders yet",
                "Click ‘Add reminder’ to add one. Or wait — defaults will load on next launch."))
            return

        for r in rules:
            self.list_layout.addWidget(HealthRow(
                r,
                on_toggle=self._on_toggle_rule,
                on_edit=self.edit_rule,
                on_delete=self.delete_rule,
                on_test=self._test_rule,
            ))

    # ---------- Actions ----------
    def add_rule(self):
        dlg = HealthRuleDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            rules = self._data(); rules.append(dlg.value()); self._save(rules); self._refresh()

    def edit_rule(self, rule):
        dlg = HealthRuleDialog(self, rule=rule)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            rules = self._data()
            for i, r in enumerate(rules):
                if r.get("id") == rule.get("id"):
                    new = dlg.value(); new["id"] = rule["id"]
                    # preserve from_defaults
                    if r.get("from_defaults"):
                        new["from_defaults"] = True
                    rules[i] = new; break
            self._save(rules); self._refresh()

    def delete_rule(self, rule):
        if QMessageBox.question(self, "Delete reminder", f"Delete '{rule['name']}'?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                == QMessageBox.StandardButton.Yes:
            rules = [r for r in self._data() if r.get("id") != rule.get("id")]
            self._save(rules); self._refresh()

    def _on_toggle_rule(self, rule, enabled):
        rules = self._data()
        for r in rules:
            if r.get("id") == rule.get("id"):
                r["enabled"] = enabled
                break
        self._save(rules)

    def _test_rule(self, rule):
        self._fire(rule, test=True)

    def _on_master_toggled(self, enabled):
        prefs = self.ctx.storage.load("preferences", {})
        prefs["health_master_enabled"] = enabled
        self.ctx.storage.save("preferences", prefs)

    # ---------- Tick ----------
    def _tick(self):
        prefs = self.ctx.storage.load("preferences", {})
        if not prefs.get("health_master_enabled", True):
            return
        now = datetime.now()
        rules = self._data()
        dirty = False
        for rule in rules:
            if not rule.get("enabled", True): continue
            if not self._in_active_window(rule, now): continue

            try:
                last = datetime.fromisoformat(rule.get("last_fired", ""))
            except (ValueError, TypeError):
                last = None

            if rule.get("kind") == "periodic":
                period = max(5, int(rule.get("every_minutes", 60)))
                if not last or (now - last).total_seconds() >= period * 60:
                    self._fire(rule)
                    rule["last_fired"] = now.isoformat(timespec="seconds")
                    dirty = True
            else:  # daily_at
                try:
                    at_h, at_m = [int(x) for x in rule.get("at", "13:00").split(":")]
                except Exception:
                    continue
                scheduled = now.replace(hour=at_h, minute=at_m, second=0, microsecond=0)
                if now >= scheduled and (not last or last.date() < now.date() or last < scheduled):
                    self._fire(rule)
                    rule["last_fired"] = now.isoformat(timespec="seconds")
                    dirty = True
        if dirty:
            self._save(rules)

    def _in_active_window(self, rule, now):
        if rule.get("kind") != "periodic": return True
        try:
            f_h, f_m = [int(x) for x in rule.get("active_from", "09:00").split(":")]
            t_h, t_m = [int(x) for x in rule.get("active_to", "20:00").split(":")]
            start = dtime(f_h, f_m); end = dtime(t_h, t_m)
            return start <= now.time() <= end
        except Exception:
            return True

    def _fire(self, rule, test=False):
        prefix = "🧪 (test) " if test else ""
        self.ctx.notify(f"{rule.get('icon', '🌱')} {prefix}{rule['name']}",
                        rule.get("message", ""),
                        sound="reminder",
                        source="Health is Wealth")

    def on_show(self):
        self._refresh()
