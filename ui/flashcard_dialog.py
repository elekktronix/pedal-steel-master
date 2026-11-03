"""UI Dialog for Jeff Newman's 'Steak or Biscuits' Timed Star Map Challenge."""

from typing import List, Optional, Set, Tuple
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.flashcard_engine import DrillResult, FlashcardEngine, FlashcardPrompt
from core.models import Neck
from core.star_map_engine import StarMapLandmark
from ui.voice_leader_dialog import MetronomeChirp


class FlashcardDrillDialog(QDialog):
    landmark_verified = Signal(int, set, set)  # fret, controllers, target_strings

    def __init__(self, neck: Neck, parent=None):
        super().__init__(parent)
        self.neck = neck
        self.setWindowTitle("Steak or Biscuits? — Newman Landmark Drill")
        self.resize(760, 520)

        self.time_limit: int = 30
        self.elapsed_sec: float = 0.0
        self.current_prompt: Optional[FlashcardPrompt] = None
        self.user_clicks: List[Tuple[int, Set[str]]] = []
        self.active_streak: int = 0

        self.metronome = MetronomeChirp()
        self.drill_timer = QTimer(self)
        self.drill_timer.setInterval(100)  # 100ms precision
        self.drill_timer.timeout.connect(self._on_timer_tick)

        self._init_ui()
        self._start_new_round()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # 1. Header & Configuration Strip
        top_h = QHBoxLayout()
        top_h.addWidget(QLabel("<b>Timer Limit:</b>"))

        self.combo_time = QComboBox()
        self.combo_time.addItem("30 Seconds (Newman Standard)", 30)
        self.combo_time.addItem("60 Seconds (Practice Mode)", 60)
        self.combo_time.addItem("15 Seconds (Pro Speed)", 15)
        self.combo_time.currentIndexChanged.connect(self._on_time_limit_changed)
        top_h.addWidget(self.combo_time)

        top_h.addStretch()

        self.lbl_streak = QLabel("Streak: <b>0</b> 🥩")
        self.lbl_streak.setStyleSheet("font-size: 13px; color: #28a745;")
        top_h.addWidget(self.lbl_streak)

        root.addLayout(top_h)

        # 2. Main Prompt Card
        self.prompt_card = QFrame()
        self.prompt_card.setStyleSheet("""
            QFrame {
                background-color: #1e2129;
                border: 2px solid #ffc107;
                border-radius: 8px;
            }
        """)
        card_l = QVBoxLayout(self.prompt_card)
        card_l.setContentsMargins(16, 12, 16, 12)
        card_l.setSpacing(4)

        self.lbl_card_title = QLabel("Find all landmarks left-to-right for:")
        self.lbl_card_title.setStyleSheet("font-size: 12px; color: #ced4da;")
        card_l.addWidget(self.lbl_card_title)

        self.lbl_chord_target = QLabel("C Major")
        self.lbl_chord_target.setStyleSheet("font-size: 28px; font-weight: bold; color: #ffde7a;")
        card_l.addWidget(self.lbl_chord_target)

        self.lbl_card_sub = QLabel("Open ➔ A&B ➔ A+LKL ➔ D Lever positions in exact fret order.")
        self.lbl_card_sub.setStyleSheet("font-size: 11px; color: #8b92a0;")
        card_l.addWidget(self.lbl_card_sub)

        root.addWidget(self.prompt_card)

        # 3. Countdown Progress Bar
        bar_layout = QVBoxLayout()
        self.lbl_timer = QLabel("Time Remaining: 30.0s")
        self.lbl_timer.setStyleSheet("font-weight: bold; color: #ffc107;")
        bar_layout.addWidget(self.lbl_timer)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 300)
        self.progress_bar.setValue(300)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #2b303c;
                border-radius: 4px;
                height: 10px;
            }
            QProgressBar::chunk {
                background-color: #28a745;
                border-radius: 4px;
            }
        """)
        bar_layout.addWidget(self.progress_bar)
        root.addLayout(bar_layout)

        # 4. Interactive Landmark Deck (Clickable Choices)
        deck_group = QGroupBox("Landmark Candidates (Click in Left-to-Right Fret Order)")
        self.deck_layout = QGridLayout(deck_group)
        self.deck_layout.setContentsMargins(10, 10, 10, 10)
        self.deck_layout.setSpacing(8)
        root.addWidget(deck_group, stretch=1)

        # 5. Result Banner & Feedback
        self.lbl_verdict = QLabel("Click the landmarks in order from left to right.")
        self.lbl_verdict.setAlignment(Qt.AlignCenter)
        self.lbl_verdict.setStyleSheet("font-weight: bold; font-size: 13px; color: #17a2b8; padding: 4px;")
        root.addWidget(self.lbl_verdict)

        # 6. Controls
        bottom_h = QHBoxLayout()
        self.btn_next = QPushButton("⏭ Next Chord")
        self.btn_next.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.btn_next.clicked.connect(self._start_new_round)
        bottom_h.addWidget(self.btn_next)

        bottom_h.addStretch()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        bottom_h.addWidget(btn_close)

        root.addLayout(bottom_h)

    def _on_time_limit_changed(self):
        self.time_limit = self.combo_time.currentData()
        self.progress_bar.setRange(0, self.time_limit * 10)
        self._start_new_round()

    def _start_new_round(self):
        self.drill_timer.stop()
        self.elapsed_sec = 0.0
        self.user_clicks.clear()

        self.current_prompt = FlashcardEngine.generate_prompt(time_limit=self.time_limit)
        self.lbl_chord_target.setText(f"{self.current_prompt.root_name} Major")
        self.lbl_timer.setText(f"Time Remaining: {self.time_limit:.1f}s")
        self.progress_bar.setRange(0, self.time_limit * 10)
        self.progress_bar.setValue(self.time_limit * 10)
        self.lbl_verdict.setText("Click the landmarks in order from left to right.")
        self.lbl_verdict.setStyleSheet("font-weight: bold; font-size: 13px; color: #17a2b8; padding: 4px;")

        self._populate_shuffled_deck()
        self.drill_timer.start()

    def _populate_shuffled_deck(self):
        while self.deck_layout.count() > 0:
            item = self.deck_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Gather true landmarks plus 2-3 distractors from adjacent frets
        correct_lms = list(self.current_prompt.ordered_landmarks)
        shuffled = list(correct_lms)
        import random
        random.shuffle(shuffled)

        col_max = 4
        for idx, lm in enumerate(shuffled):
            row = idx // col_max
            col = idx % col_max
            btn = QPushButton(lm.label)
            btn.setToolTip(f"{lm.description}\n{lm.strings_desc}")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #343a40;
                    color: #ffde7a;
                    font-weight: bold;
                    font-size: 12px;
                    border: 1.5px solid #6c757d;
                    border-radius: 6px;
                    min-height: 40px;
                }
                QPushButton:hover {
                    background-color: #495057;
                    border-color: #ffc107;
                }
            """)
            btn.clicked.connect(lambda _, l=lm, b=btn: self._on_landmark_clicked(l, b))
            self.deck_layout.addWidget(btn, row, col)

    def _on_landmark_clicked(self, lm: StarMapLandmark, btn: QPushButton):
        if not self.drill_timer.isActive():
            return

        self.user_clicks.append((lm.fret, set(lm.controllers)))
        self.metronome.play(is_downbeat=(len(self.user_clicks) == 1))

        # Transmit to main fretboard
        self.landmark_verified.emit(lm.fret, set(lm.controllers), lm.target_strings)

        # Visual button response
        expected_step = len(self.user_clicks) - 1
        if expected_step < len(self.current_prompt.ordered_landmarks):
            exp_target = self.current_prompt.ordered_landmarks[expected_step]
            if lm.fret == exp_target.fret and set(lm.controllers) == set(exp_target.controllers):
                btn.setEnabled(False)
                btn.setStyleSheet("background-color: #1e7e34; color: white; font-weight: bold; min-height: 40px; border-radius: 6px;")
            else:
                btn.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; min-height: 40px; border-radius: 6px;")

        # Check if all clicks gathered
        if len(self.user_clicks) >= len(self.current_prompt.ordered_landmarks):
            self._finalize_round()

    def _on_timer_tick(self):
        self.elapsed_sec += 0.1
        remaining = max(0.0, self.time_limit - self.elapsed_sec)
        self.lbl_timer.setText(f"Time Remaining: {remaining:.1f}s")
        self.progress_bar.setValue(int(remaining * 10))

        # Progress bar color transition
        if remaining < 5.0:
            self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #dc3545; border-radius: 4px; }")
        elif remaining < 10.0:
            self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #ffc107; border-radius: 4px; }")

        if remaining <= 0.0:
            self._finalize_round()

    def _finalize_round(self):
        self.drill_timer.stop()
        result = FlashcardEngine.evaluate_attempt(
            prompt=self.current_prompt,
            user_clicks=self.user_clicks,
            elapsed_sec=self.elapsed_sec,
            current_streak=self.active_streak,
        )

        self.active_streak = result.streak
        self.lbl_streak.setText(f"Streak: <b>{self.active_streak}</b> 🥩")
        self.lbl_verdict.setText(result.verdict)

        if result.is_success:
            self.lbl_verdict.setStyleSheet("font-weight: bold; font-size: 13px; color: #28a745; padding: 4px;")
        else:
            self.lbl_verdict.setStyleSheet("font-weight: bold; font-size: 13px; color: #dc3545; padding: 4px;")

    def closeEvent(self, event):
        if self.drill_timer.isActive():
            self.drill_timer.stop()
        super().closeEvent(event)