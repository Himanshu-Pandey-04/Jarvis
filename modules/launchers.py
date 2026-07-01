"""
Launchers — environment-aware multi-step actions.

Each launcher is a recipe:
  - 0, 1, or 2 axes (e.g. Environment, Region) with selectable options
  - A list of typed steps that execute in order:
      open_url       — open a URL in the default browser
      open_path      — open a file/folder/exe with the OS default handler
      copy_password  — pull a password from the vault, copy to clipboard,
                       restore previous clipboard content after N seconds
      copy_text      — put a literal text on the clipboard
      run            — run a shell command (with optional cwd)
      delay          — wait N seconds before the next step

A step's value can be axis-keyed: e.g. value_map = {"Prod": "https://...", "Stg": "..."}
gets resolved at run time using the user's axis selections. For 2-axis launchers
the value_map_2d shape is {"APAC": {"Dev": "...", "Stg": "..."}, ...}.

This is the WorkBench equivalent of Jarvis's Tableau / CBRAT / Migration / RDC /
Azkaban launchers — generalized so the user can author new ones from the UI.
"""
import os
import subprocess
import sys
import uuid
import webbrowser
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QFrame, QWidget, QDialog, QDialogButtonBox, QMessageBox, QMenu,
    QFormLayout, QListWidget, QListWidgetItem, QPlainTextEdit, QSpinBox, QTabWidget,
    QApplication, QFileDialog, QSizePolicy, QScrollArea,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QCursor

from modules.base import Module
from ui.widgets import SectionHeader, Card, ScrollContainer, EmptyState
from core.search import SearchResult, fuzzy_score


STEP_TYPES = [
    ("open_url",       "Open URL"),
    ("open_path",      "Open file / folder / app"),
    ("copy_password",  "Copy password from vault"),
    ("copy_text",      "Copy text to clipboard"),
    ("run",            "Run shell command"),
    ("delay",          "Wait (seconds)"),
]
STEP_TYPE_LABELS = dict(STEP_TYPES)


# ============================================================================
# Step runner
# ============================================================================

