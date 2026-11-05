"""Compact string-grip selector: small chips grouped by size (dyads, triads, 4-note grips), with
the grip's name in the tooltip and in a caption under the chips."""

from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
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

GROUP_NAMES = {2: "Dyads", 3: "Triads", 4: "4-note"}

CHIP_QSS = """
    QPushButton {
        background-color: #2b303c;
        color: #e0e6ed;
        font-size: 11px;
        font-weight: bold;
        padding: 3px 8px;
        border: 1px solid #495057;
        border-radius: 10px;
    }
    QPushButton:hover { background-color: #383f4d; border-color: #6c757d; }
    QPushButton:checked { background-color: #0d6efd; color: #ffffff; border: 1px solid #ffffff; }
"""


def grip_presets_for(neck: Neck) -> Tuple[List[Tuple[str, str, Set[int]]], Set[int]]:
    """(grip cards, default pocket) for the neck's tuning family."""
    if neck.string_count >= 12 or neck.neck_type == NeckType.UNIVERSAL_12:
        return list(U12_GRIP_CARDS), {12, 11, 9, 6}
    if neck.neck_type == NeckType.C6 or "C6" in neck.name:
        return list(C6_GRIP_CARDS), {7, 6, 5, 4}
    return list(E9_CONSOLIDATED_TRIADS) + list(NEWMAN_DYAD_POCKETS), {8, 6, 5}


class GripPocketBar(QWidget):
    pocket_changed = Signal(set)  # Emits active Set[int]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.grip_buttons: List[Tuple[QPushButton, Set[int]]] = []
        self._names: Dict[frozenset, str] = {}
        self.current_neck: Optional[Neck] = None
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.group_box = QGroupBox("String Grips")
        self.group_box.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11px; }")
        box = QVBoxLayout(self.group_box)
        box.setContentsMargins(8, 6, 8, 6)
        box.setSpacing(4)

        self.grid_layout = QGridLayout()
        self.grid_layout.setHorizontalSpacing(5)
        self.grid_layout.setVerticalSpacing(5)
        box.addLayout(self.grid_layout)

        self.lbl_selected = QLabel()
        self.lbl_selected.setStyleSheet("color: #8b92a0; font-size: 11px;")
        box.addWidget(self.lbl_selected)
        box.addStretch()

        root.addWidget(self.group_box)

    def set_neck(self, neck: Neck):
        self.current_neck = neck
        while self.grid_layout.count() > 0:
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                lay = item.layout()
                while lay.count():
                    sub = lay.takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()
        self.grip_buttons.clear()
        self._names.clear()

        cards, default_pocket = grip_presets_for(neck)
        groups: Dict[int, List[Tuple[str, str, Set[int]]]] = {}
        for strings_text, desc_text, pocket in cards:
            valid = {s for s in pocket if s <= neck.string_count}
            if valid:
                groups.setdefault(len(pocket), []).append((strings_text, desc_text, valid))

        for row, size in enumerate(sorted(groups, reverse=True)):
            label = QLabel(GROUP_NAMES.get(size, f"{size}-note"))
            label.setStyleSheet("color: #adb5bd; font-size: 11px;")
            self.grid_layout.addWidget(label, row, 0)
            chips = QHBoxLayout()
            chips.setSpacing(5)
            for strings_text, desc_text, pocket in groups[size]:
                btn = self._create_chip(strings_text, desc_text, pocket)
                chips.addWidget(btn)
                self.grip_buttons.append((btn, pocket))
                self._names.setdefault(frozenset(pocket), f"{desc_text} (strings {strings_text.replace(' ', '')})")
            chips.addStretch()
            self.grid_layout.addLayout(chips, row, 1)
        self.grid_layout.setColumnStretch(1, 1)

        self.apply_pocket(default_pocket)

    def _create_chip(self, strings_text: str, desc_text: str, pocket: Set[int]) -> QPushButton:
        btn = QPushButton(strings_text.replace(" ", ""))
        btn.setCheckable(True)
        btn.setFixedHeight(24)
        btn.setToolTip(f"{desc_text}\nStrings {strings_text}")
        btn.setStyleSheet(CHIP_QSS)
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
        if not active_pocket:
            text = "No strings selected"
        else:
            name = self._names.get(frozenset(active_pocket))
            strings = "-".join(str(s) for s in sorted(active_pocket, reverse=True))
            text = name or f"Custom pocket (strings {strings})"
        self.lbl_selected.setText(f"Selected: {text}")
