"""Custom QWidget rendering a 24-fret pedal steel neck with light/dark theme adaptation,
interactive node plucking, split halos, and interval vs. note name display toggle.
"""

from typing import Dict, List, Optional, Set, Tuple, Union
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from core.chord_identifier import ChordIdentifier
from core.models import Neck
from core.resolver import ActiveStringState, FretboardResolver
from core.stances import controller_display_names, describe_controllers


def degree_color(lbl: str) -> QColor:
    """Node colour for a chord interval or scale degree label ("R", "1", "b3", "#4", "13", ...)."""
    if lbl in ("R", "1"):
        return QColor(220, 53, 69)
    if lbl in ("2", "9", "b9", "#9"):  # extensions first: "13" must not match "3"
        return QColor(23, 162, 184)
    if lbl in ("4", "11", "#11", "#4"):
        return QColor(111, 66, 193)
    if lbl in ("6", "13", "b13", "b6"):
        return QColor(253, 126, 20)
    if "3" in lbl:
        return QColor(40, 167, 69)
    if "5" in lbl:
        return QColor(0, 123, 255)
    if "7" in lbl:
        return QColor(255, 193, 7)
    return QColor(108, 117, 125)


class FretboardCanvas(QWidget):
    fret_changed = Signal(int)
    pocket_changed = Signal(set)
    node_clicked = Signal(int, int)  # (midi_pitch, string_number)
    overlay_step_clicked = Signal(int)  # index into the scale overlay's run (E-30)
    quiz_note_clicked = Signal(object)  # BoxNote clicked while the scale quiz is running (E-30)

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

        # Scale map overlay (E-30): scale tones drawn at their own frets, independent of the bar.
        # Entries are (note, step_index or None); note is a core.scale_engine.BoxNote.
        self.scale_overlay: List[Tuple[object, Optional[int]]] = []
        self.overlay_label_mode: str = "step"  # "step", "degree" or "note"
        self.overlay_active_step: int = -1
        self.overlay_run: list = []  # the run in play order; a note can appear twice (up & back)
        self.overlay_names: Dict[str, str] = {}  # controller ID -> display name for tooltips
        self.overlay_loop_ids: Optional[Set[int]] = None  # ids of the looped notes; None = no loop
        self.scale_ghost: list = []  # faint scale tones outside the range ("whole neck")
        self.overlay_quiz: bool = False  # circles drawn blank until revealed
        self.overlay_revealed: Set[int] = set()
        self.overlay_wrong: Optional[int] = None
        self.overlay_chord_pcs: Set[int] = set()  # chord tones ringed on the scale map (E-31)

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

    def set_scale_overlay(self, notes: list, run: list):
        """Shows every scale tone in `notes` at its own fret; notes in `run` are numbered by step."""
        step_of: Dict[int, int] = {}
        for i, n in enumerate(run):
            step_of.setdefault(id(n), i)  # a note visited twice is labelled with its first step
        self.scale_overlay = [(n, step_of.get(id(n))) for n in notes]
        self.overlay_run = list(run)
        self.overlay_active_step = -1
        if self.neck:
            self.overlay_names = controller_display_names(self.neck)
        self.update()

    def clear_scale_overlay(self):
        self.scale_overlay = []
        self.overlay_run = []
        self.overlay_active_step = -1
        self.overlay_loop_ids = None
        self.scale_ghost = []
        self.overlay_quiz = False
        self.overlay_revealed = set()
        self.overlay_wrong = None
        self.overlay_chord_pcs = set()
        self.update()

    def set_overlay_chord(self, pcs: list):
        """Rings the scale notes whose pitch class is a chord tone and dims the rest (empty = none)."""
        self.overlay_chord_pcs = {int(pc) % 12 for pc in pcs}
        self.update()

    def set_overlay_loop(self, lo: int, hi: int):
        """Fades run steps outside lo..hi (run indices); lo < 0 clears the loop."""
        if lo < 0 or not self.overlay_run:
            self.overlay_loop_ids = None
        else:
            self.overlay_loop_ids = {id(n) for n in self.overlay_run[lo:hi + 1]}
        self.update()

    def set_scale_ghost(self, notes: list):
        self.scale_ghost = list(notes)
        self.update()

    def set_overlay_quiz(self, on: bool):
        self.overlay_quiz = bool(on)
        self.overlay_revealed = set()
        self.overlay_wrong = None
        self.update()

    def reveal_overlay_notes(self, notes: list):
        self.overlay_revealed = {id(n) for n in notes}
        self.overlay_wrong = None
        self.update()

    def mark_overlay_wrong(self, note):
        self.overlay_wrong = id(note) if note is not None else None
        self.update()

    def set_overlay_label_mode(self, mode: str):
        if mode in ("step", "degree", "note"):
            self.overlay_label_mode = mode
            self.update()

    def set_overlay_active_step(self, idx: int):
        self.overlay_active_step = idx
        self.update()

    def _overlay_geometry(self, fret_w: float, spacing: float):
        """Yields (x, y, radius, note, step); notes sharing a string and fret sit side by side."""
        cells: Dict[Tuple[int, int], list] = {}
        for note, step in self.scale_overlay:
            cells.setdefault((note.string_number, note.fret), []).append((note, step))
        base_r = max(6.0, min(10.0, fret_w * 0.32, spacing * 0.42))
        for (s_num, fret), items in cells.items():
            items.sort(key=lambda it: it[0].midi_note)
            n = len(items)
            r = base_r if n == 1 else max(5.0, min(base_r, fret_w * 0.95 / (2 * n)))
            cx = self._get_fret_x(fret, fret_w)
            cy = self.top_margin + (s_num - 1) * spacing
            for i, (note, step) in enumerate(items):
                x = cx + (i - (n - 1) / 2.0) * (2 * r + 1.5)
                yield x, cy, r, note, step

    def _ghost_geometry(self, fret_w: float, spacing: float):
        """Yields (x, y, radius, note) for the faint whole-neck notes."""
        cells: Dict[Tuple[int, int], list] = {}
        for note in self.scale_ghost:
            cells.setdefault((note.string_number, note.fret), []).append(note)
        base_r = max(4.0, min(7.0, fret_w * 0.22, spacing * 0.3))
        for (s_num, fret), items in cells.items():
            items.sort(key=lambda n: n.midi_note)
            n = len(items)
            r = base_r if n == 1 else max(3.5, min(base_r, fret_w * 0.95 / (2 * n)))
            cx = self._get_fret_x(fret, fret_w)
            cy = self.top_margin + (s_num - 1) * spacing
            for i, note in enumerate(items):
                yield cx + (i - (n - 1) / 2.0) * (2 * r + 1.0), cy, r, note

    def _overlay_hit(self, x: float, y: float):
        """(note, step, is_ghost) under the point, or None. Ghosts are ignored during a quiz."""
        num_strings = self.neck.string_count if self.neck else 10
        board_w = max(100.0, self.width() - self.left_margin - self.right_margin)
        board_h = max(100.0, self.height() - self.top_margin - self.bottom_margin)
        fret_w = board_w / self.num_frets
        spacing = board_h / (num_strings - 1 if num_strings > 1 else 1)
        for nx, ny, r, note, step in self._overlay_geometry(fret_w, spacing):
            if (x - nx) ** 2 + (y - ny) ** 2 <= (r + 1.5) ** 2:
                return note, step, False
        if not self.overlay_quiz:
            for nx, ny, r, note in self._ghost_geometry(fret_w, spacing):
                if (x - nx) ** 2 + (y - ny) ** 2 <= (r + 1.5) ** 2:
                    return note, None, True
        return None

    def _interval_fill(self, lbl: str) -> QColor:
        return degree_color(lbl)

    def _draw_scale_overlay(self, painter: QPainter, fret_w: float, spacing: float):
        if self.scale_ghost and not self.overlay_quiz:
            painter.setFont(QFont("Segoe UI", 6))
            chord = self.overlay_chord_pcs
            for x, y, r, note in self._ghost_geometry(fret_w, spacing):
                c = degree_color(note.degree_label)
                a = 70 if not chord else (130 if note.midi_note % 12 in chord else 30)
                painter.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), a)))
                painter.setPen(QPen(QColor(c.red(), c.green(), c.blue(), min(255, a + 50)), 1.0))
                painter.drawEllipse(QPointF(x, y), r, r)
                if r >= 5.5:
                    painter.setPen(QColor(255, 255, 255, 150) if self.is_dark_mode else QColor(30, 32, 38, 160))
                    painter.drawText(QRectF(x - r, y - r, 2 * r, 2 * r), Qt.AlignCenter, note.degree_label)

        run = self.overlay_run
        active_note = run[self.overlay_active_step] if 0 <= self.overlay_active_step < len(run) else None
        played_ids = {id(n) for n in run[:max(0, self.overlay_active_step)]}
        loop_ids = self.overlay_loop_ids
        pedal_dot = QColor(255, 140, 0)
        for x, y, r, note, step in self._overlay_geometry(fret_w, spacing):
            if self.overlay_quiz and id(note) not in self.overlay_revealed:
                # Quiz: every circle looks the same until it is answered.
                wrong = id(note) == self.overlay_wrong
                painter.setBrush(QBrush(QColor(120, 125, 135) if self.is_dark_mode else QColor(160, 165, 175)))
                painter.setPen(QPen(QColor(220, 53, 69) if wrong else QColor(255, 255, 255, 180), 3.0 if wrong else 1.2))
                painter.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
                if wrong:
                    painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                    painter.setPen(QColor(255, 255, 255))
                    painter.drawText(QRectF(x - r, y - r, 2 * r, 2 * r), Qt.AlignCenter, "✗")
                continue
            fill = QColor(self._interval_fill(note.degree_label))
            in_run = step is not None
            is_active = note is active_note
            played = in_run and not is_active and id(note) in played_ids
            if in_run and loop_ids is not None and id(note) not in loop_ids:
                played = True  # outside the loop: drawn faded like a played step
            chord_tone = bool(self.overlay_chord_pcs) and note.midi_note % 12 in self.overlay_chord_pcs
            if self.overlay_chord_pcs and not chord_tone and not is_active:
                fill.setAlpha(70)  # a chord is selected: non-chord scale notes step back

            rr = r * 1.35 if is_active else r
            rect = QRectF(x - rr, y - rr, rr * 2, rr * 2)
            if not in_run:
                # Not a step: the same pitch at another spot, or outside a root-to-root run.
                painter.setBrush(QBrush(QColor(fill.red(), fill.green(), fill.blue(), 45)))
                painter.setPen(QPen(fill, 1.5, Qt.DashLine))
            else:
                if played:
                    fill.setAlpha(110)
                painter.setBrush(QBrush(fill))
                pen_c = QColor(255, 255, 255) if self.is_dark_mode or is_active else QColor(30, 32, 38, 160)
                painter.setPen(QPen(pen_c, 3.0 if is_active else 1.2))
            painter.drawEllipse(rect)
            if chord_tone:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(255, 215, 0), 2.5))
                painter.drawEllipse(QPointF(x, y), rr + 3.0, rr + 3.0)

            if note.engaged_levers:  # orange dot = needs a pedal or lever
                d = max(2.5, r * 0.32)
                painter.setBrush(QBrush(pedal_dot))
                painter.setPen(QPen(QColor(20, 20, 20), 0.8))
                painter.drawEllipse(QPointF(x + rr * 0.72, y - rr * 0.72), d, d)

            if self.overlay_label_mode == "step" and in_run:
                text = str(step + 1)
            elif self.overlay_label_mode == "note":
                text = note.note_name.rstrip("-0123456789")
            else:
                text = note.degree_label
            size = 7 if (len(text) > 1 and rr < 9) else 8
            painter.setFont(QFont("Segoe UI", size + (1 if is_active else 0), QFont.Bold))
            if in_run:
                painter.setPen(QColor(255, 255, 255, 150 if played else 255))
            else:
                painter.setPen(fill.lighter(140) if self.is_dark_mode else fill)
            painter.drawText(rect, Qt.AlignCenter, text)

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
                        nns_symbol = get_nashville_chord_symbol(raw_tag, self.target_root, family=chord_family)
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

        # 0. Scale map overlay circles (E-30): run notes select their step, others just sound
        if self.scale_overlay:
            hit = self._overlay_hit(x, y)
            if hit:
                note, step, is_ghost = hit
                if self.overlay_quiz:
                    self.quiz_note_clicked.emit(note)
                elif step is not None:
                    self.overlay_step_clicked.emit(step)
                else:
                    self.node_clicked.emit(note.midi_note, note.string_number)
                return

        # 1. Check if user clicked directly on an active pitch circle node at the tone bar
        bar_x = self._get_fret_x(self.bar_fret, fret_w)
        node_radius = 14.0
        for state in ([] if self.scale_overlay else self.active_states):
            idx = state.string_number - 1
            sy = self.top_margin + idx * spacing
            dx = x - bar_x
            dy = y - sy
            if (dx * dx + dy * dy) <= (node_radius * node_radius):
                self.node_clicked.emit(state.active_midi, state.string_number)
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
        if self.scale_overlay:
            hit = self._overlay_hit(x, y)
            if hit and self.overlay_quiz:
                is_over_node = True
                QToolTip.hideText()
            elif hit:
                is_over_node = True
                note, step, is_ghost = hit
                ctrls = describe_controllers(note.engaged_levers, self.overlay_names)
                if is_ghost:
                    head = "Outside the fret range"
                elif step is not None:
                    head = f"Step {step + 1}"
                else:
                    head = "Not a step (another spot for this pitch, or outside the run)"
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"{head}\nDegree {note.degree_label}: {note.note_name}\n"
                    f"String {note.string_number}, fret {note.fret}\n{ctrls}",
                    self,
                )
            else:
                QToolTip.hideText()
        for state in ([] if self.scale_overlay else self.active_states):
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

        # 6a. The scale map overlay replaces the bar nodes while it is shown (E-30)
        if self.scale_overlay:
            self._draw_scale_overlay(painter, fret_w, string_spacing)

        # 6. Active Pitch Nodes (Circles)
        elif self.active_states:
            for state in self.active_states:
                idx = state.string_number - 1
                str_num = state.string_number
                is_in_pocket = str_num in self.active_pocket
                is_split = getattr(state, "is_split_applied", False)
                sy = self.top_margin + idx * string_spacing

                fill = self.color_other
                if state.is_chord_tone:
                    fill = self._interval_fill(state.interval_label or "")

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