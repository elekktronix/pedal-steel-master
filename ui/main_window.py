"""Streamlined coordinator window with permanent Up-The-Neck ribbon,
24-chord major/minor selector, multi-tuning C6/E9 engine, and clean menu delegation.
"""

import logging
from pathlib import Path
from typing import Optional, Set

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.audio import MidiAudioEngine, compute_newman_cents
from core.models import Neck, NeckType, SteelGuitar, migrate_half_stop_tokens
from core.presets import build_standard_d10_guitar
from core.profile_manager import ProfileManager
from core.settings import load_settings, save_settings
from core.star_map_engine import ENHARMONIC_FLAT_NAMES, StarMapEngine, StarMapLandmark
from core.voicing_solver import VoicingSolver
from ui.circle_of_fifths_widget import CircleOfFifthsWidget
from ui.copedant_editor_dialog import CopedantEditorDialog
from ui.fretboard_canvas import FretboardCanvas
from ui.grip_pocket_bar import GripPocketBar
from ui.harmonic_target_panel import HarmonicTargetPanel
from ui.lever_panel import LeverTogglePanel
from ui.main_menu_builder import MainMenuBuilder
from ui.manage_profiles_dialog import ProfileManagerDialog
from ui.progression_panel import ProgressionSequencerWidget
from ui.relative_moves_widget import RelativeMovesWidget
from ui.scale_finder_widget import ScaleFinderWidget
from ui.stance_chord_inspector_dialog import StanceChordInspectorDialog
from ui.themes import DARK_THEME_QSS, LIGHT_THEME_QSS
from ui.voicing_dialog import VoicingFinderWidget
from core.theory import to_root_name

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pedal Steel Guitar Copedant & Voicing Visualizer")
        self.resize(1540, 920)
        self.setMinimumWidth(1180)

        ProfileManager.ensure_storage_dir()
        self.settings = load_settings()

        self.audio = MidiAudioEngine()
        self.audio.set_compensated_temperament(self.settings.get("use_newman_tuning", False))
        self._batch_depth = 0  # >0 while apply_stance() is running; defers dependent refreshes

        # Load persisted guitar setup if present, otherwise build standard D10
        storage_dir = ProfileManager.ensure_storage_dir() or getattr(
            ProfileManager, "STORAGE_DIR", Path.home() / ".psg_visualizer" / "profiles"
        )
        active_setup_path = storage_dir / "active_guitar_setup.json"
        if active_setup_path.exists():
            try:
                self.guitar = SteelGuitar.load_from_file(str(active_setup_path))
            except Exception:
                log.exception("Could not load %s; using factory presets", active_setup_path)
                self.guitar = build_standard_d10_guitar()
        else:
            self.guitar = build_standard_d10_guitar()
        # Persisted setups predate engagement-aware half-stop splits ("P3HS" -> "P3_HALF", D-08).
        for neck in self.guitar.necks:
            migrate_half_stop_tokens(neck)

        self.current_neck_idx: int = 0
        self.voice_leader_dlg = None
        self.stance_inspector_dlg = None

        self._init_ui()
        self._init_sequencer_dock()
        self._init_popout_windows()
        MainMenuBuilder.build_menubar(self)
        self._apply_theme(self.settings.get("theme", "dark"))
        self._load_current_neck()
        self._refresh_copedant_dropdown()
        self._update_star_map_ribbon()
        self._update_relative_moves_hub()

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(12, 6, 12, 8)
        root_layout.setSpacing(5)

        # 1. Row 1: Tuning Selector & View Toggles
        row1_bar = QHBoxLayout()
        row1_bar.setSpacing(6)

        row1_bar.addWidget(QLabel("<b>Tuning:</b>"))
        self.combo_copedant = QComboBox()
        self.combo_copedant.setMinimumWidth(220)
        self.combo_copedant.currentIndexChanged.connect(self._on_copedant_dropdown_changed)
        row1_bar.addWidget(self.combo_copedant)

        self.btn_edit_copedant = QPushButton("⚙️ Matrix")
        self.btn_edit_copedant.setStyleSheet("background-color: #343a40; color: white; font-weight: bold; padding: 4px 10px;")
        self.btn_edit_copedant.clicked.connect(self._open_copedant_editor)
        row1_bar.addWidget(self.btn_edit_copedant)

        self.btn_manage_profiles = QPushButton("📁 Profiles")
        self.btn_manage_profiles.setStyleSheet("padding: 4px 10px;")
        self.btn_manage_profiles.clicked.connect(self._open_profile_manager)
        row1_bar.addWidget(self.btn_manage_profiles)

        row1_bar.addStretch()

        self.btn_toggle_display = QPushButton("🎯 Intervals (R-3-5)")
        self.btn_toggle_display.setStyleSheet("font-weight: bold; padding: 4px 10px;")
        self.btn_toggle_display.clicked.connect(self._toggle_display_mode_btn)
        row1_bar.addWidget(self.btn_toggle_display)

        self.btn_toggle_nns = QPushButton("🔢 NNS [1-4-5]")
        self.btn_toggle_nns.setCheckable(True)
        self.btn_toggle_nns.setChecked(self.settings.get("show_nashville", True))
        self.btn_toggle_nns.setStyleSheet("""
            QPushButton { font-weight: bold; padding: 4px 10px; }
            QPushButton:checked { background-color: #20c997; color: #000000; }
        """)
        self.btn_toggle_nns.toggled.connect(self._toggle_nns_button)
        row1_bar.addWidget(self.btn_toggle_nns)

        row1_bar.addSpacing(6)
        self.btn_toggle_seq = QPushButton("🎼 Sequencer")
        self.btn_toggle_seq.setCheckable(True)
        self.btn_toggle_seq.setChecked(False)
        self.btn_toggle_seq.setStyleSheet("padding: 4px 12px; font-weight: bold;")
        self.btn_toggle_seq.clicked.connect(self._toggle_sequencer_visibility)
        row1_bar.addWidget(self.btn_toggle_seq)
        root_layout.addLayout(row1_bar)

        # 2. Row 2: Standardized Theory Tools & Method Drill Ribbons
        row2_frame = QFrame()
        row2_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1d24;
                border: 1px solid #343a40;
                border-radius: 6px;
            }
        """)
        row2_bar = QHBoxLayout(row2_frame)
        row2_bar.setContentsMargins(8, 4, 8, 4)
        row2_bar.setSpacing(6)

        tool_btn_style = """
            QPushButton {
                background-color: #2b303c;
                color: #e0e6ed;
                font-size: 11px;
                font-weight: bold;
                padding: 5px 11px;
                border: 1px solid #495057;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3b4252;
                border-color: #0d6efd;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #1e222a;
            }
        """

        lbl_theory = QLabel("<b>Theory Tools:</b>")
        lbl_theory.setStyleSheet("color: #0dcaf0; font-size: 11px;")
        row2_bar.addWidget(lbl_theory)

        self.btn_pop_stance_chords = QPushButton("🔎 Stance Chords")
        self.btn_pop_stance_chords.setStyleSheet(tool_btn_style)
        self.btn_pop_stance_chords.clicked.connect(self._open_stance_chord_inspector)
        row2_bar.addWidget(self.btn_pop_stance_chords)

        self.btn_pop_chord = QPushButton("🔍 Chord Finder")
        self.btn_pop_chord.setStyleSheet(tool_btn_style)
        self.btn_pop_chord.clicked.connect(self._toggle_voicing_popout)
        row2_bar.addWidget(self.btn_pop_chord)

        self.btn_pop_scale = QPushButton("🎼 Scale Finder")
        self.btn_pop_scale.setStyleSheet(tool_btn_style)
        self.btn_pop_scale.clicked.connect(self._toggle_scale_popout)
        row2_bar.addWidget(self.btn_pop_scale)

        self.btn_pop_circle = QPushButton("⭕ Circle of Fifths")
        self.btn_pop_circle.setStyleSheet(tool_btn_style)
        self.btn_pop_circle.clicked.connect(self._toggle_circle_popout)
        row2_bar.addWidget(self.btn_pop_circle)

        self.btn_voice_leader = QPushButton("🧭 Voice Leader")
        self.btn_voice_leader.setStyleSheet(tool_btn_style)
        self.btn_voice_leader.clicked.connect(self._open_voice_leader)
        row2_bar.addWidget(self.btn_voice_leader)

        row2_bar.addSpacing(10)
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #495057;")
        row2_bar.addWidget(sep)
        row2_bar.addSpacing(10)

        lbl_methods = QLabel("<b>Methods & Drills:</b>")
        lbl_methods.setStyleSheet("color: #ffc107; font-size: 11px;")
        row2_bar.addWidget(lbl_methods)

        self.btn_pop_starmap = QPushButton("⭐ Up The Neck")
        self.btn_pop_starmap.setStyleSheet(tool_btn_style)
        self.btn_pop_starmap.clicked.connect(self._open_star_map_dialog)
        row2_bar.addWidget(self.btn_pop_starmap)

        self.btn_pop_pearls = QPushButton("📿 Strings of Pearls")
        self.btn_pop_pearls.setStyleSheet(tool_btn_style)
        self.btn_pop_pearls.clicked.connect(self._open_pearls_dialog)
        row2_bar.addWidget(self.btn_pop_pearls)

        self.btn_pop_perms = QPushButton("🖐 Permutations")
        self.btn_pop_perms.setStyleSheet(tool_btn_style)
        self.btn_pop_perms.clicked.connect(self._open_permutation_trainer)
        row2_bar.addWidget(self.btn_pop_perms)

        self.btn_pop_flashcard = QPushButton("🥩 Steak or Biscuits")
        self.btn_pop_flashcard.setStyleSheet(tool_btn_style)
        self.btn_pop_flashcard.clicked.connect(self._open_flashcard_drill)
        row2_bar.addWidget(self.btn_pop_flashcard)

        row2_bar.addStretch()
        root_layout.addWidget(row2_frame)

        # 3. Main Fretboard Canvas
        self.canvas = FretboardCanvas(self)
        self.canvas.set_show_inversions(self.settings.get("show_inversions", True))
        self.canvas.pocket_changed.connect(self._on_canvas_pocket_changed)
        self.canvas.node_clicked.connect(self._on_node_clicked)
        root_layout.addWidget(self.canvas, stretch=6)

        # 4. Permanent Up-The-Neck Navigator Ribbon
        self.star_map_box = QFrame()
        self.star_map_box.setStyleSheet("background-color: #212529; border-radius: 4px; padding: 2px;")
        star_map_h = QHBoxLayout(self.star_map_box)
        star_map_h.setContentsMargins(8, 3, 8, 3)
        star_map_h.setSpacing(8)

        self.lbl_star_map = QLabel("<b>⭐ Up-The-Neck Navigator:</b>")
        self.lbl_star_map.setStyleSheet("color: #ffc107; font-size: 11px;")
        star_map_h.addWidget(self.lbl_star_map)

        self.combo_up_neck_chord = QComboBox()
        self.combo_up_neck_chord.setToolTip("Select any Major or Minor chord to map its landmark positions up the neck")
        self._populate_up_neck_dropdown()
        self.combo_up_neck_chord.setStyleSheet("""
            QComboBox {
                background-color: #343a40;
                color: #ffde7a;
                border: 1px solid #ffc107;
                font-size: 10px;
                font-weight: bold;
                padding: 1px 6px;
                border-radius: 3px;
                min-width: 105px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1e222a;
                color: #ffde7a;
                selection-background-color: #ffc107;
                selection-color: #000000;
            }
        """)
        self.combo_up_neck_chord.currentIndexChanged.connect(self._on_up_neck_chord_dropdown_changed)
        star_map_h.addWidget(self.combo_up_neck_chord)

        star_map_scroll = QScrollArea()
        star_map_scroll.setFixedHeight(30)
        star_map_scroll.setWidgetResizable(True)
        star_map_scroll.setFrameShape(QFrame.NoFrame)
        star_map_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        star_map_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        star_map_scroll.setStyleSheet("""
            QScrollBar:horizontal { height: 4px; background: rgba(0,0,0,0.1); border-radius: 2px; }
            QScrollBar::handle:horizontal { background: rgba(255, 193, 7, 0.4); border-radius: 2px; }
        """)

        self.star_map_container = QWidget()
        self.star_map_layout = QHBoxLayout(self.star_map_container)
        self.star_map_layout.setContentsMargins(0, 0, 0, 0)
        self.star_map_layout.setSpacing(6)
        star_map_scroll.setWidget(self.star_map_container)
        star_map_h.addWidget(star_map_scroll, stretch=1)

        root_layout.addWidget(self.star_map_box, stretch=0)

        # 5. Same Fret Hub & Relative Move Assistant
        self.relative_moves_widget = RelativeMovesWidget(self)
        self.relative_moves_widget.move_applied.connect(self._apply_relative_move)
        root_layout.addWidget(self.relative_moves_widget, stretch=0)

        # 6. Bar Position Slider
        fret_controls = QHBoxLayout()
        fret_controls.addWidget(QLabel("<b>Bar Position (Fret):</b>"))

        self.fret_slider = QSlider(Qt.Horizontal)
        self.fret_slider.setRange(0, 24)
        self.fret_slider.setValue(0)
        self.fret_slider.setTickInterval(1)
        self.fret_slider.setTickPosition(QSlider.TicksBelow)
        fret_controls.addWidget(self.fret_slider, stretch=1)

        self.fret_spin = QSpinBox()
        self.fret_spin.setRange(0, 24)
        self.fret_spin.setValue(0)
        fret_controls.addWidget(self.fret_spin)

        self.fret_slider.valueChanged.connect(self._on_bar_fret_changed)
        self.fret_spin.valueChanged.connect(self._on_bar_fret_changed)
        self.canvas.fret_changed.connect(self._on_bar_fret_changed)
        root_layout.addLayout(fret_controls, stretch=0)

        # 7. Pedals & Knee Levers + Inline Articulations + Feasibility Banner
        self.lever_panel = LeverTogglePanel(self)
        self.lever_panel.levers_changed.connect(self._on_levers_changed)
        self.lever_panel.pinch_requested.connect(lambda: self._play_pocket(roll=False))
        self.lever_panel.roll_requested.connect(lambda: self._play_pocket(roll=True))
        self.lever_panel.arpeggiate_requested.connect(self._arpeggiate_active_pocket)
        self.lever_panel.all_strings_requested.connect(
            lambda: self._apply_pocket_preset(set(range(1, self.guitar.necks[self.current_neck_idx].string_count + 1)))
        )
        self.lever_panel.clear_pocket_requested.connect(lambda: self._apply_pocket_preset(set()))
        root_layout.addWidget(self.lever_panel, stretch=0)

        # 8. Bottom Row: String Grips (Left) + Harmonic Target (Right)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        self.grip_bar = GripPocketBar(self)
        self.grip_bar.pocket_changed.connect(self._on_grip_bar_pocket_changed)
        bottom_row.addWidget(self.grip_bar, stretch=3)

        self.harmonic_panel = HarmonicTargetPanel(self)
        self.harmonic_panel.target_changed.connect(self._on_harmonic_target_changed)
        self.harmonic_panel.reset_requested.connect(self.lever_panel.reset_all)
        self.harmonic_panel.find_voicings_requested.connect(self._toggle_voicing_popout)
        bottom_row.addWidget(self.harmonic_panel, stretch=1)

        root_layout.addLayout(bottom_row, stretch=0)

    def _populate_up_neck_dropdown(self):
        self.combo_up_neck_chord.blockSignals(True)
        self.combo_up_neck_chord.clear()
        roots = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
        for r in roots:
            self.combo_up_neck_chord.addItem(f"{r} Major", (r, "Major"))
            self.combo_up_neck_chord.addItem(f"{r} Minor", (r, "Minor"))
        default_idx = self.combo_up_neck_chord.findText("E Major")
        if default_idx >= 0:
            self.combo_up_neck_chord.setCurrentIndex(default_idx)
        self.combo_up_neck_chord.blockSignals(False)

    def _on_up_neck_chord_dropdown_changed(self):
        data = self.combo_up_neck_chord.currentData()
        if not data:
            return
        root, chord_type = data
        self.harmonic_panel.set_target(root, chord_type)
        self._update_star_map_ribbon()

    def _sync_up_neck_dropdown_from_panel(self, root: str, chord_type: str):
        if not root or root == "None":
            return
        q_tag = "Minor" if "Minor" in chord_type else "Major"
        # Match by pitch class so sharps and flats both find the dropdown entry (D-05).
        dropdown_roots = [self.combo_up_neck_chord.itemData(i)[0] for i in range(0, self.combo_up_neck_chord.count(), 2)]
        clean_r = to_root_name(root, dropdown_roots)
        if not clean_r:
            return
        idx = self.combo_up_neck_chord.findText(f"{clean_r} {q_tag}")
        if idx >= 0 and idx != self.combo_up_neck_chord.currentIndex():
            self.combo_up_neck_chord.blockSignals(True)
            self.combo_up_neck_chord.setCurrentIndex(idx)
            self.combo_up_neck_chord.blockSignals(False)

    def _update_star_map_ribbon(self):
        while self.star_map_layout.count() > 0:
            item = self.star_map_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        data = self.combo_up_neck_chord.currentData()
        if not data:
            root = self.harmonic_panel.get_root()
            chord_type = self.harmonic_panel.get_chord_type()
        else:
            root, chord_type = data

        if root == "None":
            root = "E"
            chord_type = "Major"

        neck = self.guitar.necks[self.current_neck_idx]
        landmarks = StarMapEngine.calculate_landmarks(root=root, chord_type=chord_type, neck=neck)

        for lm in landmarks:
            btn = QPushButton(lm.label)
            btn.setToolTip(f"{lm.description}\n{lm.strings_desc}")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #343a40;
                    color: #ffde7a;
                    font-weight: bold;
                    font-size: 10px;
                    border: 1px solid #6c757d;
                    border-radius: 4px;
                    padding: 2px 7px;
                }
                QPushButton:hover {
                    background-color: #495057;
                    border-color: #ffc107;
                    color: #ffffff;
                }
            """)
            btn.clicked.connect(lambda _, l=lm, b=btn: self._apply_star_map_landmark(l, b))
            self.star_map_layout.addWidget(btn)

        self.star_map_layout.addStretch()

    def _apply_star_map_landmark(self, landmark: StarMapLandmark, btn: Optional[QPushButton] = None):
        if btn:
            for i in range(self.star_map_layout.count()):
                w = self.star_map_layout.itemAt(i).widget()
                if isinstance(w, QPushButton):
                    w.setStyleSheet("""
                        QPushButton {
                            background-color: #343a40;
                            color: #ffde7a;
                            font-weight: bold;
                            font-size: 10px;
                            border: 1px solid #6c757d;
                            border-radius: 4px;
                            padding: 2px 7px;
                        }
                        QPushButton:hover {
                            background-color: #495057;
                            border-color: #ffc107;
                            color: #ffffff;
                        }
                    """)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #ffc107;
                    color: #000000;
                    font-weight: bold;
                    font-size: 11px;
                    border: 2px solid #ffffff;
                    border-radius: 4px;
                    padding: 2px 8px;
                }
            """)

        self.apply_stance(landmark.fret, landmark.controllers, landmark.target_strings)

    def _on_bar_fret_changed(self, fret: int):
        self.fret_slider.blockSignals(True)
        self.fret_spin.blockSignals(True)
        self.fret_slider.setValue(fret)
        self.fret_spin.setValue(fret)
        self.fret_slider.blockSignals(False)
        self.fret_spin.blockSignals(False)

        self.canvas.set_bar_fret(fret)
        self._refresh_stance_dependents()

    def apply_stance(
        self,
        fret: int,
        controllers,
        pocket=None,
        *,
        play: bool = True,
        banner: Optional[str] = None,
    ):
        """Single entry point for programmatically setting the stance (D-03).

        Updates the canvas, fret widgets, lever buttons AND the lever panel's own state/badge, the
        pocket, then refreshes dependent views once (D-31). Controllers may include "<ID>_HALF".
        """
        self._batch_depth += 1
        try:
            self.canvas.set_bar_fret(fret)
            self._sync_fret_widgets(fret)
            active = self.lever_panel.set_active_controllers(set(controllers))
            self.canvas.set_engaged_levers(active)
            if pocket is not None:
                self._apply_pocket_preset(set(pocket))
            if banner is not None:
                self.canvas.set_explicit_banner(banner)
        finally:
            self._batch_depth -= 1
        self._refresh_stance_dependents()
        if play:
            self._play_pocket(roll=False)

    def _refresh_stance_dependents(self):
        """Refreshes views derived from the current stance (skipped while a batch is running)."""
        if self._batch_depth:
            return
        self._update_relative_moves_hub()
        self._update_stance_inspector_if_open()
        if hasattr(self, "circle_widget") and self.circle_widget.isVisible():
            self.circle_widget.update_current_stance(
                self.canvas.bar_fret, self.canvas.engaged_levers, self.canvas.active_pocket
            )

    def _sync_fret_widgets(self, fret: int):
        self._on_bar_fret_changed(fret)

    def _on_levers_changed(self, active_levers: set):
        self.canvas.set_engaged_levers(set(active_levers))
        self._refresh_stance_dependents()

    def _init_sequencer_dock(self):
        self.dock_sequencer = QDockWidget("Progression Sequencer & Tablature", self)
        self.dock_sequencer.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)

        self.sequencer = ProgressionSequencerWidget(self)
        self.sequencer.btn_capture.clicked.connect(self._capture_active_step)
        self.sequencer.step_activated.connect(self._apply_sequencer_step)

        self.dock_sequencer.setWidget(self.sequencer)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_sequencer)
        self.dock_sequencer.hide()
        self.dock_sequencer.visibilityChanged.connect(self._on_dock_visibility_changed)

    def _toggle_sequencer_visibility(self):
        is_vis = self.dock_sequencer.isVisible()
        self.dock_sequencer.setVisible(not is_vis)
        if not is_vis:
            self.dock_sequencer.raise_()

    def _pop_out_sequencer(self):
        self.dock_sequencer.setFloating(True)
        self.dock_sequencer.show()
        self.dock_sequencer.raise_()

    def _on_dock_visibility_changed(self, visible: bool):
        self.btn_toggle_seq.blockSignals(True)
        self.btn_toggle_seq.setChecked(visible)
        self.btn_toggle_seq.blockSignals(False)

    def _arpeggiate_active_pocket(self):
        if not self.canvas.active_states or not self.canvas.active_pocket:
            return
        pocket_states = [s for s in self.canvas.active_states if s.string_number in self.canvas.active_pocket]
        pocket_states.sort(key=lambda s: s.string_number, reverse=True)
        cents = self._current_cents([s.string_number for s in pocket_states])
        for i, s in enumerate(pocket_states):
            delay_ms = int(i * 100)
            QTimer.singleShot(
                delay_ms,
                lambda st=s: self.audio.play_note(st.active_midi, st.string_number, cents_offset=cents.get(st.string_number, 0.0)),
            )

    def _on_grip_bar_pocket_changed(self, pocket: Set[int]):
        self.canvas.set_active_pocket(pocket)
        if hasattr(self, "scale_finder"):
            self.scale_finder.set_active_pocket(pocket)
        if hasattr(self, "circle_widget") and self.circle_widget.isVisible() and not self._batch_depth:
            self.circle_widget.set_active_pocket(pocket)
        elif hasattr(self, "circle_widget"):
            self.circle_widget.active_pocket = set(pocket)

    def _on_canvas_pocket_changed(self, pocket: Set[int]):
        self.grip_bar.sync_highlights(pocket)

    def _apply_pocket_preset(self, pocket: Set[int]):
        self.grip_bar.apply_pocket(pocket)

    def _on_harmonic_target_changed(self, root: Optional[str], chord_type: Optional[str]):
        if root is None:
            self.canvas.set_chord_analysis(None, None)
        else:
            self.canvas.set_chord_analysis(root, chord_type)
            self._sync_up_neck_dropdown_from_panel(root, chord_type)
        self._update_star_map_ribbon()
        self._update_relative_moves_hub()

    def _load_current_neck(self):
        neck = self.guitar.necks[self.current_neck_idx]
        self.canvas.set_neck(neck)
        self.canvas.set_show_nashville(self.settings.get("show_nashville", True))
        self.canvas.set_show_inversions(self.settings.get("show_inversions", True))
        self.lever_panel.set_neck(neck)
        self.grip_bar.set_neck(neck)
        self.canvas.set_engaged_levers(set())

        is_c6 = (neck.neck_type == NeckType.C6 or "C6" in neck.name)
        if hasattr(self, "action_c6_franklin_offset"):
            self.action_c6_franklin_offset.setEnabled(is_c6)
            has_franklin = "P1" in neck.pedals and "Franklin" in neck.pedals["P1"].label
            self.action_c6_franklin_offset.blockSignals(True)
            self.action_c6_franklin_offset.setChecked(has_franklin)
            self.action_c6_franklin_offset.blockSignals(False)

        if hasattr(self, "voicing_finder"):
            self.voicing_finder.update_neck(neck)
        if hasattr(self, "scale_finder"):
            self.scale_finder.update_neck(neck)
        if hasattr(self, "circle_widget"):
            self.circle_widget.update_neck(neck)
        if hasattr(self, "sequencer"):
            self.sequencer.set_neck(neck)
            self.sequencer.set_neck_type("C6" if is_c6 else "E9")
        if hasattr(self, "voice_leader_dlg") and self.voice_leader_dlg is not None:
            self.voice_leader_dlg.set_neck(neck)

        self.harmonic_panel._on_change()
        self._update_star_map_ribbon()
        self._update_relative_moves_hub()
        self._update_stance_inspector_if_open()

    def _refresh_copedant_dropdown(self):
        self.combo_copedant.blockSignals(True)
        self.combo_copedant.clear()

        for idx, neck in enumerate(self.guitar.necks):
            self.combo_copedant.addItem(self._neck_display_name(neck), ("neck", idx))

        user_profiles = ProfileManager.list_user_profiles()
        if user_profiles:
            sep_idx = self.combo_copedant.count()
            self.combo_copedant.addItem("─── Saved User Profiles ───", None)
            self.combo_copedant.model().item(sep_idx).setEnabled(False)
            for p_name in user_profiles:
                self.combo_copedant.addItem(f"📁 {p_name}", ("profile", p_name))

        self.combo_copedant.setCurrentIndex(min(self.current_neck_idx, len(self.guitar.necks) - 1))
        self.combo_copedant.blockSignals(False)
        self._rebuild_copedant_menu()

    def _on_copedant_dropdown_changed(self, index: int):
        item_data = self.combo_copedant.currentData()
        if not item_data:
            return
        kind, value = item_data
        if kind == "neck":
            self.current_neck_idx = value
            self._load_current_neck()
        elif kind == "profile":
            self._load_named_profile(value)

    @staticmethod
    def _neck_display_name(neck: Neck) -> str:
        marker = "📁 " if neck.source_profile else ""
        return f"{marker}{neck.name} ({neck.string_count} Str)"

    def _rebuild_copedant_menu(self):
        if not hasattr(self, "copedant_select_menu"):
            return
        self.copedant_select_menu.clear()
        for idx, neck in enumerate(self.guitar.necks):
            action = QAction(self._neck_display_name(neck), self)
            action.setCheckable(True)
            action.setChecked(idx == self.current_neck_idx)
            action.triggered.connect(lambda checked=False, i=idx: self._select_copedant_index(i))
            self.copedant_select_menu.addAction(action)

    def _select_copedant_index(self, index: int):
        if 0 <= index < len(self.guitar.necks):
            self.current_neck_idx = index
            self.combo_copedant.blockSignals(True)
            self.combo_copedant.setCurrentIndex(index)
            self.combo_copedant.blockSignals(False)
            self._load_current_neck()
            self._rebuild_copedant_menu()

    def _set_display_mode(self, mode: str):
        self.canvas.set_display_mode(mode)
        if mode == "notes":
            self.btn_toggle_display.setText("🔤 Notes (Plucked)")
            if hasattr(self, "action_disp_notes"):
                self.action_disp_notes.setChecked(True)
        else:
            self.btn_toggle_display.setText("🎯 Intervals (R-3-5)")
            if hasattr(self, "action_disp_intervals"):
                self.action_disp_intervals.setChecked(True)

    def _toggle_display_mode_btn(self):
        new_mode = "notes" if self.canvas.display_mode == "intervals" else "intervals"
        self._set_display_mode(new_mode)

    def _toggle_nns_button(self, checked: bool):
        self.settings["show_nashville"] = checked
        save_settings(self.settings)
        if hasattr(self, "action_nns"):
            self.action_nns.blockSignals(True)
            self.action_nns.setChecked(checked)
            self.action_nns.blockSignals(False)
        self.canvas.set_show_nashville(checked)

    def _toggle_nns_menu_preference(self):
        checked = self.action_nns.isChecked()
        self.settings["show_nashville"] = checked
        save_settings(self.settings)
        if hasattr(self, "btn_toggle_nns"):
            self.btn_toggle_nns.blockSignals(True)
            self.btn_toggle_nns.setChecked(checked)
            self.btn_toggle_nns.blockSignals(False)
        self.canvas.set_show_nashville(checked)

    def _toggle_inversions_preference(self):
        show = self.action_inversions.isChecked()
        self.settings["show_inversions"] = show
        save_settings(self.settings)
        self.canvas.set_show_inversions(show)

    def _set_theme(self, theme_name: str):
        self.settings["theme"] = theme_name
        save_settings(self.settings)
        self._apply_theme(theme_name)

    def _apply_theme(self, theme_name: str):
        is_dark = (theme_name == "dark")
        app = QApplication.instance()
        if app:
            app.setStyleSheet(DARK_THEME_QSS if is_dark else LIGHT_THEME_QSS)
        if hasattr(self, "canvas"):
            self.canvas.set_dark_mode(is_dark)

    def _init_popout_windows(self):
        current_neck = self.guitar.necks[self.current_neck_idx]

        self.voicing_finder = VoicingFinderWidget(neck=current_neck, parent=self)
        self.voicing_finder.setWindowFlags(Qt.Window)
        self.voicing_finder.setWindowTitle("Chord Voicing Finder & Position Solver")
        self.voicing_finder.resize(920, 500)
        self.voicing_finder.voicing_applied.connect(self._apply_solved_voicing)
        self.voicing_finder.target_changed.connect(self.harmonic_panel.set_target)

        show_scale_box = self.settings.get("show_scale_box", True)
        self.scale_finder = ScaleFinderWidget(
            neck=current_neck,
            show_box_initial=show_scale_box,
            parent=self,
        )
        self.scale_finder.setWindowFlags(Qt.Window)
        self.scale_finder.setWindowTitle("Scale Pocket Finder & Degree Ladder")
        self.scale_finder.resize(920, 520)
        self.scale_finder.scale_step_applied.connect(self._apply_scale_step)
        self.scale_finder.box_highlight_requested.connect(self.canvas.set_box_highlight)
        self.scale_finder.clear_highlight_requested.connect(self.canvas.clear_box_highlight)
        self.scale_finder.box_shading_toggled.connect(self._on_scale_box_preference_changed)
        self.scale_finder.play_note_requested.connect(self.audio.play_note)
        self.scale_finder.play_notes_requested.connect(self.audio.play_scale_sequence)
        self.scale_finder.target_changed.connect(self._on_scale_target_changed)

        self.circle_widget = CircleOfFifthsWidget(neck=current_neck, parent=self)
        self.circle_widget.setWindowFlags(Qt.Window)
        self.circle_widget.setWindowTitle("Circle of Fifths & Diatonic Songwriter")
        self.circle_widget.resize(760, 480)
        self.circle_widget.chord_triggered.connect(self._on_circle_chord_triggered)

    def _toggle_voicing_popout(self):
        if self.voicing_finder.isVisible():
            self.voicing_finder.hide()
        else:
            root = self.harmonic_panel.get_root()
            chord_type = self.harmonic_panel.get_chord_type()
            if root == "None":
                root = "E"
            self.voicing_finder.set_target(root, chord_type)
            self.voicing_finder.show()
            self.voicing_finder.raise_()
            self.voicing_finder.activateWindow()

    def _toggle_scale_popout(self):
        if self.scale_finder.isVisible():
            self.scale_finder.hide()
        else:
            self.scale_finder.show()
            self.scale_finder.raise_()
            self.scale_finder.activateWindow()

    def _toggle_circle_popout(self):
        if self.circle_widget.isVisible():
            self.circle_widget.hide()
        else:
            self.circle_widget.show()
            self.circle_widget.raise_()
            self.circle_widget.activateWindow()

    def _on_scale_target_changed(self, root: str, scale_name: str):
        self.canvas.set_scale_analysis(root, scale_name)

    def _apply_scale_step(self, fret: int, levers: list, string_number: int, banner: str):
        # The scale finder plays the note itself; the pocket is the single stepped string.
        self.apply_stance(fret, levers, None, play=False)
        self.canvas.set_active_pocket({string_number})
        self.canvas.set_explicit_banner(banner)

    def _on_circle_chord_triggered(self, root: str, chord_type: str, add_to_sequencer: bool):
        neck = self.guitar.necks[self.current_neck_idx]

        all_matches = VoicingSolver.find_all_voicings(
            neck=neck,
            root_name=root,
            chord_type=chord_type,
            max_fret=15,
            filter_awkward=True,
        )
        if not all_matches:
            return

        chosen_match = None
        if self.circle_widget.cb_lock_pocket.isChecked() and self.canvas.active_pocket:
            pocket_matches = [
                m for m in all_matches if set(m.grip_strings) == self.canvas.active_pocket
            ]
            if pocket_matches:
                current_fret = self.canvas.bar_fret
                pocket_matches.sort(key=lambda m: (abs(m.fret - current_fret), len(m.engaged_levers)))
                chosen_match = pocket_matches[0]

        if not chosen_match:
            chosen_match = all_matches[0]

        self.apply_stance(chosen_match.fret, chosen_match.engaged_levers, chosen_match.grip_strings)

        if add_to_sequencer:
            chord_tag = f"{root} {chord_type[:3]}"
            self.sequencer.string_count = neck.string_count
            self.sequencer.capture_step(
                fret=chosen_match.fret,
                levers=set(chosen_match.engaged_levers),
                grip=set(chosen_match.grip_strings),
                chord_label=chord_tag,
            )

    def _current_cents(self, strings) -> dict:
        """Newman compensated-tuning cents for the current stance (empty unless enabled and E9)."""
        if not self.audio.use_compensated_temperament:
            return {}
        neck = self.guitar.necks[self.current_neck_idx]
        return compute_newman_cents(neck, self.canvas.engaged_levers, strings)

    def _play_pocket(self, roll: bool = False):
        if not self.canvas.active_states or not self.canvas.active_pocket:
            return
        # Address each note by its real string number so it plays on that string's channel (D-01).
        pitches = {
            s.string_number: s.active_midi
            for s in self.canvas.active_states
            if s.string_number in self.canvas.active_pocket
        }
        self.audio.play_pocket(pitches, roll=roll, cents=self._current_cents(pitches.keys()))

    def _apply_solved_voicing(self, fret: int, levers: list, grip_strings: list):
        self.apply_stance(fret, levers, grip_strings)

    def _export_pdf(self):
        neck = self.guitar.necks[self.current_neck_idx]
        default_filename = f"{neck.name.replace(' ', '_')}_Fret_{self.canvas.bar_fret}_Reference.pdf"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Reference Sheet", default_filename, "PDF Files (*.pdf)"
        )
        if not filepath:
            return

        from core.exporter import CopedantPdfExporter
        try:
            CopedantPdfExporter.export_neck_sheet(
                filepath=filepath,
                neck=neck,
                bar_fret=self.canvas.bar_fret,
                engaged_levers=self.canvas.engaged_levers,
                active_pocket=self.canvas.active_pocket,
                target_root=self.harmonic_panel.get_root(),
                target_chord=self.harmonic_panel.get_chord_type(),
            )
        except Exception as e:  # e.g. PermissionError when the PDF is open in a viewer (D-21)
            log.exception("PDF export failed")
            QMessageBox.critical(self, "Export Failed", f"Could not write the PDF:\n{e}")
            return
        QMessageBox.information(self, "Export Successful", f"Reference sheet exported to:\n{filepath}")

    def _copy_fretboard_snapshot(self):
        pixmap = self.canvas.grab()
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setPixmap(pixmap)
            QMessageBox.information(self, "Snapshot Copied", "Fretboard image copied to clipboard.")

    def _capture_active_step(self):
        chord_tag = self.canvas.detected_chord_label
        if not chord_tag:
            root = self.harmonic_panel.get_root()
            chord = self.harmonic_panel.get_chord_type()
            chord_tag = f"{root}{chord[:3]}" if root != "None" else "Grip"

        self.sequencer.string_count = self.guitar.necks[self.current_neck_idx].string_count
        self.sequencer.capture_step(
            fret=self.canvas.bar_fret,
            levers=self.canvas.engaged_levers,
            grip=self.canvas.active_pocket,
            chord_label=chord_tag,
        )

    def _apply_sequencer_step(self, fret: int, levers: list, grip_strings: set):
        self.apply_stance(fret, levers, grip_strings)

    def _toggle_scale_box_menu_preference(self):
        show = self.action_scale_box.isChecked()
        self.settings["show_scale_box"] = show
        save_settings(self.settings)
        if hasattr(self, "scale_finder"):
            self.scale_finder.set_box_shading_state(show)

    def _on_scale_box_preference_changed(self, checked: bool):
        self.settings["show_scale_box"] = checked
        save_settings(self.settings)
        if hasattr(self, "action_scale_box"):
            self.action_scale_box.blockSignals(True)
            self.action_scale_box.setChecked(checked)
            self.action_scale_box.blockSignals(False)

    def _open_voice_leader(self):
        from ui.voice_leader_dialog import VoiceLeaderDialog
        neck = self.guitar.necks[self.current_neck_idx]
        if self.voice_leader_dlg is None:
            self.voice_leader_dlg = VoiceLeaderDialog(neck=neck, parent=self)
            self.voice_leader_dlg.setWindowFlags(Qt.Window)
            self.voice_leader_dlg.voicing_path_applied.connect(self._apply_voice_leader_path)
            self.voice_leader_dlg.voicing_applied.connect(self._apply_solved_voicing)

        if hasattr(self.voice_leader_dlg, "set_neck"):
            self.voice_leader_dlg.set_neck(neck)
        else:
            self.voice_leader_dlg.neck = neck

        self.voice_leader_dlg.show()
        self.voice_leader_dlg.raise_()
        self.voice_leader_dlg.activateWindow()

    def _apply_voice_leader_path(self, solved_steps: list):
        neck = self.guitar.necks[self.current_neck_idx]
        self.sequencer.set_neck(neck)
        self.sequencer._clear_all()

        for m_idx, v in solved_steps:
            self.sequencer.capture_step(
                fret=v.fret,
                levers=set(v.engaged_levers),
                grip=set(v.grip_strings),
                chord_label=f"M{m_idx + 1}",
            )

        if solved_steps:
            first_v = solved_steps[0][1]
            self.apply_stance(first_v.fret, first_v.engaged_levers, first_v.grip_strings, play=False)

    def _open_star_map_dialog(self):
        from ui.star_map_widget import StarMapWidget
        dlg = StarMapWidget(neck=self.guitar.necks[self.current_neck_idx], parent=self)
        dlg.landmark_selected.connect(self._on_star_map_dialog_selected)
        dlg.exec()

    def _on_star_map_dialog_selected(self, fret: int, controllers: set, target_strings: set):
        self.apply_stance(fret, controllers, target_strings)

    def _open_permutation_trainer(self):
        from ui.permutation_trainer_dialog import PermutationTrainerDialog
        neck = self.guitar.necks[self.current_neck_idx]
        dlg = PermutationTrainerDialog(
            neck=neck,
            active_pocket=self.canvas.active_pocket,
            parent=self,
        )
        dlg.exec()

    def _open_copedant_editor(self, initial_tab: Optional[str] = None):
        neck = self.guitar.necks[self.current_neck_idx]
        dialog = CopedantEditorDialog(
            neck=neck,
            guitar=self.guitar,
            current_neck_idx=self.current_neck_idx,
            initial_tab=initial_tab,
            parent=self,
        )
        if dialog.exec() == QDialog.Accepted:
            # Follow the neck the user was editing when they pressed Apply.
            self.current_neck_idx = dialog.current_neck_idx
            self._on_copedant_modified()
        elif dialog.guitar_changed:
            # Duplicate / Save-as-Profile added necks even though the dialog was cancelled.
            self._save_active_guitar_setup()
            self._refresh_copedant_dropdown()

    def _open_splits_manager(self):
        """Opens Copedant Editor focused directly on the Mechanical Splits tab."""
        self._open_copedant_editor(initial_tab="splits")

    def _open_half_stops_manager(self):
        """Opens Copedant Editor focused directly on the Half-Stops tab."""
        self._open_copedant_editor(initial_tab="half_stops")

    def _toggle_c6_menu_pedal_offset(self, checked: bool):
        neck = self.guitar.necks[self.current_neck_idx]
        if neck.neck_type == NeckType.C6 or "C6" in neck.name:
            dlg = CopedantEditorDialog(neck=neck, guitar=self.guitar, current_neck_idx=self.current_neck_idx, parent=self)
            dlg._toggle_c6_pedal_offset(checked)
            dlg._apply_and_close()
            self._on_copedant_modified()

    def _on_copedant_modified(self):
        self._save_active_guitar_setup()
        self._refresh_copedant_dropdown()
        self._load_current_neck()

    def _open_stance_chord_inspector(self):
        neck = self.guitar.necks[self.current_neck_idx]
        if self.stance_inspector_dlg is None:
            self.stance_inspector_dlg = StanceChordInspectorDialog(
                neck=neck,
                bar_fret=self.canvas.bar_fret,
                engaged_levers=self.canvas.engaged_levers,
                parent=self,
            )
            self.stance_inspector_dlg.setWindowFlags(Qt.Window)
            self.stance_inspector_dlg.grip_applied.connect(self._apply_pocket_preset)

        self.stance_inspector_dlg.refresh_scan(
            neck=neck,
            bar_fret=self.canvas.bar_fret,
            engaged_levers=self.canvas.engaged_levers,
        )
        self.stance_inspector_dlg.show()
        self.stance_inspector_dlg.raise_()
        self.stance_inspector_dlg.activateWindow()

    def _update_stance_inspector_if_open(self):
        if hasattr(self, "stance_inspector_dlg") and self.stance_inspector_dlg is not None:
            if self.stance_inspector_dlg.isVisible() and self.stance_inspector_dlg.cb_live_sync.isChecked():
                neck = self.guitar.necks[self.current_neck_idx]
                self.stance_inspector_dlg.refresh_scan(
                    neck=neck,
                    bar_fret=self.canvas.bar_fret,
                    engaged_levers=self.canvas.engaged_levers,
                )

    def _update_relative_moves_hub(self):
        neck = self.guitar.necks[self.current_neck_idx]
        is_c6 = (neck.neck_type == NeckType.C6 or "C6" in neck.name)
        if hasattr(self, "relative_moves_widget"):
            self.relative_moves_widget.update_state(
                fret=self.canvas.bar_fret,
                active_levers=self.canvas.engaged_levers,
                is_c6=is_c6,
                neck=neck,
            )

    def _open_flashcard_drill(self):
        from ui.flashcard_dialog import FlashcardDrillDialog
        neck = self.guitar.necks[self.current_neck_idx]
        dlg = FlashcardDrillDialog(neck=neck, parent=self)
        dlg.landmark_verified.connect(self._on_star_map_dialog_selected)
        dlg.exec()

    def _set_temperament(self, use_newman: bool):
        self.settings["use_newman_tuning"] = use_newman
        save_settings(self.settings)
        self.audio.set_compensated_temperament(use_newman)

    def _apply_relative_move(self, target_fret: int, controllers: set, target_strings: set, chord_root: str = "", chord_type: str = ""):
        if chord_root:
            self.harmonic_panel.set_target(chord_root, chord_type or "Major")
        self.apply_stance(target_fret, controllers, target_strings)

    def _on_node_clicked(self, midi_pitch: int, string_number: int = 0):
        cents = self._current_cents([string_number]).get(string_number, 0.0) if string_number else 0.0
        self.audio.play_note(midi_pitch, string_number or None, cents_offset=cents)

    def _open_import_copedant_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Import Copedant File",
            "",
            "PSG Compass Copedant (*.cop *.json);;All Files (*.*)",
        )
        if not filepath:
            return

        try:
            import json
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "strings" in data and "pedals" in data:
                new_neck = Neck.from_compass_json(data)
            else:
                new_neck = Neck.from_dict(data)
            migrate_half_stop_tokens(new_neck)
            # An imported copedant is a new entry, not linked to any existing profile file.
            new_neck.source_profile = ""

            existing_names = [n.name for n in self.guitar.necks]
            base_name = new_neck.name
            counter = 1
            while new_neck.name in existing_names:
                new_neck.name = f"{base_name} ({counter})"
                counter += 1

            self.guitar.necks.append(new_neck)
            self.current_neck_idx = len(self.guitar.necks) - 1
            self._refresh_copedant_dropdown()
            self._load_current_neck()

            QMessageBox.information(
                self,
                "Copedant Imported",
                f"Successfully loaded '{new_neck.name}' ({new_neck.string_count} Strings).",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Import Error",
                f"Failed to parse copedant file:\n{str(e)}",
            )

    def _open_pearls_dialog(self):
        from ui.pearls_widget import StringsOfPearlsDialog
        neck = self.guitar.necks[self.current_neck_idx]
        dlg = StringsOfPearlsDialog(neck=neck, parent=self)
        dlg.step_selected.connect(self._on_star_map_dialog_selected)
        dlg.exec()

    def _open_profile_manager(self):
        neck = self.guitar.necks[self.current_neck_idx]
        dlg = ProfileManagerDialog(current_neck=neck, parent=self)
        dlg.profile_selected.connect(self._load_named_profile)
        dlg.exec()
        self._refresh_copedant_dropdown()

    def _load_named_profile(self, profile_name: str):
        """Opens a user profile as its own neck entry. It never overwrites the active (e.g. factory)
        neck; re-loading a profile that is already open refreshes that entry from disk (D-02)."""
        try:
            loaded_neck = ProfileManager.load_user_profile(profile_name)
        except Exception as e:
            QMessageBox.critical(self, "Profile Error", f"Failed to load profile '{profile_name}':\n{e}")
            self._refresh_copedant_dropdown()
            return
        if not loaded_neck:
            QMessageBox.warning(self, "Profile Not Found", f"Profile '{profile_name}' could not be found.")
            self._refresh_copedant_dropdown()
            return
        migrate_half_stop_tokens(loaded_neck)

        existing_idx = next(
            (i for i, n in enumerate(self.guitar.necks) if n.source_profile == loaded_neck.source_profile),
            None,
        )
        if existing_idx is None:
            self.guitar.necks.append(loaded_neck)
            self.current_neck_idx = len(self.guitar.necks) - 1
        else:
            self.guitar.necks[existing_idx] = loaded_neck
            self.current_neck_idx = existing_idx

        self._save_active_guitar_setup()
        self._refresh_copedant_dropdown()
        self._load_current_neck()

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import All Necks Setup", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            guitar = SteelGuitar.load_from_file(path)
            if not guitar.necks:
                raise ValueError("The file contains no necks.")
        except Exception as e:  # D-21
            log.exception("Setup import failed")
            QMessageBox.critical(self, "Import Error", f"Failed to load setup file:\n{e}")
            return
        self.guitar = guitar
        for neck in self.guitar.necks:
            migrate_half_stop_tokens(neck)
        self.current_neck_idx = 0
        self._refresh_copedant_dropdown()
        self._load_current_neck()

    def _save_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export All Necks Setup", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            self.guitar.save_to_file(path)
        except Exception as e:  # D-21
            log.exception("Setup export failed")
            QMessageBox.critical(self, "Export Error", f"Failed to save setup file:\n{e}")

    def _save_active_guitar_setup(self):
        try:
            storage_dir = ProfileManager.ensure_storage_dir() or getattr(
                ProfileManager, "STORAGE_DIR", Path.home() / ".psg_visualizer" / "profiles"
            )
            active_setup_path = storage_dir / "active_guitar_setup.json"
            self.guitar.save_to_file(str(active_setup_path))
            # Profile files are written by the copedant editor for profile-linked necks
            # (Neck.source_profile); nothing to write back here.
        except Exception:
            log.exception("Error saving active guitar setup")

    def closeEvent(self, event):
        self._save_active_guitar_setup()
        if hasattr(self, "voicing_finder"):
            self.voicing_finder.close()
        if hasattr(self, "scale_finder"):
            self.scale_finder.close()
        if hasattr(self, "circle_widget"):
            self.circle_widget.close()
        if self.voice_leader_dlg:
            self.voice_leader_dlg.close()
        if self.stance_inspector_dlg:
            self.stance_inspector_dlg.close()
        self.audio.close()
        super().closeEvent(event)