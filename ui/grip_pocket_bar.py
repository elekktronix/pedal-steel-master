"""Compact 2-row grid string pocket selector with consolidated non-duplicate E9 grips."""

from typing import List, Optional, Set, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.grip_presets import (
    C6_GRIP_CARDS,
    E9_CONSOLIDATED_TRIADS,
    NEWMAN_DYAD_POCKETS,
    U12_GRIP_CARDS,
)
from core.models import Neck, NeckType


class GripPocketBar(QWidget):
    pocket_changed = Signal(set)  # Emits active Set[int]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.grip_buttons: List[Tuple[QPushButton, Set[int]]] = []
        self.current_neck: Optional[Neck] = None
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.group_box = QGroupBox("String Grips & Pockets (Triad Groups 10➔1 & Dyads)")
        self.group_box.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11px; }")
        self.grid_layout = QGridLayout(self.group_box)
        self.grid_layout.setContentsMargins(6, 6, 6, 6)
        self.grid_layout.setSpacing(5)

        root.addWidget(self.group_box)

    def set_neck(self, neck: Neck):
        self.current_neck = neck
        while self.grid_layout.count() > 0:
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.grip_buttons.clear()

        # Determine presets based on tuning
        if neck.string_count >= 12 or neck.neck_type == NeckType.UNIVERSAL_12:
            row1_presets = U12_GRIP_CARDS[:6]
            row2_presets = U12_GRIP_CARDS[6:]
            default_pocket = {12, 11, 9, 6}
        elif neck.neck_type == NeckType.C6 or "C6" in neck.name:
            row1_presets = C6_GRIP_CARDS[:6]
            row2_presets = C6_GRIP_CARDS[6:]
            default_pocket = {7, 6, 5, 4}
        else:
            # E9: Row 1 = 6 Consolidated Triads (Descending 10 -> 1)
            row1_presets = E9_CONSOLIDATED_TRIADS
            # E9: Row 2 = 4 Dyads (Descending 8 -> 3, High-string first)
            row2_presets = NEWMAN_DYAD_POCKETS
            default_pocket = {8, 6, 5}  # Group 3 (Low Triad)

        # Render Row 1: Triads (10-8-6 down to 4-3-1)
        for col_idx, (strings_text, desc_text, pocket) in enumerate(row1_presets):
            valid_pocket = {s for s in pocket if s <= neck.string_count}
            btn = self._create_card_button(strings_text, desc_text, valid_pocket)
            self.grid_layout.addWidget(btn, 0, col_idx)
            self.grip_buttons.append((btn, valid_pocket))

        # Render Row 2: Dyads (8-5 down to 5-3)
        for col_idx, (strings_text, desc_text, pocket) in enumerate(row2_presets):
            valid_pocket = {s for s in pocket if s <= neck.string_count}
            btn = self._create_card_button(strings_text, desc_text, valid_pocket)
            self.grid_layout.addWidget(btn, 1, col_idx)
            self.grip_buttons.append((btn, valid_pocket))

        self.apply_pocket(default_pocket)

    def _create_card_button(self, strings_text: str, desc_text: str, pocket: Set[int]) -> QPushButton:
        clean_text = f"{strings_text}\n{desc_text}"
        btn = QPushButton(clean_text)
        btn.setCheckable(True)
        btn.setFixedHeight(38)
        btn.setMinimumWidth(114)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #2b303c;
                color: #e0e6ed;
                font-size: 10px;
                font-weight: bold;
                padding: 2px 6px;
                text-align: center;
                border: 1px solid #495057;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #383f4d;
                border-color: #6c757d;
            }
            QPushButton:checked {
                background-color: #0d6efd;
                color: #ffffff;
                border: 1.5px solid #ffffff;
            }
        """)
        btn.clicked.connect(lambda _, p=pocket: self.apply_pocket(p))
        return btn

    def apply_pocket(self, pocket: Set[int]):
        valid = {s for s in pocket if not self.current_neck or s <= self.current_neck.string_count}
        self.sync_highlights(valid)
        self.pocket_changed.emit(valid)

    def sync_highlights(self, active_pocket: Set[int]):
        for btn, p in self.grip_buttons:
            btn.blockSignals(True)
            btn.setChecked(p == active_pocket and len(p) > 0)
            btn.blockSignals(False)