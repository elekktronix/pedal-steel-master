"""Compact lever and pedal toggle panel with Single-Click (Half-Stop) / Double-Click (Full-Stop)
3-state interaction, distinct amber/green color states, and inline articulations.
"""

from typing import Dict, List, Optional, Set
from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.models import Neck


class HalfStopLeverButton(QPushButton):
    """Button supporting 3-state mechanical engagement:
    - 0: Disengaged (Neutral Slate)
    - 1: Half-Stop (Amber Glow #d39e00) - Single Click
    - 2: Full-Stop (Emerald #20c997 or Blue #0d6efd) - Double Click
    """

    state_changed = Signal(str, int)  # (controller_id, state: 0, 1, or 2)

    def __init__(self, controller_id: str, label_text: str, is_pedal: bool = False, parent=None):
        super().__init__(label_text, parent)
        self.controller_id = controller_id
        self.is_pedal = is_pedal
        self.state: int = 0  # 0=off, 1=half, 2=full
        self.has_half_stop: bool = False  # Derived strictly from active profile half_stops

        self.setCheckable(False)
        self.setFixedHeight(34)
        self.setMinimumWidth(50)
        self._single_click_timer = QTimer(self)
        self._single_click_timer.setSingleShot(True)
        self._single_click_timer.timeout.connect(self._handle_single_click_timeout)

        self._update_appearance()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._single_click_timer.isActive():
                self._single_click_timer.stop()
                new_state = 0 if self.state == 2 else 2
                self._set_state(new_state)
            else:
                self._single_click_timer.start(240)
        super().mousePressEvent(event)

    def _handle_single_click_timeout(self):
        if self.has_half_stop:
            new_state = 0 if self.state != 0 else 1
        else:
            new_state = 0 if self.state != 0 else 2
        self._set_state(new_state)

    def _set_state(self, new_state: int):
        self.state = new_state
        self._update_appearance()
        self.state_changed.emit(self.controller_id, self.state)

    def set_engagement_state(self, state: int):
        self.state = state
        self._update_appearance()

    def _update_appearance(self):
        if self.state == 1:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #d39e00;
                    color: #12151c;
                    font-weight: bold;
                    font-size: 11px;
                    border: 2px solid #fff3cd;
                    border-radius: 4px;
                    padding: 3px 6px;
                }
                QPushButton:hover {
                    background-color: #e0a800;
                }
            """)
        elif self.state == 2:
            accent = "#0d6efd" if self.is_pedal else "#20c997"
            fg = "#ffffff" if self.is_pedal else "#000000"
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {accent};
                    color: {fg};
                    font-weight: bold;
                    font-size: 11px;
                    border: 2px solid #ffffff;
                    border-radius: 4px;
                    padding: 3px 6px;
                }}
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #2b303c;
                    color: #e0e6ed;
                    font-weight: bold;
                    font-size: 11px;
                    border: 1px solid #495057;
                    border-radius: 4px;
                    padding: 3px 6px;
                }
                QPushButton:hover {
                    background-color: #3b4252;
                    border-color: #6c757d;
                }
            """)


