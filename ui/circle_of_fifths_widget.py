"""Interactive 3-ring Circle of Fifths wheel with movement mechanic filters,

colored diatonic buttons, and sub-button pathway cues.
"""

import math
from typing import Any, Dict, List, Optional, Set, Tuple
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.circle_of_fifths import (
    CIRCLE_KEYS_CLOCKWISE,
    RELATIVE_MINORS,
    CircleOfFifthsEngine,
)
from core.models import Neck
from core.theory import NOTE_TO_SEMITONE, to_root_name
from core.voicing_solver import VoicingSolver


def _pc(name: Optional[str]) -> Optional[int]:
    return NOTE_TO_SEMITONE.get(name) if name else None


def _same_chord(a: Optional[Tuple[str, str]], root: str, chord_type: str) -> bool:
    """Chord equality by pitch class, so 'Db' (wheel) and 'C#' (diatonic list) match."""
    return a is not None and a[1] == chord_type and _pc(a[0]) is not None and _pc(a[0]) == _pc(root)


class CircleWheelCanvas(QWidget):
    sector_clicked = Signal(str, str)  # root_name, chord_type

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(330, 330)
        self.key_center: str = "G"
        self.active_chord: Optional[Tuple[str, str]] = None
        self.setMouseTracking(True)

    def set_key_center(self, key: str):
        self.key_center = key
        self.update()

    def set_active_chord(self, root: str, chord_type: str):
        self.active_chord = (root, chord_type)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        center = QPointF(w / 2.0, h / 2.0)
        outer_radius = min(w, h) / 2.0 - 8.0

        r_major_inner = outer_radius * 0.74
        r_minor_inner = outer_radius * 0.50
        r_dom7_inner = outer_radius * 0.28
        core_radius = r_dom7_inner

        diatonics = CircleOfFifthsEngine.get_diatonic_chords(self.key_center)
        major_diatonics = {_pc(d.root_name) for d in diatonics if d.chord_type == "Major" and d.role != "I"}
        minor_diatonics = {_pc(d.root_name) for d in diatonics if d.chord_type == "Minor"}
        v_chord_pc = next((_pc(d.root_name) for d in diatonics if d.role == "V"), None)

        sector_angle = 360.0 / 12.0

        for i, key in enumerate(CIRCLE_KEYS_CLOCKWISE):
            rel_minor = RELATIVE_MINORS.get(key, "")
            start_angle = -90.0 + (i - 0.5) * sector_angle
            mid_angle_rad = math.radians(start_angle + sector_angle / 2.0)

            # 1. Outer Ring: Major
            major_path = self._create_sector_path(center, r_major_inner, outer_radius, start_angle, sector_angle)
            is_active_major = _same_chord(self.active_chord, key, "Major")

            if _pc(key) == _pc(self.key_center):
                brush_maj = QBrush(QColor(13, 110, 253))
                pen_maj = QPen(QColor(255, 255, 255), 3.0 if is_active_major else 2.0)
                text_col_maj = QColor(255, 255, 255)
            elif _pc(key) in major_diatonics:
                brush_maj = QBrush(QColor(40, 167, 69, 230))
                pen_maj = QPen(QColor(255, 255, 255) if is_active_major else QColor(45, 52, 60), 2.5 if is_active_major else 1.0)
                text_col_maj = QColor(255, 255, 255)
            else:
                brush_maj = QBrush(QColor(45, 48, 56))
                pen_maj = QPen(QColor(255, 255, 255) if is_active_major else QColor(60, 65, 75), 2.5 if is_active_major else 1.0)
                text_col_maj = QColor(190, 195, 205)

            painter.setBrush(brush_maj)
            painter.setPen(pen_maj)
            painter.drawPath(major_path)

            r_label_major = (r_major_inner + outer_radius) / 2.0
            lx1 = center.x() + r_label_major * math.cos(mid_angle_rad)
            ly1 = center.y() + r_label_major * math.sin(mid_angle_rad)
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            painter.setPen(text_col_maj)
            painter.drawText(QRectF(lx1 - 20, ly1 - 12, 40, 24), Qt.AlignCenter, key)

            # 2. Middle Ring: Relative Minor
            minor_path = self._create_sector_path(center, r_minor_inner, r_major_inner, start_angle, sector_angle)
            is_active_minor = _same_chord(self.active_chord, rel_minor, "Minor")

            if _pc(rel_minor) in minor_diatonics:
                brush_min = QBrush(QColor(255, 193, 7, 230))
                pen_min = QPen(QColor(255, 255, 255) if is_active_minor else QColor(45, 52, 60), 2.5 if is_active_minor else 1.0)
                text_col_min = QColor(20, 20, 20)
            else:
                brush_min = QBrush(QColor(36, 38, 44))
                pen_min = QPen(QColor(255, 255, 255) if is_active_minor else QColor(55, 60, 68), 2.5 if is_active_minor else 1.0)
                text_col_min = QColor(160, 165, 175)

            painter.setBrush(brush_min)
            painter.setPen(pen_min)
            painter.drawPath(minor_path)

            r_label_minor = (r_minor_inner + r_major_inner) / 2.0
            lx2 = center.x() + r_label_minor * math.cos(mid_angle_rad)
            ly2 = center.y() + r_label_minor * math.sin(mid_angle_rad)
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.setPen(text_col_min)
            painter.drawText(QRectF(lx2 - 20, ly2 - 10, 40, 20), Qt.AlignCenter, f"{rel_minor}m")

            # 3. Inner Ring: Dominant 7th
            dom7_path = self._create_sector_path(center, r_dom7_inner, r_minor_inner, start_angle, sector_angle)
            is_active_dom7 = _same_chord(self.active_chord, key, "Dominant 7th")

            if _pc(key) == v_chord_pc:
                brush_d7 = QBrush(QColor(220, 53, 69, 230))
                pen_d7 = QPen(QColor(255, 255, 255), 3.0 if is_active_dom7 else 1.5)
                text_col_d7 = QColor(255, 255, 255)
            else:
                brush_d7 = QBrush(QColor(28, 30, 36))
                pen_d7 = QPen(QColor(255, 255, 255) if is_active_dom7 else QColor(50, 54, 62), 2.5 if is_active_dom7 else 1.0)
                text_col_d7 = QColor(140, 145, 155)

            painter.setBrush(brush_d7)
            painter.setPen(pen_d7)
            painter.drawPath(dom7_path)

            r_label_dom7 = (r_dom7_inner + r_minor_inner) / 2.0
            lx3 = center.x() + r_label_dom7 * math.cos(mid_angle_rad)
            ly3 = center.y() + r_label_dom7 * math.sin(mid_angle_rad)
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.setPen(text_col_d7)
            painter.drawText(QRectF(lx3 - 20, ly3 - 10, 40, 20), Qt.AlignCenter, f"{key}7")

        # Center Hub
        painter.setBrush(QBrush(QColor(20, 22, 26)))
        painter.setPen(QPen(QColor(255, 255, 255, 140), 1.5))
        painter.drawEllipse(center, core_radius, core_radius)

        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.setPen(QColor(230, 235, 245))
        painter.drawText(
            QRectF(center.x() - 36, center.y() - 18, 72, 36),
            Qt.AlignCenter,
            f"Key Center\n[{self.key_center}]"
        )

    def _create_sector_path(self, center: QPointF, r_in: float, r_out: float, start_deg: float, span_deg: float) -> QPainterPath:
        path = QPainterPath()
        path.arcMoveTo(QRectF(center.x() - r_out, center.y() - r_out, r_out * 2, r_out * 2), -start_deg)
        path.arcTo(QRectF(center.x() - r_out, center.y() - r_out, r_out * 2, r_out * 2), -start_deg, -span_deg)
        path.arcTo(QRectF(center.x() - r_in, center.y() - r_in, r_in * 2, r_in * 2), -start_deg - span_deg, span_deg)
        path.closeSubpath()
        return path

    def mousePressEvent(self, event):
        pos = event.position()
        w = self.width()
        h = self.height()
        center = QPointF(w / 2.0, h / 2.0)
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        r = math.sqrt(dx * dx + dy * dy)

        outer_radius = min(w, h) / 2.0 - 8.0
        r_major_inner = outer_radius * 0.74
        r_minor_inner = outer_radius * 0.50
        r_dom7_inner = outer_radius * 0.28

        if r < r_dom7_inner or r > outer_radius:
            return

        angle_deg = math.degrees(math.atan2(dy, dx))
        normalized = (angle_deg + 90.0 + 15.0) % 360.0
        sector_idx = int(normalized / 30.0) % 12
        key = CIRCLE_KEYS_CLOCKWISE[sector_idx]

        if r >= r_major_inner:
            self.sector_clicked.emit(key, "Major")
        elif r >= r_minor_inner:
            rel_m = RELATIVE_MINORS.get(key, "A")
            self.sector_clicked.emit(rel_m, "Minor")
        else:
            self.sector_clicked.emit(key, "Dominant 7th")


