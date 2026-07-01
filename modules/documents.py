"""
Documents and applications. Stores paths to files, folders, apps, and URLs
(kind=url) the user wants quick access to. Click → open with the OS default
handler for files, browser for URLs. Group-card layout — like Links.
"""
import os
import subprocess
import webbrowser
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QFileDialog, QFrame,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox, QComboBox, QMessageBox,
    QMenu, QApplication, QFormLayout, QInputDialog, QWidget, QCheckBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCursor

from modules.base import Module
from ui.widgets import SectionHeader, Card, ScrollContainer, EmptyState
from core.search import SearchResult, fuzzy_score

DEFAULT_GROUPS = ["Documents", "Spreadsheets", "Presentations", "Apps",
                  "Folders", "Essential Documents", "Other"]


def open_path(path: str, kind: str = ""):
    """OS-aware default opener. URL kind opens in browser; everything else uses OS default."""
    try:
        if kind == "url" or path.startswith(("http://", "https://")):
            webbrowser.open(path)
            return True
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif os.uname().sysname == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


# ============================================================================
# Edit dialog
# ============================================================================
class DocumentDialog(QDialog):
    def __init__(self, parent=None, doc: dict | None = None, groups: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit document" if doc else "Add document, app, or URL")
        self.setMinimumWidth(540)

        form = QFormLayout(self)
        self.name_in = QLineEdit(doc["name"] if doc else "")

        # Kind selector
        self.kind_in = QComboBox(); self.kind_in.addItems(["File / folder / app", "URL (web link)"])
        if doc and doc.get("kind") == "url":
            self.kind_in.setCurrentIndex(1)

        path_row = QHBoxLayout()
        self.path_in = QLineEdit(doc["path"] if doc else "")
        self.path_in.setPlaceholderText(r"C:\Users\You\Documents\report.xlsx  or  https://example.com")
        browse_file = QPushButton("📁  File…");   browse_file.clicked.connect(self._pick_file)
        browse_dir  = QPushButton("📂  Folder…"); browse_dir.clicked.connect(self._pick_dir)
        path_row.addWidget(self.path_in, 1)
        path_row.addWidget(browse_file); path_row.addWidget(browse_dir)

        self.icon_in = QLineEdit(doc.get("icon", "📄") if doc else "📄"); self.icon_in.setMaxLength(4)
        self.cat_in = QComboBox(); self.cat_in.setEditable(True)
        self.cat_in.addItems(groups or DEFAULT_GROUPS)
        if doc:
            self.cat_in.setCurrentText(doc.get("category", "Documents"))
        self.cred_in = QLineEdit(doc.get("cred_ref", "") if doc else "")
        self.cred_in.setPlaceholderText("Optional — vault entry to copy on open (e.g. PC, BI)")

        form.addRow("Name", self.name_in)
        form.addRow("Kind", self.kind_in)
        form.addRow("Path or URL", path_row)
        form.addRow("Icon", self.icon_in)
        form.addRow("Group", self.cat_in)
        form.addRow("Associated credentials", self.cred_in)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a file or app")
        if path:
            self.path_in.setText(path)
            if not self.name_in.text():
                self.name_in.setText(os.path.basename(path))
            self.kind_in.setCurrentIndex(0)

    def _pick_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a folder")
        if path:
            self.path_in.setText(path)
            if not self.name_in.text():
                self.name_in.setText(os.path.basename(path) or path)
            self.kind_in.setCurrentIndex(0)

    def value(self) -> dict:
        kind = "url" if self.kind_in.currentIndex() == 1 else "file"
        path = self.path_in.text().strip()
        if kind == "url" and path and not (path.startswith("http://") or path.startswith("https://")):
            path = "https://" + path
        return {
            "name":     self.name_in.text().strip() or "Untitled",
            "path":     path,
            "icon":     self.icon_in.text().strip() or ("🌐" if kind == "url" else "📄"),
            "category": self.cat_in.currentText().strip() or "Documents",
            "kind":     kind,
            "cred_ref": self.cred_in.text().strip(),
        }


# ============================================================================
# Per-document row
# ============================================================================
class DocRow(QFrame):
    def __init__(self, item, on_open, on_copy, on_edit, on_delete, on_pin, on_move_group, parent=None):
        super().__init__(parent)
        self.setObjectName("ItemRow")
        layout = QHBoxLayout(self); layout.setContentsMargins(10, 6, 10, 6); layout.setSpacing(8)

        icon = QLabel(item.get("icon", "📄")); icon.setObjectName("ItemIcon")
        layout.addWidget(icon)
        name = QLabel(item["name"]); name.setObjectName("ItemName")
        name.setToolTip(item.get("path", ""))
        if item.get("cred_ref"):
            name.setText(f"{item['name']}   🔑")
        # Show "missing" indicator only for files (not URLs)
        if item.get("kind") != "url" and item.get("path") and not os.path.exists(item["path"]):
            name.setText(name.text() + "    ⚠")
            name.setToolTip(name.toolTip() + "  ·  file not found")
        layout.addWidget(name, 1)

        copy_btn = QPushButton("📋  Copy")
        copy_btn.setProperty("ghost", True); copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setToolTip("Copy path / URL to clipboard")
        copy_btn.clicked.connect(lambda: on_copy(item))
        layout.addWidget(copy_btn)

        open_btn = QPushButton("↗  Open")
        open_btn.setProperty("primary", True); open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(lambda: on_open(item))
        layout.addWidget(open_btn)

        more_btn = QPushButton("⋯"); more_btn.setProperty("ghost", True); more_btn.setFixedWidth(28)
        more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self)
        a_pin = QAction("Pin to dashboard", self); a_pin.triggered.connect(lambda: on_pin(item))
        a_move = QAction("Move to group…", self); a_move.triggered.connect(lambda: on_move_group(item))
        a_edit = QAction("Edit…", self); a_edit.triggered.connect(lambda: on_edit(item))
        a_del = QAction("Delete", self); a_del.triggered.connect(lambda: on_delete(item))
        for a in (a_pin, a_move): menu.addAction(a)
        menu.addSeparator(); menu.addAction(a_edit); menu.addAction(a_del)
        more_btn.setMenu(menu)
        layout.addWidget(more_btn)


