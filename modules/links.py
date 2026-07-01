"""
Quick website links — grouped by category.
Cards-per-group layout. Each link row: icon + name + Copy button + Open button.
Right-click for full menu. URLs are not displayed by default — hover to see.
"""
import webbrowser
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QLineEdit, QTextEdit, QFrame,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox, QComboBox, QMessageBox,
    QMenu, QApplication, QFormLayout, QWidget, QInputDialog, QSizePolicy, QCheckBox,
)
from PyQt6.QtCore import Qt, QByteArray
from PyQt6.QtGui import QAction, QCursor, QPixmap

from modules.base import Module
from ui.widgets import SectionHeader, Card, EmptyState, ScrollContainer
from core.search import SearchResult, fuzzy_score

# Built-in defaults (always available). User-created groups persist in
# storage key "module_links_user_groups".
DEFAULT_GROUPS = ["Internal", "SNOW", "Cloud", "Docs", "Tools", "Personal"]


# ============================================================================
# Edit dialog
# ============================================================================
class LinkDialog(QDialog):
    def __init__(self, parent=None, link: dict | None = None,
                 groups: list[str] | None = None,
                 credentials: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit link" if link else "Add link")
        self.setMinimumWidth(440)

        form = QFormLayout(self)
        self.name_in  = QLineEdit(link["name"] if link else "")
        self.url_in   = QLineEdit(link["url"] if link else "")
        self.url_in.setPlaceholderText("https://example.com")
        self.icon_in  = QLineEdit(link.get("icon", "🔗") if link else "🔗")
        self.icon_in.setMaxLength(4)
        self.cat_in   = QComboBox()
        self.cat_in.setEditable(True)
        self.cat_in.addItems(groups or DEFAULT_GROUPS)
        if link:
            self.cat_in.setCurrentText(link.get("category", "Internal"))
        # Credentials dropdown — pulls names from the Credentials module.
        # Editable so the user can still type a name that doesn't exist yet.
        self.cred_in = QComboBox()
        self.cred_in.setEditable(True)
        self.cred_in.addItem("")  # blank = no associated credential
        for name in (credentials or []):
            self.cred_in.addItem(name)
        if link and link.get("cred_ref"):
            self.cred_in.setCurrentText(link["cred_ref"])
        self.cred_in.lineEdit().setPlaceholderText(
            "Pick a vault entry, or leave blank (e.g. PC, BI)")
        self.notes_in = QTextEdit(link.get("notes", "") if link else "")
        self.notes_in.setMaximumHeight(70)

        form.addRow("Name", self.name_in)
        form.addRow("URL", self.url_in)
        form.addRow("Icon (emoji)", self.icon_in)
        form.addRow("Group", self.cat_in)
        form.addRow("Associated credentials", self.cred_in)
        form.addRow("Notes", self.notes_in)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        # Enter key on any field triggers OK by default since OK button is default
        buttons.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def value(self) -> dict:
        url = self.url_in.text().strip()
        if url and not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url
        return {
            "name":     self.name_in.text().strip() or "Untitled",
            "url":      url,
            "icon":     self.icon_in.text().strip() or "🔗",
            "category": self.cat_in.currentText().strip() or "Internal",
            "cred_ref": self.cred_in.currentText().strip(),
            "notes":    self.notes_in.toPlainText().strip(),
        }


# ============================================================================
# Compact tile (replaces LinkRow — much denser, tile grid layout)
# ============================================================================
class LinkTile(QFrame):
    # Class-level favicon cache to avoid refetching across re-renders
    _favicon_cache: dict[str, QPixmap] = {}

    def __init__(self, item: dict, on_open, on_copy, on_edit, on_delete,
                 on_pin, on_move_group, select_mode: bool = False,
                 selected: bool = False, on_select_toggle=None, parent=None):
        super().__init__(parent)
        self.setObjectName("PinTile")
        self.setMinimumHeight(78)
        self.item = item
        self.on_open = on_open
        self._select_mode = select_mode
        self._on_select_toggle = on_select_toggle
        # In select mode, clicking the tile toggles selection; else opens link
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Rich whole-tile tooltip
        _tip = item["name"]
        if item.get("url"): _tip += f"\n{item['url']}"
        if item.get("cred_ref"): _tip += f"\n🔑 Credentials: {item['cred_ref']}"
        if item.get("notes"): _tip += f"\n\n{item['notes']}"
        if select_mode:
            _tip = "Click to " + ("deselect" if selected else "select") + "\n\n" + _tip
        self.setToolTip(_tip)

        layout = QVBoxLayout(self); layout.setContentsMargins(10, 8, 10, 8); layout.setSpacing(2)

        top = QHBoxLayout()
        # In selection mode, show a checkbox on the left
        if select_mode:
            self.select_cb = QCheckBox()
            self.select_cb.setChecked(selected)
            self.select_cb.setCursor(Qt.CursorShape.PointingHandCursor)
            self.select_cb.toggled.connect(
                lambda v, it=item: on_select_toggle(it, v) if on_select_toggle else None)
            top.addWidget(self.select_cb)

        # Show favicon if we have one cached or can derive one, else emoji icon
        icon_widget = self._make_icon_widget(item)
        top.addWidget(icon_widget)
        if item.get("cred_ref"):
            cred_lbl = QLabel("🔑"); cred_lbl.setStyleSheet("font-size:11px; background:transparent;")
            cred_lbl.setToolTip(f"Credentials: {item['cred_ref']}")
            top.addWidget(cred_lbl)
        top.addStretch()

        copy_btn = QPushButton("📋"); copy_btn.setProperty("ghost", True); copy_btn.setFixedWidth(28)
        copy_btn.setToolTip("Copy URL to clipboard")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.clicked.connect(lambda: on_copy(item))
        top.addWidget(copy_btn)

        more_btn = QPushButton("⋯"); more_btn.setProperty("ghost", True); more_btn.setFixedWidth(24)
        more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self)
        a_pin  = QAction("Pin to dashboard", self); a_pin.triggered.connect(lambda: on_pin(item))
        a_move = QAction("Move to group…", self);   a_move.triggered.connect(lambda: on_move_group(item))
        a_edit = QAction("Edit…", self);            a_edit.triggered.connect(lambda: on_edit(item))
        a_del  = QAction("Delete", self);           a_del.triggered.connect(lambda: on_delete(item))
        menu.addAction(a_pin); menu.addAction(a_move); menu.addSeparator(); menu.addAction(a_edit); menu.addAction(a_del)
        more_btn.setMenu(menu)
        top.addWidget(more_btn)
        layout.addLayout(top)

        name = QLabel(item["name"]); name.setObjectName("PinTileName")
        name.setToolTip(item.get("url", ""))
        name.setWordWrap(True)
        layout.addWidget(name)

        if item.get("notes"):
            notes = QLabel(item["notes"]); notes.setObjectName("PinTileKind")
            notes.setWordWrap(True)
            layout.addWidget(notes)
        layout.addStretch()

        # In select mode show a visible highlight if selected
        if select_mode and selected:
            self.setStyleSheet("QFrame#PinTile { border: 2px solid #39C7FF; }")

    def _make_icon_widget(self, item: dict) -> QLabel:
        """Return a QLabel containing either an emoji icon or a cached favicon."""
        lbl = QLabel(); lbl.setObjectName("PinTileIcon")
        lbl.setStyleSheet("background:transparent;")
        # Try favicon cache first
        url = (item.get("url") or "").strip()
        if url:
            cached = LinkTile._favicon_cache.get(url)
            if cached and not cached.isNull():
                lbl.setPixmap(cached.scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))
                return lbl
            # Kick off async fetch (if not already fetched)
            if url not in LinkTile._favicon_cache:
                LinkTile._favicon_cache[url] = QPixmap()  # placeholder to dedup
                self._fetch_favicon_async(url, lbl)
        # Default: emoji
        lbl.setText(item.get("icon", "🔗"))
        return lbl

    def _fetch_favicon_async(self, url: str, target_label: QLabel):
        """Fetch favicon in a background thread; set pixmap when done."""
        import threading
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return
            # Use Google's favicon service — works without API key, even for
            # internal hosts (returns a generic globe icon).
            favicon_url = f"https://www.google.com/s2/favicons?domain={parsed.netloc}&sz=32"
        except Exception:
            return

        def worker():
            try:
                import urllib.request
                req = urllib.request.Request(favicon_url, headers={
                    "User-Agent": "Mozilla/5.0 (JARVIS desktop)"})
                with urllib.request.urlopen(req, timeout=4) as resp:
                    data = resp.read()
                pix = QPixmap()
                pix.loadFromData(QByteArray(data))
                if pix.isNull():
                    return
                LinkTile._favicon_cache[url] = pix
                # Apply to label on UI thread via QTimer.singleShot
                from PyQt6.QtCore import QTimer
                def apply():
                    try:
                        if target_label and not target_label.isHidden():
                            target_label.setText("")  # clear emoji fallback
                            target_label.setPixmap(pix.scaled(
                                20, 20, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation))
                    except RuntimeError:
                        pass  # label was deleted
                QTimer.singleShot(0, apply)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._select_mode:
                # Toggle selection (synced via the checkbox)
                if hasattr(self, "select_cb"):
                    self.select_cb.toggle()
            else:
                self.on_open(self.item)
        super().mousePressEvent(event)


