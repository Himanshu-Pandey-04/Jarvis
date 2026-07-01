"""
Jarvis — A modular Windows desktop assistant for data professionals.
Entry point: launches the main window with all registered modules.

On first run (when storage is empty) we seed the user's launchers, links,
documents, and templates from the bundled `defaults/` folder so the app
is useful out of the box.
"""
import sys
import os as _os
import shutil as _shutil
from pathlib import Path as _Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ui.main_window import MainWindow
from core.theme import ThemeManager
from core.storage import Storage
from core.jarvis_import import seed_storage_from_defaults


def _migrate_legacy_appdata():
    """One-time migration: copy data from %APPDATA%/WorkBench → %APPDATA%/Jarvis
    if the legacy folder exists and the new one doesn't yet have data files.
    Safe no-op when not applicable. Preserves all user customizations."""
    try:
        if _os.name == "nt":
            legacy = _Path(_os.environ.get("APPDATA", _Path.home())) / "WorkBench"
            new = _Path(_os.environ.get("APPDATA", _Path.home())) / "Jarvis"
        else:
            legacy = _Path.home() / ".workbench"
            new = _Path.home() / ".jarvis"
        if not legacy.exists():
            return
        legacy_data = legacy / "data"
        new_data = new / "data"
        # Only migrate if legacy has data AND new doesn't (or is empty)
        if not legacy_data.exists() or not any(legacy_data.glob("*.json")):
            return
        new_data.mkdir(parents=True, exist_ok=True)
        if any(new_data.glob("*.json")):
            return  # user already has new-location data; don't clobber
        # Copy all JSON files
        for src in legacy_data.glob("*.json"):
            try:
                _shutil.copy2(src, new_data / src.name)
            except OSError:
                pass
        # Mark legacy folder as migrated so user knows
        try:
            (legacy / "MIGRATED_TO_JARVIS.txt").write_text(
                "Your data was copied to the new Jarvis folder. "
                "This folder is no longer used; you can delete it.")
        except OSError:
            pass
    except Exception:
        pass  # never block startup on migration errors


def main():
    # High-DPI handling (Windows laptops in MNCs often run scaled displays)
    if hasattr(Qt.ApplicationAttribute, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Jarvis")
    app.setOrganizationName("Jarvis")
    app.setApplicationDisplayName("Jarvis")

    # Prevent app from quitting when last visible window closes (we live in tray too)
    app.setQuitOnLastWindowClosed(False)

    # One-time migration from legacy WorkBench folder
    _migrate_legacy_appdata()

    storage = Storage()

    # First-run seeding: if the user has no data yet, copy in the bundled
    # defaults from the `defaults/` folder. Safe no-op on subsequent runs.
    seed_summary = seed_storage_from_defaults(storage)

    # Aggressively remove stale ambient WAVs from earlier builds (light_rain,
    # nature_birds — they sounded electronic, were removed)
    try:
        base = _Path(_os.environ.get("APPDATA", _Path.home())) / "Jarvis" / "ambient" \
               if _os.name == "nt" else _Path.home() / ".jarvis" / "ambient"
        for stale in ("light_rain.wav", "nature_birds.wav"):
            p = base / stale
            if p.exists():
                try: p.unlink()
                except OSError: pass
    except Exception:
        pass

    # Initialize sound system (generates short WAVs on first run)
    from core.sounds import sound_player
    sound_player.initialize()
    prefs = storage.load("preferences", {})
    sound_player.set_muted(prefs.get("sounds_muted", False))

    theme_manager = ThemeManager(storage)
    theme_manager.apply(app)

    window = MainWindow(storage, theme_manager)
    window.show()

    # First-run tour
    try:
        from ui.tour import show_tour_if_needed
        # Defer slightly so the main window paints first
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(400, lambda: show_tour_if_needed(window, storage))
    except Exception as e:
        print(f"[Jarvis] Tour failed: {e}")

    # If we just seeded data, fire a tray notification so the user knows
    # to look at the launchers/links/templates pages.
    if seed_summary.get("seeded"):
        bits = []
        for label, count in (("launchers", seed_summary["launchers"]),
                              ("links",     seed_summary["links"]),
                              ("documents", seed_summary["documents"]),
                              ("templates", seed_summary["templates"])):
            if count:
                bits.append(f"{count} {label}")
        if bits:
            window.context.notify("Welcome to Jarvis",
                                  "Pre-loaded " + ", ".join(bits) +
                                  " from the bundled defaults. Customize from the sidebar.",
                                  sound="", source="Jarvis", user_initiated=True)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
