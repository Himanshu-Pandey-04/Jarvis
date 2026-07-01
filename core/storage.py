"""
Storage layer. JSON files, one per logical key, stored in:
- Windows: %APPDATA%/Jarvis/data
- Other:   ~/.jarvis/data

Keep it stupid-simple: every module owns one or two keys, calls .load()/.save().
"""
import json
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Any


class Storage:
    APP_NAME = "Jarvis"

    def __init__(self):
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", Path.home())) / self.APP_NAME
        else:
            base = Path.home() / f".{self.APP_NAME.lower()}"

        self.base_dir = base
        self.data_dir = base / "data"
        self.backups_dir = base / "backups"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Sanitize key — no path traversal, no separators
        safe = "".join(c for c in key if c.isalnum() or c in "-_.")
        return self.data_dir / f"{safe}.json"

    def load(self, key: str, default: Any = None) -> Any:
        path = self._path(key)
        if not path.exists():
            return {} if default is None else default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # Corrupted file — back it up and return default
            try:
                backup = self.backups_dir / f"{key}.corrupt.{datetime.now():%Y%m%d_%H%M%S}.json"
                shutil.copy(path, backup)
            except OSError:
                pass
            return {} if default is None else default

    def save(self, key: str, data: Any) -> bool:
        path = self._path(key)
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str, ensure_ascii=False)
            # Atomic-ish replace so we never leave a half-written file
            os.replace(tmp, path)
            return True
        except OSError:
            return False

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if path.exists():
            try:
                path.unlink()
                return True
            except OSError:
                return False
        return True

    def all_keys(self) -> list[str]:
        return [p.stem for p in self.data_dir.glob("*.json")]

    def export_all(self, dest_path: str) -> bool:
        """Bundle the entire data directory into a single JSON for backup/transfer."""
        bundle = {}
        for key in self.all_keys():
            bundle[key] = self.load(key)
        try:
            with open(dest_path, "w", encoding="utf-8") as f:
                json.dump({"_jarvis_export": True,
                           "_exported_at": datetime.now().isoformat(),
                           "data": bundle}, f, indent=2, default=str)
            return True
        except OSError:
            return False

    def import_all(self, src_path: str) -> bool:
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                bundle = json.load(f)
            # Accept new and legacy export markers for migration friendliness
            if not (bundle.get("_jarvis_export") or bundle.get("_workbench_export")):
                return False
            for key, value in bundle.get("data", {}).items():
                self.save(key, value)
            return True
        except (OSError, json.JSONDecodeError):
            return False
