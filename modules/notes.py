"""
Notes — quick personal notes with markdown formatting.

Features:
  • Multiple notes with create/delete/rename
  • Recent notes pinned at top for quick switching
  • Live markdown rendering (headings, bold, italic, code, lists, links)
  • Links inside notes are clickable
  • Keyboard shortcuts: Ctrl+B (bold), Ctrl+I (italic), Ctrl+K (insert link),
    Ctrl+1/2/3 (heading levels), Ctrl+S (save)
"""
import re
import uuid
import webbrowser
from datetime import datetime
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QPushButton, QLineEdit,
    QPlainTextEdit, QListWidget, QListWidgetItem, QFrame, QMessageBox,
    QInputDialog, QMenu, QApplication, QTextBrowser, QWidget,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QShortcut, QKeySequence, QTextCursor, QAction, QDesktopServices
from PyQt6.QtCore import QUrl

from modules.base import Module
from ui.widgets import SectionHeader, Card, EmptyState, ScrollContainer
from core.search import SearchResult, fuzzy_score


# ----------------------------------------------------------------------------
# Markdown → HTML (minimal, intentional)
# ----------------------------------------------------------------------------
def md_to_html(text: str, palette: dict) -> str:
    """Tiny markdown converter. Supports:
       # H1, ## H2, ### H3
       **bold**, *italic*, `code`
       - bullets, 1. numbered
       [text](url), bare URLs
       --- horizontal rule
    """
    if not text:
        return f"<div style='color:{palette['text_muted']}; font-style:italic;'>Start typing on the left…</div>"

    # Escape HTML special chars (very minimal — we'll re-inject our own tags)
    out = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    lines = out.split("\n")
    rendered: list[str] = []
    in_ul = False
    in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul: rendered.append("</ul>"); in_ul = False
        if in_ol: rendered.append("</ol>"); in_ol = False

    accent = palette["accent"]
    text_color = palette["text"]
    code_bg = palette["surface_alt"]
    muted = palette["text_muted"]
    h1 = palette["accent"]; h2 = palette["text"]; h3 = palette["text_muted"]

    for raw in lines:
        line = raw.rstrip()
        # Horizontal rule
        if line.strip() in ("---", "***"):
            close_lists()
            rendered.append(f"<hr style='border:none; border-top:1px solid {palette['border']}; margin:8px 0;'>")
            continue
        # Headings
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            close_lists()
            level = len(m.group(1)); content = m.group(2)
            sizes = {1: "20px", 2: "16px", 3: "14px"}
            colors = {1: h1, 2: h2, 3: h3}
            weights = {1: "700", 2: "600", 3: "600"}
            margins = {1: "14px 0 6px 0", 2: "12px 0 4px 0", 3: "8px 0 2px 0"}
            rendered.append(
                f"<div style='color:{colors[level]}; font-size:{sizes[level]}; "
                f"font-weight:{weights[level]}; margin:{margins[level]};'>{_inline(content, accent, code_bg)}</div>"
            )
            continue
        # Unordered list
        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            if in_ol: rendered.append("</ol>"); in_ol = False
            if not in_ul: rendered.append("<ul style='margin:4px 0 4px 18px; padding:0;'>"); in_ul = True
            rendered.append(f"<li style='color:{text_color}; margin:2px 0;'>{_inline(m.group(1), accent, code_bg)}</li>")
            continue
        # Ordered list
        m = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if m:
            if in_ul: rendered.append("</ul>"); in_ul = False
            if not in_ol: rendered.append("<ol style='margin:4px 0 4px 18px; padding:0;'>"); in_ol = True
            rendered.append(f"<li style='color:{text_color}; margin:2px 0;'>{_inline(m.group(1), accent, code_bg)}</li>")
            continue
        # Blank line
        if not line.strip():
            close_lists()
            rendered.append("<br>")
            continue
        # Paragraph
        close_lists()
        rendered.append(f"<div style='color:{text_color}; margin:2px 0;'>{_inline(line, accent, code_bg)}</div>")

    close_lists()
    return "".join(rendered)


