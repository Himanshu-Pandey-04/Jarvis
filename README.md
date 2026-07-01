# JARVIS

> Personal workbench for data engineers and consultants. Pre-loaded with
> Tableau, ZAIDYN, Migration, RDC, SNOW, and other ZS tools — but everything
> is editable, so it works as your daily desktop assistant regardless of stack.

A PyQt6 Windows desktop app. Stores everything locally at `%APPDATA%\Jarvis\`.
No telemetry, no cloud, no auth. Bundled defaults are seeded on every launch
while your additions/edits are preserved.

## Highlights

- **Live weather + headlines** — Open-Meteo API + RSS, no key required. Manual city setting for corp networks that block IP geolocation.
- **JARVIS HUD theme** — Tony Stark cyan/blue aesthetic with an animated neural-network background (glowing nodes, traveling light pulses), glassmorphism cards, neon edge glows.
- **Live launcher progress bar** — multi-step launchers (e.g. Azkaban: run backend → wait 3s → open in browser) report in-place step status at the bottom instead of stacking toast notifications.
- **In-app themed toasts** that match your selected theme, sliding in from the corner. (Plus tray balloons for when the window is hidden.)
- **Notification preferences** — Full / Titles-only / Off. Useful while screen-sharing.
- **Update-safe customization** — every default item carries a stable identifier. When you rename or edit a default, it stays edited across app updates and *doesn't get resurrected* alongside your version. Pure-user items are always preserved.
- **First-run tour** — 9-step walk-through, re-launchable from Settings.

## Module catalog

| Module | Section | What it does |
|---|---|---|
| Dashboard | Workspace | Pinned items, music control, today snapshot |
| Launchers | Workspace | Multi-step app/URL launchers with axis pickers |
| AI Agents | Workspace | GenAI tool tiles grouped by purpose |
| Links | Workspace | Web link tiles grouped by category |
| Documents | Workspace | File + URL shortcuts |
| Notes | Workspace | Markdown notes with live preview + auto-save status |
| Templates | Workspace | Reusable text templates |
| Credentials | Workspace | Quick-copy passwords (clipboard auto-restore) |
| Reviews | Workspace | Review notes, copy-all to markdown — password-gated |
| Tasks | Tools | Unified to-dos + reminders with recurrence |
| Health is Wealth | Tools | Wellness reminders (water, eyes, movement, meals, caffeine, sleep) |
| Timers | Tools | Stopwatch + countdown |
| Focus Music | Tools | Synth ambient (noise + binaural) + YouTube playlists |
| News & Weather | Tools | Live weather + top headlines + curated source links |
| Notifications | System | Activity log |
| Settings | System | Theme, sounds, notifications, modules, data |

## Quick start (development)

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Build the .exe

```cmd
python build_exe.py
```

Output: `dist\Jarvis.exe` — a single, portable Windows executable.
The bundled JARVIS logo PNG is embedded as the exe icon.

## How customization survives app updates

Every item that JARVIS ships as a default (launcher, link, AI agent, news source, etc.) carries:
- `from_defaults: True` — flag that it was seeded by JARVIS
- `default_key: "launcher:tableau"` — a stable identifier that **never changes** across builds, even if the human-facing name does

When you **edit** a default item, JARVIS sets `from_defaults=False` (so you now own it) but preserves the `default_key`. On the next app update:
- That `default_key` is in the "claimed" set, so the fresh default for it is **skipped** (won't be re-added alongside your edited version)
- Your edited version stays in its original slot, in order

When you **delete** a default, it will come back on the next re-seed — this is intentional, so you don't permanently lose access to a tool you might want later. If you don't want it, edit it instead and clear the URL/name.

**Custom items** (anything you add from scratch) have no `default_key`. They're always preserved exactly as you left them, appended after the default block.

## Notes for the IT admin rolling this out

- The defaults that ship are defined in `defaults/configs.json` (launchers, links, docs) and `defaults/work_templates.py` (email/SQL templates). Edit these before building the .exe to ship a different default loadout for your org.
- User data lives at `%APPDATA%\Jarvis\storage.json`. No registry entries.
- Audio sounds are generated to `%APPDATA%\Jarvis\sounds\` on first run.
- Synth ambient music WAVs are generated to `%APPDATA%\Jarvis\ambient\` on first play.
- All notification settings, theme, weather city, and sound mute state live in `preferences` and persist forever.
- Pushing an app update is just shipping a new `Jarvis.exe`. User data + customizations are untouched.

## Keyboard shortcuts

- `Ctrl+K` — global search
- Notes:
  - `Ctrl+B` bold / `Ctrl+I` italic / `Ctrl+K` insert link
  - `Ctrl+1` / `Ctrl+2` / `Ctrl+3` — heading levels
  - `Ctrl+S` — force save now (notes auto-save anyway)

## Network endpoints

Live weather and headlines need outbound HTTPS to:
- `api.open-meteo.com` — weather data (no auth)
- `geocoding-api.open-meteo.com` — convert city name → lat/lon (no auth)
- `ipapi.co` — IP geolocation, used only when no city is set manually
- `feeds.bbci.co.uk`, `timesofindia.indiatimes.com` — RSS feeds for headlines

If your corporate firewall blocks these, the live cards show a friendly fallback and the curated source-link tiles still work (open the site in your browser).

## License

Internal tool. Not open source.
