"""Copedant Setup & Tuning Editor Dialog with distinct column lanes,
fixed-geometry steppers, Franklin P1 vs P4 insertion, persistent disk saving,
interactive Mechanical Splits (with Control 1 & Control 2 dropdowns), and dedicated Half-Stops configuration.
"""

import logging
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
    CHANGER_LIMIT_RANGE,
    CHANGER_PRESETS,
    DEFAULT_CHANGER,
    changer_label,
    changer_usage,
    changer_violations,
    CopedantChange,
    HalfStopRule,
    Neck,
    NeckType,
    SplitRule,
    SteelGuitar,
    StringPitch,
    detect_potential_half_stops,
    detect_potential_splits,
    migrate_half_stop_tokens,
    migrate_legacy_ids,
    shift_pedal_ids,
)
from core.profile_manager import ProfileManager, unique_neck_name
from core.theory import NOTE_NAMES_SHARP, midi_to_note_name, note_to_midi

log = logging.getLogger(__name__)

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
        # Unapplied working copies per neck index (edits survive switching necks in the combo).
        self._working: Dict[int, Neck] = {}
        # True when guitar.necks was changed structurally (Duplicate / Save as Profile),
        # which happens immediately, even if the dialog is later cancelled.
        self.guitar_changed: bool = False

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
        # Core migrations rewrite split/half-stop references together with the controllers (D-07).
        migrate_legacy_ids(self.neck)
        migrate_half_stop_tokens(self.neck)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # 1. Top Bar: Active Copedant Selector & Persistence Actions
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>Tuning:</b>"))

        self.combo_copedant = QComboBox()
        self.combo_copedant.setMinimumWidth(260)
        if self.guitar:
            self._rebuild_copedant_combo()
            self.combo_copedant.currentIndexChanged.connect(self._on_copedant_combo_changed)
        else:
            self.combo_copedant.addItem(f"{self.neck.name} ({self.neck.string_count} Str)", 0)
        top_bar.addWidget(self.combo_copedant)

        self.btn_duplicate = QPushButton("📄 Duplicate Tuning")
        self.btn_duplicate.setToolTip("Add a copy of this tuning to the open profile")
        self.btn_duplicate.setStyleSheet("padding: 5px 12px; font-weight: bold;")
        self.btn_duplicate.clicked.connect(self._duplicate_copedant)
        top_bar.addWidget(self.btn_duplicate)

        self.btn_save_profile = QPushButton("📤 Copy to Profile...")
        self.btn_save_profile.setToolTip("Add a copy of this tuning (with your edits) to another user profile")
        self.btn_save_profile.setStyleSheet("padding: 5px 12px; font-weight: bold; background-color: #0d6efd; color: white;")
        self.btn_save_profile.clicked.connect(self._copy_to_profile)
        top_bar.addWidget(self.btn_save_profile)

        self.btn_compare = QPushButton("🔍 Compare to Saved")
        self.btn_compare.setStyleSheet("padding: 5px 12px; font-weight: bold;")
        self.btn_compare.setToolTip("Show which chords your unsaved edits add or remove (E-25)")
        self.btn_compare.clicked.connect(self._compare_to_saved)
        top_bar.addWidget(self.btn_compare)

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

        # Changer configuration: most raises / lowers the changer holds per string.
        box_changer = QGroupBox("Changer Configuration")
        box_changer.setStyleSheet("QGroupBox { font-weight: bold; }")
        ch = QHBoxLayout(box_changer)
        ch.setContentsMargins(10, 8, 10, 8)
        ch.addWidget(QLabel("Preset:"))
        self.combo_changer = QComboBox()
        for raises, lowers in CHANGER_PRESETS:
            suffix = " (default)" if (raises, lowers) == DEFAULT_CHANGER else ""
            self.combo_changer.addItem(changer_label(raises, lowers) + suffix, (raises, lowers))
        self.combo_changer.addItem("Custom", None)
        self.combo_changer.currentIndexChanged.connect(self._on_changer_preset_changed)
        ch.addWidget(self.combo_changer)
        ch.addSpacing(10)
        ch.addWidget(QLabel("Raises per string:"))
        self.spin_raises = QSpinBox()
        self.spin_raises.setRange(*CHANGER_LIMIT_RANGE)
        self.spin_raises.valueChanged.connect(self._on_changer_limits_changed)
        ch.addWidget(self.spin_raises)
        ch.addWidget(QLabel("Lowers per string:"))
        self.spin_lowers = QSpinBox()
        self.spin_lowers.setRange(*CHANGER_LIMIT_RANGE)
        self.spin_lowers.valueChanged.connect(self._on_changer_limits_changed)
        ch.addWidget(self.spin_lowers)
        ch.addSpacing(10)
        self.lbl_changer_status = QLabel("")
        self.lbl_changer_status.setWordWrap(True)
        ch.addWidget(self.lbl_changer_status, stretch=1)
        vbox.addWidget(box_changer)

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
        self.splits_table.setCellWidget(row, 0, self._build_string_combo(sp.string_number))

        # 1-2. Control 1 & Control 2 Dropdowns (half-stop tokens like "P3_HALF" allowed)
        available_ctrls = self._get_single_controllers(include_half_tokens=True)
        c1_target = sp.controllers[0] if len(sp.controllers) > 0 else "P1"
        c2_target = sp.controllers[1] if len(sp.controllers) > 1 else "LKR"
        self.splits_table.setCellWidget(row, 1, self._build_choice_combo(available_ctrls, c1_target, bold=True))
        self.splits_table.setCellWidget(row, 2, self._build_choice_combo(available_ctrls, c2_target, bold=True))

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

            str_num = cb_str.currentData()
            c1 = cb_c1.currentData()
            c2 = cb_c2.currentData()
            if str_num is None or not c1 or not c2:
                continue
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

    def _build_choice_combo(self, items: List[Tuple[str, object]], selected, bold: bool = False) -> QComboBox:
        """Combo of (display, data) items. A selected value that is not among the items is kept
        as a flagged entry instead of silently falling back to the first item (D-07)."""
        combo = QComboBox()
        if bold:
            combo.setStyleSheet("font-weight: bold;")
        for disp, data in items:
            combo.addItem(disp, data)
        idx = combo.findData(selected)
        if idx < 0:
            combo.addItem(f"⚠ {selected} (undefined)", selected)
            idx = combo.count() - 1
        combo.setCurrentIndex(idx)
        return combo

    def _build_string_combo(self, selected_string: int) -> QComboBox:
        open_notes = {s.string_number: s.note_name for s in getattr(self.neck, "open_tuning", [])}
        items: List[Tuple[str, object]] = []
        for s_idx in range(1, self.neck.string_count + 1):
            note = open_notes.get(s_idx, "")
            items.append((f"String {s_idx} ({note})" if note else f"String {s_idx}", s_idx))
        return self._build_choice_combo(items, int(selected_string))

    def _get_single_controllers(self, include_half_tokens: bool = False) -> List[Tuple[str, str]]:
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

        if include_half_tokens:
            half_ids = sorted({h.controller_id for h in getattr(self.neck, "half_stops", [])})
            for cid in half_ids:
                if cid in self.neck.pedals or cid in self.neck.knee_levers:
                    items.append((f"{cid} half-stop", f"{cid}_HALF"))
        return items

    def _refresh_half_stops_tab(self):
        self.half_stops_table.setRowCount(0)
        for rule in getattr(self.neck, "half_stops", []):
            self._insert_half_stop_row(rule)

    def _insert_half_stop_row(self, rule: HalfStopRule):
        row = self.half_stops_table.rowCount()
        self.half_stops_table.insertRow(row)

        combo_ctrl = self._build_choice_combo(self._get_single_controllers(), rule.controller_id, bold=True)
        self.half_stops_table.setCellWidget(row, 0, combo_ctrl)
        self.half_stops_table.setCellWidget(row, 1, self._build_string_combo(rule.string_number))

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

            cid = cb_ctrl.currentData()
            str_num = cb_str.currentData()
            if not cid or str_num is None:
                continue
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

        self._load_changer_controls()
        self._rebuild_matrix_table()
        self._refresh_splits_tab()
        self._refresh_half_stops_tab()

    # -------------------------------------------------------------------------
    # Changer configuration
    # -------------------------------------------------------------------------
    def _load_changer_controls(self):
        for w in (self.spin_raises, self.spin_lowers, self.combo_changer):
            w.blockSignals(True)
        self.spin_raises.setValue(self.neck.changer_raises)
        self.spin_lowers.setValue(self.neck.changer_lowers)
        for w in (self.spin_raises, self.spin_lowers, self.combo_changer):
            w.blockSignals(False)
        self._select_changer_preset()

    def _select_changer_preset(self):
        current = (self.neck.changer_raises, self.neck.changer_lowers)
        row = next((i for i in range(self.combo_changer.count()) if self.combo_changer.itemData(i) == current),
                   self.combo_changer.count() - 1)  # "Custom"
        self.combo_changer.blockSignals(True)
        self.combo_changer.setCurrentIndex(row)
        self.combo_changer.blockSignals(False)

    def _on_changer_preset_changed(self, _row: int):
        data = self.combo_changer.currentData()
        if not data:
            return  # "Custom": keep the spin boxes as they are
        self.neck.changer_raises, self.neck.changer_lowers = data
        self._load_changer_controls()
        self._rebuild_matrix_table()

    def _on_changer_limits_changed(self, _value: int):
        self.neck.changer_raises = self.spin_raises.value()
        self.neck.changer_lowers = self.spin_lowers.value()
        self._select_changer_preset()
        self._rebuild_matrix_table()

    def _refresh_changer_status(self, violations) -> None:
        if not violations:
            self.lbl_changer_status.setText("✔ Every string fits this changer.")
            self.lbl_changer_status.setStyleSheet("color: #3fb950; font-weight: bold;")
            self.lbl_changer_status.setToolTip("")
            return
        lines = [v.message for v in violations]
        more = f" (+{len(lines) - 1} more, hover for all)" if len(lines) > 1 else ""
        self.lbl_changer_status.setText(f"⚠ Exceeds the changer, Apply is blocked: {lines[0]}{more}")
        self.lbl_changer_status.setStyleSheet("color: #ff7b72; font-weight: bold;")
        self.lbl_changer_status.setToolTip("\n".join(lines))

    def _on_neck_type_changed(self):
        n_type = self.combo_neck_type.currentText()
        is_c6 = (n_type == "C6")
        self.cb_c6_offset.setVisible(is_c6)

    def _has_franklin_p1(self) -> bool:
        return "P1" in self.neck.pedals and "Franklin" in self.neck.pedals["P1"].label

    def _set_franklin_p1(self, enabled: bool, franklin_changes: Optional[Dict[int, int]] = None):
        """Inserts or removes a Franklin pedal at P1, renumbering the other pedals and remapping
        every split / half-stop reference through core (D-09)."""
        if enabled == self._has_franklin_p1():
            return
        # Flush table edits into the model so the remap sees them, then rebuild the tables.
        self._save_splits_from_ui()
        self._save_half_stops_from_ui()

        if enabled:
            shift_pedal_ids(self.neck, +1)
            new_pedals: Dict[str, CopedantChange] = {
                "P1": CopedantChange(id="P1", label="P1 (Franklin)", changes=dict(franklin_changes or {}))
            }
            new_pedals.update(self.neck.pedals)
            self.neck.pedals = new_pedals
        else:
            del self.neck.pedals["P1"]
            # Rules that referenced the removed Franklin pedal no longer have a controller.
            self.neck.splits = [
                s for s in self.neck.splits if not any(c.replace("_HALF", "") == "P1" for c in s.controllers)
            ]
            self.neck.half_stops = [h for h in self.neck.half_stops if h.controller_id != "P1"]
            shift_pedal_ids(self.neck, -1)

        self.cb_c6_offset.blockSignals(True)
        self.cb_c6_offset.setChecked(self._has_franklin_p1())
        self.cb_c6_offset.blockSignals(False)
        self._rebuild_matrix_table()
        self._refresh_splits_tab()
        self._refresh_half_stops_tab()

    def _toggle_c6_pedal_offset(self, checked: bool):
        self._set_franklin_p1(checked)

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

        violations = changer_violations(self.neck)
        self._over_limit = {(c, v.string_number) for v in violations for c in v.controllers}
        usage = changer_usage(self.neck)
        self._refresh_changer_status(violations)

        headers = ["String", "Open Tuning"]
        for p_id in pedal_keys:
            p_obj = self.neck.pedals[p_id]
            headers.append(p_obj.label if p_obj.label != p_id else p_id)
        for l_id in lever_keys:
            headers.append(l_id)
        headers.append("Changer ↑/↓")
        changer_col = len(headers) - 1

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

            ups, downs = usage.get(s_num, ([], []))
            over = len(ups) > self.neck.changer_raises or len(downs) > self.neck.changer_lowers
            lbl_use = QLabel(f"↑{len(ups)}/{self.neck.changer_raises}  ↓{len(downs)}/{self.neck.changer_lowers}")
            lbl_use.setAlignment(Qt.AlignCenter)
            lbl_use.setToolTip(f"Raises: {', '.join(ups) or 'none'}\nLowers: {', '.join(downs) or 'none'}")
            color = "#ff7b72" if over else "#8b949e"
            lbl_use.setStyleSheet(f"font-weight: bold; font-size: 11px; color: {color};")
            self.table.setCellWidget(s_idx, changer_col, lbl_use)

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
        if (ctrl.id, s_num) in getattr(self, "_over_limit", set()):
            widget.setStyleSheet("background-color: #3d1418; border: 2px solid #dc3545;")
            widget.setToolTip("This pull exceeds the changer configuration for this string.")
        else:
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
        is_e9 = (self.neck.neck_type == NeckType.E9 or "E9" in self.neck.name)
        self._set_franklin_p1(True, franklin_changes={5: -1, 6: -2} if is_e9 else {})

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


    # -------------------------------------------------------------------------
    # Working copies, persistence and apply (D-22)
    # -------------------------------------------------------------------------
    def _sync_ui_to_neck(self):
        """Flushes every tab's widgets into the working copy of the current neck."""
        self._save_splits_from_ui()
        self._save_half_stops_from_ui()
        self.neck.name = self.edit_name.text().strip() or self.neck.name
        self.neck.neck_type = NeckType(self.combo_neck_type.currentText())
        self.neck.author = self.edit_author.text()
        self.neck.description = self.edit_desc.toPlainText()
        self.neck.author_bio = self.edit_bio.toPlainText()
        self.neck.social_media = self.edit_social.text()
        self._working[self.current_neck_idx] = self.neck

    def saved_neck_for_compare(self) -> Neck:
        """The saved version of the neck being edited, migrated like the working copy so a
        legacy rename (VL -> LKV) is not reported as a change (E-25)."""
        saved = self.guitar.necks[self.current_neck_idx] if self.guitar else self.original_neck
        saved = deepcopy(saved)
        migrate_legacy_ids(saved)
        migrate_half_stop_tokens(saved)
        return saved

    def _compare_to_saved(self):
        from ui.copedant_compare_dialog import CopedantCompareDialog

        self._sync_ui_to_neck()
        dlg = CopedantCompareDialog(self.saved_neck_for_compare(), deepcopy(self.neck), parent=self)
        dlg.exec()
        dlg.deleteLater()

    def _append_neck_and_switch(self, new_neck: Neck):
        """Adds a neck to the guitar immediately (flagged via guitar_changed) and edits it."""
        self.guitar.necks.append(new_neck)
        self.guitar_changed = True
        new_idx = len(self.guitar.necks) - 1
        self._working[new_idx] = deepcopy(new_neck)

        self.current_neck_idx = new_idx
        self._rebuild_copedant_combo()

        self.neck = self._working[new_idx]
        self.setWindowTitle(f"Copedant Setup & Tuning Editor - {self.neck.name}")
        self._load_neck_data()

    def _duplicate_copedant(self):
        """Adds a copy of this tuning (with unapplied edits) to the open profile."""
        if not self.guitar:
            return
        self._sync_ui_to_neck()
        base_name = self.neck.name.replace(" (Copy)", "")
        copy_neck = deepcopy(self.neck)
        copy_neck.name = unique_neck_name(self.guitar, f"{base_name} (Copy)")
        copy_neck.source_profile = ""
        self._append_neck_and_switch(copy_neck)
        self._persist_active_guitar()

    def _copy_to_profile(self):
        """Appends a copy of this tuning to another user profile (chosen or new)."""
        self._sync_ui_to_neck()
        open_profile = self.guitar.profile if self.guitar else None
        choices = [p for p in ProfileManager.list_user_profiles() if p != open_profile]
        new_item = "➕ New profile..."
        name, ok = QInputDialog.getItem(
            self, "Copy Tuning to Profile", f"Add '{self.neck.name}' to profile:",
            choices + [new_item], 0, False)
        if not ok:
            return
        if name == new_item:
            name, ok = QInputDialog.getText(self, "New Profile", "Profile name:", text=self.neck.name)
            if not ok:
                return
            safe_name = ProfileManager.sanitize_name(name)
            if not safe_name:
                QMessageBox.warning(self, "Invalid Name", "Profile names must contain letters or digits.")
                return
            if ProfileManager.profile_exists(safe_name) or safe_name == open_profile:
                QMessageBox.warning(self, "Profile Exists", f"A profile named '{safe_name}' already exists.")
                return
            name = safe_name
        try:
            tuning_name = ProfileManager.add_tuning_to_profile(name, self.neck)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Copy Failed", f"Could not save to profile '{name}':\n{e}")
            return
        QMessageBox.information(self, "Tuning Copied", f"Added '{tuning_name}' to profile '{name}'.")

    def _rebuild_copedant_combo(self):
        """The tunings of the open profile. Item data: ("neck", index)."""
        combo = self.combo_copedant
        combo.blockSignals(True)
        combo.clear()
        for idx, n in enumerate(self.guitar.necks):
            combo.addItem(f"{n.name} ({n.string_count} Str)", ("neck", idx))
        sel = next((i for i in range(combo.count()) if combo.itemData(i) == ("neck", self.current_neck_idx)), 0)
        combo.setCurrentIndex(sel)
        combo.blockSignals(False)

    def _on_copedant_combo_changed(self, _row: int):
        data = self.combo_copedant.currentData()
        if data:
            self._on_switch_copedant(data[1])

    def _on_switch_copedant(self, idx: int):
        if self.guitar and 0 <= idx < len(self.guitar.necks):
            # Keep unapplied edits of the neck we are leaving (D-22).
            self._sync_ui_to_neck()
            self.current_neck_idx = idx
            if idx in self._working:
                self.neck = self._working[idx]
            else:
                self.neck = deepcopy(self.guitar.necks[idx])
                self._migrate_legacy_levers()
                self._working[idx] = self.neck
            self.setWindowTitle(f"Copedant Setup & Tuning Editor - {self.neck.name}")
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
                log.exception("Failed to persist active guitar setup")

    def _check_changer_limits(self) -> bool:
        """Blocks Apply while any neck edited in this session needs more raises/lowers per string
        than its changer configuration holds. Shows the problems and switches to that neck."""
        pending = list(self._working.items()) if self.guitar else [(self.current_neck_idx, self.neck)]
        if self.guitar and self.current_neck_idx not in self._working:
            pending.append((self.current_neck_idx, self.neck))
        for idx, neck in pending:
            violations = changer_violations(neck)
            if not violations:
                continue
            if self.guitar and idx != self.current_neck_idx:
                self._on_switch_copedant(idx)
                self._rebuild_copedant_combo()
            self.tabs.setCurrentWidget(self.tab_matrix)
            details = "\n".join(f"• {v.message}" for v in violations)
            QMessageBox.warning(
                self,
                "Changer Configuration Exceeded",
                f"'{neck.name}' cannot be applied: its changer is set to "
                f"{changer_label(neck.changer_raises, neck.changer_lowers)}.\n\n{details}\n\n"
                "Remove a pull from these strings, or change the Changer Configuration if your "
                "guitar's changer has more fingers.",
            )
            return False
        return True

    def _apply_and_close(self):
        self._sync_ui_to_neck()
        if not self._check_changer_limits():
            return

        if self.guitar:
            # Apply every neck edited in this session, not just the visible one.
            for idx, working_neck in self._working.items():
                if 0 <= idx < len(self.guitar.necks):
                    self.guitar.necks[idx] = working_neck
        else:
            self.original_neck.__dict__.update(self.neck.__dict__)

        # The open profile's file is written by MainWindow._save_active_guitar_setup (D-22).
        self._persist_active_guitar()

        self.neck_updated.emit()
        self.accept()