# ============================================================================
# Module
# ============================================================================
class DocumentsModule(Module):
    MODULE_ID = "documents"
    NAME = "Documents"
    ICON = "📂"
    SECTION = "Workspace"
    DESCRIPTION = "Files, folders, apps, and essential URLs — grouped into cards."

    def setup_ui(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)

        # State for bulk selection
        self._selected: set = set()
        self._select_mode: bool = False

        scroll = ScrollContainer(self)

        header = SectionHeader(
            "Documents & Apps",
            "Grouped into cards. Each item gives Copy and Open. "
            "Move items between groups via the ⋯ menu.",
            action_text="+  Add item",
        )
        header.action_clicked.connect(self.add_doc)
        scroll.add(header)

        # Filter + selection toggle + new group
        filter_card = Card()
        fl = QHBoxLayout(filter_card); fl.setContentsMargins(14, 10, 14, 10); fl.setSpacing(8)
        self.filter_in = QLineEdit(); self.filter_in.setPlaceholderText("Filter…")
        self.filter_in.textChanged.connect(self._refresh)
        fl.addWidget(self.filter_in, 1)
        self.select_btn = QPushButton("☑  Select")
        self.select_btn.setCheckable(True)
        self.select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_btn.setToolTip("Toggle multi-select mode for bulk move/delete")
        self.select_btn.toggled.connect(self._on_select_toggled)
        fl.addWidget(self.select_btn)
        new_group_btn = QPushButton("➕  New group")
        new_group_btn.clicked.connect(self._create_group)
        fl.addWidget(new_group_btn)
        scroll.add(filter_card)

        # Bulk action bar
        self.bulk_bar = Card(); self.bulk_bar.setVisible(False)
        bb = QHBoxLayout(self.bulk_bar); bb.setContentsMargins(14, 8, 14, 8); bb.setSpacing(8)
        self.bulk_count_lbl = QLabel("0 selected")
        self.bulk_count_lbl.setStyleSheet("font-weight:600;")
        bb.addWidget(self.bulk_count_lbl); bb.addStretch()
        bulk_move_btn = QPushButton("📦  Move to…")
        bulk_move_btn.clicked.connect(self._bulk_move)
        bb.addWidget(bulk_move_btn)
        bulk_del_btn = QPushButton("🗑  Delete")
        bulk_del_btn.setProperty("danger", True)
        bulk_del_btn.clicked.connect(self._bulk_delete)
        bb.addWidget(bulk_del_btn)
        bulk_clear_btn = QPushButton("✕  Clear")
        bulk_clear_btn.setProperty("ghost", True)
        bulk_clear_btn.clicked.connect(self._bulk_clear)
        bb.addWidget(bulk_clear_btn)
        scroll.add(self.bulk_bar)

        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0); self.cards_layout.setSpacing(14)
        scroll.add(self.cards_host)

        scroll.add_stretch()
        outer.addWidget(scroll)
        self._refresh()

    # ---------- Selection helpers ----------
    def _key_of(self, item: dict) -> tuple:
        return (item.get("name", ""), item.get("path", ""))

    def _on_select_toggled(self, on: bool):
        self._select_mode = on
        if on:
            self.select_btn.setText("☑  Selecting…")
        else:
            self.select_btn.setText("☑  Select")
            self._selected.clear()
        self._refresh()

    def _toggle_selected(self, item: dict, checked: bool):
        k = self._key_of(item)
        if checked: self._selected.add(k)
        else: self._selected.discard(k)
        self._update_bulk_bar()

    def _update_bulk_bar(self):
        n = len(self._selected)
        self.bulk_bar.setVisible(self._select_mode and n > 0)
        self.bulk_count_lbl.setText(f"{n} selected")

    def _bulk_clear(self):
        self._selected.clear(); self._update_bulk_bar(); self._refresh()

    def _bulk_move(self):
        if not self._selected: return
        groups = self._all_groups()
        choice, ok = QInputDialog.getItem(self, "Move selected",
                                           f"Move {len(self._selected)} item(s) to:",
                                           groups, 0, False)
        if not ok or not choice: return
        data = self._data(); moved = 0
        for it in data:
            if self._key_of(it) in self._selected:
                it["category"] = choice; moved += 1
        self._save(data); self._selected.clear()
        self.ctx.notify("Items moved", f"{moved} item(s) → ‘{choice}’",
                        sound="success", source="Documents", user_initiated=True)
        self._refresh()

    def _bulk_delete(self):
        if not self._selected: return
        n = len(self._selected)
        if QMessageBox.question(self, "Delete selected",
                                 f"Delete {n} item(s)? This can't be undone."
                                 ) != QMessageBox.StandardButton.Yes:
            return
        data = [it for it in self._data() if self._key_of(it) not in self._selected]
        self._save(data); self._selected.clear()
        self.ctx.notify("Items deleted", f"Removed {n} item(s).",
                        sound="success", source="Documents", user_initiated=True)
        self._refresh()

    def _data(self):
        items = self.load_data(default=[])
        for it in items:
            it.setdefault("kind", "file")
            it.setdefault("cred_ref", "")
        return items

    def _save(self, items): self.save_data(items)

    def _user_groups(self) -> list[str]:
        return self.ctx.storage.load("module_documents_user_groups", []) or []

    def _save_user_groups(self, groups: list[str]):
        self.ctx.storage.save("module_documents_user_groups",
                              list(dict.fromkeys([g for g in groups if g])))

    def _all_groups(self) -> list[str]:
        used = [i.get("category", "Documents") for i in self._data()]
        return list(dict.fromkeys(used + self._user_groups() + DEFAULT_GROUPS))

    def _refresh(self):
        while self.cards_layout.count():
            it = self.cards_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()

        items = self._data()
        q = self.filter_in.text().lower().strip()
        if q:
            items = [it for it in items
                     if q in it["name"].lower()
                     or q in it.get("path", "").lower()
                     or q in it.get("category", "").lower()]

        from collections import OrderedDict
        groups: "OrderedDict[str, list[dict]]" = OrderedDict()
        for it in items:
            groups.setdefault(it.get("category", "Documents"), []).append(it)
        # Show empty user-groups too
        if not q:
            for g in self._user_groups():
                groups.setdefault(g, [])

        if not items and not groups:
            empty = EmptyState(
                "📂", "No items yet",
                "Click ‘Add item’ to add a file, folder, app, or URL. "
                "Group them by purpose (e.g. ‘Essential Documents’).")
            self.cards_layout.addWidget(empty)
            return

        self._update_bulk_bar()

        for group_name, group_items in groups.items():
            self.cards_layout.addWidget(self._build_group_card(group_name, group_items))

    def _build_group_card(self, group: str, items: list[dict]) -> QFrame:
        card = QFrame(); card.setObjectName("GroupCard")
        layout = QVBoxLayout(card); layout.setContentsMargins(16, 14, 16, 14); layout.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel(group); title.setObjectName("GroupTitle")
        head.addWidget(title)
        count = QLabel(f"{len(items)} item{'s' if len(items) != 1 else ''}")
        count.setObjectName("GroupCount")
        head.addWidget(count); head.addStretch()

        if self._select_mode and items:
            select_all_btn = QPushButton("☑ All")
            select_all_btn.setProperty("ghost", True)
            select_all_btn.setToolTip("Select all in this group")
            select_all_btn.clicked.connect(lambda _=False, its=items: self._select_all_in(its))
            head.addWidget(select_all_btn)

        rename_btn = QPushButton("✎  Rename"); rename_btn.setProperty("ghost", True)
        rename_btn.clicked.connect(lambda _=False, g=group: self._rename_group(g))
        head.addWidget(rename_btn)

        del_btn = QPushButton("🗑  Delete group")
        del_btn.setProperty("ghost", True)
        del_btn.setStyleSheet("color: #DC2626;")
        del_btn.setToolTip("Delete this group (and any items in it)")
        del_btn.clicked.connect(lambda _=False, g=group: self._delete_group(g))
        head.addWidget(del_btn)
        layout.addLayout(head)

        if not items:
            empty_lbl = QLabel("No items here yet. Add or move items into this group.")
            empty_lbl.setProperty("class", "Muted")
            empty_lbl.setStyleSheet("padding: 10px 4px; font-style: italic;")
            layout.addWidget(empty_lbl)
            return card

        for it in items:
            row = self._build_doc_row(it)
            layout.addWidget(row)
        return card

    def _build_doc_row(self, it: dict) -> QWidget:
        """Either a normal DocRow or a checkbox-wrapped row in select mode."""
        if not self._select_mode:
            return DocRow(it,
                          on_open=self._open_doc,
                          on_copy=self._copy_path,
                          on_edit=self.edit_doc,
                          on_delete=self.delete_doc,
                          on_pin=self._pin,
                          on_move_group=self._move_to_group)
        # Select mode: wrap with a checkbox at the front
        wrapper = QFrame(); wrapper.setObjectName("ItemRow")
        wl = QHBoxLayout(wrapper); wl.setContentsMargins(8, 4, 4, 4); wl.setSpacing(6)
        cb = QCheckBox()
        cb.setChecked(self._key_of(it) in self._selected)
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.toggled.connect(lambda v, item=it: self._toggle_selected(item, v))
        wl.addWidget(cb)
        inner = DocRow(it,
                       on_open=self._open_doc,
                       on_copy=self._copy_path,
                       on_edit=self.edit_doc,
                       on_delete=self.delete_doc,
                       on_pin=self._pin,
                       on_move_group=self._move_to_group)
        wl.addWidget(inner, 1)
        return wrapper

    def _select_all_in(self, items: list[dict]):
        for it in items:
            self._selected.add(self._key_of(it))
        self._update_bulk_bar()
        self._refresh()

    # ---------- Actions ----------
    def _open_doc(self, item):
        self.ctx.play_sound("click")
        if not item.get("path"):
            self.ctx.notify("No path", item.get("name", ""), sound="error"); return
        if not open_path(item["path"], item.get("kind", "file")):
            self.ctx.notify("Couldn't open", item.get("path", ""), sound="error")
            return
        cred = (item.get("cred_ref") or "").strip()
        if cred:
            self.ctx.copy_password_with_restore(cred, restore_after=60)

    def _copy_path(self, item):
        QApplication.clipboard().setText(item.get("path", ""))
        self.ctx.notify("Copied to clipboard", item.get("name", ""), sound="success", user_initiated=True)

    def add_doc(self):
        dlg = DocumentDialog(self, groups=self._all_groups())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = self._data(); data.append(dlg.value()); self._save(data); self._refresh()

    def edit_doc(self, item):
        dlg = DocumentDialog(self, doc=item, groups=self._all_groups())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = self._data()
            for i, it in enumerate(data):
                if it.get("path") == item.get("path") and it.get("name") == item.get("name"):
                    new = dlg.value()
                    if it.get("default_key"):
                        new["default_key"] = it["default_key"]
                    new["from_defaults"] = False
                    data[i] = new; break
            self._save(data); self._refresh()

    def delete_doc(self, item):
        if QMessageBox.question(self, "Delete", f"Remove shortcut to '{item['name']}'?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                == QMessageBox.StandardButton.Yes:
            data = [i for i in self._data()
                    if not (i.get("path") == item.get("path") and i.get("name") == item.get("name"))]
            self._save(data); self._refresh()

    def _pin(self, item):
        kind = "app" if item.get("category") == "Apps" else ("link" if item.get("kind") == "url" else "document")
        pins = self.ctx.storage.load("pinned_items", [])
        if any(p.get("kind") == kind and p.get("ref") == item["path"] for p in pins):
            self.ctx.notify("Already pinned", item["name"]); return
        pins.append({"kind": kind, "ref": item["path"], "name": item["name"],
                     "icon": item.get("icon", "📄")})
        self.ctx.storage.save("pinned_items", pins)
        self.ctx.notify("Pinned to dashboard", item["name"], sound="success", user_initiated=True)

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
            if it.get("path") == item.get("path") and it.get("name") == item.get("name"):
                it["category"] = choice; break
        self._save(data); self._refresh()

    def _create_group(self):
        new_name, ok = QInputDialog.getText(self, "New group", "Group name:")
        if not ok or not new_name.strip(): return
        new_name = new_name.strip()
        if new_name in self._all_groups():
            self.ctx.notify("Group exists",
                            f"‘{new_name}’ already exists.",
                            sound="warning", source="Documents")
            return
        groups = self._user_groups(); groups.append(new_name)
        self._save_user_groups(groups)
        self.ctx.notify("Group created",
                        f"‘{new_name}’ is ready. Add or move items here.",
                        sound="success", source="Documents", user_initiated=True)
        self._refresh()

    def _rename_group(self, old: str):
        new_name, ok = QInputDialog.getText(self, "Rename group",
                                             f"New name for ‘{old}’:", text=old)
        if not ok or not new_name.strip() or new_name.strip() == old: return
        new = new_name.strip()
        data = self._data()
        for it in data:
            if it.get("category") == old:
                it["category"] = new
        self._save(data)
        groups = [new if g == old else g for g in self._user_groups()]
        self._save_user_groups(groups)
        self._refresh()

    def _delete_group(self, group: str):
        items = [it for it in self._data() if it.get("category") == group]
        msg = (f"Delete group ‘{group}’?\n\n"
               f"{len(items)} item(s) will also be deleted." if items
               else f"Delete empty group ‘{group}’?")
        if QMessageBox.question(self, "Delete group", msg) != QMessageBox.StandardButton.Yes:
            return
        if items:
            data = [it for it in self._data() if it.get("category") != group]
            self._save(data)
        groups = [g for g in self._user_groups() if g != group]
        self._save_user_groups(groups)
        self.ctx.notify("Group deleted",
                        f"‘{group}’ removed" + (f" along with {len(items)} item(s)." if items else "."),
                        sound="success", source="Documents", user_initiated=True)
        self._refresh()

    # ---------- Search ----------
    def register_search(self):
        def provider(query: str) -> list[SearchResult]:
            results = []
            for it in self._data():
                score = max(
                    fuzzy_score(query, it.get("name", "")),
                    fuzzy_score(query, it.get("path", "")) * 0.5,
                )
                if score > 0.25:
                    item_ref = it
                    results.append(SearchResult(
                        title=it["name"],
                        subtitle=it.get("category", ""),
                        category="Document",
                        icon=it.get("icon", "📄"),
                        action=lambda x=item_ref: self._open_doc(x),
                        score=score,
                    ))
            return results
        self.ctx.search.register("documents", provider)

    def on_show(self):
        self._refresh()
