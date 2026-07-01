"""
Reviews — performance review note-taking for self and colleagues.

Each "review subject" (self or a colleague) gets a card with the standard
review categories. Inside each category, you can capture multiple bullet
points over the cycle.

Password-gated against your 'PC' credential entry (from the Credentials
module). Single unlock per session.
"""
import uuid
import webbrowser
from datetime import datetime
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QPlainTextEdit,
    QFrame, QSplitter, QListWidget, QListWidgetItem, QDialog, QDialogButtonBox,
    QFormLayout, QMessageBox, QInputDialog, QMenu, QWidget, QApplication,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction

from modules.base import Module
from ui.widgets import SectionHeader, Card, EmptyState, ScrollContainer
from core.search import SearchResult, fuzzy_score


# Categories from the user's review template
REVIEW_CATEGORIES = [
    ("Uncategorized",                              "📌"),
    ("Motivation & Initiative",                    "🚀"),
    ("Professionalism",                            "💼"),
    ("Teamwork & People Management",               "🤝"),
    ("Learning Mindset",                           "🧠"),
    ("Quality",                                    "✨"),
    ("Communication",                              "💬"),
    ("Task / Project Management",                  "📋"),
    ("Problem Solving & Results Orientation",      "🎯"),
    ("Technology Proficiency",                     "⚙️"),
    ("Business Context",                           "📊"),
    ("Data Proficiency",                           "📈"),
    ("Creativity & Innovation / Thought Leadership","💡"),
]


class ReviewSubjectDialog(QDialog):
    def __init__(self, parent=None, subject=None):
        super().__init__(parent)
        self.setWindowTitle("Edit subject" if subject else "Add review subject")
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        self.name_in = QLineEdit(subject.get("name", "") if subject else "")
        self.name_in.setPlaceholderText("Self  /  Colleague name")
        self.role_in = QLineEdit(subject.get("role", "") if subject else "")
        self.role_in.setPlaceholderText("Optional — their role (e.g. BTSA-1)")
        self.cycle_in = QLineEdit(subject.get("cycle", "") if subject else "")
        self.cycle_in.setPlaceholderText("Optional — e.g. H1 FY26, Q2 2026")
        form.addRow("Name", self.name_in)
        form.addRow("Role", self.role_in)
        form.addRow("Cycle", self.cycle_in)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def value(self):
        return {
            "id":     uuid.uuid4().hex,
            "name":   self.name_in.text().strip() or "Untitled",
            "role":   self.role_in.text().strip(),
            "cycle":  self.cycle_in.text().strip(),
            "points": {},  # category → list[{text, at}]
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }


