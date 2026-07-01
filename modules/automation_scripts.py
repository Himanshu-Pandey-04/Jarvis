"""
Automation Scripts module.

Store, view, edit, and copy automation scripts (Python, shell, JS, SQL, PS,
etc). User can upload an existing file from PC or paste code directly.
Scripts are grouped (ETL, Cleanup, Reports, …) and tagged with their file type
via prominent badges.

Storage layout:
  module_automation_scripts          → [
    {
      "id": "...",
      "name": "etl_runner.py",
      "ext": ".py",
      "language": "python",
      "group": "ETL",
      "content": "...",         # the actual script text
      "size_bytes": 1234,
      "created_at": "...",
      "updated_at": "...",
      "notes": "...",
    }
  ]
  module_automation_scripts_groups   → ["ETL", "Cleanup", ...]
"""
import uuid
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QPlainTextEdit,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox, QComboBox,
    QFileDialog, QMessageBox, QSplitter, QFrame, QWidget, QInputDialog,
    QApplication, QFormLayout, QSizePolicy, QMenu,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFont

from modules.base import Module
from ui.widgets import SectionHeader, Card, EmptyState
from core.search import SearchResult, fuzzy_score


# ---------------------------------------------------------------------------
# Extension → (language, emoji badge, badge color)
# ---------------------------------------------------------------------------
EXT_MAP = {
    ".py":   ("Python",     "🐍", "#3776AB"),
    ".sh":   ("Shell",      "🐚", "#4EAA25"),
    ".bash": ("Bash",       "🐚", "#4EAA25"),
    ".zsh":  ("Zsh",        "🐚", "#4EAA25"),
    ".ps1":  ("PowerShell", "💠", "#012456"),
    ".bat":  ("Batch",      "⚙",  "#C1F12E"),
    ".cmd":  ("Batch",      "⚙",  "#C1F12E"),
    ".js":   ("JavaScript", "🟨", "#F7DF1E"),
    ".ts":   ("TypeScript", "🔷", "#3178C6"),
    ".sql":  ("SQL",        "🗃", "#E48E00"),
    ".rb":   ("Ruby",       "💎", "#CC342D"),
    ".go":   ("Go",         "🦦", "#00ADD8"),
    ".rs":   ("Rust",       "🦀", "#CE422B"),
    ".java": ("Java",       "☕", "#B07219"),
    ".php":  ("PHP",        "🐘", "#777BB4"),
    ".pl":   ("Perl",       "🐪", "#0298C3"),
    ".r":    ("R",          "📊", "#198CE7"),
    ".yaml": ("YAML",       "📄", "#CB171E"),
    ".yml":  ("YAML",       "📄", "#CB171E"),
    ".json": ("JSON",       "📜", "#292929"),
    ".xml":  ("XML",        "📰", "#0060AC"),
    ".txt":  ("Text",       "📄", "#7E7E7E"),
    ".md":   ("Markdown",   "📝", "#083FA1"),
    ".dockerfile": ("Dockerfile", "🐳", "#2496ED"),
}

DEFAULT_GROUPS = ["Scripts", "ETL", "Cleanup", "Reports", "Automation"]


def _ext_info(name: str) -> tuple[str, str, str]:
    """Return (language, emoji, color) for a filename."""
    name_l = name.lower()
    # Dockerfile special case (no extension)
    if name_l == "dockerfile" or name_l.endswith("/dockerfile"):
        return EXT_MAP[".dockerfile"]
    ext = Path(name_l).suffix or ".txt"
    return EXT_MAP.get(ext, ("Plain", "📄", "#7E7E7E"))


def _human_size(n: int) -> str:
    if n < 1024: return f"{n} B"
    if n < 1024 * 1024: return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


# ===========================================================================
# Dialogs
# ===========================================================================

