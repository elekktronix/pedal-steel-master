"""Chord Atlas dialog (E-27): every chord the selected copedant can play at one bar position.

Same format as Compare Copedants (E-25): shared chord/controller filters (ui/chord_filter_bar.py),
"Show at fret" transposition, modeless, double-click to audition. Adds grip configurations
(source, sizes, span, custom groups) and three views:
- By chord: chord -> every way (stance + grip);
- By stance: stance -> every chord it gives (and on which grip);
- Coverage: chord type x scale degree of the key at this fret, with the number of ways.

Two modes (E-28, replaces the old Voicing Finder & Position Solver window):
- Explore a position: the views above, for one bar position;
- Find a chord: pick a root and chord type and see every position on frets 0..N (fret, stance,
  grip, ergonomics, inversion, intervals), with tones you can leave out (rootless / shell voicings).
Both modes share the filters, and selecting a way in either feeds the Circle-of-Fifths proximity
radar (IV, V, V7, vi, ii moves from that voicing; core.chord_atlas.find_neighbors, E-29: the same
strict match rule as the rest of the atlas, so a triad is never offered as a V7).

The neck is scanned once (core.chord_atlas.build_atlas); filters never re-scan. MainWindow keeps
the window in sync with the active neck (`set_active_neck`), the fretboard pocket
(`set_current_pocket`) and the note spelling (`on_note_spelling_changed`).
"""

from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.chord_atlas import (
    ATLAS_GRIP_SIZES,
    ATLAS_MAX_SPAN,
    GRIP_SOURCE_ALL,
    GRIP_SOURCE_CURRENT,
    GRIP_SOURCE_CUSTOM,
    GRIP_SOURCE_POCKETS,
    GRIP_SOURCE_SOLVER,
    AtlasEntry,
    ChordAtlas,
    ChordPosition,
    build_atlas,
    by_stance,
    coverage,
    filter_atlas,
    find_chord,
    find_neighbors,
    grips_for_config,
    sort_positions,
)
from core.copedant_compare import (
    INVERSION_SHORT,
    ChordSighting,
    chord_symbol,
    format_controllers,
    format_sighting,
    inversion_name,
    nashville,
    neck_tonic_pc,
    root_name,
)
from core.ergonomics import StanceDifficulty
from core.models import Neck, SteelGuitar
from core.theory import CHORD_FORMULAS, CHORD_SYMBOL_SUFFIX, NASHVILLE_SCALE_DEGREES, note_names, respell
from ui.chord_filter_bar import ChordFilterBar

_ROLE_WAY = Qt.UserRole          # (AtlasEntry, ChordSighting) on a "way" row
_ROLE_PENDING = Qt.UserRole + 1  # payload for lazily filled children
MODE_EXPLORE, MODE_FIND = "explore", "find"
RADAR_MECHANICS = [
    ("Same-Fret Pedal Drop", "Same-fret drops"),
    ("Hold Pedals & Slide", "Hold pedals & slide"),
    ("Open Bar Shift", "Open bar shifts"),
    ("Position Shift", "Position shifts"),
]
_ERGO_TEXT = {StanceDifficulty.NATURAL: "Natural", StanceDifficulty.STANDARD: "Standard",
              StanceDifficulty.AWKWARD: "Awkward"}
GRIP_SOURCES = [GRIP_SOURCE_ALL, GRIP_SOURCE_POCKETS, GRIP_SOURCE_SOLVER, GRIP_SOURCE_CURRENT, GRIP_SOURCE_CUSTOM]


