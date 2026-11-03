"""Custom QWidget rendering a 24-fret pedal steel neck with light/dark theme adaptation,
interactive node plucking, split halos, and interval vs. note name display toggle.
"""

from typing import Dict, List, Optional, Set, Tuple, Union
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from core.chord_identifier import ChordIdentifier
from core.models import Neck
from core.resolver import ActiveStringState, FretboardResolver


class FretboardCanvas(QWidget):
    fret_changed = Signal(int)
    pocket_changed = Signal(set)
    node_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(340)
        self.setMinimumWidth(900)
        self.setMouseTracking(True)

        self.neck: Optional[Neck] = None
        self.bar_fret: int = 0
        self.engaged_levers: Set[str] = set()
        self.target_root: Optional[str] = None
        self.target_chord: Optional[str] = None
        self.target_scale: Optional[str] = None
        self.active_pocket: Set[int] = {8, 6, 5}
        self.detected_chord_label: Optional[str] = None
        self.is_dark_mode: bool = True
        self.show_inversions: bool = True
        self.show_nashville: bool = True
        self.box_highlight_range: Optional[Tuple[int, int]] = None
        self.display_mode: str = "intervals"  # "intervals" or "notes"

        self.active_states: List[ActiveStringState] = []
        self.num_frets = 24

        self.single_dot_frets = {3, 5, 7, 9, 15, 17, 19, 21}
        self.double_dot_frets = {12, 24}

        self.color_root = QColor(220, 53, 69)
        self.color_third = QColor(40, 167, 69)
        self.color_fifth = QColor(0, 123, 255)
        self.color_seventh = QColor(255, 193, 7)
        self.color_other = QColor(108, 117, 125)
        self.color_bar = QColor(255, 235, 59, 120)
        self.color_split = QColor(111, 66, 193)

        self.left_margin = 90.0
        self.right_margin = 40.0
        self.top_margin = 48.0
        self.bottom_margin = 32.0

    def set_display_mode(self, mode: str):
        """Toggle between 'intervals' (R, 3, 5) and 'notes' (E, G#, B)."""
        self.display_mode = mode
        self.update()

    def set_dark_mode(self, is_dark: bool):
        self.is_dark_mode = is_dark
        self.update()

    def set_show_inversions(self, show: bool):
        self.show_inversions = show
        self.update_state()

    def set_show_nashville(self, show: bool):
        self.show_nashville = show
        self.update_state()

    def set_neck(self, neck: Neck):
        self.neck = neck
        self.update_state()

    def set_scale_analysis(self, root: Optional[str], scale_name: Optional[str]):
        self.target_root = root
        self.target_scale = scale_name
        self.target_chord = None
        self.update_state()

    def set_chord_analysis(self, root: Optional[str], chord_type: Optional[str]):
        self.target_root = root
        self.target_chord = chord_type
        self.target_scale = None
        self.update_state()

    def set_bar_fret(self, fret: int):
        if self.bar_fret != fret:
            self.bar_fret = max(0, min(self.num_frets, fret))
            self.update_state()
            self.fret_changed.emit(self.bar_fret)

    def set_engaged_levers(self, levers: Set[str]):
        self.engaged_levers = levers
        self.update_state()

    def set_active_pocket(self, pocket: Set[int]):
        self.active_pocket = set(pocket)
        self.update_state()
        self.pocket_changed.emit(self.active_pocket)

    def set_box_highlight(self, min_fret_or_info: Union[int, Dict, Tuple], max_fret: Optional[int] = None):
        if isinstance(min_fret_or_info, dict):
            b_min = min_fret_or_info.get("min_fret", min_fret_or_info.get("start_fret", 0))
            b_max = min_fret_or_info.get("max_fret", min_fret_or_info.get("end_fret", 0))
            self.box_highlight_range = (b_min, b_max)
        elif isinstance(min_fret_or_info, (tuple, list)):
            self.box_highlight_range = (min_fret_or_info[0], min_fret_or_info[1])
        elif max_fret is not None:
            self.box_highlight_range = (int(min_fret_or_info), int(max_fret))
        self.update()

    def clear_box_highlight(self):
        self.box_highlight_range = None
        self.update()

    def set_explicit_banner(self, banner_text: Optional[str]):
        self.detected_chord_label = banner_text
        self.update()

    def update_state(self):
        if not self.neck:
            self.active_states = []
            self.detected_chord_label = None
        else:
            self.active_states = FretboardResolver.resolve_neck_state(
                neck=self.neck,
                fret=self.bar_fret,
                engaged_levers=self.engaged_levers,
                target_root_name=self.target_root,
                target_chord_type=self.target_chord,
                target_scale_name=self.target_scale,
            )

            pocket_states = [s for s in self.active_states if s.string_number in self.active_pocket]
            if pocket_states:
                pocket_pitches = [s.active_midi for s in pocket_states]
                bass_state = max(pocket_states, key=lambda s: s.string_number)
                match = ChordIdentifier.identify_voicing(
                    pitches=pocket_pitches,
                    bass_pitch=bass_state.active_midi,
                    show_inversion=self.show_inversions,
                    grip_strings=self.active_pocket,
                )
                if match:
                    raw_tag, chord_family = match
                    display_tag = raw_tag
                    # Prepend Nashville Number if enabled and key is set
                    if self.show_nashville and self.target_root and self.target_root != "None":
                        from core.theory import get_nashville_chord_symbol
                        nns_symbol = get_nashville_chord_symbol(raw_tag, self.target_root)
                        if nns_symbol:
                            display_tag = f"[{nns_symbol}]  {raw_tag}"
                    self.detected_chord_label = display_tag
                else:
                    self.detected_chord_label = None
            else:
                self.detected_chord_label = None

        self.update()

    def _get_fret_x(self, fret: int, fret_width: float) -> float:
        return self.left_margin + fret * fret_width

    def mousePressEvent(self, event):
        x = event.position().x()
        y = event.position().y()

        num_strings = self.neck.string_count if self.neck else 10
        board_w = max(100.0, self.width() - self.left_margin - self.right_margin)
        board_h = max(100.0, self.height() - self.top_margin - self.bottom_margin)
        fret_w = board_w / self.num_frets
        spacing = board_h / (num_strings - 1 if num_strings > 1 else 1)

        # 1. Check if user clicked directly on an active pitch circle node at the tone bar
        bar_x = self._get_fret_x(self.bar_fret, fret_w)
        node_radius = 14.0
        for state in self.active_states:
            idx = state.string_number - 1
            sy = self.top_margin + idx * spacing
            dx = x - bar_x
            dy = y - sy
            if (dx * dx + dy * dy) <= (node_radius * node_radius):
                self.node_clicked.emit(state.active_midi)
                return

        # 2. Check if clicked on string number badges on the left
        if x <= self.left_margin:
            idx = int(round((y - self.top_margin) / spacing))
            if 0 <= idx < num_strings:
                sy = self.top_margin + idx * spacing
                if abs(y - sy) <= (spacing * 0.55):
                    str_num = idx + 1
                    if str_num in self.active_pocket:
                        self.active_pocket.remove(str_num)
                    else:
                        self.active_pocket.add(str_num)
                    self.update_state()
                    self.pocket_changed.emit(set(self.active_pocket))
                    return

        # 3. Else, reposition tone bar
        self._handle_fret_click(x)

    def mouseMoveEvent(self, event):
        x = event.position().x()
        y = event.position().y()

        num_strings = self.neck.string_count if self.neck else 10
        board_w = max(100.0, self.width() - self.left_margin - self.right_margin)
        board_h = max(100.0, self.height() - self.top_margin - self.bottom_margin)
        fret_w = board_w / self.num_frets
        spacing = board_h / (num_strings - 1 if num_strings > 1 else 1)
        bar_x = self._get_fret_x(self.bar_fret, fret_w)

        # Show pointer if hovering over a node or string badge
        is_over_node = False
        for state in self.active_states:
            idx = state.string_number - 1
            sy = self.top_margin + idx * spacing
            if (x - bar_x) ** 2 + (y - sy) ** 2 <= 14.0 ** 2:
                is_over_node = True
                break

        if is_over_node or (x <= self.left_margin and self.top_margin - 15 <= y <= self.height() - self.bottom_margin + 15):
            self.setCursor(QCursor(Qt.PointingHandCursor))
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))

        if event.buttons() & Qt.LeftButton and not is_over_node:
            if x > self.left_margin - 10:
                self._handle_fret_click(x)

    def _handle_fret_click(self, x: float):
        board_width = max(100.0, self.width() - self.left_margin - self.right_margin)
        fret_width = board_width / self.num_frets
        clicked_fret = int(round((x - self.left_margin) / fret_width))
        clicked_fret = max(0, min(self.num_frets, clicked_fret))
        self.set_bar_fret(clicked_fret)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        num_strings = self.neck.string_count if self.neck else 10
        board_w = max(100.0, w - self.left_margin - self.right_margin)
        board_h = max(100.0, h - self.top_margin - self.bottom_margin)
        fret_w = board_w / self.num_frets
        string_spacing = board_h / (num_strings - 1 if num_strings > 1 else 1)

        if self.is_dark_mode:
            bg_color = QColor(35, 35, 38)
            fret_color = QColor(180, 180, 190)
            nut_color = QColor(235, 235, 240)
            dot_color = QColor(130, 130, 140, 160)
            fret_text_color = QColor(170, 170, 175)
            header_text_color = QColor(150, 155, 165)
            badge_bg_inactive = QColor(48, 52, 60)
            badge_border_inactive = QColor(90, 95, 105)
            badge_text_inactive = QColor(190, 195, 205)
            str_color_active = QColor(255, 255, 255)
            str_color_inactive = QColor(140, 145, 155, 110)
        else:
            bg_color = QColor(238, 235, 226)
            fret_color = QColor(110, 115, 125)
            nut_color = QColor(30, 32, 38)
            dot_color = QColor(145, 140, 130, 190)
            fret_text_color = QColor(70, 75, 85)
            header_text_color = QColor(80, 85, 95)
            badge_bg_inactive = QColor(220, 224, 232)
            badge_border_inactive = QColor(165, 170, 180)
            badge_text_inactive = QColor(40, 45, 55)
            str_color_active = QColor(30, 32, 38)
            str_color_inactive = QColor(145, 150, 160, 150)

        # 1. Fretboard Background
        board_rect = QRectF(self.left_margin, self.top_margin, board_w, board_h)
        painter.fillRect(board_rect, bg_color)

        if self.box_highlight_range:
            b_min, b_max = self.box_highlight_range
            bx_start = self._get_fret_x(b_min, fret_w) - (fret_w * 0.45 if b_min > 0 else 0)
            bx_end = self._get_fret_x(b_max, fret_w) + (fret_w * 0.45)
            box_rect = QRectF(bx_start, self.top_margin - 4, max(20.0, bx_end - bx_start), board_h + 8)

            box_fill = QColor(13, 110, 253, 35) if self.is_dark_mode else QColor(13, 110, 253, 25)
            painter.fillRect(box_rect, box_fill)
            painter.setPen(QPen(QColor(13, 110, 253, 180), 1.5, Qt.DashLine))
            painter.drawRoundedRect(box_rect, 6, 6)

        # 2. Tone Bar Highlight
        bar_x = self._get_fret_x(self.bar_fret, fret_w)
        bar_width = max(10.0, fret_w * 0.45)
        bar_rect = QRectF(bar_x - bar_width / 2.0, self.top_margin - 8, bar_width, board_h + 16)
        painter.fillRect(bar_rect, self.color_bar)
        painter.setPen(QPen(QColor(220, 180, 0), 2))
        painter.drawRoundedRect(bar_rect, 4, 4)

        if self.detected_chord_label:
            badge_font = QFont("Segoe UI", 9, QFont.Bold)
            painter.setFont(badge_font)

            metrics = painter.fontMetrics()
            text_w = metrics.horizontalAdvance(self.detected_chord_label) + 16
            text_h = 22.0

            badge_x = bar_x - (text_w / 2.0)
            badge_x = max(48.0, min(badge_x, self.width() - text_w - 10.0))
            badge_y = self.top_margin - 34.0
            badge_rect = QRectF(badge_x, badge_y, text_w, text_h)

            painter.setBrush(QBrush(QColor(13, 110, 253)))
            painter.setPen(QPen(QColor(255, 255, 255), 1.5))
            painter.drawRoundedRect(badge_rect, 4, 4)

            painter.setPen(QColor(255, 255, 255))
            painter.drawText(badge_rect, Qt.AlignCenter, self.detected_chord_label)

        # 3. Inlay Markers
        painter.setBrush(QBrush(dot_color))
        painter.setPen(Qt.NoPen)
        for f in range(1, self.num_frets + 1):
            center_x = self.left_margin + (f - 0.5) * fret_w
            center_y = self.top_margin + board_h / 2.0
            if f in self.single_dot_frets:
                painter.drawEllipse(QPointF(center_x, center_y), 5, 5)
            elif f in self.double_dot_frets:
                painter.drawEllipse(QPointF(center_x, center_y - 25), 5, 5)
                painter.drawEllipse(QPointF(center_x, center_y + 25), 5, 5)

        # 4. Frets
        fret_pen = QPen(fret_color, 1.5)
        nut_pen = QPen(nut_color, 5.0)
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))

        for f in range(self.num_frets + 1):
            fx = self._get_fret_x(f, fret_w)
            painter.setPen(nut_pen if f == 0 else fret_pen)
            painter.drawLine(QPointF(fx, self.top_margin), QPointF(fx, self.top_margin + board_h))

            painter.setPen(fret_text_color)
            painter.drawText(
                QRectF(fx - 15, self.top_margin + board_h + 6, 30, 20),
                Qt.AlignCenter,
                str(f),
            )

        # 5. STR Header
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.setPen(header_text_color)
        painter.drawText(QRectF(10, self.top_margin - 30, 40, 16), Qt.AlignCenter, "STR")

        string_num_font = QFont("Segoe UI", 9, QFont.Bold)
        state_by_string = {s.string_number: s for s in self.active_states}

        for idx in range(num_strings):
            str_num = idx + 1
            is_in_pocket = str_num in self.active_pocket
            str_state = state_by_string.get(str_num)
            is_split_on_str = getattr(str_state, "is_split_applied", False) if str_state else False

            sy = self.top_margin + idx * string_spacing
            str_weight = 1.0 + (idx / float(num_strings)) * 2.5

            if is_in_pocket:
                painter.setPen(QPen(str_color_active, str_weight + 0.8))
            else:
                painter.setPen(QPen(str_color_inactive, str_weight))

            painter.drawLine(QPointF(self.left_margin, sy), QPointF(self.left_margin + board_w, sy))

            badge_rect = QRectF(16, sy - 10, 28, 20)
            if is_split_on_str:
                painter.setBrush(QBrush(QColor(111, 66, 193, 220) if is_in_pocket else badge_bg_inactive))
                painter.setPen(QPen(self.color_split, 2.0))
            elif is_in_pocket:
                painter.setBrush(QBrush(QColor(40, 167, 69)))
                painter.setPen(QPen(QColor(255, 255, 255), 1.5))
            else:
                painter.setBrush(QBrush(badge_bg_inactive))
                painter.setPen(QPen(badge_border_inactive, 1))

            painter.drawRoundedRect(badge_rect, 4, 4)
            painter.setFont(string_num_font)
            painter.setPen(QColor(255, 255, 255) if is_in_pocket or is_split_on_str else badge_text_inactive)
            painter.drawText(badge_rect, Qt.AlignCenter, str(str_num))

        # 6. Active Pitch Nodes (Circles)
        if self.active_states:
            for state in self.active_states:
                idx = state.string_number - 1
                str_num = state.string_number
                is_in_pocket = str_num in self.active_pocket
                is_split = getattr(state, "is_split_applied", False)
                sy = self.top_margin + idx * string_spacing

                fill = self.color_other
                if state.is_chord_tone:
                    lbl = state.interval_label or ""
                    if lbl in ("R", "1"):
                        fill = self.color_root
                    elif "3" in lbl:
                        fill = self.color_third
                    elif "5" in lbl:
                        fill = self.color_fifth
                    elif "7" in lbl:
                        fill = self.color_seventh
                    elif lbl in ("2", "9"):
                        fill = QColor(23, 162, 184)
                    elif lbl in ("4", "11"):
                        fill = QColor(111, 66, 193)
                    elif lbl in ("6", "13"):
                        fill = QColor(253, 126, 20)

                if not is_in_pocket:
                    fill = QColor(fill.red(), fill.green(), fill.blue(), 50)

                node_radius = 12.0
                node_rect = QRectF(bar_x - node_radius, sy - node_radius, node_radius * 2, node_radius * 2)

                painter.setBrush(QBrush(fill))
                if is_in_pocket:
                    painter.setPen(QPen(QColor(255, 255, 255), 2.0))
                else:
                    border_c = QColor(120, 120, 120, 70) if self.is_dark_mode else QColor(180, 180, 180, 90)
                    painter.setPen(QPen(border_c, 1.0))

                painter.drawEllipse(node_rect)

                if is_split:
                    split_ring_pen = QPen(self.color_split, 2.5)
                    painter.setPen(split_ring_pen)
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(
                        bar_x - node_radius - 3.5,
                        sy - node_radius - 3.5,
                        (node_radius + 3.5) * 2,
                        (node_radius + 3.5) * 2,
                    )

                # Text Toggle: Chord Interval (R, 3, 5) vs. Plucked Pitch (E, G#, B)
                if self.display_mode == "notes":
                    node_text = state.active_note_name[:-1]
                else:
                    node_text = state.interval_label if state.interval_label else state.active_note_name[:-1]

                painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                painter.setPen(QColor(255, 255, 255) if is_in_pocket else QColor(180, 180, 180, 80))
                painter.drawText(node_rect, Qt.AlignCenter, node_text)