class LauncherRunner:
    """
    Runs a launcher's steps in order. Handles async steps (delay, copy_password)
    by chaining via QTimer / callbacks instead of blocking the UI thread.
    """
    def __init__(self, ctx, launcher: dict, axis_selections: dict[str, str],
                 on_complete=None):
        self.ctx = ctx
        self.launcher = launcher
        self.axis_selections = axis_selections
        self.queue = list(launcher.get("steps", []))
        self._total_steps = len(self.queue)
        self._current_step_idx = 0
        self.aborted = False
        self.on_complete = on_complete

    def start(self):
        if self._total_steps > 0:
            name = self.launcher.get("name", "Launcher")
            self.ctx.status(f"Running {name} — {self._total_steps} step(s)",
                            icon="▶", auto_hide=False)
        self._run_next()

    def _report_step(self, label: str):
        """Show live progress in the status strip — one line, replaces previous."""
        name = self.launcher.get("name", "Launcher")
        text = f"{name} — Step {self._current_step_idx}/{self._total_steps}: {label}"
        self.ctx.status(text, icon="▶", auto_hide=False)

    def _report_done(self, success: bool, msg: str = ""):
        name = self.launcher.get("name", "Launcher")
        if success:
            self.ctx.status(f"{name} — done", icon="✓", auto_hide=True)
        else:
            self.ctx.status(f"{name} — {msg}"[:120], icon="⚠", auto_hide=True)

    # ----- helpers -----
    def _resolve_value(self, step: dict) -> str:
        """Pick the right value for this step based on launcher axes."""
        axes = self.launcher.get("axes", []) or []
        if len(axes) == 0:
            return step.get("value", "") or ""
        if len(axes) == 1:
            label = axes[0]["label"]
            sel = self.axis_selections.get(label, "")
            vmap = step.get("value_map", {}) or {}
            return vmap.get(sel, step.get("value", "") or "")
        # 2 axes
        l1, l2 = axes[0]["label"], axes[1]["label"]
        s1 = self.axis_selections.get(l1, "")
        s2 = self.axis_selections.get(l2, "")
        v2 = step.get("value_map_2d", {}) or {}
        inner = v2.get(s1, {}) or {}
        return inner.get(s2, step.get("value", "") or "")

    # ----- execution loop -----
    def _run_next(self):
        if self.aborted:
            return
        if not self.queue:
            self._report_done(success=True)
            if self.on_complete:
                try:
                    self.on_complete()
                except Exception:
                    pass
            return
        step = self.queue.pop(0)
        self._current_step_idx += 1
        kind = step.get("type", "")
        label = step.get("label") or kind
        self._report_step(label)
        try:
            handler = getattr(self, f"_handle_{kind}", None)
            if not handler:
                # Skip unknown step types and continue rather than abort
                self._report_done(False, f"Unknown step '{kind}'")
                return self._run_next()
            handler(step)
        except Exception as e:
            self._report_done(False, str(e)[:80])
            self.aborted = True

    # ----- step handlers -----
    def _handle_open_url(self, step):
        url = self._resolve_value(step).strip()
        if not url:
            self.ctx.status(f"Step skipped: no URL set", icon="⚠")
            return self._run_next()

        opened = False
        last_err = ""

        # Convert file:// URLs to a local path; use pathlib.Path.as_uri() to
        # produce the canonical URI form that browsers expect.
        local_path = None
        if url.lower().startswith("file:///") or url.lower().startswith("file://"):
            from urllib.parse import unquote, quote
            from pathlib import Path, PureWindowsPath
            # Strip prefix
            if url.lower().startswith("file:///"):
                raw = unquote(url[len("file:///"):])
            else:
                raw = unquote(url[len("file://"):])
            try:
                # Detect Windows-style path (e.g. "C:/..." or "C:\...") regardless
                # of host OS — important for cross-platform handling.
                is_windows_path = (len(raw) >= 2 and raw[1] == ":") or "\\" in raw
                if is_windows_path:
                    # Use PureWindowsPath to handle the path correctly even on Linux.
                    wp = PureWindowsPath(raw)
                    # Build canonical file:// URI manually for Windows paths
                    canonical_url = "file:///" + quote(str(wp).replace("\\", "/"), safe="/:")
                    local_path = wp
                else:
                    local_path = Path(raw)
                    if local_path.is_absolute():
                        canonical_url = local_path.as_uri()
                    else:
                        canonical_url = url  # fall back to original
            except Exception as e:
                last_err = f"path parse: {e}"
                canonical_url = url
        else:
            canonical_url = url

        # Strategy 1: webbrowser.open() with canonical URL (works for http and file)
        try:
            if webbrowser.open(canonical_url, new=2):
                opened = True
        except Exception as e:
            last_err = f"webbrowser: {e}"

        # Strategy 2 (Windows file fallback): os.startfile() on local path
        if not opened and local_path is not None and os.name == "nt":
            try:
                os.startfile(str(local_path))  # type: ignore[attr-defined]
                opened = True
            except Exception as e:
                last_err = f"startfile: {e}"

        # Strategy 3 (Windows): explicit `cmd /c start "" <path>`
        if not opened and local_path is not None and os.name == "nt":
            try:
                subprocess.Popen(["cmd", "/c", "start", "", str(local_path)], shell=False)
                opened = True
            except Exception as e:
                last_err = f"start cmd: {e}"

        # Strategy 4 (macOS): `open`
        if not opened and local_path is not None and sys.platform == "darwin":
            try:
                subprocess.Popen(["open", str(local_path)])
                opened = True
            except Exception as e:
                last_err = f"open: {e}"

        # Strategy 5 (Linux): `xdg-open`
        if not opened and local_path is not None and os.name == "posix":
            try:
                subprocess.Popen(["xdg-open", str(local_path)])
                opened = True
            except Exception as e:
                last_err = f"xdg-open: {e}"

        if not opened:
            self.ctx.status(f"Couldn't open URL: {last_err[:80]}", icon="⚠")
            self.ctx.notify("Couldn't open URL",
                            f"All strategies failed.\n\nURL: {url}\n\nError: {last_err}",
                            sound="error", source="Launchers")
        self._run_next()

    def _handle_open_path(self, step):
        path = self._resolve_value(step).strip()
        if not path:
            self.ctx.status(f"Step skipped: no path set", icon="⚠")
            return self._run_next()
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self.ctx.status(f"Couldn't open path: {str(e)[:60]}", icon="⚠")
        self._run_next()

    def _handle_copy_text(self, step):
        text = self._resolve_value(step)
        QApplication.clipboard().setText(text)
        # Use status instead of toast to avoid spam during chains
        self.ctx.status(f"Copied: {step.get('label', 'text')}", icon="📋")
        self._run_next()

    def _handle_copy_password(self, step):
        entry_name = (step.get("extra") or "").strip()
        try:
            restore_after = int((self._resolve_value(step) or "60").strip() or "60")
        except ValueError:
            restore_after = 60
        if not entry_name:
            self.ctx.status("copy_password step has no vault entry name", icon="⚠")
            return self._run_next()
        self.ctx.copy_password_with_restore(
            entry_name, restore_after,
            on_done=self._run_next,
            on_error=lambda reason: (self.ctx.status(f"{reason[:80]}", icon="✗"),
                                      setattr(self, "aborted", True)),
        )

    def _handle_run(self, step):
        cmd = self._resolve_value(step).strip()
        cwd = (step.get("extra") or "").strip() or None
        if not cmd:
            self.ctx.status("Step skipped: no command", icon="⚠")
            return self._run_next()
        try:
            # shell=True so users can write commands like "python backend.py" naturally
            subprocess.Popen(cmd, shell=True, cwd=cwd)
        except Exception as e:
            self.ctx.status(f"Run failed: {str(e)[:60]}", icon="⚠")
        # Always continue the chain even if Popen had issues
        self._run_next()

    def _handle_delay(self, step):
        try:
            secs = float((self._resolve_value(step) or "0").strip() or "0")
        except ValueError:
            secs = 0
        if secs <= 0:
            return self._run_next()
        # Status strip has its own icon column — don't duplicate ⏳ in text
        self.ctx.status(f"Waiting {secs:.0f}s before next step…",
                        icon="⏳", auto_hide=False)
        QTimer.singleShot(int(secs * 1000), self._run_next)


