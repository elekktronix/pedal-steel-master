"""Compare Copedants dialog (E-25).

Shows which chords a copedant change adds or removes: for all changes together, for each change
on its own, and the combined effects that only appear when changes work together. The scan runs
at fret 0 (see core.copedant_compare); the "Show at fret" box only transposes the names.

Filters (applied to the computed comparison, no re-scan):
- chord types (sticky checkable menu with presets), no-5th shells on/off;
- pedals/levers: with none selected every stance counts; otherwise only ways that use nothing but
  the selected controllers (open bar included) are shown, and "new"/"lost" is judged inside that
  set (core.copedant_compare.filter_report);
- maximum number of controllers held at once.

Two modes:
- editor mode (no `guitar`): the editor's working copy vs. the saved neck; nothing goes to the canvas;
- menu mode (`guitar` given, modeless): pick any two necks. Double-clicking a way to play a chord
  makes its neck active if needed (`activate_neck_requested`) and puts it on the fretboard
  (`stance_selected`). MainWindow calls `set_active_neck` whenever the active neck changes.
"""

from typing import List, Optional, Set

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.copedant_compare import (
    STATUS_ORDER,
    STATUS_TITLES,
    ComparisonReport,
    CopedantComparison,
    chord_symbol,
    compare_copedants,
    describe_delta,
    filter_report,
    format_sighting,
    nashville,
    neck_tonic_pc,
    root_name,
)
from core.models import Neck, SteelGuitar
from ui.chord_filter_bar import ChordFilterBar

_GAIN_COLOR = "#28a745"
_LOSS_COLOR = "#dc3545"
MAX_HEADLINES = 6


