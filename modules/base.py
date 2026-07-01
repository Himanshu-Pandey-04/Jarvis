"""
Base class for every module. Anything you can switch on/off from Settings is
a Module. Adding a new feature = subclass + register in modules/__init__'s
MODULE_CLASSES list (or via Settings UI later).
"""
from PyQt6.QtWidgets import QWidget


class Module(QWidget):
    # Override these in subclasses
    MODULE_ID: str = "base"
    NAME: str = "Module"
    ICON: str = "•"
    SECTION: str = "Tools"     # Sidebar grouping: "Workspace" | "Tools" | "System"
    DESCRIPTION: str = ""
    ALWAYS_ON: bool = False    # If True, can't be disabled from settings

    def __init__(self, app_context, parent=None):
        super().__init__(parent)
        self.ctx = app_context  # AppContext object holding storage, search, theme, etc.
        self.setup_ui()
        self.register_search()

    # --- Override in subclasses ---
    def setup_ui(self):
        """Build the widget."""

    def register_search(self):
        """Register a search provider with self.ctx.search (optional)."""

    def on_show(self):
        """Called when the user navigates to this module."""

    def on_hide(self):
        """Called when the user navigates away."""

    # --- Helpers ---
    def storage_key(self, suffix: str = "") -> str:
        return f"module_{self.MODULE_ID}{('_' + suffix) if suffix else ''}"

    def load_data(self, suffix: str = "", default=None):
        return self.ctx.storage.load(self.storage_key(suffix), default if default is not None else [])

    def save_data(self, data, suffix: str = ""):
        return self.ctx.storage.save(self.storage_key(suffix), data)
