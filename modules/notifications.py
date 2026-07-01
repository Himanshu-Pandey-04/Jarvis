"""
Notifications panel. A history log of every notification any module has fired,
plus a Clear button. Modules write here automatically via ctx.notify(source=...).
"""
from datetime import datetime
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer

from modules.base import Module
from ui.widgets import SectionHeader, Card, EmptyState
from core.search import SearchResult, fuzzy_score


class NotificationsModule(Module):
    MODULE_ID = "notifications"
    NAME = "Notifications"
    ICON = "🔔"
    SECTION = "System"
    DESCRIPTION = "History of reminders, timers and other alerts."

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)

        header_row = QHBoxLayout()
        h = SectionHeader(
            "Notifications",
            "Everything WorkBench has nudged you about, in one place.",
        )
        header_row.addWidget(h, 1)
        outer.addLayout(header_row)

        # Action row
        actions = QHBoxLayout()
        self.unread_lbl = QLabel("")
        self.unread_lbl.setProperty("class", "Muted")
        actions.addWidget(self.unread_lbl)
        actions.addStretch()

        mark_btn = QPushButton("✓  Mark all as read")
        mark_btn.clicked.connect(self._mark_all_read)
        clear_btn = QPushButton("🗑  Clear all")
        clear_btn.setProperty("danger", True)
        clear_btn.clicked.connect(self._clear_all)
        actions.addWidget(mark_btn)
        actions.addWidget(clear_btn)
        outer.addLayout(actions)

        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        outer.addWidget(self.list_widget, 1)

        # Refresh periodically so items added by background timers show up
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(5_000)

        self._refresh()

    def _data(self) -> list[dict]:
        return self.ctx.storage.load("notifications_log", [])

    def _save(self, items: list[dict]):
        # Keep newest 500 only — don't let this grow unbounded.
        items = items[-500:]
        self.ctx.storage.save("notifications_log", items)

    def _refresh(self):
        items = list(reversed(self._data()))  # newest first
        self.list_widget.clear()

        unread = sum(1 for n in items if not n.get("read"))
        if items:
            self.unread_lbl.setText(f"{len(items)} total · {unread} unread")
        else:
            self.unread_lbl.setText("")

        if not items:
            li = QListWidgetItem("No notifications yet. Reminders and timers will land here.")
            li.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(li)
            return

        for n in items:
            unread_dot = "🔵 " if not n.get("read") else "   "
            source = n.get("source", "")
            try:
                when = datetime.fromisoformat(n.get("at", "")).strftime("%a %d %b · %H:%M")
            except (ValueError, TypeError):
                when = n.get("at", "")
            title = n.get("title", "(no title)")
            body = n.get("body", "")
            text = f"{unread_dot} {title}"
            if body:
                text += f"    ·   {body}"
            text += f"    ·   {source}    ·   {when}"
            li = QListWidgetItem(text)
            li.setData(Qt.ItemDataRole.UserRole, n)
            self.list_widget.addItem(li)

    def _on_item_clicked(self, list_item: QListWidgetItem):
        n = list_item.data(Qt.ItemDataRole.UserRole)
        if not n:
            return
        # Mark this single notification as read
        items = self._data()
        for it in items:
            if (it.get("at") == n.get("at") and it.get("title") == n.get("title")
                    and it.get("source") == n.get("source")):
                it["read"] = True
                break
        self._save(items)
        self._refresh()

    def _mark_all_read(self):
        items = self._data()
        for it in items:
            it["read"] = True
        self._save(items)
        self._refresh()

    def _clear_all(self):
        if not self._data():
            return
        if QMessageBox.question(self, "Clear notifications", "Delete all notification history?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                == QMessageBox.StandardButton.Yes:
            self._save([])
            self._refresh()

    def register_search(self):
        def provider(query: str) -> list[SearchResult]:
            results = []
            score = fuzzy_score(query, "notifications")
            if score > 0.4:
                results.append(SearchResult(
                    title="Open Notifications",
                    subtitle="See history of alerts",
                    category="Action",
                    icon="🔔",
                    action=lambda: self.ctx.navigate(self.MODULE_ID),
                    score=score,
                ))
            return results
        self.ctx.search.register("notifications", provider)

    def on_show(self):
        self._refresh()