class ChordAtlasDialog(QDialog):
    # fret, controllers (set), grip strings (set), root, chord type
    stance_selected = Signal(int, object, object, object, object)
    activate_neck_requested = Signal(int)
    # Find mode root / chord type changed -> harmonic target panel
    target_changed = Signal(str, str)

    def __init__(
        self,
        neck: Neck,
        guitar: Optional[SteelGuitar] = None,
        neck_idx: Optional[int] = None,
        active_neck_idx: Optional[int] = None,
        current_pocket: Optional[Set[int]] = None,
        mode: str = MODE_EXPLORE,
        find_root: Optional[str] = None,
        find_chord_type: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Chord Atlas")
        self.resize(1180, 760)
        self.neck = neck
        self.guitar = guitar
        self.active_neck_idx = active_neck_idx
        self.current_pocket: Set[int] = set(current_pocket or ())
        self.atlas: Optional[ChordAtlas] = None
        self._atlas_cache: Dict[int, Tuple[Neck, ChordAtlas]] = {}
        self.entries: List[AtlasEntry] = []
        self.positions: List[ChordPosition] = []
        self._radar_origin = None   # (fret, controllers, strings, root name, chord type, gained-neck flag)
        self._radar_neighbors = []
        # The radar runs 5 voicing searches (about 1 s on a 12-string): wait until the selection settles.
        self._radar_timer = QTimer(self)
        self._radar_timer.setSingleShot(True)
        self._radar_timer.setInterval(250)
        self._radar_timer.timeout.connect(self.update_radar_now)

        self._build_ui(neck_idx)
        self._rescan()
        if mode == MODE_FIND:
            self.set_find_target(find_root or "E", find_chord_type or "Major")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self, neck_idx: Optional[int]):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.addWidget(QLabel("<b>Mode:</b>"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Explore a position", MODE_EXPLORE)
        self.combo_mode.addItem("Find a chord", MODE_FIND)
        self.combo_mode.setToolTip("Explore: every chord at one bar position.\n"
                                   "Find: every position of one chord on the neck.")
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        top.addWidget(self.combo_mode)
        top.addSpacing(12)
        self.combo_neck: Optional[QComboBox] = None
        self.chk_follow: Optional[QCheckBox] = None
        if self.guitar is not None:
            top.addWidget(QLabel("<b>Copedant:</b>"))
            self.combo_neck = QComboBox()
            self.combo_neck.setMinimumWidth(240)
            top.addWidget(self.combo_neck)
            self._fill_neck_combo(neck_idx)
            self.combo_neck.currentIndexChanged.connect(self._on_neck_combo_changed)
            self.chk_follow = QCheckBox("Follow active neck")
            self.chk_follow.setChecked(True)
            self.chk_follow.setToolTip("Switch to whichever neck is active in the main window.")
            top.addWidget(self.chk_follow)
        else:
            top.addWidget(QLabel(f"<b>Copedant:</b> {self.neck.name}"))
        top.addSpacing(12)
        self.explore_controls = QWidget()
        ex = QHBoxLayout(self.explore_controls)
        ex.setContentsMargins(0, 0, 0, 0)
        ex.addWidget(QLabel("Show at fret:"))
        self.spin_fret = QSpinBox()
        self.spin_fret.setRange(0, 11)
        self.spin_fret.setToolTip("Chord availability is the same at every fret; this only transposes the names.")
        self.spin_fret.valueChanged.connect(self._on_fret_changed)
        ex.addWidget(self.spin_fret)
        self.lbl_key = QLabel("")
        ex.addWidget(self.lbl_key)
        ex.addSpacing(12)
        ex.addWidget(QLabel("Root:"))
        self.combo_root = QComboBox()
        self.combo_root.setProperty("keepSpelling", True)  # rebuilt here on spelling / fret changes
        self.combo_root.currentIndexChanged.connect(self._refresh_view)
        ex.addWidget(self.combo_root)
        top.addWidget(self.explore_controls)
        top.addStretch()
        root.addLayout(top)

        # Find mode: target chord, tones to leave out, fret range, sorting
        self.find_controls = QWidget()
        fd = QHBoxLayout(self.find_controls)
        fd.setContentsMargins(0, 0, 0, 0)
        fd.addWidget(QLabel("<b>Find:</b>"))
        self.combo_find_root = QComboBox()
        self.combo_find_root.setProperty("keepSpelling", True)  # rebuilt here on spelling changes
        self.combo_find_root.addItems(note_names())
        self.combo_find_root.setCurrentText("E")
        self.combo_find_root.currentIndexChanged.connect(self._on_find_target_changed)
        fd.addWidget(self.combo_find_root)
        self.combo_find_type = QComboBox()
        self.combo_find_type.addItems(list(CHORD_FORMULAS))
        self.combo_find_type.currentIndexChanged.connect(self._on_find_type_changed)
        fd.addWidget(self.combo_find_type)
        fd.addSpacing(10)
        lbl_omit = QLabel("Tones that must sound:")
        lbl_omit.setToolTip("Untick a tone to leave it out (it must not sound): untick R for rootless\n"
                            "voicings, 5 for shells. 'Include no-5th shells' also allows a missing 5th.")
        fd.addWidget(lbl_omit)
        self.omit_box = QHBoxLayout()
        self.omit_box.setSpacing(6)
        fd.addLayout(self.omit_box)
        self.tone_checks: Dict[str, QCheckBox] = {}
        fd.addSpacing(10)
        fd.addWidget(QLabel("Up to fret:"))
        self.spin_max_fret = QSpinBox()
        self.spin_max_fret.setRange(0, 24)
        self.spin_max_fret.setValue(15)
        self.spin_max_fret.valueChanged.connect(self._refresh_view)
        fd.addWidget(self.spin_max_fret)
        self.chk_hide_awkward = QCheckBox("Hide awkward stances")
        self.chk_hide_awkward.toggled.connect(self._refresh_view)
        fd.addWidget(self.chk_hide_awkward)
        fd.addWidget(QLabel("Sort:"))
        self.combo_sort = QComboBox()
        self.combo_sort.addItem("Easiest first", "easiest")
        self.combo_sort.addItem("By fret", "fret")
        self.combo_sort.currentIndexChanged.connect(self._refresh_view)
        fd.addWidget(self.combo_sort)
        fd.addStretch()
        self.find_controls.setVisible(False)
        root.addWidget(self.find_controls)
        self._rebuild_tone_checks()

        self.filter_bar = ChordFilterBar()
        self.filter_bar.changed.connect(self._refresh_view)
        root.addWidget(self.filter_bar)

        # Grip configuration
        grip = QHBoxLayout()
        grip.addWidget(QLabel("<b>Grips:</b>"))
        self.combo_grips = QComboBox()
        self.combo_grips.addItems(GRIP_SOURCES)
        self.combo_grips.setToolTip(
            "All string groups: every 3-5 string set within the span.\n"
            "Pocket presets: the grip bar's cards for this tuning.\n"
            "Voicing finder grips: the grips the voicing finder searches.\n"
            "Current pocket: the strings selected on the fretboard.\n"
            "Custom: your own groups, e.g. 8-6-5, 6-5-4, 10-8-6.")
        self.combo_grips.currentIndexChanged.connect(self._on_grip_source_changed)
        grip.addWidget(self.combo_grips)
        self.edit_custom = QLineEdit()
        self.edit_custom.setPlaceholderText("e.g. 8-6-5, 6-5-4, 10-8-6")
        self.edit_custom.setVisible(False)
        self.edit_custom.editingFinished.connect(self._refresh_view)
        grip.addWidget(self.edit_custom, stretch=1)
        grip.addSpacing(10)
        size_tip = ("How many strings the grip picks at once:\n"
                    "3 = triads like 8-6-5, 4 = four-note grips like 8-6-5-4, 5 = five-note grips.")
        lbl_sizes = QLabel("Notes per grip:")
        lbl_sizes.setToolTip(size_tip)
        grip.addWidget(lbl_sizes)
        self.size_checks: Dict[int, QCheckBox] = {}
        for size in ATLAS_GRIP_SIZES:
            cb = QCheckBox(str(size))
            cb.setChecked(size in (3, 4))
            cb.setToolTip(size_tip)
            cb.toggled.connect(self._refresh_view)
            grip.addWidget(cb)
            self.size_checks[size] = cb
        grip.addSpacing(10)
        span_tip = ("How far apart the outer strings of a grip may be, counting every string between them\n"
                    "(skipped strings included): 8-6-5 spans 4 strings (8,7,6,5), 10-8-6 spans 5.\n"
                    "Lower it to keep grips compact for your picking hand.")
        lbl_span = QLabel("Max stretch (strings):")
        lbl_span.setToolTip(span_tip)
        grip.addWidget(lbl_span)
        self.spin_span = QSpinBox()
        self.spin_span.setRange(3, ATLAS_MAX_SPAN)
        self.spin_span.setValue(5)
        self.spin_span.setToolTip(span_tip)
        self.spin_span.valueChanged.connect(self._refresh_view)
        grip.addWidget(self.spin_span)
        self.lbl_grip_count = QLabel("")
        grip.addWidget(self.lbl_grip_count)
        grip.addStretch()
        root.addLayout(grip)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setTextFormat(Qt.RichText)
        root.addWidget(self.lbl_summary)

        self.tabs = QTabWidget()
        self.tree_chords = self._make_tree(["Chord", "Degree", "Ways"])
        self.tabs.addTab(self.tree_chords, "By chord")
        self.tree_stances = self._make_tree(["Stance", "Chords", "Ways"])
        self.tabs.addTab(self.tree_stances, "By stance")
        self.table_cov = QTableWidget()
        self.table_cov.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_cov.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_cov.cellDoubleClicked.connect(self._on_coverage_double_clicked)
        self.tabs.addTab(self.table_cov, "Coverage")
        self.tabs.currentChanged.connect(lambda *_: self._update_radar_from_selection())
        self.tree_chords.currentItemChanged.connect(lambda *_: self._update_radar_from_selection())
        self.tree_stances.currentItemChanged.connect(lambda *_: self._update_radar_from_selection())

        self.table_pos = QTableWidget(0, 7)
        self.table_pos.setHorizontalHeaderLabels(
            ["Fret", "Pedals / levers", "Ergonomics", "Strings", "Inversion", "Intervals (low → high)", "Missing"])
        self.table_pos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_pos.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_pos.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_pos.verticalHeader().setVisible(False)
        self.table_pos.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table_pos.horizontalHeader().setStretchLastSection(True)
        self.table_pos.cellDoubleClicked.connect(self._on_position_double_clicked)
        self.table_pos.itemSelectionChanged.connect(self._update_radar_from_selection)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.tabs)
        self.stack.addWidget(self.table_pos)

        # Circle-of-Fifths proximity radar (from the old Voicing Finder)
        self.radar_box = QGroupBox("Circle-of-Fifths radar: IV, V, V7, vi, ii moves from the selected voicing")
        self.radar_box.setCheckable(True)
        self.radar_box.setChecked(True)
        self.radar_box.toggled.connect(lambda on: (self.radar_body.setVisible(on), self._update_radar_from_selection()))
        rb = QVBoxLayout(self.radar_box)
        rb.setContentsMargins(8, 4, 8, 4)
        self.radar_body = QWidget()
        rbl = QVBoxLayout(self.radar_body)
        rbl.setContentsMargins(0, 0, 0, 0)
        chips = QHBoxLayout()
        chips.addWidget(QLabel("Moves:"))
        self.mechanic_buttons: Dict[str, QPushButton] = {}
        for key, label in RADAR_MECHANICS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.toggled.connect(lambda *_: self._update_radar_from_selection())
            chips.addWidget(btn)
            self.mechanic_buttons[key] = btn
        self.lbl_radar_origin = QLabel("")
        chips.addWidget(self.lbl_radar_origin, stretch=1)
        rbl.addLayout(chips)
        self.table_radar = QTableWidget(0, 5)
        self.table_radar.setHorizontalHeaderLabels(["Relationship", "Chord", "Move", "Δ frets", "How"])
        self.table_radar.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_radar.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_radar.verticalHeader().setVisible(False)
        self.table_radar.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table_radar.horizontalHeader().setStretchLastSection(True)
        self.table_radar.cellDoubleClicked.connect(self._on_radar_double_clicked)
        rbl.addWidget(self.table_radar)
        rb.addWidget(self.radar_body)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.stack)
        splitter.addWidget(self.radar_box)
        splitter.setSizes([520, 200])
        root.addWidget(splitter, stretch=1)

        self.lbl_hint = QLabel("")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("font-size: 11px;")
        root.addWidget(self.lbl_hint)

        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

    def _make_tree(self, headers: List[str]) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setColumnCount(len(headers))
        tree.setHeaderLabels(headers)
        tree.setColumnWidth(0, 460)
        tree.itemExpanded.connect(self._fill_children)
        tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        return tree

    def _fill_neck_combo(self, selected: Optional[int]):
        combo = self.combo_neck
        combo.blockSignals(True)
        combo.clear()
        for idx, n in enumerate(self.guitar.necks):
            mark = "  ● active" if idx == self.active_neck_idx else ""
            combo.addItem(f"{n.name} ({n.string_count} Str){mark}", idx)
        if selected is not None and 0 <= selected < combo.count():
            combo.setCurrentIndex(selected)
        combo.blockSignals(False)

    def _fill_root_combo(self):
        fret = self.spin_fret.value()
        current = self.combo_root.currentData()
        self.combo_root.blockSignals(True)
        self.combo_root.clear()
        self.combo_root.addItem("All roots", None)
        for pc in range(12):  # pc = root at fret 0; label = name at the displayed fret
            self.combo_root.addItem(root_name(pc, fret), pc)
        row = self.combo_root.findData(current) if current is not None else 0
        self.combo_root.setCurrentIndex(max(row, 0))
        self.combo_root.blockSignals(False)

    # ------------------------------------------------------------------
    # Public API (MainWindow, tests)
    # ------------------------------------------------------------------
    @property
    def neck_idx(self) -> Optional[int]:
        return self.combo_neck.currentData() if self.combo_neck is not None else None

    def set_active_neck(self, active_idx: int, guitar: Optional[SteelGuitar] = None):
        if self.guitar is None:
            return
        if guitar is not None:
            self.guitar = guitar
        self.active_neck_idx = active_idx
        n = len(self.guitar.necks)
        sel = active_idx if self.chk_follow.isChecked() else self.neck_idx
        sel = sel if sel is not None and sel < n else min(active_idx, n - 1)
        self._fill_neck_combo(sel)
        new_neck = self.guitar.necks[sel]
        if new_neck is not self.neck:
            self.neck = new_neck
            self._rescan()
        # Same neck: nothing to rebuild (this can run from inside a tree double-click).

    def set_current_pocket(self, pocket):
        self.current_pocket = set(pocket or ())
        if self.combo_grips.currentText() == GRIP_SOURCE_CURRENT:
            self._refresh_view()

    def on_note_spelling_changed(self):
        self._fill_root_combo()
        current = self.combo_find_root.currentText()
        self.combo_find_root.blockSignals(True)
        self.combo_find_root.clear()
        self.combo_find_root.addItems(note_names())
        self.combo_find_root.setCurrentText(respell(current))
        self.combo_find_root.blockSignals(False)
        self._refresh_view()

    @property
    def mode(self) -> str:
        return self.combo_mode.currentData()

    def set_mode(self, mode: str):
        self.combo_mode.setCurrentIndex(0 if mode == MODE_EXPLORE else 1)

    def set_find_target(self, root: Optional[str], chord_type: Optional[str]):
        """Switches to Find mode for `root chord_type` (any spelling)."""
        self.combo_find_root.blockSignals(True)
        self.combo_find_type.blockSignals(True)
        if root and respell(root) in note_names():
            self.combo_find_root.setCurrentText(respell(root))
        if chord_type in CHORD_FORMULAS:
            self.combo_find_type.setCurrentText(chord_type)
        self.combo_find_root.blockSignals(False)
        self.combo_find_type.blockSignals(False)
        self._rebuild_tone_checks()
        if self.mode != MODE_FIND:
            self.set_mode(MODE_FIND)  # refreshes
        else:
            self._refresh_view()

    def omitted_tones(self) -> Set[str]:
        return {lbl for lbl, cb in self.tone_checks.items() if not cb.isChecked()}

    def set_omitted_tones(self, labels):
        for lbl, cb in self.tone_checks.items():
            cb.blockSignals(True)
            cb.setChecked(lbl not in set(labels))
            cb.blockSignals(False)
        self._refresh_view()

    def set_grip_source(self, source: str, custom: str = ""):
        if custom:
            self.edit_custom.setText(custom)
        self.combo_grips.setCurrentText(source)
        self._refresh_view()

    def current_grips(self) -> List[Tuple[int, ...]]:
        """String groups allowed by the grip settings. Groups you name yourself (current pocket,
        custom) ignore the size and span boxes."""
        source = self.combo_grips.currentText()
        explicit = source in (GRIP_SOURCE_CURRENT, GRIP_SOURCE_CUSTOM)
        sizes = range(1, 13) if explicit else [s for s, cb in self.size_checks.items() if cb.isChecked()]
        span = 12 if explicit else self.spin_span.value()
        return grips_for_config(self.neck, source, sizes, span,
                                current_pocket=self.current_pocket, custom=self.edit_custom.text())

    # ------------------------------------------------------------------
    # Scan and render
    # ------------------------------------------------------------------
    def _on_neck_combo_changed(self, _row: int):
        self.neck = self.guitar.necks[self.combo_neck.currentData()]
        if self.chk_follow is not None and self.combo_neck.currentData() != self.active_neck_idx:
            self.chk_follow.setChecked(False)  # the user picked another neck on purpose
        self._rescan()

    def _rescan(self):
        cached = self._atlas_cache.get(id(self.neck))
        if cached is not None and cached[0] is self.neck:
            self.atlas = cached[1]
        else:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                # Every way was checked with grip_matches_chord in tests; the matcher applies the
                # same rule, so the interactive scan skips the per-way re-check (2 s on a U12).
                self.atlas = build_atlas(self.neck, verify=False)
            finally:
                QApplication.restoreOverrideCursor()
            self._atlas_cache[id(self.neck)] = (self.neck, self.atlas)
        self.filter_bar.set_controllers(set(self.neck.pedals) | set(self.neck.knee_levers))
        self._fill_root_combo()
        self._refresh_view()

    def _on_fret_changed(self, _value: int):
        self._fill_root_combo()
        self._refresh_view()

    def _on_grip_source_changed(self, _row: int):
        source = self.combo_grips.currentText()
        self.edit_custom.setVisible(source == GRIP_SOURCE_CUSTOM)
        explicit = source in (GRIP_SOURCE_CURRENT, GRIP_SOURCE_CUSTOM)
        for cb in self.size_checks.values():
            cb.setEnabled(not explicit)
        self.spin_span.setEnabled(not explicit)
        self._refresh_view()

    def _refresh_view(self, *_):
        if self.atlas is None:
            return
        fret = self.spin_fret.value()
        tonic = neck_tonic_pc(self.neck)
        self.lbl_key.setText(f"(key of {root_name(tonic, fret)})")

        grips = self.current_grips()
        outside = [g for g in grips if not (min(ATLAS_GRIP_SIZES) <= len(g) <= max(ATLAS_GRIP_SIZES))
                   or max(g) - min(g) > ATLAS_MAX_SPAN - 1]
        count = f"{len(grips)} string groups"
        if outside:
            count += (f" ⚠ {len(outside)} outside the scanned range "
                      f"({min(ATLAS_GRIP_SIZES)}-{max(ATLAS_GRIP_SIZES)} strings within {ATLAS_MAX_SPAN})")
        self.lbl_grip_count.setText(count)
        keep = self.filter_bar.keep(grips=grips)
        if self.mode == MODE_FIND:
            self._refresh_find(keep, grips)
            return
        self.entries = filter_atlas(self.atlas, keep, self.filter_bar.selected_chord_types(),
                                    root_pc=self.combo_root.currentData())

        n_ways = sum(len(e.sightings) for e in self.entries)
        stances = by_stance(self.entries)
        only = self.filter_bar.only_using_text()
        summary = (f"<b>{self.neck.name}</b>: <b>{len(self.entries)}</b> chords, {n_ways} ways, "
                   f"from {len(stances)} stances and {len(grips)} string groups"
                   f"{' — ' + only if only else ''}. "
                   f"<span style='font-size:11px'>Scanned {self.atlas.stance_count} stances × "
                   f"{self.atlas.grip_count} grips.</span>")
        if not grips:
            summary += "<br><b>No string groups match the grip settings.</b>"
        self.lbl_summary.setText(summary)

        self._render_chords(fret)
        self._render_stances(stances, fret)
        self._render_coverage(tonic, fret)
        self.lbl_hint.setText(
            "Double-click a way to play it on the fretboard"
            + (" (its neck is made active first if needed)" if self.guitar is not None else "")
            + ". Double-click a Coverage cell to jump to that chord. This window can stay open.")

    # ------------------------------------------------------------------
    # Mode switching and Find mode
    # ------------------------------------------------------------------
    def _on_mode_changed(self, _row: int):
        find = self.mode == MODE_FIND
        self.explore_controls.setVisible(not find)
        self.find_controls.setVisible(find)
        self.filter_bar.btn_types.setVisible(not find)  # Find mode targets one chord type
        self.stack.setCurrentIndex(1 if find else 0)
        self.setWindowTitle("Chord Atlas — Find a chord" if find else "Chord Atlas")
        self._refresh_view()

    def _rebuild_tone_checks(self):
        while self.omit_box.count():
            w = self.omit_box.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.tone_checks = {}
        for _st, lbl in sorted(CHORD_FORMULAS[self.combo_find_type.currentText()].items()):
            cb = QCheckBox(lbl)
            cb.setChecked(True)
            cb.toggled.connect(self._refresh_view)
            self.omit_box.addWidget(cb)
            self.tone_checks[lbl] = cb

    def _on_find_type_changed(self, _row: int):
        self._rebuild_tone_checks()
        self._on_find_target_changed()

    def _on_find_target_changed(self, *_):
        self.target_changed.emit(self.combo_find_root.currentText(), self.combo_find_type.currentText())
        self._refresh_view()

    def _refresh_find(self, keep, grips):
        root = self.combo_find_root.currentText()
        ctype = self.combo_find_type.currentText()
        found = find_chord(self.atlas, root, ctype, omitted=self.omitted_tones(),
                           allow_no_fifth=self.filter_bar.chk_shells.isChecked(),
                           max_fret=self.spin_max_fret.value())
        hide_awkward = self.chk_hide_awkward.isChecked()
        found = [p for p in found if keep(p.sighting)
                 and not (hide_awkward and p.ergonomics.difficulty == StanceDifficulty.AWKWARD)]
        self.positions = sort_positions(found, self.combo_sort.currentData())

        table = self.table_pos
        header = table.horizontalHeader()
        # Resize-to-contents re-measures on every setItem (16 ms each with ~7000 cells): size once at the end.
        table.setUpdatesEnabled(False)
        header.setSectionResizeMode(QHeaderView.Interactive)
        table.clearContents()
        table.setRowCount(len(self.positions))
        for row, p in enumerate(self.positions):
            s = p.sighting
            inv = INVERSION_SHORT.get(s.inversion, "")
            cells = [str(p.fret), format_controllers(s.controllers), _ERGO_TEXT.get(p.ergonomics.difficulty, ""),
                     "-".join(map(str, s.strings)), inv, " - ".join(p.formula),
                     ", ".join(p.missing) if p.missing else ""]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col in (0, 3):
                    item.setTextAlignment(Qt.AlignCenter)
                if col == 4:
                    item.setToolTip(inversion_name(s.chord_type, s.bass_interval))
                table.setItem(row, col, item)
        table.resizeColumnsToContents()
        header.setStretchLastSection(True)
        table.setUpdatesEnabled(True)

        only = self.filter_bar.only_using_text()
        omitted = self.omitted_tones()
        name = f"{respell(root)}{CHORD_SYMBOL_SUFFIX.get(ctype, '')}"
        frets = sorted({p.fret for p in self.positions})
        self.lbl_summary.setText(
            f"<b>{name}</b> on <b>{self.neck.name}</b>: <b>{len(self.positions)}</b> positions on "
            f"{len(frets)} frets (0–{self.spin_max_fret.value()})"
            f"{' — leaving out ' + ', '.join(sorted(omitted)) if omitted else ''}"
            f"{' — ' + only if only else ''}."
            + ("<br><b>No string groups match the grip settings.</b>" if not grips else ""))
        self.lbl_hint.setText("Double-click a position to play it on the fretboard"
                              + (" (its neck is made active first if needed)" if self.guitar is not None else "")
                              + ". Select one to see Circle-of-Fifths moves from it below.")
        if self.positions:
            table.selectRow(0)
        else:
            self._update_radar_from_selection()

    def _ensure_neck_active(self) -> bool:
        """Makes the atlas neck the active one (menu mode). False if MainWindow did not switch."""
        if self.guitar is None:
            return True
        idx = self.neck_idx
        if idx != self.active_neck_idx:
            self.activate_neck_requested.emit(idx)
        return idx == self.active_neck_idx

    def _on_position_double_clicked(self, row: int, _col: int = 0):
        if not (0 <= row < len(self.positions)):
            return
        p = self.positions[row]
        if not self._ensure_neck_active():
            return
        self.stance_selected.emit(p.fret, set(p.sighting.controllers), set(p.sighting.strings),
                                  respell(self.combo_find_root.currentText()), p.sighting.chord_type)

    # ------------------------------------------------------------------
    # Circle-of-Fifths radar
    # ------------------------------------------------------------------
    def _selected_origin(self):
        """(fret, controllers, strings, root name, chord type) of the selected voicing, or None."""
        if self.mode == MODE_FIND:
            row = self.table_pos.currentRow()
            if not (0 <= row < len(self.positions)):
                return None
            p = self.positions[row]
            return (p.fret, p.sighting.controllers, p.sighting.strings,
                    self.combo_find_root.currentText(), p.sighting.chord_type)
        tree = self.tabs.currentWidget()
        item = tree.currentItem() if isinstance(tree, QTreeWidget) else None
        payload = item.data(0, _ROLE_WAY) if item is not None else None
        if not payload:
            return None
        entry, s = payload
        fret = self.spin_fret.value()
        return (fret, s.controllers, s.strings, root_name(entry.root_pc, fret), entry.chord_type)

    def _update_radar_from_selection(self):
        self._radar_timer.start()

    def update_radar_now(self):
        self._radar_timer.stop()
        origin = self._selected_origin() if self.radar_box.isChecked() else None
        self._radar_origin = origin
        self.table_radar.setRowCount(0)
        self._radar_neighbors = []
        if origin is None:
            self.lbl_radar_origin.setText("Select a voicing to see moves from it." if self.radar_box.isChecked() else "")
            return
        fret, ctrls, strings, root, ctype = origin
        allowed = {k for k, b in self.mechanic_buttons.items() if b.isChecked()}
        self.lbl_radar_origin.setText(
            f"From <b>{root}{CHORD_SYMBOL_SUFFIX.get(ctype, '')}</b> at fret {fret}, {format_controllers(ctrls)}, "
            f"strings {'-'.join(map(str, strings))}")
        neighbors = find_neighbors(
            self.atlas, origin_root=root, origin_fret=fret, origin_strings=strings,
            origin_controllers=ctrls, allowed_moves=allowed,
            allow_no_fifth=self.filter_bar.chk_shells.isChecked())
        self._radar_neighbors = neighbors
        self.table_radar.setRowCount(len(neighbors))
        for row, n in enumerate(neighbors):
            delta = f"{n.delta_frets:+d}" if n.delta_frets else "0"
            chord = f"{n.root}{CHORD_SYMBOL_SUFFIX.get(n.chord_type, '')}"
            for col, text in enumerate([n.relationship, chord, n.movement, delta, n.how]):
                item = QTableWidgetItem(text)
                if col == 2:
                    color = {"Hold Pedals & Slide": "#0d6efd", "Same-Fret Pedal Drop": "#28a745",
                             "Open Bar Shift": "#d39e00"}.get(n.movement)
                    if color:
                        item.setForeground(QColor(color))
                self.table_radar.setItem(row, col, item)

    def _on_radar_double_clicked(self, row: int, _col: int = 0):
        if not (0 <= row < len(self._radar_neighbors)):
            return
        n = self._radar_neighbors[row]
        if not self._ensure_neck_active():
            return
        # Same flow as any other way: the target chord becomes the harmonic target, then the stance.
        self.stance_selected.emit(n.fret, set(n.controllers), set(n.strings), n.root, n.chord_type)

    def _render_chords(self, fret: int):
        tree = self.tree_chords
        tree.clear()
        bold = QFont()
        bold.setBold(True)
        for e in self.entries:
            item = QTreeWidgetItem([f"{chord_symbol(e.root_pc, e.chord_type, fret)}   ({e.chord_type})",
                                    nashville(self.neck, e.root_pc, e.chord_type, fret), str(len(e.sightings))])
            item.setFont(0, bold)
            item.setToolTip(0, f"Easiest: {format_sighting(e.best)}")
            item.setData(0, _ROLE_PENDING, ("chord", e))
            item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            tree.addTopLevelItem(item)

    def _render_stances(self, stances, fret: int):
        tree = self.tree_stances
        tree.clear()
        for ctrls, pairs in stances.items():
            chords = list(dict.fromkeys((e.root_pc, e.chord_type) for e, _ in pairs))  # atlas order
            names = ", ".join(chord_symbol(r, t, fret) for r, t in chords[:8]) + (" …" if len(chords) > 8 else "")
            item = QTreeWidgetItem([format_controllers(ctrls), names, str(len(pairs))])
            item.setData(0, _ROLE_PENDING, ("stance", pairs))
            item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            tree.addTopLevelItem(item)

    def _fill_children(self, item: QTreeWidgetItem):
        pending = item.data(0, _ROLE_PENDING)
        if not pending or item.childCount():
            return
        fret = self.spin_fret.value()
        kind, payload = pending
        if kind == "chord":
            for s in payload.sightings:
                self._add_way(item, payload, s, format_sighting(s))
        else:
            for e, s in payload:
                shell = " (no 5th)" if s.is_shell else ""
                inv = INVERSION_SHORT.get(s.inversion)
                inv = f" · {inv}" if inv else ""
                label = (f"{chord_symbol(e.root_pc, e.chord_type, fret)} — strings "
                         f"{'-'.join(map(str, s.strings))}{shell}{inv}")
                self._add_way(item, e, s, label)

    def _add_way(self, parent: QTreeWidgetItem, entry: AtlasEntry, s: ChordSighting, label: str):
        child = QTreeWidgetItem([label, "", ""])
        child.setData(0, _ROLE_WAY, (entry, s))
        child.setToolTip(0, inversion_name(s.chord_type, s.bass_interval))
        if s.is_shell:
            child.setForeground(0, QColor("#8b949e"))
        parent.addChild(child)

    def _render_coverage(self, tonic: int, fret: int):
        cov = coverage(self.entries, tonic)
        table = self.table_cov
        table.clear()
        types = list(cov)
        table.setRowCount(len(types))
        table.setColumnCount(12)
        key_pc = tonic + fret
        table.setHorizontalHeaderLabels(
            [f"{NASHVILLE_SCALE_DEGREES[d]}\n{root_name(key_pc + d)}" for d in range(12)])
        table.setVerticalHeaderLabels([f"{t}  ({CHORD_SYMBOL_SUFFIX.get(t) or 'maj'})" for t in types])
        diatonic = {0, 2, 4, 5, 7, 9, 11}
        for r, ctype in enumerate(types):
            for d in range(12):
                n = cov[ctype].get(d, 0)
                cell = QTableWidgetItem(str(n) if n else "")
                cell.setTextAlignment(Qt.AlignCenter)
                cell.setData(Qt.UserRole, ((tonic + d) % 12, ctype))
                if n:
                    alpha = min(60 + n * 12, 220)
                    cell.setBackground(QColor(40, 167, 69, alpha) if d in diatonic else QColor(13, 110, 253, alpha))
                    cell.setToolTip(f"{chord_symbol((tonic + d) % 12, ctype, fret)}: {n} ways")
                table.setItem(r, d, cell)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------
    def _on_coverage_double_clicked(self, row: int, col: int):
        cell = self.table_cov.item(row, col)
        if cell is None or not cell.text():
            return
        root_pc, ctype = cell.data(Qt.UserRole)
        self.select_chord(root_pc, ctype)

    def select_chord(self, root_pc: int, chord_type: str) -> bool:
        """Shows a chord in the By chord view, expanded."""
        for i in range(self.tree_chords.topLevelItemCount()):
            item = self.tree_chords.topLevelItem(i)
            kind, e = item.data(0, _ROLE_PENDING)
            if (e.root_pc, e.chord_type) == (root_pc, chord_type):
                self.tabs.setCurrentWidget(self.tree_chords)
                item.setExpanded(True)
                self.tree_chords.setCurrentItem(item)
                self.tree_chords.scrollToItem(item, QAbstractItemView.PositionAtTop)
                return True
        return False

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _col: int = 0):
        payload = item.data(0, _ROLE_WAY)
        if not payload:
            return
        entry, s = payload
        if not self._ensure_neck_active():
            return
        fret = self.spin_fret.value()
        self.stance_selected.emit(fret, set(s.controllers), set(s.strings),
                                  root_name(entry.root_pc, fret), entry.chord_type)
