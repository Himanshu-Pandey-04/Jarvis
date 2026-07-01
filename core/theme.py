"""
Theme manager. Holds palette definitions and applies them as Qt stylesheets.
Each palette is a dict of role-color mappings; styles.py templates them in.

All palettes are vetted for WCAG-AA contrast: any text role meets 4.5:1
against its surface, accent buttons are 3:1+ against accent_text.
"""
from PyQt6.QtCore import QObject, pyqtSignal
from ui.styles import build_stylesheet


PALETTES = {
    "Light": {
        "bg":           "#F4F6FA",
        "surface":      "#FFFFFF",
        "surface_alt":  "#EDEFF4",
        "border":       "#D5D9E0",
        "text":         "#1F2328",
        "text_muted":   "#3D4A57",  # darker for better contrast on light bg
        "accent":       "#0969DA",
        "accent_hover": "#0860C7",
        "accent_text":  "#FFFFFF",
        "success":      "#1A7F37",
        "warning":      "#9A6700",
        "danger":       "#CF222E",
        "sidebar_bg":   "#1F2328",
        "sidebar_text": "#E6EDF3",
        "sidebar_text_muted": "rgba(230,237,243,0.85)",  # boosted from 0.55
        "sidebar_accent":"#2F81F7",
        "is_dark":      "false",
    },
    "Dark": {
        "bg":           "#0D1117",
        "surface":      "#161B22",
        "surface_alt":  "#21262D",
        "border":       "#30363D",
        "text":         "#E6EDF3",
        "text_muted":   "#A8B1BD",
        "accent":       "#2F81F7",
        "accent_hover": "#1F6FEB",
        "accent_text":  "#FFFFFF",
        "success":      "#3FB950",
        "warning":      "#D29922",
        "danger":       "#F85149",
        "sidebar_bg":   "#010409",
        "sidebar_text": "#E6EDF3",
        "sidebar_text_muted": "rgba(230,237,243,0.80)",
        "sidebar_accent":"#2F81F7",
        "is_dark":      "true",
    },
    "Solarized": {
        "bg":           "#FDF6E3",
        "surface":      "#FFFCF2",
        "surface_alt":  "#EEE8D5",
        "border":       "#B5AE91",
        "text":         "#073642",
        "text_muted":   "#2A4651",  # darker, was #3E5660
        "accent":       "#1E6B9C",
        "accent_hover": "#155578",
        "accent_text":  "#FFFFFF",
        "success":      "#5A6B00",
        "warning":      "#8A6500",
        "danger":       "#B0211F",
        "sidebar_bg":   "#073642",
        "sidebar_text": "#FDF6E3",
        "sidebar_text_muted": "rgba(253,246,227,0.85)",  # boosted
        "sidebar_accent":"#2AA198",
        "is_dark":      "false",
    },
    "Consultant Blue": {
        "bg":           "#F1F4FB",
        "surface":      "#FFFFFF",
        "surface_alt":  "#E3E9F4",
        "border":       "#C8D2E5",
        "text":         "#0B1733",
        "text_muted":   "#2C3850",  # darker, was #46546F
        "accent":       "#1F4FD9",
        "accent_hover": "#1740B8",
        "accent_text":  "#FFFFFF",
        "success":      "#11703B",
        "warning":      "#9A5A06",
        "danger":       "#B91C1C",
        "sidebar_bg":   "#0B1733",
        "sidebar_text": "#E5EAF7",
        "sidebar_text_muted": "rgba(229,234,247,0.85)",  # boosted
        "sidebar_accent":"#3B82F6",
        "is_dark":      "false",
    },
    "Midnight Forest": {
        "bg":           "#0F1A14",
        "surface":      "#162820",
        "surface_alt":  "#1F362B",
        "border":       "#2C4D3C",
        "text":         "#E2F0E8",
        "text_muted":   "#A6CCB8",
        "accent":       "#34D399",
        "accent_hover": "#10B981",
        "accent_text":  "#062014",
        "success":      "#34D399",
        "warning":      "#FBBF24",
        "danger":       "#F87171",
        "sidebar_bg":   "#06120D",
        "sidebar_text": "#D5EADC",
        "sidebar_text_muted": "rgba(213,234,220,0.80)",
        "sidebar_accent":"#34D399",
        "is_dark":      "true",
    },
    "JARVIS HUD": {
        # The brand theme — Tony-Stark-blue HUD aesthetic
        "bg":           "#040A14",
        "surface":      "#0A1626",
        "surface_alt":  "#0F1F36",
        "border":       "#1B3258",
        "text":         "#D6EBFF",
        "text_muted":   "#7CA8D6",
        "accent":       "#39C7FF",
        "accent_hover": "#1FAEE8",
        "accent_text":  "#04121F",
        "success":      "#34D399",
        "warning":      "#FBBF24",
        "danger":       "#F87171",
        "sidebar_bg":   "#020713",
        "sidebar_text": "#D6EBFF",
        "sidebar_text_muted": "rgba(214,235,255,0.80)",
        "sidebar_accent":"#39C7FF",
        "is_dark":      "true",
    },
}


class ThemeManager(QObject):
    theme_changed = pyqtSignal(str)

    def __init__(self, storage):
        super().__init__()
        self.storage = storage
        prefs = self.storage.load("preferences", {})
        # Default to JARVIS HUD for the brand
        self.current_name = prefs.get("theme", "JARVIS HUD")
        if self.current_name not in PALETTES:
            self.current_name = "JARVIS HUD"
        self._app = None

    @property
    def palette(self) -> dict:
        return PALETTES[self.current_name]

    def available_themes(self) -> list[str]:
        return list(PALETTES.keys())

    def apply(self, app):
        self._app = app
        app.setStyleSheet(build_stylesheet(self.palette, theme_name=self.current_name))

    def set_theme(self, name: str):
        if name not in PALETTES or name == self.current_name:
            return
        self.current_name = name
        prefs = self.storage.load("preferences", {})
        prefs["theme"] = name
        self.storage.save("preferences", prefs)
        if self._app:
            self._app.setStyleSheet(build_stylesheet(self.palette, theme_name=self.current_name))
        self.theme_changed.emit(name)
