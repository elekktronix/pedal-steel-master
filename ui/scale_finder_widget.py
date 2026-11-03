"""Floating tool window for pedal steel scale boxes and position pockets across strings."""

from typing import Dict, List, Optional, Set
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import Neck
from core.scale_engine import BoxNote, ScaleBox, ScaleSolver
from core.theory import NOTE_NAMES_SHARP, SCALE_FORMULAS


class ScaleFinderWidget(QWidget):
    scale_step_applied = Signal(int, list, int, str)   # fret, levers, string_number, banner
    box_highlight_requested = Signal(int, int)          # min_fret, max_fret
    clear_highlight_requested = Signal()                # clear box shading
    box_shading_toggled = Signal(bool) # Emits when the user toggles the preference
    play_note_requested = Signal(int)                   # midi_note
    play_notes_requested = Signal(list)                 # list of midi notes in sequence
    target_changed = Signal(str, str)                   # root, scale_name

    def __init__(self, neck: Neck, current_pocket: Set[int] = None, show_box_initial: bool = True, parent=None):
        super().__init__(parent)
        self.neck = neck
        self.show_box_initial = show_box_initial
        self.boxes: List[ScaleBox] = []
        self.active_box: Optional[ScaleBox] = None
        self.active_step_idx: int = -1

        self.walk_timer = QTimer(self)
        self.walk_timer.timeout.connect(self._auto_step_forward)

        self._init_ui()
        self.refresh_solver()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 1. Top Controls Bar
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>Root:</b>"))
        self.root_combo = QComboBox()
        self.root_combo.addItems(NOTE_NAMES_SHARP)
        self.root_combo.setCurrentText("G")
        self.root_combo.currentIndexChanged.connect(self._on_combo_changed)
        top_bar.addWidget(self.root_combo)

        top_bar.addSpacing(10)
        top_bar.addWidget(QLabel("<b>Scale:</b>"))
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(list(SCALE_FORMULAS.keys()))
        self.scale_combo.setCurrentText("Major (Ionian)")
        self.scale_combo.currentIndexChanged.connect(self._on_combo_changed)
        top_bar.addWidget(self.scale_combo)

        top_bar.addSpacing(10)
        top_bar.addWidget(QLabel("<b>Pocket Span:</b>"))
        self.span_combo = QComboBox()
        self.span_combo.addItem("Compact (3 Frets)", 3)
        self.span_combo.addItem("Standard (4 Frets)", 4)
        self.span_combo.currentIndexChanged.connect(self.refresh_solver)
        top_bar.addWidget(self.span_combo)

        top_bar.addStretch()

        self.btn_play_run = QPushButton("▶ Play Full Pocket Run")
        self.btn_play_run.setStyleSheet(
            "background-color: #28a745; color: white; font-weight: bold; min-height: 28px; padding: 0 14px;"
        )
        self.btn_play_run.clicked.connect(self._play_box_run)
        top_bar.addWidget(self.btn_play_run)

        layout.addLayout(top_bar)

        # 2. Position Pocket Selector Ribbon
        positions_group = QGroupBox("Select 3-4 Fret Position Pocket Across All Strings")
        self.positions_layout = QHBoxLayout(positions_group)
        self.positions_layout.setContentsMargins(8, 6, 8, 6)
        self.positions_layout.setSpacing(8)
        self.pos_button_group = QButtonGroup(self)
        self.pos_button_group.idClicked.connect(self._on_position_selected)
        layout.addWidget(positions_group)

        # 3. Step Transport Strip
        transport_bar = QHBoxLayout()
        self.lbl_active_box_title = QLabel("Active Pocket: <b>Position 1 (Frets 3 - 5)</b>")
        self.lbl_active_box_title.setStyleSheet("font-size: 12px; color: #0d6efd;")
        transport_bar.addWidget(self.lbl_active_box_title)

        transport_bar.addSpacing(15)

        # Pocket Highlight Toggle Checkbox
        self.cb_show_box = QCheckBox("Show Pocket Box on Fretboard")
        self.cb_show_box.setChecked(self.show_box_initial)
        self.cb_show_box.setStyleSheet("font-weight: bold;")
        self.cb_show_box.toggled.connect(self._on_toggle_box_shading)
        transport_bar.addWidget(self.cb_show_box)

        transport_bar.addStretch()

        self.btn_prev = QPushButton("◀ Prev Note")
        self.btn_prev.clicked.connect(self.prev_step)
        transport_bar.addWidget(self.btn_prev)

        self.btn_next = QPushButton("Next Note ▶")
        self.btn_next.clicked.connect(self.next_step)
        transport_bar.addWidget(self.btn_next)

        self.btn_walk = QPushButton("▶ Auto-Walk")
        self.btn_walk.setStyleSheet("font-weight: bold; min-height: 26px; padding: 0 12px;")
        self.btn_walk.clicked.connect(self._toggle_auto_walk)
        transport_bar.addWidget(self.btn_walk)

        self.btn_highlight = QPushButton("📍 Re-Highlight")
        self.btn_highlight.clicked.connect(self._highlight_active_box)
        transport_bar.addWidget(self.btn_highlight)

        layout.addLayout(transport_bar)

        # 4. Tabbed Views: Grid vs. Staircase Run
        self.tabs = QTabWidget()

        # Tab A: String-by-String Pocket Grid
        self.table_grid = QTableWidget()
        self.table_grid.setColumnCount(5)
        self.table_grid.setHorizontalHeaderLabels([
            "String #", "Open Note", "Pocket Notes in Box (Fret & Controller)", "Degrees Covered", "Pluck String"
        ])
        self.table_grid.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_grid.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_grid.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_grid.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_grid.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_grid.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabs.addTab(self.table_grid, "🎸 Across-the-Strings Grid (String 10 → 1)")

        # Tab B: Ascending Sequential Staircase
        self.table_staircase = QTableWidget()
        self.table_staircase.setColumnCount(6)
        self.table_staircase.setHorizontalHeaderLabels([
            "Step", "Degree", "Note", "String", "Tone Bar Fret", "Pedals / Levers"
        ])
        self.table_staircase.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_staircase.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_staircase.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_staircase.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_staircase.cellClicked.connect(self._on_staircase_cell_clicked)
        self.tabs.addTab(self.table_staircase, "🪜 Sequential Pocket Run (Bass → Treble)")

        layout.addWidget(self.tabs, stretch=1)

    def update_neck(self, neck: Neck):
        self.neck = neck
        self.refresh_solver()

    def set_active_pocket(self, pocket: Set[int]):
        pass

    def _on_combo_changed(self):
        root = self.root_combo.currentText()
        scale = self.scale_combo.currentText()
        self.target_changed.emit(root, scale)
        self.refresh_solver()

    def refresh_solver(self):
        root = self.root_combo.currentText()
        scale = self.scale_combo.currentText()
        span = self.span_combo.currentData() or 3

        self.boxes = ScaleSolver.find_scale_boxes(
            neck=self.neck,
            root_name=root,
            scale_name=scale,
            fret_span=span,
            max_neck_fret=14,
        )

        self._rebuild_position_buttons()
        if self.boxes:
            self._select_box(0)

    def _rebuild_position_buttons(self):
        for btn in self.pos_button_group.buttons():
            self.pos_button_group.removeButton(btn)
            self.positions_layout.removeWidget(btn)
            btn.deleteLater()

        for idx, box in enumerate(self.boxes):
            btn = QPushButton(f"{box.name}")
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    min-height: 32px;
                    font-weight: bold;
                    padding: 4px 10px;
                    font-size: 11px;
                }
                QPushButton:checked {
                    background-color: #0d6efd;
                    color: white;
                }
            """)
            self.positions_layout.addWidget(btn)
            self.pos_button_group.addButton(btn, idx)

        self.positions_layout.addStretch()

    def _on_position_selected(self, idx: int):
        self._select_box(idx)

    def _select_box(self, idx: int):
        if not (0 <= idx < len(self.boxes)):
            return

        self.active_box = self.boxes[idx]
        btn = self.pos_button_group.button(idx)
        if btn:
            btn.setChecked(True)

        self.lbl_active_box_title.setText(
            f"Active Pocket: <b>{self.active_box.name}</b> [{self.active_box.fret_span_str}]"
        )
        self._populate_grid_table()
        self._populate_staircase_table()

        if self.cb_show_box.isChecked():
            self._highlight_active_box()
        else:
            self.clear_highlight_requested.emit()

    def _populate_grid_table(self):
        if not self.active_box:
            return

        num_strings = self.neck.string_count
        self.table_grid.setRowCount(num_strings)

        for row, s_num in enumerate(range(num_strings, 0, -1)):
            notes = self.active_box.notes_by_string.get(s_num, [])
            sp = self.neck.open_tuning[s_num - 1] if s_num <= len(self.neck.open_tuning) else None
            open_str = sp.note_name if sp else ""

            str_item = QTableWidgetItem(f"String {s_num}")
            str_item.setTextAlignment(Qt.AlignCenter)
            self.table_grid.setItem(row, 0, str_item)

            open_item = QTableWidgetItem(open_str)
            open_item.setTextAlignment(Qt.AlignCenter)
            self.table_grid.setItem(row, 1, open_item)

            if notes:
                entries = []
                for n in notes:
                    lev = f"+{'+'.join(n.engaged_levers)}" if n.engaged_levers else "Open"
                    r_star = "★ " if n.is_root else ""
                    entries.append(f"{r_star}F{n.fret} ({lev}) = {n.note_name}")
                notes_text = "   |   ".join(entries)
            else:
                notes_text = "—"

            self.table_grid.setItem(row, 2, QTableWidgetItem(notes_text))

            deg_text = ", ".join(n.degree_label for n in notes) if notes else "—"
            deg_item = QTableWidgetItem(deg_text)
            deg_item.setTextAlignment(Qt.AlignCenter)
            self.table_grid.setItem(row, 3, deg_item)

            btn = QPushButton("▶ Pluck")
            btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
            btn.setEnabled(len(notes) > 0)
            btn.clicked.connect(lambda _, n_list=notes: self._pluck_string_notes(n_list))
            self.table_grid.setCellWidget(row, 4, btn)

    def _populate_staircase_table(self):
        if not self.active_box:
            return

        run = self.active_box.ascending_run
        self.table_staircase.setRowCount(len(run))

        for row, n in enumerate(run):
            lev_str = " + ".join(n.engaged_levers) if n.engaged_levers else "Open (None)"

            step_item = QTableWidgetItem(f"Step {row + 1}")
            step_item.setTextAlignment(Qt.AlignCenter)
            self.table_staircase.setItem(row, 0, step_item)

            deg_prefix = "★ Root (1)" if n.is_root else f"Degree {n.degree_label}"
            deg_item = QTableWidgetItem(deg_prefix)
            deg_item.setTextAlignment(Qt.AlignCenter)
            self.table_staircase.setItem(row, 1, deg_item)

            note_item = QTableWidgetItem(n.note_name)
            note_item.setTextAlignment(Qt.AlignCenter)
            self.table_staircase.setItem(row, 2, note_item)

            str_item = QTableWidgetItem(f"String {n.string_number}")
            str_item.setTextAlignment(Qt.AlignCenter)
            self.table_staircase.setItem(row, 3, str_item)

            fret_item = QTableWidgetItem(f"Fret {n.fret}")
            fret_item.setTextAlignment(Qt.AlignCenter)
            self.table_staircase.setItem(row, 4, fret_item)

            self.table_staircase.setItem(row, 5, QTableWidgetItem(lev_str))

    def _on_toggle_box_shading(self, checked: bool):
        if checked and self.active_box:
            self.box_highlight_requested.emit(self.active_box.min_fret, self.active_box.max_fret)
        else:
            self.clear_highlight_requested.emit()
        self.box_shading_toggled.emit(checked)

    def set_box_shading_state(self, checked: bool):
        """Allows external controls (like the Preferences menu) to sync this checkbox."""
        self.cb_show_box.blockSignals(True)
        self.cb_show_box.setChecked(checked)
        self.cb_show_box.blockSignals(False)
        if checked and self.active_box:
            self.box_highlight_requested.emit(self.active_box.min_fret, self.active_box.max_fret)
        else:
            self.clear_highlight_requested.emit()

    def _highlight_active_box(self):
        if self.active_box:
            self.cb_show_box.blockSignals(True)
            self.cb_show_box.setChecked(True)
            self.cb_show_box.blockSignals(False)
            self.box_highlight_requested.emit(self.active_box.min_fret, self.active_box.max_fret)

    def _pluck_string_notes(self, notes: List[BoxNote]):
        if not notes:
            return
        pitches = [n.midi_note for n in notes]
        self.play_notes_requested.emit(pitches)

    def _play_box_run(self):
        if not self.active_box or not self.active_box.ascending_run:
            return
        pitches = [n.midi_note for n in self.active_box.ascending_run]
        self.play_notes_requested.emit(pitches)

    def select_step(self, idx: int):
        if not self.active_box or not self.active_box.ascending_run:
            return
        run = self.active_box.ascending_run
        if 0 <= idx < len(run):
            self.active_step_idx = idx
            self.table_staircase.selectRow(idx)
            n = run[idx]
            root = self.root_combo.currentText()
            scale = self.scale_combo.currentText()
            banner = f"{root} {scale} — Degree {n.degree_label}: {n.note_name} (Str {n.string_number}, F{n.fret})"
            self.scale_step_applied.emit(n.fret, n.engaged_levers, n.string_number, banner)
            self.play_note_requested.emit(n.midi_note)

    def next_step(self):
        if not self.active_box or not self.active_box.ascending_run:
            return
        nxt = (self.active_step_idx + 1) % len(self.active_box.ascending_run)
        self.select_step(nxt)

    def prev_step(self):
        if not self.active_box or not self.active_box.ascending_run:
            return
        prv = (self.active_step_idx - 1) % len(self.active_box.ascending_run)
        self.select_step(prv)

    def _auto_step_forward(self):
        if not self.active_box or not self.active_box.ascending_run:
            return
        nxt = self.active_step_idx + 1
        if nxt >= len(self.active_box.ascending_run):
            self._toggle_auto_walk()
            return
        self.select_step(nxt)

    def _toggle_auto_walk(self):
        if self.walk_timer.isActive():
            self.walk_timer.stop()
            self.btn_walk.setText("▶ Auto-Walk")
            self.btn_walk.setStyleSheet("font-weight: bold; min-height: 26px; padding: 0 12px;")
        else:
            if not self.active_box or not self.active_box.ascending_run:
                return
            self.active_step_idx = -1
            self.walk_timer.start(520)
            self.btn_walk.setText("⏹ Stop Walk")
            self.btn_walk.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; min-height: 26px; padding: 0 12px;")
            self._auto_step_forward()

    def _on_staircase_cell_clicked(self, row: int, col: int):
        self.select_step(row)

    def closeEvent(self, event):
        self.clear_highlight_requested.emit()
        super().closeEvent(event)