"""Dialog for managing, auto-detecting, and restoring mechanical changer splits."""

from typing import List, Optional, Set
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import Neck, NeckType, SplitRule, detect_potential_splits
from core.presets import build_standard_c6_10, build_standard_emmons_e9_10
from core.theory import midi_to_note_name


class SplitManagerDialog(QDialog):
    splits_updated = Signal()

    def __init__(self, neck: Neck, parent=None):
        super().__init__(parent)
        self.neck = neck
        self.setWindowTitle("Copedant Mechanical Splits Manager")
        self.resize(840, 500)

        self._init_ui()
        self._populate_splits_table()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Header Toolbar with Detection & Bulk Actions
        top_bar = QHBoxLayout()
        lbl_info = QLabel(
            "<b>Mechanical Splits:</b> Defines the resulting pitch when multiple pedals/levers pull the same string simultaneously."
        )
        lbl_info.setStyleSheet("color: #6c757d; font-size: 11px;")
        top_bar.addWidget(lbl_info)
        top_bar.addStretch()

        btn_detect = QPushButton("🔍 Detect Potential Splits")
        btn_detect.setStyleSheet("font-weight: bold; padding: 4px 10px;")
        btn_detect.clicked.connect(self._on_detect_splits)
        top_bar.addWidget(btn_detect)

        btn_include_all = QPushButton("Include All")
        btn_include_all.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        btn_include_all.clicked.connect(lambda: self._set_all_active(True))
        top_bar.addWidget(btn_include_all)

        btn_exclude_all = QPushButton("Exclude All")
        btn_exclude_all.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        btn_exclude_all.clicked.connect(lambda: self._set_all_active(False))
        top_bar.addWidget(btn_exclude_all)

        layout.addLayout(top_bar)

        # 2. Main Splits Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Action", "String / Open", "P/KL Combo", "Resulting Shift (ST)", "Resulting Pitch", "Description"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, stretch=1)

        # 3. Add Custom Split Box
        add_box = QGroupBox("Add / Override Custom Split")
        add_layout = QHBoxLayout(add_box)
        add_layout.setContentsMargins(8, 6, 8, 6)
        add_layout.setSpacing(10)

        add_layout.addWidget(QLabel("String:"))
        self.spin_string = QSpinBox()
        self.spin_string.setRange(1, self.neck.string_count)
        self.spin_string.setValue(4)
        add_layout.addWidget(self.spin_string)

        all_ctrls = sorted(list(self.neck.pedals.keys()) + list(self.neck.knee_levers.keys()))

        add_layout.addWidget(QLabel("Ctrl 1:"))
        self.combo_c1 = QComboBox()
        self.combo_c1.addItems(all_ctrls)
        add_layout.addWidget(self.combo_c1)

        add_layout.addWidget(QLabel("Ctrl 2:"))
        self.combo_c2 = QComboBox()
        self.combo_c2.addItems(all_ctrls)
        self.combo_c2.setCurrentIndex(min(len(all_ctrls) - 1, 3))
        add_layout.addWidget(self.combo_c2)

        add_layout.addWidget(QLabel("Net Shift:"))
        self.spin_delta = QSpinBox()
        self.spin_delta.setRange(-6, 6)
        self.spin_delta.setValue(1)
        self.spin_delta.setPrefix("+")
        add_layout.addWidget(self.spin_delta)

        btn_add = QPushButton("➕ Add Split")
        btn_add.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; padding: 4px 12px;")
        btn_add.clicked.connect(self._add_split_rule)
        add_layout.addWidget(btn_add)

        layout.addWidget(add_box)

        # 4. Bottom Controls Bar
        bottom_bar = QHBoxLayout()
        btn_restore = QPushButton("↺ Restore Factory Defaults")
        btn_restore.setStyleSheet("color: #dc3545; font-weight: bold; padding: 4px 10px;")
        btn_restore.clicked.connect(self._restore_defaults)
        bottom_bar.addWidget(btn_restore)

        btn_delete = QPushButton("Delete Selected Split")
        btn_delete.clicked.connect(self._delete_selected_split)
        bottom_bar.addWidget(btn_delete)

        bottom_bar.addStretch()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_close)

        layout.addLayout(bottom_bar)

    def _populate_splits_table(self):
        self.table.setRowCount(len(self.neck.splits))
        for row, rule in enumerate(self.neck.splits):
            # 1. Action: Include / Exclude Checkbox
            cb = QCheckBox("Include" if rule.is_active else "Exclude")
            cb.setChecked(rule.is_active)
            cb.setStyleSheet("font-weight: bold; color: #28a745;" if rule.is_active else "color: #6c757d;")
            cb.toggled.connect(lambda chk, r=rule, c=cb: self._toggle_split_active(r, chk, c))
            self.table.setCellWidget(row, 0, cb)

            # 2. String & Open Pitch
            open_sp = next((sp for sp in self.neck.open_tuning if sp.string_number == rule.string_number), None)
            open_str = f"Str {rule.string_number} ({open_sp.note_name})" if open_sp else f"Str {rule.string_number}"
            str_item = QTableWidgetItem(open_str)
            str_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, str_item)

            # 3. P/KL Combo
            combo_str = " + ".join(f"({c})" for c in sorted(rule.controllers))
            combo_item = QTableWidgetItem(combo_str)
            combo_item.setTextAlignment(Qt.AlignCenter)
            combo_item.setFont(self.font())
            self.table.setItem(row, 2, combo_item)

            # 4. Resulting Shift (ST) Inline Spinbox Editor
            spin_shift = QSpinBox()
            spin_shift.setRange(-8, 8)
            spin_shift.setValue(rule.semitone_delta)
            spin_shift.setPrefix("+" if rule.semitone_delta > 0 else "")
            spin_shift.valueChanged.connect(lambda val, r=rule, rw=row: self._on_delta_changed(r, val, rw))
            self.table.setCellWidget(row, 3, spin_shift)

            # 5. Resulting Pitch (Live Updated)
            pitch_str = midi_to_note_name(open_sp.midi_note + rule.semitone_delta) if open_sp else "—"
            pitch_item = QTableWidgetItem(pitch_str)
            pitch_item.setTextAlignment(Qt.AlignCenter)
            pitch_item.setFont(self.font())
            self.table.setItem(row, 4, pitch_item)

            # 6. Description
            self.table.setItem(row, 5, QTableWidgetItem(rule.description or "Mechanical Split"))

    def _on_delta_changed(self, rule: SplitRule, new_delta: int, row: int):
        rule.semitone_delta = new_delta
        open_sp = next((sp for sp in self.neck.open_tuning if sp.string_number == rule.string_number), None)
        if open_sp:
            new_pitch = midi_to_note_name(open_sp.midi_note + new_delta)
            self.table.setItem(row, 4, QTableWidgetItem(new_pitch))
            self.table.item(row, 4).setTextAlignment(Qt.AlignCenter)
        self.splits_updated.emit()

    def _toggle_split_active(self, rule: SplitRule, active: bool, cb: QCheckBox):
        rule.is_active = active
        cb.setText("Include" if active else "Exclude")
        cb.setStyleSheet("font-weight: bold; color: #28a745;" if active else "color: #6c757d;")
        self.splits_updated.emit()

    def _set_all_active(self, active: bool):
        for r in self.neck.splits:
            r.is_active = active
        self._populate_splits_table()
        self.splits_updated.emit()

    def _on_detect_splits(self):
        detected = detect_potential_splits(self.neck)
        count_new = len(detected) - len(self.neck.splits)
        self.neck.splits = detected
        self._populate_splits_table()
        self.splits_updated.emit()
        QMessageBox.information(
            self,
            "Split Detection Complete",
            f"Found {len(detected)} potential split configurations based on current copedant pulls."
            + (f" ({count_new} new candidates added)" if count_new > 0 else " (All combinations verified)"),
        )

    def _restore_defaults(self):
        confirm = QMessageBox.question(
            self,
            "Restore Factory Splits",
            f"Reset all split rules for '{self.neck.name}' back to factory defaults?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            if self.neck.neck_type == NeckType.C6:
                default_neck = build_standard_c6_10()
            else:
                default_neck = build_standard_emmons_e9_10()

            self.neck.splits = [SplitRule.from_dict(s.to_dict()) for s in default_neck.splits]
            self._populate_splits_table()
            self.splits_updated.emit()

    def _add_split_rule(self):
        s_num = self.spin_string.value()
        c1 = self.combo_c1.currentText()
        c2 = self.combo_c2.currentText()
        delta = self.spin_delta.value()

        if c1 == c2:
            return

        ctrls = sorted([c1, c2])
        self.neck.splits = [
            r for r in self.neck.splits if not (r.string_number == s_num and sorted(r.controllers) == ctrls)
        ]

        new_rule = SplitRule(
            string_number=s_num,
            controllers=ctrls,
            semitone_delta=delta,
            is_active=True,
            description=f"Manual split: ({c1}) + ({c2}) on Str {s_num}",
        )
        self.neck.splits.append(new_rule)
        self._populate_splits_table()
        self.splits_updated.emit()

    def _delete_selected_split(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.neck.splits):
            del self.neck.splits[row]
            self._populate_splits_table()
            self.splits_updated.emit()