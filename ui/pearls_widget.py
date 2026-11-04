"""UI Explorer for Jeff Newman's 'Strings of Pearls' Harmonized Runs."""

from typing import List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.models import Neck
from core.pearls_engine import PearlsEngine, PearlStep
from core.theory import note_names, respell


class StringsOfPearlsDialog(QDialog):
    step_selected = Signal(int, set, set)  # fret, controllers, target_strings

    def __init__(self, neck: Neck, parent=None):
        super().__init__(parent)
        self.neck = neck
        self.parent_window = parent
        self.setWindowTitle("Strings of Pearls — Harmonized Scale Runner (Newman)")
        self.resize(860, 560)

        self.current_key = "G"
        self.current_track = "Strings 3 & 5 (6ths / 3rds)"
        self.current_step_idx: int = -1
        self.steps: List[PearlStep] = []

        self._init_ui()
        self._refresh_pearls_run()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 1. Configuration Strip
        top_box = QGroupBox("Harmonized Track Configuration")
        top_l = QGridLayout(top_box)
        top_l.setContentsMargins(10, 8, 10, 8)
        top_l.setSpacing(8)

        top_l.addWidget(QLabel("<b>Key Center:</b>"), 0, 0)
        self.combo_key = QComboBox()
        self.combo_key.addItems(note_names())
        self.combo_key.setCurrentText(respell(self.current_key))
        self.combo_key.currentIndexChanged.connect(self._on_config_changed)
        top_l.addWidget(self.combo_key, 0, 1)

        top_l.addWidget(QLabel("<b>Twin-Track Pair:</b>"), 0, 2)
        self.combo_track = QComboBox()
        self.combo_track.addItems(list(PearlsEngine.TWIN_TRACKS.keys()))
        self.combo_track.setCurrentText(self.current_track)
        self.combo_track.currentIndexChanged.connect(self._on_config_changed)
        top_l.addWidget(self.combo_track, 0, 3)

        root.addWidget(top_box)

        # 2. Sequential Slider Controls
        nav_h = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Prev Step")
        self.btn_prev.setStyleSheet("font-weight: bold; min-height: 32px;")
        self.btn_prev.clicked.connect(self._prev_step)
        nav_h.addWidget(self.btn_prev)

        self.lbl_step_info = QLabel("Step: None")
        self.lbl_step_info.setAlignment(Qt.AlignCenter)
        self.lbl_step_info.setStyleSheet("""
            background-color: #212529;
            color: #ffc107;
            font-weight: bold;
            font-size: 13px;
            border-radius: 4px;
            padding: 6px;
        """)
        nav_h.addWidget(self.lbl_step_info, stretch=1)

        self.btn_next = QPushButton("Next Step ▶")
        self.btn_next.setStyleSheet("font-weight: bold; min-height: 32px;")
        self.btn_next.clicked.connect(self._next_step)
        nav_h.addWidget(self.btn_next)

        root.addLayout(nav_h)

        # 3. Pearls Run Steps Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Scale Degree", "Fret", "Slide Delta", "Pedals / Levers", "Sounding Dyad", "Interval Type"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.cellClicked.connect(self._on_table_row_clicked)
        root.addWidget(self.table, stretch=1)

        # 4. Action Buttons
        btn_h = QHBoxLayout()
        self.btn_play_dyad = QPushButton("🔊 Play Selected Dyad")
        self.btn_play_dyad.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; min-height: 30px;")
        self.btn_play_dyad.clicked.connect(self._play_active_step)
        btn_h.addWidget(self.btn_play_dyad)

        btn_h.addStretch()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_h.addWidget(btn_close)

        root.addLayout(btn_h)

    def _on_config_changed(self):
        self.current_key = self.combo_key.currentText()
        self.current_track = self.combo_track.currentText()
        self._refresh_pearls_run()

    def _refresh_pearls_run(self):
        self.steps = PearlsEngine.generate_scale_run(
            key_root=self.current_key,
            track_name=self.current_track,
            neck=self.neck,
        )

        self.table.setRowCount(len(self.steps))
        for idx, s in enumerate(self.steps):
            lev_str = " + ".join(sorted(s.controllers)) if s.controllers else "Open"
            delta_str = f"+{s.fret_delta}" if s.fret_delta > 0 else f"{s.fret_delta}" if s.fret_delta < 0 else "—"

            self.table.setItem(idx, 0, QTableWidgetItem(s.degree_label))
            self.table.setItem(idx, 1, QTableWidgetItem(f"Fret {s.fret}"))
            self.table.setItem(idx, 2, QTableWidgetItem(delta_str))
            self.table.setItem(idx, 3, QTableWidgetItem(lev_str))
            self.table.setItem(idx, 4, QTableWidgetItem(f"{s.notes[0]} & {s.notes[1]}"))
            self.table.setItem(idx, 5, QTableWidgetItem(s.interval_desc))

        if self.steps:
            self._select_step(0)

    def _select_step(self, idx: int):
        if 0 <= idx < len(self.steps):
            self.current_step_idx = idx
            self.table.selectRow(idx)
            step = self.steps[idx]
            lev_str = " + ".join(sorted(step.controllers)) if step.controllers else "Open"
            self.lbl_step_info.setText(
                f"{step.degree_label} ➔ Fret {step.fret} ({lev_str}) | {step.notes[0]} & {step.notes[1]} ({step.interval_desc})"
            )
            # Transmit to main fretboard
            self.step_selected.emit(step.fret, step.controllers, set(step.string_pair))
            self._play_active_step()

    def _next_step(self):
        if not self.steps:
            return
        nxt = (self.current_step_idx + 1) % len(self.steps)
        self._select_step(nxt)

    def _prev_step(self):
        if not self.steps:
            return
        prv = (self.current_step_idx - 1) % len(self.steps)
        self._select_step(prv)

    def _on_table_row_clicked(self, row: int, col: int):
        self._select_step(row)

    def _play_active_step(self):
        if self.current_step_idx < 0 or self.current_step_idx >= len(self.steps):
            return
        if self.parent_window and hasattr(self.parent_window, "_play_pocket"):
            self.parent_window._play_pocket(roll=False)