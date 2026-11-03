"""Main application window integrating pocket selection and live audio."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.audio import MidiAudioEngine
from core.models import SteelGuitar
from core.presets import build_standard_d10_guitar
from core.theory import CHORD_FORMULAS, NOTE_NAMES_SHARP
from ui.fretboard_canvas import FretboardCanvas
from ui.lever_panel import LeverTogglePanel
from ui.pocket_panel import PocketSelectorPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pedal Steel Guitar Copedant & Voicing Visualizer")
        self.resize(1180, 780)

        self.audio = MidiAudioEngine()
        self.guitar: SteelGuitar = build_standard_d10_guitar()
        self.current_neck_idx: int = 0

        self._init_ui()
        self._load_current_neck()

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        # 1. Top Controls Bar: File I/O & Neck Switcher
        top_bar = QHBoxLayout()
        self.btn_load = QPushButton("Load Setup (JSON)")
        self.btn_load.clicked.connect(self._load_file)
        self.btn_save = QPushButton("Save Setup (JSON)")
        self.btn_save.clicked.connect(self._save_file)
        top_bar.addWidget(self.btn_load)
        top_bar.addWidget(self.btn_save)

        top_bar.addSpacing(20)
        top_bar.addWidget(QLabel("<b>Neck:</b>"))
        self.neck_tabs = QTabWidget()
        for neck in self.guitar.necks:
            self.neck_tabs.addTab(QWidget(), neck.name)
        self.neck_tabs.currentChanged.connect(self._on_neck_switched)
        top_bar.addWidget(self.neck_tabs)
        top_bar.addStretch()

        root_layout.addLayout(top_bar)

        # 2. Main Fretboard View
        self.canvas = FretboardCanvas(self)
        self.canvas.string_clicked.connect(self._toggle_string_pocket)
        root_layout.addWidget(self.canvas, stretch=3)

        # 3. Bar Position Controls
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

        self.fret_slider.valueChanged.connect(self.fret_spin.setValue)
        self.fret_spin.valueChanged.connect(self.fret_slider.setValue)
        self.fret_slider.valueChanged.connect(self.canvas.set_bar_fret)
        self.canvas.fret_changed.connect(self._sync_fret_widgets)

        root_layout.addLayout(fret_controls)

        # 4. Pocket / Grip Selector Panel
        self.pocket_panel = PocketSelectorPanel(self)
        self.pocket_panel.pocket_changed.connect(self.canvas.set_active_pocket)
        self.pocket_panel.pluck_requested.connect(self._play_pocket_audio)
        root_layout.addWidget(self.pocket_panel)

        # 5. Lever & Chord Analysis
        bottom_box = QHBoxLayout()

        self.lever_panel = LeverTogglePanel(self)
        self.lever_panel.levers_changed.connect(self.canvas.set_engaged_levers)
        bottom_box.addWidget(self.lever_panel, stretch=2)

        chord_box = QGroupBox("Harmonic Target / Interval Analysis")
        chord_layout = QGridLayout(chord_box)

        chord_layout.addWidget(QLabel("Root:"), 0, 0)
        self.root_combo = QComboBox()
        self.root_combo.addItem("None")
        self.root_combo.addItems(NOTE_NAMES_SHARP)
        self.root_combo.currentIndexChanged.connect(self._on_chord_selected)
        chord_layout.addWidget(self.root_combo, 0, 1)

        chord_layout.addWidget(QLabel("Chord:"), 1, 0)
        self.chord_combo = QComboBox()
        self.chord_combo.addItems(list(CHORD_FORMULAS.keys()))
        self.chord_combo.currentIndexChanged.connect(self._on_chord_selected)
        chord_layout.addWidget(self.chord_combo, 1, 1)

        self.btn_reset_all = QPushButton("Reset Pedals/Levers")
        self.btn_reset_all.clicked.connect(self.lever_panel.reset_all)
        chord_layout.addWidget(self.btn_reset_all, 2, 0, 1, 2)

        bottom_box.addWidget(chord_box, stretch=1)
        root_layout.addLayout(bottom_box, stretch=1)

    def _sync_fret_widgets(self, fret: int):
        self.fret_slider.blockSignals(True)
        self.fret_spin.blockSignals(True)
        self.fret_slider.setValue(fret)
        self.fret_spin.setValue(fret)
        self.fret_slider.blockSignals(False)
        self.fret_spin.blockSignals(False)

    def _on_neck_switched(self, idx: int):
        self.current_neck_idx = idx
        self._load_current_neck()

    def _load_current_neck(self):
        neck = self.guitar.necks[self.current_neck_idx]
        self.canvas.set_neck(neck)
        self.lever_panel.set_neck(neck)
        self.pocket_panel.rebuild_string_buttons(neck.string_count)
        self.pocket_panel.apply_pocket({8, 6, 4})
        self.canvas.set_engaged_levers(set())

    def _toggle_string_pocket(self, string_num: int):
        current_pocket = set(self.pocket_panel.get_active_pocket())
        if string_num in current_pocket:
            current_pocket.remove(string_num)
        else:
            current_pocket.add(string_num)
        self.pocket_panel.apply_pocket(current_pocket)

    def _play_pocket_audio(self, roll: bool = False):
        active_pocket = self.pocket_panel.get_active_pocket()
        if not active_pocket or not self.canvas.active_states:
            return

        # Collect active pitches only for strings in the pocket
        pitches_to_play = [
            s.active_midi for s in self.canvas.active_states
            if s.string_number in active_pocket
        ]
        self.audio.play_pocket(pitches_to_play, roll=roll)

    def _on_chord_selected(self):
        root = self.root_combo.currentText()
        chord_type = self.chord_combo.currentText()
        if root == "None":
            self.canvas.set_chord_analysis(None, None)
        else:
            self.canvas.set_chord_analysis(root, chord_type)

    def _save_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Copedant Setup", "", "JSON Files (*.json)")
        if path:
            self.guitar.save_to_file(path)

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Copedant Setup", "", "JSON Files (*.json)")
        if path:
            self.guitar = SteelGuitar.load_from_file(path)
            self.neck_tabs.blockSignals(True)
            self.neck_tabs.clear()
            for neck in self.guitar.necks:
                self.neck_tabs.addTab(QWidget(), neck.name)
            self.neck_tabs.blockSignals(False)
            self.current_neck_idx = 0
            self._load_current_neck()

    def closeEvent(self, event):
        self.audio.close()
        super().closeEvent(event)