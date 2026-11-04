"""Interactive workout dialog for Paul Franklin's 24 Right-Hand Picking Permutations.

Non-modal: the main fretboard stays usable while it is open. The strings follow the main
window's pocket live, notes come from the main fretboard's current stance, and the metronome
click goes through the MIDI scheduler (same queue as the notes) so the two stay in sync.
"""

from typing import Dict, List, Optional, Set

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from core.audio import CLICK_SOUNDS
from core.models import Neck
from core.permutation_engine import FRANKLIN_24_PERMUTATIONS, PermutationEngine, PickEvent

CLICK_OFF = "Off"
CLICK_CHIRP = "Chirp (WAV)"
CLICK_CHOICES = list(CLICK_SOUNDS) + [CLICK_CHIRP, CLICK_OFF]
CLICK_MODES = ["Every note", "Beat 1 only"]

_LANE_IDLE = """
    QFrame {
        background-color: #2b303c;
        border: 1.5px solid #4a5263;
        border-radius: 6px;
    }
"""
_LANE_ACTIVE = """
    QFrame {
        background-color: #49391d;
        border: 2px solid #ffc107;
        border-radius: 6px;
    }
"""
_BADGE_IDLE = """
    background-color: #1a1d24;
    color: #6c757d;
    font-weight: bold;
    font-size: 16px;
    border-radius: 4px;
    min-width: 50px;
    padding: 4px;
"""
_BADGE_ACTIVE = """
    background-color: #ffc107;
    color: #000000;
    font-weight: bold;
    font-size: 16px;
    border-radius: 4px;
    min-width: 80px;
    padding: 4px;
"""
_PILL_IDLE = "background-color: #2b303c; color: #adb5bd; font-weight: bold; padding: 6px 12px; border-radius: 4px;"
_PILL_ACTIVE = "background-color: #0d6efd; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;"


def played_strings(pocket: Set[int]) -> List[int]:
    """The distinct strings a permutation plays for this pocket (the 4 lowest-pitched), bass first."""
    return sorted(set(pocket), reverse=True)[:4]


