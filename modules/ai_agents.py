"""
AI Agents — a curated launchpad for GenAI tools. Pinned as its own navbar page
because data folks hit these dozens of times a day.
"""
import webbrowser
from collections import OrderedDict

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame, QLineEdit,
    QDialog, QDialogButtonBox, QFormLayout, QComboBox, QMessageBox, QApplication,
    QMenu, QInputDialog, QWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction

from modules.base import Module
from ui.widgets import SectionHeader, Card, ScrollContainer, EmptyState
from core.search import SearchResult, fuzzy_score


DEFAULT_GROUPS = ["Chat", "Coding", "Search", "Research", "Image", "Video", "Audio"]


class AIAgentDialog(QDialog):
    def __init__(self, parent=None, item=None, groups=None):
        super().__init__(parent)
        self.setWindowTitle("Edit AI agent" if item else "Add AI agent")
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        self.name_in = QLineEdit(item["name"] if item else "")
        self.url_in  = QLineEdit(item["url"] if item else "")
        self.url_in.setPlaceholderText("https://...")
        self.icon_in = QLineEdit(item.get("icon", "🤖") if item else "🤖"); self.icon_in.setMaxLength(4)
        self.cat_in  = QComboBox(); self.cat_in.setEditable(True)
        self.cat_in.addItems(groups or DEFAULT_GROUPS)
        if item: self.cat_in.setCurrentText(item.get("category", "Chat"))
        self.notes_in = QLineEdit(item.get("notes", "") if item else "")

        form.addRow("Name", self.name_in)
        form.addRow("URL", self.url_in)
        form.addRow("Icon", self.icon_in)
        form.addRow("Group", self.cat_in)
        form.addRow("Notes", self.notes_in)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def value(self):
        url = self.url_in.text().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        return {
            "name":     self.name_in.text().strip() or "Untitled",
            "url":      url,
            "icon":     self.icon_in.text().strip() or "🤖",
            "category": self.cat_in.currentText().strip() or "Chat",
            "notes":    self.notes_in.text().strip(),
        }


