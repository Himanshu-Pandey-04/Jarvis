"""
Settings. Where users:
  - Pick a theme
  - Enable/disable modules (the "add/modify/remove functionalities" feature)
  - Reorder sidebar modules
  - Export / import their data bundle
  - Reset the password vault (destructive)
"""
import os
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QListWidget,
    QListWidgetItem, QMessageBox, QFileDialog, QCheckBox, QFrame, QWidget,
    QInputDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from modules.base import Module
from ui.widgets import SectionHeader, Card, ScrollContainer


class SettingsModule(Module):
    MODULE_ID = "settings"
    NAME = "Settings"
    ICON = "⚙"
    SECTION = "System"
    DESCRIPTION = "Theme, modules, data."
    ALWAYS_ON = True

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = ScrollContainer(self)
        scroll.add(SectionHeader("Settings", "Theme, modules, sounds, and data."))
        scroll.add(self._build_help_card())
        scroll.add(self._build_theme_card())
        scroll.add(self._build_sounds_card())
        scroll.add(self._build_notifications_card())
        scroll.add(self._build_modules_card())
        scroll.add(self._build_data_card())
        scroll.add(self._build_danger_card())
        scroll.add_stretch()
        outer.addWidget(scroll)

    # ---------- Help / Tour ----------
    def _build_help_card(self) -> Card:
        card = Card()
        l = QHBoxLayout(card); l.setContentsMargins(20, 14, 20, 14); l.setSpacing(12)
        icon = QLabel("🎓"); icon.setStyleSheet("font-size:28px;")
        l.addWidget(icon)
        col = QVBoxLayout(); col.setSpacing(2)
        title = QLabel("New here? Take the tour")
        title.setStyleSheet("font-size:14px; font-weight:600;")
        sub = QLabel("60-second walk-through of every section in JARVIS.")
        sub.setProperty("class", "Muted")
        col.addWidget(title); col.addWidget(sub)
        l.addLayout(col, 1)
        tour_btn = QPushButton("Start tour")
        tour_btn.setProperty("primary", True)
        tour_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tour_btn.clicked.connect(self._launch_tour)
        l.addWidget(tour_btn)
        return card

    def _launch_tour(self):
        try:
            from ui.tour import show_tour_manual
            show_tour_manual(self.ctx._main, self.ctx.storage)
        except Exception as e:
            QMessageBox.warning(self, "Tour unavailable", str(e))

    # ---------- Sounds ----------
    def _build_sounds_card(self) -> Card:
        card = Card()
        l = QVBoxLayout(card); l.setContentsMargins(20, 16, 20, 18); l.setSpacing(8)
        title = QLabel("Sounds"); title.setStyleSheet("font-size:15px; font-weight:600;")
        sub = QLabel("UI feedback, notifications, timers, reminders.")
        sub.setProperty("class", "Muted")
        l.addWidget(title); l.addWidget(sub)

        row = QHBoxLayout()
        from core.sounds import sound_player
        prefs = self.ctx.storage.load("preferences", {})
        self.mute_cb = QCheckBox("Mute all app sounds")
        self.mute_cb.setChecked(prefs.get("sounds_muted", False))
        self.mute_cb.toggled.connect(self._on_mute_toggled)
        row.addWidget(self.mute_cb)
        row.addStretch()
        test_btn = QPushButton("🔊  Test"); test_btn.clicked.connect(lambda: sound_player.play("notify"))
        row.addWidget(test_btn)
        l.addLayout(row)
        return card

    def _on_mute_toggled(self, muted: bool):
        from core.sounds import sound_player
        sound_player.set_muted(muted)
        prefs = self.ctx.storage.load("preferences", {})
        prefs["sounds_muted"] = muted
        self.ctx.storage.save("preferences", prefs)

    # ---------- Notifications ----------
    def _build_notifications_card(self) -> Card:
        card = Card()
        l = QVBoxLayout(card); l.setContentsMargins(20, 16, 20, 18); l.setSpacing(8)
        title = QLabel("Notifications"); title.setStyleSheet("font-size:15px; font-weight:600;")
        sub = QLabel("Control how reminders and alerts appear. "
                     "The in-app notification log (System → Notifications) always records everything.")
        sub.setProperty("class", "Muted"); sub.setWordWrap(True)
        l.addWidget(title); l.addWidget(sub)

        prefs = self.ctx.storage.load("preferences", {}) or {}
        current = prefs.get("notifications_mode", "full")

        row = QHBoxLayout()
        row.addWidget(QLabel("Mode"))
        self.notif_combo = QComboBox()
        self.notif_combo.addItem("Full — show title and details", userData="full")
        self.notif_combo.addItem("Titles only — hide details", userData="titles_only")
        self.notif_combo.addItem("Off — don't surface anything (still logged)", userData="off")
        # Select current
        for i in range(self.notif_combo.count()):
            if self.notif_combo.itemData(i) == current:
                self.notif_combo.setCurrentIndex(i); break
        self.notif_combo.currentIndexChanged.connect(self._on_notifications_mode_changed)
        row.addWidget(self.notif_combo, 1)
        l.addLayout(row)

        hint = QLabel(
            "Use ‘Titles only’ if you don't want passwords, reminders, or review titles "
            "showing details when you're screen-sharing."
        )
        hint.setProperty("class", "Muted"); hint.setWordWrap(True)
        l.addWidget(hint)
        return card

    def _on_notifications_mode_changed(self, _idx):
        mode = self.notif_combo.currentData()
        prefs = self.ctx.storage.load("preferences", {}) or {}
        prefs["notifications_mode"] = mode
        self.ctx.storage.save("preferences", prefs)
        self.ctx.notify("Notifications updated",
                        f"Mode: {self.notif_combo.currentText()}",
                        sound="success" if mode != "off" else "")

    # ---------- Theme ----------
    def _build_theme_card(self) -> Card:
        card = Card()
        l = QVBoxLayout(card); l.setContentsMargins(20, 16, 20, 18); l.setSpacing(8)
        title = QLabel("Theme"); title.setStyleSheet("font-size:15px; font-weight:600;")
        sub = QLabel("Pick a palette. Applies instantly across the app.")
        sub.setProperty("class", "Muted")
        l.addWidget(title); l.addWidget(sub)

        row = QHBoxLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(self.ctx.theme.available_themes())
        self.theme_combo.setCurrentText(self.ctx.theme.current_name)
        self.theme_combo.currentTextChanged.connect(self.ctx.theme.set_theme)
        row.addWidget(self.theme_combo)
        row.addStretch()
        l.addLayout(row)
        return card

    # ---------- Modules ----------
    def _build_modules_card(self) -> Card:
        card = Card()
        l = QVBoxLayout(card); l.setContentsMargins(20, 16, 20, 18); l.setSpacing(8)
        title = QLabel("Modules"); title.setStyleSheet("font-size:15px; font-weight:600;")
        sub = QLabel("Show or hide features in the sidebar. Drag to reorder. "
                     "Changes apply on the next app start.")
        sub.setProperty("class", "Muted"); sub.setWordWrap(True)
        l.addWidget(title); l.addWidget(sub)

        self.modules_list = QListWidget()
        self.modules_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.modules_list.setMinimumHeight(380)
        self.modules_list.model().rowsMoved.connect(lambda *_: self._save_module_order())
        self.modules_list.itemChanged.connect(self._on_module_toggled)
        l.addWidget(self.modules_list)

        hint = QLabel("Tip: ‘Dashboard’ and ‘Settings’ are always on.")
        hint.setProperty("class", "Muted")
        l.addWidget(hint)

        self._refresh_modules_list()
        return card

    def _refresh_modules_list(self):
        all_modules = self.ctx.all_module_classes()  # list of classes
        prefs = self.ctx.storage.load("preferences", {})
        enabled = set(prefs.get("enabled_modules", [m.MODULE_ID for m in all_modules]))
        order = prefs.get("module_order", [m.MODULE_ID for m in all_modules])

        # Build ordered list: known order first, unknown (new) modules after
        by_id = {m.MODULE_ID: m for m in all_modules}
        ordered_ids = [mid for mid in order if mid in by_id]
        for mid in by_id:
            if mid not in ordered_ids:
                ordered_ids.append(mid)

        self.modules_list.blockSignals(True)
        self.modules_list.clear()
        for mid in ordered_ids:
            cls = by_id[mid]
            li = QListWidgetItem(f"  {cls.ICON}    {cls.NAME}    ·   {cls.DESCRIPTION}")
            li.setData(Qt.ItemDataRole.UserRole, mid)
            li.setFlags(li.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            li.setCheckState(Qt.CheckState.Checked if mid in enabled else Qt.CheckState.Unchecked)
            if cls.ALWAYS_ON:
                li.setFlags(li.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                li.setCheckState(Qt.CheckState.Checked)
                li.setText(li.text() + "    ·   (always on)")
            self.modules_list.addItem(li)
        self.modules_list.blockSignals(False)

    def _on_module_toggled(self, item: QListWidgetItem):
        prefs = self.ctx.storage.load("preferences", {})
        enabled = []
        for i in range(self.modules_list.count()):
            it = self.modules_list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                enabled.append(it.data(Qt.ItemDataRole.UserRole))
        prefs["enabled_modules"] = enabled
        self.ctx.storage.save("preferences", prefs)
        # Schedule debounced reload (multiple fast events → one notify)
        self._schedule_reload()

    def _schedule_reload(self):
        """Coalesce multiple rapid 'reload sidebar' requests into one to avoid
        duplicate notifications (item toggled also fires row-moved, etc)."""
        if not hasattr(self, "_reload_timer"):
            self._reload_timer = QTimer(self)
            self._reload_timer.setSingleShot(True)
            self._reload_timer.timeout.connect(self._do_live_reload)
        self._reload_timer.start(150)

    def _do_live_reload(self):
        try:
            mw = self.ctx._main
            mw.live_rebuild_sidebar()
            self.ctx.notify("Modules updated",
                            "Sidebar refreshed — no restart needed.",
                            sound="success", source="Settings", user_initiated=True)
        except Exception as e:
            self.ctx.notify("Couldn't refresh sidebar",
                            f"Restart JARVIS to apply. ({str(e)[:60]})",
                            sound="error", source="Settings")

    def _save_module_order(self):
        prefs = self.ctx.storage.load("preferences", {})
        order = [self.modules_list.item(i).data(Qt.ItemDataRole.UserRole)
                 for i in range(self.modules_list.count())]
        prefs["module_order"] = order
        self.ctx.storage.save("preferences", prefs)
        self._schedule_reload()

    # ---------- Data ----------
    def _build_data_card(self) -> Card:
        card = Card()
        l = QVBoxLayout(card); l.setContentsMargins(20, 16, 20, 18); l.setSpacing(8)
        title = QLabel("Data"); title.setStyleSheet("font-size:15px; font-weight:600;")
        sub = QLabel(f"Stored in: {self.ctx.storage.base_dir}")
        sub.setProperty("class", "Muted"); sub.setWordWrap(True)
        l.addWidget(title); l.addWidget(sub)

        row = QHBoxLayout(); row.setSpacing(8)
        export_btn = QPushButton("Export all data…")
        export_btn.clicked.connect(self._export_data)
        import_btn = QPushButton("Import data bundle…")
        import_btn.clicked.connect(self._import_data)
        open_folder_btn = QPushButton("Open data folder")
        open_folder_btn.clicked.connect(self._open_data_folder)
        row.addWidget(export_btn); row.addWidget(import_btn); row.addWidget(open_folder_btn); row.addStretch()
        l.addLayout(row)

        warn = QLabel("Exports include all your data including credentials in plain JSON. "
                      "Keep export files private.")
        warn.setProperty("class", "Muted"); warn.setWordWrap(True)
        l.addWidget(warn)

        # ---- Jarvis migration ----
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setStyleSheet("color: palette(mid);")
        l.addWidget(sep)
        j_title = QLabel("Migrating from Jarvis?")
        j_title.setStyleSheet("font-weight: 600;")
        l.addWidget(j_title)
        j_sub = QLabel("Pick a folder containing your Jarvis files (configs.json, creds.json, "
                       "work_templates.py). WorkBench will create matching launchers, links, "
                       "documents, templates, and password-vault entries — none of your existing "
                       "WorkBench data is overwritten unless names collide.")
        j_sub.setProperty("class", "Muted"); j_sub.setWordWrap(True)
        l.addWidget(j_sub)

        j_row = QHBoxLayout()
        j_btn = QPushButton("Import from Jarvis folder…")
        j_btn.setProperty("primary", True)
        j_btn.clicked.connect(self._import_from_jarvis_folder)
        j_row.addWidget(j_btn); j_row.addStretch()
        l.addLayout(j_row)
        return card

    def _import_from_jarvis_folder(self):
        from core.jarvis_import import import_from_directory

        folder = QFileDialog.getExistingDirectory(self, "Pick the folder with your Jarvis files")
        if not folder:
            return
        result = import_from_directory(folder)
        found = result["found"]
        if not any(found.values()):
            QMessageBox.warning(self, "Nothing to import",
                                "No configs.json, creds.json or work_templates.py found in that folder.")
            return

        # Summarize what we'd do, ask for confirmation
        summary_lines = [
            f"From {folder}:",
            "",
            f"  • {len(result['launchers'])} launchers  (Tableau, CBRAT, Migration, RDCs, Azkaban…)",
            f"  • {len(result['links'])} links",
            f"  • {len(result['documents'])} documents / RDCs",
            f"  • {len(result['templates'])} text templates",
            f"  • {len(result['passwords'])} password-vault entries",
            "",
            "Existing items with matching names will be replaced; everything else stays put.",
            "Password entries import as empty if your creds.json had placeholders — fill them in afterwards.",
        ]
        if QMessageBox.question(self, "Import from Jarvis",
                                "\n".join(summary_lines),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                != QMessageBox.StandardButton.Yes:
            return

        self._apply_jarvis_import(result)

    def _apply_jarvis_import(self, result: dict):
        """Merge imported data into WorkBench storage."""
        # --- Launchers ---
        if result["launchers"]:
            existing = self.ctx.storage.load("module_launchers", [])
            existing_names = {L.get("name", "").lower() for L in existing}
            kept = [L for L in existing if L.get("name", "").lower() not in
                    {x.get("name", "").lower() for x in result["launchers"]}]
            kept.extend(result["launchers"])
            self.ctx.storage.save("module_launchers", kept)

        # --- Links ---
        if result["links"]:
            existing = self.ctx.storage.load("module_links", [])
            seen = {(it.get("name", ""), it.get("url", "")) for it in result["links"]}
            kept = [it for it in existing
                    if (it.get("name", ""), it.get("url", "")) not in seen]
            kept.extend(result["links"])
            self.ctx.storage.save("module_links", kept)

        # --- Documents ---
        if result["documents"]:
            existing = self.ctx.storage.load("module_documents", [])
            seen = {(it.get("name", ""), it.get("path", "")) for it in result["documents"]}
            kept = [it for it in existing
                    if (it.get("name", ""), it.get("path", "")) not in seen]
            kept.extend(result["documents"])
            self.ctx.storage.save("module_documents", kept)

        # --- Templates ---
        if result["templates"]:
            existing = self.ctx.storage.load("module_templates", [])
            new_names = {t["name"] for t in result["templates"]}
            kept = [it for it in existing if it.get("name") not in new_names]
            kept.extend(result["templates"])
            self.ctx.storage.save("module_templates", kept)

        # --- Passwords (now plain — no vault setup needed) ---
        password_count = 0
        if result["passwords"]:
            existing = self.ctx.storage.load("module_passwords", [])
            new_names = {(p.get("name") or "").lower() for p in result["passwords"]}
            kept = [it for it in existing
                    if (it.get("name") or "").lower() not in new_names]
            kept.extend(result["passwords"])
            self.ctx.storage.save("module_passwords", kept)
            password_count = len(result["passwords"])

        # Trigger a refresh on currently-open module pages
        for mid in ("launchers", "links", "documents", "templates", "passwords"):
            mod = self.ctx.get_module(mid)
            if mod and hasattr(mod, "on_show"):
                try: mod.on_show()
                except Exception: pass

        msg = (f"Imported {len(result['launchers'])} launchers, "
               f"{len(result['links'])} links, {len(result['documents'])} documents, "
               f"{len(result['templates'])} templates, {password_count} credential entries.")
        self.ctx.notify("Jarvis import complete", msg)
        QMessageBox.information(self, "Import complete", msg)

    # (legacy vault-protected import removed — credentials are plain now)


    def _export_data(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export data",
                                              "workbench_export.json", "JSON (*.json)")
        if not path:
            return
        ok = self.ctx.storage.export_all(path)
        if ok:
            self.ctx.notify("Data exported", path)
        else:
            QMessageBox.warning(self, "Export failed", "Could not write the file.")

    def _import_data(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import data bundle", "", "JSON (*.json)")
        if not path:
            return
        if QMessageBox.question(self, "Import data",
                                "Importing will overwrite any keys present in the bundle. "
                                "Continue?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) \
                != QMessageBox.StandardButton.Yes:
            return
        ok = self.ctx.storage.import_all(path)
        if ok:
            QMessageBox.information(self, "Import complete",
                                    "Restart WorkBench to see all imported data.")
        else:
            QMessageBox.warning(self, "Import failed",
                                "That file isn't a valid WorkBench export.")

    def _open_data_folder(self):
        try:
            if os.name == "nt":
                os.startfile(str(self.ctx.storage.base_dir))  # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(self.ctx.storage.base_dir)])
        except Exception as e:
            QMessageBox.warning(self, "Couldn't open folder", str(e))

    # ---------- Danger zone ----------
    def _build_danger_card(self) -> Card:
        card = Card()
        l = QVBoxLayout(card); l.setContentsMargins(20, 16, 20, 18); l.setSpacing(8)
        title = QLabel("Danger zone"); title.setStyleSheet("font-size:15px; font-weight:600; color:#CF222E;")
        l.addWidget(title)

        clear_creds_btn = QPushButton("Delete all credentials")
        clear_creds_btn.setProperty("danger", True)
        clear_creds_btn.clicked.connect(self._clear_credentials)
        l.addWidget(clear_creds_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        clear_all_btn = QPushButton("Reset all JARVIS data")
        clear_all_btn.setProperty("danger", True)
        clear_all_btn.clicked.connect(self._reset_all)
        l.addWidget(clear_all_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        return card

    def _clear_credentials(self):
        text, ok = QInputDialog.getText(
            self, "Delete all credentials",
            "This permanently deletes all credential entries. Type DELETE to confirm:")
        if not ok or text.strip() != "DELETE":
            return
        self.ctx.storage.delete("module_passwords")
        self.ctx.notify("Credentials deleted", "All entries removed.")
        passwords = self.ctx.get_module("passwords")
        if passwords:
            try: passwords.on_show()
            except Exception: pass

    def _reset_all(self):
        text, ok = QInputDialog.getText(
            self, "Reset all JARVIS data",
            "This deletes EVERYTHING — launchers, links, credentials, notes, "
            "reminders, settings. Type RESET ALL to confirm:")
        if not ok or text.strip() != "RESET ALL":
            return
        # Wipe by deleting each known storage key
        for key in ("module_launchers", "module_links", "module_ai_agents",
                    "module_documents", "module_templates", "module_passwords",
                    "module_tasks", "module_timers_state",
                    "module_notes", "module_reviews", "module_health",
                    "module_news", "module_focus_yt",
                    "notifications_log", "pinned_items", "preferences",
                    "activity_today",
                    # legacy keys (in case they survived a partial migration)
                    "module_todos", "module_reminders"):
            self.ctx.storage.delete(key)
        QMessageBox.information(self, "Reset complete",
                                "Restart JARVIS. The defaults will reload.")

    def on_show(self):
        # Modules list might have changed (e.g. user reset something). Refresh.
        self._refresh_modules_list()
        self.theme_combo.setCurrentText(self.ctx.theme.current_name)
