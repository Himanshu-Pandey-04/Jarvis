"""
First-run tour — a guided introduction to JARVIS.

Shows a sequence of overlay cards walking through the main features:
sidebar nav, launchers, links, credentials, tasks, focus music, etc.

Triggered on first launch (or manually from Settings → "Take the tour").
Skipping or completing it sets a pref so it never auto-appears again.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PyQt6.QtCore import Qt


TOUR_STEPS = [
    {
        "icon": "🤖",
        "title": "Welcome to Jarvis",
        "body": (
            "Jarvis is your personal workbench — a faster way to launch tools, "
            "track tasks, take notes, and stay on top of the day.\n\n"
            "It's all local — no cloud, no telemetry. Data lives in your "
            "%APPDATA%\\Jarvis folder.\n\n"
            "Let's take a quick 90-second tour."
        ),
    },
    {
        "icon": "🧭",
        "title": "The sidebar",
        "body": (
            "Three sections in the sidebar:\n\n"
            "• Workspace — Dashboard, Launchers, AI Agents, Links, Documents, "
            "Notes, Templates, Credentials, Reviews, Automation Scripts\n\n"
            "• Tools — Tasks, Health, Timers, Focus Music, News & Weather\n\n"
            "• System — Notifications log, Settings\n\n"
            "Click a section header to collapse it. Your preference persists across sessions."
        ),
    },
    {
        "icon": "🚀",
        "title": "Launchers — your day in one click",
        "body": (
            "Launchers chain multiple steps into one button — opening a URL, "
            "running an app, copying a credential, all in sequence.\n\n"
            "Jarvis ships with launchers for Tableau, ZAIDYN ZDH, Migration, "
            "RDC Tools, and Azkaban Designer. Edit them or add your own."
        ),
    },
    {
        "icon": "🔑",
        "title": "Credentials — copy-and-go",
        "body": (
            "Store passwords for one-click clipboard copy. The clipboard "
            "auto-restores after 30 seconds, so you don't leave secrets sitting around.\n\n"
            "Pro tip: in Links and Launchers, the “Associated credentials” dropdown "
            "pulls names from here. Open a link and its password copies automatically."
        ),
    },
    {
        "icon": "✓",
        "title": "Tasks — to-dos + reminders",
        "body": (
            "Click ‘+ New task’. Pick a priority, set a due time, and choose recurrence "
            "from the Repeat dropdown.\n\n"
            "Choose ‘Every N…’ to repeat every N hours/days/working days/weeks — the "
            "Interval field shows up only for that option.\n\n"
            "Pre-loaded: Friday Time Entry, 6 PM book cab tomorrow, 6:55 PM cab logout, "
            "monthly LOS training. High-priority tasks flash the window and double-beep."
        ),
    },
    {
        "icon": "📝",
        "title": "Notes — markdown that stays out of the way",
        "body": (
            "Click ‘+ New note’ → type the title at the top → write below. "
            "Auto-saves every keystroke. The title in the sidebar updates immediately.\n\n"
            "Use the toolbar or Ctrl+B/I/K/1/2/3/S shortcuts. Toggle the live "
            "markdown preview with the 👁 button."
        ),
    },
    {
        "icon": "🔗",
        "title": "Links — grouped tiles with favicons",
        "body": (
            "Each link gets a favicon, an icon, an optional credential to copy on open, "
            "and lives in a group (Internal, SNOW, Cloud, etc).\n\n"
            "Need a new group? Click ‘➕ New group’ — it persists even when empty. "
            "Use the ☑ Select mode to bulk-move or bulk-delete. Use the 🗑 Delete group "
            "button on any card to remove a whole category."
        ),
    },
    {
        "icon": "🛠",
        "title": "Automation Scripts",
        "body": (
            "Drop your .py / .sh / .js / .sql / .ps1 files into one place. "
            "Add a script by uploading from your PC or paste code directly into the editor.\n\n"
            "Group them by purpose (e.g. ‘ETL’, ‘Cleanup’). Click any script to view/edit/copy. "
            "File-type badges show at a glance what each script is."
        ),
    },
    {
        "icon": "🎵",
        "title": "Focus Music",
        "body": (
            "Synthesized ambient sounds (noise tracks + binaural beats) play "
            "in-app on a loop. Curated YouTube playlists for real recordings.\n\n"
            "First play synthesizes the WAV in the background — takes 5–10s but "
            "your UI stays responsive. After that, instant playback."
        ),
    },
    {
        "icon": "⏳",
        "title": "Timers & history",
        "body": (
            "Quick presets: Pomodoro (25), Short break (5), Long break (15), "
            "Deep focus (50). Or create a custom-duration timer.\n\n"
            "Every timer you start gets logged. The history card at the bottom "
            "lets you pick any date and see what you worked on — total focused "
            "time, what completed, what was stopped early."
        ),
    },
    {
        "icon": "🔍",
        "title": "Search — Ctrl+K from anywhere",
        "body": (
            "Press Ctrl+K to fuzzy-search across launchers, links, notes, "
            "AI agents, credentials, news sources, and ambient sounds — all "
            "from one box. ESC to close."
        ),
    },
    {
        "icon": "⚙",
        "title": "Settings — themes, modules, your data",
        "body": (
            "Open Settings (bottom of the sidebar) to:\n\n"
            "• Switch themes — Dark, Light, Solarized, Consultant Blue, "
            "Midnight Forest, JARVIS HUD (animated neural background)\n"
            "• Control notification verbosity (Full / Titles only / Off)\n"
            "• Mute sounds (great for screen shares)\n"
            "• Enable/disable modules — sidebar updates instantly, no restart\n"
            "• Re-run this tour anytime from the ‘Take the tour’ button\n"
            "• Export/import all your data to JSON for backup"
        ),
    },
    {
        "icon": "🚀",
        "title": "You're set",
        "body": (
            "Updates: your customizations always survive. Renamed defaults stay "
            "renamed, custom links/notes/tasks/passwords are preserved across "
            "Jarvis releases.\n\n"
            "Welcome aboard. Click around and break things — you can always "
            "Reset all data from Settings → Danger zone."
        ),
    },
]


class TourDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Jarvis")
        self.setMinimumSize(540, 420)
        self.setModal(True)

        self._step = 0
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(28, 24, 28, 20)
        self._layout.setSpacing(12)

        # Icon + title
        head = QHBoxLayout()
        self.icon_lbl = QLabel("🤖")
        self.icon_lbl.setStyleSheet("font-size:42px;")
        head.addWidget(self.icon_lbl)
        title_col = QVBoxLayout(); title_col.setSpacing(2)
        self.title_lbl = QLabel("")
        self.title_lbl.setStyleSheet("font-size:20px; font-weight:700;")
        self.step_lbl = QLabel("")
        self.step_lbl.setProperty("class", "Muted")
        self.step_lbl.setStyleSheet("font-size:11px;")
        title_col.addWidget(self.title_lbl)
        title_col.addWidget(self.step_lbl)
        head.addLayout(title_col, 1)
        self._layout.addLayout(head)

        # Body
        self.body_lbl = QLabel("")
        self.body_lbl.setWordWrap(True)
        self.body_lbl.setStyleSheet("font-size:13px; line-height:1.5;")
        self.body_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._layout.addWidget(self.body_lbl, 1)

        # Buttons
        btn_row = QHBoxLayout()
        self.skip_btn = QPushButton("Skip tour")
        self.skip_btn.setProperty("ghost", True)
        self.skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.skip_btn)
        btn_row.addStretch()
        self.back_btn = QPushButton("← Back")
        self.back_btn.setProperty("ghost", True)
        self.back_btn.clicked.connect(self._on_back)
        btn_row.addWidget(self.back_btn)
        self.next_btn = QPushButton("Next →")
        self.next_btn.setProperty("primary", True)
        self.next_btn.setDefault(True)
        self.next_btn.clicked.connect(self._on_next)
        btn_row.addWidget(self.next_btn)
        self._layout.addLayout(btn_row)

        self._render()

    def _render(self):
        step = TOUR_STEPS[self._step]
        self.icon_lbl.setText(step["icon"])
        self.title_lbl.setText(step["title"])
        self.step_lbl.setText(f"Step {self._step + 1} of {len(TOUR_STEPS)}")
        self.body_lbl.setText(step["body"])
        self.back_btn.setEnabled(self._step > 0)
        if self._step == len(TOUR_STEPS) - 1:
            self.next_btn.setText("Got it ✓")
        else:
            self.next_btn.setText("Next →")

    def _on_back(self):
        if self._step > 0:
            self._step -= 1
            self._render()

    def _on_next(self):
        if self._step < len(TOUR_STEPS) - 1:
            self._step += 1
            self._render()
        else:
            self.accept()


def show_tour_if_needed(window, storage):
    """Show the tour if the user hasn't seen it yet. Returns True if shown."""
    prefs = storage.load("preferences", {}) or {}
    if prefs.get("tour_completed"):
        return False
    dlg = TourDialog(window)
    dlg.exec()
    prefs["tour_completed"] = True
    storage.save("preferences", prefs)
    return True


def show_tour_manual(window, storage):
    """Force-show the tour (called from Settings → ‘Take the tour’)."""
    dlg = TourDialog(window)
    dlg.exec()
    prefs = storage.load("preferences", {}) or {}
    prefs["tour_completed"] = True
    storage.save("preferences", prefs)
