"""
Parse a Jarvis-style installation (configs.json, creds.json, work_templates.py)
and translate it into WorkBench data structures: launchers, links, templates,
and password-vault entries.

Pure-Python, no Qt — easy to unit-test, no side effects until the caller saves.
"""
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any


# ----------------------------------------------------------------------------
# Resource path — works for both source and PyInstaller-frozen builds
# ----------------------------------------------------------------------------
def resource_path(*parts: str) -> Path:
    """
    Resolve a path bundled with the app. In a PyInstaller --onefile build,
    bundled data lives under sys._MEIPASS. In source, it's relative to the
    project root (one level above this file).
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", "."))
    else:
        # this file lives at <project>/core/jarvis_import.py
        base = Path(__file__).resolve().parent.parent
    return base.joinpath(*parts)


# ----------------------------------------------------------------------------
# Loaders
# ----------------------------------------------------------------------------

def load_json(path: Path | str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def load_templates_py(path: Path | str) -> dict:
    """
    Parse a work_templates.py file. It defines a `templates` dict (Python literal).
    We do NOT exec the file — we extract the literal with a regex + ast.literal_eval.
    """
    import ast
    p = Path(path)
    if not p.exists():
        return {}
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return {}

    # Find `templates = { ... }` and parse the dict literal safely
    match = re.search(r"templates\s*=\s*(\{)", text)
    if not match:
        return {}
    start = match.start(1)
    # Walk forward to find the matching closing brace, respecting strings
    depth = 0
    i = start
    in_str: str | None = None
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        else:
            if ch in ("'", '"'):
                # triple quoted?
                if text[i:i+3] in ('"""', "'''"):
                    triple = text[i:i+3]
                    end = text.find(triple, i + 3)
                    if end == -1:
                        return {}
                    i = end + 3
                    continue
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    literal = text[start:i+1]
                    try:
                        return ast.literal_eval(literal)
                    except (SyntaxError, ValueError):
                        return {}
        i += 1
    return {}


# ----------------------------------------------------------------------------
# Translators — Jarvis-shaped → WorkBench-shaped
# ----------------------------------------------------------------------------

def jarvis_to_links(configs: dict) -> list[dict]:
    """Pull out URL collections as Links. Each group in configs.json
    becomes its own Links category. Essential documents go to Documents."""
    out: list[dict] = []

    def _slug(s: str) -> str:
        out_chars = []
        for ch in s.lower():
            if ch.isalnum(): out_chars.append(ch)
            elif ch in " -_": out_chars.append("-")
        return "".join(out_chars).strip("-") or "untitled"

    # "Websites" group → "Internal" category
    websites = configs.get("Websites", {}) or {}
    for name, url in websites.items():
        if isinstance(url, str) and url.strip():
            out.append({
                "name":     name if name[0].isupper() else name.title(),
                "url":      url.strip(),
                "icon":     "🔗",
                "category": "Internal",
                "notes":    "",
                "cred_ref": "",
                "default_key": f"link:Internal/{_slug(name)}",
                "from_defaults": True,
            })

    # Any other top-level groups whose values are name→URL maps
    GROUP_AS_LINKS = {"SNOW", "Tools", "ZS"}
    for group_name in GROUP_AS_LINKS:
        group = configs.get(group_name, {}) or {}
        if not isinstance(group, dict):
            continue
        for item_name, url in group.items():
            if isinstance(url, str) and url.strip() and url.startswith(("http://", "https://")):
                out.append({
                    "name":     item_name,
                    "url":      url.strip(),
                    "icon":     {"SNOW": "🎫", "ZS": "🏢"}.get(group_name, "🔗"),
                    "category": group_name,
                    "notes":    "",
                    "cred_ref": "",
                    "default_key": f"link:{group_name}/{_slug(item_name)}",
                    "from_defaults": True,
                })

    return out