class PermutationTrainerDialog(QDialog):
    def __init__(self, neck: Neck, active_pocket: Set[int], parent=None):
        super().__init__(parent)
        self.neck = neck
        self.parent_window = parent
        self.setWindowTitle("Franklin 24 Right-Hand Picking & Blocking Trainer")
        self.setModal(False)
        self.resize(840, 600)

        self.pocket: Set[int] = set(active_pocket)
        self.current_perm_id = 2
        self.events: List[PickEvent] = []
        self.current_event_idx = 0
        self._chirp = None  # MetronomeChirp, created only if that sound is chosen

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)  # default CoarseTimer drifts up to 5 %
        self.timer.timeout.connect(self._on_tick)

        self.lane_cards: List[QFrame] = []
        self.lane_finger_badges: List[QLabel] = []
        self.lane_index: Dict[int, int] = {}

        self._init_ui()
        self._rebuild_lanes()
        self._load_permutation_events()

        canvas = getattr(parent, "canvas", None)
        if canvas is not None and hasattr(canvas, "pocket_changed"):
            canvas.pocket_changed.connect(self._on_pocket_changed)

    # ---- settings helpers -----------------------------------------------------------------------
    def _settings(self) -> dict:
        return getattr(self.parent_window, "settings", None) or {}

    def _save_setting(self, key: str, value) -> None:
        settings = getattr(self.parent_window, "settings", None)
        if settings is None:
            return
        settings[key] = value
        try:
            from core.settings import save_settings
            save_settings(settings)
        except Exception:
            pass

    # ---- UI -------------------------------------------------------------------------------------
    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        top_group = QGroupBox("Select Right-Hand Permutation (Paul Franklin, pp. 37-39)")
        top_l = QGridLayout(top_group)
        top_l.setContentsMargins(10, 8, 10, 8)
        top_l.setSpacing(8)

        top_l.addWidget(QLabel("<b>Pattern:</b>"), 0, 0)
        self.combo_perm = QComboBox()
        self.combo_perm.setMinimumWidth(320)
        for pid, (pattern_str, notes, *_) in FRANKLIN_24_PERMUTATIONS.items():
            self.combo_perm.addItem(f"#{pid:02d}:  {pattern_str}  (book: {notes})", pid)
        self.combo_perm.setCurrentIndex(1)  # Permutation #2
        self.combo_perm.currentIndexChanged.connect(self._on_perm_changed)
        top_l.addWidget(self.combo_perm, 0, 1)

        top_l.addWidget(QLabel("<b>Strings:</b>"), 0, 2)
        self.lbl_strings = QLabel("")
        self.lbl_strings.setStyleSheet("font-weight: bold; color: #0d6efd;")
        top_l.addWidget(self.lbl_strings, 0, 3)

        self.lbl_strings_hint = QLabel("Follows the strings selected on the main fretboard.")
        self.lbl_strings_hint.setStyleSheet("color: #adb5bd; font-size: 11px;")
        top_l.addWidget(self.lbl_strings_hint, 1, 1, 1, 3)
        root.addWidget(top_group)

        self.deck_box = QGroupBox("Right-Hand Pick & Blocking Visualizer")
        self.deck_layout = QVBoxLayout(self.deck_box)
        self.deck_layout.setContentsMargins(12, 16, 12, 16)
        self.deck_layout.setSpacing(12)
        root.addWidget(self.deck_box, stretch=1)

        self.step_box = QFrame()
        self.step_box.setStyleSheet("background-color: #1e2129; border-radius: 6px; padding: 6px;")
        step_layout = QHBoxLayout(self.step_box)
        step_layout.setContentsMargins(8, 4, 8, 4)
        step_layout.setSpacing(8)
        self.step_indicators: List[QLabel] = []
        for i in range(4):
            lbl_step = QLabel(f"Beat {i+1}")
            lbl_step.setAlignment(Qt.AlignCenter)
            lbl_step.setStyleSheet(_PILL_IDLE)
            step_layout.addWidget(lbl_step)
            self.step_indicators.append(lbl_step)
        root.addWidget(self.step_box)

        # Metronome
        click_h = QHBoxLayout()
        click_h.addWidget(QLabel("<b>Click:</b>"))
        self.combo_click = QComboBox()
        self.combo_click.addItems(CLICK_CHOICES)
        saved = self._settings().get("perm_click_sound", "Woodblock")
        self.combo_click.setCurrentText(saved if saved in CLICK_CHOICES else "Woodblock")
        self.combo_click.setToolTip("MIDI clicks share the note queue and stay in sync; the WAV chirp "
                                    "plays through the sound card and may lag behind the notes.")
        self.combo_click.currentTextChanged.connect(lambda v: self._save_setting("perm_click_sound", v))
        click_h.addWidget(self.combo_click)
        self.combo_click_mode = QComboBox()
        self.combo_click_mode.addItems(CLICK_MODES)
        saved_mode = self._settings().get("perm_click_mode", "Every note")
        self.combo_click_mode.setCurrentText(saved_mode if saved_mode in CLICK_MODES else "Every note")
        self.combo_click_mode.currentTextChanged.connect(lambda v: self._save_setting("perm_click_mode", v))
        click_h.addWidget(self.combo_click_mode)
        click_h.addStretch()
        root.addLayout(click_h)

        # Transport
        ctrl_h = QHBoxLayout()
        ctrl_h.addWidget(QLabel("<b>Tempo:</b>"))
        self.spin_tempo = QSpinBox()
        self.spin_tempo.setRange(40, 240)
        self.spin_tempo.setValue(100)
        self.spin_tempo.setSuffix(" BPM")
        ctrl_h.addWidget(self.spin_tempo)

        self.slider_tempo = QSlider(Qt.Horizontal)
        self.slider_tempo.setRange(40, 240)
        self.slider_tempo.setValue(100)
        self.slider_tempo.valueChanged.connect(self.spin_tempo.setValue)
        self.spin_tempo.valueChanged.connect(self.slider_tempo.setValue)
        self.spin_tempo.valueChanged.connect(self._on_tempo_changed)
        ctrl_h.addWidget(self.slider_tempo, stretch=1)
        ctrl_h.addSpacing(15)

        self.btn_play = QPushButton("▶ Start Workout")
        self._style_play_button(False)
        self.btn_play.clicked.connect(self._toggle_workout)
        ctrl_h.addWidget(self.btn_play)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        ctrl_h.addWidget(btn_close)
        root.addLayout(ctrl_h)

    def _style_play_button(self, playing: bool):
        color = "#dc3545" if playing else "#28a745"
        self.btn_play.setText("⏹ Stop" if playing else "▶ Start Workout")
        self.btn_play.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: white; font-weight: bold; font-size: 13px;"
            " min-height: 34px; padding: 0 20px; border-radius: 4px; }"
        )

    def _rebuild_lanes(self):
        while self.deck_layout.count():
            item = self.deck_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.lane_cards.clear()
        self.lane_finger_badges.clear()
        self.lane_index.clear()

        strings = played_strings(self.pocket)
        for idx, s_num in enumerate(sorted(strings)):  # string 1 (highest pitch) at the top
            row_frame = QFrame()
            row_frame.setStyleSheet(_LANE_IDLE)
            r_layout = QHBoxLayout(row_frame)
            r_layout.setContentsMargins(12, 6, 12, 6)
            lbl_str = QLabel(f"String {s_num}")
            lbl_str.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff; min-width: 80px;")
            r_layout.addWidget(lbl_str)
            badge = QLabel("—")
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(_BADGE_IDLE)
            r_layout.addWidget(badge)
            r_layout.addStretch()
            self.deck_layout.addWidget(row_frame)
            self.lane_cards.append(row_frame)
            self.lane_finger_badges.append(badge)
            self.lane_index[s_num] = idx

        if strings:
            self.lbl_strings.setText(", ".join(map(str, sorted(strings, reverse=True))))
        else:
            self.lbl_strings.setText("none")
        if not strings:
            hint = "Select 4 strings on the main fretboard."
        elif len(strings) < 4:
            hint = f"Only {len(strings)} strings selected: the lowest is doubled. Select 4 on the fretboard."
        elif len(self.pocket) > 4:
            hint = "Using the 4 lowest-pitched strings of the fretboard selection."
        else:
            hint = "Follows the strings selected on the main fretboard."
        self.lbl_strings_hint.setText(hint)

    # ---- state ----------------------------------------------------------------------------------
    def _on_pocket_changed(self, pocket):
        if set(pocket) == self.pocket:
            return
        self.pocket = set(pocket)
        self._rebuild_lanes()
        self._load_permutation_events(keep_position=True)

    def _on_perm_changed(self):
        self.current_perm_id = self.combo_perm.currentData()
        self._load_permutation_events(keep_position=True)

    def _on_tempo_changed(self, bpm: int):
        if self.timer.isActive():
            self.timer.setInterval(self._interval_ms())

    def _interval_ms(self) -> int:
        return int(round(60000.0 / max(40, self.spin_tempo.value())))

    def _load_permutation_events(self, keep_position: bool = False):
        position = self.current_event_idx
        self.events = PermutationEngine.generate_sequence(
            perm_id=self.current_perm_id,
            target_strings=sorted(self.pocket),
            cycles=8,
        )
        self.current_event_idx = position % len(self.events) if (keep_position and self.events) else 0

        _, _, pattern, _ = PermutationEngine.get_permutation_info(self.current_perm_id)
        for i, finger in enumerate(pattern):
            if i < len(self.step_indicators):
                self.step_indicators[i].setText(f"Beat {i+1}\n[{finger}]")

    # ---- transport ------------------------------------------------------------------------------
    def _toggle_workout(self):
        if self.timer.isActive():
            self.stop_workout()
        else:
            self.current_event_idx = 0
            self.timer.start(self._interval_ms())
            self._style_play_button(True)
            self._on_tick()

    def stop_workout(self):
        self.timer.stop()
        self._style_play_button(False)
        self._reset_lane_highlights()

    def _audio(self):
        return getattr(self.parent_window, "audio", None)

    def _play_click(self, accent: bool):
        sound = self.combo_click.currentText()
        if sound == CLICK_OFF:
            return
        if self.combo_click_mode.currentText() == "Beat 1 only" and not accent:
            return
        if sound == CLICK_CHIRP:
            if self._chirp is None:
                from ui.metronome_chirp import MetronomeChirp
                self._chirp = MetronomeChirp()
            self._chirp.play(is_downbeat=accent)
            return
        audio = self._audio()
        if audio is not None and hasattr(audio, "play_click"):
            audio.play_click(accent=accent, sound=sound)

    def _on_tick(self):
        if not self.events:
            return
        ev = self.events[self.current_event_idx]

        # Click and note are queued back to back on the MIDI scheduler, so they sound together.
        self._play_click(ev.is_downbeat)
        audio = self._audio()
        canvas = getattr(self.parent_window, "canvas", None)
        if audio is not None and canvas is not None:
            match_state = next((s for s in canvas.active_states if s.string_number == ev.string_number), None)
            if match_state:
                audio.play_note(match_state.active_midi, match_state.string_number)

        self._reset_lane_highlights()
        lane_idx = self.lane_index.get(ev.string_number)
        if lane_idx is not None:
            self.lane_cards[lane_idx].setStyleSheet(_LANE_ACTIVE)
            self.lane_finger_badges[lane_idx].setText(f"PICK: {ev.finger}")
            self.lane_finger_badges[lane_idx].setStyleSheet(_BADGE_ACTIVE)

        beat_in_bar = ev.step_index % 4
        for b_idx, pill in enumerate(self.step_indicators):
            pill.setStyleSheet(_PILL_ACTIVE if b_idx == beat_in_bar else _PILL_IDLE)

        self.current_event_idx = (self.current_event_idx + 1) % len(self.events)

    def _reset_lane_highlights(self):
        for card in self.lane_cards:
            card.setStyleSheet(_LANE_IDLE)
        for badge in self.lane_finger_badges:
            badge.setText("—")
            badge.setStyleSheet(_BADGE_IDLE)

    # ---- lifetime -------------------------------------------------------------------------------
    def hideEvent(self, event):
        if self.timer.isActive():
            self.stop_workout()
        super().hideEvent(event)

    def closeEvent(self, event):
        if self.timer.isActive():
            self.stop_workout()
        super().closeEvent(event)
