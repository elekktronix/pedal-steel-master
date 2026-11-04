"""Progression Studio (E-32): one dock that replaces the Voice Leader window and the Progression
Sequencer. Chords and stances live in the same steps (core.progression_studio); one transport plays
them in time on the fretboard.

Timing: a single-shot PreciseTimer is re-armed against an absolute beat grid, so beats do not drift
(the old CoarseTimer lost about 12 ms per beat). Clicks and notes both go through the MIDI scheduler
(`audio.play_click` / `play_note`), so they sound together. Play acts on beat 1 immediately.
"""

import copy
import json
import random
import time
from typing import Dict, List, Optional

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from core.audio import CLICK_SOUNDS
from core.models import Neck
from core.permutation_engine import FRANKLIN_24_PERMUTATIONS
from core.progression_presets import PROGRESSION_PRESETS
from core.progression_studio import (
    CADENCES,
    STYLE_ARPEGGIO,
    STYLE_BLOCK,
    STYLE_ROLL,
    TIME_SIGNATURES,
    PlaybackPlan,
    StudioProgression,
    StudioStep,
    arpeggio_strings,
    cadence_progression,
    dice_progression,
    fill_stances,
    format_progression_text,
    parse_progression_text,
    preset_progression,
    tab_steps,
)
from core.stances import controller_display_names, describe_controllers, grip_matches_chord, is_c6_neck
from core.tab_generator import TabGenerator
from core.theory import CHORD_FORMULAS, note_names, respell
from core.voice_leader import VoiceLeadingConstraints

CLICK_OFF = "Off"
NO_CHORD = "(no chord)"
SHAPES = [("Smooth (least bar travel)", "minimal"), ("Climb up the neck", "up"), ("Walk down the neck", "down"),
          ("Up, then down", "up_down"), ("Down, then up", "down_up"), ("Random", "random")]
STYLE_LABELS = [("Block chord", STYLE_BLOCK), ("Roll (bass to treble)", STYLE_ROLL), ("Arpeggio pattern", STYLE_ARPEGGIO)]
_STYLE_ICON = {STYLE_BLOCK: "", STYLE_ROLL: " ↗", STYLE_ARPEGGIO: " ≋"}

CARD_BASE = "QPushButton { text-align: left; padding: 4px 8px; border-radius: 6px; font-size: 11px; "
CARD_STYLES = {
    "normal": CARD_BASE + "border: 1px solid #6c757d; }",
    "unvoiced": CARD_BASE + "border: 1px dashed #dc3545; }",
    "selected": CARD_BASE + "border: 2px solid #0d6efd; }",
    "playing": CARD_BASE + "border: 2px solid #198754; background-color: #198754; color: white; }",
}
PLAY_STYLE = "background-color: #198754; color: white; font-weight: bold; min-height: 28px; padding: 0 16px;"
STOP_STYLE = "background-color: #dc3545; color: white; font-weight: bold; min-height: 28px; padding: 0 16px;"


def _clear_layout(layout) -> None:
    """Hides then deletes every widget in a layout (a removed, still-visible widget is otherwise
    drawn at its default geometry until deleteLater runs)."""
    while layout.count():
        w = layout.takeAt(0).widget()
        if w is not None:
            w.hide()
            w.deleteLater()