def jarvis_to_documents(configs: dict) -> list[dict]:
    out: list[dict] = []

    def _slug(s: str) -> str:
        out_chars = []
        for ch in s.lower():
            if ch.isalnum(): out_chars.append(ch)
            elif ch in " -_": out_chars.append("-")
        return "".join(out_chars).strip("-") or "untitled"

    migration = configs.get("migration", {}) or {}
    for k, v in migration.items():
        if k in ("dev-stg", "stg-prod", "dev-prod") and isinstance(v, str) and v.strip():
            out.append({
                "name":     f"Migration — {k}",
                "path":     v.strip(),
                "icon":     "📊",
                "category": "Spreadsheets",
                "kind":     "file",
                "cred_ref": "",
                "default_key": f"doc:migration-{k}",
                "from_defaults": True,
            })
    essentials = configs.get("essential documents", {}) or {}
    for name, url in essentials.items():
        if not isinstance(url, str) or not url.strip():
            continue
        out.append({
            "name":     name,
            "path":     url.strip(),
            "icon":     "📄",
            "category": "Essential Documents",
            "kind":     "url",
            "cred_ref": "",
            "default_key": f"doc:essential-{_slug(name)}",
            "from_defaults": True,
        })
    return out


def jarvis_to_templates(templates_py: dict) -> list[dict]:
    """Convert work_templates.py's nested dict into WorkBench template entries."""
    if not isinstance(templates_py, dict):
        return []

    def _slug(s: str) -> str:
        out_chars = []
        for ch in s.lower():
            if ch.isalnum(): out_chars.append(ch)
            elif ch in " -_": out_chars.append("-")
        return "".join(out_chars).strip("-") or "untitled"

    out: list[dict] = []
    category_map = {
        "snow":  ("Email", "❄"),
        "email": ("Email", "✉"),
        "sql":   ("SQL", "🗃"),
    }
    for group, items in templates_py.items():
        if not isinstance(items, dict):
            continue
        category, icon = category_map.get(str(group).lower(), ("Snippets", "📋"))
        prefix = str(group).strip().capitalize()
        for name, body in items.items():
            if not isinstance(body, str):
                continue
            out.append({
                "name":     f"{prefix} — {name}",
                "category": category,
                "icon":     icon,
                "body":     body.strip("\n"),
                "default_key": f"tmpl:{_slug(group)}-{_slug(name)}",
                "from_defaults": True,
            })
    return out


def jarvis_to_password_entries(creds: dict) -> list[dict]:
    """
    Convert creds.json shape into credential entries for the Credentials module.
    No encryption — JARVIS now stores credentials as plain JSON.
    """
    import uuid as _uuid
    out: list[dict] = []
    for key, info in (creds or {}).items():
        if not isinstance(info, dict):
            continue
        username = info.get("id", "") or ""
        password = info.get("password", "") or ""
        if "PUT YOUR OWN PASSWORD" in password.upper():
            password = ""
        out.append({
            "id":       _uuid.uuid4().hex,
            "name":     key.upper(),
            "username": username,
            "password": password,
            "url":      "",
            "notes":    "Imported from Jarvis creds.json",
        })
    return out


