"""Mechanical Half-Stop Configuration Dialog.
Configures single-controller intermediate feel-stops per copedant profile.
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

from core.models import HalfStopRule, Neck


class HalfStopDialog(QDialog):
    half_stops_updated = Signal()

    def __init__(self, neck: Neck, parent=None):
        super().__init__(parent)
        self.neck = neck
        self.setWindowTitle("Mechanical Half-Stop Configuration")
        self.resize(800, 460)

        self._init_ui()
        self._load_data()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        lbl_desc = QLabel(
            "<b>Mechanical Half-Stop Configuration:</b><br>"
            "<small style='color: #8b92a0;'>"
            "Enable intermediate mechanical feel-stops on individual knee levers or pedals. "
            "When enabled, a single click engages the half-stop (amber glow), and a double click engages the full stop."
            "</small>"
        )
        root.addWidget(lbl_desc)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Lever / Pedal", "Affected String", "Half-Stop Delta", "Enabled", "Description"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setShowGrid(True)
        root.addWidget(self.table, stretch=1)

        btn_h = QHBoxLayout()

        btn_add = QPushButton("+ Add Half-Stop")
        btn_add.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        btn_add.clicked.connect(self._add_rule)
        btn_h.addWidget(btn_add)

        btn_auto = QPushButton("⚡ Auto-Detect 2-Semitone Pulls")
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

    def _get_single_controllers(self) -> List[tuple[str, str]]:
        items: List[tuple[str, str]] = []
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

    def _load_data(self):
        self.table.setRowCount(0)
        for rule in getattr(self.neck, "half_stops", []):
            self._insert_row(rule)

    def _insert_row(self, rule: HalfStopRule):
        row = self.table.rowCount()
        self.table.insertRow(row)

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
        self.table.setCellWidget(row, 0, combo_ctrl)

        combo_str = QComboBox()
        combo_str.setStyleSheet("font-weight: bold;")
        open_notes = {s.string_number: s.note_name for s in getattr(self.neck, "open_tuning", [])}
        str_count = self.neck.string_count if self.neck else 10

        selected_s = 0
        for s_idx in range(1, str_count + 1):
            note = open_notes.get(s_idx, "")
            label = f"String {s_idx} ({note})" if note else f"String {s_idx}"
            combo_str.addItem(label, s_idx)
            if s_idx == rule.string_number:
                selected_s = s_idx - 1
        combo_str.setCurrentIndex(selected_s)
        self.table.setCellWidget(row, 1, combo_str)

        spin = QSpinBox()
        spin.setRange(-4, 4)
        spin.setValue(int(rule.semitone_delta))
        self.table.setCellWidget(row, 2, spin)

        check_box = QCheckBox()
        check_box.setChecked(rule.is_active)
        check_widget = QWidget()
        layout_c = QHBoxLayout(check_widget)
        layout_c.setContentsMargins(0, 0, 0, 0)
        layout_c.setAlignment(Qt.AlignCenter)
        layout_c.addWidget(check_box)
        self.table.setCellWidget(row, 3, check_widget)

        edit_desc = QLineEdit(rule.description or "")
        self.table.setCellWidget(row, 4, edit_desc)

    def _add_rule(self):
        rule = HalfStopRule(
            controller_id="LKL",
            string_number=4,
            semitone_delta=1,
            is_active=True,
            description="Intermediate feel stop (E to F)",
        )
        self._insert_row(rule)

    def _auto_detect(self):
        added = 0
        all_controllers = {**self.neck.pedals, **self.neck.knee_levers}
        existing_pairs = {(r.controller_id, r.string_number) for r in getattr(self.neck, "half_stops", [])}

        for cid, cobj in all_controllers.items():
            for s_num, delta in cobj.changes.items():
                if abs(delta) >= 2 and (cid, s_num) not in existing_pairs:
                    half_delta = 1 if delta > 0 else -1
                    rule = HalfStopRule(
                        controller_id=cid,
                        string_number=s_num,
                        semitone_delta=half_delta,
                        is_active=True,
                        description=f"Auto-detected feel stop on {cid}",
                    )
                    self._insert_row(rule)
                    added += 1

        QMessageBox.information(self, "Detection Complete", f"Identified and added {added} half-stop positions.")

    def _remove_selected(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _save_and_close(self):
        rules: List[HalfStopRule] = []
        for r in range(self.table.rowCount()):
            cb_ctrl = self.table.cellWidget(r, 0)
            cb_str = self.table.cellWidget(r, 1)
            spin = self.table.cellWidget(r, 2)
            c_box_widget = self.table.cellWidget(r, 3)
            edit = self.table.cellWidget(r, 4)

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
        self.half_stops_updated.emit()
        self.accept()