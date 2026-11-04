"""Floating tool window for pedal steel scale boxes and position pockets across strings."""

import random
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
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import Neck
from core.scale_chords import ScaleChord, chords_in_scale
from core.scale_engine import BoxNote, ScaleBox, ScaleSolver
from core.stances import controller_display_names, describe_controllers
from core.theory import NOTE_TO_SEMITONE, SCALE_FORMULAS, note_names, respell, spell_pc
from ui.fretboard_canvas import degree_color


SEGMENT_STYLE = """
    QPushButton { padding: 3px 10px; font-weight: bold; }
    QPushButton:checked { background-color: #0d6efd; color: white; border-color: #0d6efd; }
"""


def _clear_layout(layout) -> None:
    """Removes and deletes every widget in a layout. Widgets are hidden first: deleteLater only runs
    on the next event-loop pass, and a removed but visible widget is drawn at its default geometry."""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.deleteLater()


class ScaleFinderWidget(QWidget):
    scale_step_applied = Signal(int, list, int, str)   # fret, levers, string_number, banner
    box_highlight_requested = Signal(int, int)          # min_fret, max_fret
    clear_highlight_requested = Signal()                # clear box shading
    box_shading_toggled = Signal(bool) # Emits when the user toggles the preference
    play_note_requested = Signal(int)                   # midi_note
    target_changed = Signal(str, str)                   # root, scale_name
    # Scale map on the fretboard (E-30)
    overlay_changed = Signal(list, list)                # all BoxNotes in the range, ascending run
    overlay_cleared = Signal()
    overlay_step_changed = Signal(int)                  # run index of the current step (-1 = none)
    overlay_label_mode_changed = Signal(str)            # "step", "degree" or "note"
    # Learning aids (E-30 phase 3)
    ghost_changed = Signal(list)                        # faint whole-neck notes outside the range
    overlay_loop_changed = Signal(int, int)             # looped run indices (-1, -1 = no loop)
    overlay_quiz_changed = Signal(bool)                 # blank the circles for the quiz
    overlay_reveal_requested = Signal(list)             # notes to show normally during the quiz
    overlay_wrong_marked = Signal(object)               # BoxNote marked wrong (None = clear)
    # Scale <-> chord link (E-31)
    overlay_chord_changed = Signal(list)                # pitch classes to ring ([] = none)
    find_chord_requested = Signal(str, str, int, int)   # root, chord type, min fret, max fret

    QUIZ_OFF, QUIZ_NAME, QUIZ_EAR = "off", "name", "ear"
    QUIZ_NEXT_DELAY_MS = 1100

    SUGGESTION_SPAN = 4  # fret width of the suggested positions

    def __init__(
        self,
        neck: Neck,
        current_pocket: Set[int] = None,
        show_box_initial: bool = True,
        overlay_label_initial: str = "step",
        parent=None,
    ):
        super().__init__(parent)
        self.neck = neck
        self.show_box_initial = show_box_initial
        self.overlay_label_initial = overlay_label_initial
        self.boxes: List[ScaleBox] = []          # suggested positions
        self.active_box: Optional[ScaleBox] = None  # the user's fret range
        self.active_step_idx: int = -1
        self.run: List[BoxNote] = []             # active_box's run in the chosen order
        self.names: Dict[str, str] = controller_display_names(neck)
        self._overlay_notes: List[BoxNote] = []   # every circle in the range (what the canvas draws)
        self.ghost_notes: List[BoxNote] = []

        self.quiz_mode: str = self.QUIZ_OFF
        self.quiz_target: Optional[BoxNote] = None
        self.quiz_correct = self.quiz_attempts = self.quiz_streak = 0
        self._quiz_waiting = False
        self._rng = random.Random()

        self.walk_timer = QTimer(self)
        self.walk_timer.timeout.connect(self._auto_step_forward)
        self.quiz_timer = QTimer(self)
        self.quiz_timer.setSingleShot(True)
        self.quiz_timer.timeout.connect(self._next_question)
        self.play_timer = QTimer(self)                 # Play Run, one note per beat (stoppable)
        self.play_timer.timeout.connect(self._play_tick)
        self._play_indices: List[int] = []
        self.scale_chords: List[ScaleChord] = []
        self.selected_chord: Optional[ScaleChord] = None

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
        self.root_combo.addItems(note_names())
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
        top_bar.addWidget(QLabel("<b>Frets:</b>"))
        self.spin_from = QSpinBox()
        self.spin_from.setRange(0, 24)
        self.spin_from.setValue(3)
        self.spin_from.setToolTip("Lowest fret of the range")
        top_bar.addWidget(self.spin_from)
        top_bar.addWidget(QLabel("to"))
        self.spin_to = QSpinBox()
        self.spin_to.setRange(0, 24)
        self.spin_to.setValue(6)
        self.spin_to.setToolTip("Highest fret of the range")
        top_bar.addWidget(self.spin_to)
        self.spin_from.valueChanged.connect(self._on_from_changed)
        self.spin_to.valueChanged.connect(self._on_to_changed)

        top_bar.addSpacing(10)
        top_bar.addWidget(QLabel("<b>Circles show:</b>"))
        self.label_group = QButtonGroup(self)
        self.label_group.setExclusive(True)
        seg = QHBoxLayout()
        seg.setSpacing(0)
        for mode, text in (("step", "Step #"), ("degree", "Degree"), ("note", "Note")):
            rb = QPushButton(text)
            rb.setCheckable(True)
            rb.setStyleSheet(SEGMENT_STYLE)
            rb.setProperty("mode", mode)
            rb.setChecked(mode == self.overlay_label_initial)
            self.label_group.addButton(rb)
            seg.addWidget(rb)
        top_bar.addLayout(seg)
        if self.label_group.checkedButton() is None:
            self.label_group.buttons()[0].setChecked(True)
        self.label_group.buttonToggled.connect(self._on_label_mode_toggled)

        top_bar.addStretch()

        self.btn_play_run = QPushButton("▶ Play Run")
        self.btn_play_run.setStyleSheet(
            "background-color: #28a745; color: white; font-weight: bold; min-height: 28px; padding: 0 14px;"
        )
        self.btn_play_run.setToolTip("Plays the run (or the loop) at the Tempo; click again to stop")
        self.btn_play_run.clicked.connect(self._play_box_run)
        top_bar.addWidget(self.btn_play_run)

        layout.addLayout(top_bar)

        legend = QLabel(
            "On the fretboard: numbers = step order · colour = scale degree (red = root) · "
            "orange dot = needs a pedal or lever · dashed = not a step (same pitch elsewhere) · "
            "click a circle to jump to that step, hover for details."
        )
        legend.setWordWrap(True)
        legend.setStyleSheet("font-size: 11px; color: gray;")
        layout.addWidget(legend)

        degree_row = QHBoxLayout()
        degree_row.addWidget(QLabel("<b>Degrees:</b>"))
        self.degree_legend_layout = QHBoxLayout()
        self.degree_legend_layout.setSpacing(4)
        degree_row.addLayout(self.degree_legend_layout)
        degree_row.addStretch()
        self.cb_whole_neck = QCheckBox("Whole neck (faint)")
        self.cb_whole_neck.setToolTip("Also draw the scale faintly outside the fret range, to see how positions connect")
        self.cb_whole_neck.toggled.connect(self._on_whole_neck_toggled)
        degree_row.addWidget(self.cb_whole_neck)
        layout.addLayout(degree_row)

        chords_group = QGroupBox("Chords in this scale (click to ring its tones on the fretboard)")
        cg = QVBoxLayout(chords_group)
        cg.setContentsMargins(8, 4, 8, 6)
        cg.setSpacing(4)
        self.chord_group = QButtonGroup(self)
        self.chord_group.setExclusive(False)  # exclusive by hand, so a chord can be clicked off again
        self.chord_group.buttonClicked.connect(self._on_chord_clicked)
        self.triad_layout = QHBoxLayout()
        self.seventh_layout = QHBoxLayout()
        for lay, title in ((self.triad_layout, "Triads:"), (self.seventh_layout, "7ths:")):
            row = QHBoxLayout()
            lbl = QLabel(f"<b>{title}</b>")
            lbl.setFixedWidth(52)
            row.addWidget(lbl)
            lay.setSpacing(4)
            row.addLayout(lay)
            row.addStretch()
            cg.addLayout(row)
        find_row = QHBoxLayout()
        self.lbl_chord = QLabel("")
        find_row.addWidget(self.lbl_chord)
        find_row.addStretch()
        self.btn_find_chord = QPushButton("🔍 Find voicings in these frets")
        self.btn_find_chord.setToolTip("Open the Chord Atlas (Find mode) for the selected chord, limited to the fret range")
        self.btn_find_chord.setEnabled(False)
        self.btn_find_chord.clicked.connect(self._request_find_chord)
        find_row.addWidget(self.btn_find_chord)
        cg.addLayout(find_row)
        layout.addWidget(chords_group)

        # 2. Suggested positions ribbon
        positions_group = QGroupBox("Suggested positions (click to load the fret range)")
        self.positions_layout = QHBoxLayout(positions_group)
        self.positions_layout.setContentsMargins(8, 6, 8, 6)
        self.positions_layout.setSpacing(8)
        self.pos_button_group = QButtonGroup(self)
        self.pos_button_group.idClicked.connect(self._on_position_selected)
        layout.addWidget(positions_group)

        # 3. Run options and transport
        transport_bar = QHBoxLayout()
        transport_bar.addWidget(QLabel("<b>Order:</b>"))
        self.direction_combo = QComboBox()
        self.direction_combo.addItem("Up", ScaleSolver.RUN_UP)
        self.direction_combo.addItem("Down", ScaleSolver.RUN_DOWN)
        self.direction_combo.addItem("Up & back", ScaleSolver.RUN_UP_DOWN)
        self.direction_combo.currentIndexChanged.connect(self._rebuild_run)
        transport_bar.addWidget(self.direction_combo)

        self.cb_root_to_root = QCheckBox("Root to root")
        self.cb_root_to_root.setToolTip("Start and end the run on the lowest and highest root in the range")
        self.cb_root_to_root.toggled.connect(self._rebuild_run)
        transport_bar.addWidget(self.cb_root_to_root)

        transport_bar.addSpacing(12)
        transport_bar.addWidget(QLabel("<b>Tempo:</b>"))
        self.spin_tempo = QSpinBox()
        self.spin_tempo.setRange(30, 240)
        self.spin_tempo.setValue(115)
        self.spin_tempo.setSuffix(" BPM")
        self.spin_tempo.setToolTip("Auto-walk speed (one step per beat)")
        self.spin_tempo.valueChanged.connect(self._on_tempo_changed)
        transport_bar.addWidget(self.spin_tempo)

        transport_bar.addSpacing(12)
        self.cb_show_box = QCheckBox("Shade range")
        self.cb_show_box.setToolTip("Shade the chosen frets on the fretboard")
        self.cb_show_box.setChecked(self.show_box_initial)
        self.cb_show_box.toggled.connect(self._on_toggle_box_shading)
        transport_bar.addWidget(self.cb_show_box)

        transport_bar.addStretch()

        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.clicked.connect(self.prev_step)
        transport_bar.addWidget(self.btn_prev)

        self.btn_next = QPushButton("Next ▶")
        self.btn_next.clicked.connect(self.next_step)
        transport_bar.addWidget(self.btn_next)

        self.btn_walk = QPushButton("▶ Auto-Walk")
        self.btn_walk.setStyleSheet("font-weight: bold; min-height: 26px; padding: 0 12px;")
        self.btn_walk.clicked.connect(self._toggle_auto_walk)
        transport_bar.addWidget(self.btn_walk)

        layout.addLayout(transport_bar)

        self.lbl_active_box_title = QLabel("")
        self.lbl_active_box_title.setStyleSheet("font-size: 12px; color: #0d6efd;")
        layout.addWidget(self.lbl_active_box_title)

        practice = QGroupBox("Practice")
        practice_layout = QVBoxLayout(practice)
        practice_layout.setContentsMargins(8, 4, 8, 6)
        row = QHBoxLayout()
        self.cb_loop = QCheckBox("Loop steps")
        self.cb_loop.setToolTip("Prev/Next, Auto-Walk, Play Run and the quiz stay inside these steps")
        self.cb_loop.toggled.connect(self._on_loop_changed)
        row.addWidget(self.cb_loop)
        self.spin_loop_from = QSpinBox()
        self.spin_loop_from.setRange(1, 1)
        self.spin_loop_to = QSpinBox()
        self.spin_loop_to.setRange(1, 1)
        self.spin_loop_from.valueChanged.connect(self._on_loop_from_changed)
        self.spin_loop_to.valueChanged.connect(self._on_loop_to_changed)
        row.addWidget(self.spin_loop_from)
        row.addWidget(QLabel("to"))
        row.addWidget(self.spin_loop_to)

        row.addSpacing(16)
        row.addWidget(QLabel("<b>Quiz:</b>"))
        self.quiz_combo = QComboBox()
        self.quiz_combo.addItem("Off", self.QUIZ_OFF)
        self.quiz_combo.addItem("Find the degree", self.QUIZ_NAME)
        self.quiz_combo.addItem("Find by ear", self.QUIZ_EAR)
        self.quiz_combo.setToolTip(
            "Find the degree: click any circle with the named degree.\n"
            "Find by ear: listen, then click a circle with that exact pitch."
        )
        self.quiz_combo.currentIndexChanged.connect(self._on_quiz_mode_changed)
        row.addWidget(self.quiz_combo)
        self.btn_replay = QPushButton("🔊 Replay")
        self.btn_replay.clicked.connect(self._replay_target)
        row.addWidget(self.btn_replay)
        self.btn_skip = QPushButton("Skip")
        self.btn_skip.clicked.connect(self._skip_question)
        row.addWidget(self.btn_skip)
        row.addStretch()
        self.lbl_score = QLabel("")
        self.lbl_score.setStyleSheet("font-weight: bold;")
        row.addWidget(self.lbl_score)
        practice_layout.addLayout(row)
        self.lbl_quiz_prompt = QLabel("")
        self.lbl_quiz_prompt.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.lbl_quiz_prompt.setVisible(False)
        practice_layout.addWidget(self.lbl_quiz_prompt)
        layout.addWidget(practice)
        self.btn_replay.setVisible(False)
        self.btn_skip.setVisible(False)

        # 4. Step list, kept in sync with the fretboard circles
        self.table_staircase = QTableWidget()
        self.table_staircase.setColumnCount(7)
        self.table_staircase.setHorizontalHeaderLabels(
            ["#", "Degree", "Note", "String", "Fret", "Pedals / Levers", "Change from previous step"]
        )
        header = self.table_staircase.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        self.table_staircase.verticalHeader().setVisible(False)
        self.table_staircase.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_staircase.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_staircase.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_staircase.cellClicked.connect(self._on_staircase_cell_clicked)
        layout.addWidget(self.table_staircase, stretch=1)

    def update_neck(self, neck: Neck):
        self.neck = neck
        self.names = controller_display_names(neck)
        self.refresh_solver()

    def set_active_pocket(self, pocket: Set[int]):
        pass

    def _on_combo_changed(self):
        self.refresh_solver()  # publishes the new target to the fretboard while shown

    def refresh_solver(self):
        """Recomputes the suggested positions and the scale inside the chosen fret range."""
        root = self.root_combo.currentText()
        scale = self.scale_combo.currentText()

        self.boxes = ScaleSolver.find_scale_boxes(
            neck=self.neck,
            root_name=root,
            scale_name=scale,
            fret_span=self.SUGGESTION_SPAN,
            max_neck_fret=14,
        )
        self._rebuild_position_buttons()
        self._refresh_range()
        self._rebuild_degree_legend()
        self._rebuild_chord_buttons()

    def set_fret_range(self, min_fret: int, max_fret: int):
        lo, hi = sorted((int(min_fret), int(max_fret)))
        for spin, val in ((self.spin_from, lo), (self.spin_to, hi)):
            spin.blockSignals(True)
            spin.setValue(val)
            spin.blockSignals(False)
        self._refresh_range()

    def _on_from_changed(self, value: int):
        if value > self.spin_to.value():
            self.spin_to.blockSignals(True)
            self.spin_to.setValue(value)
            self.spin_to.blockSignals(False)
        self._refresh_range()

    def _on_to_changed(self, value: int):
        if value < self.spin_from.value():
            self.spin_from.blockSignals(True)
            self.spin_from.setValue(value)
            self.spin_from.blockSignals(False)
        self._refresh_range()

    def _refresh_range(self):
        lo, hi = self.spin_from.value(), self.spin_to.value()
        self.active_box = ScaleSolver.find_scale_in_range(
            self.neck, self.root_combo.currentText(), self.scale_combo.currentText(), lo, hi
        )
        self._sync_position_buttons()
        self._compute_ghost()
        self._rebuild_run()

    def _rebuild_run(self):
        """Applies the order options to the range's playable run, then refreshes the list and fretboard."""
        if self.walk_timer.isActive():
            self._toggle_auto_walk()
        self.stop_play_run()
        self.active_step_idx = -1
        if self.active_box:
            self.run = ScaleSolver.build_run(
                self.active_box, self.direction_combo.currentData(), self.cb_root_to_root.isChecked()
            )
        else:
            self.run = []
        n = max(1, len(self.run))
        for spin, val in ((self.spin_loop_from, 1), (self.spin_loop_to, n)):
            spin.blockSignals(True)
            spin.setRange(1, n)
            spin.setValue(val)
            spin.blockSignals(False)
        self._update_status()
        self._populate_staircase_table()
        self._publish_to_fretboard()
        if self.quiz_mode != self.QUIZ_OFF:
            self._next_question()

    def _update_status(self):
        if not self.active_box:
            self.lbl_active_box_title.setText("")
            return
        lo, hi = self.active_box.min_fret, self.active_box.max_fret
        degrees = ", ".join(self.active_box.covered_degrees) or "—"
        text = f"Frets <b>{lo}–{hi}</b>: {len(self.run)} steps · degrees {degrees}"
        if 0 <= self.active_step_idx < len(self.run):
            n = self.run[self.active_step_idx]
            text += (
                f" &nbsp;|&nbsp; <b>Step {self.active_step_idx + 1}</b>: degree {n.degree_label} · {n.note_name} · "
                f"string {n.string_number}, fret {n.fret} · {describe_controllers(n.engaged_levers, self.names)}"
            )
        self.lbl_active_box_title.setText(text)

    def _publish_to_fretboard(self):
        """Sends scale, overlay and shading to the fretboard, but only while this window is shown."""
        if not self.isVisible():
            return
        self.target_changed.emit(self.root_combo.currentText(), self.scale_combo.currentText())
        if self.active_box:
            notes = [n for s in sorted(self.active_box.notes_by_string) for n in self.active_box.notes_by_string[s]]
            self._overlay_notes = notes
            self.overlay_changed.emit(notes, list(self.run))
            self.overlay_step_changed.emit(self.active_step_idx)
            self._publish_loop()
            self.ghost_changed.emit(list(self.ghost_notes))
            self.overlay_chord_changed.emit(sorted(self.selected_chord.pcs) if self.selected_chord else [])
            if self.quiz_mode != self.QUIZ_OFF:
                self.overlay_quiz_changed.emit(True)
        else:
            self._overlay_notes = []
            self.overlay_cleared.emit()
        if self.cb_show_box.isChecked() and self.active_box:
            self.box_highlight_requested.emit(self.active_box.min_fret, self.active_box.max_fret)
        else:
            self.clear_highlight_requested.emit()

    def overlay_label_mode(self) -> str:
        btn = self.label_group.checkedButton()
        return btn.property("mode") if btn else "step"

    def _on_label_mode_toggled(self, button, checked: bool):
        if checked:
            self.overlay_label_mode_changed.emit(button.property("mode"))

    def showEvent(self, event):
        super().showEvent(event)
        self._publish_to_fretboard()

    def hideEvent(self, event):
        if self.walk_timer.isActive():
            self._toggle_auto_walk()
        self.stop_play_run()
        if self.quiz_mode != self.QUIZ_OFF:
            self.quiz_combo.setCurrentIndex(0)  # ends the quiz
        self.overlay_cleared.emit()
        self.clear_highlight_requested.emit()
        super().hideEvent(event)

    def _rebuild_position_buttons(self):
        for btn in self.pos_button_group.buttons():
            self.pos_button_group.removeButton(btn)
        _clear_layout(self.positions_layout)  # buttons and the old trailing stretch

        for idx, box in enumerate(self.boxes):
            roots = f"roots on str {', '.join(map(str, box.root_strings))}" if box.root_strings else "no root"
            btn = QPushButton(f"Frets {box.min_fret}–{box.max_fret}\n{roots}")
            btn.setToolTip(box.name)
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
        if 0 <= idx < len(self.boxes):
            self.set_fret_range(self.boxes[idx].min_fret, self.boxes[idx].max_fret)

    def _sync_position_buttons(self):
        """Checks the suggestion whose frets equal the current range (none if the range is custom)."""
        lo, hi = self.spin_from.value(), self.spin_to.value()
        self.pos_button_group.setExclusive(False)
        for idx, box in enumerate(self.boxes):
            btn = self.pos_button_group.button(idx)
            if btn:
                btn.setChecked((box.min_fret, box.max_fret) == (lo, hi))
        self.pos_button_group.setExclusive(True)

    def describe_change(self, prev: Optional[BoxNote], cur: BoxNote) -> str:
        """What the player does to get from prev to cur: bar move, string, pedals/levers."""
        if prev is None:
            return "Start"
        parts = []
        if cur.fret != prev.fret:
            parts.append(f"bar {prev.fret} → {cur.fret}")
        if cur.string_number != prev.string_number:
            parts.append(f"string {prev.string_number} → {cur.string_number}")
        else:
            parts.append("same string")
        before, after = set(prev.engaged_levers), set(cur.engaged_levers)
        for cid in sorted(after - before):
            parts.append(f"press {describe_controllers([cid], self.names)}")
        for cid in sorted(before - after):
            parts.append(f"release {describe_controllers([cid], self.names)}")
        return " · ".join(parts)

    def _populate_staircase_table(self):
        run = self.run
        self.table_staircase.setRowCount(len(run))
        prev = None
        for row, n in enumerate(run):
            cells = [
                str(row + 1),
                f"★ {n.degree_label}" if n.is_root else n.degree_label,
                n.note_name,
                str(n.string_number),
                str(n.fret),
                describe_controllers(n.engaged_levers, self.names),
                self.describe_change(prev, n),
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col < 5:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table_staircase.setItem(row, col, item)
            prev = n

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

    def _play_box_run(self):
        """Toggles: plays the run (or loop) one note per beat, lighting each circle; stops if playing."""
        if self.play_timer.isActive():
            self.stop_play_run()
            return
        if not self.run:
            return
        if self.walk_timer.isActive():
            self._toggle_auto_walk()
        lo, hi = self.loop_bounds()
        self._play_indices = list(range(lo, hi + 1))
        self.btn_play_run.setText("⏹ Stop Run")
        self.btn_play_run.setStyleSheet(
            "background-color: #dc3545; color: white; font-weight: bold; min-height: 28px; padding: 0 14px;"
        )
        self.play_timer.start(self._walk_interval_ms())
        self._play_tick()

    def _play_tick(self):
        if not self._play_indices:
            self.stop_play_run()
            return
        idx = self._play_indices.pop(0)
        if 0 <= idx < len(self.run):
            if self.isVisible():
                self.overlay_step_changed.emit(idx)
            self.play_note_requested.emit(self.run[idx].midi_note)

    def stop_play_run(self):
        was_playing = self.play_timer.isActive() or bool(self._play_indices)
        self.play_timer.stop()
        self._play_indices = []
        self.btn_play_run.setText("▶ Play Run")
        self.btn_play_run.setStyleSheet(
            "background-color: #28a745; color: white; font-weight: bold; min-height: 28px; padding: 0 14px;"
        )
        if was_playing and self.isVisible():
            self.overlay_step_changed.emit(self.active_step_idx)  # back to the stepped note

    @property
    def is_playing_run(self) -> bool:
        return self.play_timer.isActive()

    # ----- Chords in the scale (E-31) -----

    def set_target(self, root: str, scale_name: str):
        """Sets root and scale (any spelling) with a single refresh."""
        for combo, value in ((self.root_combo, respell(root)), (self.scale_combo, scale_name)):
            if combo.findText(value) >= 0:
                combo.blockSignals(True)
                combo.setCurrentText(value)
                combo.blockSignals(False)
        self.refresh_solver()

    def _rebuild_chord_buttons(self):
        for btn in self.chord_group.buttons():
            self.chord_group.removeButton(btn)
        _clear_layout(self.triad_layout)
        _clear_layout(self.seventh_layout)
        previous = self.selected_chord
        self.selected_chord = None
        self.scale_chords = chords_in_scale(self.root_combo.currentText(), self.scale_combo.currentText())
        for idx, ch in enumerate(self.scale_chords):
            btn = QPushButton(f"{ch.numeral}  {ch.symbol}")
            btn.setCheckable(True)
            btn.setStyleSheet(SEGMENT_STYLE + "QPushButton { padding: 2px 8px; font-size: 11px; }")
            btn.setToolTip(f"{ch.symbol} ({ch.chord_type}): {self._chord_tones(ch)}")
            self.chord_group.addButton(btn, idx)
            (self.seventh_layout if ch.is_seventh else self.triad_layout).addWidget(btn)
        if previous is not None:  # keep the same chord selected if the new scale still has it
            self.select_chord(previous.root_name, previous.chord_type, publish=False)
        self._update_chord_label()
        self._publish_chord()

    def select_chord(self, root: str, chord_type: Optional[str], publish: bool = True) -> bool:
        """Selects the scale chord root+chord_type (None clears). False if the scale has no such chord."""
        pc = NOTE_TO_SEMITONE.get(root) if root else None
        found = None
        for idx, ch in enumerate(self.scale_chords):
            hit = chord_type is not None and ch.root_pc == pc and ch.chord_type == chord_type
            btn = self.chord_group.button(idx)
            if btn:
                btn.setChecked(hit)
            if hit:
                found = ch
        self.selected_chord = found
        self._update_chord_label()
        if publish:
            self._publish_chord()
        return found is not None or chord_type is None

    def _on_chord_clicked(self, button):
        idx = self.chord_group.id(button)
        ch = self.scale_chords[idx] if 0 <= idx < len(self.scale_chords) else None
        if ch is None or not button.isChecked():
            self.select_chord("", None)
        else:
            self.select_chord(ch.root_name, ch.chord_type)

    def _update_chord_label(self):
        ch = self.selected_chord
        self.btn_find_chord.setEnabled(ch is not None)
        if ch is None:
            self.lbl_chord.setText("")
            return
        self.lbl_chord.setText(
            f"<b>{ch.numeral} {ch.symbol}</b>: {self._chord_tones(ch)} — ringed in gold on the fretboard"
        )

    @staticmethod
    def _chord_tones(ch: ScaleChord) -> str:
        return " ".join(spell_pc(pc) for pc in sorted(ch.pcs, key=lambda pc: (pc - ch.root_pc) % 12))

    def _publish_chord(self):
        if self.isVisible():
            self.overlay_chord_changed.emit(sorted(self.selected_chord.pcs) if self.selected_chord else [])

    def _request_find_chord(self):
        ch = self.selected_chord
        if ch is not None:
            self.find_chord_requested.emit(ch.root_name, ch.chord_type, self.spin_from.value(), self.spin_to.value())

    # ----- Degree legend and whole neck (E-30 phase 3) -----

    def _rebuild_degree_legend(self):
        _clear_layout(self.degree_legend_layout)
        formula = SCALE_FORMULAS.get(self.scale_combo.currentText(), {})
        notes = self._overlay_notes or [n for ns in (self.active_box.notes_by_string.values() if self.active_box else []) for n in ns]
        name_of = {}
        for n in notes:
            name_of.setdefault(n.degree_label, n.note_name.rstrip("-0123456789"))
        for semis in sorted(formula):
            deg = formula[semis]
            c = degree_color(deg)
            text_c = "black" if c.lightness() > 150 else "white"
            chip = QLabel(f" {deg} {name_of.get(deg, '')} ".replace("  ", " "))
            chip.setStyleSheet(
                f"background-color: {c.name()}; color: {text_c}; border-radius: 8px; "
                "padding: 1px 6px; font-weight: bold; font-size: 11px;"
            )
            chip.setToolTip(f"Degree {deg}")
            self.degree_legend_layout.addWidget(chip)

    def _compute_ghost(self):
        self.ghost_notes = []
        if not self.cb_whole_neck.isChecked() or not self.active_box:
            return
        whole = ScaleSolver.find_scale_in_range(
            self.neck, self.root_combo.currentText(), self.scale_combo.currentText(), 0, 24
        )
        if whole:
            lo, hi = self.active_box.min_fret, self.active_box.max_fret
            self.ghost_notes = [
                n for ns in whole.notes_by_string.values() for n in ns if not (lo <= n.fret <= hi)
            ]

    def _on_whole_neck_toggled(self, checked: bool):
        self._compute_ghost()
        if self.isVisible():
            self.ghost_changed.emit(list(self.ghost_notes))

    # ----- Loop (E-30 phase 3) -----

    def loop_bounds(self):
        """(first, last) run indices the transport and quiz use: the loop, or the whole run."""
        if not self.run:
            return 0, -1
        if not self.cb_loop.isChecked():
            return 0, len(self.run) - 1
        lo = min(self.spin_loop_from.value(), len(self.run)) - 1
        hi = min(self.spin_loop_to.value(), len(self.run)) - 1
        return lo, max(lo, hi)

    def set_loop(self, first_step: int, last_step: int):
        """Loops steps first_step..last_step (1-based, as shown in the list)."""
        for spin, val in ((self.spin_loop_from, first_step), (self.spin_loop_to, last_step)):
            spin.blockSignals(True)
            spin.setValue(val)
            spin.blockSignals(False)
        if self.cb_loop.isChecked():
            self._on_loop_changed()
        else:
            self.cb_loop.setChecked(True)

    def _on_loop_from_changed(self, value: int):
        if value > self.spin_loop_to.value():
            self.spin_loop_to.blockSignals(True)
            self.spin_loop_to.setValue(value)
            self.spin_loop_to.blockSignals(False)
        self._on_loop_changed()

    def _on_loop_to_changed(self, value: int):
        if value < self.spin_loop_from.value():
            self.spin_loop_from.blockSignals(True)
            self.spin_loop_from.setValue(value)
            self.spin_loop_from.blockSignals(False)
        self._on_loop_changed()

    def _on_loop_changed(self, *_):
        lo, hi = self.loop_bounds()
        for row in range(self.table_staircase.rowCount()):
            inside = lo <= row <= hi
            for col in range(self.table_staircase.columnCount()):
                item = self.table_staircase.item(row, col)
                if item:
                    item.setForeground(self.palette().text() if inside else self.palette().placeholderText())
        self._publish_loop()
        if self.quiz_mode != self.QUIZ_OFF:
            self._next_question()

    def _publish_loop(self):
        if not self.isVisible():
            return
        if self.cb_loop.isChecked() and self.run:
            lo, hi = self.loop_bounds()
            self.overlay_loop_changed.emit(lo, hi)
        else:
            self.overlay_loop_changed.emit(-1, -1)

    # ----- Quiz (E-30 phase 3) -----

    def _on_quiz_mode_changed(self, *_):
        mode = self.quiz_combo.currentData() or self.QUIZ_OFF
        self.quiz_mode = mode
        if self.walk_timer.isActive():
            self._toggle_auto_walk()
        self.stop_play_run()
        self.quiz_timer.stop()
        self._quiz_waiting = False
        self.quiz_target = None
        self.quiz_correct = self.quiz_attempts = self.quiz_streak = 0
        on = mode != self.QUIZ_OFF
        # The list and status line give the answers away, so they are hidden while quizzing.
        self.table_staircase.setVisible(not on)
        self.lbl_active_box_title.setVisible(not on)
        for w in (self.btn_prev, self.btn_next, self.btn_walk):
            w.setEnabled(not on)
        for w in (self.btn_replay, self.btn_skip, self.lbl_quiz_prompt):
            w.setVisible(on)
        if self.isVisible():
            self.overlay_quiz_changed.emit(on)
        self._update_score()
        if on:
            self._next_question()
        else:
            self.lbl_quiz_prompt.setText("")

    def _quiz_pool(self) -> List[BoxNote]:
        lo, hi = self.loop_bounds()
        pool, seen = [], set()
        for n in self.run[lo:hi + 1]:
            if id(n) not in seen:
                seen.add(id(n))
                pool.append(n)
        return pool

    def _matches_target(self, note: BoxNote) -> bool:
        t = self.quiz_target
        if t is None:
            return False
        if self.quiz_mode == self.QUIZ_EAR:
            return note.midi_note == t.midi_note
        return note.degree_label == t.degree_label

    def _next_question(self):
        self._quiz_waiting = False
        if self.quiz_mode == self.QUIZ_OFF:
            return
        pool = self._quiz_pool()
        if not pool:
            self.quiz_target = None
            self.lbl_quiz_prompt.setText("No scale notes in this range.")
            return
        choices = [n for n in pool if n is not self.quiz_target] or pool
        if self.quiz_mode == self.QUIZ_NAME and self.quiz_target is not None:
            # Prefer a different degree, not just a different octave of the same one.
            other = [n for n in choices if n.degree_label != self.quiz_target.degree_label]
            choices = other or choices
        self.quiz_target = self._rng.choice(choices)
        if self.isVisible():
            self.overlay_reveal_requested.emit([])
        if self.quiz_mode == self.QUIZ_EAR:
            self.lbl_quiz_prompt.setText("🎧 Listen, then click the note you heard (Replay to hear it again).")
            self.play_note_requested.emit(self.quiz_target.midi_note)
        else:
            name = self.quiz_target.note_name.rstrip("-0123456789")
            self.lbl_quiz_prompt.setText(f"Find any <b>{self.quiz_target.degree_label}</b> ({name}) in the range.")

    def _replay_target(self):
        if self.quiz_target is not None:
            self.play_note_requested.emit(self.quiz_target.midi_note)

    def _skip_question(self):
        if self.quiz_target is not None and self.isVisible():
            self.overlay_reveal_requested.emit([n for n in self._overlay_notes if self._matches_target(n)])
        self.quiz_streak = 0
        self._update_score()
        self._quiz_waiting = True
        self.quiz_timer.start(self.QUIZ_NEXT_DELAY_MS)

    def answer_quiz(self, note: BoxNote):
        """Called with the circle the player clicked while the quiz runs."""
        if self.quiz_mode == self.QUIZ_OFF or self.quiz_target is None or self._quiz_waiting:
            return
        self.play_note_requested.emit(note.midi_note)
        self.quiz_attempts += 1
        where = (
            f"string {note.string_number}, fret {note.fret}, "
            f"{describe_controllers(note.engaged_levers, self.names)}"
        )
        if self._matches_target(note):
            self.quiz_correct += 1
            self.quiz_streak += 1
            self.overlay_reveal_requested.emit([n for n in self._overlay_notes if self._matches_target(n)])
            self.lbl_quiz_prompt.setText(
                f"✓ Yes: degree {note.degree_label} = {note.note_name} ({where}). All its spots are shown."
            )
            self._quiz_waiting = True
            self.quiz_timer.start(self.QUIZ_NEXT_DELAY_MS)
        else:
            self.quiz_streak = 0
            self.overlay_wrong_marked.emit(note)
            self.lbl_quiz_prompt.setText(
                f"✗ That one is degree {note.degree_label} ({note.note_name}). Try again."
            )
        self._update_score()

    def _update_score(self):
        if self.quiz_mode == self.QUIZ_OFF:
            self.lbl_score.setText("")
            return
        pct = f" ({round(100 * self.quiz_correct / self.quiz_attempts)}%)" if self.quiz_attempts else ""
        self.lbl_score.setText(f"Score {self.quiz_correct}/{self.quiz_attempts}{pct} · streak {self.quiz_streak}")

    def _on_tempo_changed(self, bpm: int):
        for timer in (self.walk_timer, self.play_timer):
            if timer.isActive():
                timer.setInterval(self._walk_interval_ms())

    def _walk_interval_ms(self) -> int:
        return int(round(60000 / max(1, self.spin_tempo.value())))

    def select_step(self, idx: int):
        run = self.run
        if not (0 <= idx < len(run)):
            return
        self.active_step_idx = idx
        self.table_staircase.selectRow(idx)
        n = run[idx]
        root = self.root_combo.currentText()
        scale = self.scale_combo.currentText()
        banner = (
            f"{root} {scale} — step {idx + 1}/{len(run)} · degree {n.degree_label}: {n.note_name} "
            f"(str {n.string_number}, fret {n.fret}, {describe_controllers(n.engaged_levers, self.names)})"
        )
        self._update_status()
        self.scale_step_applied.emit(n.fret, n.engaged_levers, n.string_number, banner)
        self.overlay_step_changed.emit(idx)
        self.play_note_requested.emit(n.midi_note)

    def next_step(self):
        if self.run:
            lo, hi = self.loop_bounds()
            i = self.active_step_idx
            self.select_step(lo if not (lo <= i < hi) else i + 1)

    def prev_step(self):
        if self.run:
            lo, hi = self.loop_bounds()
            i = self.active_step_idx
            self.select_step(hi if not (lo < i <= hi) else i - 1)

    def _auto_step_forward(self):
        lo, hi = self.loop_bounds()
        i = self.active_step_idx
        if i < lo or i > hi:
            self.select_step(lo)
        elif i < hi:
            self.select_step(i + 1)
        elif self.cb_loop.isChecked():
            self.select_step(lo)  # keep looping until stopped
        else:
            self._toggle_auto_walk()

    def _toggle_auto_walk(self):
        if self.walk_timer.isActive():
            self.walk_timer.stop()
            self.btn_walk.setText("▶ Auto-Walk")
            self.btn_walk.setStyleSheet("font-weight: bold; min-height: 26px; padding: 0 12px;")
        else:
            if not self.run:
                return
            self.stop_play_run()
            self.active_step_idx = -1
            self.walk_timer.start(self._walk_interval_ms())
            self.btn_walk.setText("⏹ Stop Walk")
            self.btn_walk.setStyleSheet(
                "background-color: #dc3545; color: white; font-weight: bold; min-height: 26px; padding: 0 12px;"
            )
            self._auto_step_forward()

    def _on_staircase_cell_clicked(self, row: int, col: int):
        self.select_step(row)

    def closeEvent(self, event):
        self.clear_highlight_requested.emit()
        super().closeEvent(event)