class AgentTile(QFrame):
    """A larger clickable tile for an AI agent."""
    def __init__(self, item, on_open, on_edit, on_delete, on_move, parent=None):
        super().__init__(parent)
        self.setObjectName("PinTile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(96)
        self.item = item; self.on_open = on_open
        _tip = item["name"]
        if item.get("url"): _tip += "\n" + item["url"]
        if item.get("notes"): _tip += "\n\n" + item["notes"]
        self.setToolTip(_tip)

        layout = QVBoxLayout(self); layout.setContentsMargins(14, 10, 14, 10); layout.setSpacing(3)
        top = QHBoxLayout()
        icon = QLabel(item.get("icon", "🤖")); icon.setObjectName("PinTileIcon")
        top.addWidget(icon); top.addStretch()

        # Three-dot menu
        more = QPushButton("⋯"); more.setProperty("ghost", True); more.setFixedWidth(24)
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        m = QMenu(self)
        a_edit = QAction("Edit…", self); a_edit.triggered.connect(lambda: on_edit(item))
        a_move = QAction("Move to group…", self); a_move.triggered.connect(lambda: on_move(item))
        a_del  = QAction("Delete", self); a_del.triggered.connect(lambda: on_delete(item))
        m.addAction(a_edit); m.addAction(a_move); m.addSeparator(); m.addAction(a_del)
        more.setMenu(m)
        top.addWidget(more)
        layout.addLayout(top)

        name = QLabel(item["name"]); name.setObjectName("PinTileName")
        name.setToolTip(item.get("url", ""))
        layout.addWidget(name)

        notes = item.get("notes", "")
        if notes:
            n = QLabel(notes); n.setObjectName("PinTileKind"); n.setWordWrap(True)
            layout.addWidget(n)
        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_open(self.item)
        super().mousePressEvent(event)


class AIAgentsModule(Module):
    MODULE_ID = "ai_agents"
    NAME = "AI Agents"
    ICON = "🤖"
    SECTION = "Workspace"
    DESCRIPTION = "GenAI tools — Copilot, ChatGPT, Claude, and more."

    # Note: this module uses its own storage key, not module_ai_agents which is
    # already used. Override load/save:
    def load_data(self, default=None):
        return self.ctx.storage.load("module_ai_agents", default if default is not None else [])

    def save_data(self, data):
        self.ctx.storage.save("module_ai_agents", data)

    def setup_ui(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollContainer(self)

        header = SectionHeader(
            "AI Agents",
            "GenAI tools at your fingertips. Click a tile to open in your browser.",
            action_text="+  Add agent",
        )
        header.action_clicked.connect(self.add_agent)
        scroll.add(header)

        # Filter
        filter_card = Card()
        fl = QHBoxLayout(filter_card); fl.setContentsMargins(14, 10, 14, 10); fl.setSpacing(8)
        self.filter_in = QLineEdit(); self.filter_in.setPlaceholderText("Filter agents…")
        self.filter_in.textChanged.connect(self._refresh)
        fl.addWidget(self.filter_in, 1)
        new_group_btn = QPushButton("➕  New group")
        new_group_btn.clicked.connect(self._create_group)
        fl.addWidget(new_group_btn)
        scroll.add(filter_card)

        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0); self.cards_layout.setSpacing(14)
        scroll.add(self.cards_host)

        scroll.add_stretch()
        outer.addWidget(scroll)
        self._refresh()

    def _data(self): return self.load_data(default=[])
    def _save(self, items): self.save_data(items)

    def _all_groups(self):
        used = sorted({i.get("category", "Chat") for i in self._data()})
        return list(dict.fromkeys(used + DEFAULT_GROUPS))

    def _refresh(self):
        while self.cards_layout.count():
            it = self.cards_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()

        items = self._data()
        q = self.filter_in.text().lower().strip()
        if q:
            items = [it for it in items
                     if q in it["name"].lower()
                     or q in it.get("category", "").lower()
                     or q in it.get("notes", "").lower()]

        if not items:
            self.cards_layout.addWidget(EmptyState(
                "🤖", "No agents yet",
                "Click ‘Add agent’ to add a GenAI tool you use. Group by purpose (Chat, Coding, Research…)."))
            return

        groups = OrderedDict()
        for it in items:
            groups.setdefault(it.get("category", "Chat"), []).append(it)

        for group_name, group_items in groups.items():
            self.cards_layout.addWidget(self._build_group_card(group_name, group_items))

    def _build_group_card(self, group, items):
        card = QFrame(); card.setObjectName("GroupCard")
        layout = QVBoxLayout(card); layout.setContentsMargins(16, 14, 16, 14); layout.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel(group); title.setObjectName("GroupTitle")
        head.addWidget(title)
        count = QLabel(f"{len(items)} item{'s' if len(items) != 1 else ''}")
        count.setObjectName("GroupCount")
        head.addWidget(count); head.addStretch()
        rename_btn = QPushButton("✎  Rename"); rename_btn.setProperty("ghost", True)
        rename_btn.clicked.connect(lambda _=False, g=group: self._rename_group(g))
        head.addWidget(rename_btn)
        layout.addLayout(head)

        # Grid of tiles
        grid_host = QWidget()
        grid = QGridLayout(grid_host); grid.setSpacing(10); grid.setContentsMargins(0, 0, 0, 0)
        cols = 3
        for i, it in enumerate(items):
            tile = AgentTile(it,
                             on_open=self._open_agent,
                             on_edit=self.edit_agent,
                             on_delete=self.delete_agent,
                             on_move=self._move_to_group)
            grid.addWidget(tile, i // cols, i % cols)
        # Fill empty cells
        for c in range(cols):
            grid.setColumnStretch(c, 1)
        layout.addWidget(grid_host)
        return card

    def _open_agent(self, item):
        self.ctx.play_sound("click")
        try:
            webbrowser.open(item["url"])
        except Exception as e:
            self.ctx.notify("Couldn't open", str(e), sound="error")

    def add_agent(self):
        dlg = AIAgentDialog(self, groups=self._all_groups())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = self._data(); data.append(dlg.value()); self._save(data); self._refresh()

    def edit_agent(self, item):
        dlg = AIAgentDialog(self, item=item, groups=self._all_groups())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = self._data()
            for i, it in enumerate(data):
                if it.get("url") == item.get("url") and it.get("name") == item.get("name"):
                    new = dlg.value()
                    # User edited this — preserve identity but mark as user-owned
                    if it.get("default_key"):
                        new["default_key"] = it["default_key"]
                    new["from_defaults"] = False
                    data[i] = new; break
            self._save(data); self._refresh()

    def delete_agent(self, item):
        if QMessageBox.question(self, "Delete", f"Remove '{item['name']}'?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                == QMessageBox.StandardButton.Yes:
            data = [i for i in self._data()
                    if not (i.get("url") == item.get("url") and i.get("name") == item.get("name"))]
            self._save(data); self._refresh()

    def _move_to_group(self, item):
        groups = self._all_groups()
        choice, ok = QInputDialog.getItem(self, "Move to group",
                                          f"Move '{item['name']}' to:",
                                          groups + ["+ New group…"], 0, False)
        if not ok: return
        if choice == "+ New group…":
            new_name, ok = QInputDialog.getText(self, "New group", "Group name:")
            if not ok or not new_name.strip(): return
            choice = new_name.strip()
        data = self._data()
        for it in data:
            if it.get("url") == item.get("url") and it.get("name") == item.get("name"):
                it["category"] = choice; break
        self._save(data); self._refresh()

    def _create_group(self):
        new_name, ok = QInputDialog.getText(self, "New group", "Group name:")
        if not ok or not new_name.strip(): return
        self.ctx.notify("Group ready",
                        f"‘{new_name.strip()}’ is selectable when you add or move an agent.",
                        sound="success")

    def _rename_group(self, old):
        new_name, ok = QInputDialog.getText(self, "Rename group",
                                             f"New name for ‘{old}’:", text=old)
        if not ok or not new_name.strip() or new_name.strip() == old: return
        new = new_name.strip()
        data = self._data()
        for it in data:
            if it.get("category") == old:
                it["category"] = new
        self._save(data); self._refresh()

    def register_search(self):
        def provider(query: str):
            results = []
            for it in self._data():
                score = max(fuzzy_score(query, it.get("name", "")),
                            fuzzy_score(query, it.get("category", "")) * 0.6)
                if score > 0.25:
                    item_ref = it
                    results.append(SearchResult(
                        title=it["name"], subtitle=it.get("category", ""), category="AI Agent",
                        icon=it.get("icon", "🤖"),
                        action=lambda x=item_ref: self._open_agent(x),
                        score=score,
                    ))
            return results
        self.ctx.search.register("ai_agents", provider)

    def on_show(self): self._refresh()