def jarvis_to_launchers(configs: dict) -> list[dict]:
    """
    Convert Jarvis configs into WorkBench Launcher dicts.

    A Launcher: { id, name, icon, description, axes:[{label,options}], steps:[{type, ...}] }

    We map known Jarvis sections to launcher shapes:
      - tableau          → 1-axis (env) URL launcher
      - ZAIDYN           → 1-axis (env) URL launcher
      - cbrat (TWHK)     → 1-axis (env) URL launcher
      - cbrat (APAC)     → 0-axis URL launcher (apac-urls only)
      - cbrat (META)     → 0-axis URL launcher (META.Prod only)
      - migration        → 1-axis (pipeline) → opens web-loc + per-pipeline file
      - RDCs             → individual 0-axis launchers, each: copy_password(pc) → open_path(rdp)
      - Azkaban          → 0-axis multi-step (run backend, delay, open html)
    """
    out: list[dict] = []

    def _slugify(s: str) -> str:
        """Turn 'My Launcher Name!' into 'my-launcher-name' for stable IDs."""
        out_chars = []
        for ch in s.lower():
            if ch.isalnum():
                out_chars.append(ch)
            elif ch in (" ", "-", "_"):
                out_chars.append("-")
        return "".join(out_chars).strip("-") or "untitled"

    def make_launcher(name, icon, description, section="Workspace") -> dict:
        return {
            "id":          uuid.uuid4().hex,
            "default_key": f"launcher:{_slugify(name)}",
            "name":        name,
            "icon":        icon,
            "description": description,
            "section":     section,
            "axes":        [],
            "steps":       [],
            "cred_ref":    "",
            "from_defaults": True,
        }

    # ----- Tableau (1-axis, env → URL) -----
    tableau = configs.get("tableau", {})
    if isinstance(tableau, dict) and tableau:
        envs = list(tableau.keys())
        L = make_launcher("Tableau", "📊", "Open Tableau in selected environment.")
        L["axes"] = [{"label": "Environment", "options": [e.capitalize() for e in envs]}]
        L["steps"] = [{
            "type":      "open_url",
            "label":     "Open Tableau",
            "value":     "",
            "value_map": {e.capitalize(): tableau[e] for e in envs if isinstance(tableau[e], str)},
            "extra":     "",
        }]
        out.append(L)

    # ----- ZAIDYN (1-axis, env → URL) -----
    zaidyn = configs.get("ZAIDYN", {})
    if isinstance(zaidyn, dict) and zaidyn:
        envs = list(zaidyn.keys())
        L = make_launcher("ZAIDYN ZDH", "🔐", "Open Zaidyn Data Hub in selected environment.")
        L["axes"] = [{"label": "Environment", "options": envs}]
        L["steps"] = [{
            "type":      "open_url",
            "label":     "Open ZDH",
            "value":     "",
            "value_map": {e: zaidyn[e] for e in envs if isinstance(zaidyn[e], str)},
            "extra":     "",
        }]
        out.append(L)

    # CBRAT removed in build 4 — was being unconditionally re-seeded from
    # ancient stored launchers. We no longer process the "cbrat" config key
    # even if present.

    # ----- Migration (1-axis, pipeline → opens web-loc + per-pipeline file) -----
    migration = configs.get("migration", {})
    if isinstance(migration, dict):
        web_loc = migration.get("web-loc", "")
        pipelines = [k for k in ("dev-stg", "stg-prod", "dev-prod") if isinstance(migration.get(k), str) and migration[k]]
        if pipelines:
            L = make_launcher("Migration", "🔄",
                               "Open ServiceNow request page and migration file for selected pipeline.")
            L["axes"] = [{"label": "Pipeline", "options": pipelines}]
            steps = []
            if isinstance(web_loc, str) and web_loc.strip():
                steps.append({"type": "open_url", "label": "Open SNOW migration request",
                              "value": web_loc, "value_map": {}, "extra": ""})
            steps.append({
                "type":      "open_path",
                "label":     "Open migration file",
                "value":     "",
                "value_map": {p: migration[p] for p in pipelines},
                "extra":     "",
            })
            L["steps"] = steps
            out.append(L)

    # ----- RDCs (single unified launcher: Tool axis → copy PC pwd, then open .rdp) -----
    rdcs = configs.get("RDCs", {})
    if isinstance(rdcs, dict):
        rdc_items = [(name, path) for name, path in rdcs.items()
                     if isinstance(path, str) and path.strip()]
        if rdc_items:
            tool_names = [name for name, _ in rdc_items]
            L = make_launcher("RDC Tools", "🖥",
                              "Pick a tool. Copies your PC password (auto-restores after 60s) and launches the RDC session.",
                              section="Workspace")
            L["cred_ref"] = "PC"
            L["axes"] = [{"label": "Tool", "options": tool_names}]
            L["steps"] = [
                {"type": "copy_password", "label": "Copy PC password (60s restore)",
                 "value": "60", "value_map": {}, "value_map_2d": {}, "extra": "PC"},
                {"type": "open_path", "label": "Launch tool",
                 "value": "",
                 "value_map": {name: path for name, path in rdc_items},
                 "value_map_2d": {}, "extra": ""},
            ]
            out.append(L)

    # ----- Azkaban (cd + run + delay + open file URL) -----
    azkaban = configs.get("azkaban", {})
    if isinstance(azkaban, dict):
        designer = azkaban.get("designer", "")
        if isinstance(designer, str) and designer.strip():
            index_url = "file:///" + designer.replace("\\", "/").rstrip("/") + "/index.html"
            L = make_launcher("Azkaban Designer", "🔮",
                               "Start the Azkaban backend and open the designer in your browser.")
            L["steps"] = [
                {"type": "run", "label": "Start backend (python backend_1.py)",
                 "value": "python backend_1.py", "value_map": {}, "extra": designer},
                {"type": "delay", "label": "Wait 3 seconds for backend",
                 "value": "3", "value_map": {}, "extra": ""},
                {"type": "open_url", "label": "Open designer in browser",
                 "value": index_url, "value_map": {}, "extra": ""},
            ]
            out.append(L)

    return out


