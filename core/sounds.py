"""
App sound system. We generate small WAV files on first launch (no need to
ship binaries), cache them under %APPDATA%/Jarvis/sounds, and play them
via QSoundEffect — non-blocking and zero-latency.

Sound names: click, notify, timer, reminder, error, success.
Use sound_player.play("notify") from anywhere.
"""
import math
import os
import struct
import wave
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QSoundEffect


SAMPLE_RATE = 44100


def _envelope(t: float, attack=0.005, release=0.10, total=0.12) -> float:
    """A short attack/decay envelope so we don't hear clicks/pops at start/end."""
    if t < attack:
        return t / attack
    if t > total - release:
        return max(0.0, (total - t) / release)
    return 1.0


def _write_wav(path: Path, samples: list[float]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        # Convert float -1..1 → int16
        frames = b"".join(struct.pack("<h", max(-32767, min(32767, int(s * 32767))))
                          for s in samples)
        w.writeframes(frames)


def _tone(freq: float, duration: float, volume: float = 0.3) -> list[float]:
    """A pure sine tone with envelope."""
    n = int(SAMPLE_RATE * duration)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = _envelope(t, total=duration)
        out.append(math.sin(2 * math.pi * freq * t) * env * volume)
    return out


def _sequence(parts: list[tuple[float, float, float]]) -> list[float]:
    """Concatenate (freq, duration, volume) tones."""
    out: list[float] = []
    for f, d, v in parts:
        out.extend(_tone(f, d, v))
    return out


def _chord(freqs: list[float], duration: float, volume: float = 0.25) -> list[float]:
    """Multiple tones added together."""
    n = int(SAMPLE_RATE * duration)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = _envelope(t, total=duration)
        s = sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
        out.append(s * env * volume)
    return out


# Recipe per sound — tuned to be subtle, not annoying
SOUND_RECIPES: dict[str, callable] = {
    # short crisp click ~50ms
    "click":    lambda: _tone(1200, 0.04, 0.18),
    # gentle two-note chime, ascending
    "notify":   lambda: _sequence([(660, 0.10, 0.25), (880, 0.18, 0.25)]),
    # rising 3-note arpeggio for timer-end (more attention-grabbing)
    "timer":    lambda: _sequence([(523, 0.10, 0.28), (659, 0.10, 0.28), (784, 0.22, 0.28)]),
    # warm bell-ish chord for reminders
    "reminder": lambda: _chord([523, 659, 784], 0.40, 0.20),
    # short low-pitched tone for errors
    "error":    lambda: _sequence([(330, 0.08, 0.25), (220, 0.16, 0.25)]),
    # quick rising pair for success
    "success":  lambda: _sequence([(784, 0.08, 0.22), (1046, 0.14, 0.22)]),
}


# ----------------------------------------------------------------------------
# Player
# ----------------------------------------------------------------------------
class SoundPlayer:
    """
    Loads (or generates) WAV files and plays them via QSoundEffect.
    Singleton — see `sound_player` below.
    """

    def __init__(self):
        self._effects: dict[str, QSoundEffect] = {}
        self._muted = False
        self._initialized = False
        self._sounds_dir: Path | None = None

    def _resolve_sounds_dir(self) -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", Path.home())) / "Jarvis"
        else:
            base = Path.home() / ".jarvis"
        return base / "sounds"

    def initialize(self):
        """Generate WAVs (if missing) and load them. Idempotent."""
        if self._initialized:
            return
        try:
            self._sounds_dir = self._resolve_sounds_dir()
            self._sounds_dir.mkdir(parents=True, exist_ok=True)

            for name, recipe in SOUND_RECIPES.items():
                wav = self._sounds_dir / f"{name}.wav"
                if not wav.exists():
                    try:
                        _write_wav(wav, recipe())
                    except OSError:
                        continue
                if wav.exists():
                    eff = QSoundEffect()
                    eff.setSource(QUrl.fromLocalFile(str(wav)))
                    eff.setVolume(0.55)
                    self._effects[name] = eff
            self._initialized = True
        except Exception as e:
            # Sounds are best-effort — never crash the app over them
            print(f"[Jarvis] Sound init failed: {e}")
            self._initialized = True  # don't keep retrying

    def play(self, name: str):
        if not self._initialized:
            self.initialize()
        if self._muted:
            return
        eff = self._effects.get(name)
        if eff is not None:
            try:
                eff.play()
            except Exception:
                pass

    def set_muted(self, muted: bool):
        self._muted = muted

    def is_muted(self) -> bool:
        return self._muted


# Singleton
sound_player = SoundPlayer()