class CircleOfFifthsWidget(QWidget):
    chord_triggered = Signal(str, str, bool, set)

    def __init__(self, neck: Neck, is_dark_mode: bool = True, parent=None):
        super().__init__(parent)
        self.neck = neck
        self._voicing_cache: dict = {}
        self.is_dark_mode = is_dark_mode
        self.current_key: str = "G"
        self.active_pocket: Set[int] = {8, 6, 4}
        self.current_bar_fret: int = 0
        self.current_levers: List[str] = []
        self.active_chord: Optional[Tuple[str, str]] = ("G", "Major")
        self.family_buttons_data: List[Dict[str, Any]] = []
        self.legend_pill_widgets: List[Tuple[QFrame, QLabel, str]] = []
        self.movement_buttons: Dict[str, QPushButton] = {}

        self._init_ui()
        self._refresh_family_buttons()
        self.set_dark_mode(self.is_dark_mode)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # 1. Top Controls Bar
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>Key Center:</b>"))
        self.combo_key = QComboBox()
        self.combo_key.addItems(CIRCLE_KEYS_CLOCKWISE)
        self.combo_key.setProperty("keepSpelling", True)  # traditional circle key names; skip global respell
        self.combo_key.setCurrentText("G")
        self.combo_key.currentIndexChanged.connect(self._on_key_combo_changed)
        top_bar.addWidget(self.combo_key)

        top_bar.addSpacing(15)
        self.cb_lock_pocket = QCheckBox("Lock to Current Grip / Pocket")
        self.cb_lock_pocket.setChecked(True)
        top_bar.addWidget(self.cb_lock_pocket)

        self.cb_auto_seq = QCheckBox("➕ Auto-Add to Sequencer")
        self.cb_auto_seq.setChecked(False)
        self.cb_auto_seq.setStyleSheet("color: #28a745; font-weight: bold;")
        top_bar.addWidget(self.cb_auto_seq)

        top_bar.addStretch()
        layout.addLayout(top_bar)

        # 2. Movement Mechanics Filter Ribbon
        filter_box = QGroupBox("Movement Mechanics Allowed (Physical Pathway Filter)")
        filter_h = QHBoxLayout(filter_box)
        filter_h.setContentsMargins(8, 4, 8, 4)
        filter_h.setSpacing(8)

        mechanics_def = [
            ("Same-Fret Pedal Drop", "🟢 Same-Fret (Δ0)"),
            ("Hold Pedals & Slide", "🔵 Hold Pedals & Slide (+2)"),
            ("Open Bar Shift", "🟡 Open Shifts"),
            ("Position Shift", "⚪ Position Shifts"),
        ]

        for m_key, m_label in mechanics_def:
            btn = QPushButton(m_label)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 11px;
                    font-weight: bold;
                    padding: 3px 10px;
                    min-height: 22px;
                }
                QPushButton:checked {
                    background-color: #0d6efd;
                    color: white;
                }
            """)
            btn.toggled.connect(self._on_mechanic_toggled)
            filter_h.addWidget(btn)
            self.movement_buttons[m_key] = btn

        filter_h.addStretch()
        layout.addWidget(filter_box)

        # 3. Main Content Split: Wheel on left, Family panel on right
        content_layout = QHBoxLayout()

        wheel_container = QWidget()
        wheel_vbox = QVBoxLayout(wheel_container)
        wheel_vbox.setContentsMargins(0, 0, 0, 0)
        wheel_vbox.setSpacing(8)

        self.canvas_wheel = CircleWheelCanvas(self)
        self.canvas_wheel.set_key_center(self.current_key)
        self.canvas_wheel.sector_clicked.connect(self._on_sector_clicked)
        wheel_vbox.addWidget(self.canvas_wheel, stretch=1)

        # High-Contrast Legend Container Strip
        self.legend_frame = QFrame()
        self.legend_layout = QHBoxLayout(self.legend_frame)
        self.legend_layout.setContentsMargins(6, 5, 6, 5)
        self.legend_layout.setSpacing(6)

        legend_defs = [
            ("Tonic (I)", "#0d6efd", "tonic"),
            ("Major (IV, V)", "#28a745", "major"),
            ("Minor (ii, iii, vi)", "#ffc107", "minor"),
            ("Dominant (V7)", "#dc3545", "dom7"),
            ("Non-Diatonic", "#6c757d", "nondiatonic"),
        ]

        for text, dot_color, role_key in legend_defs:
            pill = QFrame()
            pill_h = QHBoxLayout(pill)
            pill_h.setContentsMargins(6, 3, 6, 3)
            pill_h.setSpacing(5)

            dot = QLabel()
            dot.setFixedSize(11, 11)
            dot.setStyleSheet(f"background-color: {dot_color}; border-radius: 3px; border: 1px solid rgba(0,0,0,0.25);")

            lbl = QLabel(text)
            lbl.setFont(QFont("Segoe UI", 8, QFont.Bold))

            pill_h.addWidget(dot)
            pill_h.addWidget(lbl)
            self.legend_layout.addWidget(pill)

            self.legend_pill_widgets.append((pill, lbl, role_key))

        wheel_vbox.addWidget(self.legend_frame)
        content_layout.addWidget(wheel_container, stretch=1)

        # 4. Diatonic Family Panel with Sub-Button Pathway Labels
        family_container = QWidget()
        family_vbox = QVBoxLayout(family_container)
        family_vbox.setContentsMargins(0, 0, 0, 0)
        family_vbox.setSpacing(6)

        family_group = QGroupBox("Diatonic Chord Family && Cadences")
        self.family_layout = QGridLayout(family_group)
        self.family_layout.setContentsMargins(10, 10, 10, 10)
        self.family_layout.setHorizontalSpacing(10)
        self.family_layout.setVerticalSpacing(8)
        family_vbox.addWidget(family_group, stretch=1)

        # Physical Transition Cue Banner
        self.lbl_transition_cue = QLabel("Select any chord to inspect physical hand & pedal transitions.")
        self.lbl_transition_cue.setStyleSheet("font-size: 11px; font-weight: bold; color: #0d6efd; padding: 4px;")
        self.lbl_transition_cue.setAlignment(Qt.AlignCenter)
        family_vbox.addWidget(self.lbl_transition_cue)

        content_layout.addWidget(family_container, stretch=1)
        layout.addLayout(content_layout)

    def get_allowed_mechanics(self) -> Set[str]:
        return {k for k, btn in self.movement_buttons.items() if btn.isChecked()}

    def _on_mechanic_toggled(self):
        self.update_current_stance(self.current_bar_fret, set(self.current_levers), self.active_pocket)

    def set_dark_mode(self, is_dark: bool):
        self.is_dark_mode = is_dark

        if is_dark:
            self.legend_frame.setStyleSheet("""
                QFrame {
                    background-color: #21252d;
                    border: 1px solid #3c4049;
                    border-radius: 6px;
                }
            """)
            palette_map = {
                "tonic":       ("rgba(13, 110, 253, 0.22)", "#0d6efd", "#70b1ff"),
                "major":       ("rgba(40, 167, 69, 0.22)",  "#28a745", "#7de89a"),
                "minor":       ("rgba(255, 193, 7, 0.22)",  "#ffc107", "#ffde7a"),
                "dom7":        ("rgba(220, 53, 69, 0.22)",  "#dc3545", "#ff8a94"),
                "nondiatonic": ("#2a2e38",                   "#4a505e", "#c5cad4"),
            }
        else:
            self.legend_frame.setStyleSheet("""
                QFrame {
                    background-color: #ffffff;
                    border: 1px solid #ced4da;
                    border-radius: 6px;
                }
            """)
            palette_map = {
                "tonic":       ("#eef5ff", "#0d6efd", "#084298"),
                "major":       ("#ebf9f1", "#28a745", "#0f5132"),
                "minor":       ("#fffbeb", "#d39e00", "#664d03"),
                "dom7":        ("#fdf2f2", "#dc3545", "#842029"),
                "nondiatonic": ("#f1f3f5", "#adb5bd", "#495057"),
            }

        for pill, lbl, role_key in self.legend_pill_widgets:
            bg_col, border_col, text_col = palette_map[role_key]
            pill.setStyleSheet(f"""
                QFrame {{
                    background-color: {bg_col};
                    border: 1.5px solid {border_col};
                    border-radius: 4px;
                }}
            """)
            lbl.setStyleSheet(f"color: {text_col}; background: transparent; border: none; font-size: 10px; font-weight: bold;")

        self._refresh_family_buttons()

    def set_key_center(self, key: str):
        key = to_root_name(key, CIRCLE_KEYS_CLOCKWISE) or key  # any spelling -> the wheel's key name
        if key in CIRCLE_KEYS_CLOCKWISE:
            self.current_key = key
            self.combo_key.blockSignals(True)
            self.combo_key.setCurrentText(key)
            self.combo_key.blockSignals(False)
            self.canvas_wheel.set_key_center(key)
            self._refresh_family_buttons()

    def set_active_pocket(self, pocket: Set[int]):
        self.active_pocket = set(pocket)
        self.update_current_stance(self.current_bar_fret, set(self.current_levers), self.active_pocket)

    def update_neck(self, neck: Neck):
        self.neck = neck
        self._voicing_cache.clear()
        self._refresh_family_buttons()

    def update_current_stance(self, bar_fret: int, levers: Set[str], pocket: Set[int]):
        """Live updates pathway cues underneath each button without altering button dimensions."""
        self.current_bar_fret = bar_fret
        self.current_levers = sorted(list(levers))
        self.active_pocket = set(pocket)

        allowed = self.get_allowed_mechanics()
        pocket_list = sorted(list(pocket))

        for data in self.family_buttons_data:
            lbl_cue = data["cue_label"]
            root = data["root"]
            c_type = data["chord_type"]

            # Voicings depend on the neck and fret window only, not on the levers: cache them (D-31).
            cache_key = (id(self.neck), root, c_type, min(22, bar_fret + 9))
            matches = self._voicing_cache.get(cache_key)
            if matches is None:
                matches = VoicingSolver.find_all_voicings(
                    neck=self.neck,
                    root_name=root,
                    chord_type=c_type,
                    max_fret=min(22, bar_fret + 9),
                    filter_awkward=True,
                    omitted_intervals={"5"} if "7" in c_type else None,
                )
                self._voicing_cache[cache_key] = matches

            pocket_matches = [m for m in matches if m.grip_strings == pocket_list]
            pool = pocket_matches if (self.cb_lock_pocket.isChecked() and pocket_matches) else matches

            valid_pool = []
            for m in pool:
                mech = VoicingSolver.classify_movement(bar_fret, self.current_levers, m.fret, m.engaged_levers)
                if not allowed or mech in allowed:
                    valid_pool.append((m, mech))

            if valid_pool:
                valid_pool.sort(key=lambda item: (abs(item[0].fret - bar_fret), len(item[0].engaged_levers)))
                best_m, _ = valid_pool[0]
                delta = best_m.fret - bar_fret
                delta_str = f"+{delta}" if delta > 0 else f"{delta}" if delta < 0 else "Δ0"
                lev_abbr = "+".join(best_m.engaged_levers) if best_m.engaged_levers else "Open"
                lbl_cue.setText(f"F{best_m.fret} ({delta_str} | {lev_abbr})")
                lbl_cue.setStyleSheet("font-size: 9px; font-weight: bold; color: #0d6efd;" if self.is_dark_mode else "font-size: 9px; font-weight: bold; color: #0a58ca;")
            else:
                lbl_cue.setText("No Match")
                lbl_cue.setStyleSheet("font-size: 9px; color: #888888;")

    def _refresh_family_buttons(self):
        for data in self.family_buttons_data:
            wrapper = data["wrapper"]
            self.family_layout.removeWidget(wrapper)
            wrapper.deleteLater()
        self.family_buttons_data.clear()

        diatonics = CircleOfFifthsEngine.get_diatonic_chords(self.current_key)

        for idx, d in enumerate(diatonics):
            wrapper = QWidget()
            vbox = QVBoxLayout(wrapper)
            vbox.setContentsMargins(0, 0, 0, 0)
            vbox.setSpacing(3)

            # 1. Fixed-size button with clean 2-line text
            btn = QPushButton(f"{d.role}\n{d.root_name} {d.chord_type[:3]}")
            btn.setFixedHeight(50)
            btn.clicked.connect(lambda _, r=d.root_name, t=d.chord_type: self._trigger_chord(r, t))
            vbox.addWidget(btn)

            # 2. Independent pathway cue label directly below the button
            lbl_cue = QLabel("F0 (Δ0 | Open)")
            lbl_cue.setAlignment(Qt.AlignCenter)
            lbl_cue.setStyleSheet("font-size: 9px; font-weight: bold; color: #6c757d;")
            vbox.addWidget(lbl_cue)

            row = idx // 3
            col = idx % 3
            self.family_layout.addWidget(wrapper, row, col)

            self.family_buttons_data.append({
                "wrapper": wrapper,
                "button": btn,
                "cue_label": lbl_cue,
                "role": d.role,
                "root": d.root_name,
                "chord_type": d.chord_type,
            })

        # Explicit V7 Cadence Cell
        v_chord = next((d for d in diatonics if d.role == "V"), None)
        if v_chord:
            wrapper_v7 = QWidget()
            vbox_v7 = QVBoxLayout(wrapper_v7)
            vbox_v7.setContentsMargins(0, 0, 0, 0)
            vbox_v7.setSpacing(3)

            btn_v7 = QPushButton(f"V7 (Cadence)\n{v_chord.root_name}7")
            btn_v7.setFixedHeight(50)
            btn_v7.clicked.connect(lambda: self._trigger_chord(v_chord.root_name, "Dominant 7th"))
            vbox_v7.addWidget(btn_v7)

            lbl_v7_cue = QLabel("F0 (Δ0 | Open)")
            lbl_v7_cue.setAlignment(Qt.AlignCenter)
            lbl_v7_cue.setStyleSheet("font-size: 9px; font-weight: bold; color: #dc3545;")
            vbox_v7.addWidget(lbl_v7_cue)

            self.family_layout.addWidget(wrapper_v7, 2, 1)
            self.family_buttons_data.append({
                "wrapper": wrapper_v7,
                "button": btn_v7,
                "cue_label": lbl_v7_cue,
                "role": "V7",
                "root": v_chord.root_name,
                "chord_type": "Dominant 7th",
            })

        active_r = self.active_chord[0] if self.active_chord else self.current_key
        active_t = self.active_chord[1] if self.active_chord else "Major"
        self.highlight_chord(active_r, active_t)
        self.update_current_stance(self.current_bar_fret, set(self.current_levers), self.active_pocket)

    def highlight_chord(self, root: str, chord_type: str, transition_summary: str = ""):
        self.active_chord = (root, chord_type)
        self.canvas_wheel.set_active_chord(root, chord_type)

        if transition_summary:
            self.lbl_transition_cue.setText(f"Pathway to {root}{'7' if '7' in chord_type else chord_type[:3]}: {transition_summary}")

        for data in self.family_buttons_data:
            btn = data["button"]
            role = data["role"]
            is_match = _same_chord((data["root"], data["chord_type"]), root, chord_type)
            self._style_family_button(btn, role, is_active=is_match)

    def _style_family_button(self, btn: QPushButton, role: str, is_active: bool):
        if is_active:
            # Solid High-Contrast Selection
            if role == "I":
                style = "background-color: #0d6efd; color: #ffffff; border: 2.5px solid #0044b3;"
            elif role in ("IV", "V"):
                style = "background-color: #28a745; color: #ffffff; border: 2.5px solid #146c2e;"
            elif role in ("ii", "iii", "vi"):
                style = "background-color: #ffc107; color: #1a1a1a; border: 2.5px solid #b28704;"
            elif "V7" in role:
                style = "background-color: #dc3545; color: #ffffff; border: 2.5px solid #842029;"
            else:
                style = "background-color: #6c757d; color: #ffffff; border: 2px solid #343a40;"
        else:
            # Unselected with Colored Outlines
            base_bg = "#2b303c" if self.is_dark_mode else "#f8f9fa"
            text_c = "#e6edf3" if self.is_dark_mode else "#212529"
            if role == "I":
                style = f"background-color: {base_bg}; color: {text_c}; border: 2px solid #0d6efd;"
            elif role in ("IV", "V"):
                style = f"background-color: {base_bg}; color: {text_c}; border: 2px solid #28a745;"
            elif role in ("ii", "iii", "vi"):
                style = f"background-color: {base_bg}; color: {text_c}; border: 2px solid #d39e00;"
            elif "V7" in role:
                style = f"background-color: {base_bg}; color: {text_c}; border: 2px solid #dc3545;"
            else:
                style = f"background-color: {base_bg}; color: {text_c}; border: 1.5px solid #adb5bd;"

        btn.setStyleSheet(f"""
            QPushButton {{
                min-width: 84px;
                height: 50px;
                font-weight: bold;
                font-size: 11px;
                border-radius: 6px;
                {style}
            }}
        """)

    def _on_key_combo_changed(self):
        new_key = self.combo_key.currentText()
        self.set_key_center(new_key)

    def _on_sector_clicked(self, root: str, chord_type: str):
        self._trigger_chord(root, chord_type)

    def _trigger_chord(self, root: str, chord_type: str):
        allowed = self.get_allowed_mechanics()
        add_seq = self.cb_auto_seq.isChecked()
        self.chord_triggered.emit(root, chord_type, add_seq, allowed)