"""
Focus Music — ambient sounds (offline) + user-editable YouTube playlists.

Ambient sounds are synthesized on first play and looped seamlessly via
QMediaPlayer. New defaults this build:
  • Light rainfall (proper filtered noise + soft droplet patter)
  • Nature with bird chirps (filtered pink noise + intermittent pure-tone trills)
  • Brown noise (deep rumble — most relaxing for many)
  • White noise (broadband — blocks chatter)
  • Pink noise (balanced, softer than white)
  • Alpha brainwave beats (10 Hz binaural for relaxed focus)
  • Gamma brainwave beats (40 Hz binaural for sustained focus)
  • Deep focus instrumental (low-frequency drone with sparse harmonic chords)

YouTube playlists are user-editable: add/remove from the UI. Defaults
include the three links the user specifically requested.
"""
import math
import os
import random
import re
import struct
import uuid
import wave
import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame, QSlider,
    QLineEdit, QDialog, QDialogButtonBox, QFormLayout, QMessageBox, QMenu,
)
from PyQt6.QtGui import QAction

from modules.base import Module
from ui.widgets import SectionHeader, Card, ScrollContainer, EmptyState
from core.search import SearchResult, fuzzy_score


SAMPLE_RATE = 44100
LOOP_SECONDS = 12  # long enough not to feel repetitive, short enough to generate fast


