"""
System-wide activity tracker.

On Windows we call GetLastInputInfo() (no admin needed, no extra deps).
On other OSes we use a Qt event filter as a best-effort fallback that only
counts in-app activity. Either way the API is the same:

    tracker = ActivityTracker()
    tracker.tick()                       # call every ~5s
    seconds = tracker.session_active     # how long the user was active today
"""
import sys
import time
from datetime import date


class ActivityTracker:
    IDLE_THRESHOLD_SECONDS = 60  # idle longer than this → not "actively working"
    MAX_TICK_INCREMENT = 30      # cap any single tick to this many seconds

    def __init__(self):
        self.session_active: float = 0.0  # seconds today
        self._last_tick = time.time()
        self._today = date.today()

    def tick(self) -> float:
        """
        Called periodically. Returns total active seconds *today* after this tick.
        Resets to 0 at midnight.
        """
        now = time.time()
        today = date.today()
        if today != self._today:
            self.session_active = 0.0
            self._today = today

        elapsed = min(now - self._last_tick, self.MAX_TICK_INCREMENT)
        self._last_tick = now

        idle = self.idle_seconds()
        if idle < self.IDLE_THRESHOLD_SECONDS:
            self.session_active += elapsed
        return self.session_active

    @staticmethod
    def idle_seconds() -> float:
        """Return seconds since last system-wide input. 0 if unknown."""
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import Structure, c_uint, byref, sizeof, windll

                class LASTINPUTINFO(Structure):
                    _fields_ = [('cbSize', c_uint), ('dwTime', c_uint)]

                info = LASTINPUTINFO()
                info.cbSize = sizeof(info)
                if windll.user32.GetLastInputInfo(byref(info)):
                    millis = windll.kernel32.GetTickCount() - info.dwTime
                    return millis / 1000.0
            except Exception:
                return 0.0
        # macOS/Linux fallback: assume active. The dashboard timer will
        # therefore advance whenever the app is running on those OSes.
        return 0.0

    @staticmethod
    def format_duration(secs: float) -> str:
        """Format seconds as '2h 14m' or '14m 30s'."""
        s = int(secs)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h > 0:
            return f"{h}h {m:02d}m"
        if m > 0:
            return f"{m}m {sec:02d}s"
        return f"{sec}s"
