"""
Build a Windows .exe with PyInstaller.

Usage (from this folder, on Windows):
    pip install -r requirements.txt
    pip install pyinstaller
    python build_exe.py

The resulting binary is at:
    dist/Jarvis.exe
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main():
    # Wipe previous build artifacts so we don't ship stale code
    for d in ("build", "dist"):
        p = HERE / d
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
    for spec_name in ("Jarvis.spec", "WorkBench.spec"):
        spec_file = HERE / spec_name
        if spec_file.exists():
            spec_file.unlink()

    # PyInstaller wants 'src;dest' on Windows and 'src:dest' on Linux/macOS.
    sep = os.pathsep

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",                    # No console window
        "--name", "Jarvis",
        # App icon (Windows .exe icon)
        "--icon", str(HERE / "defaults" / "assets" / "jarvis_logo.png"),
        # Bundle the defaults/ folder so first-run seeding works in the .exe.
        "--add-data", f"defaults{sep}defaults",
        # Hidden imports — make sure dynamic module loading is bundled
        "--hidden-import", "modules.dashboard",
        "--hidden-import", "modules.launchers",
        "--hidden-import", "modules.ai_agents",
        "--hidden-import", "modules.links",
        "--hidden-import", "modules.documents",
        "--hidden-import", "modules.notes",
        "--hidden-import", "modules.templates",
        "--hidden-import", "modules.passwords",
        "--hidden-import", "modules.reviews",
        "--hidden-import", "modules.tasks",
        "--hidden-import", "modules.health",
        "--hidden-import", "modules.timers",
        "--hidden-import", "modules.focus_music",
        "--hidden-import", "modules.news",
        "--hidden-import", "modules.notifications",
        "--hidden-import", "modules.settings",
        "--hidden-import", "modules.automation_scripts",
        "main.py",
    ]
    print("Running:", " ".join(args))
    result = subprocess.run(args, cwd=str(HERE))
    if result.returncode != 0:
        print("\nBuild failed.")
        sys.exit(result.returncode)

    exe = HERE / "dist" / ("Jarvis.exe" if sys.platform.startswith("win") else "Jarvis")
    if exe.exists():
        print(f"\n✔ Built: {exe}")
        print(f"  Size: {exe.stat().st_size / (1024*1024):.1f} MB")
    else:
        print("\nBuild produced no executable. Check PyInstaller output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
