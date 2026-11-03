"""Dialog for saving, naming, and managing custom neck profiles."""

from copy import deepcopy
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.models import Neck
from core.profile_manager import ProfileManager


class ProfileManagerDialog(QDialog):
    profile_selected = Signal(str)  # Emits name of profile to load

    def __init__(self, current_neck: Neck, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Custom Neck Profiles")
        self.resize(480, 360)

        self.current_neck = current_neck
        self._init_ui()
        self._refresh_list()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Save Section
        layout.addWidget(QLabel("<b>Save Current Active Neck as Profile:</b>"))
        save_row = QHBoxLayout()
        self.txt_profile_name = QLineEdit()
        self.txt_profile_name.setPlaceholderText("e.g. My 12-String Universal or Buddy Emmons E9")
        self.txt_profile_name.setText(self.current_neck.name)
        save_row.addWidget(self.txt_profile_name)

        self.btn_save = QPushButton("💾 Save As Profile")
        self.btn_save.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; min-height: 28px;")
        self.btn_save.clicked.connect(self._save_profile)
        save_row.addWidget(self.btn_save)
        layout.addLayout(save_row)

        layout.addSpacing(10)

        # 2. Existing Profiles List
        layout.addWidget(QLabel("<b>Saved User Profiles:</b>"))
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, stretch=1)

        # 3. Action Buttons
        btn_row = QHBoxLayout()
        self.btn_load = QPushButton("Load Selected")
        self.btn_load.setStyleSheet("background-color: #007bff; color: white; font-weight: bold; min-height: 28px;")
        self.btn_load.clicked.connect(self._load_selected)
        btn_row.addWidget(self.btn_load)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setStyleSheet("background-color: #dc3545; color: white; min-height: 28px;")
        self.btn_delete.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.btn_delete)

        btn_row.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)

        layout.addLayout(btn_row)

    def _refresh_list(self):
        self.list_widget.clear()
        profiles = ProfileManager.list_user_profiles()
        for p in profiles:
            self.list_widget.addItem(p)

    def _save_profile(self):
        name = self.txt_profile_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a profile name.")
            return

        safe_name = ProfileManager.sanitize_name(name)
        if not safe_name:
            QMessageBox.warning(self, "Invalid Name", "Profile names must contain letters or digits.")
            return
        if ProfileManager.profile_exists(safe_name):
            reply = QMessageBox.question(
                self, "Overwrite Profile", f"Profile '{safe_name}' already exists. Overwrite it?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        # Save a linked copy; the active neck itself is not modified.
        profile_neck = deepcopy(self.current_neck)
        profile_neck.name = safe_name
        profile_neck.source_profile = safe_name
        try:
            path = ProfileManager.save_user_profile(safe_name, profile_neck)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save profile:\n{e}")
            return
        QMessageBox.information(self, "Saved", f"Profile '{path.stem}' saved successfully!")
        self._refresh_list()

    def _load_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        self.profile_selected.emit(item.text())
        self.accept()

    def _delete_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        name = item.text()
        reply = QMessageBox.question(
            self, "Confirm Delete", f"Are you sure you want to delete profile '{name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            ProfileManager.delete_user_profile(name)
            self._refresh_list()