"""Interactive workout dialog for Paul Franklin's 24 Right-Hand Picking Permutations."""

from typing import List, Optional, Set
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
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
    QWidget,
)

from core.models import Neck
from core.permutation_engine import FRANKLIN_24_PERMUTATIONS, PermutationEngine, PickEvent
from ui.voice_leader_dialog import MetronomeChirp


class PermutationTrainerDialog(QDialog):
    def __init__(self, neck: Neck, active_pocket: Set[int], parent=None):
        super().__init__(parent)
        self.neck = neck
        self.parent_window = parent
        self.setWindowTitle("Franklin 24 Right-Hand Picking & Blocking Trainer")
        self.resize(840, 560)

        # Ensure we have 4 valid strings (default to Franklin Group 2: 4, 5, 6, 8)
        pocket_list = sorted(list(active_pocket), reverse=True)
        if len(pocket_list) >= 4:
            self.active_strings = pocket_list[:4]
        else:
            self.active_strings = [8, 6, 5, 4]

        self.current_perm_id = 2  # Default to T-I-M-T Standard Forward Roll
        self.events: List[PickEvent] = []
        self.current_event_idx = 0

        self.metronome = MetronomeChirp()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)

        self._init_ui()
        self._load_permutation_events()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # 1. Header & Permutation Selector
        top_group = QGroupBox("Select Right-Hand Permutation (Paul Franklin, pp. 37-39)")
        top_l = QGridLayout(top_group)
        top_l.setContentsMargins(10, 8, 10, 8)
        top_l.setSpacing(8)

        top_l.addWidget(QLabel("<b>Pattern:</b>"), 0, 0)
        self.combo_perm = QComboBox()
        self.combo_perm.setMinimumWidth(320)
        for pid, (pattern_str, name, _) in FRANKLIN_24_PERMUTATIONS.items():
            self.combo_perm.addItem(f"#{pid:02d}:  {pattern_str}  ({name})", pid)
        self.combo_perm.setCurrentIndex(1)  # Permutation #2
        self.combo_perm.currentIndexChanged.connect(self._on_perm_changed)
        top_l.addWidget(self.combo_perm, 0, 1)

        top_l.addWidget(QLabel("<b>Target Strings:</b>"), 0, 2)
        self.lbl_strings = QLabel(f"Strings: {', '.join(map(str, sorted(self.active_strings)))}")
        self.lbl_strings.setStyleSheet("font-weight: bold; color: #0d6efd;")
        top_l.addWidget(self.lbl_strings, 0, 3)

        root.addWidget(top_group)

        # 2. Visual Picking Deck (Animated 4-String Lane)
        self.deck_box = QGroupBox("Right-Hand Pick & Blocking Visualizer")
        deck_l = QVBoxLayout(self.deck_box)
        deck_l.setContentsMargins(12, 16, 12, 16)
        deck_l.setSpacing(12)

        self.lane_cards: List[QFrame] = []
        self.lane_labels: List[QLabel] = []
        self.lane_finger_badges: List[QLabel] = []

        # Render 4 string rows (top string to lowest string)
        for s_num in sorted(self.active_strings):
            row_frame = QFrame()
            row_frame.setStyleSheet("""
                QFrame {
                    background-color: #2b303c;
                    border: 1.5px solid #4a5263;
                    border-radius: 6px;
                }
            """)
            r_layout = QHBoxLayout(row_frame)
            r_layout.setContentsMargins(12, 6, 12, 6)

            lbl_str = QLabel(f"String {s_num}")
            lbl_str.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff; min-width: 80px;")
            r_layout.addWidget(lbl_str)

            lbl_finger = QLabel("—")
            lbl_finger.setAlignment(Qt.AlignCenter)
            lbl_finger.setStyleSheet("""
                background-color: #1a1d24;
                color: #6c757d;
                font-weight: bold;
                font-size: 16px;
                border-radius: 4px;
                min-width: 50px;
                padding: 4px;
            """)
            r_layout.addWidget(lbl_finger)

            r_layout.addStretch()
            deck_l.addWidget(row_frame)

            self.lane_cards.append(row_frame)
            self.lane_labels.append(lbl_str)
            self.lane_finger_badges.append(lbl_finger)

        root.addWidget(self.deck_box, stretch=1)

        # 3. Step Pattern Strip (Beat Indicators)
        self.step_box = QFrame()
        self.step_box.setStyleSheet("background-color: #1e2129; border-radius: 6px; padding: 6px;")
        self.step_layout = QHBoxLayout(self.step_box)
        self.step_layout.setContentsMargins(8, 4, 8, 4)
        self.step_layout.setSpacing(8)

        self.step_indicators: List[QLabel] = []
        for i in range(4):
            lbl_step = QLabel(f"Beat {i+1}")
            lbl_step.setAlignment(Qt.AlignCenter)
            lbl_step.setStyleSheet("""
                background-color: #2b303c;
                color: #adb5bd;
                font-weight: bold;
                font-size: 11px;
                border-radius: 4px;
                padding: 6px 12px;
            """)
            self.step_layout.addWidget(lbl_step)
            self.step_indicators.append(lbl_step)

        root.addWidget(self.step_box)

        # 4. Transport & Metronome Controls
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
        ctrl_h.addWidget(self.slider_tempo, stretch=1)

        ctrl_h.addSpacing(15)

        self.btn_play = QPushButton("▶ Start Workout")
        self.btn_play.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                font-size: 13px;
                min-height: 34px;
                padding: 0 20px;
                border-radius: 4px;
            }
        """)
        self.btn_play.clicked.connect(self._toggle_workout)
        ctrl_h.addWidget(self.btn_play)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        ctrl_h.addWidget(btn_close)

        root.addLayout(ctrl_h)

    def _on_perm_changed(self):
        self.current_perm_id = self.combo_perm.currentData()
        self._load_permutation_events()

    def _load_permutation_events(self):
        self.events = PermutationEngine.generate_sequence(
            perm_id=self.current_perm_id,
            target_strings=self.active_strings,
            cycles=8,
        )
        self.current_event_idx = 0

        # Update pattern string indicators
        _, _, pattern = PermutationEngine.get_permutation_info(self.current_perm_id)
        for i, finger in enumerate(pattern):
            if i < len(self.step_indicators):
                self.step_indicators[i].setText(f"Beat {i+1}\n[{finger}]")

    def _toggle_workout(self):
        if self.timer.isActive():
            self.timer.stop()
            self.btn_play.setText("▶ Start Workout")
            self.btn_play.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; min-height: 34px;")
            self._reset_lane_highlights()
        else:
            self.current_event_idx = 0
            bpm = max(40, self.spin_tempo.value())
            interval_ms = int(60000.0 / bpm)
            self.timer.start(interval_ms)
            self.btn_play.setText("⏹ Stop")
            self.btn_play.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; min-height: 34px;")
            self._on_tick()

    def _on_tick(self):
        if not self.events:
            return

        ev = self.events[self.current_event_idx]

        # 1. Metronome audio click
        self.metronome.play(is_downbeat=ev.is_downbeat)

        # 2. Sound individual plucked string note via audio engine
        if self.parent_window and hasattr(self.parent_window, "audio") and hasattr(self.parent_window, "canvas"):
            states = self.parent_window.canvas.active_states
            match_state = next((s for s in states if s.string_number == ev.string_number), None)
            if match_state:
                self.parent_window.audio.play_note(match_state.active_midi, match_state.string_number)

        # 3. Update Visual Highlight Lane
        sorted_strs = sorted(self.active_strings)
        try:
            lane_idx = sorted_strs.index(ev.string_number)
        except ValueError:
            lane_idx = 0

        self._reset_lane_highlights()

        # Highlight current active string card
        self.lane_cards[lane_idx].setStyleSheet("""
            QFrame {
                background-color: #49391d;
                border: 2px solid #ffc107;
                border-radius: 6px;
            }
        """)
        self.lane_finger_badges[lane_idx].setText(f"PICK: {ev.finger}")
        self.lane_finger_badges[lane_idx].setStyleSheet("""
            background-color: #ffc107;
            color: #000000;
            font-weight: bold;
            font-size: 16px;
            border-radius: 4px;
            min-width: 80px;
            padding: 4px;
        """)

        # Highlight beat step pill
        beat_in_bar = ev.step_index % 4
        for b_idx, pill in enumerate(self.step_indicators):
            if b_idx == beat_in_bar:
                pill.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
            else:
                pill.setStyleSheet("background-color: #2b303c; color: #adb5bd; font-weight: bold; padding: 6px 12px; border-radius: 4px;")

        self.current_event_idx = (self.current_event_idx + 1) % len(self.events)

    def _reset_lane_highlights(self):
        for card in self.lane_cards:
            card.setStyleSheet("""
                QFrame {
                    background-color: #2b303c;
                    border: 1.5px solid #4a5263;
                    border-radius: 6px;
                }
            """)
        for badge in self.lane_finger_badges:
            badge.setText("—")
            badge.setStyleSheet("""
                background-color: #1a1d24;
                color: #6c757d;
                font-weight: bold;
                font-size: 16px;
                border-radius: 4px;
                min-width: 50px;
                padding: 4px;
            """)

    def closeEvent(self, event):
        if self.timer.isActive():
            self.timer.stop()
        super().closeEvent(event)