# ============================================================================
# Launcher card — one card per launcher on the launchers page
# ============================================================================

class LauncherCard(Card):
    AXIS_BUTTON_THRESHOLD = 4  # <4 options → buttons, ≥4 → dropdown

    def __init__(self, launcher: dict, ctx, on_edit, on_delete, on_pin):
        super().__init__()
        self.launcher = launcher
        self.ctx = ctx
        # axis label → ("dropdown"|"buttons", widget-or-list)
        self._axis_state: dict[str, tuple[str, object]] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        # Header row: icon + name + action menu
        hrow = QHBoxLayout()
        title = QLabel(f"{launcher.get('icon','▶')}  {launcher.get('name', 'Launcher')}")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        if launcher.get("description"):
            title.setToolTip(launcher["description"])
        hrow.addWidget(title, 1)

        menu_btn = QPushButton("⋯")
        menu_btn.setProperty("ghost", True)
        menu_btn.setFixedWidth(32)
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self)
        edit_a = QAction("Edit…", self); edit_a.triggered.connect(lambda: on_edit(self.launcher))
        pin_a = QAction("Pin to dashboard", self); pin_a.triggered.connect(lambda: on_pin(self.launcher))
        del_a = QAction("Delete", self); del_a.triggered.connect(lambda: on_delete(self.launcher))
        menu.addAction(pin_a); menu.addAction(edit_a); menu.addSeparator(); menu.addAction(del_a)
        menu_btn.setMenu(menu)
        hrow.addWidget(menu_btn)
        layout.addLayout(hrow)

        # Description
        desc = launcher.get("description", "")
        if desc:
            d_lbl = QLabel(desc)
            d_lbl.setProperty("class", "Muted")
            d_lbl.setWordWrap(True)
            layout.addWidget(d_lbl)

        # Cred-ref hint
        cred_ref = launcher.get("cred_ref", "")
        if cred_ref:
            cred_lbl = QLabel(f"🔑  associated credentials: {cred_ref}")
            cred_lbl.setProperty("class", "Muted")
            cred_lbl.setStyleSheet("font-size: 11px;")
            layout.addWidget(cred_lbl)

        # Axes — buttons for short option lists, dropdown for long
        for axis in launcher.get("axes", []) or []:
            options = axis.get("options", [])
            label = axis["label"]
            if 0 < len(options) < self.AXIS_BUTTON_THRESHOLD:
                # Inline button row
                row_lbl = QLabel(label + ":"); row_lbl.setProperty("class", "Muted")
                row_lbl.setStyleSheet("font-size: 12px;")
                layout.addWidget(row_lbl)
                btn_row = QHBoxLayout(); btn_row.setSpacing(6)
                btn_list: list[QPushButton] = []
                for i, opt in enumerate(options):
                    b = QPushButton(opt)
                    b.setProperty("axisbtn", True)
                    b.setProperty("selected", i == 0)
                    b.setCheckable(True)
                    b.setChecked(i == 0)
                    b.setCursor(Qt.CursorShape.PointingHandCursor)
                    def _select(_=False, _b=b, _list=btn_list):
                        for other in _list:
                            other.setChecked(other is _b)
                            other.setProperty("selected", other is _b)
                            # Force style refresh on property change
                            other.style().unpolish(other); other.style().polish(other)
                    b.clicked.connect(_select)
                    btn_row.addWidget(b)
                    btn_list.append(b)
                btn_row.addStretch()
                layout.addLayout(btn_row)
                self._axis_state[label] = ("buttons", btn_list)
            elif options:
                # Dropdown
                drow = QHBoxLayout()
                lbl = QLabel(label + ":"); lbl.setProperty("class", "Muted")
                drow.addWidget(lbl)
                combo = QComboBox()
                combo.addItems(options)
                drow.addWidget(combo, 1)
                layout.addLayout(drow)
                self._axis_state[label] = ("dropdown", combo)

        # Step summary (small, grey)
        steps = launcher.get("steps", []) or []
        if steps:
            summary = "  →  ".join(STEP_TYPE_LABELS.get(s.get("type", ""), s.get("type", "?"))
                                    for s in steps)
            s_lbl = QLabel(summary)
            s_lbl.setProperty("class", "Muted")
            s_lbl.setStyleSheet("font-size: 11px;")
            s_lbl.setWordWrap(True)
            layout.addWidget(s_lbl)

        # Run button
        run_btn = QPushButton(f"  ▶   Run")
        run_btn.setProperty("primary", True)
        run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        run_btn.setMinimumHeight(34)
        run_btn.clicked.connect(self.run)
        layout.addWidget(run_btn, alignment=Qt.AlignmentFlag.AlignLeft)

    def current_selections(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for label, (kind, w) in self._axis_state.items():
            if kind == "buttons":
                # w is list of QPushButton
                selected = next((b for b in w if b.isChecked()), None)
                out[label] = selected.text() if selected else ""
            else:
                out[label] = w.currentText()
        return out

    def run(self):
        self.ctx.play_sound("click")
        sels = self.current_selections()
        # Keep a strong reference so the async chain isn't GC'd mid-flight.
        # Stored as an attribute on the dialog instance.
        self._active_runner = LauncherRunner(self.ctx, self.launcher, sels,
                                              on_complete=self._on_run_complete)
        self._active_runner.start()

    def _on_run_complete(self):
        # Auto-copy associated credentials after the launcher completes
        cred_ref = (self.launcher.get("cred_ref") or "").strip()
        if cred_ref:
            self.ctx.copy_password_with_restore(cred_ref, restore_after=60)


# ============================================================================
# Editor dialog — supports 0/1/2 axes and any number of steps
# ============================================================================

class StepRow(QWidget):
    """One row in the steps editor. Type dropdown + dynamic value field(s)."""
    def __init__(self, step: dict, axes: list[dict], on_change_callback, on_remove, parent=None):
        super().__init__(parent)
        self.step = dict(step)  # copy
        self.axes = axes
        self.on_change_callback = on_change_callback
        self.on_remove = on_remove

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self.setStyleSheet("StepRow { border: 1px solid palette(mid); border-radius: 6px; }")

        head = QHBoxLayout()
        self.type_combo = QComboBox()
        for tid, tlabel in STEP_TYPES:
            self.type_combo.addItem(tlabel, tid)
        self.type_combo.setCurrentIndex(self._index_for_type(step.get("type", "open_url")))
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)

        self.label_in = QLineEdit(step.get("label", ""))
        self.label_in.setPlaceholderText("Step label (shown to user)")
        self.label_in.textChanged.connect(self._sync_step)

        rm_btn = QPushButton("✕"); rm_btn.setFixedWidth(28); rm_btn.setProperty("ghost", True)
        rm_btn.clicked.connect(lambda: self.on_remove(self))

        head.addWidget(QLabel("Type:")); head.addWidget(self.type_combo)
        head.addSpacing(8); head.addWidget(QLabel("Label:")); head.addWidget(self.label_in, 1)
        head.addWidget(rm_btn)
        layout.addLayout(head)

        # Value area — built dynamically based on type + axes
        self.value_host = QWidget()
        self.value_layout = QVBoxLayout(self.value_host)
        self.value_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.value_host)

        self._build_value_area()

    def _index_for_type(self, t: str) -> int:
        for i, (tid, _) in enumerate(STEP_TYPES):
            if tid == t:
                return i
        return 0

    def _on_type_changed(self, *_):
        self.step["type"] = self.type_combo.currentData()
        self._build_value_area()
        self._sync_step()

    def refresh_axes(self, axes: list[dict]):
        """Called by the parent dialog when axes change."""
        self.axes = axes
        self._build_value_area()

    def _clear_value_area(self):
        while self.value_layout.count():
            it = self.value_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _build_value_area(self):
        self._clear_value_area()
        kind = self.type_combo.currentData()
        self._value_widgets: dict = {}  # used by _sync_step

        if kind == "copy_password":
            # extra = vault entry name; value = restore seconds (no axis support)
            row = QFormLayout()
            self.entry_in = QLineEdit(self.step.get("extra", ""))
            self.entry_in.setPlaceholderText("Vault entry name (e.g. PC, ZS-SER, BI)")
            self.entry_in.textChanged.connect(self._sync_step)
            self.restore_in = QSpinBox()
            self.restore_in.setRange(5, 600); self.restore_in.setSuffix("  s")
            try:
                self.restore_in.setValue(int(self.step.get("value", "60") or 60))
            except ValueError:
                self.restore_in.setValue(60)
            self.restore_in.valueChanged.connect(self._sync_step)
            row.addRow("Vault entry", self.entry_in)
            row.addRow("Restore previous clipboard after", self.restore_in)
            host = QWidget(); host.setLayout(row); self.value_layout.addWidget(host)
            return

        if kind == "delay":
            row = QFormLayout()
            self.delay_in = QSpinBox()
            self.delay_in.setRange(0, 600); self.delay_in.setSuffix("  s")
            try:
                self.delay_in.setValue(int(float(self.step.get("value", "0") or 0)))
            except ValueError:
                self.delay_in.setValue(0)
            self.delay_in.valueChanged.connect(self._sync_step)
            row.addRow("Wait", self.delay_in)
            host = QWidget(); host.setLayout(row); self.value_layout.addWidget(host)
            return

        if kind == "run":
            row = QFormLayout()
            self.cmd_in = QLineEdit(self.step.get("value", ""))
            self.cmd_in.setPlaceholderText('e.g. python backend_1.py  or  npm start')
            self.cmd_in.textChanged.connect(self._sync_step)
            self.cwd_in = QLineEdit(self.step.get("extra", ""))
            self.cwd_in.setPlaceholderText("Working directory (optional)")
            self.cwd_in.textChanged.connect(self._sync_step)
            row.addRow("Command", self.cmd_in)
            row.addRow("Run from folder", self.cwd_in)
            host = QWidget(); host.setLayout(row); self.value_layout.addWidget(host)
            return

        # open_url / open_path / copy_text — these support axis-keyed values
        if not self.axes:
            row = QFormLayout()
            self.value_in = QLineEdit(self.step.get("value", ""))
            self.value_in.setPlaceholderText(self._placeholder_for(kind))
            self.value_in.textChanged.connect(self._sync_step)
            row.addRow("Value", self.value_in)
            host = QWidget(); host.setLayout(row); self.value_layout.addWidget(host)
            return

        if len(self.axes) == 1:
            ax = self.axes[0]
            opts = ax.get("options", [])
            grid_host = QFrame()
            grid = QGridLayout(grid_host); grid.setContentsMargins(0, 0, 0, 0)
            head_lbl = QLabel(f"Per {ax['label']}:")
            head_lbl.setProperty("class", "Muted")
            grid.addWidget(head_lbl, 0, 0, 1, 2)
            existing = self.step.get("value_map", {}) or {}
            self._value_widgets["map"] = {}
            for i, opt in enumerate(opts):
                lbl = QLabel(opt)
                edit = QLineEdit(existing.get(opt, ""))
                edit.setPlaceholderText(self._placeholder_for(kind))
                edit.textChanged.connect(self._sync_step)
                grid.addWidget(lbl, i + 1, 0)
                grid.addWidget(edit, i + 1, 1)
                self._value_widgets["map"][opt] = edit
            grid.setColumnStretch(1, 1)
            self.value_layout.addWidget(grid_host)
            return

        # 2 axes
        ax1, ax2 = self.axes[0], self.axes[1]
        existing_2d = self.step.get("value_map_2d", {}) or {}
        self._value_widgets["map_2d"] = {}
        grid_host = QFrame()
        grid = QGridLayout(grid_host); grid.setContentsMargins(0, 0, 0, 0)
        head = QLabel(f"Per {ax1['label']} × {ax2['label']}:")
        head.setProperty("class", "Muted")
        grid.addWidget(head, 0, 0, 1, 3)
        # Header row
        for j, opt2 in enumerate(ax2.get("options", [])):
            grid.addWidget(QLabel(opt2), 1, j + 1)
        for i, opt1 in enumerate(ax1.get("options", [])):
            grid.addWidget(QLabel(opt1), i + 2, 0)
            self._value_widgets["map_2d"].setdefault(opt1, {})
            for j, opt2 in enumerate(ax2.get("options", [])):
                val = (existing_2d.get(opt1, {}) or {}).get(opt2, "")
                edit = QLineEdit(val)
                edit.setPlaceholderText(self._placeholder_for(kind))
                edit.textChanged.connect(self._sync_step)
                grid.addWidget(edit, i + 2, j + 1)
                self._value_widgets["map_2d"][opt1][opt2] = edit
        grid.setColumnStretch(1, 1)
        self.value_layout.addWidget(grid_host)

    def _placeholder_for(self, kind: str) -> str:
        if kind == "open_url":  return "https://example.com"
        if kind == "open_path": return r"C:\path\to\file_or_app.exe"
        if kind == "copy_text": return "Text to put on clipboard"
        return ""

    def _sync_step(self, *_):
        kind = self.type_combo.currentData()
        self.step["type"] = kind
        self.step["label"] = self.label_in.text().strip()

        # Reset the variants this step doesn't use
        self.step["value"] = ""
        self.step["value_map"] = {}
        self.step["value_map_2d"] = {}
        self.step["extra"] = ""

        if kind == "copy_password":
            self.step["extra"] = getattr(self, "entry_in", QLineEdit()).text().strip()
            self.step["value"] = str(getattr(self, "restore_in", QSpinBox()).value())
        elif kind == "delay":
            self.step["value"] = str(getattr(self, "delay_in", QSpinBox()).value())
        elif kind == "run":
            self.step["value"] = getattr(self, "cmd_in", QLineEdit()).text().strip()
            self.step["extra"] = getattr(self, "cwd_in", QLineEdit()).text().strip()
        else:
            # open_url / open_path / copy_text — use axes
            if not self.axes:
                self.step["value"] = getattr(self, "value_in", QLineEdit()).text().strip()
            elif len(self.axes) == 1 and "map" in self._value_widgets:
                self.step["value_map"] = {opt: w.text().strip()
                                          for opt, w in self._value_widgets["map"].items()}
            elif len(self.axes) == 2 and "map_2d" in self._value_widgets:
                m: dict[str, dict[str, str]] = {}
                for opt1, sub in self._value_widgets["map_2d"].items():
                    m[opt1] = {opt2: w.text().strip() for opt2, w in sub.items()}
                self.step["value_map_2d"] = m

        if self.on_change_callback:
            self.on_change_callback()