class ScriptEditDialog(QDialog):
    """Add a script via paste-or-upload, or edit an existing one."""
    def __init__(self, parent=None, script: dict | None = None,
                 groups: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit script" if script else "Add script")
        self.resize(820, 580)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14); layout.setSpacing(10)

        # Top form: name, group
        form = QFormLayout()
        self.name_in = QLineEdit(script.get("name", "") if script else "")
        self.name_in.setPlaceholderText("e.g. backup_logs.sh")
        self.group_in = QComboBox(); self.group_in.setEditable(True)
        self.group_in.addItems(groups or DEFAULT_GROUPS)
        if script:
            self.group_in.setCurrentText(script.get("group", "Scripts"))
        self.notes_in = QLineEdit(script.get("notes", "") if script else "")
        self.notes_in.setPlaceholderText("Optional one-line description")

        form.addRow("File name", self.name_in)
        form.addRow("Group", self.group_in)
        form.addRow("Notes", self.notes_in)
        layout.addLayout(form)

        # File ops row
        ops = QHBoxLayout()
        upload_btn = QPushButton("📂  Upload from PC…")
        upload_btn.clicked.connect(self._upload)
        ops.addWidget(upload_btn)
        ops.addStretch()
        layout.addLayout(ops)

        # Code editor (monospace, plain text)
        editor_label = QLabel("Script content (paste or edit here):")
        editor_label.setProperty("class", "Muted")
        layout.addWidget(editor_label)
        self.editor = QPlainTextEdit(script.get("content", "") if script else "")
        mono = QFont("Consolas, Menlo, Monaco, 'Courier New', monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self.editor.setFont(mono)
        self.editor.setTabStopDistance(28)
        self.editor.setPlaceholderText("# Paste code here…")
        layout.addWidget(self.editor, 1)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_btn.setText("✓  Save")
        save_btn.setProperty("primary", True)
        save_btn.setDefault(True)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText("✕  Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _upload(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Pick a script file", "",
            "All scripts (*.py *.sh *.bash *.zsh *.ps1 *.bat *.cmd *.js *.ts "
            "*.sql *.rb *.go *.rs *.java *.php *.pl *.r *.yaml *.yml *.json "
            "*.xml *.txt *.md);;All files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            QMessageBox.warning(self, "Couldn't read file", str(e))
            return
        # Limit to 1 MB to keep storage sane
        if len(content) > 1_048_576:
            QMessageBox.warning(self, "File too large",
                                "Scripts above 1 MB aren't supported.")
            return
        self.editor.setPlainText(content)
        # Suggest the original filename
        if not self.name_in.text().strip():
            self.name_in.setText(Path(path).name)

    def keyPressEvent(self, event):
        # Ctrl+Enter saves
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.accept()
                return
        super().keyPressEvent(event)

    def value(self) -> dict:
        name = self.name_in.text().strip() or "untitled.txt"
        content = self.editor.toPlainText()
        lang, _emoji, _color = _ext_info(name)
        return {
            "name":     name,
            "ext":      Path(name).suffix.lower() or ".txt",
            "language": lang,
            "group":    self.group_in.currentText().strip() or "Scripts",
            "content":  content,
            "notes":    self.notes_in.text().strip(),
            "size_bytes": len(content.encode("utf-8")),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }


# ===========================================================================
# Tile widget — one card per script
# ===========================================================================

class ScriptTile(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, script: dict, on_open, on_edit, on_copy, on_export,
                 on_delete, on_move, parent=None):
        super().__init__(parent)
        self.setObjectName("PinTile")
        self.setMinimumHeight(96)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.script = script

        lang, emoji, color = _ext_info(script.get("name", ""))
        self.setToolTip(
            f"{script.get('name')}\n"
            f"{lang} · {_human_size(script.get('size_bytes', 0))}\n"
            f"Group: {script.get('group', 'Scripts')}\n\n"
            f"{script.get('notes', '') or 'Click to open in editor'}"
        )

        layout = QVBoxLayout(self); layout.setContentsMargins(12, 10, 12, 10); layout.setSpacing(4)

        # Top row: language badge + name + ⋯ menu
        top = QHBoxLayout(); top.setSpacing(8)
        badge = QLabel(f" {emoji}  {lang.upper()} ")
        badge.setStyleSheet(
            f"background-color: {color}; color: white; "
            f"border-radius: 4px; padding: 2px 6px; font-size: 10px; "
            f"font-weight: 700; letter-spacing: 0.5px;")
        top.addWidget(badge)
        top.addStretch()

        copy_btn = QPushButton("📋")
        copy_btn.setProperty("ghost", True); copy_btn.setFixedWidth(28)
        copy_btn.setToolTip("Copy script contents")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.clicked.connect(lambda: on_copy(script))
        top.addWidget(copy_btn)

        more_btn = QPushButton("⋯")
        more_btn.setProperty("ghost", True); more_btn.setFixedWidth(24)
        more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self)
        a_open  = QAction("Open in editor", self); a_open.triggered.connect(lambda: on_open(script))
        a_edit  = QAction("Edit metadata…", self); a_edit.triggered.connect(lambda: on_edit(script))
        a_move  = QAction("Move to group…", self); a_move.triggered.connect(lambda: on_move(script))
        a_exp   = QAction("Export to file…", self); a_exp.triggered.connect(lambda: on_export(script))
        a_del   = QAction("Delete", self); a_del.triggered.connect(lambda: on_delete(script))
        menu.addAction(a_open); menu.addAction(a_edit); menu.addAction(a_move)
        menu.addSeparator(); menu.addAction(a_exp); menu.addSeparator(); menu.addAction(a_del)
        more_btn.setMenu(menu)
        top.addWidget(more_btn)
        layout.addLayout(top)

        # Name (filename)
        name_lbl = QLabel(script.get("name", "untitled"))
        name_lbl.setStyleSheet("font-weight: 600; font-size: 13px;")
        name_lbl.setWordWrap(True)
        layout.addWidget(name_lbl)

        # Meta row: size + group
        meta = QLabel(
            f"{_human_size(script.get('size_bytes', 0))}  ·  {script.get('group', 'Scripts')}"
        )
        meta.setProperty("class", "Muted")
        meta.setStyleSheet("font-size: 11px;")
        layout.addWidget(meta)

        if script.get("notes"):
            notes = QLabel(script["notes"])
            notes.setProperty("class", "Muted")
            notes.setStyleSheet("font-size: 11px; font-style: italic;")
            notes.setWordWrap(True)
            layout.addWidget(notes)

        layout.addStretch()
        self._on_open = on_open

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._on_open(self.script)
        super().mousePressEvent(e)


# ===========================================================================
# Module
# ===========================================================================

class AutomationScriptsModule(Module):
    MODULE_ID = "automation_scripts"
    NAME = "Automation Scripts"
    ICON = "🛠"
    SECTION = "Workspace"
    DESCRIPTION = "Store, edit, and copy your automation scripts. Grouped by purpose."

    def setup_ui(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(24, 24, 24, 24); outer.setSpacing(12)

        header = SectionHeader(
            "Automation Scripts",
            "Save your reusable scripts. Upload from disk or paste. "
            "Group by purpose (ETL, Cleanup, Reports). Click any tile to view / edit / copy.",
            action_text="+  Add script",
        )
        header.action_clicked.connect(self.add_script)
        outer.addWidget(header)

        # Filter + new group + upload
        filter_card = Card()
        fl = QHBoxLayout(filter_card); fl.setContentsMargins(14, 10, 14, 10); fl.setSpacing(8)
        self.filter_in = QLineEdit()
        self.filter_in.setPlaceholderText("Filter scripts…")
        self.filter_in.textChanged.connect(self._refresh)
        fl.addWidget(self.filter_in, 1)
        new_group_btn = QPushButton("➕  New group")
        new_group_btn.clicked.connect(self._create_group)
        fl.addWidget(new_group_btn)
        outer.addWidget(filter_card)

        # Scroll container for group cards
        from ui.widgets import ScrollContainer
        self.scroll = ScrollContainer(self)
        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0); self.cards_layout.setSpacing(14)
        self.scroll.add(self.cards_host)
        self.scroll.add_stretch()
        outer.addWidget(self.scroll, 1)

        self._refresh()

    # ---------- Data ----------
    def _data(self) -> list[dict]:
        items = self.ctx.storage.load("module_automation_scripts", []) or []
        for it in items:
            it.setdefault("id", uuid.uuid4().hex)
            it.setdefault("group", "Scripts")
            it.setdefault("ext", Path(it.get("name", "")).suffix.lower() or ".txt")
        return items

    def _save(self, items): self.ctx.storage.save("module_automation_scripts", items)

    def _user_groups(self) -> list[str]:
        return self.ctx.storage.load("module_automation_scripts_groups", []) or []

    def _save_user_groups(self, groups: list[str]):
        self.ctx.storage.save("module_automation_scripts_groups",
                              list(dict.fromkeys([g for g in groups if g])))

    def _all_groups(self) -> list[str]:
        used = [s.get("group", "Scripts") for s in self._data()]
        return list(dict.fromkeys(used + self._user_groups() + DEFAULT_GROUPS))

    # ---------- Render ----------
    def _refresh(self):
        while self.cards_layout.count():
            it = self.cards_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()

        items = self._data()
        q = (self.filter_in.text() or "").lower().strip()
        if q:
            items = [s for s in items
                     if q in s.get("name", "").lower()
                     or q in s.get("notes", "").lower()
                     or q in s.get("language", "").lower()
                     or q in s.get("content", "").lower()
                     or q in s.get("group", "").lower()]

        from collections import OrderedDict
        groups: "OrderedDict[str, list[dict]]" = OrderedDict()
        for s in items:
            groups.setdefault(s.get("group", "Scripts"), []).append(s)
        if not q:
            for g in self._user_groups():
                groups.setdefault(g, [])

        if not items and not groups:
            empty = EmptyState(
                "🛠", "No scripts yet",
                "Click ‘+ Add script’ to paste code or upload a file. "
                "Group your scripts by purpose so they're easy to find later."
            )
            self.cards_layout.addWidget(empty)
            return

        for name, group_items in groups.items():
            self.cards_layout.addWidget(self._build_group_card(name, group_items))

    def _build_group_card(self, group: str, items: list[dict]) -> QFrame:
        card = QFrame(); card.setObjectName("GroupCard")
        layout = QVBoxLayout(card); layout.setContentsMargins(16, 14, 16, 14); layout.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel(group); title.setObjectName("GroupTitle")
        head.addWidget(title)
        count = QLabel(f"{len(items)} script{'s' if len(items) != 1 else ''}")
        count.setObjectName("GroupCount")
        head.addWidget(count); head.addStretch()
        rename_btn = QPushButton("✎  Rename"); rename_btn.setProperty("ghost", True)
        rename_btn.clicked.connect(lambda _=False, g=group: self._rename_group(g))
        head.addWidget(rename_btn)
        del_btn = QPushButton("🗑  Delete group"); del_btn.setProperty("ghost", True)
        del_btn.setStyleSheet("color: #DC2626;")
        del_btn.clicked.connect(lambda _=False, g=group: self._delete_group(g))
        head.addWidget(del_btn)
        layout.addLayout(head)

        if not items:
            empty_lbl = QLabel("No scripts here yet. Add a script and pick this group, "
                              "or use the ⋯ menu on any script to move it here.")
            empty_lbl.setProperty("class", "Muted")
            empty_lbl.setWordWrap(True)
            empty_lbl.setStyleSheet("padding: 10px 4px; font-style: italic;")
            layout.addWidget(empty_lbl)
            return card

        # Grid of tiles
        from PyQt6.QtWidgets import QGridLayout
        grid_host = QWidget()
        grid = QGridLayout(grid_host); grid.setSpacing(10); grid.setContentsMargins(0, 0, 0, 0)
        cols = 3
        for i, it in enumerate(items):
            tile = ScriptTile(it,
                              on_open=self.open_script,
                              on_edit=self.edit_script,
                              on_copy=self.copy_script,
                              on_export=self.export_script,
                              on_delete=self.delete_script,
                              on_move=self.move_script)
            grid.addWidget(tile, i // cols, i % cols)
        for c in range(cols):
            grid.setColumnStretch(c, 1)
        layout.addWidget(grid_host)
        return card

    # ---------- Actions ----------
    def add_script(self):
        dlg = ScriptEditDialog(self, groups=self._all_groups())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.value()
        v["id"] = uuid.uuid4().hex
        v["created_at"] = datetime.now().isoformat(timespec="seconds")
        data = self._data(); data.append(v); self._save(data)
        self.ctx.notify("Script saved", f"‘{v['name']}’ added.",
                        sound="success", source="Automation", user_initiated=True)
        self._refresh()

    def edit_script(self, script: dict):
        dlg = ScriptEditDialog(self, script=script, groups=self._all_groups())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.value()
        v["id"] = script["id"]
        v["created_at"] = script.get("created_at")
        data = self._data()
        for i, s in enumerate(data):
            if s.get("id") == script.get("id"):
                data[i] = v; break
        self._save(data)
        self.ctx.notify("Script updated", f"‘{v['name']}’ saved.",
                        sound="success", source="Automation", user_initiated=True)
        self._refresh()

    def open_script(self, script: dict):
        """Same as edit — opens the editor dialog."""
        self.edit_script(script)

    def copy_script(self, script: dict):
        QApplication.clipboard().setText(script.get("content", ""))
        self.ctx.notify("Script copied",
                        f"‘{script.get('name')}’ contents on clipboard.",
                        sound="success", source="Automation", user_initiated=True)

    def export_script(self, script: dict):
        suggested = script.get("name", "script.txt")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export script", suggested, "All files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(script.get("content", ""))
            self.ctx.notify("Script exported", path,
                            sound="success", source="Automation", user_initiated=True)
        except OSError as e:
            self.ctx.notify("Export failed", str(e), sound="error", source="Automation")

    def delete_script(self, script: dict):
        if QMessageBox.question(self, "Delete script",
                                 f"Delete ‘{script.get('name')}’? This can't be undone."
                                 ) != QMessageBox.StandardButton.Yes:
            return
        data = [s for s in self._data() if s.get("id") != script.get("id")]
        self._save(data)
        self.ctx.notify("Script deleted", script.get("name", ""),
                        sound="success", source="Automation", user_initiated=True)
        self._refresh()

    def move_script(self, script: dict):
        groups = self._all_groups()
        current = script.get("group", "Scripts")
        try:
            idx = groups.index(current)
        except ValueError:
            idx = 0
        choice, ok = QInputDialog.getItem(
            self, "Move script", f"Move ‘{script.get('name')}’ to group:",
            groups, idx, False)
        if not ok or not choice or choice == current:
            return
        data = self._data()
        for s in data:
            if s.get("id") == script.get("id"):
                s["group"] = choice; break
        self._save(data)
        self._refresh()

    # ---------- Groups ----------
    def _create_group(self):
        name, ok = QInputDialog.getText(self, "New script group", "Group name:")
        if not ok or not name.strip(): return
        name = name.strip()
        if name in self._all_groups():
            self.ctx.notify("Group exists", f"‘{name}’ already exists.",
                            sound="warning", source="Automation"); return
        groups = self._user_groups(); groups.append(name)
        self._save_user_groups(groups)
        self.ctx.notify("Group created", f"‘{name}’ ready.",
                        sound="success", source="Automation", user_initiated=True)
        self._refresh()

    def _rename_group(self, old: str):
        new_name, ok = QInputDialog.getText(
            self, "Rename group", f"New name for ‘{old}’:", text=old)
        if not ok or not new_name.strip() or new_name.strip() == old: return
        new = new_name.strip()
        data = self._data()
        for s in data:
            if s.get("group") == old:
                s["group"] = new
        self._save(data)
        groups = [new if g == old else g for g in self._user_groups()]
        self._save_user_groups(groups)
        self._refresh()

    def _delete_group(self, group: str):
        items = [s for s in self._data() if s.get("group") == group]
        msg = (f"Delete group ‘{group}’?\n\n"
               f"{len(items)} script(s) will also be deleted." if items
               else f"Delete empty group ‘{group}’?")
        if QMessageBox.question(self, "Delete group", msg
                                ) != QMessageBox.StandardButton.Yes:
            return
        if items:
            self._save([s for s in self._data() if s.get("group") != group])
        self._save_user_groups([g for g in self._user_groups() if g != group])
        self.ctx.notify("Group deleted",
                        f"‘{group}’ removed" + (f" with {len(items)} script(s)." if items else "."),
                        sound="success", source="Automation", user_initiated=True)
        self._refresh()

    # ---------- Search ----------
    def register_search(self):
        def provider(query: str) -> list[SearchResult]:
            out = []
            for s in self._data():
                score = max(
                    fuzzy_score(query, s.get("name", "")),
                    fuzzy_score(query, s.get("group", "")),
                )
                if score > 0.3:
                    _, emoji, _ = _ext_info(s.get("name", ""))
                    out.append(SearchResult(
                        title=s.get("name", "Script"),
                        subtitle=f"{s.get('language', 'Script')} · {s.get('group', 'Scripts')}",
                        category="Automation",
                        icon=emoji,
                        action=lambda script=s: self.open_script(script),
                        score=score,
                    ))
            return out
        self.ctx.search.register("automation_scripts", provider)
