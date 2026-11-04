"""Shared chord / controller filter controls for Compare Copedants (E-25) and the Chord Atlas (E-27).

Row 1: chord types (sticky checkable menu with presets), no-5th shells, max pedals/levers at once,
       plus any extra widgets the host adds (`add_widget`).
Row 2: pedal/lever toggles plus a match mode (exactly these / including these / only these and
       open); none selected = every stance counts.
Emits `changed` whenever a filter changes. `keep()` returns the sighting predicate
(core.copedant_compare.sighting_filter) for the current state.
"""

from typing import Dict, Iterable, List, Optional, Set

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.copedant_compare import (
    CHORD_GROUPS,
    CONTROLLER_MATCH_EXACT,
    CONTROLLER_MATCH_INCLUDE,
    CONTROLLER_MATCH_ONLY,
    INVERSION_NAMES,
    sighting_filter,
)
from core.theory import CHORD_FORMULAS

DEFAULT_CHORD_TYPES = CHORD_GROUPS["Triads"] + CHORD_GROUPS["6ths & 7ths"]
_KNEE_ORDER = ["LKL", "LKL2", "LKV", "LKR", "CKL", "CKV", "CKR", "RKL", "RKR"]


def controller_order(cid: str):
    if cid.startswith("P") and cid[1:].isdigit():
        return (0, int(cid[1:]), cid)
    return (1, _KNEE_ORDER.index(cid) if cid in _KNEE_ORDER else 99, cid)


class StickyMenu(QMenu):
    """A menu that stays open when a checkable action is clicked."""

    def mouseReleaseEvent(self, event):
        action = self.activeAction()
        if action is not None and action.isEnabled() and action.isCheckable():
            action.trigger()
            return
        super().mouseReleaseEvent(event)