class ProgressionStudioWidget(QWidget):
    stance_requested = Signal(int, list, list, str)   # fret, controllers, grip strings, banner
    play_step_requested = Signal(str, list, float)    # style, strings (play order), seconds between notes
    click_requested = Signal(bool, str)               # accent, CLICK_SOUNDS name
    silence_requested = Signal()
    capture_requested = Signal(bool)                  # True = replace the selected step's stance

    def __init__(self, neck: Neck, settings: Optional[dict] = None, save_settings=None, parent=None):
        super().__init__(parent)
        self.neck = neck
        self.names: Dict[str, str] = controller_display_names(neck)
        self._neck_sig = self._signature(neck)
        self.settings = settings if settings is not None else {}
        self._save_settings = save_settings
        self.progression = StudioProgression(name="I–IV–I–V in G", key="G", neck_name=neck.name,
                                             steps=parse_progression_text("G C G D"))
        self.selected = 0
        self.playing_idx: Optional[int] = None
        self.unsolved: set = set()
        self._rng = random.Random()
        self._cards: List[QPushButton] = []
        self._tab_dlg: Optional[QDialog] = None

        self._plan: Optional[PlaybackPlan] = None
        self._beat = 0
        self._t0 = 0.0
        self._interval = 0.6
        self.beat_timer = QTimer(self)
        self.beat_timer.setSingleShot(True)
        self.beat_timer.setTimerType(Qt.PreciseTimer)
        self.beat_timer.timeout.connect(self._on_beat)

        self._init_ui()
        self._refresh_all()

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(6)

        # 1. Song + transport
        bar = QHBoxLayout()
        self.btn_load = QToolButton()
        self.btn_load.setText("📂 Load ▾")
        self.btn_load.setPopupMode(QToolButton.InstantPopup)
        self.load_menu = QMenu(self)
        self.btn_load.setMenu(self.load_menu)
        self._build_load_menu()
        bar.addWidget(self.btn_load)
        self.btn_save = QPushButton("💾 Save")
        self.btn_save.clicked.connect(self._save_file)
        bar.addWidget(self.btn_save)

        bar.addSpacing(8)
        bar.addWidget(QLabel("Key:"))
        self.combo_key = QComboBox()
        self.combo_key.addItems(note_names())
        self.combo_key.setToolTip("Key for the cadences and the dice")
        self.combo_key.currentTextChanged.connect(self._on_key_changed)
        bar.addWidget(self.combo_key)
        bar.addWidget(QLabel("Time:"))
        self.combo_time = QComboBox()
        self.combo_time.addItems(list(TIME_SIGNATURES))
        self.combo_time.currentTextChanged.connect(self._on_time_changed)
        bar.addWidget(self.combo_time)
        bar.addWidget(QLabel("BPM:"))
        self.spin_bpm = QSpinBox()
        self.spin_bpm.setRange(30, 300)
        self.spin_bpm.valueChanged.connect(self._on_bpm_changed)
        bar.addWidget(self.spin_bpm)
        bar.addWidget(QLabel("Count-in:"))
        self.combo_count_in = QComboBox()
        for text, bars in (("Off", 0), ("1 bar", 1), ("2 bars", 2)):
            self.combo_count_in.addItem(text, bars)
        self.combo_count_in.setCurrentIndex(max(0, self.combo_count_in.findData(int(self.settings.get("studio_count_in", 1)))))
        self.combo_count_in.currentIndexChanged.connect(lambda _: self._save("studio_count_in", self.combo_count_in.currentData()))
        bar.addWidget(self.combo_count_in)
        bar.addWidget(QLabel("Click:"))
        self.combo_click = QComboBox()
        self.combo_click.addItems(list(CLICK_SOUNDS) + [CLICK_OFF])
        saved = self.settings.get("studio_click_sound", "Woodblock")
        self.combo_click.setCurrentText(saved if saved in CLICK_SOUNDS or saved == CLICK_OFF else "Woodblock")
        self.combo_click.setToolTip("Metronome click (beat 1 accented). It shares the MIDI queue with the notes,\n"
                                    "so click and chord stay together. The count-in always clicks.")
        self.combo_click.currentTextChanged.connect(lambda v: self._save("studio_click_sound", v))
        bar.addWidget(self.combo_click)

        bar.addSpacing(8)
        self.cb_loop = QCheckBox("⟳ Loop steps")
        self.cb_loop.setChecked(True)
        bar.addWidget(self.cb_loop)
        self.spin_loop_from = QSpinBox()
        self.spin_loop_to = QSpinBox()
        for sp in (self.spin_loop_from, self.spin_loop_to):
            sp.setRange(1, 1)
        bar.addWidget(self.spin_loop_from)
        bar.addWidget(QLabel("to"))
        bar.addWidget(self.spin_loop_to)
        self.spin_loop_from.valueChanged.connect(
            lambda v: self.spin_loop_to.setValue(max(v, self.spin_loop_to.value())))
        self.spin_loop_to.valueChanged.connect(
            lambda v: self.spin_loop_from.setValue(min(v, self.spin_loop_from.value())))
        bar.addStretch()
        self.btn_prev = QPushButton("⏮")
        self.btn_prev.setToolTip("Previous step (plays it)")
        self.btn_prev.clicked.connect(lambda: self.step_by(-1))
        bar.addWidget(self.btn_prev)
        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setStyleSheet(PLAY_STYLE)
        self.btn_play.setToolTip("Starts on beat 1 straight away (after the count-in, if any). Click again to stop.")
        self.btn_play.clicked.connect(self.toggle_play)
        bar.addWidget(self.btn_play)
        self.btn_next = QPushButton("⏭")
        self.btn_next.setToolTip("Next step (plays it)")
        self.btn_next.clicked.connect(lambda: self.step_by(1))
        bar.addWidget(self.btn_next)
        root.addLayout(bar)

        # 2. Typed chords
        text_row = QHBoxLayout()
        text_row.addWidget(QLabel("<b>Chords:</b>"))
        self.edit_chords = QLineEdit()
        self.edit_chords.setPlaceholderText("e.g.  G C D7 G   ·   | Am7 D7 | Gmaj7 | %  |   ·   Am7:2 D7:2   ( - = rest )")
        self.edit_chords.setToolTip("Type chord symbols and press Enter. Without '|' each chord is one bar;\n"
                                    "with '|' the chords in a bar share it. ':n' sets beats, '%' repeats, '-' rests.")
        self.edit_chords.returnPressed.connect(self._apply_text)
        text_row.addWidget(self.edit_chords, stretch=1)
        self.btn_apply_text = QPushButton("Apply")
        self.btn_apply_text.clicked.connect(self._apply_text)
        text_row.addWidget(self.btn_apply_text)
        root.addLayout(text_row)

        # 3. Timeline
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setFixedHeight(92)
        holder = QWidget()
        self.cards_layout = QHBoxLayout(holder)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(6)
        self.scroll.setWidget(holder)
        root.addWidget(self.scroll)

        # 4. Step editor
        ed = QHBoxLayout()
        self.lbl_step = QLabel("")
        self.lbl_step.setStyleSheet("font-weight: bold;")
        ed.addWidget(self.lbl_step)
        self.combo_root = QComboBox()
        self.combo_root.addItems(note_names())
        self.combo_root.currentIndexChanged.connect(self._on_chord_edited)
        ed.addWidget(self.combo_root)
        self.combo_type = QComboBox()
        self.combo_type.addItems([NO_CHORD] + list(CHORD_FORMULAS))
        self.combo_type.currentIndexChanged.connect(self._on_chord_edited)
        ed.addWidget(self.combo_type)
        ed.addWidget(QLabel("Beats:"))
        self.spin_beats = QSpinBox()
        self.spin_beats.setRange(1, 16)
        self.spin_beats.valueChanged.connect(self._on_beats_edited)
        ed.addWidget(self.spin_beats)
        ed.addWidget(QLabel("Play as:"))
        self.combo_style = QComboBox()
        for text, style in STYLE_LABELS:
            self.combo_style.addItem(text, style)
        self.combo_style.currentIndexChanged.connect(self._on_style_edited)
        ed.addWidget(self.combo_style)
        self.combo_perm = QComboBox()
        for pid, (p_str, notes, *_) in FRANKLIN_24_PERMUTATIONS.items():
            self.combo_perm.addItem(f"#{pid:02d} {p_str}", pid)
        self.combo_perm.setToolTip("Franklin picking permutation for the arpeggio (one cycle per beat)")
        self.combo_perm.currentIndexChanged.connect(self._on_style_edited)
        ed.addWidget(self.combo_perm)
        self.cb_pin = QCheckBox("📌 Pinned")
        self.cb_pin.setToolTip("A pinned stance is kept when you re-voice the progression")
        self.cb_pin.toggled.connect(self._on_pin_toggled)
        ed.addWidget(self.cb_pin)
        ed.addStretch()
        for text, tip, slot in (
            ("➕", "Add a step after this one", self._add_step),
            ("⧉", "Duplicate this step", self._duplicate_step),
            ("◀", "Move left", lambda: self._move_step(-1)),
            ("▶", "Move right", lambda: self._move_step(1)),
            ("🗑", "Remove this step", self._remove_step),
        ):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setFixedWidth(34)
            b.clicked.connect(slot)
            ed.addWidget(b)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self._clear_steps)
        ed.addWidget(self.btn_clear)
        root.addLayout(ed)

        # 5. Capture + voice leading + tab
        vl = QHBoxLayout()
        self.btn_capture = QPushButton("➕ Capture fretboard")
        self.btn_capture.setToolTip("Add the fretboard's current stance and pocket as a new pinned step")
        self.btn_capture.clicked.connect(lambda: self.capture_requested.emit(False))
        vl.addWidget(self.btn_capture)
        self.btn_use_stance = QPushButton("🎯 Use fretboard for this step")
        self.btn_use_stance.setToolTip("Replace the selected step's stance with the fretboard's (pinned)")
        self.btn_use_stance.clicked.connect(lambda: self.capture_requested.emit(True))
        vl.addWidget(self.btn_use_stance)
        vl.addSpacing(12)
        vl.addWidget(QLabel("<b>Voice-lead:</b>"))
        self.combo_shape = QComboBox()
        for text, traj in SHAPES:
            self.combo_shape.addItem(text, traj)
        vl.addWidget(self.combo_shape)
        vl.addWidget(QLabel("Frets"))
        self.spin_min_fret = QSpinBox()
        self.spin_min_fret.setRange(0, 22)
        self.spin_max_fret = QSpinBox()
        self.spin_max_fret.setRange(2, 24)
        self.spin_max_fret.setValue(12)
        vl.addWidget(self.spin_min_fret)
        vl.addWidget(QLabel("–"))
        vl.addWidget(self.spin_max_fret)
        self.spin_min_fret.valueChanged.connect(
            lambda v: self.spin_max_fret.setValue(max(v, self.spin_max_fret.value())))
        vl.addWidget(QLabel("Max jump"))
        self.spin_jump = QSpinBox()
        self.spin_jump.setRange(1, 12)
        self.spin_jump.setValue(3)
        vl.addWidget(self.spin_jump)
        vl.addWidget(QLabel("Start near fret"))
        self.spin_start = QSpinBox()
        self.spin_start.setRange(0, 24)
        self.spin_start.setValue(3)
        vl.addWidget(self.spin_start)
        self.btn_fill = QPushButton("🧭 Re-voice")
        self.btn_fill.setToolTip("Voice-lead every chord that is not pinned, using the shape and frets above")
        self.btn_fill.clicked.connect(self.revoice)
        vl.addWidget(self.btn_fill)
        vl.addStretch()
        self.btn_tab = QPushButton("🎼 Tab")
        self.btn_tab.clicked.connect(self._show_tab)
        vl.addWidget(self.btn_tab)
        root.addLayout(vl)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("font-size: 11px;")
        root.addWidget(self.lbl_status)

    def _build_load_menu(self):
        menu = self.load_menu
        menu.clear()
        e9 = menu.addMenu("E9 practice progressions")
        c6 = menu.addMenu("C6 practice progressions")
        for p in PROGRESSION_PRESETS:
            act = (c6 if p.neck_type == "C6" else e9).addAction(p.name)
            act.setToolTip(p.description)
            act.triggered.connect(lambda _=False, p=p: self.load_preset(p))
        cad = menu.addMenu("Cadences in the selected key")
        for kind, (title, _degrees) in CADENCES.items():
            cad.addAction(title).triggered.connect(lambda _=False, k=kind: self.load_cadence(k))
        menu.addAction("🎲 Roll the dice (two V7 → chord moves)").triggered.connect(self.roll_dice)
        menu.addSeparator()
        menu.addAction("Open file… (.cp / .json)").triggered.connect(self._open_file)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _signature(neck: Neck):
        return (neck.name, neck.string_count, tuple(sorted(neck.pedals)), tuple(sorted(neck.knee_levers)))

    def _save(self, key, value):
        self.settings[key] = value
        if self._save_settings:
            self._save_settings(self.settings)

    @property
    def steps(self) -> List[StudioStep]:
        return self.progression.steps

    @property
    def is_playing(self) -> bool:
        return self._plan is not None

    def _constraints(self) -> VoiceLeadingConstraints:
        return VoiceLeadingConstraints(
            min_fret=self.spin_min_fret.value(), max_fret=self.spin_max_fret.value(),
            max_fret_jump=self.spin_jump.value(), trajectory=self.combo_shape.currentData(),
            start_fret=self.spin_start.value(),
        )

    def _status(self, text: str, error: bool = False):
        self.lbl_status.setStyleSheet(f"font-size: 11px; color: {'#dc3545' if error else 'gray'};")
        self.lbl_status.setText(text)

    def _stance_text(self, i: int, s: StudioStep) -> str:
        if s.has_stance:
            strings = "-".join(str(x) for x in sorted(s.grip, reverse=True))
            return f"F{s.fret} · {describe_controllers(s.controllers, self.names)}\nstr {strings}"
        if s.is_rest:
            return "rest\n"
        return "no voicing in range\n" if i in self.unsolved else "needs voicing\n"

    # ------------------------------------------------------------------ refresh
    def _refresh_all(self):
        prog = self.progression
        for combo, value in ((self.combo_key, respell(prog.key)), (self.combo_time, prog.time_signature)):
            combo.blockSignals(True)
            if combo.findText(value) >= 0:
                combo.setCurrentText(value)
            combo.blockSignals(False)
        self.spin_bpm.blockSignals(True)
        self.spin_bpm.setValue(prog.tempo)
        self.spin_bpm.blockSignals(False)
        self._rebuild_cards()

    def _rebuild_cards(self):
        _clear_layout(self.cards_layout)
        self._cards = []
        n = len(self.steps)
        self.selected = max(0, min(self.selected, n - 1)) if n else 0
        for i, s in enumerate(self.steps):
            bar, beat = self.progression.bar_position(i)
            head = f"{bar}" if beat == 1 else f"{bar}.{beat}"
            pin = " 📌" if s.pinned else ""
            card = QPushButton(f"{head}{pin}{_STYLE_ICON.get(s.style, '')}  {s.symbol}\n{self._stance_text(i, s)}")
            card.setMinimumWidth(70 + 16 * s.beats)
            card.setMinimumHeight(70)
            card.setToolTip(f"Step {i + 1}: {s.symbol}, {s.beats} beat(s). Click to select and hear it.")
            card.clicked.connect(lambda _=False, i=i: self.select_step(i, audition=not self.is_playing))
            self.cards_layout.addWidget(card)
            self._cards.append(card)
        self.cards_layout.addStretch()
        # Keep the user's loop range; one that covered every step keeps covering every step.
        was_full = self.spin_loop_to.value() == self.spin_loop_to.maximum()
        for sp in (self.spin_loop_from, self.spin_loop_to):
            sp.blockSignals(True)
            sp.setRange(1, max(1, n))
            sp.blockSignals(False)
        if was_full:
            self.spin_loop_to.setValue(max(1, n))
        if self.spin_loop_from.value() > self.spin_loop_to.value():
            self.spin_loop_from.setValue(self.spin_loop_to.value())
        self._restyle_cards()
        self._load_editor()
        if not self.edit_chords.hasFocus():
            self.edit_chords.setText(format_progression_text(self.steps, self.progression.beats_per_bar))

    def _restyle_cards(self):
        for i, card in enumerate(self._cards):
            s = self.steps[i]
            if i == self.playing_idx:
                key = "playing"
            elif i == self.selected:
                key = "selected"
            elif s.has_chord and not s.has_stance:
                key = "unvoiced"
            else:
                key = "normal"
            card.setStyleSheet(CARD_STYLES[key])
        if self._cards and 0 <= self.selected < len(self._cards):
            self.scroll.ensureWidgetVisible(self._cards[self.playing_idx if self.playing_idx is not None else self.selected])

    def _load_editor(self):
        has = bool(self.steps)
        for w in (self.combo_root, self.combo_type, self.spin_beats, self.combo_style, self.combo_perm, self.cb_pin):
            w.setEnabled(has)
        if not has:
            self.lbl_step.setText("No steps")
            return
        s = self.steps[self.selected]
        widgets = (self.combo_root, self.combo_type, self.spin_beats, self.combo_style, self.combo_perm, self.cb_pin)
        for w in widgets:
            w.blockSignals(True)
        self.lbl_step.setText(f"Step {self.selected + 1}:")
        if s.has_chord:
            self.combo_root.setCurrentText(respell(s.root))
            self.combo_type.setCurrentText(s.chord_type)
        else:
            self.combo_type.setCurrentText(NO_CHORD)
        self.combo_root.setEnabled(s.has_chord)
        self.spin_beats.setValue(s.beats)
        self.combo_style.setCurrentIndex(max(0, self.combo_style.findData(s.style)))
        self.combo_perm.setCurrentIndex(max(0, self.combo_perm.findData(s.perm_id)))
        self.combo_perm.setVisible(s.style == STYLE_ARPEGGIO)
        self.cb_pin.setChecked(s.pinned)
        self.cb_pin.setEnabled(s.has_stance)
        for w in widgets:
            w.blockSignals(False)

    # ------------------------------------------------------------------ neck / session
    def set_neck(self, neck: Neck):
        """Stances are neck-specific: on a different neck (or different controllers) they are cleared
        and re-voiced, never replayed on the wrong copedant (D-45)."""
        self.neck = neck
        self.names = controller_display_names(neck)
        sig = self._signature(neck)
        if sig == self._neck_sig:
            self._rebuild_cards()
            return
        self._neck_sig = sig
        self.stop()
        had = any(s.has_stance for s in self.steps)
        for s in self.steps:
            s.clear_stance()
        self.progression.neck_name = neck.name
        self.unsolved = set()
        if self.isVisible():
            self._fill_missing()
        self._rebuild_cards()
        if had:
            self._status(f"Neck changed to {neck.name}: stances were re-voiced for it.")

    def session_data(self) -> dict:
        return self.progression.to_dict()

    def restore_session(self, data: dict):
        try:
            prog = StudioProgression.from_dict(data)
        except Exception:
            return
        self.load_progression(prog, fill=False)

    def showEvent(self, event):
        super().showEvent(event)
        if any(s.has_chord and not s.has_stance for s in self.steps):
            self._fill_missing()
            self._rebuild_cards()

    def hideEvent(self, event):
        self.stop()
        super().hideEvent(event)

    # ------------------------------------------------------------------ loading
    def load_progression(self, prog: StudioProgression, fill: bool = True, message: str = ""):
        self.stop()
        if prog.neck_name and prog.neck_name != self.neck.name:
            for s in prog.steps:
                s.clear_stance()
        prog.neck_name = self.neck.name
        self.progression = prog
        self.selected = 0
        self.unsolved = set()
        if fill:
            self._fill_missing()
        self._refresh_all()
        self._status(message or f"Loaded “{prog.name}”: {len(prog.steps)} steps.")

    def load_preset(self, preset):
        if (preset.neck_type == "C6") != is_c6_neck(self.neck):
            self._status(f"“{preset.name}” is written for {preset.neck_type}; the active neck is {self.neck.name}.", True)
            return
        prog = preset_progression(preset, self.neck, self.progression.beats_per_bar)
        if prog is None:
            self._status(f"The active copedant lacks a pedal or lever that “{preset.name}” needs.", True)
            return
        prog.tempo = self.spin_bpm.value()
        prog.time_signature = self.combo_time.currentText()
        self.load_progression(prog, message=f"Loaded “{preset.name}” with its pinned stances. {preset.description}")

    def load_cadence(self, kind: str):
        key = self.combo_key.currentText()
        prog = cadence_progression(kind, key, self.progression.beats_per_bar)
        prog.tempo = self.spin_bpm.value()
        prog.time_signature = self.combo_time.currentText()
        self.load_progression(prog)

    def roll_dice(self):
        prog, text = dice_progression(self.combo_key.currentText(), self.progression.beats_per_bar, self._rng)
        prog.tempo = self.spin_bpm.value()
        prog.time_signature = self.combo_time.currentText()
        self.load_progression(prog, message=f"🎲 {text}")

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open progression", "",
                                              "Chord Progression (*.cp *.json *.cprog);;All Files (*.*)")
        if path:
            self.load_file(path)

    def load_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                prog = StudioProgression.from_dict(json.load(f))
        except Exception as e:
            self._status(f"Could not open {path}: {e}", True)
            return
        self.load_progression(prog)

    def _save_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save progression", f"{self.progression.name}.cp",
                                              "Chord Progression (*.cp *.json *.cprog)")
        if path:
            self.save_file(path)

    def save_file(self, path: str):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.progression.to_dict(), f, indent=2)
        except Exception as e:
            self._status(f"Could not save {path}: {e}", True)
            return
        self._status(f"Saved to {path} (chords, beats, stances and play styles).")

    def _apply_text(self):
        text = self.edit_chords.text().strip()
        if not text:
            return
        try:
            steps = parse_progression_text(text, self.progression.beats_per_bar)
        except ValueError as e:
            self._status(str(e), True)
            return
        old = self.progression
        prog = StudioProgression(name="Typed progression", key=old.key, time_signature=old.time_signature,
                                 tempo=old.tempo, steps=steps, neck_name=self.neck.name)
        self.edit_chords.clearFocus()
        self.load_progression(prog, message=f"{len(steps)} steps from the chord text.")

    # ------------------------------------------------------------------ voice leading
    def _fill_missing(self) -> List[int]:
        """Voices chords that have no stance yet, around the existing ones (edits, loads, Play)."""
        if not any(s.has_chord and not s.has_stance for s in self.steps):
            return []
        unsolved = fill_stances(self.neck, self.steps, self._constraints(), only_missing=True)
        self.unsolved = set(unsolved)
        if unsolved:
            names = ", ".join(self.steps[i].symbol for i in unsolved)
            self._status(f"No voicing for {names} in frets {self.spin_min_fret.value()}–{self.spin_max_fret.value()} "
                         "(widen the frets or capture one from the fretboard). Those steps will be silent.", True)
        return unsolved

    def revoice(self):
        self.stop()
        pinned = sum(1 for s in self.steps if s.pinned)
        unsolved = fill_stances(self.neck, self.steps, self._constraints())
        self.unsolved = set(unsolved)
        self._rebuild_cards()
        voiced = sum(1 for s in self.steps if s.has_chord and s.has_stance and not s.pinned)
        msg = f"Re-voiced {voiced} chord(s) ({self.combo_shape.currentText().lower()})"
        msg += f"; kept {pinned} pinned." if pinned else "."
        if unsolved:
            msg += f" No voicing for {', '.join(self.steps[i].symbol for i in unsolved)} in these frets."
        self._status(msg, bool(unsolved))

    # ------------------------------------------------------------------ editing
    def _edit_guard(self):
        if self.is_playing:
            self.stop()

    def _on_chord_edited(self, *_):
        if not self.steps:
            return
        self._edit_guard()
        s = self.steps[self.selected]
        ctype = self.combo_type.currentText()
        if ctype == NO_CHORD:
            s.set_chord(None, None)
        else:
            s.set_chord(self.combo_root.currentText(), ctype)
            s.label = ""
        self.unsolved.discard(self.selected)
        self._fill_missing()
        self._rebuild_cards()

    def _on_beats_edited(self, value: int):
        if self.steps:
            self._edit_guard()
            self.steps[self.selected].beats = value
            self._rebuild_cards()

    def _on_style_edited(self, *_):
        if self.steps:
            s = self.steps[self.selected]
            s.style = self.combo_style.currentData()
            s.perm_id = self.combo_perm.currentData()
            self._rebuild_cards()

    def _on_pin_toggled(self, checked: bool):
        if self.steps and self.steps[self.selected].has_stance:
            self.steps[self.selected].pinned = checked
            self._rebuild_cards()

    def _new_step_like(self, src: Optional[StudioStep]) -> StudioStep:
        bpb = self.progression.beats_per_bar
        if src is not None and src.has_chord:
            return StudioStep(root=src.root, chord_type=src.chord_type, beats=src.beats, style=src.style, perm_id=src.perm_id)
        return StudioStep(root=self.combo_key.currentText(), chord_type="Major", beats=bpb)

    def _add_step(self):
        self._edit_guard()
        src = self.steps[self.selected] if self.steps else None
        at = self.selected + 1 if self.steps else 0
        self.steps.insert(at, self._new_step_like(src))
        self.selected = at
        self._fill_missing()
        self._rebuild_cards()

    def _duplicate_step(self):
        if not self.steps:
            return
        self._edit_guard()
        self.steps.insert(self.selected + 1, copy.deepcopy(self.steps[self.selected]))
        self.selected += 1
        self._rebuild_cards()

    def _move_step(self, delta: int):
        j = self.selected + delta
        if not self.steps or not (0 <= j < len(self.steps)):
            return
        self._edit_guard()
        self.steps[self.selected], self.steps[j] = self.steps[j], self.steps[self.selected]
        self.selected = j
        self._rebuild_cards()

    def _remove_step(self):
        if not self.steps:
            return
        self._edit_guard()
        self.steps.pop(self.selected)
        self.unsolved = set()
        self.selected = min(self.selected, len(self.steps) - 1)
        self._rebuild_cards()

    def _clear_steps(self):
        self._edit_guard()
        self.progression.steps = []
        self.selected = 0
        self.unsolved = set()
        self._rebuild_cards()
        self._status("Cleared. Type chords, load a progression or capture the fretboard.")

    def _on_key_changed(self, key: str):
        self.progression.key = key

    def _on_time_changed(self, ts: str):
        self.progression.time_signature = ts
        self._edit_guard()
        self._rebuild_cards()

    def _on_bpm_changed(self, bpm: int):
        self.progression.tempo = bpm
        if self.is_playing:
            # Keep the beat already played where it was; the next one comes one new beat later.
            now = time.perf_counter()
            new = 60.0 / bpm
            last = self._t0 + (self._beat - 1) * self._interval
            self._interval = new
            self._t0 = min(last, now) - (self._beat - 1) * new
            self._arm()

    # ------------------------------------------------------------------ capture (from MainWindow)
    def add_captured_step(self, fret: int, controllers, grip, chord: Optional[tuple], replace: bool = False):
        """The fretboard stance as a pinned step: a new step after the selection, or (replace) the
        selected step's stance. `chord` is the (root, type) the grip sounds, if it was recognised."""
        if not grip:
            self._status("Pick some strings on the fretboard first (the pocket is empty).", True)
            return
        self._edit_guard()
        if replace and self.steps:
            s = self.steps[self.selected]
            if not s.has_chord and chord:
                s.set_chord(*chord)
            s.set_stance(fret, controllers, grip, pinned=True)
            self.unsolved.discard(self.selected)
            if s.has_chord and not grip_matches_chord(self.neck, fret, controllers, grip, s.root, s.chord_type,
                                                      require_root=False):
                self._status(f"Pinned, but that stance doesn't sound {s.symbol}.", True)
            else:
                self._status(f"Step {self.selected + 1} now uses the fretboard stance (pinned).")
        else:
            st = StudioStep(beats=self.progression.beats_per_bar, label="" if chord else "Grip")
            if chord:
                st.set_chord(*chord)
            st.set_stance(fret, controllers, grip, pinned=True)
            at = self.selected + 1 if self.steps else 0
            self.steps.insert(at, st)
            self.selected = at
            self._status(f"Captured {st.symbol} at fret {fret}." if chord else
                         f"Captured a grip at fret {fret} (no chord recognised: pick one in the step editor).")
        self._rebuild_cards()

    def add_chord_step(self, root: str, chord_type: str, fret: int, controllers, grip):
        """Appends a pinned chord step (e.g. from the circle of fifths)."""
        st = StudioStep(root=root, chord_type=chord_type, beats=self.progression.beats_per_bar)
        st.set_stance(fret, controllers, grip, pinned=True)
        self.steps.append(st)
        self.selected = len(self.steps) - 1
        self._rebuild_cards()

    # ------------------------------------------------------------------ transport
    def select_step(self, idx: int, audition: bool = True):
        if not (0 <= idx < len(self.steps)):
            return
        self.selected = idx
        self._restyle_cards()
        self._load_editor()
        if audition:
            self._sound_step(idx)

    def step_by(self, delta: int):
        if self.steps:
            self._edit_guard()
            self.select_step((self.selected + delta) % len(self.steps), audition=True)

    def _sound_step(self, idx: int):
        s = self.steps[idx]
        if not s.has_stance:
            self.silence_requested.emit()
            return
        bar, beat = self.progression.bar_position(idx)
        banner = f"{s.symbol} — bar {bar}" + (f" beat {beat}" if beat > 1 else "")
        self.stance_requested.emit(s.fret, list(s.controllers), list(s.grip), banner)
        beat_sec = 60.0 / max(1, self.spin_bpm.value())
        if s.style == STYLE_ARPEGGIO:
            order = arpeggio_strings(s)
            dt = (s.beats * beat_sec) / max(1, len(order))
            self.play_step_requested.emit(STYLE_ARPEGGIO, order, dt)
        else:
            self.play_step_requested.emit(s.style, list(s.grip), 0.0)

    def toggle_play(self):
        if self.is_playing:
            self.stop()
        else:
            self.play()

    def loop_range(self):
        n = len(self.steps)
        if not self.cb_loop.isChecked():
            return 0, n - 1
        return self.spin_loop_from.value() - 1, min(n, self.spin_loop_to.value()) - 1

    def play(self):
        if not self.steps:
            self._status("Nothing to play: type chords, load a progression or capture the fretboard.", True)
            return
        if any(s.has_chord and not s.has_stance for s in self.steps):
            self._fill_missing()
            self._rebuild_cards()
        first, last = self.loop_range()
        self._plan = PlaybackPlan.build(self.progression, first, last, self.combo_count_in.currentData() or 0,
                                        loop=self.cb_loop.isChecked())
        self._beat = 0
        self._interval = 60.0 / max(1, self.spin_bpm.value())
        self._t0 = time.perf_counter()
        self.btn_play.setText("⏹ Stop")
        self.btn_play.setStyleSheet(STOP_STYLE)
        self._on_beat()  # beat 1 (or the count-in's first click) right now

    def stop(self):
        if self._plan is None:
            return
        self.beat_timer.stop()
        self._plan = None
        self.playing_idx = None
        self.silence_requested.emit()
        self.btn_play.setText("▶ Play")
        self.btn_play.setStyleSheet(PLAY_STYLE)
        self._restyle_cards()

    def _arm(self):
        due = self._t0 + self._beat * self._interval
        self.beat_timer.start(max(0, int(round((due - time.perf_counter()) * 1000))))

    def _on_beat(self):
        plan = self._plan
        if plan is None:
            return
        ev = plan.at(self._beat)
        if ev.done:
            self.stop()
            self._status("End of the progression. Tick Loop to repeat it.")
            return
        sound = self.combo_click.currentText()
        if ev.count_in or sound != CLICK_OFF:
            self.click_requested.emit(ev.accent, sound if sound != CLICK_OFF else "Woodblock")
        if ev.count_in:
            self._status(f"Count-in: {self._beat % plan.bpb + 1}")
        if ev.step is not None:
            self.playing_idx = ev.step
            self.selected = ev.step
            self._restyle_cards()
            self._load_editor()
            self._sound_step(ev.step)
            s = self.steps[ev.step]
            bar, _ = self.progression.bar_position(ev.step)
            self._status(f"▶ Bar {bar}: {s.symbol}" + ("" if s.has_stance else " (no voicing: silent)"))
        self._beat += 1
        self._arm()

    # ------------------------------------------------------------------ tab
    def tab_text(self) -> str:
        return TabGenerator.generate_ascii_tab(self.neck.string_count, tab_steps(self.steps, self.names))

    def _show_tab(self):
        if not any(s.has_stance for s in self.steps):
            self._status("Nothing voiced yet to write as tab.", True)
            return
        if self._tab_dlg is None:
            dlg = QDialog(self)
            dlg.setWindowTitle("Progression tab")
            dlg.resize(760, 440)
            v = QVBoxLayout(dlg)
            self._tab_edit = QPlainTextEdit()
            self._tab_edit.setReadOnly(True)
            self._tab_edit.setFont(QFont("Consolas", 10))
            v.addWidget(self._tab_edit)
            row = QHBoxLayout()
            row.addStretch()
            btn_copy = QPushButton("Copy")
            btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(self._tab_edit.toPlainText()))
            row.addWidget(btn_copy)
            btn_close = QPushButton("Close")
            btn_close.clicked.connect(dlg.hide)
            row.addWidget(btn_close)
            v.addLayout(row)
            self._tab_dlg = dlg
        self._tab_edit.setPlainText(self.tab_text())
        self._tab_dlg.show()
        self._tab_dlg.raise_()
