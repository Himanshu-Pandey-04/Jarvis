"""
Credentials store. Simple plain-JSON storage at %APPDATA%/Jarvis/storage.json.

No master password. The app sits in your user profile directory, which has
OS-level access protection (other users on the machine can't read it without
admin). The point of JARVIS is to reduce friction, so we don't gate every
session behind a password prompt.

For higher-stakes use cases (sharing the machine, dual-boot, etc.) keep the
sensitive passwords in your enterprise vault.
"""
import uuid
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QFrame,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox, QMessageBox,
    QMenu, QApplication, QFormLayout, QInputDialog, QWidget,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction

from modules.base import Module
from ui.widgets import SectionHeader, Card, ScrollContainer, EmptyState
from core.search import SearchResult, fuzzy_score


# ============================================================================
# Edit dialog
# ============================================================================
class PasswordDialog(QDialog):
    def __init__(self, parent=None, entry: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit credential" if entry else "Add credential")
        self.setMinimumWidth(420)

        form = QFormLayout(self)
        self.name_in = QLineEdit(entry["name"] if entry else "")
        self.name_in.setPlaceholderText("e.g. PC, BI, zs-ser")
        self.user_in = QLineEdit(entry.get("username", "") if entry else "")
        self.pwd_in  = QLineEdit(entry.get("password", "") if entry else "")
        self.pwd_in.setEchoMode(QLineEdit.EchoMode.Password)

        show_btn = QPushButton("👁")
        show_btn.setCheckable(True); show_btn.setFixedWidth(36)
        show_btn.toggled.connect(lambda checked: self.pwd_in.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
        pwd_row = QHBoxLayout(); pwd_row.addWidget(self.pwd_in, 1); pwd_row.addWidget(show_btn)

        self.url_in   = QLineEdit(entry.get("url", "") if entry else "")
        self.notes_in = QLineEdit(entry.get("notes", "") if entry else "")

        form.addRow("Name", self.name_in)
        form.addRow("Username", self.user_in)
        form.addRow("Password", pwd_row)
        form.addRow("URL (optional)", self.url_in)
        form.addRow("Notes (optional)", self.notes_in)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def value(self) -> dict:
        return {
            "id":       uuid.uuid4().hex,
            "name":     self.name_in.text().strip() or "Untitled",
            "username": self.user_in.text().strip(),
            "password": self.pwd_in.text(),
            "url":      self.url_in.text().strip(),
            "notes":    self.notes_in.text().strip(),
        }


# ============================================================================
# Credential row
# ============================================================================
class CredRow(QFrame):
    def __init__(self, item: dict, on_copy_user, on_copy_pwd, on_edit,
                 on_delete, parent=None):
        super().__init__(parent)
        self.setObjectName("ItemRow")
        layout = QHBoxLayout(self); layout.setContentsMargins(10, 6, 10, 6); layout.setSpacing(8)

        icon = QLabel("🔑"); icon.setObjectName("ItemIcon")
        layout.addWidget(icon)

        name = QLabel(item["name"]); name.setObjectName("ItemName")
        if item.get("url"):
            name.setToolTip(item["url"])
        layout.addWidget(name, 1)

        if item.get("username"):
            user_btn = QPushButton("👤  User")
            user_btn.setProperty("ghost", True); user_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            user_btn.setToolTip(f"Copy username: {item['username']}")
            user_btn.clicked.connect(lambda: on_copy_user(item))
            layout.addWidget(user_btn)

        pwd_btn = QPushButton("🔓  Password")
        pwd_btn.setProperty("primary", True); pwd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pwd_btn.setToolTip("Copy password (clipboard auto-restores after 30s)")
        pwd_btn.clicked.connect(lambda: on_copy_pwd(item))
        layout.addWidget(pwd_btn)

        more_btn = QPushButton("⋯"); more_btn.setProperty("ghost", True); more_btn.setFixedWidth(28)
        more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self)
        a_edit = QAction("Edit…", self); a_edit.triggered.connect(lambda: on_edit(item))
        a_del  = QAction("Delete", self); a_del.triggered.connect(lambda: on_delete(item))
        menu.addAction(a_edit); menu.addSeparator(); menu.addAction(a_del)
        more_btn.setMenu(menu)
        layout.addWidget(more_btn)


# ============================================================================
# Module
# ============================================================================
class PasswordsModule(Module):
    MODULE_ID = "passwords"
    NAME = "Credentials"
    ICON = "🔑"
    SECTION = "Workspace"
    DESCRIPTION = "Quick-copy passwords with clipboard auto-restore. No master password."

    def setup_ui(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollContainer(self)

        header = SectionHeader(
            "Credentials",
            "One-click copy with 30-second clipboard restore. Stored locally in your user profile.",
            action_text="+  Add credential",
        )
        header.action_clicked.connect(self.add_credential)
        scroll.add(header)

        # Info card explaining the trade-off
        info = Card()
        il = QVBoxLayout(info); il.setContentsMargins(20, 14, 20, 14); il.setSpacing(4)
        info_title = QLabel("ℹ  No master password by design")
        info_title.setStyleSheet("font-size:13px; font-weight:600;")
        info_body = QLabel(
            "JARVIS exists to reduce friction. Credentials live at %APPDATA%\\Jarvis\\storage.json — "
            "OS-protected against other users. For higher-stakes secrets, keep them in your enterprise vault."
        )
        info_body.setProperty("class", "Muted"); info_body.setWordWrap(True)
        il.addWidget(info_title); il.addWidget(info_body)
        scroll.add(info)

        # Filter
        filter_card = Card()
        fl = QHBoxLayout(filter_card); fl.setContentsMargins(14, 10, 14, 10)
        self.filter_in = QLineEdit(); self.filter_in.setPlaceholderText("Filter credentials…")
        self.filter_in.textChanged.connect(self._refresh)
        fl.addWidget(self.filter_in)
        scroll.add(filter_card)

        # Host for credential rows
        self.list_card = Card()
        self.list_layout = QVBoxLayout(self.list_card)
        self.list_layout.setContentsMargins(16, 12, 16, 12); self.list_layout.setSpacing(4)
        scroll.add(self.list_card)

        scroll.add_stretch()
        outer.addWidget(scroll)
        self._refresh()

    def _data(self) -> list[dict]:
        return self.load_data(default=[])

    def _save(self, items): self.save_data(items)

    def _refresh(self):
        while self.list_layout.count():
            it = self.list_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()

        items = self._data()
        q = self.filter_in.text().lower().strip()
        if q:
            items = [it for it in items
                     if q in it["name"].lower()
                     or q in it.get("username", "").lower()
                     or q in it.get("notes", "").lower()]

        if not items:
            self.list_layout.addWidget(EmptyState(
                "🔑", "No credentials yet",
                "Click ‘Add credential’ to add a password. Then reference it from a Launcher / Link / Document by the name you gave it (e.g. ‘PC’).",
            ))
            return

        for it in items:
            self.list_layout.addWidget(CredRow(
                it, self._copy_user, self._copy_pwd, self.edit_credential, self.delete_credential
            ))

    # ---------- Actions ----------
    def _copy_user(self, item: dict):
        QApplication.clipboard().setText(item.get("username", ""))
        self.ctx.notify("Username copied", item["name"], sound="success", user_initiated=True)

    def _copy_pwd(self, item: dict):
        pwd = item.get("password", "")
        if not pwd:
            self.ctx.notify("No password set", item["name"], sound="error"); return
        self._copy_with_restore(pwd, 30)
        self.ctx.notify("Password copied", f"Clipboard restores in 30s", sound="success", user_initiated=True)

    def _copy_with_restore(self, text: str, seconds: int = 30):
        cb = QApplication.clipboard()
        prev = cb.text()
        cb.setText(text)
        def restore():
            if cb.text() == text:
                cb.setText(prev)
        QTimer.singleShot(seconds * 1000, restore)

    def add_credential(self):
        dlg = PasswordDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = self._data(); data.append(dlg.value()); self._save(data); self._refresh()

    def edit_credential(self, item):
        dlg = PasswordDialog(self, entry=item)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = self._data()
            for i, it in enumerate(data):
                if it.get("id") == item.get("id") or it.get("name") == item.get("name"):
                    new = dlg.value(); new["id"] = item.get("id") or new["id"]
                    data[i] = new; break
            self._save(data); self._refresh()

    def delete_credential(self, item):
        if QMessageBox.question(self, "Delete", f"Delete credential '{item['name']}'?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                == QMessageBox.StandardButton.Yes:
            data = [i for i in self._data() if i.get("id") != item.get("id")]
            self._save(data); self._refresh()

    # ---------- Public API used by Launchers/Links/Documents for cred_ref ----------
    def copy_named_password(self, name: str, restore_after: int = 60,
                             on_done=None, on_error=None):
        """Find a credential by name (case-insensitive) and copy its password.
        Debounced: identical name within 800ms is silently ignored to avoid
        duplicate notifications (e.g. when a click handler triggers twice)."""
        import time as _time
        if not hasattr(self, "_copy_debounce"):
            self._copy_debounce = {}
        last = self._copy_debounce.get(name.lower(), 0)
        now = _time.monotonic()
        if now - last < 0.8:
            # Already copied very recently — skip duplicate notify but still
            # call on_done so launcher chains don't stall
            if on_done: on_done()
            return True
        self._copy_debounce[name.lower()] = now

        target = next((it for it in self._data()
                       if it.get("name", "").strip().lower() == name.strip().lower()), None)
        if not target:
            if on_error: on_error(f"No credential named '{name}'.")
            self.ctx.notify("Credential not found",
                            f"No credential named '{name}'. Add one in the Credentials page.",
                            sound="error")
            return False
        pwd = target.get("password", "")
        if not pwd:
            if on_error: on_error(f"Credential '{name}' has no password set.")
            self.ctx.notify("Empty credential",
                            f"'{name}' has no password set.", sound="error")
            return False
        self._copy_with_restore(pwd, restore_after)
        self.ctx.notify(f"🔓 Copied '{name}' password",
                         f"Clipboard restores in {restore_after}s",
                         user_initiated=True)
        if on_done: on_done()
        return True

    def get_password_by_name(self, name: str) -> str | None:
        """Returns the raw password value (used by review-protected modules)."""
        target = next((it for it in self._data()
                       if it.get("name", "").strip().lower() == name.strip().lower()), None)
        return target.get("password") if target else None

    # ---------- Search ----------
    def register_search(self):
        def provider(query: str) -> list[SearchResult]:
            results = []
            for it in self._data():
                score = fuzzy_score(query, it.get("name", ""))
                if score > 0.3:
                    item_ref = it
                    results.append(SearchResult(
                        title=it["name"], subtitle="Credential", category="Credentials",
                        icon="🔑",
                        action=lambda x=item_ref: self._copy_pwd(x),
                        score=score,
                    ))
            return results
        self.ctx.search.register("credentials", provider)

    def on_show(self): self._refresh()