# ============================================================================
# Module
# ============================================================================
class LinksModule(Module):
    MODULE_ID = "links"
    NAME = "Links"
    ICON = "🔗"
    SECTION = "Workspace"
    DESCRIPTION = "Website shortcuts grouped into cards. Copy or open with one click."

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # State for bulk selection — set of (name, url) tuples
        self._selected: set = set()
        self._select_mode: bool = False

        scroll = ScrollContainer(self)

        header = SectionHeader(
            "Links",
            "One card per group. Each link gives you Copy and Open. "
            "Use the ⋯ menu to move a link between groups.",
            action_text="+  Add link",
        )
        header.action_clicked.connect(self.add_link)
        scroll.add(header)

        # Filter bar + group create + selection toggle
        filter_card = Card()
        fl = QHBoxLayout(filter_card); fl.setContentsMargins(14, 10, 14, 10); fl.setSpacing(8)
        self.filter_in = QLineEdit()
        self.filter_in.setPlaceholderText("Filter links…")
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

        # Bulk action bar — hidden by default, visible when items selected
        self.bulk_bar = Card()
        self.bulk_bar.setVisible(False)
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

        # Host for group cards
        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(14)
        scroll.add(self.cards_host)

        scroll.add_stretch()
        outer.addWidget(scroll)
        self._refresh()

    # ---------- Bulk selection ----------
    def _key_of(self, item: dict) -> tuple:
        return (item.get("name", ""), item.get("url", ""))

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
        if checked:
            self._selected.add(k)
        else:
            self._selected.discard(k)
        self._update_bulk_bar()

    def _update_bulk_bar(self):
        n = len(self._selected)
        self.bulk_bar.setVisible(self._select_mode and n > 0)
        self.bulk_count_lbl.setText(f"{n} selected")

    def _bulk_clear(self):
        self._selected.clear()
        self._update_bulk_bar()
        self._refresh()

    def _bulk_move(self):
        if not self._selected: return
        groups = self._all_groups()
        choice, ok = QInputDialog.getItem(self, "Move selected",
                                           f"Move {len(self._selected)} link(s) to:",
                                           groups, 0, False)
        if not ok or not choice:
            return
        data = self._data()
        moved = 0
        for it in data:
            if self._key_of(it) in self._selected:
                it["category"] = choice
                moved += 1
        self._save(data)
        self._selected.clear()
        self.ctx.notify("Links moved", f"{moved} link(s) → ‘{choice}’",
                        sound="success", source="Links", user_initiated=True)
        self._refresh()

    def _bulk_delete(self):
        if not self._selected: return
        n = len(self._selected)
        if QMessageBox.question(self, "Delete selected",
                                 f"Delete {n} link(s)? This can't be undone."
                                 ) != QMessageBox.StandardButton.Yes:
            return
        data = [it for it in self._data() if self._key_of(it) not in self._selected]
        self._save(data)
        self._selected.clear()
        self.ctx.notify("Links deleted", f"Removed {n} link(s).",
                        sound="success", source="Links", user_initiated=True)
        self._refresh()

    # ---------- Data ----------
    def _data(self) -> list[dict]:
        items = self.load_data(default=[])
        # Backward compat: ensure cred_ref field exists
        for it in items:
            it.setdefault("cred_ref", "")
        return items

    def _save(self, items): self.save_data(items)

    def _user_groups(self) -> list[str]:
        """Groups the user has explicitly created. Persists separately from
        links so empty groups don't disappear."""
        return self.ctx.storage.load("module_links_user_groups", []) or []

    def _save_user_groups(self, groups: list[str]):
        self.ctx.storage.save("module_links_user_groups",
                              list(dict.fromkeys([g for g in groups if g])))

    def _all_groups(self) -> list[str]:
        used = [i.get("category", "Internal") for i in self._data()]
        # Merge: used + user-defined + defaults, deduplicating but preserving order
        return list(dict.fromkeys(used + self._user_groups() + DEFAULT_GROUPS))

    # ---------- Render ----------
    def _refresh(self):
        # Clear
        while self.cards_layout.count():
            it = self.cards_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        items = self._data()
        q = self.filter_in.text().lower().strip()
        if q:
            items = [it for it in items
                     if q in it["name"].lower()
                     or q in it.get("url", "").lower()
                     or q in it.get("notes", "").lower()
                     or q in it.get("category", "").lower()]

        # Group items by category, preserving insertion order of categories
        from collections import OrderedDict
        groups: "OrderedDict[str, list[dict]]" = OrderedDict()
        for it in items:
            groups.setdefault(it.get("category", "Internal"), []).append(it)
        # Also show empty user-created groups (so users can see what they made)
        if not q:
            for g in self._user_groups():
                groups.setdefault(g, [])

        if not items and not groups:
            empty = EmptyState(
                "🔗", "No links yet",
                "Click ‘Add link’ to add a website. Group them with the Group field "
                "(e.g. ‘Internal’, ‘SNOW’, ‘Cloud’).")
            self.cards_layout.addWidget(empty)
            return

        # Bulk action bar (visible only in selection mode with ≥1 selected)
        self._update_bulk_bar()

        for group_name, group_items in groups.items():
            self.cards_layout.addWidget(self._build_group_card(group_name, group_items))

    def _build_group_card(self, group: str, items: list[dict]) -> QFrame:
        card = QFrame()
        card.setObjectName("GroupCard")
        layout = QVBoxLayout(card); layout.setContentsMargins(16, 14, 16, 14); layout.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel(group); title.setObjectName("GroupTitle")
        head.addWidget(title)
        count = QLabel(f"{len(items)} item{'s' if len(items) != 1 else ''}")
        count.setObjectName("GroupCount")
        head.addWidget(count)
        head.addStretch()

        if self._select_mode and items:
            select_all_btn = QPushButton("☑ All")
            select_all_btn.setProperty("ghost", True)
            select_all_btn.setToolTip("Select all links in this group")
            select_all_btn.clicked.connect(lambda _=False, its=items: self._select_all_in(its))
            head.addWidget(select_all_btn)

        rename_btn = QPushButton("✎  Rename")
        rename_btn.setProperty("ghost", True)
        rename_btn.clicked.connect(lambda _=False, g=group: self._rename_group(g))
        head.addWidget(rename_btn)

        del_btn = QPushButton("🗑  Delete group")
        del_btn.setProperty("ghost", True)
        del_btn.setStyleSheet("color: #DC2626;")
        del_btn.setToolTip("Delete this group (and any links in it)")
        del_btn.clicked.connect(lambda _=False, g=group: self._delete_group(g))
        head.addWidget(del_btn)
        layout.addLayout(head)

        if not items:
            # Empty group placeholder
            empty_lbl = QLabel("No links here yet. Use ‘Add link’ and pick this group, "
                              "or use the ⋯ menu on a link to move it here.")
            empty_lbl.setProperty("class", "Muted")
            empty_lbl.setWordWrap(True)
            empty_lbl.setStyleSheet("padding: 12px 4px; font-style: italic;")
            layout.addWidget(empty_lbl)
            return card

        # Tile grid (3 columns)
        grid_host = QWidget()
        grid = QGridLayout(grid_host); grid.setSpacing(10); grid.setContentsMargins(0, 0, 0, 0)
        cols = 3
        for i, it in enumerate(items):
            tile = LinkTile(it,
                             on_open=self._open_link,
                             on_copy=self._copy_url,
                             on_edit=self.edit_link,
                             on_delete=self.delete_link,
                             on_pin=self._pin_to_dashboard,
                             on_move_group=self._move_to_group,
                             select_mode=self._select_mode,
                             selected=self._key_of(it) in self._selected,
                             on_select_toggle=self._toggle_selected)
            grid.addWidget(tile, i // cols, i % cols)
        for c in range(cols):
            grid.setColumnStretch(c, 1)
        layout.addWidget(grid_host)
        return card

    def _select_all_in(self, items: list[dict]):
        for it in items:
            self._selected.add(self._key_of(it))
        self._update_bulk_bar()
        self._refresh()

    # ---------- Actions ----------
    def _open_link(self, item: dict):
        self.ctx.play_sound("click")
        try:
            webbrowser.open(item["url"])
        except Exception as e:
            self.ctx.notify("Couldn't open", str(e), sound="error")
            return
        # Auto-copy associated credentials if any
        cred = (item.get("cred_ref") or "").strip()
        if cred:
            self.ctx.copy_password_with_restore(cred, restore_after=60)

    def _copy_url(self, item: dict):
        QApplication.clipboard().setText(item.get("url", ""))
        self.ctx.notify("URL copied", item.get("name", ""), sound="success")

    def _credential_names(self) -> list[str]:
        """Pull credential names from the Credentials module for the dropdown."""
        items = self.ctx.storage.load("module_passwords", []) or []
        return sorted({(it.get("name") or "").strip()
                       for it in items if it.get("name")})

    def add_link(self):
        dlg = LinkDialog(self, groups=self._all_groups(),
                         credentials=self._credential_names())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = self._data(); data.append(dlg.value()); self._save(data)
            self._refresh()

    def edit_link(self, item: dict):
        dlg = LinkDialog(self, link=item, groups=self._all_groups(),
                         credentials=self._credential_names())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = self._data()
            for i, it in enumerate(data):
                if it.get("url") == item.get("url") and it.get("name") == item.get("name"):
                    new = dlg.value()
                    # User edited — keep identity, mark as user-owned
                    if it.get("default_key"):
                        new["default_key"] = it["default_key"]
                    new["from_defaults"] = False
                    data[i] = new; break
            self._save(data)
            self._refresh()

    def delete_link(self, item: dict):
        if QMessageBox.question(self, "Delete link", f"Delete '{item['name']}'?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                == QMessageBox.StandardButton.Yes:
            data = [i for i in self._data()
                    if not (i.get("url") == item.get("url") and i.get("name") == item.get("name"))]
            self._save(data); self._refresh()

    def _pin_to_dashboard(self, item: dict):
        pins = self.ctx.storage.load("pinned_items", [])
        if any(p.get("kind") == "link" and p.get("ref") == item["url"] for p in pins):
            self.ctx.notify("Already pinned", item["name"]); return
        pins.append({"kind": "link", "ref": item["url"], "name": item["name"],
                     "icon": item.get("icon", "🔗")})
        self.ctx.storage.save("pinned_items", pins)
        self.ctx.notify("Pinned to dashboard", item["name"], sound="success", user_initiated=True)

    def _move_to_group(self, item: dict):
        groups = self._all_groups()
        choice, ok = QInputDialog.getItem(self, "Move to group",
                                          f"Move '{item['name']}' to:",
                                          groups + ["+ New group…"], 0, False)
        if not ok:
            return
        if choice == "+ New group…":
            new_name, ok = QInputDialog.getText(self, "New group", "Group name:")
            if not ok or not new_name.strip():
                return
            choice = new_name.strip()
        data = self._data()
        for it in data:
            if it.get("url") == item.get("url") and it.get("name") == item.get("name"):
                it["category"] = choice
                break
        self._save(data); self._refresh()

    def _create_group(self):
        new_name, ok = QInputDialog.getText(self, "New group",
                                             "Group name:")
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        existing = self._all_groups()
        if new_name in existing:
            self.ctx.notify("Group exists",
                            f"‘{new_name}’ already exists.",
                            sound="warning", source="Links")
            return
        # Persist the group so it's selectable in dialogs and shows as an empty card
        groups = self._user_groups()
        groups.append(new_name)
        self._save_user_groups(groups)
        self.ctx.notify("Group created",
                        f"‘{new_name}’ is ready. Add or move links here.",
                        sound="success", source="Links", user_initiated=True)
        self._refresh()

    def _rename_group(self, old: str):
        new_name, ok = QInputDialog.getText(self, "Rename group",
                                             f"New name for ‘{old}’:", text=old)
        if not ok or not new_name.strip() or new_name.strip() == old:
            return
        new = new_name.strip()
        data = self._data()
        for it in data:
            if it.get("category") == old:
                it["category"] = new
        self._save(data)
        # Also update user_groups list if old was there
        groups = self._user_groups()
        groups = [new if g == old else g for g in groups]
        self._save_user_groups(groups)
        self._refresh()

    def _delete_group(self, group: str):
        items = [it for it in self._data() if it.get("category") == group]
        msg = (f"Delete group ‘{group}’?\n\n"
               f"{len(items)} link(s) will also be deleted." if items
               else f"Delete empty group ‘{group}’?")
        if QMessageBox.question(self, "Delete group", msg) != QMessageBox.StandardButton.Yes:
            return
        # Remove all links in this group
        if items:
            data = [it for it in self._data() if it.get("category") != group]
            self._save(data)
        # Remove from user_groups
        groups = [g for g in self._user_groups() if g != group]
        self._save_user_groups(groups)
        self.ctx.notify("Group deleted",
                        f"‘{group}’ removed" + (f" along with {len(items)} link(s)." if items else "."),
                        sound="success", source="Links", user_initiated=True)
        self._refresh()

    # ---------- Search ----------
    def register_search(self):
        def provider(query: str) -> list[SearchResult]:
            results = []
            for it in self._data():
                score = max(
                    fuzzy_score(query, it.get("name", "")),
                    fuzzy_score(query, it.get("url", "")) * 0.7,
                    fuzzy_score(query, it.get("category", "")) * 0.5,
                )
                if score > 0.25:
                    item_ref = it
                    results.append(SearchResult(
                        title=it["name"],
                        subtitle=it.get("category", ""),
                        category="Link",
                        icon=it.get("icon", "🔗"),
                        action=lambda x=item_ref: self._open_link(x),
                        score=score,
                    ))
            return results
        self.ctx.search.register("links", provider)

    def on_show(self):
        self._refresh()
