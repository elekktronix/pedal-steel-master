"""Pedal steel position pocket and scale box engine (3-4 fret spans across all strings)."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from core.models import Neck
from core.resolver import FretboardResolver
from core.theory import NOTE_NAMES_SHARP, NOTE_TO_SEMITONE, SCALE_FORMULAS, get_pitch_class


@dataclass
class BoxNote:
    string_number: int
    fret: int
    engaged_levers: List[str]
    note_name: str
    midi_note: int
    degree_label: str
    is_root: bool


@dataclass
class ScaleBox:
    box_id: int
    name: str                       # e.g. "Position 1 (Frets 3 - 5)"
    min_fret: int                   # 3
    max_fret: int                   # 5
    fret_span_str: str              # "Frets 3 - 5 (3-fret pocket)"
    root_strings: List[int]         # Strings holding root notes, e.g. [8, 4, 2]
    notes_by_string: Dict[int, List[BoxNote]]  # String 10 down to 1
    ascending_run: List[BoxNote]    # Step-by-step staircase from lowest bass to highest treble
    total_notes: int
    covered_degrees: List[str]


class ScaleSolver:
    ALLOWED_COMBOS_E9 = [
        set(),
        {"P1"},
        {"P2"},
        {"P1", "P2"},
        {"LKL"},
        {"LKR"},
        {"P1", "LKL"},
        {"P2", "RKL"},
    ]

    ALLOWED_COMBOS_C6 = [
        set(),
        {"P4"},
        {"P5"},
        {"P6"},
        {"P7"},
        {"P8"},
        {"P4", "P5"},
        {"P5", "P6"},
        {"RKL"},
        {"RKR"},
    ]

    @classmethod
    def find_scale_boxes(
        cls,
        neck: Neck,
        root_name: str,
        scale_name: str,
        fret_span: int = 3,  # 3 or 4 frets
        max_neck_fret: int = 14,
    ) -> List[ScaleBox]:
        """Finds idiomatic 3-4 fret position pockets covering the scale across all strings."""
        if root_name not in NOTE_TO_SEMITONE or scale_name not in SCALE_FORMULAS:
            return []

        scale_formula = SCALE_FORMULAS[scale_name]
        root_pc = NOTE_TO_SEMITONE[root_name]
        combos = cls.ALLOWED_COMBOS_C6 if "C6" in neck.name else cls.ALLOWED_COMBOS_E9
        available_controllers = set(neck.pedals.keys()) | set(neck.knee_levers.keys())
        valid_combos = [c for c in combos if c.issubset(available_controllers)]

        candidate_boxes: List[ScaleBox] = []

        # Scan anchor fret positions
        for anchor in range(0, max_neck_fret + 1):
            f_start = anchor
            f_end = min(24, anchor + fret_span - 1)

            notes_by_string: Dict[int, List[BoxNote]] = {
                s: [] for s in range(neck.string_count, 0, -1)
            }
            all_box_notes: List[BoxNote] = []

            # Harvest scale notes on every string inside this fret window
            for s_num in range(1, neck.string_count + 1):
                seen_pitches_on_string: Dict[int, BoxNote] = {}

                for fret in range(f_start, f_end + 1):
                    for levers in valid_combos:
                        states = FretboardResolver.resolve_neck_state(
                            neck=neck,
                            fret=fret,
                            engaged_levers=levers,
                            target_root_name=root_name,
                            target_scale_name=scale_name,
                        )
                        s_state = next((st for st in states if st.string_number == s_num), None)
                        if not s_state:
                            continue

                        interval = (s_state.pitch_class - root_pc) % 12
                        if interval in scale_formula:
                            deg = scale_formula[interval]
                            is_r = (deg == "1")
                            b_note = BoxNote(
                                string_number=s_num,
                                fret=fret,
                                engaged_levers=sorted(list(levers)),
                                note_name=s_state.active_note_name,
                                midi_note=s_state.active_midi,
                                degree_label=deg,
                                is_root=is_r,
                            )

                            p = s_state.active_midi
                            # If pitch seen on this string, keep the one with fewer pedals / closer fret
                            if p not in seen_pitches_on_string or len(levers) < len(seen_pitches_on_string[p].engaged_levers):
                                seen_pitches_on_string[p] = b_note

                sorted_string_notes = sorted(seen_pitches_on_string.values(), key=lambda n: n.midi_note)
                notes_by_string[s_num] = sorted_string_notes
                all_box_notes.extend(sorted_string_notes)

            # Filter out windows that lack string coverage
            strings_with_notes = [s for s, n in notes_by_string.items() if len(n) > 0]
            if len(strings_with_notes) < max(5, neck.string_count - 3):
                continue

            unique_degrees = sorted(list(set(n.degree_label for n in all_box_notes)))
            # Require at least 5 unique scale degrees in the box
            if len(unique_degrees) < min(5, len(scale_formula)):
                continue

            # Build strictly ascending staircase run across strings from bass to treble
            all_box_notes.sort(key=lambda n: (n.midi_note, -n.string_number, len(n.engaged_levers)))
            ascending_run: List[BoxNote] = []
            last_midi = -1

            for n in all_box_notes:
                if n.midi_note > last_midi:
                    ascending_run.append(n)
                    last_midi = n.midi_note

            root_strings = sorted(list(set(n.string_number for n in all_box_notes if n.is_root)))

            # Score box: rewards complete degree coverage, ascending run length, and root presence
            score = len(ascending_run) * 10 + len(unique_degrees) * 15 + len(root_strings) * 12

            candidate_boxes.append((
                score,
                f_start,
                ScaleBox(
                    box_id=0,
                    name=f"Position (Frets {f_start} - {f_end})",
                    min_fret=f_start,
                    max_fret=f_end,
                    fret_span_str=f"Frets {f_start} - {f_end} ({fret_span}-fret pocket)",
                    root_strings=root_strings,
                    notes_by_string=notes_by_string,
                    ascending_run=ascending_run,
                    total_notes=len(all_box_notes),
                    covered_degrees=unique_degrees,
                )
            ))

        # Deduplicate overlapping boxes (keep best positions across the neck)
        candidate_boxes.sort(key=lambda x: -x[0])
        selected_boxes: List[ScaleBox] = []
        covered_frets = set()

        for score, f_start, box in candidate_boxes:
            # Prevent dense overlapping windows (require at least 2 frets between box anchors)
            if any(abs(f_start - cf) < 2 for cf in covered_frets):
                continue
            selected_boxes.append(box)
            covered_frets.add(f_start)
            if len(selected_boxes) >= 5:
                break

        # Sort positions up the neck chronologically
        selected_boxes.sort(key=lambda b: b.min_fret)
        for idx, b in enumerate(selected_boxes, 1):
            b.box_id = idx
            roots_str = f"Roots on Str {', '.join(map(str, b.root_strings))}" if b.root_strings else "Scale Extension"
            b.name = f"Position {idx}: Frets {b.min_fret} - {b.max_fret} ({roots_str})"

        return selected_boxes