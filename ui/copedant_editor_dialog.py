"""Copedant Setup & Tuning Editor Dialog with distinct column lanes,
fixed-geometry steppers, Franklin P1 vs P4 insertion, persistent disk saving,
interactive Mechanical Splits (with Control 1 & Control 2 dropdowns), and dedicated Half-Stops configuration.
"""

from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.models import (
    CopedantChange,
    HalfStopRule,
    Neck,
    NeckType,
    SplitRule,
    SteelGuitar,
    StringPitch,
    detect_potential_half_stops,
    detect_potential_splits,
)
from core.profile_manager import ProfileManager
from core.theory import NOTE_NAMES_SHARP, midi_to_note_name, note_to_midi

STANDARDIZED_KNEE_LEVERS: List[Tuple[str, str, str]] = [
    ("LKL", "Left Knee Left", "Left Knee"),
    ("LKV", "Left Knee Vertical", "Left Knee"),
    ("LKR", "Left Knee Right", "Left Knee"),
    ("LKL2", "Left Knee Left 2", "Left Knee"),
    ("CKL", "Center Knee Left", "Center Knee"),
    ("CKV", "Center Knee Vertical", "Center Knee"),
    ("CKR", "Center Knee Right", "Center Knee"),
    ("RKL", "Right Knee Left", "Right Knee"),
    ("RKR", "Right Knee Right", "Right Knee"),
]


