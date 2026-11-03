"""Floating tool window for reverse-searching chord voicings with multi-select movement filters,

interval omissions, and an expanded Circle of Fifths proximity radar.
"""

from typing import Dict, List, Optional, Set
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.ergonomics import StanceDifficulty
from core.models import Neck
from core.theory import CHORD_FORMULAS, NOTE_NAMES_SHARP, to_root_name
from core.voicing_solver import NeighborVoicing, VoicingMatch, VoicingSolver

GRIP_DESCRIPTIONS = {
    "10-8-6": "Bass Root/5th",
    "8-6-5": "Lower Closed",
    "8-6-4": "Standard Open",
    "6-5-4": "Middle Inv",
    "5-4-3": "High Triad (A+B)",
    "4-3-1": "Top Treble",
    "10-8-6-5": "Bass 4-Block",
    "8-6-5-4": "Full Middle 4",
    "6-5-4-3": "Upper 4-Block",
    "5-4-3-2": "High 4-Block",
    "8-6-5-4-3": "5-Note Block",
    "7-6-5": "Root Triad",
    "6-5-3": "1st Inversion",
    "5-3-2": "2nd Inversion",
    "4-3-2": "Am / Upper",
    "3-2-1": "9th Treble",
    "7-6-5-4": "C6 Root Block",
    "6-5-4-3": "C6 Comping Inv",
    "5-4-3-2": "Upper 4-Block",
    "4-3-2-1": "6/9 Swing Grip",
    "10-7-5": "Deep Bass",
    "9-8-7-6": "Lower 4-Block",
}


