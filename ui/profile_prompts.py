"""Shared prompts for saving user profiles (D-38)."""

from typing import Optional

from PySide6.QtWidgets import QMessageBox, QWidget

from core.profile_manager import ProfileManager


def choose_profile_name(parent: QWidget, safe_name: str) -> Optional[str]:
    """Returns the profile name to save under, or None if the user cancels.

    If `safe_name` is free it is returned as-is. Otherwise the user chooses between overwriting it
    and saving under the next free name ("Name 2", ...), so different names that sanitize to the
    same file never overwrite each other silently.
    """
    if not ProfileManager.profile_exists(safe_name):
        return safe_name
    alternative = ProfileManager.unique_profile_name(safe_name)
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle("Profile Exists")
    box.setText(f"A profile named '{safe_name}' already exists.")
    btn_overwrite = box.addButton("Overwrite", QMessageBox.DestructiveRole)
    btn_new = box.addButton(f"Save as '{alternative}'", QMessageBox.AcceptRole)
    box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(btn_new)
    box.exec()
    clicked = box.clickedButton()
    if clicked is btn_overwrite:
        return safe_name
    if clicked is btn_new:
        return alternative
    return None
