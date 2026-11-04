"""Voice Leader UI: progression manager, directional motion generator, tab generator,
cadence loader, roll-the-dice generator, and metronome chirp.
"""

import math
from pathlib import Path
import random
import struct
import tempfile
from typing import Any, Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QFont, QCursor
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.models import Neck
from core.theory import NOTE_NAMES_SHARP, NOTE_TO_SEMITONE, note_names, respell
from core.voice_leader import ChordProgression, VoiceLeadingConstraints, VoiceLeadingEngine
from core.voicing_solver import VoicingSolver


class MetronomeChirp:
    """Generates and plays crisp, authentic electronic woodblock clicks/chirps."""
    def __init__(self):
        self.sound_hi: Optional[QSoundEffect] = None
        self.sound_lo: Optional[QSoundEffect] = None
        self._init_sounds()

    def _init_sounds(self):
        temp_dir = Path(tempfile.gettempdir())
        path_hi = temp_dir / "psg_metronome_chirp_hi.wav"
        path_lo = temp_dir / "psg_metronome_chirp_lo.wav"

        if not path_hi.exists():
            self._write_chirp_wav(str(path_hi), base_freq=2600.0, duration_ms=18.0)
        if not path_lo.exists():
            self._write_chirp_wav(str(path_lo), base_freq=1500.0, duration_ms=14.0)

        self.sound_hi = QSoundEffect()
        self.sound_hi.setSource(QUrl.fromLocalFile(str(path_hi)))
        self.sound_hi.setVolume(0.95)

        self.sound_lo = QSoundEffect()
        self.sound_lo.setSource(QUrl.fromLocalFile(str(path_lo)))
        self.sound_lo.setVolume(0.75)

    def _write_chirp_wav(self, filepath: str, base_freq: float, duration_ms: float):
        sample_rate = 44100
        num_samples = int(sample_rate * (duration_ms / 1000.0))
        raw_data = bytearray()

        for i in range(num_samples):
            t = i / sample_rate
            decay = math.exp(-i / (num_samples * 0.22))
            sweep = base_freq * (1.0 + 0.9 * math.exp(-i / (num_samples * 0.12)))
            val = math.sin(2.0 * math.pi * sweep * t) * decay
            sample_val = int(max(-32767, min(32767, val * 30000)))
            raw_data.extend(struct.pack("<h", sample_val))

        data_size = len(raw_data)
        with open(filepath, "wb") as f:
            f.write(b"RIFF")
            f.write(struct.pack("<I", 36 + data_size))
            f.write(b"WAVE")
            f.write(b"fmt ")
            f.write(struct.pack("<I", 16))
            f.write(struct.pack("<H", 1))
            f.write(struct.pack("<H", 1))
            f.write(struct.pack("<I", sample_rate))
            f.write(struct.pack("<I", sample_rate * 2))
            f.write(struct.pack("<H", 2))
            f.write(struct.pack("<H", 16))
            f.write(b"data")
            f.write(struct.pack("<I", data_size))
            f.write(raw_data)

    def play(self, is_downbeat: bool):
        if is_downbeat and self.sound_hi:
            self.sound_hi.play()
        elif not is_downbeat and self.sound_lo:
            self.sound_lo.play()


