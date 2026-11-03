"""Interactive Progression Sequencer & Tablature View with prebuilt library progressions."""

from typing import List, Optional, Set
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.progression_presets import PROGRESSION_PRESETS, ProgressionPreset, resolve_preset_steps
from core.tab_generator import TabGenerator, TabStep
from core.permutation_engine import FRANKLIN_24_PERMUTATIONS, PermutationEngine


class ProgressionSequencerWidget(QWidget):
    step_activated = Signal(int, list, set)  # fret, levers, grip_strings

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps: List[TabStep] = []
        self.current_step_idx: int = -1
        self.string_count = 10
        self.current_neck_type = "E9"
        self.neck = None  # set by MainWindow; presets are mapped onto its controllers

        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._auto_advance_step)

        self._init_ui()
        self._populate_presets_dropdown()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 1. Progression Library Loader
        lib_box = QGroupBox("Load Practice Progression")
        lib_layout = QVBoxLayout(lib_box)
        lib_layout.setContentsMargins(6, 6, 6, 6)
        lib_layout.setSpacing(4)

        self.combo_presets = QComboBox()
        self.combo_presets.currentIndexChanged.connect(self._on_preset_selected)
        lib_layout.addWidget(self.combo_presets)

        self.lbl_preset_desc = QLabel("<small>Select a preset above to load changes.</small>")
        self.lbl_preset_desc.setStyleSheet("color: #8b92a0;")
        self.lbl_preset_desc.setWordWrap(True)
        lib_layout.addWidget(self.lbl_preset_desc)

        layout.addWidget(lib_box)

        # 2. Transport Controls
        transport_box = QGroupBox("Transport & Capture")
        t_layout = QGridLayout(transport_box)
        t_layout.setContentsMargins(6, 6, 6, 6)
        t_layout.setSpacing(6)

        # Arpeggiate Step with Franklin Permutation
        arp_layout = QHBoxLayout()
        arp_layout.addWidget(QLabel("<b>Permutation:</b>"))

        self.combo_perm_arp = QComboBox()
        for pid, (p_str, name, _) in FRANKLIN_24_PERMUTATIONS.items():
            self.combo_perm_arp.addItem(f"#{pid:02d}: {p_str}", pid)
        self.combo_perm_arp.setCurrentIndex(1)  # #02: T-I-M-T
        arp_layout.addWidget(self.combo_perm_arp, stretch=1)

        self.btn_arpeggiate = QPushButton("⚡ Arpeggiate")
        self.btn_arpeggiate.setToolTip("Deconstructs selected step into a sequential 4-note Franklin picking roll")
        self.btn_arpeggiate.setStyleSheet("font-weight: bold; background-color: #6f42c1; color: white;")
        self.btn_arpeggiate.clicked.connect(self._arpeggiate_selected_step)
        arp_layout.addWidget(self.btn_arpeggiate)

        t_layout.addLayout(arp_layout, 4, 0, 1, 2)

        self.btn_capture = QPushButton("➕ Capture Bar")
        self.btn_capture.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; min-height: 26px;")
        t_layout.addWidget(self.btn_capture, 0, 0, 1, 2)

        self.btn_remove = QPushButton("🗑️ Remove")
        self.btn_remove.clicked.connect(self._remove_current_step)
        t_layout.addWidget(self.btn_remove, 1, 0)

        self.btn_clear = QPushButton("Clear All")
        self.btn_clear.clicked.connect(self._clear_all)
        t_layout.addWidget(self.btn_clear, 1, 1)

        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.clicked.connect(self.prev_step)
        t_layout.addWidget(self.btn_prev, 2, 0)

        self.btn_next = QPushButton("Next ▶")
        self.btn_next.clicked.connect(self.next_step)
        t_layout.addWidget(self.btn_next, 2, 1)

        self.btn_play = QPushButton("▶ Play Loop")
        self.btn_play.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; min-height: 26px;")
        self.btn_play.clicked.connect(self._toggle_playback)
        t_layout.addWidget(self.btn_play, 3, 0)

        tempo_layout = QHBoxLayout()
        tempo_layout.addWidget(QLabel("Tempo:"))
        self.spin_tempo = QSpinBox()
        self.spin_tempo.setRange(1, 5)
        self.spin_tempo.setValue(1)
        self.spin_tempo.setSuffix("s")
        tempo_layout.addWidget(self.spin_tempo)
        t_layout.addLayout(tempo_layout, 3, 1)

        layout.addWidget(transport_box)

        # 3. Steps Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["#", "Chord", "Fret", "Pedals"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.cellClicked.connect(self._on_table_cell_clicked)
        layout.addWidget(self.table, stretch=1)

        # 4. Tab Generation Button
        self.btn_view_tab = QPushButton("🎼 Generate ASCII Tab")
        self.btn_view_tab.setStyleSheet("font-weight: bold; min-height: 28px;")
        self.btn_view_tab.clicked.connect(self._show_tab_dialog)
        layout.addWidget(self.btn_view_tab)

    def _populate_presets_dropdown(self):
        self.combo_presets.blockSignals(True)
        self.combo_presets.clear()
        self.combo_presets.addItem("--- Select Practice Progression ---")
        self.combo_presets.model().item(0).setEnabled(False)

        # Group by Neck Type
        e9_presets = [p for p in PROGRESSION_PRESETS if p.neck_type == "E9"]
        c6_presets = [p for p in PROGRESSION_PRESETS if p.neck_type == "C6"]

        idx = self.combo_presets.count()
        self.combo_presets.addItem("--- E9 Chromatic Progressions ---")
        self.combo_presets.model().item(idx).setEnabled(False)
        for p in e9_presets:
            self.combo_presets.addItem(p.name, p)

        idx = self.combo_presets.count()
        self.combo_presets.addItem("--- C6 Western Swing Progressions ---")
        self.combo_presets.model().item(idx).setEnabled(False)
        for p in c6_presets:
            self.combo_presets.addItem(p.name, p)

        self.combo_presets.blockSignals(False)

    def _on_preset_selected(self):
        preset = self.combo_presets.currentData()
        if not preset or not isinstance(preset, ProgressionPreset):
            return

        self.lbl_preset_desc.setText(f"<small>{preset.description}</small>")
        if preset.neck_type != self.current_neck_type:
            QMessageBox.warning(
                self, "Different Tuning",
                f"'{preset.name}' is written for {preset.neck_type}; the active neck is {self.current_neck_type}.",
            )
            return
        steps = resolve_preset_steps(preset, self.neck) if self.neck is not None else None
        if steps is None:
            QMessageBox.warning(
                self, "Missing Controllers",
                f"The active copedant lacks a pedal or lever that '{preset.name}' needs.",
            )
            return
        self.steps = steps
        self._refresh_table()
        if self.steps:
            self.select_step(0)

    def _arpeggiate_selected_step(self):
        """Replaces or expands the selected step into a 4-step Franklin picking roll."""
        row = self.table.currentRow()
        if row < 0 or row >= len(self.steps):
            QMessageBox.information(self, "Select Step", "Click a step row in the table to arpeggiate.")
            return

        base_step = self.steps[row]
        grip_list = sorted(list(base_step.grip_strings), reverse=True)
        if len(grip_list) < 2:
            QMessageBox.warning(self, "Insufficient Strings", "Capture a grip with at least 2 strings to arpeggiate.")
            return

        perm_id = self.combo_perm_arp.currentData()
        events = PermutationEngine.generate_sequence(perm_id=perm_id, target_strings=grip_list, cycles=1)

        # Replace selected step with the 4 arpeggiated sub-steps
        self.steps.pop(row)
        for i, ev in enumerate(events):
            sub_step = TabStep(
                fret=base_step.fret,
                engaged_levers=list(base_step.engaged_levers),
                grip_strings={ev.string_number},
                chord_label=base_step.chord_label if i == 0 else "",
                pick_finger=ev.finger,
            )
            self.steps.insert(row + i, sub_step)

        self._refresh_table()
        self.select_step(row)

    def set_neck_type(self, neck_type_str: str):
        self.current_neck_type = neck_type_str

    def set_neck(self, neck):
        self.neck = neck
        self.string_count = neck.string_count

    def capture_step(self, fret: int, levers: Set[str], grip: Set[int], chord_label: str = ""):
        step = TabStep(
            fret=fret,
            engaged_levers=sorted(list(levers)),
            grip_strings=set(grip),
            chord_label=chord_label,
        )
        self.steps.append(step)
        self._refresh_table()
        self.select_step(len(self.steps) - 1)

    def _refresh_table(self):
        self.table.setRowCount(len(self.steps))
        for idx, s in enumerate(self.steps):
            lev_str = " + ".join(s.engaged_levers) if s.engaged_levers else "None"
            pick_tag = f" [{s.pick_finger}]" if s.pick_finger else ""
            self.table.setItem(idx, 0, QTableWidgetItem(str(idx + 1)))
            self.table.setItem(idx, 1, QTableWidgetItem(f"{s.chord_label or 'Grip'}{pick_tag}"))
            self.table.setItem(idx, 2, QTableWidgetItem(f"F{s.fret}"))
            self.table.setItem(idx, 3, QTableWidgetItem(lev_str))

    def select_step(self, idx: int):
        if 0 <= idx < len(self.steps):
            self.current_step_idx = idx
            self.table.selectRow(idx)
            step = self.steps[idx]
            self.step_activated.emit(step.fret, step.engaged_levers, step.grip_strings)

    def next_step(self):
        if not self.steps:
            return
        nxt = (self.current_step_idx + 1) % len(self.steps)
        self.select_step(nxt)

    def prev_step(self):
        if not self.steps:
            return
        prv = (self.current_step_idx - 1) % len(self.steps)
        self.select_step(prv)

    def _auto_advance_step(self):
        self.next_step()

    def _toggle_playback(self):
        if self.play_timer.isActive():
            self.play_timer.stop()
            self.btn_play.setText("▶ Play Loop")
            self.btn_play.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; min-height: 26px;")
        else:
            if not self.steps:
                return
            interval_ms = self.spin_tempo.value() * 1000
            self.play_timer.start(interval_ms)
            self.btn_play.setText("⏹ Stop")
            self.btn_play.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; min-height: 26px;")

    def _remove_current_step(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.steps):
            self.steps.pop(row)
            self._refresh_table()
            if self.steps:
                self.select_step(min(row, len(self.steps) - 1))
            else:
                self.current_step_idx = -1

    def _clear_all(self):
        if self.play_timer.isActive():
            self._toggle_playback()
        self.steps.clear()
        self.current_step_idx = -1
        self._refresh_table()

    def _on_table_cell_clicked(self, row: int, col: int):
        self.select_step(row)

    def _show_tab_dialog(self):
        if not self.steps:
            QMessageBox.information(self, "No Steps", "Load or capture steps in the progression to generate tablature.")
            return

        ascii_text = TabGenerator.generate_ascii_tab(self.string_count, self.steps)

        dlg = QDialog(self)
        dlg.setWindowTitle("Pedal Steel Practice Tablature")
        dlg.resize(680, 420)
        vbox = QVBoxLayout(dlg)

        edit = QTextEdit()
        edit.setFontFamily("Consolas")
        edit.setFontPointSize(10)
        edit.setReadOnly(True)
        edit.setPlainText(ascii_text)
        vbox.addWidget(edit)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        vbox.addWidget(close_btn)
        dlg.exec()