def _inline(s: str, accent: str, code_bg: str) -> str:
    """Inline markdown: **bold**, *italic*, `code`, [text](url), bare URLs."""
    # `code` first (so we don't transform inside it later — we'll use a sentinel)
    code_parts: list[str] = []
    def code_repl(m):
        code_parts.append(m.group(1))
        return f"\x00CODE{len(code_parts)-1}\x00"
    s = re.sub(r"`([^`]+)`", code_repl, s)

    # Links [text](url)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)",
               lambda m: f'<a href="{m.group(2)}" style="color:{accent};">{m.group(1)}</a>', s)
    # Bare URLs
    s = re.sub(r"(?<!\")(https?://[^\s<]+)",
               lambda m: f'<a href="{m.group(1)}" style="color:{accent};">{m.group(1)}</a>', s)
    # Bold then italic
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", s)
    # Restore code with style
    for i, c in enumerate(code_parts):
        s = s.replace(f"\x00CODE{i}\x00",
                      f'<code style="background:{code_bg}; padding:1px 4px; border-radius:3px;">{c}</code>')
    return s


# ----------------------------------------------------------------------------
# Module
# ----------------------------------------------------------------------------
class NotesModule(Module):
    MODULE_ID = "notes"
    NAME = "Notes"
    ICON = "📝"
    SECTION = "Workspace"
    DESCRIPTION = "Quick personal notes with markdown."

    def setup_ui(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        # Header — title + cheat sheet
        header_host = QWidget()
        hh = QVBoxLayout(header_host); hh.setContentsMargins(24, 18, 24, 8); hh.setSpacing(2)
        title = QLabel("📝  Notes"); title.setStyleSheet("font-size:22px; font-weight:700;")
        sub = QLabel("Notes save automatically as you type. Use the toolbar or shortcuts: "
                     "Ctrl+B bold · Ctrl+I italic · Ctrl+K link · Ctrl+1/2/3 headings · Ctrl+S save now")
        sub.setProperty("class", "Muted"); sub.setWordWrap(True)
        hh.addWidget(title); hh.addWidget(sub)
        outer.addWidget(header_host)

        # Recent notes strip
        recent_host = QWidget()
        rh = QVBoxLayout(recent_host); rh.setContentsMargins(24, 0, 24, 8); rh.setSpacing(4)
        rh_title = QLabel("Recent")
        rh_title.setProperty("class", "Muted")
        rh_title.setStyleSheet("font-size:11px; font-weight:600; letter-spacing:0.5px;")
        rh.addWidget(rh_title)
        self.recent_strip = QWidget()
        self.recent_strip_layout = QHBoxLayout(self.recent_strip)
        self.recent_strip_layout.setContentsMargins(0, 0, 0, 0); self.recent_strip_layout.setSpacing(6)
        rh.addWidget(self.recent_strip)
        outer.addWidget(recent_host)

        # Body — splitter: list | editor | (optional) preview
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setHandleWidth(1)

        # Left: notes list
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(8, 4, 4, 8); ll.setSpacing(6)
        list_row = QHBoxLayout()
        new_btn = QPushButton("+  New note"); new_btn.setProperty("primary", True)
        new_btn.clicked.connect(self.new_note)
        list_row.addWidget(new_btn, 1)
        ll.addLayout(list_row)
        self.search_in = QLineEdit(); self.search_in.setPlaceholderText("Filter notes…")
        self.search_in.textChanged.connect(self._refresh_list)
        ll.addWidget(self.search_in)
        self.notes_list = QListWidget()
        self.notes_list.currentItemChanged.connect(self._on_select)
        self.notes_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.notes_list.customContextMenuRequested.connect(self._show_list_menu)
        ll.addWidget(self.notes_list, 1)

        # Middle: editor with save indicator + formatting toolbar
        mid = QWidget(); ml = QVBoxLayout(mid); ml.setContentsMargins(4, 4, 4, 8); ml.setSpacing(6)

        # Title row with save status
        title_row = QHBoxLayout()
        self.title_in = QLineEdit()
        self.title_in.setPlaceholderText("Note title…")
        self.title_in.setStyleSheet("font-size:16px; font-weight:600; padding:8px;")
        self.title_in.textChanged.connect(self._on_title_changed)
        title_row.addWidget(self.title_in, 1)
        self.save_status_lbl = QLabel("")
        self.save_status_lbl.setProperty("class", "Muted")
        self.save_status_lbl.setStyleSheet("font-size:11px; padding:0 8px;")
        self.save_status_lbl.setMinimumWidth(100)
        self.save_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.addWidget(self.save_status_lbl)
        self.toggle_preview_btn = QPushButton("👁  Preview")
        self.toggle_preview_btn.setProperty("ghost", True)
        self.toggle_preview_btn.setCheckable(True)
        self.toggle_preview_btn.setChecked(True)  # preview ON by default
        self.toggle_preview_btn.clicked.connect(self._toggle_preview)
        self.toggle_preview_btn.setToolTip("Show / hide live markdown preview")
        title_row.addWidget(self.toggle_preview_btn)
        ml.addLayout(title_row)

        # Formatting toolbar
        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(4)
        def _fmt_btn(label, tooltip, slot):
            b = QPushButton(label)
            b.setProperty("ghost", True)
            b.setToolTip(tooltip)
            b.setFixedWidth(36)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            return b
        fmt_row.addWidget(_fmt_btn("H₁", "Heading 1 (Ctrl+1)", lambda: self._prefix_line("# ")))
        fmt_row.addWidget(_fmt_btn("H₂", "Heading 2 (Ctrl+2)", lambda: self._prefix_line("## ")))
        fmt_row.addWidget(_fmt_btn("H₃", "Heading 3 (Ctrl+3)", lambda: self._prefix_line("### ")))
        fmt_row.addSpacing(8)
        fmt_row.addWidget(_fmt_btn("𝐁", "Bold (Ctrl+B)", lambda: self._wrap("**", "**")))
        fmt_row.addWidget(_fmt_btn("𝑰", "Italic (Ctrl+I)", lambda: self._wrap("*", "*")))
        fmt_row.addWidget(_fmt_btn("</>", "Inline code", lambda: self._wrap("`", "`")))
        fmt_row.addSpacing(8)
        fmt_row.addWidget(_fmt_btn("•", "Bulleted list", lambda: self._prefix_line("- ")))
        fmt_row.addWidget(_fmt_btn("1.", "Numbered list", lambda: self._prefix_line("1. ")))
        fmt_row.addWidget(_fmt_btn("🔗", "Insert link (Ctrl+K)", self._insert_link))
        fmt_row.addStretch()
        save_now_btn = QPushButton("💾  Save")
        save_now_btn.setProperty("ghost", True)
        save_now_btn.setToolTip("Force save (Ctrl+S). Notes auto-save anyway.")
        save_now_btn.clicked.connect(self._force_save_with_feedback)
        fmt_row.addWidget(save_now_btn)
        ml.addLayout(fmt_row)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("# Heading\n\nStart writing... markdown supported.")
        self.editor.textChanged.connect(self._on_body_changed)
        ml.addWidget(self.editor, 1)

        # Right: preview
        self.preview_pane = QWidget()
        rl = QVBoxLayout(self.preview_pane); rl.setContentsMargins(4, 4, 8, 8); rl.setSpacing(6)
        prev_lbl = QLabel("Preview"); prev_lbl.setProperty("class", "Muted")
        prev_lbl.setStyleSheet("font-size:11px; font-weight:600;")
        rl.addWidget(prev_lbl)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)  # we handle them
        self.preview.anchorClicked.connect(self._open_link)
        rl.addWidget(self.preview, 1)

        body.addWidget(left); body.addWidget(mid); body.addWidget(self.preview_pane)
        body.setSizes([200, 450, 350])
        self._body_splitter = body  # keep reference for toggle
        outer.addWidget(body, 1)

        # Shortcuts
        QShortcut(QKeySequence("Ctrl+B"), self).activated.connect(lambda: self._wrap("**", "**"))
        QShortcut(QKeySequence("Ctrl+I"), self).activated.connect(lambda: self._wrap("*", "*"))
        QShortcut(QKeySequence("Ctrl+K"), self).activated.connect(self._insert_link)
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(lambda: self._prefix_line("# "))
        QShortcut(QKeySequence("Ctrl+2"), self).activated.connect(lambda: self._prefix_line("## "))
        QShortcut(QKeySequence("Ctrl+3"), self).activated.connect(lambda: self._prefix_line("### "))
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._force_save_with_feedback)

        # State
        self._current_id: str | None = None
        self._save_timer = QTimer(self); self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_current)
        self._loading = False  # block save during note-switch

        self._refresh_list()
        # Auto-open most recent
        items = self._data()
        if items:
            self._open_note(items[0]["id"])

    # ---------- Data ----------
    def _data(self) -> list[dict]:
        """List of notes sorted by updated_at desc."""
        notes = self.ctx.storage.load("module_notes", [])
        return sorted(notes, key=lambda n: n.get("updated_at", ""), reverse=True)

    def _save_all(self, notes):
        self.ctx.storage.save("module_notes", notes)

    # ---------- List refresh ----------
    def _refresh_list(self):
        self.notes_list.blockSignals(True)
        self.notes_list.clear()
        q = self.search_in.text().lower().strip()
        for n in self._data():
            title = n.get("title") or "Untitled"
            if q and q not in title.lower() and q not in n.get("body", "").lower():
                continue
            item = QListWidgetItem(f"📄  {title}")
            item.setData(Qt.ItemDataRole.UserRole, n["id"])
            self.notes_list.addItem(item)
            if n["id"] == self._current_id:
                self.notes_list.setCurrentItem(item)
        self.notes_list.blockSignals(False)
        self._refresh_recent_strip()

    def _refresh_recent_strip(self):
        # Clear
        while self.recent_strip_layout.count():
            it = self.recent_strip_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        recent = self._data()[:5]  # top 5 by updated_at
        for n in recent:
            btn = QPushButton(f"📄 {n.get('title') or 'Untitled'}")
            btn.setProperty("ghost", True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            nid = n["id"]
            btn.clicked.connect(lambda _=False, x=nid: self._open_note(x))
            self.recent_strip_layout.addWidget(btn)
        self.recent_strip_layout.addStretch()

    # ---------- Selection ----------
    def _on_select(self, item, _prev):
        if not item: return
        nid = item.data(Qt.ItemDataRole.UserRole)
        if nid != self._current_id:
            self._open_note(nid)

    def _open_note(self, note_id: str):
        # Save current before switching
        if self._current_id and self._current_id != note_id:
            self._save_current()
        notes = self._data()
        note = next((n for n in notes if n["id"] == note_id), None)
        if not note: return
        self._loading = True
        self._current_id = note_id
        self.title_in.setText(note.get("title", ""))
        self.editor.setPlainText(note.get("body", ""))
        self._loading = False
        self._render_preview()
        # Highlight in list
        for i in range(self.notes_list.count()):
            it = self.notes_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == note_id:
                self.notes_list.setCurrentItem(it); break

    def _show_list_menu(self, pos):
        item = self.notes_list.itemAt(pos)
        if not item: return
        nid = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        a_rename = QAction("Rename…", self); a_rename.triggered.connect(lambda: self._rename(nid))
        a_dup = QAction("Duplicate", self); a_dup.triggered.connect(lambda: self._duplicate(nid))
        a_del = QAction("Delete", self); a_del.triggered.connect(lambda: self._delete(nid))
        menu.addAction(a_rename); menu.addAction(a_dup); menu.addSeparator(); menu.addAction(a_del)
        menu.exec(self.notes_list.viewport().mapToGlobal(pos))

    # ---------- CRUD ----------
    def new_note(self):
        nid = uuid.uuid4().hex
        notes = self._data()
        new = {"id": nid, "title": "Untitled", "body": "",
               "created_at": datetime.now().isoformat(timespec="seconds"),
               "updated_at": datetime.now().isoformat(timespec="seconds")}
        notes.append(new)
        self._save_all(notes)
        self._current_id = nid
        self._refresh_list()
        self._open_note(nid)
        self.title_in.setFocus(); self.title_in.selectAll()

    def _rename(self, nid):
        notes = self._data()
        note = next((n for n in notes if n["id"] == nid), None)
        if not note: return
        new, ok = QInputDialog.getText(self, "Rename note", "Title:", text=note.get("title", ""))
        if ok and new.strip():
            note["title"] = new.strip()
            note["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._save_all(notes); self._refresh_list()

    def _duplicate(self, nid):
        notes = self._data()
        note = next((n for n in notes if n["id"] == nid), None)
        if not note: return
        copy = dict(note); copy["id"] = uuid.uuid4().hex
        copy["title"] = (note.get("title") or "Untitled") + " (copy)"
        copy["updated_at"] = datetime.now().isoformat(timespec="seconds")
        notes.append(copy); self._save_all(notes); self._refresh_list()

    def _delete(self, nid):
        notes = self._data()
        note = next((n for n in notes if n["id"] == nid), None)
        if not note: return
        if QMessageBox.question(self, "Delete note", f"Delete '{note.get('title') or 'Untitled'}'?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                != QMessageBox.StandardButton.Yes:
            return
        notes = [n for n in notes if n["id"] != nid]
        self._save_all(notes)
        if nid == self._current_id:
            self._current_id = None
            self.title_in.clear(); self.editor.clear()
        self._refresh_list()
        if notes:
            self._open_note(notes[0]["id"])

    # ---------- Editing ----------
    def _on_title_changed(self, _):
        if not self._loading:
            self._save_timer.start(500)
            self._set_save_status("Editing…", muted=True)

    def _on_body_changed(self):
        if not self._loading:
            self._save_timer.start(400)
            self._set_save_status("Editing…", muted=True)
        self._render_preview()

    def _save_current(self):
        if self._loading or not self._current_id: return
        notes = self._data()
        for n in notes:
            if n["id"] == self._current_id:
                n["title"] = self.title_in.text().strip() or "Untitled"
                n["body"] = self.editor.toPlainText()
                n["updated_at"] = datetime.now().isoformat(timespec="seconds")
                break
        self._save_all(notes)
        # Refresh BOTH the sidebar list (so renamed titles show immediately)
        # and the recent strip
        self._refresh_list()
        self._set_save_status("✓ Saved", muted=False)
        # After 2.5s, fade the indicator
        QTimer.singleShot(2500, lambda: self._set_save_status("", muted=True))

    def _set_save_status(self, text: str, muted: bool = True):
        if hasattr(self, "save_status_lbl"):
            self.save_status_lbl.setText(text)
            if muted:
                self.save_status_lbl.setStyleSheet(
                    f"font-size:11px; padding:0 8px; color:{self.ctx.theme.palette['text_muted']};")
            else:
                self.save_status_lbl.setStyleSheet(
                    f"font-size:11px; padding:0 8px; color:{self.ctx.theme.palette['success']}; font-weight:600;")

    def _force_save_with_feedback(self):
        if not self._current_id:
            self.ctx.notify("No note selected", "Create one with ‘+ New note’.",
                            sound="error", source="Notes")
            return
        self._save_current()  # already sets the saved indicator
        self.ctx.play_sound("success")

    def _toggle_preview(self):
        on = self.toggle_preview_btn.isChecked()
        self.preview_pane.setVisible(on)
        if on:
            # Recompute and re-show
            self._render_preview()
            # Re-apply sane sizes
            try:
                self._body_splitter.setSizes([200, 450, 350])
            except Exception:
                pass
        else:
            try:
                self._body_splitter.setSizes([200, 800, 0])
            except Exception:
                pass

    def _render_preview(self):
        body = self.editor.toPlainText()
        html = md_to_html(body, self.ctx.theme.palette)
        # Wrap in font-family hint
        self.preview.setHtml(
            f"<div style='font-family:Segoe UI, system-ui, sans-serif; font-size:13.5px; "
            f"line-height:1.5;'>{html}</div>"
        )

    def _open_link(self, url: QUrl):
        # Open external links in browser; restore preview after (Qt resets the HTML on anchorClicked)
        webbrowser.open(url.toString())
        QTimer.singleShot(0, self._render_preview)

    # ---------- Shortcuts ----------
    def _wrap(self, prefix: str, suffix: str):
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            sel = cursor.selectedText()
            cursor.insertText(f"{prefix}{sel}{suffix}")
        else:
            pos = cursor.position()
            cursor.insertText(f"{prefix}{suffix}")
            cursor.setPosition(pos + len(prefix))
            self.editor.setTextCursor(cursor)

    def _insert_link(self):
        cursor = self.editor.textCursor()
        sel = cursor.selectedText() if cursor.hasSelection() else "link text"
        url, ok = QInputDialog.getText(self, "Insert link", "URL:", text="https://")
        if not ok or not url.strip(): return
        cursor.insertText(f"[{sel}]({url.strip()})")

    def _prefix_line(self, prefix: str):
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.insertText(prefix)

    # ---------- Search ----------
    def register_search(self):
        def provider(query: str):
            results = []
            for n in self._data():
                score = max(fuzzy_score(query, n.get("title", "")),
                            fuzzy_score(query, n.get("body", "")[:200]) * 0.5)
                if score > 0.3:
                    nid = n["id"]
                    results.append(SearchResult(
                        title=n.get("title") or "Untitled", subtitle="Note", category="Notes",
                        icon="📄",
                        action=lambda x=nid: (self.ctx.navigate("notes"), self._open_note(x)),
                        score=score,
                    ))
            return results
        self.ctx.search.register("notes", provider)

    def on_show(self):
        self._refresh_list()
        if self._current_id:
            self._render_preview()