class VoicingFinderWidget(QWidget):
    voicing_applied = Signal(int, list, list)
    target_changed = Signal(str, str)

    def __init__(self, neck: Neck, initial_root: str = "E", initial_chord: str = "Major", parent=None):
        super().__init__(parent)
        self.neck = neck
        self.all_matches: List[VoicingMatch] = []
        self.grip_buttons: Dict[str, QPushButton] = {}
        self.interval_checkboxes: Dict[str, QCheckBox] = {}
        self.mechanic_buttons: Dict[str, QPushButton] = {}
        self.selected_match: Optional[VoicingMatch] = None

        self.setWindowTitle("Chord Voicing Finder & Circle of Fifths Proximity Radar")
        self.resize(1100, 820)

        self._init_ui(initial_root, initial_chord)
        self._rebuild_interval_chips()
        self.run_search()

    def _init_ui(self, initial_root: str, initial_chord: str):
        root_vbox = QVBoxLayout(self)
        root_vbox.setContentsMargins(10, 10, 10, 10)
        root_vbox.setSpacing(8)

        # 1. Target Controls Bar
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>Root:</b>"))
        self.root_combo = QComboBox()
        self.root_combo.addItems(NOTE_NAMES_SHARP)
        if initial_root in NOTE_NAMES_SHARP:
            self.root_combo.setCurrentText(initial_root)
        self.root_combo.currentIndexChanged.connect(self._on_combo_changed)
        top_bar.addWidget(self.root_combo)

        top_bar.addSpacing(10)
        top_bar.addWidget(QLabel("<b>Chord:</b>"))
        self.chord_combo = QComboBox()
        self.chord_combo.addItems(list(CHORD_FORMULAS.keys()))
        if initial_chord in CHORD_FORMULAS:
            self.chord_combo.setCurrentText(initial_chord)
        self.chord_combo.currentIndexChanged.connect(self._on_chord_combo_changed)
        top_bar.addWidget(self.chord_combo)

        top_bar.addSpacing(15)
        top_bar.addWidget(QLabel("<b>Pedal Filter:</b>"))
        self.combo_controller_filter = QComboBox()
        self.combo_controller_filter.addItem("Any / All Playable", None)
        self.combo_controller_filter.addItem("Open Bar Only (No Pedals)", 0)
        self.combo_controller_filter.addItem("Max 1 Controller (Pedal/Lever)", 1)
        self.combo_controller_filter.addItem("Max 2 Controllers (A+B Splits)", 2)
        self.combo_controller_filter.currentIndexChanged.connect(self.run_search)
        top_bar.addWidget(self.combo_controller_filter)

        top_bar.addSpacing(15)
        self.cb_filter_awkward = QCheckBox("Hide Awkward Stances")
        self.cb_filter_awkward.setChecked(False)
        self.cb_filter_awkward.stateChanged.connect(self.run_search)
        top_bar.addWidget(self.cb_filter_awkward)

        top_bar.addStretch()

        self.btn_select_all_grips = QPushButton("All Grips")
        self.btn_select_all_grips.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_select_all_grips.clicked.connect(self._select_all_grips)
        top_bar.addWidget(self.btn_select_all_grips)

        self.btn_clear_all_grips = QPushButton("Clear Grips")
        self.btn_clear_all_grips.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_clear_all_grips.clicked.connect(self._clear_all_grips)
        top_bar.addWidget(self.btn_clear_all_grips)

        root_vbox.addLayout(top_bar)

        # 2. Chord Intervals Omission Filter Ribbon
        filter_box = QGroupBox("Filter Chord Intervals (Uncheck to omit / find shell voicings)")
        f_layout = QHBoxLayout(filter_box)
        f_layout.setContentsMargins(8, 4, 8, 4)
        f_layout.setSpacing(12)

        self.interval_container = QWidget()
        self.interval_chips_layout = QHBoxLayout(self.interval_container)
        self.interval_chips_layout.setContentsMargins(0, 0, 0, 0)
        self.interval_chips_layout.setSpacing(10)
        f_layout.addWidget(self.interval_container)

        f_layout.addStretch()

        self.btn_reset_intervals = QPushButton("Reset All Intervals")
        self.btn_reset_intervals.setStyleSheet("font-size: 10px; padding: 2px 8px;")
        self.btn_reset_intervals.clicked.connect(self._reset_all_intervals)
        f_layout.addWidget(self.btn_reset_intervals)

        root_vbox.addWidget(filter_box)

        # 3. Scrollable Grip Filter Chips
        scroll = QScrollArea()
        scroll.setFixedHeight(46)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.chips_container = QWidget()
        self.chips_layout = QHBoxLayout(self.chips_container)
        self.chips_layout.setContentsMargins(0, 2, 0, 2)
        self.chips_layout.setSpacing(6)

        scroll.setWidget(self.chips_container)
        root_vbox.addWidget(scroll)
        self._rebuild_grip_chips()

        # 4. Splitter enclosing Primary Voicings (Top) and Expanded Proximity Radar (Bottom)
        splitter = QSplitter(Qt.Vertical)

        # Top Section: Search Results Table
        top_panel = QWidget()
        top_panel_layout = QVBoxLayout(top_panel)
        top_panel_layout.setContentsMargins(0, 0, 0, 0)
        top_panel_layout.setSpacing(4)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Fret", "Pedals / Levers", "Ergonomics", "Grip Strings", "Bass Note", "Interval Formula", "Action"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        top_panel_layout.addWidget(self.table)
        splitter.addWidget(top_panel)

        # Bottom Section: Expanded Proximity Radar with Multi-Select Toggle Chips
        bottom_panel = QWidget()
        bottom_panel_layout = QVBoxLayout(bottom_panel)
        bottom_panel_layout.setContentsMargins(0, 0, 0, 0)
        bottom_panel_layout.setSpacing(6)

        self.radar_box = QGroupBox("Circle of Fifths Proximity Radar (IV, V, V7, vi, ii Pathways from Selected Voicing)")
        radar_vbox = QVBoxLayout(self.radar_box)
        radar_vbox.setContentsMargins(8, 6, 8, 6)
        radar_vbox.setSpacing(6)

        # Multi-Select Movement Filter Chips
        chips_bar = QHBoxLayout()
        chips_bar.addWidget(QLabel("<b>Movement Filters (Multi-Select):</b>"))

        mechanics_def = [
            ("Same-Fret Pedal Drop", "🟢 Same-Fret Drops (Δ0)"),
            ("Hold Pedals & Slide", "🔵 Hold Pedals & Slide (+2)"),
            ("Open Bar Shift", "🟡 Open Bar Shifts"),
            ("Position Shift", "⚪ Position Shifts"),
        ]

        for m_key, m_label in mechanics_def:
            btn = QPushButton(m_label)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 11px;
                    font-weight: bold;
                    padding: 3px 10px;
                    min-height: 24px;
                }
                QPushButton:checked {
                    background-color: #0d6efd;
                    color: white;
                }
            """)
            btn.toggled.connect(self._on_mechanic_toggled)
            chips_bar.addWidget(btn)
            self.mechanic_buttons[m_key] = btn

        chips_bar.addStretch()

        btn_all_m = QPushButton("Select All")
        btn_all_m.setStyleSheet("font-size: 10px; padding: 2px 6px;")
        btn_all_m.clicked.connect(self._select_all_mechanics)
        chips_bar.addWidget(btn_all_m)

        radar_vbox.addLayout(chips_bar)

        self.table_radar = QTableWidget()
        self.table_radar.setColumnCount(5)
        self.table_radar.setHorizontalHeaderLabels([
            "Relationship", "Chord", "Movement Mechanic", "Bar Shift (Δ)", "Physical Action Instructions"
        ])
        self.table_radar.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_radar.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_radar.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_radar.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_radar.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_radar.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_radar.cellDoubleClicked.connect(self._on_radar_row_double_clicked)
        radar_vbox.addWidget(self.table_radar)

        bottom_panel_layout.addWidget(self.radar_box)
        splitter.addWidget(bottom_panel)

        # Generous vertical space allocation: 50% Top, 50% Bottom
        splitter.setSizes([350, 350])
        root_vbox.addWidget(splitter, stretch=1)

        # 5. Bottom Status Bar
        bottom_bar = QHBoxLayout()
        self.status_lbl = QLabel("")
        bottom_bar.addWidget(self.status_lbl)
        bottom_bar.addStretch()

        self.btn_apply = QPushButton("Apply Position")
        self.btn_apply.setStyleSheet(
            "background-color: #0d6efd; color: white; font-weight: bold; min-height: 26px; padding: 0 16px;"
        )
        self.btn_apply.clicked.connect(self._apply_current_row)
        bottom_bar.addWidget(self.btn_apply)

        root_vbox.addLayout(bottom_bar)

    def _select_all_mechanics(self):
        for btn in self.mechanic_buttons.values():
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)
        self._on_mechanic_toggled()

    def _on_mechanic_toggled(self):
        if self.selected_match:
            self._update_proximity_radar(self.selected_match)

    def _rebuild_interval_chips(self):
        for cb in self.interval_checkboxes.values():
            self.interval_chips_layout.removeWidget(cb)
            cb.deleteLater()
        self.interval_checkboxes.clear()

        chord_type = self.chord_combo.currentText()
        formula = CHORD_FORMULAS.get(chord_type, {})

        for interval_st, label in sorted(formula.items(), key=lambda x: x[0]):
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.setStyleSheet("font-weight: bold; font-size: 11px;")
            cb.toggled.connect(self.run_search)
            self.interval_chips_layout.addWidget(cb)
            self.interval_checkboxes[label] = cb

    def _reset_all_intervals(self):
        for cb in self.interval_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)
        self.run_search()

    def _rebuild_grip_chips(self):
        for btn in self.grip_buttons.values():
            self.chips_layout.removeWidget(btn)
            btn.deleteLater()
        self.grip_buttons.clear()

        candidate_grips = VoicingSolver.get_candidate_grips(self.neck)
        for g in candidate_grips:
            key = "-".join(map(str, sorted(g, reverse=True)))
            desc = GRIP_DESCRIPTIONS.get(key, "Grip")
            display_num = " - ".join(map(str, sorted(g, reverse=True)))

            btn = QPushButton(f"{display_num} ({desc})")
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setStyleSheet("min-width: 90px; height: 32px; font-size: 10px; font-weight: bold; padding: 2px 6px;")
            btn.toggled.connect(self._filter_table)
            self.chips_layout.addWidget(btn)
            self.grip_buttons[key] = btn

        self.chips_layout.addStretch()

    def update_neck(self, neck: Neck):
        self.neck = neck
        self._rebuild_grip_chips()
        self.run_search()

    def set_target(self, root: str, chord_type: str):
        self.root_combo.blockSignals(True)
        self.chord_combo.blockSignals(True)
        sharp_root = to_root_name(root)  # accepts flats like "Bb" (D-05)
        if sharp_root:
            self.root_combo.setCurrentText(sharp_root)
        if chord_type in CHORD_FORMULAS:
            self.chord_combo.setCurrentText(chord_type)
        self.root_combo.blockSignals(False)
        self.chord_combo.blockSignals(False)
        self._rebuild_interval_chips()
        self.run_search()

    def _on_chord_combo_changed(self):
        self._rebuild_interval_chips()
        self._on_combo_changed()

    def _on_combo_changed(self):
        root = self.root_combo.currentText()
        chord_type = self.chord_combo.currentText()
        self.target_changed.emit(root, chord_type)
        self.run_search()

    def run_search(self):
        root = self.root_combo.currentText()
        chord_type = self.chord_combo.currentText()
        filter_awkward = self.cb_filter_awkward.isChecked()
        max_ctrls = self.combo_controller_filter.currentData()

        omitted = {lbl for lbl, cb in self.interval_checkboxes.items() if not cb.isChecked()}

        self.all_matches = VoicingSolver.find_all_voicings(
            neck=self.neck,
            root_name=root,
            chord_type=chord_type,
            max_fret=15,
            filter_awkward=filter_awkward,
            omitted_intervals=omitted,
            max_controllers=max_ctrls,
        )
        self._filter_table()

    def _filter_table(self):
        active_grips = {k for k, btn in self.grip_buttons.items() if btn.isChecked()}
        filtered = [m for m in self.all_matches if m.grip_key in active_grips]

        self.table.setRowCount(len(filtered))
        for row, m in enumerate(filtered):
            levers_str = " + ".join(m.engaged_levers) if m.engaged_levers else "Open (None)"
            grip_display = " - ".join(map(str, m.grip_strings))

            fret_item = QTableWidgetItem(f"Fret {m.fret}")
            fret_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, fret_item)

            self.table.setItem(row, 1, QTableWidgetItem(levers_str))

            diff = m.ergonomics.difficulty
            if diff == StanceDifficulty.NATURAL:
                ergo_text = "🟢 Natural"
            elif diff == StanceDifficulty.STANDARD:
                ergo_text = "🟡 Standard"
            else:
                ergo_text = "🟠 Awkward"

            ergo_item = QTableWidgetItem(ergo_text)
            ergo_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, ergo_item)

            grip_item = QTableWidgetItem(grip_display)
            grip_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, grip_item)

            bass_item = QTableWidgetItem(f"{m.bass_note} ({m.bass_interval})")
            bass_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, bass_item)

            self.table.setItem(row, 5, QTableWidgetItem(m.voicing_formula))

            btn = QPushButton("Go")
            btn.setStyleSheet("font-weight: bold; padding: 2px 8px;")
            btn.clicked.connect(lambda _, item=m: self._apply_match(item))
            self.table.setCellWidget(row, 6, btn)

        omitted_count = sum(1 for cb in self.interval_checkboxes.values() if not cb.isChecked())
        omitted_text = f" (Omitted {omitted_count} intervals)" if omitted_count > 0 else ""
        self.status_lbl.setText(
            f"Showing <b>{len(filtered)}</b> playable voicings found{omitted_text}."
        )

        if filtered:
            self.table.selectRow(0)
            self.selected_match = filtered[0]
            self._update_proximity_radar(self.selected_match)
        else:
            self.table_radar.setRowCount(0)

    def _on_table_selection_changed(self):
        row = self.table.currentRow()
        active_grips = {k for k, btn in self.grip_buttons.items() if btn.isChecked()}
        filtered = [m for m in self.all_matches if m.grip_key in active_grips]

        if 0 <= row < len(filtered):
            self.selected_match = filtered[row]
            self._update_proximity_radar(self.selected_match)

    def _update_proximity_radar(self, match: VoicingMatch):
        """Calculates nearest Circle of Fifths neighbors (IV, V, V7, vi, ii) with multi-selected mechanics."""
        root = self.root_combo.currentText()

        # Gather all currently checked movement mechanic filters
        allowed = {k for k, btn in self.mechanic_buttons.items() if btn.isChecked()}

        neighbors = VoicingSolver.find_circle_neighbors(
            neck=self.neck,
            origin_root=root,
            origin_fret=match.fret,
            origin_grip=match.grip_strings,
            origin_levers=match.engaged_levers,
            allowed_mechanics=allowed,
        )

        self.table_radar.setRowCount(len(neighbors))

        for row, n in enumerate(neighbors):
            rel_item = QTableWidgetItem(n.relationship)
            rel_item.setTextAlignment(Qt.AlignCenter)
            if "V7" in n.relationship:
                rel_item.setForeground(QColor(220, 53, 69))
                rel_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.table_radar.setItem(row, 0, rel_item)

            chord_item = QTableWidgetItem(n.chord_name)
            chord_item.setTextAlignment(Qt.AlignCenter)
            self.table_radar.setItem(row, 1, chord_item)

            type_item = QTableWidgetItem(n.movement_type)
            type_item.setTextAlignment(Qt.AlignCenter)
            if "Hold" in n.movement_type:
                type_item.setForeground(QColor(13, 110, 253))
            elif "Same-Fret" in n.movement_type:
                type_item.setForeground(QColor(40, 167, 69))
            elif "Open" in n.movement_type:
                type_item.setForeground(QColor(255, 193, 7))
            self.table_radar.setItem(row, 2, type_item)

            delta_str = f"{'+' if n.delta_frets > 0 else ''}{n.delta_frets}" if n.delta_frets != 0 else "0 (Anchor)"
            delta_item = QTableWidgetItem(delta_str)
            delta_item.setTextAlignment(Qt.AlignCenter)
            self.table_radar.setItem(row, 3, delta_item)

            action_item = QTableWidgetItem(n.transition_summary)
            action_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.table_radar.setItem(row, 4, action_item)

    def _on_radar_row_double_clicked(self, row: int, col: int):
        if not self.selected_match:
            return
        root = self.root_combo.currentText()
        allowed = {k for k, btn in self.mechanic_buttons.items() if btn.isChecked()}
        neighbors = VoicingSolver.find_circle_neighbors(
            neck=self.neck,
            origin_root=root,
            origin_fret=self.selected_match.fret,
            origin_grip=self.selected_match.grip_strings,
            origin_levers=self.selected_match.engaged_levers,
            allowed_mechanics=allowed,
        )
        if 0 <= row < len(neighbors):
            n = neighbors[row]
            self.voicing_applied.emit(n.fret, n.engaged_levers, n.grip_strings)

    def _select_all_grips(self):
        for btn in self.grip_buttons.values():
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)
        self._filter_table()

    def _clear_all_grips(self):
        for btn in self.grip_buttons.values():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
        self._filter_table()

    def _apply_match(self, m: VoicingMatch):
        self.voicing_applied.emit(m.fret, m.engaged_levers, m.grip_strings)

    def _apply_current_row(self):
        row = self.table.currentRow()
        if row >= 0:
            btn = self.table.cellWidget(row, 6)
            if btn:
                btn.click()

    def _on_row_double_clicked(self, row: int, col: int):
        self._apply_current_row()