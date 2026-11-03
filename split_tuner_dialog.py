"""Mechanical Split Manager Dialog.
Configures conflict resolutions when two or more controllers are engaged simultaneously.
"""

from typing import Dict, List, Optional, Set
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from core.models import Neck, SplitRule, detect_potential_splits


class SplitTunerDialog(QDialog):
    splits_updated = Signal()

    def __init__(self, neck: Neck, parent=None):
        super().__init__(parent)
        self.neck = neck
        self.setWindowTitle("Mechanical Split Manager (Changer Conflicts)")
        self.resize(840, 500)

        self._init_ui()
        self._load_data()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        lbl_desc = QLabel(
            "<b>Changer Split Conflicts (2+ Controllers):</b><br>"
            "<small style='color: #8b92a0;'>"
            "Tune mechanical conflict resolutions when multiple pedals or knee levers pull on the same string simultaneously "
            "(e.g., Pedal A raise + LKR lower on String 5)."
            "</small>"
        )
        root.addWidget(lbl_desc)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Controller Combination", "String", "Resolved Net Delta", "Active", "Description"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setShowGrid(True)
        root.addWidget(self.table, stretch=1)

        btn_h = QHBoxLayout()

        btn_add = QPushButton("+ Add Split Conflict")
        btn_add.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        btn_add.clicked.connect(self._add_rule)
        btn_h.addWidget(btn_add)

        btn_auto = QPushButton("⚡ Auto-Detect Changer Conflicts")
        btn_auto.setStyleSheet("font-weight: bold; padding: 6px 14px; color: #20c997;")
        btn_auto.clicked.connect(self._auto_detect)
        btn_h.addWidget(btn_auto)

        btn_rem = QPushButton("Remove Selected")
        btn_rem.setStyleSheet("color: #dc3545; font-weight: bold; padding: 6px 14px;")
        btn_rem.clicked.connect(self._remove_selected)
        btn_h.addWidget(btn_rem)

        btn_h.addStretch()

        btn_save = QPushButton("Save & Apply")
        btn_save.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 6px 20px; border-radius: 4px;")
        btn_save.clicked.connect(self._save_and_close)
        btn_h.addWidget(btn_save)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("padding: 6px 14px;")
        btn_cancel.clicked.connect(self.reject)
        btn_h.addWidget(btn_cancel)

        root.addLayout(btn_h)

    def _load_data(self):
        self.table.setRowCount(0)
        for sp in getattr(self.neck, "splits", []):
            if len(sp.controllers) >= 2:
                self._insert_row(sp)

    def _insert_row(self, sp: SplitRule):
        row = self.table.rowCount()
        self.table.insertRow(row)

        edit_ctrl = QLineEdit(" + ".join(sp.controllers))
        edit_ctrl.setStyleSheet("font-weight: bold;")
        self.table.setCellWidget(row, 0, edit_ctrl)

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
        self.table.setCellWidget(row, 1, combo_str)

        spin = QSpinBox()
        spin.setRange(-6, 6)
        spin.setValue(int(sp.semitone_delta))
        self.table.setCellWidget(row, 2, spin)

        check_box = QCheckBox()
        check_box.setChecked(sp.is_active)
        check_widget = QWidget()
        layout_c = QHBoxLayout(check_widget)
        layout_c.setContentsMargins(0, 0, 0, 0)
        layout_c.setAlignment(Qt.AlignCenter)
        layout_c.addWidget(check_box)
        self.table.setCellWidget(row, 3, check_widget)

        edit_desc = QLineEdit(sp.description or "")
        self.table.setCellWidget(row, 4, edit_desc)

    def _add_rule(self):
        sp = SplitRule(
            string_number=5,
            controllers=["P1", "LKR"],
            semitone_delta=0,
            is_active=True,
            description="P1 raise + LKR lower conflict",
        )
        self._insert_row(sp)

    def _auto_detect(self):
        detected = detect_potential_splits(self.neck)
        for s in detected:
            self._insert_row(s)
        QMessageBox.information(self, "Detection Complete", f"Identified {len(detected)} simultaneous changer conflicts.")

    def _remove_selected(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _save_and_close(self):
        updated_splits: List[SplitRule] = []
        for r in range(self.table.rowCount()):
            edit_ctrl = self.table.cellWidget(r, 0)
            cb_str = self.table.cellWidget(r, 1)
            spin = self.table.cellWidget(r, 2)
            c_box_widget = self.table.cellWidget(r, 3)
            edit_desc = self.table.cellWidget(r, 4)

            if not isinstance(edit_ctrl, QLineEdit) or not isinstance(cb_str, QComboBox):
                continue

            ctrl_tokens = [c.strip() for c in edit_ctrl.text().split("+") if c.strip()]
            str_num = cb_str.currentData() or 1
            delta = spin.value() if isinstance(spin, QSpinBox) else 0
            is_act = c_box_widget.findChild(QCheckBox).isChecked() if c_box_widget else True
            desc = edit_desc.text().strip() if isinstance(edit_desc, QLineEdit) else ""

            updated_splits.append(SplitRule(
                string_number=int(str_num),
                controllers=ctrl_tokens,
                semitone_delta=int(delta),
                is_active=is_act,
                description=desc,
            ))

        self.neck.splits = updated_splits
        self.splits_updated.emit()
        self.accept()