class CopedantCompareDialog(QDialog):
    # fret, controllers (set), grip strings (set), root, chord type
    stance_selected = Signal(int, object, object, object, object)
    # neck index the user wants to make active (to audition a way on that neck)
    activate_neck_requested = Signal(int)

    def __init__(
        self,
        base: Neck,
        modified: Neck,
        guitar: Optional[SteelGuitar] = None,
        base_idx: Optional[int] = None,
        modified_idx: Optional[int] = None,
        active_neck_idx: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Compare Copedants")
        self.resize(1180, 720)
        self.base = base
        self.modified = modified
        self.guitar = guitar
        self.active_neck_idx = active_neck_idx
        self.comparison: Optional[CopedantComparison] = None
        self._reports: List[ComparisonReport] = []

        self._build_ui(base_idx, modified_idx)
        self._recompute()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self, base_idx: Optional[int], modified_idx: Optional[int]):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        # Row 1: necks and display
        top = QHBoxLayout()
        self.combo_base: Optional[QComboBox] = None
        self.combo_mod: Optional[QComboBox] = None
        if self.guitar is not None:
            top.addWidget(QLabel("<b>Baseline:</b>"))
            self.combo_base = QComboBox()
            top.addWidget(self.combo_base)
            top.addWidget(QLabel("<b>Modified:</b>"))
            self.combo_mod = QComboBox()
            top.addWidget(self.combo_mod)
            self._fill_neck_combos(base_idx, modified_idx)
            self.combo_base.currentIndexChanged.connect(self._on_necks_changed)
            self.combo_mod.currentIndexChanged.connect(self._on_necks_changed)
        else:
            top.addWidget(QLabel(f"<b>Saved:</b> {self.base.name} &nbsp; vs &nbsp; <b>Edited copy</b>"))
        top.addSpacing(12)
        top.addWidget(QLabel("Show at fret:"))
        self.spin_fret = QSpinBox()
        self.spin_fret.setRange(0, 11)
        self.spin_fret.setToolTip("Chord availability is the same at every fret; this only transposes the names.")
        self.spin_fret.valueChanged.connect(self._refresh_view)
        top.addWidget(self.spin_fret)
        self.lbl_key = QLabel("")
        top.addWidget(self.lbl_key)
        top.addStretch()
        root.addLayout(top)

        # Rows 2-3: shared chord / controller filters (ui/chord_filter_bar.py)
        self.filter_bar = ChordFilterBar()
        self.filter_bar.changed.connect(self._refresh_view)
        show_box = QWidget()
        sb = QHBoxLayout(show_box)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.addWidget(QLabel("Show:"))
        self.combo_show = QComboBox()
        self.combo_show.addItems(["Gains & losses", "Gains only", "Losses only"])
        self.combo_show.currentIndexChanged.connect(self._refresh_view)
        sb.addWidget(self.combo_show)
        self.filter_bar.add_widget(show_box)
        root.addWidget(self.filter_bar)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("<b>Changes</b>"))
        self.list_scope = QListWidget()
        self.list_scope.currentRowChanged.connect(self._refresh_view)
        ll.addWidget(self.list_scope, stretch=1)
        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.lbl_summary = QLabel("")
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setTextFormat(Qt.RichText)
        rl.addWidget(self.lbl_summary)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Chord", "Degree", "Ways"])
        self.tree.setColumnWidth(0, 440)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        rl.addWidget(self.tree, stretch=1)
        self.lbl_hint = QLabel("")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("font-size: 11px;")
        rl.addWidget(self.lbl_hint)
        splitter.addWidget(right)
        splitter.setSizes([340, 840])
        root.addWidget(splitter, stretch=1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

    def _fill_neck_combos(self, base_idx: Optional[int], modified_idx: Optional[int]):
        for combo, sel in ((self.combo_base, base_idx), (self.combo_mod, modified_idx)):
            combo.blockSignals(True)
            combo.clear()
            combo.setMinimumWidth(230)
            for idx, n in enumerate(self.guitar.necks):
                mark = "  ● active" if idx == self.active_neck_idx else ""
                combo.addItem(f"{n.name} ({n.string_count} Str){mark}", idx)
            if sel is not None and 0 <= sel < combo.count():
                combo.setCurrentIndex(sel)
            combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Filters (delegate to the shared bar; public so tests and MainWindow can drive them)
    # ------------------------------------------------------------------
    @property
    def chk_shells(self):
        return self.filter_bar.chk_shells

    @property
    def spin_max_ctrl(self):
        return self.filter_bar.spin_max_ctrl

    @property
    def controller_buttons(self):
        return self.filter_bar.controller_buttons

    def selected_chord_types(self) -> List[str]:
        return self.filter_bar.selected_chord_types()

    def set_chord_types(self, types):
        self.filter_bar.set_chord_types(types)

    def selected_controllers(self) -> Set[str]:
        return self.filter_bar.selected_controllers()

    def set_controller_filter(self, controllers):
        self.filter_bar.set_controller_filter(controllers)

    def filtered_report(self, report: ComparisonReport) -> ComparisonReport:
        return filter_report(
            report,
            chord_types=self.selected_chord_types(),
            allowed_controllers=self.selected_controllers() or None,
            include_shells=self.chk_shells.isChecked(),
            max_controllers=self.filter_bar.max_controllers(),
            inversions=self.filter_bar.selected_inversions(),
            controller_match=self.filter_bar.controller_match(),
        )

    # ------------------------------------------------------------------
    # Active neck (menu mode)
    # ------------------------------------------------------------------
    def set_active_neck(self, active_idx: int, guitar: Optional[SteelGuitar] = None):
        """Called by MainWindow whenever the active neck changes (or the neck list was edited)."""
        if self.guitar is None:
            return
        if guitar is not None:
            self.guitar = guitar
        self.active_neck_idx = active_idx
        n = len(self.guitar.necks)
        b = self.combo_base.currentData()
        m = self.combo_mod.currentData()
        b = b if b is not None and b < n else min(active_idx, n - 1)
        m = m if m is not None and m < n else min(active_idx, n - 1)
        self._fill_neck_combos(b, m)
        new_base, new_mod = self.guitar.necks[b], self.guitar.necks[m]
        if new_base is not self.base or new_mod is not self.modified:
            self.base, self.modified = new_base, new_mod
            self._recompute()
        # Otherwise the results are unchanged; don't rebuild the tree (this can run from inside a
        # tree double-click, when the neck switch was requested by the dialog itself).

    def on_note_spelling_changed(self):
        self._refresh_view()

    # ------------------------------------------------------------------
    # Compute and render
    # ------------------------------------------------------------------
    def _on_necks_changed(self):
        self.base = self.guitar.necks[self.combo_base.currentData()]
        self.modified = self.guitar.necks[self.combo_mod.currentData()]
        self._recompute()

    def _recompute(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.comparison = compare_copedants(self.base, self.modified)
        finally:
            QApplication.restoreOverrideCursor()

        c = self.comparison
        self._reports = [c.total] + [rep for _, rep in c.per_item]
        labels = [f"All changes ({len(c.items)})"] + [item.description for item, _ in c.per_item]
        if c.per_item and c.interactions.deltas:
            self._reports.append(c.interactions)
            labels.append("Combined effects (changes working together)")
        self._scope_labels = labels

        self.list_scope.blockSignals(True)
        self.list_scope.clear()
        for label in labels:
            item = QListWidgetItem(label)
            item.setToolTip(label)
            self.list_scope.addItem(item)
        f = QFont()
        f.setBold(True)
        self.list_scope.item(0).setFont(f)
        self.list_scope.setCurrentRow(0)
        self.list_scope.blockSignals(False)
        ids = (set(self.base.pedals) | set(self.base.knee_levers)
               | set(self.modified.pedals) | set(self.modified.knee_levers))
        self.filter_bar.set_controllers(ids, highlight={i.controller_id for i in c.items})
        self._refresh_view()

    def _update_scope_counts(self):
        for row, (label, rep) in enumerate(zip(self._scope_labels, self._reports)):
            fr = self.filtered_report(rep)
            self.list_scope.item(row).setText(f"{label}   +{fr.gained_count} / −{fr.lost_count}")

    def _refresh_view(self, *_):
        fret = self.spin_fret.value()
        self.lbl_key.setText(f"(key of {root_name(neck_tonic_pc(self.modified), fret)})")
        self.tree.clear()
        if not self.comparison:
            return
        if not self.comparison.items:
            self.lbl_summary.setText("<b>The two copedants are identical</b> (pulls, splits, half-stops and tuning).")
            self.lbl_hint.setText("")
            return
        self._update_scope_counts()

        row = max(0, self.list_scope.currentRow())
        report = self._reports[row] if row < len(self._reports) else self.comparison.total
        show = self.combo_show.currentIndex()  # 0 both, 1 gains, 2 losses
        deltas = [d for d in self.filtered_report(report).deltas
                  if not (show == 1 and not d.gained) and not (show == 2 and not d.lost)]

        scope_txt = report.scope
        if self.filter_bar.only_using_text():
            scope_txt += " — " + self.filter_bar.only_using_text()
        heads = [describe_delta(d, self.modified, fret) for d in deltas[:MAX_HEADLINES]]
        summary = f"<b>{scope_txt}</b>: {len(deltas)} chords affected"
        if heads:
            summary += "<ul style='margin-top:2px'>" + "".join(f"<li>{h}</li>" for h in heads) + "</ul>"
        else:
            summary += " (none with the current filters)."
        self.lbl_summary.setText(summary)

        for status in STATUS_ORDER:
            group = [d for d in deltas if d.status == status]
            if not group:
                continue
            top = QTreeWidgetItem([f"{STATUS_TITLES[status]} ({len(group)})", "", ""])
            f = QFont()
            f.setBold(True)
            top.setFont(0, f)
            self.tree.addTopLevelItem(top)
            for d in group:
                name = chord_symbol(d.root_pc, d.chord_type, fret)
                ways = f"+{len(d.gained)} / −{len(d.lost)}"
                c_item = QTreeWidgetItem([f"{name}   ({d.chord_type})",
                                          nashville(self.modified, d.root_pc, d.chord_type, fret), ways])
                top.addChild(c_item)
                if show != 2:
                    for s in d.gained:
                        self._add_sighting(c_item, "+", s, gained=True)
                if show != 1:
                    for s in d.lost:
                        self._add_sighting(c_item, "−", s, gained=False)
            top.setExpanded(True)

        if self.guitar is not None:
            self.lbl_hint.setText("Double-click a way to hear it: green (+) ways play on the modified neck, red (−) ways "
                                  "on the baseline. The neck is made active first if needed. This window can stay open "
                                  "while you use the main window.")
        else:
            self.lbl_hint.setText("+ = new way to play the chord, − = way that no longer works. "
                                  "Apply the edits to try the new stances on the fretboard.")

    def _add_sighting(self, parent: QTreeWidgetItem, sign: str, s, gained: bool):
        item = QTreeWidgetItem([f"{sign} {format_sighting(s)}", "", ""])
        item.setForeground(0, QColor(_GAIN_COLOR if gained else _LOSS_COLOR))
        item.setData(0, Qt.UserRole, (s, gained))
        parent.addChild(item)

    # ------------------------------------------------------------------
    # Audition
    # ------------------------------------------------------------------
    def neck_index_for(self, gained: bool) -> Optional[int]:
        """Index of the neck a gained (modified) or lost (baseline) way belongs to; None in editor mode."""
        if self.guitar is None:
            return None
        combo = self.combo_mod if gained else self.combo_base
        return combo.currentData()

    def can_apply(self, gained: bool) -> bool:
        """True if the way's neck is already active (no neck switch needed)."""
        idx = self.neck_index_for(gained)
        return idx is not None and idx == self.active_neck_idx

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _col: int = 0):
        payload = item.data(0, Qt.UserRole)
        if not payload:
            return
        sighting, gained = payload
        idx = self.neck_index_for(gained)
        if idx is None:
            return
        if idx != self.active_neck_idx:
            self.activate_neck_requested.emit(idx)
            if idx != self.active_neck_idx:  # MainWindow did not switch
                return
        fret = self.spin_fret.value()
        self.stance_selected.emit(
            fret, set(sighting.controllers), set(sighting.strings),
            root_name(sighting.root_pc, fret), sighting.chord_type,
        )
