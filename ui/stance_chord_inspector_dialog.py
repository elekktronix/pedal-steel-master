"""Current Stance Chord Inspector: Evaluates all sounding chords, inversions,
dyads, and active mechanical splits for the currently active bar fret, pedals, and knee levers.
"""

from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.chord_identifier import ChordIdentifier
from core.grip_presets import (
    C6_GRIP_CARDS,
    E9_GRIP_CARDS,
    FRANKLIN_E9_GROUPS,
    NEWMAN_DYAD_POCKETS,
    U12_GRIP_CARDS,
)
from core.models import Neck, NeckType
from core.resolver import ActiveStringState, FretboardResolver
from core.theory import NOTE_NAMES_SHARP, NOTE_TO_SEMITONE


class StanceChordInspectorDialog(QDialog):
    grip_applied = Signal(set)  # Emits Set[int] of string numbers to arm on main fretboard

    def __init__(self, neck: Neck, bar_fret: int, engaged_levers: Set[str], parent=None):
        super().__init__(parent)
        self.neck = neck
        self.bar_fret = bar_fret
        self.engaged_levers = set(engaged_levers)
        self.parent_window = parent

        self.setWindowTitle("Current Stance Chord & Grip Inspector")
        self.resize(1020, 680)
        self.setMinimumWidth(880)

        self.active_category = "All Candidates"
        self.cached_results: List[Dict] = []
        self.custom_selected_strings: Set[int] = set()

        self._init_ui()
        self.refresh_scan(self.neck, self.bar_fret, self.engaged_levers)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # 1. Stance State & Split Banner
        self.info_frame = QFrame()
        self.info_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1d24;
                border: 1.5px solid #343a40;
                border-radius: 8px;
            }
        """)
        info_vbox = QVBoxLayout(self.info_frame)
        info_vbox.setContentsMargins(12, 10, 12, 10)
        info_vbox.setSpacing(6)

        info_top = QHBoxLayout()
        self.lbl_stance_title = QLabel("<b>Current Stance:</b> Fret 0 | Controllers: Open")
        self.lbl_stance_title.setStyleSheet("font-size: 14px; color: #ffc107;")
        info_top.addWidget(self.lbl_stance_title)

        info_top.addStretch()

        self.cb_live_sync = QCheckBox("🔄 Live Sync with Fretboard")
        self.cb_live_sync.setChecked(True)
        self.cb_live_sync.setStyleSheet("font-weight: bold; color: #20c997;")
        info_top.addWidget(self.cb_live_sync)

        info_vbox.addLayout(info_top)

        self.lbl_split_status = QLabel("Splits: None Active")
        self.lbl_split_status.setStyleSheet("font-size: 11px; color: #adb5bd;")
        info_vbox.addWidget(self.lbl_split_status)

        root.addWidget(self.info_frame)

        # 2. Interactive Custom String Picker & Category Filters
        filter_group = QGroupBox("Filter by Grip Type or Select Active Strings")
        filter_layout = QVBoxLayout(filter_group)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setSpacing(8)

        # Quick Category Buttons
        cat_h = QHBoxLayout()
        cat_h.addWidget(QLabel("<b>Grip Filter:</b>"))

        self.combo_category = QComboBox()
        self.combo_category.addItems([
            "All Candidates",
            "Franklin Foundation Groups",
            "3-Note Triads",
            "4-Note Comping Blocks",
            "Newman 2-Note Dyads",
            "Copedant Presets",
            "Custom Selected Strings",
        ])
        self.combo_category.currentIndexChanged.connect(self._on_category_changed)
        cat_h.addWidget(self.combo_category, stretch=1)

        self.lbl_match_count = QLabel("Found: 0 chords")
        self.lbl_match_count.setStyleSheet("font-weight: bold; color: #0dcaf0; padding-left: 10px;")
        cat_h.addWidget(self.lbl_match_count)

        filter_layout.addLayout(cat_h)

        # Interactive String Toggle Strip for Custom Grip Evaluation
        str_picker_h = QHBoxLayout()
        str_picker_h.addWidget(QLabel("<small><b>Toggle Strings for Custom Grip:</b></small>"))

        self.string_check_buttons: Dict[int, QPushButton] = {}
        for s_num in range(1, self.neck.string_count + 1):
            btn = QPushButton(str(s_num))
            btn.setCheckable(True)
            btn.setFixedSize(28, 28)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2b303c;
                    color: #ced4da;
                    font-weight: bold;
                    border: 1px solid #495057;
                    border-radius: 4px;
                }
                QPushButton:checked {
                    background-color: #0d6efd;
                    color: white;
                    border: 1.5px solid #ffffff;
                }
            """)
            btn.toggled.connect(lambda checked, s=s_num: self._on_custom_string_toggled(s, checked))
            str_picker_h.addWidget(btn)
            self.string_check_buttons[s_num] = btn

        self.btn_clear_custom = QPushButton("Clear")
        self.btn_clear_custom.setStyleSheet("padding: 2px 8px; font-size: 11px;")
        self.btn_clear_custom.clicked.connect(self._clear_custom_strings)
        str_picker_h.addWidget(self.btn_clear_custom)

        str_picker_h.addStretch()
        filter_layout.addLayout(str_picker_h)

        root.addWidget(filter_group)

        # 3. Main Results Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Grip (Strings)",
            "Identified Chord / Harmony",
            "Voicing Type",
            "Group / Category",
            "Notes Sounding",
            "Action",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.cellDoubleClicked.connect(self._on_table_double_clicked)
        root.addWidget(self.table, stretch=1)

        # 4. Footer Actions
        footer = QHBoxLayout()
        self.lbl_hint = QLabel("<small>💡 <i>Click any row or 'Arm & Play' to load that grip onto the fretboard canvas.</i></small>")
        self.lbl_hint.setStyleSheet("color: #8b92a0;")
        footer.addWidget(self.lbl_hint)

        footer.addStretch()

        self.btn_refresh = QPushButton("🔄 Refresh Scan")
        self.btn_refresh.setStyleSheet("font-weight: bold; padding: 4px 12px;")
        self.btn_refresh.clicked.connect(lambda: self.refresh_scan(self.neck, self.bar_fret, self.engaged_levers))
        footer.addWidget(self.btn_refresh)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)

        root.addLayout(footer)

    def _get_candidate_grips_pool(self) -> List[Tuple[Tuple[int, ...], str]]:
        """Compiles standard, consecutive, skipped, and preset grip groupings for evaluation."""
        grips: List[Tuple[Tuple[int, ...], str]] = []
        num_str = self.neck.string_count

        # 1. Franklin Foundation Groups
        for text, desc, pocket in FRANKLIN_E9_GROUPS:
            tup = tuple(sorted(pocket))
            if max(tup) <= num_str:
                grips.append((tup, f"Franklin ({text})"))

        # 2. Newman Dyads
        for text, desc, pocket in NEWMAN_DYAD_POCKETS:
            tup = tuple(sorted(pocket))
            if max(tup) <= num_str:
                grips.append((tup, f"Newman Dyad ({text})"))

        # 3. Standard Copedant Presets
        if self.neck.neck_type == NeckType.C6 or "C6" in self.neck.name:
            c_cards = C6_GRIP_CARDS
        elif num_str >= 12:
            c_cards = U12_GRIP_CARDS
        else:
            c_cards = E9_GRIP_CARDS

        for text, desc, pocket in c_cards:
            tup = tuple(sorted(pocket))
            if max(tup) <= num_str and (tup, desc) not in grips:
                grips.append((tup, desc))

        # 4. All Consecutive 3-String Triads
        for i in range(1, num_str - 1):
            grips.append(((i, i + 1, i + 2), f"Triad ({i}-{i+1}-{i+2})"))

        # 5. All Consecutive 4-String Comping Blocks
        for i in range(1, num_str - 2):
            grips.append(((i, i + 1, i + 2, i + 3), f"4-Block ({i}-{i+1}-{i+2}-{i+3})"))

        # 6. Common Skip-String Pockets
        skip_patterns = [
            (10, 8, 6), (9, 7, 5), (8, 6, 4), (7, 5, 3), (6, 4, 2), (5, 3, 1),
            (10, 8, 6, 5), (8, 6, 5, 4), (6, 5, 4, 3), (5, 4, 3, 2), (4, 3, 2, 1),
            (12, 10, 8), (11, 9, 6), (12, 11, 9), (12, 11, 9, 6),
        ]
        for sp in skip_patterns:
            tup = tuple(sorted(sp))
            if max(tup) <= num_str:
                desc_str = "-".join(map(str, sorted(tup, reverse=True)))
                grips.append((tup, f"Pocket ({desc_str})"))

        # Deduplicate
        seen = set()
        deduped = []
        for g, cat in grips:
            if g not in seen:
                seen.add(g)
                deduped.append((g, cat))

        return deduped

    def refresh_scan(self, neck: Neck, bar_fret: int, engaged_levers: Set[str]):
        """Evaluates all sounding pitches for the exact current stance and populates chords."""
        self.neck = neck
        self.bar_fret = bar_fret
        self.engaged_levers = set(engaged_levers)

        # 1. Update Info Header
        ctrl_str = " + ".join(sorted(self.engaged_levers)) if self.engaged_levers else "None (Open)"
        self.lbl_stance_title.setText(f"<b>Current Stance:</b> Fret {self.bar_fret} | Controllers: <b>{ctrl_str}</b> ({self.neck.name})")

        # 2. Resolve Active States across entire neck (including active mechanical splits)
        states = FretboardResolver.resolve_neck_state(
            neck=self.neck,
            fret=self.bar_fret,
            engaged_levers=self.engaged_levers,
        )
        state_by_str: Dict[int, ActiveStringState] = {s.string_number: s for s in states}

        # Check Active Splits
        active_splits = [s for s in states if getattr(s, "is_split_applied", False)]
        if active_splits:
            split_descs = [f"Str {s.string_number} ➔ {s.active_note_name}" for s in active_splits]
            self.lbl_split_status.setText(f"<b>⚡ Active Changer Splits:</b> {', '.join(split_descs)}")
            self.lbl_split_status.setStyleSheet("font-size: 11px; color: #b180f0; font-weight: bold;")
        else:
            self.lbl_split_status.setText("Splits: None Active (standard changer movement)")
            self.lbl_split_status.setStyleSheet("font-size: 11px; color: #8b92a0;")

        # 3. Scan Grips
        candidates = self._get_candidate_grips_pool()
        if self.custom_selected_strings and len(self.custom_selected_strings) >= 2:
            custom_tup = tuple(sorted(self.custom_selected_strings))
            candidates.insert(0, (custom_tup, "Custom Selected Strings"))

        results = []
        for grip_tup, cat_desc in candidates:
            grip_states = [state_by_str[s] for s in grip_tup if s in state_by_str]
            if len(grip_states) != len(grip_tup):
                continue

            pitches = [s.active_midi for s in grip_states]
            # Bass note is on highest string number (lowest physical pitch in standard steel tuning)
            bass_state = max(grip_states, key=lambda s: s.string_number)
            sounding_notes_str = ", ".join(f"Str {s.string_number}: {s.active_note_name}" for s in sorted(grip_states, key=lambda x: x.string_number))

            if len(grip_tup) == 2:
                # 2-Note Dyad
                p1, p2 = pitches[0], pitches[1]
                semi = abs(p1 - p2) % 12
                int_names = {
                    0: "Unison / Octave", 3: "Minor 3rd", 4: "Major 3rd",
                    5: "Perfect 4th", 6: "Tritone (b5 / #4)", 7: "Perfect 5th",
                    8: "Minor 6th", 9: "Major 6th", 10: "Minor 7th", 11: "Major 7th",
                }
                int_lbl = int_names.get(semi, f"{semi} Semitones")
                n1, n2 = grip_states[0].active_note_name[:-1], grip_states[1].active_note_name[:-1]
                chord_title = f"{n1} & {n2} ({int_lbl})"
                results.append({
                    "grip": set(grip_tup),
                    "grip_label": " - ".join(map(str, sorted(grip_tup, reverse=True))),
                    "chord_name": chord_title,
                    "voicing_type": "Dyad / Interval",
                    "category": cat_desc,
                    "sounding_notes": sounding_notes_str,
                })
            else:
                # 3- or 4-Note Chords
                match = ChordIdentifier.identify_voicing(
                    pitches=pitches,
                    bass_pitch=bass_state.active_midi,
                    show_inversion=True,
                    grip_strings=set(grip_tup),
                )
                if match:
                    raw_tag, family = match
                    results.append({
                        "grip": set(grip_tup),
                        "grip_label": " - ".join(map(str, sorted(grip_tup, reverse=True))),
                        "chord_name": raw_tag,
                        "voicing_type": family,
                        "category": cat_desc,
                        "sounding_notes": sounding_notes_str,
                    })

        self.cached_results = results
        self._populate_table()

    def _on_category_changed(self):
        self.active_category = self.combo_category.currentText()
        self._populate_table()

    def _on_custom_string_toggled(self, str_num: int, checked: bool):
        if checked:
            self.custom_selected_strings.add(str_num)
        else:
            self.custom_selected_strings.discard(str_num)

        if len(self.custom_selected_strings) >= 2:
            self.combo_category.setCurrentText("Custom Selected Strings")
        self.refresh_scan(self.neck, self.bar_fret, self.engaged_levers)

    def _clear_custom_strings(self):
        for btn in self.string_check_buttons.values():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
        self.custom_selected_strings.clear()
        self.combo_category.setCurrentText("All Candidates")
        self.refresh_scan(self.neck, self.bar_fret, self.engaged_levers)

    def _populate_table(self):
        # Filter based on active_category
        filtered = []
        for r in self.cached_results:
            cat = r["category"]
            v_type = r["voicing_type"]
            g_len = len(r["grip"])

            if self.active_category == "All Candidates":
                filtered.append(r)
            elif self.active_category == "Franklin Foundation Groups" and "Franklin" in cat:
                filtered.append(r)
            elif self.active_category == "3-Note Triads" and g_len == 3 and "Dyad" not in v_type:
                filtered.append(r)
            elif self.active_category == "4-Note Comping Blocks" and g_len == 4:
                filtered.append(r)
            elif self.active_category == "Newman 2-Note Dyads" and g_len == 2:
                filtered.append(r)
            elif self.active_category == "Copedant Presets" and ("Franklin" in cat or "Pocket" in cat or "Grip" in cat or "Triad (" in cat):
                filtered.append(r)
            elif self.active_category == "Custom Selected Strings" and cat == "Custom Selected Strings":
                filtered.append(r)

        self.lbl_match_count.setText(f"Found: {len(filtered)} chords")
        self.table.setRowCount(len(filtered))

        for idx, item in enumerate(filtered):
            self.table.setItem(idx, 0, QTableWidgetItem(item["grip_label"]))

            ch_item = QTableWidgetItem(item["chord_name"])
            ch_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.table.setItem(idx, 1, ch_item)

            self.table.setItem(idx, 2, QTableWidgetItem(item["voicing_type"]))
            self.table.setItem(idx, 3, QTableWidgetItem(item["category"]))
            self.table.setItem(idx, 4, QTableWidgetItem(item["sounding_notes"]))

            btn_arm = QPushButton("🤏 Arm & Play")
            btn_arm.setCursor(QCursor(Qt.PointingHandCursor))
            btn_arm.setStyleSheet("""
                QPushButton {
                    background-color: #0d6efd;
                    color: white;
                    font-weight: bold;
                    font-size: 10px;
                    border-radius: 4px;
                    padding: 3px 8px;
                }
                QPushButton:hover {
                    background-color: #0b5ed7;
                }
            """)
            btn_arm.clicked.connect(lambda _, g=item["grip"]: self._apply_and_play_grip(g))
            self.table.setCellWidget(idx, 5, btn_arm)

    def _apply_and_play_grip(self, grip: Set[int]):
        """Transmits the selected grip to the main fretboard canvas and plays it."""
        self.grip_applied.emit(set(grip))
        if self.parent_window and hasattr(self.parent_window, "_apply_pocket_preset"):
            self.parent_window._apply_pocket_preset(set(grip))
            self.parent_window._play_pocket(roll=False)

    def _on_table_double_clicked(self, row: int, col: int):
        item_text = self.table.item(row, 0).text()
        nums = {int(x.strip()) for x in item_text.split("-")}
        self._apply_and_play_grip(nums)