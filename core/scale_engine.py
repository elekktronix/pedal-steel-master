"""Pedal steel position pocket and scale box engine (3-4 fret spans across all strings)."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from core.ergonomics import ErgonomicsEngine
from core.models import Neck
from core.resolver import FretboardResolver
from core.stances import detect_roles, is_c6_neck, resolve_stance
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
    # Role tokens (core.stances); mapped to the neck's controller IDs at runtime (D-23).
    ALLOWED_COMBOS_E9 = [
        (),
        ("A",),
        ("B",),
        ("A", "B"),
        ("F",),
        ("D",),
        ("A", "F"),
        ("B", "RKL"),
    ]

    ALLOWED_COMBOS_C6 = [
        (),
        ("C6P4",),
        ("C6P5",),
        ("C6P6",),
        ("C6P7",),
        ("C6P8",),
        ("C6P4", "C6P5"),
        ("C6P5", "C6P6"),
        ("RKL",),
        ("RKR",),
    ]

    @classmethod
    def _valid_combos(cls, neck: Neck) -> List[Set[str]]:
        combos = cls.ALLOWED_COMBOS_C6 if is_c6_neck(neck) else cls.ALLOWED_COMBOS_E9
        roles = detect_roles(neck)
        valid_combos: List[Set[str]] = []
        for tokens in combos:
            stance = resolve_stance(neck, tokens, roles)
            if stance is None or stance in valid_combos:
                continue
            if not ErgonomicsEngine.evaluate_stance(stance).is_possible:
                continue  # a role can land on a controller the player can't combine with the other
            valid_combos.append(stance)
        return valid_combos

    @staticmethod
    def _state_lookup(neck: Neck, root_name: str, scale_name: str):
        """Resolves each (fret, combo) once; callers only look results up (D-31)."""
        state_cache: Dict[Tuple[int, frozenset], Dict[int, object]] = {}

        def _states(fret: int, levers: Set[str]) -> Dict[int, object]:
            key = (fret, frozenset(levers))
            if key not in state_cache:
                state_cache[key] = {
                    st.string_number: st
                    for st in FretboardResolver.resolve_neck_state(
                        neck=neck,
                        fret=fret,
                        engaged_levers=levers,
                        target_root_name=root_name,
                        target_scale_name=scale_name,
                    )
                }
            return state_cache[key]

        return _states

    @staticmethod
    def _harvest_window(
        neck: Neck,
        root_pc: int,
        scale_formula: Dict[int, str],
        valid_combos: List[Set[str]],
        states,
        f_start: int,
        f_end: int,
    ) -> Tuple[Dict[int, List[BoxNote]], List[BoxNote], List[BoxNote]]:
        """Scale tones per string inside frets f_start..f_end, plus the strictly ascending run."""
        notes_by_string: Dict[int, List[BoxNote]] = {
            s: [] for s in range(neck.string_count, 0, -1)
        }
        all_box_notes: List[BoxNote] = []

        for s_num in range(1, neck.string_count + 1):
            seen_pitches_on_string: Dict[int, BoxNote] = {}

            for fret in range(f_start, f_end + 1):
                for levers in valid_combos:
                    s_state = states(fret, levers).get(s_num)
                    if not s_state:
                        continue

                    interval = (s_state.pitch_class - root_pc) % 12
                    if interval in scale_formula:
                        deg = scale_formula[interval]
                        b_note = BoxNote(
                            string_number=s_num,
                            fret=fret,
                            engaged_levers=sorted(list(levers)),
                            note_name=s_state.active_note_name,
                            midi_note=s_state.active_midi,
                            degree_label=deg,
                            is_root=(deg == "1"),
                        )

                        p = s_state.active_midi
                        # If pitch seen on this string, keep the one with fewer pedals / closer fret
                        if p not in seen_pitches_on_string or len(levers) < len(seen_pitches_on_string[p].engaged_levers):
                            seen_pitches_on_string[p] = b_note

            sorted_string_notes = sorted(seen_pitches_on_string.values(), key=lambda n: n.midi_note)
            notes_by_string[s_num] = sorted_string_notes
            all_box_notes.extend(sorted_string_notes)

        return notes_by_string, all_box_notes, ScaleSolver.playable_run(all_box_notes)

    # Step-path weights (E-30 phase 2): what it costs to go from one note of the run to the next.
    COST_FRET = 3.0          # per fret the bar travels
    COST_CONTROLLER = 2.0    # per pedal or lever pressed or released
    COST_STRING_SKIP = 1.5   # per string skipped beyond the neighbouring one
    COST_BACKTRACK = 2.5     # moving to a lower-pitched string while the run climbs
    COST_HELD = 0.5          # per controller held down for the note itself

    @classmethod
    def transition_cost(cls, a: BoxNote, b: BoxNote) -> float:
        """Cost of playing b right after a, for a run that climbs from a to b."""
        cost = abs(a.fret - b.fret) * cls.COST_FRET
        cost += len(set(a.engaged_levers) ^ set(b.engaged_levers)) * cls.COST_CONTROLLER
        ds = b.string_number - a.string_number  # negative = towards the higher-pitched strings
        cost += max(0, abs(ds) - 1) * cls.COST_STRING_SKIP
        if ds > 0:
            cost += cls.COST_BACKTRACK
        return cost

    @classmethod
    def playable_run(cls, notes: List[BoxNote]) -> List[BoxNote]:
        """One note per distinct pitch, low to high, choosing for each pitch the spot (string, fret,
        controllers) that gives the cheapest path overall (dynamic programming over the spots)."""
        by_pitch: Dict[int, List[BoxNote]] = {}
        for n in notes:
            by_pitch.setdefault(n.midi_note, []).append(n)
        if not by_pitch:
            return []
        layers = [
            sorted(by_pitch[p], key=lambda n: (-n.string_number, len(n.engaged_levers), n.fret))
            for p in sorted(by_pitch)
        ]
        best = [len(n.engaged_levers) * cls.COST_HELD for n in layers[0]]
        back: List[List[int]] = []
        for prev_layer, layer in zip(layers, layers[1:]):
            row_cost, row_back = [], []
            for n in layer:
                held = len(n.engaged_levers) * cls.COST_HELD
                costs = [best[i] + cls.transition_cost(p, n) for i, p in enumerate(prev_layer)]
                i_min = min(range(len(costs)), key=costs.__getitem__)
                row_cost.append(costs[i_min] + held)
                row_back.append(i_min)
            best = row_cost
            back.append(row_back)
        j = min(range(len(best)), key=best.__getitem__)
        path = [layers[-1][j]]
        for depth in range(len(back) - 1, -1, -1):
            j = back[depth][j]
            path.append(layers[depth][j])
        return path[::-1]

    @classmethod
    def run_cost(cls, run: List[BoxNote]) -> float:
        return sum(cls.transition_cost(a, b) for a, b in zip(run, run[1:]))

    RUN_UP, RUN_DOWN, RUN_UP_DOWN = "up", "down", "updown"

    @classmethod
    def build_run(cls, box: ScaleBox, direction: str = "up", root_to_root: bool = False) -> List[BoxNote]:
        """The box's playable run in the requested order. Up & back does not repeat the top note.
        root_to_root trims the run to the lowest..highest root when the range holds at least two."""
        run = list(box.ascending_run)
        if root_to_root:
            roots = [i for i, n in enumerate(run) if n.is_root]
            if len(roots) >= 2:
                run = run[roots[0]:roots[-1] + 1]
        if direction == cls.RUN_DOWN:
            return run[::-1]
        if direction == cls.RUN_UP_DOWN:
            return run + run[-2::-1]
        return run

    @classmethod
    def find_scale_in_range(
        cls,
        neck: Neck,
        root_name: str,
        scale_name: str,
        min_fret: int,
        max_fret: int,
    ) -> Optional[ScaleBox]:
        """Every scale tone between two user-chosen frets (inclusive), as one ScaleBox (E-30).

        Unlike find_scale_boxes there is no coverage filter: the user asked for exactly this range.
        """
        if root_name not in NOTE_TO_SEMITONE or scale_name not in SCALE_FORMULAS:
            return None
        lo, hi = sorted((max(0, min(24, int(min_fret))), max(0, min(24, int(max_fret)))))
        scale_formula = SCALE_FORMULAS[scale_name]
        notes_by_string, all_box_notes, ascending_run = cls._harvest_window(
            neck, NOTE_TO_SEMITONE[root_name], scale_formula, cls._valid_combos(neck),
            cls._state_lookup(neck, root_name, scale_name), lo, hi,
        )
        root_strings = sorted({n.string_number for n in all_box_notes if n.is_root})
        width = hi - lo + 1
        return ScaleBox(
            box_id=0,
            name=f"Frets {lo} - {hi}",
            min_fret=lo,
            max_fret=hi,
            fret_span_str=f"Frets {lo} - {hi} ({width}-fret range)",
            root_strings=root_strings,
            notes_by_string=notes_by_string,
            ascending_run=ascending_run,
            total_notes=len(all_box_notes),
            covered_degrees=sorted({n.degree_label for n in all_box_notes}),
        )

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
        valid_combos = cls._valid_combos(neck)
        _states = cls._state_lookup(neck, root_name, scale_name)

        candidate_boxes: List[ScaleBox] = []

        # Scan anchor fret positions
        for anchor in range(0, max_neck_fret + 1):
            f_start = anchor
            f_end = min(24, anchor + fret_span - 1)

            notes_by_string, all_box_notes, ascending_run = cls._harvest_window(
                neck, root_pc, scale_formula, valid_combos, _states, f_start, f_end
            )

            # Filter out windows that lack string coverage
            strings_with_notes = [s for s, n in notes_by_string.items() if len(n) > 0]
            if len(strings_with_notes) < max(5, neck.string_count - 3):
                continue

            unique_degrees = sorted(list(set(n.degree_label for n in all_box_notes)))
            # Require at least 5 unique scale degrees in the box
            if len(unique_degrees) < min(5, len(scale_formula)):
                continue

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