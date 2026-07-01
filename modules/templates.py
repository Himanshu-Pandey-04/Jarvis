"""
Clipboard templates. Save reusable snippets (emails, SQL, code patterns)
with optional {{placeholders}} that prompt at copy time.
"""
import re
from datetime import datetime
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QTextEdit, QSplitter,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox, QComboBox, QMessageBox,
    QMenu, QApplication, QFormLayout, QWidget, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCursor

from modules.base import Module
from ui.widgets import SectionHeader, Card
from core.search import SearchResult, fuzzy_score

DEFAULT_TEMPLATE_CATEGORIES = ["Email", "SQL", "Python", "Cloud CLI", "Snippets", "Other"]
PLACEHOLDER_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


class PlaceholderDialog(QDialog):
    """Asks the user to fill {{placeholders}} when copying."""
    def __init__(self, names: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fill in placeholders")
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        self.fields: dict[str, QLineEdit] = {}
        for n in names:
            edit = QLineEdit()
            self.fields[n] = edit
            form.addRow(n, edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> dict[str, str]:
        return {k: v.text() for k, v in self.fields.items()}


class TemplateEditDialog(QDialog):
    def __init__(self, parent=None, tpl: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit template" if tpl else "New template")
        self.setMinimumSize(560, 420)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_in = QLineEdit(tpl["name"] if tpl else "")
        self.cat_in = QComboBox(); self.cat_in.setEditable(True); self.cat_in.addItems(DEFAULT_TEMPLATE_CATEGORIES)
        if tpl: self.cat_in.setCurrentText(tpl.get("category", "Snippets"))
        self.icon_in = QLineEdit(tpl.get("icon", "📋") if tpl else "📋")
        self.icon_in.setMaxLength(4)
        form.addRow("Name", self.name_in)
        form.addRow("Category", self.cat_in)
        form.addRow("Icon", self.icon_in)
        layout.addLayout(form)

        layout.addWidget(QLabel("Body  ·  use {{placeholder_name}} for prompts at copy time, "
                                "and {{date}} / {{datetime}} for live values"))
        self.body_in = QTextEdit(tpl.get("body", "") if tpl else "")
        self.body_in.setStyleSheet("font-family: 'Cascadia Mono','Consolas','SF Mono',monospace; font-size:13px;")
        self.body_in.setMinimumHeight(220)
        layout.addWidget(self.body_in)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def value(self) -> dict:
        return {
            "name":     self.name_in.text().strip() or "Untitled",
            "category": self.cat_in.currentText().strip() or "Snippets",
            "icon":     self.icon_in.text().strip() or "📋",
            "body":     self.body_in.toPlainText(),
        }


class TemplatesModule(Module):
    MODULE_ID = "templates"
    NAME = "Templates"
    ICON = "📋"
    SECTION = "Workspace"
    DESCRIPTION = "Reusable text snippets with placeholders, one click to clipboard."

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        header = SectionHeader(
            "Templates",
            "Stop retyping the same email, SQL or message. Click to copy.",
            action_text="+  New template",
        )
        header.action_clicked.connect(self.add_template)
        outer.addWidget(header)

        # Filter
        filter_card = Card()
        fl = QHBoxLayout(filter_card)
        fl.setContentsMargins(14, 10, 14, 10)
        self.filter_in = QLineEdit(); self.filter_in.setPlaceholderText("Filter templates…")
        self.filter_in.textChanged.connect(self._refresh_list)
        self.cat_filter = QComboBox(); self.cat_filter.addItem("All categories")
        self.cat_filter.currentTextChanged.connect(self._refresh_list)
        fl.addWidget(self.filter_in, 2); fl.addWidget(self.cat_filter, 1)
        outer.addWidget(filter_card)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        # Left: list
        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_select)
        self.list_widget.itemDoubleClicked.connect(self._copy_selected_to_clipboard)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        splitter.addWidget(self.list_widget)

        # Right: preview
        right = QFrame(); right.setObjectName("Card"); right.setProperty("class", "Card")
        rlay = QVBoxLayout(right); rlay.setContentsMargins(16, 16, 16, 16); rlay.setSpacing(8)
        self.preview_title = QLabel("Select a template to preview")
        self.preview_title.setStyleSheet("font-size:15px; font-weight:600;")
        self.preview_meta = QLabel(""); self.preview_meta.setProperty("class", "Muted")
        self.preview_body = QTextEdit(); self.preview_body.setReadOnly(True)
        self.preview_body.setStyleSheet("font-family:'Cascadia Mono','Consolas',monospace; font-size:13px;")
        copy_btn = QPushButton("Copy to clipboard"); copy_btn.setProperty("primary", True)
        copy_btn.clicked.connect(lambda: self._copy_selected_to_clipboard())
        rlay.addWidget(self.preview_title)
        rlay.addWidget(self.preview_meta)
        rlay.addWidget(self.preview_body, 1)
        rlay.addWidget(copy_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([400, 500])
        outer.addWidget(splitter, 1)

        self._refresh_list()

    def _data(self) -> list[dict]:
        return self.load_data(default=[])

    def _save(self, items):
        self.save_data(items)

    def _refresh_list(self):
        items = self._data()
        cats = sorted({i.get("category", "Snippets") for i in items}) or DEFAULT_TEMPLATE_CATEGORIES
        current = self.cat_filter.currentText()
        self.cat_filter.blockSignals(True)
        self.cat_filter.clear(); self.cat_filter.addItem("All categories"); self.cat_filter.addItems(cats)
        idx = self.cat_filter.findText(current); self.cat_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.cat_filter.blockSignals(False)

        q = self.filter_in.text().lower().strip()
        cat = self.cat_filter.currentText()

        self.list_widget.clear()
        for it in items:
            if cat != "All categories" and it.get("category") != cat:
                continue
            if q and q not in it["name"].lower() and q not in it.get("body", "").lower():
                continue
            li = QListWidgetItem(f"  {it.get('icon','📋')}   {it['name']}    ·   {it.get('category','Snippets')}")
            li.setData(Qt.ItemDataRole.UserRole, it)
            self.list_widget.addItem(li)

    def _on_select(self, current, _previous):
        if not current:
            return
        it = current.data(Qt.ItemDataRole.UserRole)
        if not it:
            return
        self.preview_title.setText(f"{it.get('icon','📋')}  {it['name']}")
        ph = sorted(set(PLACEHOLDER_RE.findall(it.get("body", ""))))
        ph = [p for p in ph if p not in ("date", "datetime")]
        meta = f"{it.get('category','Snippets')}"
        if ph:
            meta += "   ·   placeholders: " + ", ".join(ph)
        self.preview_meta.setText(meta)
        self.preview_body.setPlainText(it.get("body", ""))

    def _copy_selected_to_clipboard(self, *_):
        cur = self.list_widget.currentItem()
        if not cur:
            return
        it = cur.data(Qt.ItemDataRole.UserRole)
        if not it:
            return
        body = self._render(it.get("body", ""))
        if body is None:
            return
        QApplication.clipboard().setText(body)
        self.ctx.notify("Template copied", it.get("name", ""))

    def _render(self, body: str) -> str | None:
        """Substitute placeholders. Returns None if the user cancels."""
        # Auto-fill {{date}}, {{datetime}}
        now = datetime.now()
        autos = {"date": now.strftime("%Y-%m-%d"),
                 "datetime": now.strftime("%Y-%m-%d %H:%M")}

        names = sorted(set(PLACEHOLDER_RE.findall(body)))
        prompt_names = [n for n in names if n not in autos]
        values = dict(autos)
        if prompt_names:
            dlg = PlaceholderDialog(prompt_names, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return None
            values.update(dlg.values())
        return PLACEHOLDER_RE.sub(lambda m: values.get(m.group(1).strip(), m.group(0)), body)

    def add_template(self):
        dlg = TemplateEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = self._data()
            data.append(dlg.value())
            self._save(data)
            self._refresh_list()

    def edit_template(self, tpl):
        dlg = TemplateEditDialog(self, tpl=tpl)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = self._data()
            for i, it in enumerate(data):
                if it["name"] == tpl["name"] and it.get("body") == tpl.get("body"):
                    new = dlg.value()
                    if it.get("default_key"):
                        new["default_key"] = it["default_key"]
                    new["from_defaults"] = False
                    data[i] = new
                    break
            self._save(data)
            self._refresh_list()

    def delete_template(self, tpl):
        if QMessageBox.question(self, "Delete template", f"Delete '{tpl['name']}'?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                == QMessageBox.StandardButton.Yes:
            data = [i for i in self._data() if not (i["name"] == tpl["name"] and i.get("body") == tpl.get("body"))]
            self._save(data)
            self._refresh_list()

    def _show_context_menu(self, _pos):
        cur = self.list_widget.currentItem()
        if not cur: return
        it = cur.data(Qt.ItemDataRole.UserRole)
        if not it: return
        menu = QMenu(self)
        copy_act = QAction("Copy to clipboard", self); copy_act.triggered.connect(self._copy_selected_to_clipboard)
        pin_act  = QAction("Pin to dashboard", self);  pin_act.triggered.connect(lambda: self._pin(it))
        edit_act = QAction("Edit…", self);              edit_act.triggered.connect(lambda: self.edit_template(it))
        del_act  = QAction("Delete", self);             del_act.triggered.connect(lambda: self.delete_template(it))
        for a in (copy_act, pin_act): menu.addAction(a)
        menu.addSeparator(); menu.addAction(edit_act); menu.addAction(del_act)
        menu.exec(QCursor.pos())

    def _pin(self, item: dict):
        # For templates we store the rendered/raw body in `ref` (no placeholder prompt at click time
        # would be unexpected from a pin — so we only allow pinning placeholder-free templates).
        if PLACEHOLDER_RE.search(item.get("body", "")):
            self.ctx.notify("Can't pin templates with placeholders",
                            "Pin only fixed snippets — placeholders need a prompt at copy time.")
            return
        pins = self.ctx.storage.load("pinned_items", [])
        pins.append({"kind": "template", "ref": item["body"], "name": item["name"], "icon": item.get("icon", "📋")})
        self.ctx.storage.save("pinned_items", pins)
        self.ctx.notify("Pinned to dashboard", item["name"], user_initiated=True)

    def register_search(self):
        def provider(query: str) -> list[SearchResult]:
            results = []
            for it in self._data():
                score = max(
                    fuzzy_score(query, it.get("name", "")),
                    fuzzy_score(query, it.get("body", "")[:60]) * 0.4,
                )
                if score > 0.25:
                    body = it.get("body", "")
                    name = it.get("name", "")
                    results.append(SearchResult(
                        title=name,
                        subtitle=(body[:60] + "…") if len(body) > 60 else body,
                        category="Template",
                        icon=it.get("icon", "📋"),
                        action=lambda b=body, n=name: self._search_copy(b, n),
                        score=score,
                    ))
            return results
        self.ctx.search.register("templates", provider)

    def _search_copy(self, body: str, name: str):
        """Copy via search bar — runs placeholder prompt if needed."""
        rendered = self._render(body)
        if rendered is None:
            return
        QApplication.clipboard().setText(rendered)
        self.ctx.notify("Template copied", name)

    def on_show(self):
        self._refresh_list()
