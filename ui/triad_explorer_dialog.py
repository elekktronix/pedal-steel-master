"""Triads Over a Chord explorer (E-19): Franklin, "Intervals" pp. 20-28.

Pick a backing chord; the table lists the triads that work over it and what each sounds like.
Select a triad to list its 3-string grips on the active neck; click a grip to put it on the
fretboard. The harmonic target is set to the "sounds like" chord when it has a formula, so the
canvas labels the triad tones as intervals of the backing chord (5, b7, 9 ...).
"""

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import Neck
from core.theory import NOTE_TO_SEMITONE, note_names
from core.triad_explorer import (
    SUPPORTED_CHORD_TYPES,
    TriadOverChord,
    explore,
    find_triad_grips,
    grip_intervals_over_chord,
)

ROOT_CHOICES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
_CATEGORY_TINT = {"Diatonic": "#5bc0de", "From the 3rd & 5th": "#ffc107", "Altered": "#ff6b6b"}


def common_root_name(name: Optional[str]) -> Optional[str]:
    """Respells a root into the root combo's spelling (global sharps/flats preference)."""
    if not name or name not in NOTE_TO_SEMITONE:
        return None
    return note_names()[NOTE_TO_SEMITONE[name]]


class TriadExplorerDialog(QDialog):
    # fret, controllers, grip strings, target root, target chord type
    grip_selected = Signal(int, object, object, object, object)

    def __init__(self, neck: Neck, root: Optional[str] = None, chord_type: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Triads Over a Chord (Franklin, Intervals pp. 20-28)")
        self.resize(980, 560)
        self.neck = neck
        self.triads: List[TriadOverChord] = []
        self.grips: list = []

        self._build_ui()
        self.combo_root.setCurrentText(common_root_name(root) or "G")
        self.combo_type.setCurrentText(chord_type if chord_type in SUPPORTED_CHORD_TYPES else "Dominant 7th")
        self.combo_root.currentIndexChanged.connect(self._refresh_triads)
        self.combo_type.currentIndexChanged.connect(self._refresh_triads)
        self._refresh_triads()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.addWidget(QLabel("<b>Backing chord:</b>"))
        self.combo_root = QComboBox()
        self.combo_root.addItems(note_names())
        top.addWidget(self.combo_root)
        self.combo_type = QComboBox()
        self.combo_type.addItems(SUPPORTED_CHORD_TYPES)
        self.combo_type.setMinimumWidth(160)
        top.addWidget(self.combo_type)
        top.addSpacing(12)
        hint = QLabel("Play the triad and let the bass play the root. "
                      "Stable = chord tones and 9/13; Sus = contains the 11; Altered = b5/#5/b9/#9.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #adb5bd; font-size: 11px;")
        top.addWidget(hint, stretch=1)
        root.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Group", "Triad", "On", "Intervals", "Sounds like", "Color"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._refresh_grips)
        splitter.addWidget(self.table)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.lbl_grips = QLabel("<b>Grips</b>")
        rl.addWidget(self.lbl_grips)
        self.lbl_source = QLabel("")
        self.lbl_source.setWordWrap(True)
        self.lbl_source.setStyleSheet("color: #adb5bd; font-size: 11px;")
        rl.addWidget(self.lbl_source)
        self.list_grips = QListWidget()
        self.list_grips.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 11px;")
        self.list_grips.itemClicked.connect(self._on_grip_clicked)
        rl.addWidget(self.list_grips, stretch=1)
        splitter.addWidget(right)
        splitter.setSizes([600, 360])
        root.addWidget(splitter, stretch=1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

    def _refresh_triads(self):
        self.triads = explore(self.combo_root.currentText(), self.combo_type.currentText())
        self.table.setRowCount(len(self.triads))
        for row, t in enumerate(self.triads):
            cells = [t.category, t.triad_name, t.built_on, " - ".join(t.intervals), t.sounds_like, t.color]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setForeground(QColor(_CATEGORY_TINT.get(t.category, "#dee2e6")))
                self.table.setItem(row, col, item)
        self.list_grips.clear()
        self.lbl_source.setText("")
        if self.triads:
            self.table.selectRow(0)

    def selected_triad(self) -> Optional[TriadOverChord]:
        rows = self.table.selectionModel().selectedRows()
        return self.triads[rows[0].row()] if rows else None

    def _refresh_grips(self):
        self.list_grips.clear()
        t = self.selected_triad()
        if t is None:
            return
        self.grips = find_triad_grips(self.neck, t)
        self.lbl_grips.setText(f"<b>{t.triad_name} grips on {self.neck.name}</b> ({len(self.grips)})")
        self.lbl_source.setText(f"{t.triad_name} = {' - '.join(t.intervals)} of "
                                f"{self.combo_root.currentText()} → sounds like {t.sounds_like}. From: {t.source}.")
        for m in self.grips:
            levers = "+".join(m.engaged_levers) or "open"
            strings = "-".join(map(str, sorted(m.grip_strings, reverse=True)))
            item = QListWidgetItem(f"Fret {m.fret:>2} | {levers:<10} | strings {strings:<8} | {grip_intervals_over_chord(t, m.voicing_formula)}")
            self.list_grips.addItem(item)
        if not self.grips:
            self.list_grips.addItem("No 3-string grip for this triad on this neck (frets 0-15).")

    def _on_grip_clicked(self, item: QListWidgetItem):
        row = self.list_grips.row(item)
        t = self.selected_triad()
        if t is None or row >= len(self.grips):
            return
        m = self.grips[row]
        if t.sounds_like_type:
            target = (self.combo_root.currentText(), t.sounds_like_type)
        else:
            target = (t.triad_root, t.triad_type)
        self.grip_selected.emit(m.fret, set(m.engaged_levers), set(m.grip_strings), target[0], target[1])