class CopedantEditorDialog(QDialog):
    neck_updated = Signal()

    def __init__(
        self,
        neck: Neck,
        guitar: Optional[SteelGuitar] = None,
        current_neck_idx: int = 0,
        initial_tab: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.original_neck = neck
        self.neck = deepcopy(neck)
        self.guitar = guitar
        self.current_neck_idx = current_neck_idx

        self._migrate_legacy_levers()

        self.setWindowTitle(f"Copedant Setup & Tuning Editor - {self.neck.name}")
        self.resize(1260, 780)
        self.setMinimumWidth(1100)

        self.lever_checkboxes: Dict[str, QCheckBox] = {}
        self._init_ui()
        self._load_neck_data()

        if initial_tab == "splits":
            self.tabs.setCurrentWidget(self.tab_splits)
        elif initial_tab == "half_stops":
            self.tabs.setCurrentWidget(self.tab_half_stops)
        elif initial_tab == "info":
            self.tabs.setCurrentWidget(self.tab_info)
        elif initial_tab == "matrix":
            self.tabs.setCurrentWidget(self.tab_matrix)

    def _migrate_legacy_levers(self):
        if "VL" in self.neck.knee_levers and "LKV" not in self.neck.knee_levers:
            ch = self.neck.knee_levers.pop("VL")
            ch.id = "LKV"
            ch.label = "LKV"
            self.neck.knee_levers["LKV"] = ch

        retired = {"VL2", "LKR2", "RKL2", "VR", "VR2", "RKRHS"}
        for r_id in retired:
            self.neck.knee_levers.pop(r_id, None)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # 1. Top Bar: Active Copedant Selector & Persistence Actions
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>Active Copedant:</b>"))

        self.combo_copedant = QComboBox()
        self.combo_copedant.setMinimumWidth(260)
        if self.guitar:
            for idx, n in enumerate(self.guitar.necks):
                self.combo_copedant.addItem(f"{n.name} ({n.string_count} Str)", idx)
            self.combo_copedant.setCurrentIndex(self.current_neck_idx)
            self.combo_copedant.currentIndexChanged.connect(self._on_switch_copedant)
        else:
            self.combo_copedant.addItem(f"{self.neck.name} ({self.neck.string_count} Str)", 0)
        top_bar.addWidget(self.combo_copedant)

        self.btn_duplicate = QPushButton("📄 Duplicate as Copy")
        self.btn_duplicate.setStyleSheet("padding: 5px 12px; font-weight: bold;")
        self.btn_duplicate.clicked.connect(self._duplicate_copedant)
        top_bar.addWidget(self.btn_duplicate)

        self.btn_save_profile = QPushButton("💾 Save as Profile")
        self.btn_save_profile.setStyleSheet("padding: 5px 12px; font-weight: bold; background-color: #0d6efd; color: white;")
        self.btn_save_profile.clicked.connect(self._save_explicit_profile)
        top_bar.addWidget(self.btn_save_profile)

        top_bar.addStretch()
        root.addLayout(top_bar)

        # 2. Main Tabs
        self.tabs = QTabWidget()

        self.tab_matrix = QWidget()
        self._init_matrix_tab()
        self.tabs.addTab(self.tab_matrix, "1. Copedant Definition (Matrix)")

        self.tab_info = QWidget()
        self._init_info_tab()
        self.tabs.addTab(self.tab_info, "2. Information Bio")

        self.tab_splits = QWidget()
        self._init_splits_tab()
        self.tabs.addTab(self.tab_splits, "3. Mechanical Splits")

        self.tab_half_stops = QWidget()
        self._init_half_stops_tab()
        self.tabs.addTab(self.tab_half_stops, "4. Half-Stops")

        root.addWidget(self.tabs, stretch=1)

        # 3. Bottom Action Bar
        bottom_h = QHBoxLayout()
        lbl_notice = QLabel("<small style='color: #8b92a0;'>Changes save directly to disk and take effect across all visualizer tools upon applying.</small>")
        bottom_h.addWidget(lbl_notice)

        bottom_h.addStretch()

        self.btn_apply = QPushButton("Apply & Update Visualizer")
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 7px 22px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.btn_apply.clicked.connect(self._apply_and_close)
        bottom_h.addWidget(self.btn_apply)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("padding: 7px 16px;")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_h.addWidget(self.btn_cancel)

        root.addLayout(bottom_h)

    def _init_matrix_tab(self):
        vbox = QVBoxLayout(self.tab_matrix)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(6)

        box_levers = QGroupBox("Select Active Knee Levers (9 Standard Levers)")
        box_levers.setStyleSheet("QGroupBox { font-weight: bold; }")
        l_grid = QGridLayout(box_levers)
        l_grid.setContentsMargins(10, 8, 10, 8)
        l_grid.setSpacing(10)

        col_idx = 0
        row_idx = 0
        for lid, desc, knee_grp in STANDARDIZED_KNEE_LEVERS:
            cb = QCheckBox(f"{lid}")
            cb.setToolTip(f"{lid}: {desc} ({knee_grp})")
            cb.setStyleSheet("font-weight: bold;")
            cb.toggled.connect(self._on_lever_toggled)
            self.lever_checkboxes[lid] = cb
            l_grid.addWidget(cb, row_idx, col_idx)

            col_idx += 1
            if col_idx >= 5:
                col_idx = 0
                row_idx += 1

        vbox.addWidget(box_levers)

        tools_h = QHBoxLayout()
        tools_h.setSpacing(8)

        tools_h.addWidget(QLabel("<b>Strings:</b>"))
        btn_add_str = QPushButton("+ Add String")
        btn_add_str.setStyleSheet("color: #28a745; font-weight: bold; padding: 4px 10px;")
        btn_add_str.clicked.connect(self._add_string)
        tools_h.addWidget(btn_add_str)

        btn_rem_str = QPushButton("- Remove String")
        btn_rem_str.setStyleSheet("color: #dc3545; font-weight: bold; padding: 4px 10px;")
        btn_rem_str.clicked.connect(self._remove_string)
        tools_h.addWidget(btn_rem_str)

        tools_h.addSpacing(16)
        tools_h.addWidget(QLabel("<b>Pedals:</b>"))
        btn_add_ped = QPushButton("+ Add Pedal")
        btn_add_ped.setStyleSheet("color: #20c997; font-weight: bold; padding: 4px 10px;")
        btn_add_ped.clicked.connect(self._add_pedal)
        tools_h.addWidget(btn_add_ped)

        btn_rem_ped = QPushButton("- Remove Pedal")
        btn_rem_ped.setStyleSheet("color: #dc3545; font-weight: bold; padding: 4px 10px;")
        btn_rem_ped.clicked.connect(self._remove_pedal)
        tools_h.addWidget(btn_rem_ped)

        tools_h.addSpacing(16)
        self.cb_c6_offset = QCheckBox("⚡ Offset C6 Pedals +1 (Franklin P1)")
        self.cb_c6_offset.setToolTip("Shifts existing C6 pedals right by +1 and inserts a Franklin pedal at P1")
        self.cb_c6_offset.setStyleSheet("font-weight: bold; color: #ffc107;")
        self.cb_c6_offset.toggled.connect(self._toggle_c6_pedal_offset)
        tools_h.addWidget(self.cb_c6_offset)

        tools_h.addStretch()
        vbox.addLayout(tools_h)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #161920;
                gridline-color: #2b3140;
                border: 1px solid #3c4456;
                border-radius: 4px;
            }
            QHeaderView::section {
                font-weight: bold;
                font-size: 11px;
                border-top: 1px solid #3c4456;
                border-bottom: 2px solid #4a546a;
                border-right: 1px solid #3c4456;
                padding: 6px 2px;
            }
        """)
        vbox.addWidget(self.table, stretch=1)

    def _init_info_tab(self):
        layout = QGridLayout(self.tab_info)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        layout.addWidget(QLabel("<b>Copedant Name:</b>"), 0, 0)
        self.edit_name = QLineEdit()
        layout.addWidget(self.edit_name, 0, 1)

        layout.addWidget(QLabel("<b>Neck Type:</b>"), 1, 0)
        self.combo_neck_type = QComboBox()
        self.combo_neck_type.addItems(["E9", "C6", "Universal 12", "Custom"])
        self.combo_neck_type.currentIndexChanged.connect(self._on_neck_type_changed)
        layout.addWidget(self.combo_neck_type, 1, 1)

        layout.addWidget(QLabel("<b>Author:</b>"), 2, 0)
        self.edit_author = QLineEdit()
        layout.addWidget(self.edit_author, 2, 1)

        layout.addWidget(QLabel("<b>Description:</b>"), 3, 0)
        self.edit_desc = QTextEdit()
        self.edit_desc.setMaximumHeight(80)
        layout.addWidget(self.edit_desc, 3, 1)

        layout.addWidget(QLabel("<b>Author Bio:</b>"), 4, 0)
        self.edit_bio = QTextEdit()
        self.edit_bio.setMaximumHeight(80)
        layout.addWidget(self.edit_bio, 4, 1)

        layout.addWidget(QLabel("<b>Social / Notes:</b>"), 5, 0)
        self.edit_social = QLineEdit()
        layout.addWidget(self.edit_social, 5, 1)

        layout.setRowStretch(6, 1)

    # -------------------------------------------------------------------------
    # TAB 3: Mechanical Splits (Dedicated Control 1 & Control 2 Selectors)
    # -------------------------------------------------------------------------
    def _init_splits_tab(self):
        vbox = QVBoxLayout(self.tab_splits)
        vbox.setContentsMargins(12, 10, 12, 10)
        vbox.setSpacing(8)

        lbl = QLabel(
            "<b>Mechanical Changer Splits Configuration:</b><br>"
            "<small style='color: #8b92a0;'>"
            "Tune mechanical conflict resolutions when two controllers are pressed simultaneously on the same string "
            "(e.g., Control 1: P3 & Control 2: RKR)."
            "</small>"
        )
        vbox.addWidget(lbl)

        self.splits_table = QTableWidget()
        self.splits_table.setColumnCount(6)
        self.splits_table.setHorizontalHeaderLabels([
            "String", "Control 1 (e.g. P3)", "Control 2 (e.g. RKR)", "Resolved Net Delta", "Active", "Description"
        ])
        self.splits_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.splits_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.splits_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.splits_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.splits_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.splits_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.splits_table.setShowGrid(True)
        vbox.addWidget(self.splits_table, stretch=1)

        btn_h = QHBoxLayout()

        btn_add = QPushButton("+ Add Split")
        btn_add.setStyleSheet("font-weight: bold; padding: 5px 14px; color: #20c997;")
        btn_add.clicked.connect(self._add_split_rule)
        btn_h.addWidget(btn_add)

        btn_auto = QPushButton("⚡ Auto-Detect Splits")
        btn_auto.setStyleSheet("font-weight: bold; padding: 5px 14px;")
        btn_auto.clicked.connect(self._auto_detect_splits)
        btn_h.addWidget(btn_auto)

        btn_rem = QPushButton("Remove Selected")
        btn_rem.setStyleSheet("color: #dc3545; font-weight: bold; padding: 5px 14px;")
        btn_rem.clicked.connect(self._remove_split_rule)
        btn_h.addWidget(btn_rem)

        btn_h.addStretch()
        vbox.addLayout(btn_h)

    def _refresh_splits_tab(self):
        self.splits_table.setRowCount(0)
        for sp in getattr(self.neck, "splits", []):
            if len(sp.controllers) >= 2:
                self._insert_split_row(sp)

    def _insert_split_row(self, sp: SplitRule):
        row = self.splits_table.rowCount()
        self.splits_table.insertRow(row)

        # 0. String Selector Dropdown
        combo_str = QComboBox()
        open_notes = {s.string_number: s.note_name for s in getattr(self.neck, "open_tuning", [])}
        str_count = self.neck.string_count if self.neck else 10
        sel_idx = 0
        for s_idx in range(1, str_count + 1):
            note = open_notes.get(s_idx, "")
            label = f"String {s_idx} ({note})" if note else f"String {s_idx}"
            combo_str.addItem(label, s_idx)
            if s_idx == sp.string_number:
                sel_idx = s_idx - 1
        combo_str.setCurrentIndex(sel_idx)
        self.splits_table.setCellWidget(row, 0, combo_str)

        available_ctrls = self._get_single_controllers()

        # 1. Control 1 Dropdown
        combo_c1 = QComboBox()
        combo_c1.setStyleSheet("font-weight: bold;")
        for disp, cid in available_ctrls:
            combo_c1.addItem(disp, cid)

        c1_target = sp.controllers[0] if len(sp.controllers) > 0 else "P1"
        idx1 = 0
        for i in range(combo_c1.count()):
            if combo_c1.itemData(i) == c1_target:
                idx1 = i
                break
        combo_c1.setCurrentIndex(idx1)
        self.splits_table.setCellWidget(row, 1, combo_c1)

        # 2. Control 2 Dropdown
        combo_c2 = QComboBox()
        combo_c2.setStyleSheet("font-weight: bold;")
        for disp, cid in available_ctrls:
            combo_c2.addItem(disp, cid)

        c2_target = sp.controllers[1] if len(sp.controllers) > 1 else "LKR"
        idx2 = 0
        for i in range(combo_c2.count()):
            if combo_c2.itemData(i) == c2_target:
                idx2 = i
                break
        combo_c2.setCurrentIndex(idx2)
        self.splits_table.setCellWidget(row, 2, combo_c2)

        # 3. Resolved Net Delta
        spin = QSpinBox()
        spin.setRange(-6, 6)
        spin.setValue(int(sp.semitone_delta))
        self.splits_table.setCellWidget(row, 3, spin)

        # 4. Active Checkbox Container
        check_box = QCheckBox()
        check_box.setChecked(sp.is_active)
        check_widget = QWidget()
        layout_c = QHBoxLayout(check_widget)
        layout_c.setContentsMargins(0, 0, 0, 0)
        layout_c.setAlignment(Qt.AlignCenter)
        layout_c.addWidget(check_box)
        self.splits_table.setCellWidget(row, 4, check_widget)

        # 5. Description LineEdit
        edit_desc = QLineEdit(sp.description or "")
        self.splits_table.setCellWidget(row, 5, edit_desc)

    def _add_split_rule(self):
        sp = SplitRule(
            string_number=5,
            controllers=["P1", "LKR"],
            semitone_delta=0,
            is_active=True,
            description="P1 raise + LKR lower conflict",
        )
        self._insert_split_row(sp)

    def _remove_split_rule(self):
        row = self.splits_table.currentRow()
        if row >= 0:
            self.splits_table.removeRow(row)

    def _auto_detect_splits(self):
        detected = detect_potential_splits(self.neck)
        for s in detected:
            self._insert_split_row(s)
        QMessageBox.information(self, "Splits Detected", f"Auto-detected and populated {len(detected)} changer split points.")

    def _save_splits_from_ui(self):
        updated_splits: List[SplitRule] = []
        for r in range(self.splits_table.rowCount()):
            cb_str = self.splits_table.cellWidget(r, 0)
            cb_c1 = self.splits_table.cellWidget(r, 1)
            cb_c2 = self.splits_table.cellWidget(r, 2)
            spin = self.splits_table.cellWidget(r, 3)
            c_box_widget = self.splits_table.cellWidget(r, 4)
            edit_desc = self.splits_table.cellWidget(r, 5)

            if not isinstance(cb_str, QComboBox) or not isinstance(cb_c1, QComboBox) or not isinstance(cb_c2, QComboBox):
                continue

            str_num = cb_str.currentData() or 1
            c1 = cb_c1.currentData() or cb_c1.currentText().split("(")[0].strip()
            c2 = cb_c2.currentData() or cb_c2.currentText().split("(")[0].strip()
            delta = spin.value() if isinstance(spin, QSpinBox) else 0
            is_act = c_box_widget.findChild(QCheckBox).isChecked() if c_box_widget else True
            desc = edit_desc.text().strip() if isinstance(edit_desc, QLineEdit) else ""

            updated_splits.append(SplitRule(
                string_number=int(str_num),
                controllers=[str(c1), str(c2)],
                semitone_delta=int(delta),
                is_active=is_act,
                description=desc,
            ))
        self.neck.splits = updated_splits

    # -------------------------------------------------------------------------
    # TAB 4: Half-Stops (Single-Controller Intermediate Feel-Stops)
    # -------------------------------------------------------------------------
    def _init_half_stops_tab(self):
        vbox = QVBoxLayout(self.tab_half_stops)
        vbox.setContentsMargins(12, 10, 12, 10)
        vbox.setSpacing(8)

        lbl = QLabel(
            "<b>Mechanical Half-Stop Configuration:</b><br>"
            "<small style='color: #8b92a0;'>Configure intermediate feel-stops on individual knee levers or pedals. "
            "When enabled, a single click engages the half-stop (amber glow), and a double click engages the full stop.</small>"
        )
        vbox.addWidget(lbl)

        self.half_stops_table = QTableWidget()
        self.half_stops_table.setColumnCount(5)
        self.half_stops_table.setHorizontalHeaderLabels([
            "Lever / Pedal", "Affected String", "Half-Stop Delta", "Enabled", "Description"
        ])
        self.half_stops_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.half_stops_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.half_stops_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.half_stops_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.half_stops_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.half_stops_table.setShowGrid(True)
        vbox.addWidget(self.half_stops_table, stretch=1)

        btn_h = QHBoxLayout()

        btn_add = QPushButton("+ Add Half-Stop")
        btn_add.setStyleSheet("font-weight: bold; padding: 5px 14px; color: #ffc107;")
        btn_add.clicked.connect(self._add_half_stop_rule)
        btn_h.addWidget(btn_add)

        btn_auto = QPushButton("⚡ Auto-Detect 2-Semitone Pulls")
        btn_auto.setStyleSheet("font-weight: bold; padding: 5px 14px;")
        btn_auto.clicked.connect(self._auto_detect_half_stops)
        btn_h.addWidget(btn_auto)

        btn_rem = QPushButton("Remove Selected")
        btn_rem.setStyleSheet("color: #dc3545; font-weight: bold; padding: 5px 14px;")
        btn_rem.clicked.connect(self._remove_half_stop_rule)
        btn_h.addWidget(btn_rem)

        btn_h.addStretch()
        vbox.addLayout(btn_h)

    def _get_single_controllers(self) -> List[Tuple[str, str]]:
        items: List[Tuple[str, str]] = []
        for pid in sorted(self.neck.pedals.keys(), key=lambda k: int(k[1:]) if k[1:].isdigit() else 99):
            p = self.neck.pedals[pid]
            lbl = f"{pid} ({p.label})" if p.label else pid
            items.append((lbl, pid))

        lever_order = ["LKL", "LKV", "LKR", "RKL", "RKR"]
        for lid in sorted(self.neck.knee_levers.keys(), key=lambda k: lever_order.index(k) if k in lever_order else 99):
            l = self.neck.knee_levers[lid]
            lbl = f"{lid} ({l.label})" if l.label else lid
            items.append((lbl, lid))
        return items

    def _refresh_half_stops_tab(self):
        self.half_stops_table.setRowCount(0)
        for rule in getattr(self.neck, "half_stops", []):
            self._insert_half_stop_row(rule)

    def _insert_half_stop_row(self, rule: HalfStopRule):
        row = self.half_stops_table.rowCount()
        self.half_stops_table.insertRow(row)

        combo_ctrl = QComboBox()
        combo_ctrl.setStyleSheet("font-weight: bold;")
        for disp, cid in self._get_single_controllers():
            combo_ctrl.addItem(disp, cid)

        match_idx = 0
        for i in range(combo_ctrl.count()):
            if combo_ctrl.itemData(i) == rule.controller_id:
                match_idx = i
                break
        combo_ctrl.setCurrentIndex(match_idx)
        self.half_stops_table.setCellWidget(row, 0, combo_ctrl)

        combo_str = QComboBox()
        open_notes = {s.string_number: s.note_name for s in getattr(self.neck, "open_tuning", [])}
        str_count = self.neck.string_count if self.neck else 10
        sel_idx = 0
        for s_idx in range(1, str_count + 1):
            note = open_notes.get(s_idx, "")
            label = f"String {s_idx} ({note})" if note else f"String {s_idx}"
            combo_str.addItem(label, s_idx)
            if s_idx == rule.string_number:
                sel_idx = s_idx - 1
        combo_str.setCurrentIndex(sel_idx)
        self.half_stops_table.setCellWidget(row, 1, combo_str)

        spin = QSpinBox()
        spin.setRange(-4, 4)
        spin.setValue(int(rule.semitone_delta))
        self.half_stops_table.setCellWidget(row, 2, spin)

        check_box = QCheckBox()
        check_box.setChecked(rule.is_active)
        check_widget = QWidget()
        layout_c = QHBoxLayout(check_widget)
        layout_c.setContentsMargins(0, 0, 0, 0)
        layout_c.setAlignment(Qt.AlignCenter)
        layout_c.addWidget(check_box)
        self.half_stops_table.setCellWidget(row, 3, check_widget)

        edit_desc = QLineEdit(rule.description or "")
        self.half_stops_table.setCellWidget(row, 4, edit_desc)

    def _add_half_stop_rule(self):
        rule = HalfStopRule(
            controller_id="LKL",
            string_number=4,
            semitone_delta=1,
            is_active=True,
            description="Intermediate feel stop (E to F)",
        )
        self._insert_half_stop_row(rule)

    def _remove_half_stop_rule(self):
        row = self.half_stops_table.currentRow()
        if row >= 0:
            self.half_stops_table.removeRow(row)

    def _auto_detect_half_stops(self):
        detected = detect_potential_half_stops(self.neck)
        for r in detected:
            self._insert_half_stop_row(r)
        QMessageBox.information(self, "Detection Complete", f"Identified and populated {len(detected)} potential half-stop controllers.")

    def _save_half_stops_from_ui(self):
        rules: List[HalfStopRule] = []
        for r in range(self.half_stops_table.rowCount()):
            cb_ctrl = self.half_stops_table.cellWidget(r, 0)
            cb_str = self.half_stops_table.cellWidget(r, 1)
            spin = self.half_stops_table.cellWidget(r, 2)
            c_box_widget = self.half_stops_table.cellWidget(r, 3)
            edit = self.half_stops_table.cellWidget(r, 4)

            if not isinstance(cb_ctrl, QComboBox) or not isinstance(cb_str, QComboBox):
                continue

            cid = cb_ctrl.currentData() or cb_ctrl.currentText().split("(")[0].strip()
            str_num = cb_str.currentData() or 1
            delta = spin.value() if isinstance(spin, QSpinBox) else 1
            is_act = c_box_widget.findChild(QCheckBox).isChecked() if c_box_widget else True
            desc = edit.text().strip() if isinstance(edit, QLineEdit) else ""

            rules.append(HalfStopRule(
                controller_id=str(cid),
                string_number=int(str_num),
                semitone_delta=int(delta),
                is_active=is_act,
                description=desc,
            ))
        self.neck.half_stops = rules

    # -------------------------------------------------------------------------
    # Core Data Loading and Matrix Building
    # -------------------------------------------------------------------------
    def _load_neck_data(self):
        self.edit_name.setText(self.neck.name)
        self.combo_neck_type.setCurrentText(self.neck.neck_type.value)
        self.edit_author.setText(self.neck.author)
        self.edit_desc.setPlainText(self.neck.description)
        self.edit_bio.setPlainText(self.neck.author_bio)
        self.edit_social.setText(self.neck.social_media)

        is_c6 = (self.neck.neck_type == NeckType.C6 or "C6" in self.neck.name)
        self.cb_c6_offset.setVisible(is_c6)
        has_franklin_p1 = "P1" in self.neck.pedals and "Franklin" in self.neck.pedals["P1"].label
        self.cb_c6_offset.blockSignals(True)
        self.cb_c6_offset.setChecked(has_franklin_p1)
        self.cb_c6_offset.blockSignals(False)

        for lid, cb in self.lever_checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(lid in self.neck.knee_levers)
            cb.blockSignals(False)

        self._rebuild_matrix_table()
        self._refresh_splits_tab()
        self._refresh_half_stops_tab()

    def _on_neck_type_changed(self):
        n_type = self.combo_neck_type.currentText()
        is_c6 = (n_type == "C6")
        self.cb_c6_offset.setVisible(is_c6)

    def _toggle_c6_pedal_offset(self, checked: bool):
        pedal_keys = sorted(list(self.neck.pedals.keys()), key=lambda k: int(k[1:]) if k[1:].isdigit() else 99)
        if checked:
            new_pedals: Dict[str, CopedantChange] = {}
            new_pedals["P1"] = CopedantChange(id="P1", label="P1 (Franklin)", changes={})
            for p_id in pedal_keys:
                if p_id[1:].isdigit():
                    old_num = int(p_id[1:])
                    new_id = f"P{old_num + 1}"
                    old_ch = self.neck.pedals[p_id]
                    new_pedals[new_id] = CopedantChange(id=new_id, label=new_id, changes=dict(old_ch.changes))
                else:
                    new_pedals[p_id] = self.neck.pedals[p_id]
            self.neck.pedals = new_pedals
        else:
            new_pedals = {}
            for p_id in pedal_keys:
                if p_id == "P1" and "Franklin" in self.neck.pedals["P1"].label:
                    continue
                if p_id[1:].isdigit():
                    num = int(p_id[1:])
                    new_id = f"P{max(1, num - 1)}"
                    old_ch = self.neck.pedals[p_id]
                    new_pedals[new_id] = CopedantChange(id=new_id, label=new_id, changes=dict(old_ch.changes))
                else:
                    new_pedals[p_id] = self.neck.pedals[p_id]
            self.neck.pedals = new_pedals

        self._rebuild_matrix_table()

    def _on_lever_toggled(self):
        for lid, cb in self.lever_checkboxes.items():
            if cb.isChecked() and lid not in self.neck.knee_levers:
                self.neck.knee_levers[lid] = CopedantChange(id=lid, label=lid, changes={})
            elif not cb.isChecked() and lid in self.neck.knee_levers:
                del self.neck.knee_levers[lid]
        self._rebuild_matrix_table()

    def _rebuild_matrix_table(self):
        self.table.blockSignals(True)
        self.table.clear()

        pedal_keys = sorted(list(self.neck.pedals.keys()), key=lambda k: int(k[1:]) if k[1:].isdigit() else 99)
        lever_order = [lid for lid, _, _ in STANDARDIZED_KNEE_LEVERS]
        lever_keys = sorted(
            list(self.neck.knee_levers.keys()),
            key=lambda k: lever_order.index(k) if k in lever_order else 99,
        )

        headers = ["String", "Open Tuning"]
        for p_id in pedal_keys:
            p_obj = self.neck.pedals[p_id]
            headers.append(p_obj.label if p_obj.label != p_id else p_id)
        for l_id in lever_keys:
            headers.append(l_id)

        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(self.neck.string_count)

        for c in range(len(headers)):
            item = self.table.horizontalHeaderItem(c)
            if not item:
                continue
            if c == 0:
                item.setBackground(QColor("#1e222a"))
                item.setForeground(QColor("#20c997"))
            elif c == 1:
                item.setBackground(QColor("#1e222a"))
                item.setForeground(QColor("#58a6ff"))
            elif c < 2 + len(pedal_keys):
                item.setBackground(QColor("#1c2b3e"))
                item.setForeground(QColor("#79b8ff"))
            else:
                item.setBackground(QColor("#152e24"))
                item.setForeground(QColor("#48d597"))

        for s_idx, sp in enumerate(self.neck.open_tuning):
            s_num = sp.string_number

            str_lbl = QLabel(f"S{s_num}")
            str_lbl.setAlignment(Qt.AlignCenter)
            str_lbl.setStyleSheet("background-color: #212631; color: #20c997; font-weight: bold; border-radius: 3px; font-size: 11px;")
            self.table.setCellWidget(s_idx, 0, str_lbl)

            open_widget = self._create_open_note_cell(s_idx, sp)
            self.table.setCellWidget(s_idx, 1, open_widget)

            col_offset = 2
            for p_idx, p_id in enumerate(pedal_keys):
                ctrl = self.neck.pedals[p_id]
                delta = ctrl.changes.get(s_num, 0)
                is_even_lane = (p_idx % 2 == 0)
                cell = self._create_changer_cell(ctrl, s_num, sp.midi_note, delta, is_even_lane, is_pedal=True)
                self.table.setCellWidget(s_idx, col_offset + p_idx, cell)

            col_offset += len(pedal_keys)
            for l_idx, l_id in enumerate(lever_keys):
                ctrl = self.neck.knee_levers[l_id]
                delta = ctrl.changes.get(s_num, 0)
                is_even_lane = (l_idx % 2 == 0)
                cell = self._create_changer_cell(ctrl, s_num, sp.midi_note, delta, is_even_lane, is_pedal=False)
                self.table.setCellWidget(s_idx, col_offset + l_idx, cell)

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.blockSignals(False)

    def _create_open_note_cell(self, s_idx: int, sp: StringPitch) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet("background-color: #1a1e27; border-right: 1px solid #3c4456;")
        h = QHBoxLayout(widget)
        h.setContentsMargins(6, 2, 6, 2)
        h.setSpacing(4)
        h.setAlignment(Qt.AlignCenter)

        lbl = QLabel(sp.note_name)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #58a6ff; min-width: 38px; max-width: 38px;")
        h.addWidget(lbl)

        btn_minus = QPushButton("−")
        btn_minus.setFixedSize(22, 22)
        btn_minus.setStyleSheet("""
            QPushButton {
                background-color: #2b3140;
                color: #ff7b72;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #4a546a;
                border-radius: 3px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #dc3545;
                color: #ffffff;
                border-color: #dc3545;
            }
        """)
        btn_minus.clicked.connect(lambda: self._shift_open_pitch(s_idx, -1))
        h.addWidget(btn_minus)

        btn_plus = QPushButton("+")
        btn_plus.setFixedSize(22, 22)
        btn_plus.setStyleSheet("""
            QPushButton {
                background-color: #2b3140;
                color: #56d364;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #4a546a;
                border-radius: 3px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #28a745;
                color: #ffffff;
                border-color: #28a745;
            }
        """)
        btn_plus.clicked.connect(lambda: self._shift_open_pitch(s_idx, 1))
        h.addWidget(btn_plus)

        return widget

    def _shift_open_pitch(self, s_idx: int, delta: int):
        sp = self.neck.open_tuning[s_idx]
        new_midi = max(24, min(96, sp.midi_note + delta))
        sp.midi_note = new_midi
        sp.note_name = midi_to_note_name(new_midi)
        self._rebuild_matrix_table()

    def _create_changer_cell(
        self,
        ctrl: CopedantChange,
        s_num: int,
        open_midi: int,
        delta: int,
        is_even_lane: bool,
        is_pedal: bool,
    ) -> QWidget:
        widget = QWidget()
        if is_pedal:
            bg_color = "#18202d" if is_even_lane else "#141a24"
        else:
            bg_color = "#15241e" if is_even_lane else "#121d18"
        widget.setStyleSheet(f"background-color: {bg_color}; border-right: 1px solid #2e3545;")

        h = QHBoxLayout(widget)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(4)
        h.setAlignment(Qt.AlignCenter)

        btn_minus = QPushButton("−")
        btn_minus.setFixedSize(22, 22)
        btn_minus.setStyleSheet("""
            QPushButton {
                background-color: #2c3242;
                color: #ff7b72;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #485268;
                border-radius: 3px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #dc3545;
                color: #ffffff;
                border-color: #dc3545;
            }
            QPushButton:pressed {
                background-color: #a71d2a;
            }
        """)
        btn_minus.clicked.connect(lambda: self._adjust_changer_delta(ctrl, s_num, -1))
        h.addWidget(btn_minus)

        lbl_val = QLabel(f"{delta:+d}" if delta != 0 else "0")
        lbl_val.setAlignment(Qt.AlignCenter)
        if delta > 0:
            val_style = "color: #3fb950; font-weight: bold; font-size: 11px;"
        elif delta < 0:
            val_style = "color: #ff7b72; font-weight: bold; font-size: 11px;"
        else:
            val_style = "color: #6e7681; font-weight: normal; font-size: 11px;"
        lbl_val.setStyleSheet(f"{val_style} min-width: 24px; max-width: 24px;")
        h.addWidget(lbl_val)

        btn_plus = QPushButton("+")
        btn_plus.setFixedSize(22, 22)
        btn_plus.setStyleSheet("""
            QPushButton {
                background-color: #2c3242;
                color: #56d364;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #485268;
                border-radius: 3px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #28a745;
                color: #ffffff;
                border-color: #28a745;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
        """)
        btn_plus.clicked.connect(lambda: self._adjust_changer_delta(ctrl, s_num, 1))
        h.addWidget(btn_plus)

        lbl_badge = QLabel()
        lbl_badge.setAlignment(Qt.AlignCenter)
        if delta != 0:
            sounding_note = midi_to_note_name(open_midi + delta)
            lbl_badge.setText(f"({sounding_note})")
            lbl_badge.setStyleSheet("""
                background-color: #d39e00;
                color: #12151c;
                font-weight: bold;
                font-size: 10px;
                border-radius: 3px;
                min-width: 42px;
                max-width: 42px;
            """)
        else:
            lbl_badge.setText("")
            lbl_badge.setStyleSheet("background: transparent; min-width: 42px; max-width: 42px;")
        h.addWidget(lbl_badge)

        return widget

    def _adjust_changer_delta(self, ctrl: CopedantChange, s_num: int, step: int):
        curr = ctrl.changes.get(s_num, 0)
        new_val = curr + step
        if new_val == 0:
            ctrl.changes.pop(s_num, None)
        else:
            ctrl.changes[s_num] = new_val
        self._rebuild_matrix_table()

    def _add_string(self):
        new_num = self.neck.string_count + 1
        low_midi = self.neck.open_tuning[-1].midi_note - 2 if self.neck.open_tuning else 45
        self.neck.open_tuning.append(
            StringPitch(string_number=new_num, midi_note=low_midi, note_name=midi_to_note_name(low_midi))
        )
        self.neck.string_count = len(self.neck.open_tuning)
        self._rebuild_matrix_table()

    def _remove_string(self):
        if self.neck.string_count > 6:
            self.neck.open_tuning.pop()
            self.neck.string_count = len(self.neck.open_tuning)
            self._rebuild_matrix_table()

    def _add_pedal(self):
        is_e9 = (self.neck.neck_type == NeckType.E9 or "E9" in self.neck.name)
        has_p1_franklin = ("P1" in self.neck.pedals and "Franklin" in self.neck.pedals["P1"].label)
        pedal_count = len(self.neck.pedals)

        if (is_e9 or pedal_count == 3) and not has_p1_franklin:
            msg = QMessageBox(self)
            msg.setWindowTitle("Add Pedal - Position & Type")
            msg.setText("<h3>Select 4th Pedal Configuration</h3><p>How would you like to configure this pedal?</p>")
            msg.setInformativeText(
                "<b>Option 1: P1 (Franklin Pedal Shift)</b><br>"
                "Inserts P1 to the left of Pedal A, shifting existing Pedals A, B, C to the right (P1➔P2, P2➔P3, P3➔P4).<br><br>"
                "<b>Option 2: P4 (Standard 4th Pedal)</b><br>Appends P4 to the right of Pedal C."
            )
            btn_franklin = msg.addButton("⚡ Add as P1 (Franklin Shift)", QMessageBox.ActionRole)
            btn_p4 = msg.addButton("Add as P4 (Standard Right)", QMessageBox.ActionRole)
            btn_cancel = msg.addButton("Cancel", QMessageBox.RejectRole)

            msg.exec()
            clicked = msg.clickedButton()

            if clicked == btn_cancel:
                return
            elif clicked == btn_franklin:
                self._insert_franklin_p1()
                return
            elif clicked == btn_p4:
                self._append_standard_pedal("P4")
                return

        pedal_nums = [int(k[1:]) for k in self.neck.pedals.keys() if k[1:].isdigit()]
        next_num = max(pedal_nums, default=0) + 1
        self._append_standard_pedal(f"P{next_num}")

    def _insert_franklin_p1(self):
        pedal_keys = sorted(list(self.neck.pedals.keys()), key=lambda k: int(k[1:]) if k[1:].isdigit() else 99)
        new_pedals: Dict[str, CopedantChange] = {}

        is_e9 = (self.neck.neck_type == NeckType.E9 or "E9" in self.neck.name)
        franklin_changes = {5: -1, 6: -2} if is_e9 else {}
        new_pedals["P1"] = CopedantChange(id="P1", label="P1 (Franklin)", changes=franklin_changes)

        for p_id in pedal_keys:
            if p_id[1:].isdigit():
                old_num = int(p_id[1:])
                new_id = f"P{old_num + 1}"
                old_ch = self.neck.pedals[p_id]
                new_label = new_id
                if "A" in old_ch.label or p_id == "P1":
                    new_label = "Pedal 2 (A)"
                elif "B" in old_ch.label or p_id == "P2":
                    new_label = "Pedal 3 (B)"
                elif "C" in old_ch.label or p_id == "P3":
                    new_label = "Pedal 4 (C)"
                new_pedals[new_id] = CopedantChange(id=new_id, label=new_label, changes=dict(old_ch.changes))
            else:
                new_pedals[p_id] = self.neck.pedals[p_id]

        self.neck.pedals = new_pedals
        self._rebuild_matrix_table()

    def _append_standard_pedal(self, p_id: str):
        label = p_id
        if p_id == "P4":
            label = "Pedal 4"
        self.neck.pedals[p_id] = CopedantChange(id=p_id, label=label, changes={})
        self._rebuild_matrix_table()

    def _remove_pedal(self):
        pedal_keys = sorted(list(self.neck.pedals.keys()), key=lambda k: int(k[1:]) if k[1:].isdigit() else 99)
        if not pedal_keys:
            return

        has_p1_franklin = ("P1" in self.neck.pedals and "Franklin" in self.neck.pedals["P1"].label)
        if has_p1_franklin:
            reply = QMessageBox.question(
                self,
                "Remove Pedal",
                "Do you want to remove the Franklin P1 pedal and shift Pedals P2-P4 back to P1-P3?\n(Click No to remove the last pedal instead)",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Yes:
                self._toggle_c6_pedal_offset(checked=False)
                return

        del self.neck.pedals[pedal_keys[-1]]
        self._rebuild_matrix_table()

    def _duplicate_copedant(self):
        if not self.guitar:
            return
        self._save_splits_from_ui()
        self._save_half_stops_from_ui()

        copy_neck = deepcopy(self.neck)
        base_name = self.neck.name.replace(" (Copy)", "")
        existing_names = [n.name for n in self.guitar.necks]
        counter = 1
        new_name = f"{base_name} (Copy)"
        while new_name in existing_names:
            counter += 1
            new_name = f"{base_name} (Copy {counter})"

        copy_neck.name = new_name
        self.guitar.necks.append(copy_neck)
        self.current_neck_idx = len(self.guitar.necks) - 1
        self.neck = copy_neck

        ProfileManager.save_user_profile(copy_neck.name, copy_neck)
        self._persist_active_guitar()

        self.combo_copedant.blockSignals(True)
        self.combo_copedant.addItem(f"{copy_neck.name} ({copy_neck.string_count} Str)", self.current_neck_idx)
        self.combo_copedant.setCurrentIndex(self.current_neck_idx)
        self.combo_copedant.blockSignals(False)
        self._load_neck_data()

        QMessageBox.information(self, "Copedant Duplicated", f"Duplicated and saved '{new_name}' to user profiles.")

    def _save_explicit_profile(self):
        name, ok = QInputDialog.getText(
            self,
            "Save Copedant Profile",
            "Enter profile name:",
            text=self.edit_name.text().strip() or self.neck.name,
        )
        if ok and name.strip():
            self._save_splits_from_ui()
            self._save_half_stops_from_ui()

            profile_name = name.strip()
            self.neck.name = profile_name
            self.edit_name.setText(profile_name)
            ProfileManager.save_user_profile(profile_name, self.neck)
            if self.guitar and 0 <= self.current_neck_idx < len(self.guitar.necks):
                self.guitar.necks[self.current_neck_idx] = self.neck
            self._persist_active_guitar()
            QMessageBox.information(self, "Profile Saved", f"Successfully saved '{profile_name}' to disk.")

    def _on_switch_copedant(self, idx: int):
        if self.guitar and 0 <= idx < len(self.guitar.necks):
            self._save_splits_from_ui()
            self._save_half_stops_from_ui()
            self.current_neck_idx = idx
            self.neck = deepcopy(self.guitar.necks[idx])
            self._migrate_legacy_levers()
            self._load_neck_data()

    def _persist_active_guitar(self):
        if self.guitar:
            try:
                storage_dir = ProfileManager.ensure_storage_dir() or getattr(
                    ProfileManager, "STORAGE_DIR", Path.home() / ".psg_visualizer" / "profiles"
                )
                active_path = storage_dir / "active_guitar_setup.json"
                self.guitar.save_to_file(str(active_path))
            except Exception:
                pass

    def _apply_and_close(self):
        self._save_splits_from_ui()
        self._save_half_stops_from_ui()

        self.neck.name = self.edit_name.text().strip() or self.neck.name
        self.neck.neck_type = NeckType(self.combo_neck_type.currentText())
        self.neck.author = self.edit_author.text()
        self.neck.description = self.edit_desc.toPlainText()
        self.neck.author_bio = self.edit_bio.toPlainText()
        self.neck.social_media = self.edit_social.text()

        if self.guitar and 0 <= self.current_neck_idx < len(self.guitar.necks):
            self.guitar.necks[self.current_neck_idx] = self.neck
        else:
            self.original_neck.__dict__.update(self.neck.__dict__)

        ProfileManager.save_user_profile(self.neck.name, self.neck)
        self._persist_active_guitar()

        self.neck_updated.emit()
        self.accept()
        self.accept()