class LauncherEditDialog(QDialog):
    def __init__(self, parent=None, launcher: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit launcher" if launcher else "New launcher")
        self.setMinimumSize(720, 600)
        self._existing_launcher = launcher
        self._step_rows: list[StepRow] = []

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        # ---- Basics ----
        basics = QFormLayout()
        self.name_in = QLineEdit((launcher or {}).get("name", ""))
        self.icon_in = QLineEdit((launcher or {}).get("icon", "▶")); self.icon_in.setMaxLength(4)
        self.desc_in = QLineEdit((launcher or {}).get("description", ""))
        self.cred_ref_in = QLineEdit((launcher or {}).get("cred_ref", ""))
        self.cred_ref_in.setPlaceholderText("Optional — vault entry name to copy after run (e.g. PC, BI)")
        basics.addRow("Name", self.name_in)
        basics.addRow("Icon (emoji)", self.icon_in)
        basics.addRow("Description", self.desc_in)
        basics.addRow("Associated credentials", self.cred_ref_in)
        outer.addLayout(basics)

        # ---- Axes ----
        axes_box = QFrame(); axes_box.setProperty("class", "Card")
        axes_layout = QVBoxLayout(axes_box); axes_layout.setContentsMargins(14, 12, 14, 12); axes_layout.setSpacing(6)
        ax_title = QLabel("Selectors (optional)")
        ax_title.setStyleSheet("font-weight: 600;")
        axes_layout.addWidget(ax_title)
        ax_hint = QLabel("Up to two dropdowns shown on the launcher card. "
                         "Their selections control what each step does.")
        ax_hint.setProperty("class", "Muted"); ax_hint.setWordWrap(True)
        axes_layout.addWidget(ax_hint)

        existing_axes = (launcher or {}).get("axes", []) or []
        self.axis_widgets: list[tuple[QLineEdit, QLineEdit]] = []
        for i in range(2):
            row = QHBoxLayout()
            ax = existing_axes[i] if i < len(existing_axes) else None
            label_in = QLineEdit(ax["label"] if ax else "")
            label_in.setPlaceholderText(f"Axis {i+1} label  (e.g. Environment)")
            opts_in = QLineEdit(", ".join(ax["options"]) if ax else "")
            opts_in.setPlaceholderText(f"Comma-separated options  (e.g. Dev, Stg, Prod)")
            label_in.textChanged.connect(self._on_axis_changed)
            opts_in.textChanged.connect(self._on_axis_changed)
            row.addWidget(label_in, 1); row.addWidget(opts_in, 2)
            axes_layout.addLayout(row)
            self.axis_widgets.append((label_in, opts_in))
        outer.addWidget(axes_box)

        # ---- Steps ----
        steps_header = QHBoxLayout()
        st_lbl = QLabel("Steps  ·  run top to bottom")
        st_lbl.setStyleSheet("font-weight: 600;")
        steps_header.addWidget(st_lbl, 1)
        add_btn = QPushButton("+  Add step"); add_btn.clicked.connect(self._add_step_row)
        steps_header.addWidget(add_btn)
        outer.addLayout(steps_header)

        self.steps_scroll = QScrollArea()
        self.steps_scroll.setWidgetResizable(True)
        self.steps_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.steps_inner = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_inner)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(8)
        self.steps_scroll.setWidget(self.steps_inner)
        outer.addWidget(self.steps_scroll, 1)

        # Existing steps or one empty step
        existing_steps = (launcher or {}).get("steps", []) or []
        if existing_steps:
            for s in existing_steps:
                self._add_step_row(s)
        else:
            self._add_step_row()

        # ---- Buttons ----
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _current_axes(self) -> list[dict]:
        out = []
        for label_in, opts_in in self.axis_widgets:
            label = label_in.text().strip()
            opts_raw = opts_in.text()
            opts = [o.strip() for o in opts_raw.split(",") if o.strip()]
            if label and opts:
                out.append({"label": label, "options": opts})
        return out

    def _on_axis_changed(self, *_):
        axes = self._current_axes()
        for row in self._step_rows:
            row.refresh_axes(axes)
            row._sync_step()

    def _add_step_row(self, step: dict | None = None):
        step = step or {"type": "open_url", "label": "", "value": "",
                        "value_map": {}, "value_map_2d": {}, "extra": ""}
        row = StepRow(step, self._current_axes(), self._on_step_changed, self._remove_step_row)
        self._step_rows.append(row)
        self.steps_layout.addWidget(row)

    def _remove_step_row(self, row: StepRow):
        if row in self._step_rows:
            self._step_rows.remove(row)
        row.deleteLater()

    def _on_step_changed(self):
        pass  # No-op for now; values flush directly into row.step

    def value(self) -> dict:
        existing = self._existing_launcher or {}
        return {
            "id":          existing.get("id") or uuid.uuid4().hex,
            "name":        self.name_in.text().strip() or "Launcher",
            "icon":        self.icon_in.text().strip() or "▶",
            "description": self.desc_in.text().strip(),
            "section":     existing.get("section", "Workspace"),
            "cred_ref":    self.cred_ref_in.text().strip(),
            "axes":        self._current_axes(),
            "steps":       [r.step for r in self._step_rows],
        }