# ============================================================================
# Module
# ============================================================================
class ReviewsModule(Module):
    MODULE_ID = "reviews"
    NAME = "Reviews"
    ICON = "📝"
    SECTION = "Workspace"
    DESCRIPTION = "Performance review notes — for yourself and colleagues. Password-gated."

    def setup_ui(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        self._outer = outer

        # Lock state — re-prompt on every navigation to this module (one unlock per session)
        # We store unlocked-this-session in self._unlocked.
        self._unlocked = False
        self._build_locked_view()

    def _build_locked_view(self):
        # Clear
        while self._outer.count():
            it = self._outer.takeAt(0)
            if it.widget(): it.widget().deleteLater()

        host = QWidget()
        v = QVBoxLayout(host); v.setContentsMargins(40, 60, 40, 40); v.setSpacing(16)
        v.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("🔒  Reviews")
        title.setStyleSheet("font-size:28px; font-weight:700;")
        v.addWidget(title)

        sub = QLabel("Sensitive content. Unlock with your PC credential to view.")
        sub.setProperty("class", "Muted")
        v.addWidget(sub)

        # Password input
        form = QFormLayout()
        self.pwd_in = QLineEdit()
        self.pwd_in.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_in.setPlaceholderText("Your PC password")
        self.pwd_in.returnPressed.connect(self._try_unlock)
        form.addRow("Password", self.pwd_in)
        v.addLayout(form)

        # Unlock button
        unlock_btn = QPushButton("🔓  Unlock Reviews")
        unlock_btn.setProperty("primary", True)
        unlock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        unlock_btn.clicked.connect(self._try_unlock)
        v.addWidget(unlock_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        # Hint about credential setup
        hint = QLabel(
            "<i>This page unlocks against the password stored as 'PC' in the Credentials module. "
            "Add or update that entry if needed.</i>"
        )
        hint.setProperty("class", "Muted"); hint.setWordWrap(True)
        v.addWidget(hint)
        v.addStretch()

        self._outer.addWidget(host)
        QTimer.singleShot(0, self.pwd_in.setFocus)

    def _try_unlock(self):
        entered = self.pwd_in.text()
        if not entered:
            return
        passwords = self.ctx.get_module("passwords")
        if not passwords:
            QMessageBox.warning(self, "Credentials unavailable",
                                "The Credentials module isn't loaded. Enable it in Settings.")
            return
        stored = passwords.get_password_by_name("PC")
        if not stored:
            ans = QMessageBox.question(
                self, "No 'PC' credential set",
                "No credential named 'PC' is configured. Set the password you entered as your PC password now? "
                "(You can change it later in Credentials.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ans != QMessageBox.StandardButton.Yes:
                return
            # Create a new credential
            data = passwords._data()
            data.append({
                "id": uuid.uuid4().hex,
                "name": "PC", "username": "", "password": entered,
                "url": "", "notes": "Auto-created by Reviews unlock",
            })
            passwords._save(data)
            passwords.on_show()
            self._unlocked = True
            self._build_unlocked_view()
            return
        if entered == stored:
            self._unlocked = True
            self._build_unlocked_view()
            self.ctx.play_sound("success")
        else:
            QMessageBox.warning(self, "Incorrect password", "That doesn't match your 'PC' credential.")
            self.ctx.play_sound("error")
            self.pwd_in.clear()
            self.pwd_in.setFocus()

    # ------------------------------------------------------------------ unlocked
    def _build_unlocked_view(self):
        while self._outer.count():
            it = self._outer.takeAt(0)
            if it.widget(): it.widget().deleteLater()

        # Header
        header_host = QWidget()
        hh = QVBoxLayout(header_host); hh.setContentsMargins(24, 18, 24, 8)
        title_row = QHBoxLayout()
        title = QLabel("📝  Reviews"); title.setStyleSheet("font-size:22px; font-weight:700;")
        title_row.addWidget(title); title_row.addStretch()

        copy_btn = QPushButton("📋  Copy all")
        copy_btn.setProperty("ghost", True); copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setToolTip("Copy all points for the current subject (with category headings) to clipboard")
        copy_btn.clicked.connect(self._copy_current_subject)
        title_row.addWidget(copy_btn)

        lock_btn = QPushButton("🔒  Lock")
        lock_btn.setProperty("ghost", True); lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        lock_btn.clicked.connect(self._lock)
        title_row.addWidget(lock_btn)
        new_btn = QPushButton("+  Add subject")
        new_btn.setProperty("primary", True); new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self.add_subject)
        title_row.addWidget(new_btn)
        hh.addLayout(title_row)

        sub = QLabel("Notes on yourself and colleagues, by category. Use the cycle field to track review periods.")
        sub.setProperty("class", "Muted")
        hh.addWidget(sub)

        # ZS Performance portal quick link
        perf_row = QHBoxLayout()
        perf_row.setContentsMargins(0, 6, 0, 0)
        perf_label = QLabel("📊  Submit final reviews on:")
        perf_label.setStyleSheet("font-size:12px;")
        perf_row.addWidget(perf_label)
        perf_btn = QPushButton("↗  ZS Performance Portal")
        perf_btn.setProperty("primary", True)
        perf_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        perf_btn.setToolTip("https://performance.zs.com/")
        perf_btn.clicked.connect(self._open_performance_portal)
        perf_row.addWidget(perf_btn)
        perf_row.addStretch()
        hh.addLayout(perf_row)

        self._outer.addWidget(header_host)

        # Splitter: subjects | category cards
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setHandleWidth(1)

        # Left: subjects list
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(16, 8, 8, 16); ll.setSpacing(6)
        ll.addWidget(QLabel("Subjects"))
        self.subjects_list = QListWidget()
        self.subjects_list.currentItemChanged.connect(self._on_subject_select)
        self.subjects_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.subjects_list.customContextMenuRequested.connect(self._show_subject_menu)
        ll.addWidget(self.subjects_list, 1)

        # Right: category cards
        right_scroll = ScrollContainer(self)
        right = right_scroll
        self._cat_host = QWidget()
        self._cat_layout = QVBoxLayout(self._cat_host)
        self._cat_layout.setContentsMargins(0, 0, 0, 0); self._cat_layout.setSpacing(10)
        right.add(self._cat_host)
        right.add_stretch()

        body.addWidget(left); body.addWidget(right)
        body.setSizes([230, 700])
        self._outer.addWidget(body, 1)

        self._current_subject_id: str | None = None
        self._refresh_subjects()
        # Auto-select first
        subjects = self._data()
        if subjects:
            self._select_subject(subjects[0]["id"])

    def _lock(self):
        self._unlocked = False
        self._build_locked_view()

    def _open_performance_portal(self):
        try:
            webbrowser.open("https://performance.zs.com/")
            self.ctx.notify("Opening ZS Performance Portal",
                            "https://performance.zs.com/",
                            sound="click", source="Reviews", user_initiated=True)
        except Exception as e:
            self.ctx.notify("Couldn't open browser", str(e)[:120],
                            sound="error", source="Reviews")

    # ---------- Data ----------
    def _data(self) -> list[dict]:
        return self.ctx.storage.load("module_reviews", [])

    def _save_all(self, subjects):
        self.ctx.storage.save("module_reviews", subjects)

    # ---------- Subjects ----------
    def _refresh_subjects(self):
        self.subjects_list.blockSignals(True)
        self.subjects_list.clear()
        for s in self._data():
            label = s.get("name", "Untitled")
            details = []
            if s.get("role"): details.append(s["role"])
            if s.get("cycle"): details.append(s["cycle"])
            if details:
                label += "  ·  " + ", ".join(details)
            item = QListWidgetItem(f"👤  {label}")
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            self.subjects_list.addItem(item)
            if s["id"] == self._current_subject_id:
                self.subjects_list.setCurrentItem(item)
        self.subjects_list.blockSignals(False)

    def add_subject(self):
        dlg = ReviewSubjectDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            subjects = self._data()
            new = dlg.value()
            subjects.append(new); self._save_all(subjects); self._refresh_subjects()
            self._select_subject(new["id"])

    def edit_subject(self, sid):
        subjects = self._data()
        target = next((s for s in subjects if s["id"] == sid), None)
        if not target: return
        dlg = ReviewSubjectDialog(self, subject=target)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new = dlg.value(); new["id"] = sid; new["points"] = target.get("points", {})
            new["created_at"] = target.get("created_at", new["created_at"])
            for i, s in enumerate(subjects):
                if s["id"] == sid: subjects[i] = new; break
            self._save_all(subjects); self._refresh_subjects(); self._select_subject(sid)

    def delete_subject(self, sid):
        subjects = self._data()
        target = next((s for s in subjects if s["id"] == sid), None)
        if not target: return
        if QMessageBox.question(self, "Delete subject",
                                f"Delete review notes for '{target['name']}'? This cannot be undone.",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                != QMessageBox.StandardButton.Yes:
            return
        subjects = [s for s in subjects if s["id"] != sid]
        self._save_all(subjects)
        if sid == self._current_subject_id:
            self._current_subject_id = None
            self._clear_categories()
        self._refresh_subjects()
        if subjects:
            self._select_subject(subjects[0]["id"])

    def _show_subject_menu(self, pos):
        item = self.subjects_list.itemAt(pos)
        if not item: return
        sid = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        a_edit = QAction("Edit subject…", self); a_edit.triggered.connect(lambda: self.edit_subject(sid))
        a_del  = QAction("Delete subject", self); a_del.triggered.connect(lambda: self.delete_subject(sid))
        menu.addAction(a_edit); menu.addSeparator(); menu.addAction(a_del)
        menu.exec(self.subjects_list.viewport().mapToGlobal(pos))

    def _on_subject_select(self, item, _prev):
        if not item: return
        sid = item.data(Qt.ItemDataRole.UserRole)
        self._select_subject(sid)

    def _select_subject(self, sid: str):
        self._current_subject_id = sid
        self._clear_categories()
        subject = next((s for s in self._data() if s["id"] == sid), None)
        if not subject: return
        # Render one card per category
        for cat_name, cat_icon in REVIEW_CATEGORIES:
            self._cat_layout.addWidget(self._build_category_card(subject, cat_name, cat_icon))

    def _clear_categories(self):
        while self._cat_layout.count():
            it = self._cat_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()

    def _build_category_card(self, subject, cat_name, cat_icon):
        card = QFrame(); card.setObjectName("GroupCard")
        layout = QVBoxLayout(card); layout.setContentsMargins(16, 12, 16, 12); layout.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel(f"{cat_icon}  {cat_name}"); title.setObjectName("GroupTitle")
        head.addWidget(title)
        points = subject.get("points", {}).get(cat_name, [])
        count = QLabel(f"{len(points)} point{'s' if len(points) != 1 else ''}")
        count.setObjectName("GroupCount")
        head.addWidget(count); head.addStretch()
        if points:
            copy_btn = QPushButton("📋  Copy")
            copy_btn.setProperty("ghost", True); copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            copy_btn.setToolTip(f"Copy this category's points to clipboard")
            copy_btn.clicked.connect(lambda _=False, s=subject, c=cat_name: self._copy_category(s, c))
            head.addWidget(copy_btn)
        layout.addLayout(head)

        # Existing points
        for i, point in enumerate(points):
            layout.addWidget(self._build_point_row(subject["id"], cat_name, i, point))

        # Add new point row
        add_row = QHBoxLayout()
        new_in = QPlainTextEdit()
        new_in.setPlaceholderText(f"Add a note for {cat_name}…")
        new_in.setMaximumHeight(60)
        add_btn = QPushButton("Add")
        add_btn.setProperty("primary", True)
        def _add(_=False, ed=new_in):
            text = ed.toPlainText().strip()
            if not text: return
            self._add_point(subject["id"], cat_name, text)
        add_btn.clicked.connect(_add)
        add_row.addWidget(new_in, 1)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)
        return card

    # ---------- Bulk copy ----------
    def _format_subject_markdown(self, subject: dict) -> str:
        """Format the subject's points as markdown — categories as headings,
        points as bullets. Empty categories are omitted."""
        lines = []
        header_bits = [subject.get("name") or "Untitled"]
        if subject.get("role"): header_bits.append(subject["role"])
        if subject.get("cycle"): header_bits.append(subject["cycle"])
        lines.append(f"# Review — {'  ·  '.join(header_bits)}")
        lines.append("")
        total_points = 0
        points_by_cat = subject.get("points", {}) or {}
        for cat_name, cat_icon in REVIEW_CATEGORIES:
            pts = points_by_cat.get(cat_name, [])
            if not pts: continue
            lines.append(f"## {cat_name}")
            for p in pts:
                txt = (p.get("text") or "").strip().replace("\n", " ")
                lines.append(f"- {txt}")
                total_points += 1
            lines.append("")
        if total_points == 0:
            lines.append("_(no points recorded yet)_")
        return "\n".join(lines).rstrip() + "\n"

    def _copy_current_subject(self):
        if not self._current_subject_id:
            self.ctx.notify("No subject selected", "Pick a subject first.", sound="error")
            return
        subject = next((s for s in self._data() if s["id"] == self._current_subject_id), None)
        if not subject:
            return
        text = self._format_subject_markdown(subject)
        QApplication.clipboard().setText(text)
        n_points = sum(len(v) for v in (subject.get("points", {}) or {}).values())
        self.ctx.notify("✓ Copied to clipboard",
                        f"{n_points} point{'s' if n_points != 1 else ''} from "
                        f"{subject.get('name', 'subject')} (with headings).",
                        sound="success", source="Reviews", user_initiated=True)

    def _copy_category(self, subject, cat_name):
        pts = subject.get("points", {}).get(cat_name, []) or []
        if not pts:
            return
        lines = [f"## {cat_name}"]
        for p in pts:
            txt = (p.get("text") or "").strip().replace("\n", " ")
            lines.append(f"- {txt}")
        QApplication.clipboard().setText("\n".join(lines) + "\n")
        self.ctx.notify("✓ Copied",
                        f"{cat_name}: {len(pts)} point{'s' if len(pts) != 1 else ''}",
                        sound="success", source="Reviews", user_initiated=True)

    def _build_point_row(self, sid, cat_name, idx, point):
        row = QFrame(); row.setObjectName("ItemRow")
        rl = QHBoxLayout(row); rl.setContentsMargins(8, 6, 8, 6); rl.setSpacing(8)

        text = QLabel(f"• {point.get('text', '')}")
        text.setWordWrap(True)
        text.setToolTip("Double-click to edit, or use the ✎ button.")
        text.setCursor(Qt.CursorShape.IBeamCursor)
        # Double-click on the text opens edit dialog
        def _dbl(_e=None, s=sid, c=cat_name, i=idx, p=point):
            self._edit_point(s, c, i, p)
        text.mouseDoubleClickEvent = lambda e, fn=_dbl: fn()
        rl.addWidget(text, 1)

        when = QLabel(point.get("at", "")[:10])
        when.setProperty("class", "Muted")
        when.setStyleSheet("font-size:11px;")
        when.setToolTip(point.get("at", ""))
        rl.addWidget(when)

        edit_btn = QPushButton("✎")
        edit_btn.setProperty("ghost", True); edit_btn.setFixedWidth(28)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setToolTip("Edit this point")
        edit_btn.clicked.connect(lambda _=False, s=sid, c=cat_name, i=idx, p=point:
                                 self._edit_point(s, c, i, p))
        rl.addWidget(edit_btn)

        del_btn = QPushButton("🗑"); del_btn.setProperty("ghost", True); del_btn.setFixedWidth(28)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("Delete this point")
        del_btn.clicked.connect(lambda _=False, s=sid, c=cat_name, i=idx:
                                self._delete_point(s, c, i))
        rl.addWidget(del_btn)
        return row

    def _edit_point(self, sid, cat_name, idx, point):
        """Pop a dialog to edit the text of an existing point."""
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QPlainTextEdit
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit · {cat_name}")
        dlg.setMinimumSize(520, 240)
        v = QVBoxLayout(dlg); v.setContentsMargins(16, 14, 16, 14); v.setSpacing(8)
        v.addWidget(QLabel(f"Editing point in {cat_name}:"))
        editor = QPlainTextEdit(point.get("text", ""))
        editor.setMinimumHeight(140)
        v.addWidget(editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setProperty("primary", True)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        v.addWidget(buttons)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_text = editor.toPlainText().strip()
        if not new_text:
            self.ctx.notify("Empty point", "Point text can't be empty. Use the trash icon to delete.",
                            sound="error", source="Reviews")
            return
        subjects = self._data()
        for s in subjects:
            if s["id"] == sid:
                points = s.get("points", {}).get(cat_name, [])
                if 0 <= idx < len(points):
                    points[idx]["text"] = new_text
                    points[idx]["updated_at"] = datetime.now().isoformat(timespec="seconds")
                break
        self._save_all(subjects)
        self._select_subject(sid)
        self.ctx.notify("Point updated", f"{cat_name}: edits saved.",
                        sound="success", source="Reviews", user_initiated=True)

    def _add_point(self, sid, cat_name, text):
        subjects = self._data()
        for s in subjects:
            if s["id"] == sid:
                s.setdefault("points", {}).setdefault(cat_name, []).append({
                    "text": text,
                    "at": datetime.now().isoformat(timespec="seconds"),
                })
                break
        self._save_all(subjects)
        # Re-render
        self._select_subject(sid)

    def _delete_point(self, sid, cat_name, idx):
        subjects = self._data()
        for s in subjects:
            if s["id"] == sid:
                points = s.get("points", {}).get(cat_name, [])
                if 0 <= idx < len(points):
                    points.pop(idx)
                break
        self._save_all(subjects)
        self._select_subject(sid)

    # ---------- Search ----------
    def register_search(self):
        # Searching reviews is sensitive — only expose subject names, not points
        def provider(query: str):
            if not self._unlocked: return []
            results = []
            for s in self._data():
                score = fuzzy_score(query, s.get("name", ""))
                if score > 0.3:
                    sid = s["id"]
                    results.append(SearchResult(
                        title=s["name"], subtitle="Review subject", category="Reviews",
                        icon="👤",
                        action=lambda x=sid: (self.ctx.navigate("reviews"), self._select_subject(x)),
                        score=score,
                    ))
            return results
        self.ctx.search.register("reviews", provider)

    def on_show(self):
        # Re-prompt for password every time the user navigates here in a new session.
        # Within a session, _unlocked stays True.
        if not self._unlocked:
            self._build_locked_view()
        else:
            # Refresh in case data changed
            self._refresh_subjects()
            if self._current_subject_id:
                self._select_subject(self._current_subject_id)
