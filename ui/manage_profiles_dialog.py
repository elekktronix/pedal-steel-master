"""Profiles dialog: open, save, rename, import, export and delete profiles (groups of tunings),
and choose which profile and tuning open at startup."""

import logging
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from core.models import Neck, SteelGuitar
from core.profile_manager import (
    COPEDANT_FILE_FILTER,
    FACTORY_PROFILE,
    STARTUP_LAST_SESSION,
    STARTUP_PROFILE,
    ProfileManager,
    profile_label,
)
from core.settings import save_settings
from ui.profile_prompts import choose_profile_name

log = logging.getLogger(__name__)


def _tuning_text(neck: Neck) -> str:
    return (f"{neck.name}  ·  {neck.string_count} strings, {len(neck.pedals)} pedals, "
            f"{len(neck.knee_levers)} levers")


class ProfileManagerDialog(QDialog):
    """`guitar` is the open profile (its live tunings are shown for it). Emits `open_requested`
    (profile key, tuning index) to switch profiles, and `saved_as` (name) after the open setup
    was saved as a new user profile."""

    open_requested = Signal(str, int)
    saved_as = Signal(str)
    browse_requested = Signal()

    def __init__(self, guitar: SteelGuitar, settings: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Profiles")
        self.resize(720, 520)
        self.guitar = guitar
        self.settings = settings if settings is not None else {}
        self._init_ui()
        self._refresh_list(select=guitar.profile)
        self._load_startup_controls()

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        intro = QLabel(
            "A <b>profile</b> is a group of tunings (necks). <b>Factory</b> holds the built-in "
            "default tunings; your own profiles hold your tunings and are saved automatically "
            "when you edit them.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        lists = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Profiles</b>"))
        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_profile_selected)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._load_selected())
        left.addWidget(self.list_widget, stretch=1)
        lists.addLayout(left, stretch=2)

        right = QVBoxLayout()
        right.addWidget(QLabel("<b>Tunings in this profile</b>"))
        self.list_tunings = QListWidget()
        self.list_tunings.itemDoubleClicked.connect(lambda _item: self._load_selected())
        right.addWidget(self.list_tunings, stretch=1)
        lists.addLayout(right, stretch=3)
        layout.addLayout(lists, stretch=1)

        btn_row = QHBoxLayout()
        self.btn_load = QPushButton("Open")
        self.btn_load.setToolTip("Open the selected profile (and the selected tuning)")
        self.btn_load.setStyleSheet("background-color: #007bff; color: white; font-weight: bold; min-height: 28px;")
        self.btn_load.clicked.connect(self._load_selected)
        btn_row.addWidget(self.btn_load)

        self.btn_save = QPushButton("💾 Save Open Setup As...")
        self.btn_save.setToolTip("Save every tuning that is open now as a new user profile")
        self.btn_save.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; min-height: 28px;")
        self.btn_save.clicked.connect(self._save_profile)
        btn_row.addWidget(self.btn_save)

        self.btn_rename = QPushButton("Rename...")
        self.btn_rename.clicked.connect(self._rename_selected)
        btn_row.addWidget(self.btn_rename)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setStyleSheet("background-color: #dc3545; color: white; min-height: 28px;")
        self.btn_delete.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.btn_delete)

        self.btn_import = QPushButton("Import...")
        self.btn_import.setToolTip("Create a profile from a copedant file (exported copedant or profile, "
                                   "full setup, or PSG Compass). Existing profiles are never overwritten.")
        self.btn_import.clicked.connect(self._import_profiles)
        btn_row.addWidget(self.btn_import)

        self.btn_export = QPushButton("Export...")
        self.btn_export.setToolTip("Save the selected profile (all its tunings) as a .json file.")
        self.btn_export.clicked.connect(self._export_selected)
        btn_row.addWidget(self.btn_export)

        btn_row.addStretch()
        self.btn_browse = QPushButton("🔎 Browse All Tunings...")
        self.btn_browse.clicked.connect(self._browse)
        btn_row.addWidget(self.btn_browse)
        layout.addLayout(btn_row)

        # Startup default
        startup_box = QGroupBox("At startup")
        sb = QVBoxLayout(startup_box)
        self.radio_last = QRadioButton("Resume the last session")
        self.radio_profile = QRadioButton("Open this profile and tuning:")
        group = QButtonGroup(self)
        group.addButton(self.radio_last)
        group.addButton(self.radio_profile)
        sb.addWidget(self.radio_last)
        row = QHBoxLayout()
        row.addWidget(self.radio_profile)
        self.combo_startup_profile = QComboBox()
        self.combo_startup_profile.currentIndexChanged.connect(self._fill_startup_tunings)
        row.addWidget(self.combo_startup_profile, stretch=1)
        self.combo_startup_tuning = QComboBox()
        row.addWidget(self.combo_startup_tuning, stretch=2)
        self.btn_startup_current = QPushButton("Use Current")
        self.btn_startup_current.setToolTip("Use the open profile and tuning")
        self.btn_startup_current.clicked.connect(self._use_current_for_startup)
        row.addWidget(self.btn_startup_current)
        sb.addLayout(row)
        for w in (self.radio_last, self.radio_profile):
            w.toggled.connect(self._save_startup)
        self.combo_startup_tuning.currentIndexChanged.connect(self._save_startup)
        layout.addWidget(startup_box)

        close_row = QHBoxLayout()
        close_row.addStretch()
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        close_row.addWidget(self.btn_close)
        layout.addLayout(close_row)

    # ------------------------------------------------------------------ data
    def _profile_keys(self) -> List[str]:
        return [FACTORY_PROFILE] + ProfileManager.list_user_profiles()

    def _tunings_of(self, key: str) -> List[Neck]:
        if key == self.guitar.profile:
            return list(self.guitar.necks)
        try:
            guitar = ProfileManager.load_any_profile(key)
        except Exception:
            log.exception("Could not read profile %r", key)
            return []
        return guitar.necks if guitar else []

    def _selected_key(self) -> Optional[str]:
        item = self.list_widget.currentItem()
        return None if item is None else item.data(Qt.UserRole)

    def _refresh_list(self, select: Optional[str] = None):
        if select is None:
            select = self._selected_key()
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for key in self._profile_keys():
            text = ("🏭 " if key == FACTORY_PROFILE else "📁 ") + profile_label(key)
            if key == self.guitar.profile:
                text += "   (open)"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, key)
            self.list_widget.addItem(item)
            if key == select:
                self.list_widget.setCurrentItem(item)
        if self.list_widget.currentItem() is None and self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        self.list_widget.blockSignals(False)
        self._on_profile_selected()

    def _on_profile_selected(self, *_):
        key = self._selected_key()
        self.list_tunings.clear()
        if key is None:
            return
        for idx, neck in enumerate(self._tunings_of(key)):
            item = QListWidgetItem(_tuning_text(neck))
            item.setData(Qt.UserRole, idx)
            self.list_tunings.addItem(item)
        if self.list_tunings.count():
            self.list_tunings.setCurrentRow(0)
        is_user = key != FACTORY_PROFILE
        self.btn_rename.setEnabled(is_user)
        self.btn_export.setEnabled(is_user)
        self.btn_delete.setEnabled(is_user and key != self.guitar.profile)

    # ------------------------------------------------------------------ actions
    def _load_selected(self):
        key = self._selected_key()
        if key is None:
            return
        item = self.list_tunings.currentItem()
        idx = item.data(Qt.UserRole) if item else 0
        self.open_requested.emit(key, idx)
        self.accept()

    def _save_profile(self):
        default = self.guitar.profile or "My Profile"
        name, ok = QInputDialog.getText(self, "Save Open Setup as Profile",
                                        "Profile name (holds every open tuning):", text=default)
        if not ok:
            return
        safe_name = ProfileManager.sanitize_name(name)
        if not safe_name:
            QMessageBox.warning(self, "Invalid Name", "Profile names must contain letters or digits.")
            return
        if safe_name != self.guitar.profile:
            safe_name = choose_profile_name(self, safe_name)
            if safe_name is None:
                return
        try:
            path = ProfileManager.save_profile(safe_name, self.guitar)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save profile:\n{e}")
            return
        self.saved_as.emit(path.stem)
        self._refresh_list(select=path.stem)
        QMessageBox.information(self, "Saved", f"Profile '{path.stem}' saved. It is now the open profile.")

    def _rename_selected(self):
        key = self._selected_key()
        if not key:
            return
        new, ok = QInputDialog.getText(self, "Rename Profile", "New name:", text=key)
        if not ok:
            return
        try:
            new_name = ProfileManager.rename_profile(key, new)
        except (OSError, ValueError, FileNotFoundError) as e:
            QMessageBox.warning(self, "Rename Failed", str(e))
            return
        if key == self.guitar.profile:
            self.saved_as.emit(new_name)
        if self.settings.get("startup_profile") == key:
            self.settings["startup_profile"] = new_name
            save_settings(self.settings)
        self._refresh_list(select=new_name)
        self._load_startup_controls()

    def _import_profiles(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Profile", "", COPEDANT_FILE_FILTER)
        if not path:
            return
        try:
            name = ProfileManager.import_profile_file(path)
        except Exception as e:
            log.exception("Profile import failed")
            QMessageBox.critical(self, "Import Error", f"Failed to import profile:\n{e}")
            return
        self._refresh_list(select=name)
        self._load_startup_controls()
        QMessageBox.information(self, "Imported", f"Added profile '{name}'.")

    def _export_selected(self):
        key = self._selected_key()
        if not key:
            QMessageBox.information(self, "Export Profile", "Select a user profile to export.")
            return
        default = str(Path.home() / f"{key}.json")
        path, _ = QFileDialog.getSaveFileName(self, "Export Profile", default, "Copedant JSON (*.json)")
        if not path:
            return
        try:
            ProfileManager.export_profile(key, path)
        except Exception as e:
            log.exception("Profile export failed")
            QMessageBox.critical(self, "Export Error", f"Failed to export profile:\n{e}")
            return
        QMessageBox.information(self, "Exported", f"Saved profile '{key}' to:\n{path}")

    def _delete_selected(self):
        key = self._selected_key()
        if not key or key == self.guitar.profile:
            return
        reply = QMessageBox.question(
            self, "Confirm Delete", f"Delete profile '{key}' and all its tunings?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            ProfileManager.delete_user_profile(key)
            if self.settings.get("startup_profile") == key:
                self.settings.update(startup_mode=STARTUP_LAST_SESSION, startup_profile="", startup_tuning="")
                save_settings(self.settings)
            self._refresh_list(select=FACTORY_PROFILE)
            self._load_startup_controls()

    def _browse(self):
        self.browse_requested.emit()
        self.accept()

    # ------------------------------------------------------------------ startup default
    def _load_startup_controls(self):
        self._loading_startup = True
        combo = self.combo_startup_profile
        combo.blockSignals(True)
        combo.clear()
        for key in self._profile_keys():
            combo.addItem(profile_label(key), key)
        idx = combo.findData(self.settings.get("startup_profile", FACTORY_PROFILE))
        combo.setCurrentIndex(max(0, idx))
        combo.blockSignals(False)
        self._fill_startup_tunings()
        t_idx = self.combo_startup_tuning.findData(self.settings.get("startup_tuning", ""))
        self.combo_startup_tuning.setCurrentIndex(max(0, t_idx))
        if self.settings.get("startup_mode") == STARTUP_PROFILE:
            self.radio_profile.setChecked(True)
        else:
            self.radio_last.setChecked(True)
        enabled = self.radio_profile.isChecked()
        self.combo_startup_profile.setEnabled(enabled)
        self.combo_startup_tuning.setEnabled(enabled)
        self._loading_startup = False

    def _fill_startup_tunings(self, *_):
        combo = self.combo_startup_tuning
        combo.blockSignals(True)
        combo.clear()
        for neck in self._tunings_of(self.combo_startup_profile.currentData() or FACTORY_PROFILE):
            combo.addItem(f"{neck.name} ({neck.string_count} Str)", neck.name)
        combo.blockSignals(False)
        self._save_startup()

    def _use_current_for_startup(self):
        idx = self.combo_startup_profile.findData(self.guitar.profile)
        if idx >= 0:
            self.combo_startup_profile.setCurrentIndex(idx)
        parent = self.parent()
        current_idx = getattr(parent, "current_neck_idx", 0)
        if 0 <= current_idx < len(self.guitar.necks):
            t_idx = self.combo_startup_tuning.findData(self.guitar.necks[current_idx].name)
            self.combo_startup_tuning.setCurrentIndex(max(0, t_idx))
        self.radio_profile.setChecked(True)
        self._save_startup()

    def _save_startup(self, *_):
        if getattr(self, "_loading_startup", True):
            return
        enabled = self.radio_profile.isChecked()
        self.combo_startup_profile.setEnabled(enabled)
        self.combo_startup_tuning.setEnabled(enabled)
        self.settings.update(
            startup_mode=STARTUP_PROFILE if enabled else STARTUP_LAST_SESSION,
            startup_profile=self.combo_startup_profile.currentData() or FACTORY_PROFILE,
            startup_tuning=self.combo_startup_tuning.currentData() or "",
        )
        save_settings(self.settings)