# ----------------------------------------------------------------------------
# WAV writing with seamless loop crossfade
# ----------------------------------------------------------------------------
def _save(path: Path, samples_left: list[float], samples_right: list[float] | None = None):
    """Write WAV. If samples_right provided, output is stereo (for binaural)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(samples_left)
    # Crossfade the head and tail with each other for seamless loop
    fade = int(SAMPLE_RATE * 0.30)
    for i in range(min(fade, n // 2)):
        t = i / fade
        samples_left[i] = samples_left[i] * t + samples_left[n - fade + i] * (1 - t)
        if samples_right:
            samples_right[i] = samples_right[i] * t + samples_right[n - fade + i] * (1 - t)
    channels = 2 if samples_right else 1
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels); w.setsampwidth(2); w.setframerate(SAMPLE_RATE)
        if samples_right:
            frames = bytearray()
            for l, r in zip(samples_left, samples_right):
                frames += struct.pack("<hh",
                                       max(-32767, min(32767, int(l * 32767))),
                                       max(-32767, min(32767, int(r * 32767))))
            w.writeframes(bytes(frames))
        else:
            w.writeframes(b"".join(
                struct.pack("<h", max(-32767, min(32767, int(s * 32767))))
                for s in samples_left
            ))


# ----------------------------------------------------------------------------
# Noise generators
# ----------------------------------------------------------------------------
def _white_noise(seconds=LOOP_SECONDS):
    n = SAMPLE_RATE * seconds
    return [random.uniform(-0.4, 0.4) for _ in range(n)]


def _brown_noise(seconds=LOOP_SECONDS):
    """Integrated white noise — low frequencies dominate."""
    n = SAMPLE_RATE * seconds
    out = []
    last = 0.0
    for _ in range(n):
        last = (last + random.uniform(-0.05, 0.05)) * 0.998
        last = max(-1.0, min(1.0, last))
        out.append(last * 0.65)
    return out


def _pink_noise(seconds=LOOP_SECONDS):
    """Voss-McCartney pink noise — equal energy per octave."""
    n = SAMPLE_RATE * seconds
    rows = 16
    state = [random.uniform(-1, 1) for _ in range(rows)]
    out = []
    counter = 0
    for _ in range(n):
        counter += 1
        for r in range(rows):
            if counter % (1 << r) == 0:
                state[r] = random.uniform(-1, 1)
                break
        out.append(sum(state) / rows * 0.4)
    return out


def _lowpass(samples: list[float], cutoff_factor: float = 0.05) -> list[float]:
    """Simple single-pole low-pass for smoothing."""
    out = []
    last = 0.0
    for s in samples:
        last = last + cutoff_factor * (s - last)
        out.append(last)
    return out


def _bandpass_around(samples: list[float], lo_factor: float, hi_factor: float) -> list[float]:
    """Quick-and-dirty bandpass: lowpass then subtract a stronger lowpass."""
    weak = _lowpass(samples, hi_factor)
    strong = _lowpass(samples, lo_factor)
    return [w - s for w, s in zip(weak, strong)]


# (Synthesized rain and nature-with-birds were attempted in an earlier build
#  but sounded too electronic. Removed. Use the YouTube playlists below for
#  convincing real-world recordings.)


# ----------------------------------------------------------------------------
# Binaural beats — alpha (relaxed focus), gamma (sustained focus)
# ----------------------------------------------------------------------------
def _binaural(base_freq: float, beat_freq: float, seconds=LOOP_SECONDS):
    """
    Generate a stereo binaural-beat track. Left ear plays base_freq, right
    ear plays base_freq + beat_freq. The brain perceives the difference
    as an entrainment frequency.

    Returns (left_samples, right_samples).
    """
    n = SAMPLE_RATE * seconds
    left  = []
    right = []
    # Use headphones for binaural beats! Layered with very soft brown noise
    # to make it pleasant to listen to.
    noise_base = _brown_noise(seconds)
    noise_base = [s * 0.15 for s in noise_base]
    for i in range(n):
        t = i / SAMPLE_RATE
        l = math.sin(2 * math.pi * base_freq * t) * 0.25 + noise_base[i]
        r = math.sin(2 * math.pi * (base_freq + beat_freq) * t) * 0.25 + noise_base[i]
        left.append(l); right.append(r)
    return left, right


# ----------------------------------------------------------------------------
# Deep focus drone — sparse harmonic chord with low-frequency hum
# ----------------------------------------------------------------------------
def _deep_focus_drone(seconds=LOOP_SECONDS):
    """
    A low-frequency drone (60 Hz) with slow-evolving harmonic overtones.
    Soft, sub-conscious — intended to be background, not foreground.
    """
    n = SAMPLE_RATE * seconds
    fundamental = 65.4  # C2
    harmonics = [1.0, 1.5, 2.0, 2.5, 3.0]  # tonic, fifth, octave, etc.
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        sample = 0.0
        for j, h in enumerate(harmonics):
            # Slowly varying amplitude per harmonic so the texture evolves
            amp = 0.10 / (j + 1) * (0.5 + 0.5 * math.sin(2 * math.pi * (0.05 + 0.013 * j) * t))
            sample += math.sin(2 * math.pi * fundamental * h * t) * amp
        out.append(sample)
    return out


# ----------------------------------------------------------------------------
# Recipe table
# ----------------------------------------------------------------------------
AMBIENT_RECIPES = {
    "brown_noise":  ("🟤", "Brown noise",           "Deep rumble. Many find this the most relaxing.",                       _brown_noise, False),
    "white_noise":  ("⚪", "White noise",           "Even broadband hiss. Blocks chatter.",                                 _white_noise, False),
    "pink_noise":   ("🌸", "Pink noise",            "Balanced — softer than white, brighter than brown.",                   _pink_noise, False),
    "alpha_beats":  ("🧘", "Alpha brainwave beats", "8–13 Hz binaural for relaxed focus. Wear headphones.",                  lambda: _binaural(200, 10), True),
    "gamma_beats":  ("⚡", "Gamma brainwave beats", "40 Hz binaural — claimed to support sustained focus. Headphones.",     lambda: _binaural(220, 40), True),
    "deep_focus":   ("🎼", "Deep focus drone",      "Low-frequency drone with slow harmonic motion. Subtle background.",    _deep_focus_drone, False),
}
# Note: synthesized rain/forest sounds were dropped — even with multi-layer
# generators they read as robotic. For convincing rain or birdsong, use the
# YouTube playlists below instead.


def _ambient_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home())) / "Jarvis"
    else:
        base = Path.home() / ".jarvis"
    return base / "ambient"


# ----------------------------------------------------------------------------
# YouTube playlist defaults (user-editable)
# ----------------------------------------------------------------------------
DEFAULT_YT_PLAYLISTS = [
    # User-provided links
    {"name": "User pick 1 — focus mix",
     "url":  "https://youtu.be/Fd1ooG8AFNA",
     "icon": "🎵", "from_defaults": True},
    {"name": "User pick 2 — focus mix",
     "url":  "https://youtu.be/oPVte6aMprI",
     "icon": "🎵", "from_defaults": True},
    {"name": "User pick 3 — focus mix",
     "url":  "https://youtu.be/OuUzTz_XyKE",
     "icon": "🎵", "from_defaults": True},
    # Curated extras (the synthetic rain/forest don't sound real,
    # so the YouTube versions cover those needs instead)
    {"name": "Lo-fi hip hop — beats to relax/study to",
     "url":  "https://www.youtube.com/watch?v=jfKfPfyJRdk",
     "icon": "🎧", "from_defaults": True},
    {"name": "Deep focus — ambient cinematic",
     "url":  "https://www.youtube.com/watch?v=4xDzrJKXOOY",
     "icon": "🌌", "from_defaults": True},
    {"name": "Real rain — 10 hours",
     "url":  "https://www.youtube.com/results?search_query=real+rain+sounds+10+hours",
     "icon": "🌧", "from_defaults": True},
    {"name": "Forest birds & nature — 10 hours",
     "url":  "https://www.youtube.com/results?search_query=forest+birds+nature+sounds+10+hours",
     "icon": "🐦", "from_defaults": True},
    {"name": "Classical for deep work",
     "url":  "https://www.youtube.com/results?search_query=classical+music+for+deep+work",
     "icon": "🎼", "from_defaults": True},
    {"name": "Coffee shop ambience",
     "url":  "https://www.youtube.com/results?search_query=coffee+shop+ambience",
     "icon": "☕", "from_defaults": True},
]


# ============================================================================
# YouTube add/edit dialog
# ============================================================================
class YouTubeDialog(QDialog):
    def __init__(self, parent=None, item=None):
        super().__init__(parent)
        self.setWindowTitle("Edit playlist" if item else "Add YouTube playlist")
        self.setMinimumWidth(440)
        form = QFormLayout(self)
        self.name_in = QLineEdit(item.get("name", "") if item else "")
        self.url_in  = QLineEdit(item.get("url", "") if item else "")
        self.url_in.setPlaceholderText("https://youtube.com/... or https://youtu.be/...")
        self.icon_in = QLineEdit(item.get("icon", "🎵") if item else "🎵")
        self.icon_in.setMaxLength(4)
        form.addRow("Name", self.name_in)
        form.addRow("URL", self.url_in)
        form.addRow("Icon", self.icon_in)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def value(self):
        url = self.url_in.text().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        return {
            "id":   uuid.uuid4().hex,
            "name": self.name_in.text().strip() or "Untitled",
            "url":  url,
            "icon": self.icon_in.text().strip() or "🎵",
        }


# ============================================================================
# Module
# ============================================================================
class FocusMusicModule(Module):
    MODULE_ID = "focus_music"
    NAME = "Focus Music"
    ICON = "🎵"
    SECTION = "Tools"
    DESCRIPTION = "Offline ambient sounds and curated YouTube playlists."

    def setup_ui(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollContainer(self)

        scroll.add(SectionHeader(
            "Focus Music",
            "Ambient sounds play in-app on a loop. YouTube playlists open in your browser — JARVIS keeps running in the tray."
        ))

        # ---- Now playing card ----
        now_card = Card()
        nl = QVBoxLayout(now_card); nl.setContentsMargins(20, 16, 20, 16); nl.setSpacing(8)
        title_row = QHBoxLayout()
        nl_title = QLabel("Now playing"); nl_title.setStyleSheet("font-size:15px; font-weight:600;")
        self.now_lbl = QLabel("Nothing playing"); self.now_lbl.setProperty("class", "Muted")
        title_row.addWidget(nl_title); title_row.addStretch(); title_row.addWidget(self.now_lbl)
        nl.addLayout(title_row)

        ctrl_row = QHBoxLayout()
        self.stop_btn = QPushButton("⏹  Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_playback)
        ctrl_row.addWidget(self.stop_btn)
        ctrl_row.addStretch()
        ctrl_row.addWidget(QLabel("Volume"))
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100); self.vol_slider.setValue(50)
        self.vol_slider.setFixedWidth(160)
        self.vol_slider.valueChanged.connect(self._on_volume)
        ctrl_row.addWidget(self.vol_slider)
        nl.addLayout(ctrl_row)
        scroll.add(now_card)

        # ---- Ambient sounds ----
        amb_card = Card()
        al = QVBoxLayout(amb_card); al.setContentsMargins(20, 16, 20, 18); al.setSpacing(10)
        amb_title = QLabel("Ambient sounds (offline)")
        amb_title.setStyleSheet("font-size:15px; font-weight:600;")
        amb_sub = QLabel("Generated locally on first play. Loops seamlessly. Binaural tracks marked 🎧 work best on headphones.")
        amb_sub.setProperty("class", "Muted"); amb_sub.setWordWrap(True)
        al.addWidget(amb_title); al.addWidget(amb_sub)

        grid = QGridLayout(); grid.setSpacing(10)
        for i, (key, (icon, name, desc, _gen, is_stereo)) in enumerate(AMBIENT_RECIPES.items()):
            tile = self._build_ambient_tile(key, icon, name, desc, is_stereo)
            grid.addWidget(tile, i // 2, i % 2)
        al.addLayout(grid)
        scroll.add(amb_card)

        # ---- YouTube playlists ----
        yt_card = Card()
        yl = QVBoxLayout(yt_card); yl.setContentsMargins(20, 16, 20, 18); yl.setSpacing(10)
        yt_head = QHBoxLayout()
        yt_title = QLabel("YouTube playlists")
        yt_title.setStyleSheet("font-size:15px; font-weight:600;")
        yt_head.addWidget(yt_title); yt_head.addStretch()
        add_yt = QPushButton("+  Add playlist")
        add_yt.setProperty("primary", True)
        add_yt.clicked.connect(self.add_playlist)
        yt_head.addWidget(add_yt)
        yl.addLayout(yt_head)
        yt_sub = QLabel("Opens in your default browser. Add or remove via the ⋯ menu on each row.")
        yt_sub.setProperty("class", "Muted")
        yl.addWidget(yt_sub)

        self.yt_host = QGridLayout(); self.yt_host.setSpacing(8)
        yl.addLayout(self.yt_host)
        scroll.add(yt_card)

        scroll.add_stretch()
        outer.addWidget(scroll)

        self._player: QMediaPlayer | None = None
        self._audio_output: QAudioOutput | None = None
        self._current_key: str | None = None
        self._current_display: str | None = None

        # Seed YouTube defaults and render
        self._ensure_yt_defaults()
        self._refresh_yt()
        # Clean up WAVs from recipes we no longer ship
        self._cleanup_stale_wavs()

    def _cleanup_stale_wavs(self):
        """Delete any .wav files in the ambient dir whose key isn't in
        AMBIENT_RECIPES anymore (e.g. light_rain.wav, nature_birds.wav from
        earlier builds)."""
        d = _ambient_dir()
        if not d.is_dir(): return
        valid = {f"{k}.wav" for k in AMBIENT_RECIPES.keys()}
        for f in d.glob("*.wav"):
            if f.name not in valid:
                try: f.unlink()
                except OSError: pass

    def _ensure_yt_defaults(self):
        def _slug(s: str) -> str:
            out = []
            for ch in (s or "").lower():
                if ch.isalnum(): out.append(ch)
                elif ch in " -_": out.append("-")
            return "".join(out).strip("-") or "untitled"

        existing = self.ctx.storage.load("module_focus_yt", [])
        existing_urls = {it.get("url") for it in existing}
        claimed = {e.get("default_key") for e in existing
                   if e.get("default_key") and not e.get("from_defaults")}
        added = False
        for d in DEFAULT_YT_PLAYLISTS:
            dkey = f"yt:{_slug(d['name'])}"
            if dkey in claimed:
                continue
            if d["url"] in existing_urls:
                continue
            new = dict(d)
            new["id"] = uuid.uuid4().hex
            new["default_key"] = dkey
            existing.append(new); added = True
        if added:
            self.ctx.storage.save("module_focus_yt", existing)

    def _yt_data(self):
        return self.ctx.storage.load("module_focus_yt", [])

    def _yt_save(self, items):
        self.ctx.storage.save("module_focus_yt", items)

    def _refresh_yt(self):
        # Clear grid
        while self.yt_host.count():
            it = self.yt_host.takeAt(0)
            if it.widget(): it.widget().deleteLater()

        items = self._yt_data()
        if not items:
            empty = QLabel("No playlists. Click ‘+ Add playlist’ to add one.")
            empty.setProperty("class", "Muted")
            self.yt_host.addWidget(empty, 0, 0)
            return
        for i, it in enumerate(items):
            self.yt_host.addWidget(self._build_yt_tile(it), i // 2, i % 2)

    def _build_yt_tile(self, item):
        f = QFrame(); f.setObjectName("ItemRow")
        l = QHBoxLayout(f); l.setContentsMargins(10, 8, 10, 8); l.setSpacing(8)
        l.addWidget(QLabel(item.get("icon", "🎵"), styleSheet="font-size:18px;"))
        nm = QLabel(item["name"]); nm.setStyleSheet("font-weight:500;")
        nm.setToolTip(item.get("url", ""))
        l.addWidget(nm, 1)
        btn = QPushButton("↗  Open"); btn.setProperty("primary", True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _=False, u=item.get("url",""), n=item["name"]: self._open_yt(u, n))
        l.addWidget(btn)
        more = QPushButton("⋯"); more.setProperty("ghost", True); more.setFixedWidth(24)
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self)
        a_edit = QAction("Edit…", self); a_edit.triggered.connect(lambda: self.edit_playlist(item))
        a_del  = QAction("Delete", self); a_del.triggered.connect(lambda: self.delete_playlist(item))
        menu.addAction(a_edit); menu.addSeparator(); menu.addAction(a_del)
        more.setMenu(menu)
        l.addWidget(more)
        return f

    def add_playlist(self):
        dlg = YouTubeDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = self._yt_data(); data.append(dlg.value()); self._yt_save(data); self._refresh_yt()

    def edit_playlist(self, item):
        dlg = YouTubeDialog(self, item=item)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = self._yt_data()
            for i, it in enumerate(data):
                if it.get("id") == item.get("id") or it.get("url") == item.get("url"):
                    new = dlg.value(); new["id"] = item.get("id") or new["id"]
                    # Preserve identity but mark as user-owned
                    if it.get("default_key"):
                        new["default_key"] = it["default_key"]
                    new["from_defaults"] = False
                    data[i] = new; break
            self._yt_save(data); self._refresh_yt()

    def delete_playlist(self, item):
        if QMessageBox.question(self, "Remove playlist", f"Remove '{item['name']}'?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                != QMessageBox.StandardButton.Yes:
            return
        data = [i for i in self._yt_data()
                if (i.get("id") != item.get("id")) and (i.get("url") != item.get("url"))]
        # When id and url both differ, item is removed
        # Above filter is too strict — use a single key:
        data = [i for i in self._yt_data() if i.get("id") != item.get("id")]
        self._yt_save(data); self._refresh_yt()

    # ---------- Ambient tile ----------
    def _build_ambient_tile(self, key, icon, name, desc, is_stereo):
        f = QFrame(); f.setObjectName("GroupCard")
        l = QVBoxLayout(f); l.setContentsMargins(14, 12, 14, 12); l.setSpacing(4)
        head = QHBoxLayout()
        head.addWidget(QLabel(f"{icon}  {name}", styleSheet="font-size:14px; font-weight:600;"))
        head.addStretch()
        play_btn = QPushButton("▶  Play"); play_btn.setProperty("primary", True)
        play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        play_btn.clicked.connect(lambda _=False, k=key, n=name: self._play_ambient(k, n))
        head.addWidget(play_btn)
        l.addLayout(head)
        label = desc + ("  🎧" if is_stereo else "")
        sub = QLabel(label); sub.setProperty("class", "Muted"); sub.setWordWrap(True)
        l.addWidget(sub)
        return f

    # ---------- Playback ----------
    def _play_ambient(self, key: str, display_name: str):
        wav_path = _ambient_dir() / f"{key}.wav"
        recipe = AMBIENT_RECIPES.get(key)
        if not recipe:
            return
        _, _, _, gen_fn, is_stereo = recipe

        if not wav_path.exists():
            # Generation can take several seconds; do it on a background
            # thread so the UI stays responsive.
            self.ctx.notify("Generating ambient track",
                            "First play — synthesizing in the background. Takes a few seconds…",
                            sound="click", source="Focus Music", user_initiated=True)
            self.ctx.status(f"Synthesizing {display_name}…",
                             icon="🎵", auto_hide=False)
            self._begin_ambient_generation(key, display_name, wav_path, gen_fn, is_stereo)
            return

        self._start_ambient_playback(wav_path, display_name)

    def _begin_ambient_generation(self, key, display_name, wav_path, gen_fn, is_stereo):
        """Kick off synthesis in a background thread, then play when done."""
        import threading
        from PyQt6.QtCore import QTimer

        def worker():
            try:
                if is_stereo:
                    left, right = gen_fn()
                    _save(wav_path, left, right)
                else:
                    samples = gen_fn()
                    _save(wav_path, samples)
                success, err = True, ""
            except Exception as e:
                success, err = False, str(e)[:120]
            # Marshal back to UI thread
            def done():
                self.ctx.status_clear()
                if success:
                    self._start_ambient_playback(wav_path, display_name)
                else:
                    self.ctx.notify("Couldn't generate audio", err,
                                    sound="error", source="Focus Music")
            QTimer.singleShot(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _start_ambient_playback(self, wav_path, display_name):
        # Tear down any previous player to avoid the QFFmpeg::Demuxer
        # disconnect spam and AUDCLNT_E_DEVICE_INVALIDATED errors that come
        # from reusing a player across sources / after device changes.
        self._teardown_player()

        try:
            self._player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_output)
            self._audio_output.setVolume(self.vol_slider.value() / 100.0)
            self._player.setLoops(QMediaPlayer.Loops.Infinite)
            # Surface playback errors to the user
            self._player.errorOccurred.connect(self._on_player_error)
            self._player.setSource(QUrl.fromLocalFile(str(wav_path)))
            self._player.play()
        except Exception as e:
            self.ctx.notify("Couldn't start playback", str(e)[:120],
                            sound="error", source="Focus Music")
            self._teardown_player()
            self.now_lbl.setText("Nothing playing")
            self.stop_btn.setEnabled(False)
            return

        self._current_key = wav_path.stem
        self._current_display = display_name
        self.now_lbl.setText(f"♪  {display_name}")
        self.stop_btn.setEnabled(True)
        # Light feedback, no duplicate in log
        self.ctx.play_sound("click")
        if hasattr(self.ctx, "on_music_state_changed"):
            self.ctx.on_music_state_changed()

    def _on_player_error(self, error, error_string=""):
        """Called by QMediaPlayer when something goes wrong (device gone, format
        unsupported, etc.). We log it and clean up — no scary tracebacks."""
        msg = error_string or "Audio playback error."
        # Some common Windows errors get a friendlier message
        low = msg.lower()
        if "audclnt_e_device_invalidated" in low or "could not activate audio" in low:
            msg = "Audio device was unplugged or went to sleep. Try again."
        elif "qaudioformat not supported" in low:
            msg = "Audio format not supported by your current output device."
        self.ctx.notify("Playback issue", msg[:140], sound="error",
                        source="Focus Music")
        self._teardown_player()
        self.now_lbl.setText("Nothing playing")
        self.stop_btn.setEnabled(False)
        self._current_key = None
        self._current_display = None
        if hasattr(self.ctx, "on_music_state_changed"):
            self.ctx.on_music_state_changed()

    def _teardown_player(self):
        """Cleanly destroy the active player + audio output, swallowing any
        errors raised during teardown (the C++ side is finicky)."""
        if self._player is not None:
            try: self._player.stop()
            except Exception: pass
            try: self._player.setSource(QUrl())
            except Exception: pass
            try: self._player.deleteLater()
            except Exception: pass
            self._player = None
        if self._audio_output is not None:
            try: self._audio_output.deleteLater()
            except Exception: pass
            self._audio_output = None

    def _stop_playback(self):
        self._teardown_player()
        self._current_key = None
        self._current_display = None
        self.now_lbl.setText("Nothing playing")
        self.stop_btn.setEnabled(False)
        self.ctx.play_sound("click")
        if hasattr(self.ctx, "on_music_state_changed"):
            self.ctx.on_music_state_changed()

    # ---------- Public API (called by Dashboard) ----------
    def is_playing(self) -> bool:
        return self._player is not None and self._current_key is not None \
               and self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def is_paused(self) -> bool:
        return self._player is not None \
               and self._player.playbackState() == QMediaPlayer.PlaybackState.PausedState

    def current_display_name(self) -> str | None:
        return getattr(self, "_current_display", None) if self._current_key else None

    def pause_resume(self):
        """Toggle play/pause for the dashboard widget."""
        if self._player is None: return
        if self.is_playing():
            self._player.pause()
        elif self.is_paused():
            self._player.play()
        if hasattr(self.ctx, "on_music_state_changed"):
            self.ctx.on_music_state_changed()

    def stop_external(self):
        """Public stop, callable from dashboard."""
        self._stop_playback()

    def _on_volume(self, val: int):
        if self._audio_output is not None:
            self._audio_output.setVolume(val / 100.0)

    def _open_yt(self, url: str, name: str):
        if not url: return
        webbrowser.open(url)
        self.ctx.notify("Opening playlist", name, sound="click")

    # ---------- Search ----------
    def register_search(self):
        def provider(query: str):
            results = []
            for key, (icon, name, _, _, _) in AMBIENT_RECIPES.items():
                score = fuzzy_score(query, name)
                if score > 0.3:
                    results.append(SearchResult(
                        title=name, subtitle="Ambient sound", category="Focus",
                        icon=icon,
                        action=lambda k=key, n=name: self._play_ambient(k, n),
                        score=score,
                    ))
            for item in self._yt_data():
                score = fuzzy_score(query, item.get("name", ""))
                if score > 0.3:
                    results.append(SearchResult(
                        title=item["name"], subtitle="YouTube playlist", category="Focus",
                        icon=item.get("icon", "🎵"),
                        action=lambda u=item["url"], n=item["name"]: self._open_yt(u, n),
                        score=score,
                    ))
            return results
        self.ctx.search.register("focus_music", provider)

    def on_show(self):
        self._refresh_yt()