class VoiceLeaderDialog(QDialog):
    voicing_path_applied = Signal(list)
    voicing_applied = Signal(int, list, list)  # fret, controllers, grip strings

    def __init__(self, neck: Neck, parent=None):
        super().__init__(parent)
        self.neck = neck
        self.setWindowTitle("Voice Leader - Directional Voicing & Tab Generator")
        self.resize(1120, 780)

        self.progression: ChordProgression = self._get_default_progression()
        self.solved_voicings: List[Optional[Any]] = []

        self.metronome = MetronomeChirp()
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._on_clock_tick)
        self.current_measure_idx = 0
        self.current_beat = 1

        self._init_ui()
        self._refresh_progression_strip()

    def set_neck(self, neck: Neck):
        """Updates the neck model and recalculates voicings for the active tuning."""
        self.neck = neck
        if self.isVisible():
            self._solve_trajectory("minimal")

    def _get_default_progression(self) -> ChordProgression:
        data = {
            "name": "Blue Bossa",
            "tonalCenter": "Cm",
            "tempo": 146,
            "measures": [
                {"id": 0, "slots": [{"beat": 1, "chord": {"root": "C", "type": "Minor 7"}}]},
                {"id": 1, "slots": [{"beat": 1, "chord": {"root": "C", "type": "Minor 7"}}]},
                {"id": 2, "slots": [{"beat": 1, "chord": {"root": "F", "type": "Minor 7"}}]},
                {"id": 3, "slots": [{"beat": 1, "chord": {"root": "F", "type": "Minor 7"}}]},
            ],
        }
        return ChordProgression.from_dict(data)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # 1. Top Section
        top_h = QHBoxLayout()

        box_music = QGroupBox("Music Settings")
        music_l = QGridLayout(box_music)
        music_l.setContentsMargins(8, 8, 8, 8)
        music_l.setSpacing(6)

        music_l.addWidget(QLabel("Key:"), 0, 0)
        self.combo_key = QComboBox()
        self.combo_key.addItems(note_names() + ["Cm", "Fm", "Am", "Dm", "Gm"])
        self.combo_key.setCurrentText(respell(self.progression.tonal_center))
        music_l.addWidget(self.combo_key, 0, 1)

        music_l.addWidget(QLabel("Time:"), 0, 2)
        self.btn_time = QPushButton("4/4")
        self.btn_time.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold;")
        music_l.addWidget(self.btn_time, 0, 3)

        music_l.addWidget(QLabel("Tempo:"), 1, 0)
        self.spin_tempo = QSpinBox()
        self.spin_tempo.setRange(40, 260)
        self.spin_tempo.setValue(self.progression.tempo)
        music_l.addWidget(self.spin_tempo, 1, 1)

        self.slider_tempo = QSlider(Qt.Horizontal)
        self.slider_tempo.setRange(40, 260)
        self.slider_tempo.setValue(self.progression.tempo)
        self.slider_tempo.valueChanged.connect(self.spin_tempo.setValue)
        self.spin_tempo.valueChanged.connect(self.slider_tempo.setValue)
        music_l.addWidget(self.slider_tempo, 1, 2, 1, 2)

        top_h.addWidget(box_music, stretch=4)

        box_play = QGroupBox("Playback & Metronome Settings")
        play_l = QHBoxLayout(box_play)
        play_l.setContentsMargins(8, 8, 8, 8)
        play_l.setSpacing(8)

        v_toggles = QVBoxLayout()
        self.btn_loop = QPushButton("Loop: OFF")
        self.btn_loop.setCheckable(True)
        self.btn_loop.toggled.connect(lambda c: self.btn_loop.setText("Loop: ON" if c else "Loop: OFF"))
        v_toggles.addWidget(self.btn_loop)

        self.cb_metronome = QCheckBox("🔔 Metronome Chirp")
        self.cb_metronome.setChecked(True)
        self.cb_metronome.setStyleSheet("font-weight: bold; color: #28a745;")
        v_toggles.addWidget(self.cb_metronome)
        play_l.addLayout(v_toggles)

        self.btn_play = QPushButton("▶\nPLAY")
        self.btn_play.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 6px;
                min-width: 60px;
                min-height: 50px;
            }
        """)
        self.btn_play.clicked.connect(self._toggle_playback)
        play_l.addWidget(self.btn_play)

        top_h.addWidget(box_play, stretch=4)

        box_io = QGroupBox("Load and Save")
        io_grid = QGridLayout(box_io)
        io_grid.setContentsMargins(6, 6, 6, 6)
        io_grid.setSpacing(4)

        btn_load_cp = QPushButton("Load CP")
        btn_load_cp.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; font-size: 11px;")
        btn_load_cp.clicked.connect(self._load_cp_file)
        io_grid.addWidget(btn_load_cp, 0, 0)

        btn_save_cp = QPushButton("Save CP")
        btn_save_cp.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; font-size: 11px;")
        btn_save_cp.clicked.connect(self._save_cp_file)
        io_grid.addWidget(btn_save_cp, 1, 0)

        btn_import_cp = QPushButton("Import CP")
        btn_import_cp.setStyleSheet("background-color: #6f42c1; color: white; font-weight: bold; font-size: 11px;")
        btn_import_cp.clicked.connect(self._load_cp_file)
        io_grid.addWidget(btn_import_cp, 2, 0)

        top_h.addWidget(box_io, stretch=2)
        root.addLayout(top_h)

        # 2. Middle Section: Timeline Strip
        mid_box = QGroupBox()
        mid_vbox = QVBoxLayout(mid_box)
        mid_vbox.setContentsMargins(8, 6, 8, 6)
        mid_vbox.setSpacing(6)

        header_row = QHBoxLayout()
        self.lbl_prog_title = QLabel(f"<b>Chord Progression Loaded:</b> {self.progression.name}")
        self.lbl_prog_title.setStyleSheet("font-size: 13px; color: #0d6efd;")
        header_row.addWidget(self.lbl_prog_title)

        header_row.addStretch()
        header_row.addWidget(QLabel("Measures:"))
        self.lbl_m_count = QLabel(f"<b>{len(self.progression.measures)}</b>")
        header_row.addWidget(self.lbl_m_count)

        btn_add_m = QPushButton("+")
        btn_add_m.setFixedSize(22, 22)
        btn_add_m.clicked.connect(lambda: self._adjust_measures(1))
        header_row.addWidget(btn_add_m)

        btn_sub_m = QPushButton("-")
        btn_sub_m.setFixedSize(22, 22)
        btn_sub_m.clicked.connect(lambda: self._adjust_measures(-1))
        header_row.addWidget(btn_sub_m)

        mid_vbox.addLayout(header_row)

        cadence_bar = QHBoxLayout()
        cadence_bar.addWidget(QLabel("<b>Cadences (Franklin):</b>"))

        btn_cad_maj = QPushButton("Major ii - V - I")
        btn_cad_maj.setStyleSheet("font-size: 11px; font-weight: bold; background-color: #343a40; color: #ffde7a;")
        btn_cad_maj.clicked.connect(self._load_cadence_major_251)
        cadence_bar.addWidget(btn_cad_maj)

        btn_cad_min = QPushButton("Minor iiø - Valt - i")
        btn_cad_min.setStyleSheet("font-size: 11px; font-weight: bold; background-color: #343a40; color: #ffde7a;")
        btn_cad_min.clicked.connect(self._load_cadence_minor_251)
        cadence_bar.addWidget(btn_cad_min)

        btn_cad_turn = QPushButton("Turnaround iii - vi - ii - V")
        btn_cad_turn.setStyleSheet("font-size: 11px; font-weight: bold; background-color: #343a40; color: #ffde7a;")
        btn_cad_turn.clicked.connect(self._load_cadence_turnaround)
        cadence_bar.addWidget(btn_cad_turn)

        btn_dice = QPushButton("🎲 Roll the Dice Challenge")
        btn_dice.setStyleSheet("font-size: 11px; font-weight: bold; background-color: #e06d10; color: white;")
        btn_dice.clicked.connect(self._roll_the_dice_cadence)
        cadence_bar.addWidget(btn_dice)

        cadence_bar.addStretch()
        mid_vbox.addLayout(cadence_bar)

        scroll_timeline = QScrollArea()
        scroll_timeline.setFixedHeight(95)
        scroll_timeline.setWidgetResizable(True)
        scroll_timeline.setFrameShape(QFrame.NoFrame)

        self.timeline_container = QWidget()
        self.timeline_layout = QHBoxLayout(self.timeline_container)
        self.timeline_layout.setContentsMargins(0, 0, 0, 0)
        self.timeline_layout.setSpacing(8)
        scroll_timeline.setWidget(self.timeline_container)

        mid_vbox.addWidget(scroll_timeline)
        root.addWidget(mid_box)

        # 3. Bottom Section: Controls
        vl_box = QGroupBox("Voice Leading Controls")
        vl_layout = QHBoxLayout(vl_box)
        vl_layout.setContentsMargins(12, 10, 12, 10)
        vl_layout.setSpacing(15)

        v_left = QVBoxLayout()
        v_left.addWidget(QLabel("<b>Fret Start:</b>"))
        self.spin_fret_start = QSpinBox()
        self.spin_fret_start.setRange(0, 22)
        self.spin_fret_start.setValue(0)
        v_left.addWidget(self.spin_fret_start)

        v_left.addSpacing(6)
        v_left.addWidget(QLabel("<b>Fret Jump Max:</b>"))
        self.spin_fret_jump = QSpinBox()
        self.spin_fret_jump.setRange(1, 12)
        self.spin_fret_jump.setValue(3)
        v_left.addWidget(self.spin_fret_jump)
        vl_layout.addLayout(v_left, stretch=2)

        v_center = QVBoxLayout()
        self.lbl_fret_range = QLabel("<b>Fret Range:</b> 0 - 12")
        v_center.addWidget(self.lbl_fret_range)

        h_range_spins = QHBoxLayout()
        h_range_spins.addWidget(QLabel("Min:"))
        self.spin_min_fret = QSpinBox()
        self.spin_min_fret.setRange(0, 20)
        self.spin_min_fret.setValue(0)
        self.spin_min_fret.valueChanged.connect(self._on_fret_boundary_changed)
        h_range_spins.addWidget(self.spin_min_fret)

        h_range_spins.addWidget(QLabel("Max:"))
        self.spin_max_fret = QSpinBox()
        self.spin_max_fret.setRange(2, 24)
        self.spin_max_fret.setValue(12)
        self.spin_max_fret.valueChanged.connect(self._on_fret_boundary_changed)
        h_range_spins.addWidget(self.spin_max_fret)
        v_center.addLayout(h_range_spins)

        v_center.addSpacing(6)
        self.lbl_status = QLabel("Trajectory: Minimal Bar Travel")
        self.lbl_status.setStyleSheet("color: #0d6efd; font-weight: bold;")
        v_center.addWidget(self.lbl_status)
        vl_layout.addLayout(v_center, stretch=3)

        v_actions = QGridLayout()
        v_actions.setSpacing(6)

        btn_gen_tab = QPushButton("Gen Tab")
        btn_gen_tab.setStyleSheet("background-color: #df9e12; color: white; font-weight: bold; height: 32px;")
        btn_gen_tab.clicked.connect(self._generate_tablature)
        v_actions.addWidget(btn_gen_tab, 0, 0)

        btn_random = QPushButton("🎲 Random")
        btn_random.setStyleSheet("background-color: #e06d10; color: white; font-weight: bold; height: 32px;")
        btn_random.clicked.connect(lambda: self._solve_trajectory("random"))
        v_actions.addWidget(btn_random, 0, 1)

        btn_up = QPushButton("▲ Up")
        btn_up.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold; height: 32px;")
        btn_up.clicked.connect(lambda: self._solve_trajectory("up"))
        v_actions.addWidget(btn_up, 1, 0)

        btn_down = QPushButton("▼ Down")
        btn_down.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; height: 32px;")
        btn_down.clicked.connect(lambda: self._solve_trajectory("down"))
        v_actions.addWidget(btn_down, 1, 1)

        btn_up_down = QPushButton("Up-Down ↗↘")
        btn_up_down.setStyleSheet("background-color: #4a90e2; color: white; font-weight: bold; height: 30px;")
        btn_up_down.clicked.connect(lambda: self._solve_trajectory("up_down"))
        v_actions.addWidget(btn_up_down, 2, 0)

        btn_down_up = QPushButton("Down-Up ↘↗")
        btn_down_up.setStyleSheet("background-color: #48bb78; color: white; font-weight: bold; height: 30px;")
        btn_down_up.clicked.connect(lambda: self._solve_trajectory("down_up"))
        v_actions.addWidget(btn_down_up, 2, 1)

        vl_layout.addLayout(v_actions, stretch=4)
        root.addWidget(vl_box)

        # 4. Solved Voicing Path Solution Strip
        self.solution_frame = QGroupBox("Solved Voicing Path across Progression (Click any chip to jump)")
        self.solution_layout = QHBoxLayout(self.solution_frame)
        self.solution_layout.setContentsMargins(8, 6, 8, 6)
        self.solution_layout.setSpacing(8)
        root.addWidget(self.solution_frame)

    def _on_fret_boundary_changed(self):
        mn = self.spin_min_fret.value()
        mx = self.spin_max_fret.value()
        if mn > mx:
            self.spin_max_fret.setValue(mn)
            mx = mn
        self.lbl_fret_range.setText(f"<b>Fret Range:</b> {mn} - {mx}")

    def _refresh_progression_strip(self):
        while self.timeline_layout.count() > 0:
            item = self.timeline_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.lbl_prog_title.setText(f"<b>Chord Progression Loaded:</b> {self.progression.name}")
        self.lbl_m_count.setText(f"<b>{len(self.progression.measures)}</b>")
        self.combo_key.setCurrentText(self.progression.tonal_center)
        self.spin_tempo.setValue(self.progression.tempo)

        for m_idx, measure in enumerate(self.progression.measures):
            m_card = QFrame()
            m_card.setStyleSheet("""
                QFrame {
                    background-color: #fff9e6;
                    border: 1.5px solid #ebd79b;
                    border-radius: 6px;
                }
            """)
            m_h = QHBoxLayout(m_card)
            m_h.setContentsMargins(6, 4, 6, 4)
            m_h.setSpacing(6)

            lbl_num = QLabel(f"<b>{m_idx + 1}</b>")
            lbl_num.setStyleSheet("color: #d9534f; font-size: 11px;")
            m_h.addWidget(lbl_num)

            for b in range(1, 5):
                slot = next((s for s in measure.slots if s.beat == b), None)
                if slot and slot.root and slot.chord_type:
                    tag = f"{slot.root}{'m7' if 'Minor' in slot.chord_type else '7' if 'Dominant' in slot.chord_type else slot.chord_type[:3]}"
                    lbl_beat = QLabel(tag)
                    lbl_beat.setAlignment(Qt.AlignCenter)
                    lbl_beat.setStyleSheet("""
                        background-color: #0d6efd;
                        color: white;
                        font-weight: bold;
                        border-radius: 12px;
                        padding: 4px 8px;
                        font-size: 10px;
                    """)
                    m_h.addWidget(lbl_beat)
                else:
                    lbl_empty = QLabel(f"{b}")
                    lbl_empty.setAlignment(Qt.AlignCenter)
                    lbl_empty.setStyleSheet("""
                        color: #b5b5b5;
                        border: 1px dashed #d0d0d0;
                        border-radius: 11px;
                        min-width: 20px;
                        min-height: 20px;
                        font-size: 9px;
                    """)
                    m_h.addWidget(lbl_empty)

            self.timeline_layout.addWidget(m_card)

        self.timeline_layout.addStretch()

    def _solve_trajectory(self, trajectory: str):
        self.lbl_status.setText(f"Trajectory: {trajectory.upper()}")

        constraints = VoiceLeadingConstraints(
            min_fret=self.spin_min_fret.value(),
            max_fret=self.spin_max_fret.value(),
            max_fret_jump=self.spin_fret_jump.value(),
            trajectory=trajectory,
            start_fret=self.spin_fret_start.value(),
        )

        self.solved_voicings = VoiceLeadingEngine.solve_progression(
            neck=self.neck,
            progression=self.progression,
            constraints=constraints,
        )

        self._render_solution_strip()

    def _render_solution_strip(self):
        while self.solution_layout.count() > 0:
            item = self.solution_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        for idx, (m, v) in enumerate(zip(self.progression.measures, self.solved_voicings)):
            chip = QPushButton()
            chip.setCursor(QCursor(Qt.PointingHandCursor))
            ch_name = f"{m.primary_chord[0]} {m.primary_chord[1][:3]}" if m.primary_chord else "Rest"

            if v:
                lev = "+".join(v.engaged_levers) if v.engaged_levers else "Open"
                chip.setText(f"M{idx + 1}: {ch_name}\nFret {v.fret} ({lev})")
                chip.setStyleSheet("""
                    QPushButton {
                        background-color: #eaf5ea;
                        border: 1.5px solid #28a745;
                        border-radius: 6px;
                        color: #1e7e34;
                        font-weight: bold;
                        font-size: 11px;
                        padding: 6px 10px;
                        text-align: center;
                    }
                    QPushButton:hover {
                        background-color: #28a745;
                        color: white;
                    }
                """)
                chip.clicked.connect(lambda _, voicing=v: self._apply_single_voicing_to_main(voicing))
            else:
                chip.setText(f"M{idx + 1}: {ch_name}\nNo match")
                chip.setStyleSheet("""
                    QPushButton {
                        background-color: #f8f9fa;
                        border: 1px solid #ced4da;
                        border-radius: 6px;
                        color: #6c757d;
                        font-size: 11px;
                        padding: 6px 10px;
                    }
                """)

            self.solution_layout.addWidget(chip)

        self.solution_layout.addStretch()

    def _apply_single_voicing_to_main(self, v):
        """Immediately transmits the selected voicing to the main visualizer."""
        if not v:
            return
        # MainWindow.apply_stance updates canvas, lever buttons, lever panel state and audio (D-04).
        self.voicing_applied.emit(v.fret, list(v.engaged_levers), list(v.grip_strings))

    def _generate_tablature(self):
        if not self.solved_voicings or all(v is None for v in self.solved_voicings):
            self._solve_trajectory("minimal")

        active_pairs = [(i, v) for i, v in enumerate(self.solved_voicings) if v is not None]
        self.voicing_path_applied.emit(active_pairs)
        QMessageBox.information(
            self,
            "Tablature & Sequence Generated",
            f"Voice leading path with {len(active_pairs)} voicings loaded into Sequencer.",
        )

    def _toggle_playback(self):
        if self.play_timer.isActive():
            self.play_timer.stop()
            self.btn_play.setText("▶\nPLAY")
            self.btn_play.setStyleSheet("background-color: #28a745; color: white; font-size: 14px; font-weight: bold;")
        else:
            if not self.solved_voicings:
                self._solve_trajectory("minimal")
            self.current_measure_idx = 0
            self.current_beat = 1

            tempo = max(40, self.spin_tempo.value())
            beat_interval_ms = int(60000.0 / tempo)
            self.play_timer.start(beat_interval_ms)

            self.btn_play.setText("⏹\nSTOP")
            self.btn_play.setStyleSheet("background-color: #dc3545; color: white; font-size: 14px; font-weight: bold;")
            self._on_clock_tick()

    def _on_clock_tick(self):
        if self.cb_metronome.isChecked():
            self.metronome.play(is_downbeat=(self.current_beat == 1))

        if self.current_beat == 1:
            if self.current_measure_idx >= len(self.solved_voicings):
                if self.btn_loop.isChecked():
                    self.current_measure_idx = 0
                else:
                    self._toggle_playback()
                    return

            v = self.solved_voicings[self.current_measure_idx]
            if v:
                self._apply_single_voicing_to_main(v)

            self.current_measure_idx += 1

        self.current_beat = (self.current_beat % 4) + 1

    def _load_cadence_major_251(self):
        key = self.combo_key.currentText().replace("m", "").strip() or "C"
        key_pc = NOTE_TO_SEMITONE.get(key, 0)
        two_root = NOTE_NAMES_SHARP[(key_pc + 2) % 12]
        five_root = NOTE_NAMES_SHARP[(key_pc + 7) % 12]

        prog_data = {
            "name": f"{key} Major ii - V - I Cadence",
            "tonalCenter": key,
            "tempo": self.spin_tempo.value(),
            "measures": [
                {"id": 0, "slots": [{"beat": 1, "chord": {"root": two_root, "type": "Minor 7"}}]},
                {"id": 1, "slots": [{"beat": 1, "chord": {"root": five_root, "type": "Dominant 7"}}]},
                {"id": 2, "slots": [{"beat": 1, "chord": {"root": key, "type": "Major 7"}}]},
                {"id": 3, "slots": [{"beat": 1, "chord": {"root": key, "type": "Major 7"}}]},
            ],
        }
        self.progression = ChordProgression.from_dict(prog_data)
        self._refresh_progression_strip()
        self._solve_trajectory("minimal")

    def _load_cadence_minor_251(self):
        raw_key = self.combo_key.currentText().replace("m", "").strip() or "C"
        key_pc = NOTE_TO_SEMITONE.get(raw_key, 0)
        two_root = NOTE_NAMES_SHARP[(key_pc + 2) % 12]
        five_root = NOTE_NAMES_SHARP[(key_pc + 7) % 12]

        prog_data = {
            "name": f"{raw_key}m Minor iiø - Valt - i Cadence",
            "tonalCenter": f"{raw_key}m",
            "tempo": self.spin_tempo.value(),
            "measures": [
                {"id": 0, "slots": [{"beat": 1, "chord": {"root": two_root, "type": "Half-Diminished"}}]},
                {"id": 1, "slots": [{"beat": 1, "chord": {"root": five_root, "type": "Dominant 7"}}]},
                {"id": 2, "slots": [{"beat": 1, "chord": {"root": raw_key, "type": "Minor 7"}}]},
                {"id": 3, "slots": [{"beat": 1, "chord": {"root": raw_key, "type": "Minor 7"}}]},
            ],
        }
        self.progression = ChordProgression.from_dict(prog_data)
        self._refresh_progression_strip()
        self._solve_trajectory("minimal")

    def _load_cadence_turnaround(self):
        raw_key = self.combo_key.currentText().replace("m", "").strip() or "C"
        key_pc = NOTE_TO_SEMITONE.get(raw_key, 0)
        three_root = NOTE_NAMES_SHARP[(key_pc + 4) % 12]
        six_root = NOTE_NAMES_SHARP[(key_pc + 9) % 12]
        two_root = NOTE_NAMES_SHARP[(key_pc + 2) % 12]
        five_root = NOTE_NAMES_SHARP[(key_pc + 7) % 12]

        prog_data = {
            "name": f"{raw_key} Jazz Turnaround (iii - vi - ii - V)",
            "tonalCenter": raw_key,
            "tempo": self.spin_tempo.value(),
            "measures": [
                {"id": 0, "slots": [{"beat": 1, "chord": {"root": three_root, "type": "Minor 7"}}]},
                {"id": 1, "slots": [{"beat": 1, "chord": {"root": six_root, "type": "Dominant 7"}}]},
                {"id": 2, "slots": [{"beat": 1, "chord": {"root": two_root, "type": "Minor 7"}}]},
                {"id": 3, "slots": [{"beat": 1, "chord": {"root": five_root, "type": "Dominant 7"}}]},
            ],
        }
        self.progression = ChordProgression.from_dict(prog_data)
        self._refresh_progression_strip()
        self._solve_trajectory("minimal")

    def _roll_the_dice_cadence(self):
        raw_key = self.combo_key.currentText().replace("m", "").strip()
        if not raw_key or raw_key not in NOTE_TO_SEMITONE:
            raw_key = "G"

        key_pc = NOTE_TO_SEMITONE[raw_key]

        scale_degree_offsets = {
            1: (0, "Major"),
            2: (2, "Minor 7"),
            3: (4, "Minor 7"),
            4: (5, "Major 7"),
            5: (7, "Dominant 7"),
            6: (9, "Minor 7"),
        }

        die1 = random.randint(1, 6)
        die2 = random.randint(1, 6)

        semi1, type1 = scale_degree_offsets[die1]
        semi2, type2 = scale_degree_offsets[die2]
        root1 = NOTE_NAMES_SHARP[(key_pc + semi1) % 12]
        root2 = NOTE_NAMES_SHARP[(key_pc + semi2) % 12]

        v1_root = NOTE_NAMES_SHARP[(NOTE_TO_SEMITONE[root1] + 7) % 12]
        v2_root = NOTE_NAMES_SHARP[(NOTE_TO_SEMITONE[root2] + 7) % 12]

        prog_data = {
            "name": f"Dice #{die1} & #{die2} ({raw_key} Cadence)",
            "tonalCenter": raw_key,
            "tempo": self.spin_tempo.value(),
            "measures": [
                {"id": 0, "slots": [{"beat": 1, "chord": {"root": v1_root, "type": "Dominant 7"}}]},
                {"id": 1, "slots": [{"beat": 1, "chord": {"root": root1, "type": type1}}]},
                {"id": 2, "slots": [{"beat": 1, "chord": {"root": v2_root, "type": "Dominant 7"}}]},
                {"id": 3, "slots": [{"beat": 1, "chord": {"root": root2, "type": type2}}]},
            ],
        }
        self.progression = ChordProgression.from_dict(prog_data)
        self._refresh_progression_strip()
        self._solve_trajectory("minimal")

        QMessageBox.information(
            self,
            "Dice Rolled!",
            f"Key of {raw_key} — Rolled Degrees: #{die1} and #{die2}\n\n"
            f"Measures 1-2: {v1_root}7  ➔  {root1} ({type1})\n"
            f"Measures 3-4: {v2_root}7  ➔  {root2} ({type2})",
        )

    def _load_cp_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Chord Progression (.cp / .json)", "", "Chord Progression (*.cp *.json *.cprog);;All Files (*.*)"
        )
        if not filepath:
            return
        try:
            self.progression = ChordProgression.from_json_file(filepath)
            self._refresh_progression_strip()
            self._solve_trajectory("minimal")
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load progression file:\n{str(e)}")

    def _save_cp_file(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Chord Progression (.cp)", f"{self.progression.name}.cp", "Chord Progression (*.cp *.json *.cprog)"
        )
        if not filepath:
            return
        try:
            data = {
                "name": self.progression.name,
                "tonalCenter": self.combo_key.currentText(),
                "tempo": self.spin_tempo.value(),
                "measures": [
                    {
                        "id": m.measure_id,
                        "slots": [
                            {"beat": s.beat, "chord": {"root": s.root, "type": s.chord_type} if s.root else None}
                            for s in m.slots
                        ],
                    }
                    for m in self.progression.measures
                ],
            }
            import json
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            QMessageBox.information(self, "Saved", f"Progression saved to {filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save progression:\n{str(e)}")

    def _adjust_measures(self, delta: int):
        new_count = len(self.progression.measures) + delta
        if new_count < 1:
            return
        if delta > 0:
            from core.voice_leader import ChordSlot, ProgressionMeasure
            self.progression.measures.append(
                ProgressionMeasure(
                    measure_id=new_count - 1,
                    slots=[ChordSlot(beat=1, root="C", chord_type="Major")] + [ChordSlot(beat=b) for b in range(2, 5)],
                )
            )
        else:
            self.progression.measures.pop()
        self._refresh_progression_strip()