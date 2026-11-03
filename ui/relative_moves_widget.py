"""Widget displaying the interactive Same Fret Hub with selection highlighting,
clean filtering, and Warnock/Barndo Relative Move Assistant.
"""

from typing import List, Optional, Set
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.models import Neck
from core.relative_moves import RelativeMoveOption, RelativeMovesEngine


class RelativeMovesWidget(QWidget):
    move_applied = Signal(int, set, set, str, str)  # (fret, ctrls, strings, chord_name, chord_type)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_fret: int = 0
        self.active_levers: Set[str] = set()
        self.is_c6: bool = False
        self.neck: Optional[Neck] = None
        self.filter_mode: str = "i_iv_v"
        self.active_pill_label: Optional[str] = None  # Tracks the active clicked pill

        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # ---------------- 1. Same-Fret Hub Ribbon ----------------
        self.hub_frame = QFrame()
        self.hub_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1d24;
                border: 1px solid #343a40;
                border-radius: 4px;
            }
        """)
        hub_layout = QHBoxLayout(self.hub_frame)
        hub_layout.setContentsMargins(8, 3, 8, 3)
        hub_layout.setSpacing(8)

        self.lbl_hub_title = QLabel("<b>Same Fret Hub:</b>")
        self.lbl_hub_title.setStyleSheet("color: #20c997; font-size: 11px;")
        hub_layout.addWidget(self.lbl_hub_title)

        self.combo_filter = QComboBox()
        self.combo_filter.setToolTip("Select which same-fret chord relationships to display")
        self.combo_filter.addItem("I - IV - V (Primary)", "i_iv_v")
        self.combo_filter.addItem("Diatonic (I - vi)", "diatonic")
        self.combo_filter.addItem("Franklin 7 (Classic)", "franklin")
        self.combo_filter.addItem("Dominants & Blues", "dominants")
        self.combo_filter.addItem("All Available", "all")
        self.combo_filter.setCurrentIndex(0)
        self.combo_filter.setStyleSheet("""
            QComboBox {
                background-color: #0f3d30;
                color: #20c997;
                border: 1px solid #20c997;
                font-size: 10px;
                font-weight: bold;
                padding: 1px 6px;
                border-radius: 3px;
                min-width: 130px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1e222a;
                color: #e0e6ed;
                selection-background-color: #20c997;
                selection-color: #000000;
            }
        """)
        self.combo_filter.currentIndexChanged.connect(self._on_filter_changed)
        hub_layout.addWidget(self.combo_filter)

        hub_scroll = QScrollArea()
        hub_scroll.setFixedHeight(32)
        hub_scroll.setWidgetResizable(True)
        hub_scroll.setFrameShape(QFrame.NoFrame)
        hub_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        hub_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hub_scroll.setStyleSheet("""
            QScrollBar:horizontal { height: 4px; background: rgba(0,0,0,0.1); border-radius: 2px; }
            QScrollBar::handle:horizontal { background: rgba(32, 201, 151, 0.4); border-radius: 2px; }
        """)

        self.hub_pills_container = QWidget()
        self.hub_pills_layout = QHBoxLayout(self.hub_pills_container)
        self.hub_pills_layout.setContentsMargins(0, 0, 0, 0)
        self.hub_pills_layout.setSpacing(6)
        hub_scroll.setWidget(self.hub_pills_container)
        hub_layout.addWidget(hub_scroll, stretch=1)

        root.addWidget(self.hub_frame)

        # ---------------- 2. Relative Move Assistant Ribbon ----------------
        self.moves_frame = QFrame()
        self.moves_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1d24;
                border: 1px solid #343a40;
                border-radius: 4px;
            }
        """)
        moves_layout = QHBoxLayout(self.moves_frame)
        moves_layout.setContentsMargins(8, 3, 8, 3)
        moves_layout.setSpacing(8)

        self.lbl_moves_title = QLabel("<b>Relative Move Assistant:</b>")
        self.lbl_moves_title.setStyleSheet("color: #0dcaf0; font-size: 11px;")
        moves_layout.addWidget(self.lbl_moves_title)

        moves_scroll = QScrollArea()
        moves_scroll.setFixedHeight(32)
        moves_scroll.setWidgetResizable(True)
        moves_scroll.setFrameShape(QFrame.NoFrame)
        moves_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        moves_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        moves_scroll.setStyleSheet("""
            QScrollBar:horizontal { height: 4px; background: rgba(0,0,0,0.1); border-radius: 2px; }
            QScrollBar::handle:horizontal { background: rgba(13, 202, 240, 0.4); border-radius: 2px; }
        """)

        self.moves_pills_container = QWidget()
        self.moves_pills_layout = QHBoxLayout(self.moves_pills_container)
        self.moves_pills_layout.setContentsMargins(0, 0, 0, 0)
        self.moves_pills_layout.setSpacing(6)
        moves_scroll.setWidget(self.moves_pills_container)
        moves_layout.addWidget(moves_scroll, stretch=1)

        root.addWidget(self.moves_frame)

    def _on_filter_changed(self):
        self.filter_mode = self.combo_filter.currentData()
        self._refresh_hub_ribbon()

    def update_state(
        self,
        fret: int,
        active_levers: Set[str],
        is_c6: bool = False,
        neck: Optional[Neck] = None,
    ):
        self.current_fret = fret
        self.active_levers = set(active_levers)
        self.is_c6 = is_c6
        if neck is not None:
            self.neck = neck

        self._refresh_hub_ribbon()
        self._refresh_moves_ribbon()

    def _refresh_hub_ribbon(self):
        while self.hub_pills_layout.count() > 0:
            item = self.hub_pills_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self.neck:
            options = RelativeMovesEngine.get_all_same_fret_chords(
                self.neck, self.current_fret, filter_mode=self.filter_mode
            )
        else:
            options = RelativeMovesEngine.get_same_fret_diatonic_hub(self.current_fret)

        for opt in options:
            btn = QPushButton(opt.label)
            btn.setToolTip(f"{opt.description}\nPedals: {', '.join(sorted(opt.controllers)) or 'Open'}")

            is_active = (opt.label == self.active_pill_label)
            is_dom = "7" in opt.label and "maj" not in opt.label.lower()

            if is_active:
                btn_style = """
                    QPushButton {
                        background-color: #ffc107;
                        color: #000000;
                        font-weight: bold;
                        font-size: 11px;
                        border: 2px solid #ffffff;
                        border-radius: 4px;
                        padding: 2px 9px;
                    }
                """
            elif is_dom:
                btn_style = """
                    QPushButton {
                        background-color: #4d3800;
                        color: #ffda6a;
                        font-weight: bold;
                        font-size: 10px;
                        border: 1px solid #ffc107;
                        border-radius: 3px;
                        padding: 2px 8px;
                    }
                    QPushButton:hover {
                        background-color: #ffc107;
                        color: #000000;
                    }
                """
            else:
                btn_style = """
                    QPushButton {
                        background-color: #12382c;
                        color: #75b798;
                        font-weight: bold;
                        font-size: 10px;
                        border: 1px solid #20c997;
                        border-radius: 3px;
                        padding: 2px 8px;
                    }
                    QPushButton:hover {
                        background-color: #20c997;
                        color: #000000;
                    }
                """
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(lambda _, o=opt: self._emit_hub_move(o))
            self.hub_pills_layout.addWidget(btn)

        self.hub_pills_layout.addStretch()

    def _refresh_moves_ribbon(self):
        while self.moves_pills_layout.count() > 0:
            item = self.moves_pills_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self.is_c6:
            moves = RelativeMovesEngine.get_c6_relative_movements(self.current_fret)
        else:
            moves = RelativeMovesEngine.get_e9_relative_movements(self.current_fret, self.active_levers)

        for m in moves:
            btn = QPushButton(f"{m.label} ➔ {m.chord_name}")
            btn.setToolTip(m.description)
            is_active = (f"{m.label} ➔ {m.chord_name}" == self.active_pill_label)

            if is_active:
                btn_style = """
                    QPushButton {
                        background-color: #0dcaf0;
                        color: #000000;
                        font-weight: bold;
                        font-size: 11px;
                        border: 2px solid #ffffff;
                        border-radius: 4px;
                        padding: 2px 8px;
                    }
                """
            else:
                btn_style = """
                    QPushButton {
                        background-color: #0c3547;
                        color: #6edff6;
                        font-weight: bold;
                        font-size: 10px;
                        border: 1px solid #0dcaf0;
                        border-radius: 3px;
                        padding: 2px 7px;
                    }
                    QPushButton:hover {
                        background-color: #0dcaf0;
                        color: #000000;
                    }
                """
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(lambda _, o=m: self._emit_relative_move(o))
            self.moves_pills_layout.addWidget(btn)

        self.moves_pills_layout.addStretch()

    def _emit_hub_move(self, opt: RelativeMoveOption):
        self.active_pill_label = opt.label
        self._refresh_hub_ribbon()
        # Parse root and quality for synchronized canvas interval analysis
        from core.relative_moves import _safe_extract_root_and_quality
        root, quality = _safe_extract_root_and_quality(opt.chord_name)
        chord_type = "Dominant 7th" if "7" in quality else ("Minor" if "m" in quality else "Major")
        self.move_applied.emit(opt.target_fret, set(opt.controllers), set(opt.target_strings), root, chord_type)

    def _emit_relative_move(self, opt: RelativeMoveOption):
        self.active_pill_label = f"{opt.label} ➔ {opt.chord_name}"
        self._refresh_moves_ribbon()
        from core.relative_moves import _safe_extract_root_and_quality
        root, quality = _safe_extract_root_and_quality(opt.chord_name)
        chord_type = "Dominant 7th" if "7" in quality else ("Minor" if "m" in quality else "Major")
        self.move_applied.emit(opt.target_fret, set(opt.controllers), set(opt.target_strings), root, chord_type)