class ChordFilterBar(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.type_actions: Dict[str, QAction] = {}
        self.inversion_actions: Dict[int, QAction] = {}
        self.controller_buttons: Dict[str, QPushButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self.row1 = QHBoxLayout()
        self.btn_types = QToolButton()
        self.btn_types.setPopupMode(QToolButton.InstantPopup)
        self.menu_types = StickyMenu(self.btn_types)
        self._build_type_menu()
        self.btn_types.setMenu(self.menu_types)
        self.row1.addWidget(self.btn_types)

        # Inversion: which chord tone sounds lowest (resolved pitch), e.g. E9 8-6-5 open = root position.
        self.btn_inversions = QToolButton()
        self.btn_inversions.setPopupMode(QToolButton.InstantPopup)
        self.btn_inversions.setToolTip("Which chord tone is the lowest note of the grip:\n"
                                       "root position (R), 1st inversion (3rd), 2nd inversion (5th),\n"
                                       "3rd inversion (7th or 6th), or an extension (9/11/13).")
        self.menu_inversions = StickyMenu(self.btn_inversions)
        all_inv = self.menu_inversions.addAction("All inversions")
        all_inv.triggered.connect(lambda: self.set_inversions(INVERSION_NAMES))
        self.menu_inversions.addSeparator()
        for idx, name in INVERSION_NAMES.items():
            act = QAction(name, self.menu_inversions, checkable=True)
            act.setChecked(True)
            act.toggled.connect(self._on_inversions_changed)
            self.menu_inversions.addAction(act)
            self.inversion_actions[idx] = act
        self.btn_inversions.setMenu(self.menu_inversions)
        self._update_inversions_button()
        self.row1.addWidget(self.btn_inversions)

        self.chk_shells = QCheckBox("Include no-5th shells")
        self.chk_shells.setToolTip("Also count 7th/9th chords voiced without their 5th (e.g. R-3-b7).")
        self.chk_shells.toggled.connect(self._emit)
        self.row1.addWidget(self.chk_shells)

        self.row1.addSpacing(12)
        self.row1.addWidget(QLabel("Max pedals/levers at once:"))
        self.spin_max_ctrl = QSpinBox()
        self.spin_max_ctrl.setRange(0, 4)
        self.spin_max_ctrl.setSpecialValueText("Any")
        self.spin_max_ctrl.valueChanged.connect(self._emit)
        self.row1.addWidget(self.spin_max_ctrl)
        self._extra_at = self.row1.count()
        self.row1.addStretch()
        root.addLayout(self.row1)

        row2 = QHBoxLayout()
        row2.setSpacing(4)
        lbl = QLabel("<b>Pedals/levers:</b>")
        lbl.setToolTip("Select pedals/levers to filter the ways by the controllers they use.\n"
                       "With none selected, every stance counts.")
        row2.addWidget(lbl)
        self.combo_ctrl_match = QComboBox()
        self.combo_ctrl_match.addItem("Exactly these", CONTROLLER_MATCH_EXACT)
        self.combo_ctrl_match.addItem("Including these", CONTROLLER_MATCH_INCLUDE)
        self.combo_ctrl_match.addItem("Only these (and open)", CONTROLLER_MATCH_ONLY)
        self.combo_ctrl_match.setToolTip(
            "With P1 + P2 selected:\n"
            "Exactly these: only ways played with P1 + P2.\n"
            "Including these: P1 + P2 plus anything else (e.g. P1 + P2 + LKL).\n"
            "Only these (and open): open bar, P1, P2 or P1 + P2 (drill down to a set of controllers).")
        self.combo_ctrl_match.currentIndexChanged.connect(self._emit)
        row2.addWidget(self.combo_ctrl_match)
        self.ctrl_container = QHBoxLayout()
        self.ctrl_container.setSpacing(4)
        row2.addLayout(self.ctrl_container)
        self.btn_ctrl_clear = QPushButton("All stances")
        self.btn_ctrl_clear.clicked.connect(lambda: self.set_controller_filter(set()))
        row2.addWidget(self.btn_ctrl_clear)
        row2.addStretch()
        root.addLayout(row2)

    # ------------------------------------------------------------------
    def add_widget(self, widget: QWidget, spacing: int = 12):
        """Adds a host widget to row 1 (before the stretch)."""
        if spacing:
            self.row1.insertSpacing(self._extra_at, spacing)
            self._extra_at += 1
        self.row1.insertWidget(self._extra_at, widget)
        self._extra_at += 1

    def _emit(self, *_):
        self.changed.emit()

    def _build_type_menu(self):
        m = self.menu_types
        presets = [
            ("All chord types", tuple(CHORD_FORMULAS)),
            ("Triads only", CHORD_GROUPS["Triads"]),
            ("Triads + 6ths & 7ths", DEFAULT_CHORD_TYPES),
            ("Extensions only", CHORD_GROUPS["Extensions"]),
        ]
        for label, types in presets:
            act = m.addAction(label)
            act.triggered.connect(lambda _=False, t=types: self.set_chord_types(t))
        for group, types in CHORD_GROUPS.items():
            m.addSection(group)
            for ctype in types:
                act = QAction(ctype, m, checkable=True)
                act.setChecked(ctype in DEFAULT_CHORD_TYPES)
                act.toggled.connect(self._on_types_changed)
                m.addAction(act)
                self.type_actions[ctype] = act
        self._update_types_button()

    def _on_inversions_changed(self, *_):
        self._update_inversions_button()
        self.changed.emit()

    def _update_inversions_button(self):
        sel = self.selected_inversions()
        if sel is None:
            text = "All"
        elif len(sel) == 1:
            text = INVERSION_NAMES[next(iter(sel))]
        else:
            text = f"{len(sel)}/{len(self.inversion_actions)}"
        self.btn_inversions.setText(f"Inversions ({text}) ▾")

    def selected_inversions(self) -> Optional[Set[int]]:
        """Checked inversion indexes, or None when all are checked (no filtering)."""
        sel = {i for i, a in self.inversion_actions.items() if a.isChecked()}
        return None if len(sel) == len(self.inversion_actions) else sel

    def set_inversions(self, indexes):
        wanted = set(indexes)
        for i, a in self.inversion_actions.items():
            a.blockSignals(True)
            a.setChecked(i in wanted)
            a.blockSignals(False)
        self._on_inversions_changed()

    def _on_types_changed(self, *_):
        self._update_types_button()
        self.changed.emit()

    def _update_types_button(self):
        self.btn_types.setText(f"Chord types ({len(self.selected_chord_types())}/{len(self.type_actions)}) ▾")

    # ------------------------------------------------------------------
    def set_controllers(self, ids: Iterable[str], highlight: Optional[Set[str]] = None):
        """(Re)builds the controller toggles, keeping the current selection where possible."""
        previous = self.selected_controllers()
        while self.ctrl_container.count():
            w = self.ctrl_container.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.controller_buttons = {}
        highlight = highlight or set()
        for cid in sorted(set(ids), key=controller_order):
            btn = QPushButton(cid)
            btn.setCheckable(True)
            btn.setChecked(cid in previous)
            btn.setMinimumWidth(44)
            if cid in highlight:
                f = btn.font()
                f.setBold(True)
                btn.setFont(f)
                btn.setToolTip(f"{cid} is changed in this comparison")
            btn.toggled.connect(self._emit)
            self.ctrl_container.addWidget(btn)
            self.controller_buttons[cid] = btn

    def selected_chord_types(self) -> List[str]:
        return [t for t, a in self.type_actions.items() if a.isChecked()]

    def set_chord_types(self, types):
        wanted = set(types)
        for t, a in self.type_actions.items():
            a.blockSignals(True)
            a.setChecked(t in wanted)
            a.blockSignals(False)
        self._on_types_changed()

    def selected_controllers(self) -> Set[str]:
        return {c for c, b in self.controller_buttons.items() if b.isChecked()}

    def set_controller_filter(self, controllers):
        wanted = set(controllers)
        for c, b in self.controller_buttons.items():
            b.blockSignals(True)
            b.setChecked(c in wanted)
            b.blockSignals(False)
        self.changed.emit()

    def controller_match(self) -> str:
        return self.combo_ctrl_match.currentData()

    def set_controller_match(self, mode: str):
        row = self.combo_ctrl_match.findData(mode)
        if row >= 0:
            self.combo_ctrl_match.setCurrentIndex(row)

    def max_controllers(self) -> Optional[int]:
        return self.spin_max_ctrl.value() or None

    def keep(self, grips=None):
        """Sighting predicate for the current filters (plus an optional grip set)."""
        return sighting_filter(
            allowed_controllers=self.selected_controllers() or None,
            include_shells=self.chk_shells.isChecked(),
            max_controllers=self.max_controllers(),
            grips=grips,
            inversions=self.selected_inversions(),
            controller_match=self.controller_match(),
        )

    def only_using_text(self) -> str:
        sel = self.selected_controllers()
        if not sel:
            return ""
        names = " + ".join(sorted(sel, key=controller_order))
        mode = self.controller_match()
        if mode == CONTROLLER_MATCH_EXACT:
            return f"played with exactly {names}"
        if mode == CONTROLLER_MATCH_INCLUDE:
            return f"using {names} (plus any others)"
        return f"only using {names} (and open)"