# ============================================================================
# The module
# ============================================================================

class LaunchersModule(Module):
    MODULE_ID = "launchers"
    NAME = "Launchers"
    ICON = "🚀"
    SECTION = "Workspace"
    DESCRIPTION = "Environment-aware multi-step actions: open URLs, files, copy passwords, run commands."

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = ScrollContainer(self)

        header = SectionHeader(
            "Launchers",
            "One-click recipes for the things you do every day — "
            "Tableau by env, RDC + password copy, multi-step migrations.",
            action_text="+  New launcher",
        )
        header.action_clicked.connect(self.add_launcher)
        scroll.add(header)

        # Filter bar
        filter_card = Card()
        fl = QHBoxLayout(filter_card); fl.setContentsMargins(14, 10, 14, 10)
        self.filter_in = QLineEdit()
        self.filter_in.setPlaceholderText("Filter launchers…")
        self.filter_in.textChanged.connect(self._refresh)
        fl.addWidget(self.filter_in)
        scroll.add(filter_card)

        # Grid host
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)
        scroll.add(self.grid_host)

        scroll.add_stretch()
        outer.addWidget(scroll)

        self._refresh()

    # ---------- Data ----------
    def _data(self) -> list[dict]:
        return self.load_data(default=[])

    def _save(self, items: list[dict]):
        self.save_data(items)

    # ---------- Render ----------
    def _refresh(self):
        # Clear existing
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        items = self._data()
        q = self.filter_in.text().strip().lower()
        if q:
            items = [L for L in items
                     if q in L.get("name", "").lower()
                     or q in L.get("description", "").lower()]

        if not items:
            empty = EmptyState(
                "🚀", "No launchers yet",
                "Click ‘+ New launcher’ to build a recipe — for example, "
                "‘Open Tableau’ with a Prod/Stg dropdown, or "
                "‘Open RDC + copy PC password’. "
                "Or import your existing Jarvis configs from Settings → Data."
            )
            self.grid.addWidget(empty, 0, 0, 1, 2)
            return

        cols = 2
        for idx, L in enumerate(items):
            card = LauncherCard(L, self.ctx,
                                 on_edit=self._edit_launcher,
                                 on_delete=self._delete_launcher,
                                 on_pin=self._pin_launcher)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.grid.addWidget(card, idx // cols, idx % cols)
        # Final stretch row so cards don't get vertically stretched
        self.grid.setRowStretch(self.grid.rowCount(), 1)

    # ---------- CRUD ----------
    def add_launcher(self):
        dlg = LauncherEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            v = dlg.value()
            items = self._data(); items.append(v); self._save(items)
            self._refresh()

    def _edit_launcher(self, launcher: dict):
        dlg = LauncherEditDialog(self, launcher=launcher)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            v = dlg.value()
            items = self._data()
            for i, L in enumerate(items):
                if L.get("id") == launcher.get("id"):
                    # Preserve default_key (identity) but mark user-owned now
                    if L.get("default_key"):
                        v["default_key"] = L["default_key"]
                    v["from_defaults"] = False
                    items[i] = v; break
            self._save(items)
            self._refresh()

    def _delete_launcher(self, launcher: dict):
        if QMessageBox.question(self, "Delete launcher", f"Delete '{launcher['name']}'?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                != QMessageBox.StandardButton.Yes:
            return
        items = [L for L in self._data() if L.get("id") != launcher.get("id")]
        self._save(items)
        self._refresh()

    def _pin_launcher(self, launcher: dict):
        pins = self.ctx.storage.load("pinned_items", [])
        if any(p.get("kind") == "launcher" and p.get("ref") == launcher.get("id") for p in pins):
            self.ctx.notify("Already pinned", launcher.get("name", ""), user_initiated=True)
            return
        pins.append({"kind": "launcher", "ref": launcher["id"],
                     "name": launcher.get("name", "Launcher"),
                     "icon": launcher.get("icon", "🚀")})
        self.ctx.storage.save("pinned_items", pins)
        self.ctx.notify("Pinned to dashboard", launcher.get("name", ""), user_initiated=True)

    # ---------- Public — used by dashboard pin & search ----------
    def run_launcher_by_id(self, launcher_id: str, axis_selections: dict[str, str] | None = None):
        for L in self._data():
            if L.get("id") == launcher_id:
                if not L.get("axes") or axis_selections is None:
                    # Use the first option for each axis
                    sels = {ax["label"]: (ax.get("options") or [""])[0] for ax in L.get("axes", [])}
                else:
                    sels = axis_selections
                LauncherRunner(self.ctx, L, sels).start()
                return True
        return False

    # ---------- Search integration ----------
    def register_search(self):
        def provider(query: str) -> list[SearchResult]:
            results = []
            for L in self._data():
                score = max(
                    fuzzy_score(query, L.get("name", "")),
                    fuzzy_score(query, L.get("description", "")) * 0.5,
                )
                if score > 0.25:
                    lid = L["id"]
                    name = L.get("name", "")
                    icon = L.get("icon", "🚀")
                    desc = L.get("description", "")
                    has_axes = bool(L.get("axes"))
                    sub = ("Run with default selection · " if has_axes else "Run · ") + desc
                    results.append(SearchResult(
                        title=f"Run {name}",
                        subtitle=sub,
                        category="Launcher",
                        icon=icon,
                        action=lambda lid=lid: self.run_launcher_by_id(lid),
                        score=score,
                    ))
            return results
        self.ctx.search.register("launchers", provider)

    def on_show(self):
        self._refresh()