# ----------------------------------------------------------------------------
# Top-level: import everything available in a directory
# ----------------------------------------------------------------------------
def default_ai_agents_links() -> list[dict]:
    """Default GenAI tool links seeded into the AI Agents module on every run."""
    items = [
        {"name": "Microsoft Copilot",  "url": "https://copilot.microsoft.com/",
         "icon": "🤝", "category": "Chat", "notes": ""},
        {"name": "ChatGPT",            "url": "https://chatgpt.com/",
         "icon": "🤖", "category": "Chat", "notes": ""},
        {"name": "Claude",             "url": "https://claude.ai/",
         "icon": "🧠", "category": "Chat", "notes": ""},
        {"name": "Google Gemini",      "url": "https://gemini.google.com/",
         "icon": "✨", "category": "Chat", "notes": ""},
        {"name": "Perplexity",         "url": "https://www.perplexity.ai/",
         "icon": "🔎", "category": "Search", "notes": ""},
        {"name": "GitHub Copilot",     "url": "https://github.com/features/copilot",
         "icon": "👨‍💻", "category": "Coding", "notes": ""},
        {"name": "Cursor",             "url": "https://cursor.com/",
         "icon": "⌨️",  "category": "Coding", "notes": ""},
        {"name": "v0 by Vercel",       "url": "https://v0.dev/",
         "icon": "🎨", "category": "Coding", "notes": ""},
        {"name": "NotebookLM",         "url": "https://notebooklm.google.com/",
         "icon": "📓", "category": "Research", "notes": ""},
        {"name": "Hugging Face",       "url": "https://huggingface.co/",
         "icon": "🤗", "category": "Research", "notes": ""},
    ]

    def _slug(s: str) -> str:
        out = []
        for ch in s.lower():
            if ch.isalnum(): out.append(ch)
            elif ch in " -_": out.append("-")
        return "".join(out).strip("-") or "untitled"

    for it in items:
        it["from_defaults"] = True
        it["default_key"] = f"ai:{_slug(it['name'])}"
    return items


def import_from_directory(folder: Path | str) -> dict:
    """
    Look for configs.json / creds.json / work_templates.py in the folder.
    Returns a dict of WorkBench-shaped data ready to merge.

    Returned shape:
      {
        "launchers":   [...],
        "links":       [...],
        "documents":   [...],
        "templates":   [...],
        "passwords":   [...],   # each entry has 'plain_password' the caller must encrypt
        "found": {"configs": bool, "creds": bool, "templates": bool}
      }
    """
    folder = Path(folder)
    cfg_path = folder / "configs.json"
    cred_path = folder / "creds.json"
    tpl_path = folder / "work_templates.py"

    configs = load_json(cfg_path) if cfg_path.exists() else {}
    creds = load_json(cred_path) if cred_path.exists() else {}
    tpls = load_templates_py(tpl_path) if tpl_path.exists() else {}

    return {
        "launchers": jarvis_to_launchers(configs),
        "links":     jarvis_to_links(configs),
        "documents": jarvis_to_documents(configs),
        "templates": jarvis_to_templates(tpls),
        "passwords": jarvis_to_password_entries(creds),
        "found": {
            "configs":   bool(configs),
            "creds":     bool(creds),
            "templates": bool(tpls),
        },
    }


