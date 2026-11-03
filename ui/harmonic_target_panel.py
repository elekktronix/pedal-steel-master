"""Harmonic Target and Interval Analysis dockable panel."""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.theory import CHORD_FORMULAS, NOTE_NAMES_SHARP
from core.voicing_solver import VoicingSolver


class HarmonicTargetPanel(QWidget):
    target_changed = Signal(str, str)  # root, chord_type
    reset_requested = Signal()         # Reset pedals/levers
    find_voicings_requested = Signal() # Launch chord position solver

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        root_vbox = QVBoxLayout(self)
        root_vbox.setContentsMargins(0, 0, 0, 0)
        root_vbox.setSpacing(0)

        self.box = QGroupBox("Harmonic Target / Interval Analysis")
        self.box.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11px; }")
        grid = QGridLayout(self.box)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setSpacing(6)

        grid.addWidget(QLabel("Root:"), 0, 0)
        self.combo_root = QComboBox()
        self.combo_root.addItem("None")
        self.combo_root.addItems(NOTE_NAMES_SHARP)
        self.combo_root.setCurrentText("E")
        self.combo_root.currentIndexChanged.connect(self._on_change)
        grid.addWidget(self.combo_root, 0, 1)

        grid.addWidget(QLabel("Chord:"), 1, 0)
        self.combo_chord = QComboBox()
        self.combo_chord.addItems(list(CHORD_FORMULAS.keys()))
        self.combo_chord.setCurrentText("Major")
        self.combo_chord.currentIndexChanged.connect(self._on_change)
        grid.addWidget(self.combo_chord, 1, 1)

        # Franklin Triad Substitution Chip
        self.lbl_triad_sub = QLabel("Franklin Triad: None")
        self.lbl_triad_sub.setAlignment(Qt.AlignCenter)
        self.lbl_triad_sub.setWordWrap(True)
        self.lbl_triad_sub.setStyleSheet("""
            QLabel {
                background-color: #172b38;
                color: #5bc0de;
                font-weight: bold;
                font-size: 10px;
                border: 1px solid #28a745;
                border-radius: 4px;
                padding: 3px 6px;
            }
        """)
        grid.addWidget(self.lbl_triad_sub, 2, 0, 1, 2)

        self.btn_reset = QPushButton("Reset Pedals/Levers")
        self.btn_reset.setStyleSheet("padding: 3px 6px; font-size: 11px;")
        self.btn_reset.clicked.connect(self.reset_requested.emit)
        grid.addWidget(self.btn_reset, 3, 0, 1, 2)

        self.btn_find = QPushButton("🔍 Find Chord Positions")
        self.btn_find.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 4px 10px;
                font-size: 11px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #218838; }
        """)
        self.btn_find.clicked.connect(self.find_voicings_requested.emit)
        grid.addWidget(self.btn_find, 4, 0, 1, 2)

        root_vbox.addWidget(self.box)

    def _on_change(self):
        root = self.combo_root.currentText()
        chord_type = self.combo_chord.currentText()
        if root == "None":
            self.lbl_triad_sub.setText("Franklin Triad: None")
            self.target_changed.emit(None, None)
        else:
            sub_info = VoicingSolver.get_triad_substitution(root, chord_type)
            if sub_info:
                sub_triad, rel, desc = sub_info
                self.lbl_triad_sub.setText(f"Franklin: Play {sub_triad} ({rel})")
                self.lbl_triad_sub.setToolTip(desc)
            else:
                self.lbl_triad_sub.setText(f"Franklin: {root} Root Position")
                self.lbl_triad_sub.setToolTip(f"Standard {root} triad")
            self.target_changed.emit(root, chord_type)

    def set_target(self, root: str, chord_type: str):
        self.combo_root.blockSignals(True)
        self.combo_chord.blockSignals(True)
        if root in NOTE_NAMES_SHARP:
            self.combo_root.setCurrentText(root)
        if chord_type in CHORD_FORMULAS:
            self.combo_chord.setCurrentText(chord_type)
        self.combo_root.blockSignals(False)
        self.combo_chord.blockSignals(False)
        self._on_change()

    def get_root(self) -> str:
        return self.combo_root.currentText()

    def get_chord_type(self) -> str:
        return self.combo_chord.currentText()