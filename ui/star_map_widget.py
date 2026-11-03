"""Floating Star Map & Strings of Pearls Reference Tool (Jeff Newman Methodology)."""

from typing import List, Set
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.star_map_engine import StarMapEngine, StarMapLandmark
from core.theory import NOTE_NAMES_SHARP


class StarMapWidget(QDialog):
    landmark_selected = Signal(int, set, set)  # fret, controllers, target_strings

    def __init__(self, neck=None, parent=None):
        super().__init__(parent)
        self.neck = neck
        self.setWindowTitle("Jeff Newman Star Map & Strings of Pearls Explorer")
        self.resize(880, 520)

        self.current_root = "C"
        self._init_ui()
        self._refresh_star_map()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Root Key Selector
        top_h = QHBoxLayout()
        top_h.addWidget(QLabel("<b>Chord Key:</b>"))
        self.combo_root = QComboBox()
        self.combo_root.addItems(NOTE_NAMES_SHARP)
        self.combo_root.setCurrentText(self.current_root)
        self.combo_root.currentIndexChanged.connect(self._on_root_changed)
        top_h.addWidget(self.combo_root)
        top_h.addStretch()
        layout.addLayout(top_h)

        # 2. 4-Anchor Star Map Chain
        self.box_chain = QGroupBox("4-Anchor Major Chain (Left-to-Right)")
        self.chain_layout = QHBoxLayout(self.box_chain)
        self.chain_layout.setContentsMargins(10, 8, 10, 8)
        self.chain_layout.setSpacing(8)
        layout.addWidget(self.box_chain)

        # 3. Lateral D-Lever Pockets Summary
        box_pockets = QGroupBox("The 3 Lateral D-Lever Pockets (Strings 5 & 8 / 4 & 5)")
        pockets_grid = QGridLayout(box_pockets)
        pockets_grid.setContentsMargins(10, 8, 10, 8)
        pockets_grid.setSpacing(8)

        self.btn_pocket_1 = QPushButton("Pocket #1: A&B ⟷ D Lever (-2 Frets)")
        self.btn_pocket_1.setStyleSheet("font-weight: bold; min-height: 32px;")
        self.btn_pocket_1.clicked.connect(lambda: self._select_pocket(1))
        pockets_grid.addWidget(self.btn_pocket_1, 0, 0)

        self.btn_pocket_2 = QPushButton("Pocket #2: A&B ⟷ Open (+5 Frets via D)")
        self.btn_pocket_2.setStyleSheet("font-weight: bold; min-height: 32px;")
        self.btn_pocket_2.clicked.connect(lambda: self._select_pocket(2))
        pockets_grid.addWidget(self.btn_pocket_2, 0, 1)

        self.btn_pocket_3 = QPushButton("Pocket #3: Open ⟷ D Lever (+5 Frets)")
        self.btn_pocket_3.setStyleSheet("font-weight: bold; min-height: 32px;")
        self.btn_pocket_3.clicked.connect(lambda: self._select_pocket(3))
        pockets_grid.addWidget(self.btn_pocket_3, 0, 2)

        layout.addWidget(box_pockets)

        # 4. Detailed Landmark Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Landmark", "Fret", "Pedals / Levers", "Strings", "Theory Note"])
        self.table.cellDoubleClicked.connect(self._on_table_double_clicked)
        layout.addWidget(self.table, stretch=1)

    def _on_root_changed(self):
        self.current_root = self.combo_root.currentText()
        self._refresh_star_map()

    def _refresh_star_map(self):
        landmarks = StarMapEngine.calculate_major_star_map(self.current_root, self.neck)

        # Rebuild visual chain buttons
        while self.chain_layout.count() > 0:
            item = self.chain_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for lm in landmarks:
            btn = QPushButton(lm.label)
            btn.setToolTip(f"{lm.description}\n{lm.strings_desc}")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #212529;
                    color: #ffde7a;
                    font-weight: bold;
                    font-size: 12px;
                    border: 1.5px solid #ffc107;
                    border-radius: 4px;
                    padding: 6px 12px;
                }
                QPushButton:hover {
                    background-color: #ffc107;
                    color: #000000;
                }
            """)
            btn.clicked.connect(lambda _, l=lm: self.landmark_selected.emit(l.fret, l.controllers, l.target_strings))
            self.chain_layout.addWidget(btn)

        self.chain_layout.addStretch()

        # Populate table
        self.table.setRowCount(len(landmarks))
        for idx, lm in enumerate(landmarks):
            lev_str = " + ".join(sorted(lm.controllers)) if lm.controllers else "None (Open)"
            self.table.setItem(idx, 0, QTableWidgetItem(lm.label))
            self.table.setItem(idx, 1, QTableWidgetItem(f"Fret {lm.fret}"))
            self.table.setItem(idx, 2, QTableWidgetItem(lev_str))
            self.table.setItem(idx, 3, QTableWidgetItem(lm.strings_desc))
            self.table.setItem(idx, 4, QTableWidgetItem(lm.description))

    def _select_pocket(self, pocket_num: int):
        landmarks = StarMapEngine.calculate_major_star_map(self.current_root, self.neck)
        if not landmarks:
            return

        if pocket_num == 1:
            lm = next((l for l in landmarks if "D" in l.label), landmarks[0])
        elif pocket_num == 2:
            lm = next((l for l in landmarks if "AB" in l.label), landmarks[0])
        else:
            lm = next((l for l in landmarks if "Open" in l.label), landmarks[0])

        self.landmark_selected.emit(lm.fret, set(lm.controllers), set(lm.target_strings))

    def _on_table_double_clicked(self, row: int, col: int):
        landmarks = StarMapEngine.calculate_major_star_map(self.current_root, self.neck)
        if 0 <= row < len(landmarks):
            lm = landmarks[row]
            self.landmark_selected.emit(lm.fret, lm.controllers, lm.target_strings)