def _migrate_legacy_tasks(storage):
    """Migrate old module_todos + module_reminders into module_tasks. One-shot:
    if module_tasks file already exists, do nothing. Old keys are wiped after
    migration to avoid confusion."""
    # Check the file exists rather than load (load returns {} for missing keys)
    if (storage.base_dir / "module_tasks.json").exists():
        return  # already migrated or fresh install with tasks
    old_todos = storage.load("module_todos", []) or []
    old_reminders = storage.load("module_reminders", []) or []
    if not old_todos and not old_reminders:
        return  # nothing to migrate

    migrated: list[dict] = []
    for td in old_todos:
        migrated.append({
            "id":            uuid.uuid4().hex,
            "title":         td.get("title", "") or td.get("name", "Untitled"),
            "notes":         td.get("notes", ""),
            "url":           "",
            "priority":      td.get("priority", "Normal"),
            "recurrence":    "None",
            "interval_n":    1,
            "interval_unit": "days",
            "due_at":        None,
            "completed":     bool(td.get("completed", False)),
            "fired_at":      None,
        })
    for rm in old_reminders:
        migrated.append({
            "id":            uuid.uuid4().hex,
            "title":         rm.get("title", "Reminder"),
            "notes":         rm.get("notes", ""),
            "url":           "",
            "priority":      "Normal",
            "recurrence":    rm.get("recurrence", "None"),
            "interval_n":    1,
            "interval_unit": "days",
            "due_at":        rm.get("when"),
            "completed":     bool(rm.get("fired", False)),
            "fired_at":      None,
        })
    storage.save("module_tasks", migrated)
    # Wipe old keys
    storage.delete("module_todos")
    storage.delete("module_reminders")


# ----------------------------------------------------------------------------
# Default seeding — runs on every launch, merges intelligently
# ----------------------------------------------------------------------------

def _merge_defaults(existing: list[dict], fresh_defaults: list[dict],
                    key_fields: tuple = ("name", "category")) -> list[dict]:
    """
    Merge fresh defaults into existing storage.

    Identity model:
      • Every item built by our default-loading code is given a stable
        `default_key` (e.g. "launcher:tableau", "link:Websites/jira"). This
        identifier never changes across builds even when the human-facing name
        does.
      • When the user EDITS a default, our caller clears `from_defaults` but
        the `default_key` is preserved as plain data. That tells the merge to
        keep the user's edited version and NOT re-add the original.
      • When the user adds a brand-new item from scratch, it has no
        `default_key` — it's purely theirs.

    On every launch:
      1. Drop all current 'from_defaults' items (they may have changed in
         configs.json — we'll re-add the fresh set below).
      2. Skip any fresh default whose `default_key` is already claimed by a
         surviving user item (user has renamed/edited it).
      3. For backward compatibility with items without a `default_key`, fall
         back to the old name-based collision check.
      4. Keep all surviving user items.
    """
    user_items = [it for it in (existing or []) if not it.get("from_defaults")]

    def keyof(item):
        return tuple(item.get(k, "") for k in key_fields)

    # Map default_key → user-edited version (if any). This is the user's
    # edited copy of a default — we want it back where the default would have been.
    user_claimed_by_key = {it["default_key"]: it
                           for it in user_items if it.get("default_key")}

    # Pure-user items: no default_key, never claimed a default
    pure_user_items = [it for it in user_items if not it.get("default_key")]

    # Walk fresh defaults in their canonical order. For each:
    #   • if user has an edited version of it (claimed default_key), slot the
    #     user's version in here
    #   • else use the fresh default
    ordered_result = []
    for d in fresh_defaults:
        dkey = d.get("default_key")
        if dkey and dkey in user_claimed_by_key:
            ordered_result.append(user_claimed_by_key[dkey])
        else:
            ordered_result.append(d)

    # Backward compat: drop pure-user items that collide BY NAME with a fresh
    # default (legacy data from before default_key existed)
    fresh_keys_set = {keyof(it) for it in fresh_defaults}
    pure_user_items = [it for it in pure_user_items
                       if keyof(it) not in fresh_keys_set]

    return ordered_result + pure_user_items