class LeverTogglePanel(QWidget):
    levers_changed = Signal(set)
    pinch_requested = Signal()
    roll_requested = Signal()
    arpeggiate_requested = Signal()
    all_strings_requested = Signal()
    clear_pocket_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pedal_buttons: Dict[str, HalfStopLeverButton] = {}
        self.lever_buttons: Dict[str, HalfStopLeverButton] = {}
        self.active_controllers: Set[str] = set()
        self.neck: Optional[Neck] = None

        self._init_ui()

    def _init_ui(self):
        root_vbox = QVBoxLayout(self)
        root_vbox.setContentsMargins(0, 0, 0, 0)
        root_vbox.setSpacing(4)

        # Stance Feasibility Banner without dedicated edit buttons
        feasibility_row = QHBoxLayout()
        feasibility_row.setSpacing(8)

        self.lbl_feasibility_title = QLabel("<b>Mechanical Feasibility:</b>")
        self.lbl_feasibility_title.setStyleSheet("font-size: 11px; color: #adb5bd;")
        feasibility_row.addWidget(self.lbl_feasibility_title)

        self.lbl_feasibility_badge = QLabel("✅ Stance Feasible (Open Fretboard)")
        self.lbl_feasibility_badge.setStyleSheet("""
            background-color: #163820;
            color: #75b798;
            border: 1px solid #28a745;
            font-weight: bold;
            border-radius: 4px;
            padding: 2px 10px;
            font-size: 11px;
        """)
        feasibility_row.addWidget(self.lbl_feasibility_badge)

        lbl_hint = QLabel("<small style='color: #8b92a0;'>[1-Click: Half-Stop (Amber) | 2-Click: Full-Stop (Green/Blue)]</small>")
        feasibility_row.addWidget(lbl_hint)

        feasibility_row.addStretch()
        root_vbox.addLayout(feasibility_row)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(6)

        # Foot Pedals Box
        self.pedal_box = QGroupBox("Foot Pedals")
        self.pedal_box.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11px; }")
        self.pedal_layout = QHBoxLayout(self.pedal_box)
        self.pedal_layout.setContentsMargins(8, 4, 8, 6)
        self.pedal_layout.setSpacing(6)
        controls_row.addWidget(self.pedal_box, stretch=2)

        # Knee Levers Box
        self.lever_box = QGroupBox("Knee Levers")
        self.lever_box.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11px; }")
        self.lever_layout = QHBoxLayout(self.lever_box)
        self.lever_layout.setContentsMargins(8, 4, 8, 6)
        self.lever_layout.setSpacing(6)
        controls_row.addWidget(self.lever_box, stretch=3)

        # Pluck Articulation Box
        self.action_box = QGroupBox("Pluck & Articulation")
        self.action_box.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11px; }")
        act_layout = QHBoxLayout(self.action_box)
        act_layout.setContentsMargins(8, 4, 8, 6)
        act_layout.setSpacing(6)

        self.btn_pinch = QPushButton("🤏 Pinch")
        self.btn_pinch.setFixedHeight(34)
        self.btn_pinch.setStyleSheet("""
            QPushButton {
                background-color: #0d6efd;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #0b5ed7; }
        """)
        self.btn_pinch.clicked.connect(self.pinch_requested.emit)
        act_layout.addWidget(self.btn_pinch)

        self.btn_roll = QPushButton("🎶 Roll")
        self.btn_roll.setFixedHeight(34)
        self.btn_roll.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #138496; }
        """)
        self.btn_roll.clicked.connect(self.roll_requested.emit)
        act_layout.addWidget(self.btn_roll)

        self.btn_arp = QPushButton("⚡ Arpeggiate")
        self.btn_arp.setFixedHeight(34)
        self.btn_arp.setStyleSheet("""
            QPushButton {
                background-color: #6f42c1;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #59359a; }
        """)
        self.btn_arp.clicked.connect(self.arpeggiate_requested.emit)
        act_layout.addWidget(self.btn_arp)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #495057;")
        act_layout.addWidget(sep)

        self.btn_all = QPushButton("All")
        self.btn_all.setFixedHeight(34)
        self.btn_all.setStyleSheet("font-weight: bold; font-size: 11px; padding: 4px 10px;")
        self.btn_all.clicked.connect(self.all_strings_requested.emit)
        act_layout.addWidget(self.btn_all)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setFixedHeight(34)
        self.btn_clear.setStyleSheet("font-weight: bold; font-size: 11px; padding: 4px 10px;")
        self.btn_clear.clicked.connect(self.clear_pocket_requested.emit)
        act_layout.addWidget(self.btn_clear)

        controls_row.addWidget(self.action_box, stretch=2)
        root_vbox.addLayout(controls_row)

    def set_neck(self, neck: Neck):
        self.neck = neck
        while self.pedal_layout.count() > 0:
            item = self.pedal_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.pedal_buttons.clear()

        while self.lever_layout.count() > 0:
            item = self.lever_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.lever_buttons.clear()
        self.active_controllers.clear()

        # Derive enabled half-stops strictly from neck.half_stops
        enabled_half_stops = {
            rule.controller_id
            for rule in getattr(neck, "half_stops", [])
            if rule.is_active
        }

        # Foot Pedals
        pedal_keys = sorted(list(neck.pedals.keys()), key=lambda k: int(k[1:]) if k[1:].isdigit() else 99)
        for p_id in pedal_keys:
            p_obj = neck.pedals[p_id]
            btn_label = p_obj.label if "Franklin" in p_obj.label else p_id
            btn = HalfStopLeverButton(p_id, btn_label, is_pedal=True, parent=self)
            btn.has_half_stop = (p_id in enabled_half_stops)
            btn.set_engagement_state(0)
            btn.state_changed.connect(self._on_controller_state_changed)
            self.pedal_layout.addWidget(btn)
            self.pedal_buttons[p_id] = btn
        self.pedal_layout.addStretch()

        # Knee Levers
        from ui.copedant_editor_dialog import STANDARDIZED_KNEE_LEVERS
        physical_order = [lid for lid, _, _ in STANDARDIZED_KNEE_LEVERS]
        lever_keys = sorted(
            list(neck.knee_levers.keys()),
            key=lambda k: physical_order.index(k) if k in physical_order else 99,
        )

        for l_id in lever_keys:
            btn = HalfStopLeverButton(l_id, l_id, is_pedal=False, parent=self)
            btn.has_half_stop = (l_id in enabled_half_stops)
            btn.set_engagement_state(0)
            btn.state_changed.connect(self._on_controller_state_changed)
            self.lever_layout.addWidget(btn)
            self.lever_buttons[l_id] = btn
        self.lever_layout.addStretch()

        self._update_feasibility()

    def _on_controller_state_changed(self, controller_id: str, state: int):
        self.active_controllers.discard(controller_id)
        self.active_controllers.discard(f"{controller_id}_HALF")

        if state == 1:
            self.active_controllers.add(f"{controller_id}_HALF")
        elif state == 2:
            self.active_controllers.add(controller_id)

        self._update_feasibility()
        self.levers_changed.emit(set(self.active_controllers))

    def set_active_controllers(self, controllers: Set[str]) -> Set[str]:
        """Sets button states, the panel's own state and the feasibility badge WITHOUT emitting
        levers_changed (D-03). Accepts "<ID>_HALF" tokens. Returns the tokens actually applied
        (controllers that do not exist on this neck are dropped)."""
        buttons = {**self.pedal_buttons, **self.lever_buttons}
        applied: Set[str] = set()
        for token in controllers:
            base = token.replace("_HALF", "")
            if base in buttons:
                applied.add(f"{base}_HALF" if token.endswith("_HALF") else base)
        for cid, btn in buttons.items():
            state = 2 if cid in applied else (1 if f"{cid}_HALF" in applied else 0)
            btn.set_engagement_state(state)
        self.active_controllers = applied
        self._update_feasibility()
        return set(applied)

    def _update_feasibility(self):
        from core.ergonomics import ErgonomicsEngine, StanceDifficulty

        base_ctrls = {c.replace("_HALF", "") for c in self.active_controllers}
        has_half = any("_HALF" in c for c in self.active_controllers)

        stance = ErgonomicsEngine.evaluate_stance(base_ctrls)
        half_tag = " (Half-Stop)" if has_half else ""
        if not stance.is_possible:
            desc = "; ".join(stance.clash_reasons) or "Conflicting controllers engaged"  # D-25
            self.lbl_feasibility_badge.setText(f"❌ Stance Impossible: {desc}")
            self.lbl_feasibility_badge.setStyleSheet("""
                background-color: #4c1d24;
                color: #ea868f;
                border: 1px solid #dc3545;
                font-weight: bold;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 11px;
            """)
        elif getattr(stance, "difficulty", None) == StanceDifficulty.AWKWARD:
            desc = getattr(stance, "description", "") or "Challenging reach"
            self.lbl_feasibility_badge.setText(f"⚠️ Stance Awkward{half_tag}: {desc}")
            self.lbl_feasibility_badge.setStyleSheet("""
                background-color: #4d3e12;
                color: #ffda6a;
                border: 1px solid #ffc107;
                font-weight: bold;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 11px;
            """)
        else:
            count = len(self.active_controllers)
            tag = "Open Fretboard" if count == 0 else f"{count} Engaged{half_tag}"
            self.lbl_feasibility_badge.setText(f"✅ Stance Feasible ({tag})")
            self.lbl_feasibility_badge.setStyleSheet("""
                background-color: #163820;
                color: #75b798;
                border: 1px solid #28a745;
                font-weight: bold;
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 11px;
            """)

    def reset_all(self):
        for btn in self.pedal_buttons.values():
            btn.set_engagement_state(0)
        for btn in self.lever_buttons.values():
            btn.set_engagement_state(0)
        self.active_controllers.clear()
        self._update_feasibility()
        self.levers_changed.emit(set())