def seed_storage_from_defaults(storage) -> dict:
    """
    Seed (or re-seed) the storage from the bundled `defaults/` folder.
    Runs on EVERY launch — items tagged from_defaults=True are refreshed
    from disk, but user-added items are preserved untouched.

    This means: you can edit defaults/configs.json (or replace it before
    building the .exe) and the next launch will pick up the changes
    without clobbering the user's customizations.
    """
    summary = {"seeded": False, "first_run": False,
               "launchers": 0, "links": 0, "documents": 0, "templates": 0}

    defaults_dir = resource_path("defaults")
    if not defaults_dir.is_dir():
        return summary

    parsed = import_from_directory(defaults_dir)
    if not any(parsed["found"].values()):
        return summary

    # Detect first run for the welcome notification
    has_existing = any(storage.load(key) for key in
                       ("module_launchers", "module_links",
                        "module_documents", "module_templates"))
    summary["first_run"] = not has_existing

    # ---- One-time migration: legacy module_todos + module_reminders → module_tasks ----
    _migrate_legacy_tasks(storage)

    # ---- Launchers ----
    fresh_launchers = parsed["launchers"]
    existing = storage.load("module_launchers", [])
    # Migration: strip CBRAT-named launchers if they survived from earlier builds
    existing = [L for L in existing if not (L.get("name", "").upper().startswith("CBRAT"))]
    merged = _merge_defaults(existing, fresh_launchers, key_fields=("name",))
    storage.save("module_launchers", merged)
    summary["launchers"] = sum(1 for it in merged if it.get("from_defaults"))

    # ---- Links (Jarvis Websites + SNOW). AI Agents go to their own module. ----
    fresh_links = parsed["links"]
    existing = storage.load("module_links", [])
    # Migration: an earlier build seeded AI agents into Links under category "AI Agents".
    # Strip those out unconditionally — the user now has a dedicated AI Agents page.
    existing = [L for L in existing if L.get("category") != "AI Agents"]
    merged = _merge_defaults(existing, fresh_links, key_fields=("name", "category"))
    storage.save("module_links", merged)
    summary["links"] = sum(1 for it in merged if it.get("from_defaults"))

    # ---- AI Agents (separate page now) ----
    fresh_ai = default_ai_agents_links()
    existing = storage.load("module_ai_agents", [])
    merged = _merge_defaults(existing, fresh_ai, key_fields=("name",))
    storage.save("module_ai_agents", merged)

    # ---- Documents ----
    fresh_docs = parsed["documents"]
    existing = storage.load("module_documents", [])
    merged = _merge_defaults(existing, fresh_docs, key_fields=("name", "category"))
    storage.save("module_documents", merged)
    summary["documents"] = sum(1 for it in merged if it.get("from_defaults"))

    # ---- Templates ----
    if parsed["templates"]:
        existing = storage.load("module_templates", [])
        merged = _merge_defaults(existing, parsed["templates"], key_fields=("name", "category"))
        storage.save("module_templates", merged)
        summary["templates"] = sum(1 for it in merged if it.get("from_defaults"))

    summary["seeded"] = any(summary[k] for k in
                            ("launchers", "links", "documents", "templates"))
    return summary
