"""Engine for Same-Fret Harmony (Diatonic, I-IV-V, Dominants, and Full Copedant Scan)
and Relative Fret Movements (Warnock / Barndo).

Stances are declared with functional role tokens (core.stances) and mapped to the neck's real
controller IDs. Static formulas (Franklin hub, Warnock, Barndo) are verified with the resolver,
so an option is only offered if it really sounds the chord it names on the active neck.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from core.chord_identifier import ChordIdentifier
from core.models import Neck
from core.resolver import FretboardResolver
from core.stances import detect_roles, grip_matches_chord, is_c6_neck, resolve_stance
from core.theory import CHORD_FORMULAS, CHORD_SYMBOL_SUFFIX, NOTE_NAMES_SHARP, NOTE_TO_SEMITONE, respell

ENHARMONIC_FLAT_NAMES: Dict[str, str] = {
    "A#": "Bb",
    "D#": "Eb",
    "G#": "Ab",
}



_DIM_TYPES = {"Diminished": "°", "Diminished 7th": "°7", "Half-Diminished": "ø7"}
_MINOR_TYPES = {"Minor": "", "Minor 7th": "7", "Minor 6th": "6", "Minor 9th": "9"}


def _chord_name(root: str, chord_type: str) -> str:
    """Display name built from the root and the formula suffix (A1); "E Maj" for a plain triad."""
    if chord_type == "Major":
        return f"{root} Maj"
    return f"{root}{CHORD_SYMBOL_SUFFIX.get(chord_type, ' ' + chord_type)}"


def _roman_for(chord_type: str, delta: int, root: str, roman_maj: Dict[int, str],
               roman_min: Dict[int, str]) -> Tuple[str, str, str]:
    """(roman numeral, pill label, category) for a same-fret option, decided by the chord type
    (a CHORD_FORMULAS key), so aug, m6 and m7b5 keep their own forms (A1)."""
    name = _chord_name(root, chord_type) if chord_type != "Major" else root
    if chord_type in _DIM_TYPES:
        roman = f"{roman_min[delta]}{_DIM_TYPES[chord_type]}"
        return roman, f"{roman} ({name})", "dim"
    if chord_type in _MINOR_TYPES:
        roman = f"{roman_min[delta]}{_MINOR_TYPES[chord_type]}"
        if chord_type == "Minor":
            cat = "diatonic" if roman in ("ii", "iii", "vi") else "minor"
        else:
            cat = "minor" if chord_type == "Minor 7th" else "color"
        return roman, f"{roman} ({name})", cat
    if chord_type == "Dominant 7th":
        roman = f"{roman_maj[delta]}7"
        return roman, f"{roman} ({name})", "primary" if roman == "V7" else "dominant"
    if chord_type.startswith("Dominant"):
        roman = f"{roman_maj[delta]}{CHORD_SYMBOL_SUFFIX.get(chord_type, '7')}"
        return roman, f"{roman} ({name})", "dominant"
    if chord_type == "Major":
        roman = roman_maj[delta]
        return roman, f"{roman} ({name})", "primary" if roman in ("I", "IV", "V") else "diatonic"
    special = {"Sus4": "sus", "6/9": " 6/9", "Major 6th": "6", "Major 7th": "maj7", "Augmented": "+"}
    roman = f"{roman_maj[delta]}{special.get(chord_type, CHORD_SYMBOL_SUFFIX.get(chord_type, ''))}"
    return roman, f"{roman} ({name})", "color"


def format_chord_root(name: str) -> str:
    return respell(name)  # global sharps/flats preference


def _default_neck(c6: bool = False) -> Neck:
    from core import presets

    return presets.build_standard_c6_10() if c6 else presets.build_standard_emmons_e9_10()


@dataclass
class RelativeMoveOption:
    label: str               # e.g., "I (G)", "IV (C)", "V7 (D7)"
    chord_name: str          # e.g., "G Maj", "C Maj", "D7"
    target_fret: int
    delta_frets: int
    controllers: Set[str]    # actual controller IDs, e.g. {"P1", "P2"}
    target_strings: Set[int]
    description: str
    roman_degree: str = ""   # e.g., "I", "IV", "V7", "ii", "vi"
    category: str = "diatonic"
    chord_root: str = ""     # e.g. "Bb" (for harmonic analysis; never parse chord_name, D-28)
    chord_type: str = ""     # CHORD_FORMULAS key, e.g. "Minor", "Dominant 7th"


# Franklin same-fret hub: (roman, semitones above tonic, chord type, role tokens, grip, description,
#                          category, require_root). Tonic = E at fret 0.
_FRANKLIN_HUB = [
    ("I", 0, "Major", (), {8, 6, 5}, "Tonic I Major (open)", "primary", True),
    ("ii", 2, "Minor", ("B", "C"), {6, 5, 4}, "Supertonic ii Minor (B+C pedals)", "diatonic", True),
    ("iii", 4, "Minor", ("D",), {8, 6, 5}, "Mediant iii Minor (D lever lowers Es)", "diatonic", True),
    ("IV", 5, "Major", ("A", "B"), {8, 6, 5}, "Subdominant IV Major (A&B pedals)", "primary", True),
    ("vi", 9, "Minor", ("A",), {6, 5, 4}, "Submediant vi Minor (A pedal)", "diatonic", True),
    ("#I°", 1, "Diminished", ("F",), {6, 5, 4}, "#1 Diminished passing (F lever raises Es)", "dim", True),
    ("I 6/9", 0, "6/9", ("C",), {6, 5, 4}, "Tonic 6/9 color chord (C pedal)", "color", False),
]

_E9_SCAN_STANCES: List[Tuple[str, ...]] = [
    (), ("A", "B"), ("B", "D"), ("A",), ("B",), ("C",), ("F",), ("BL",), ("D",), ("RKL",), ("RKR",),
    ("B", "C"), ("A", "C"), ("A", "F"), ("B", "F"), ("A", "D"), ("C", "D"), ("C", "F"),
    ("A", "RKL"), ("B", "RKL"),
]
_C6_SCAN_STANCES: List[Tuple[str, ...]] = [
    (), ("C6P5",), ("C6P6",), ("C6P7",), ("C6P8",),
    ("C6P5", "C6P6"), ("C6P6", "C6P7"), ("C6P7", "C6P8"),
]
# Textbook stances that win ties for a given roman numeral (E9).
_E9_CANONICAL = {"I": (), "IV": ("A", "B"), "V7": ("B", "D"), "vi": ("A",), "ii": ("B", "C"), "iii": ("D",)}
_CANONICAL_BONUS = {"I": 500, "IV": 500, "V7": 500, "vi": 400, "ii": 400, "iii": 400}


def _root_name(pc: int) -> str:
    return format_chord_root(NOTE_NAMES_SHARP[pc % 12])


class RelativeMovesEngine:
    @classmethod
    def get_same_fret_diatonic_hub(cls, current_fret: int, neck: Optional[Neck] = None) -> List[RelativeMoveOption]:
        """Franklin's same-fret diatonic etude chords, verified against the neck (D-15)."""
        neck = neck if neck is not None else _default_neck()
        roles = detect_roles(neck)
        tonic_pc = (4 + current_fret) % 12
        options: List[RelativeMoveOption] = []

        for roman, offset, chord_type, tokens, grip, desc, cat, need_root in _FRANKLIN_HUB:
            stance = resolve_stance(neck, tokens, roles)
            if stance is None:
                continue
            root = _root_name(tonic_pc + offset)
            if not grip_matches_chord(neck, current_fret, stance, grip, root, chord_type, require_root=need_root):
                continue
            suffix = {"Minor": "m", "Diminished": "°", "6/9": "6/9"}.get(chord_type, "")
            chord_name = f"{root} Maj" if chord_type == "Major" else f"{root}{'dim' if suffix == '°' else suffix}"
            options.append(
                RelativeMoveOption(
                    label=f"{roman} ({root}{suffix})",
                    chord_name=chord_name,
                    target_fret=current_fret,
                    delta_frets=0,
                    controllers=stance,
                    target_strings=set(grip),
                    description=desc,
                    roman_degree=roman,
                    category=cat,
                    chord_root=root,
                    chord_type=chord_type,
                )
            )
        return options

    @classmethod
    def get_all_same_fret_chords(
        cls,
        neck: Neck,
        current_fret: int,
        filter_mode: str = "diatonic",
    ) -> List[RelativeMoveOption]:
        """Scans the neck at current_fret, eliminates ghost controllers and false dyads,
        and prioritizes full triads over partial chords.
        """
        if filter_mode == "franklin":
            return cls.get_same_fret_diatonic_hub(current_fret, neck)

        is_c6 = is_c6_neck(neck)
        tonic_pc = (0 + current_fret) % 12 if is_c6 else (4 + current_fret) % 12
        roles = detect_roles(neck)

        if is_c6:
            stance_tokens = _C6_SCAN_STANCES
            candidate_grips = [
                {7, 6, 5}, {6, 5, 4}, {5, 4, 3}, {4, 3, 2},
                {8, 7, 6, 5}, {7, 6, 5, 4}, {6, 5, 4, 3},
            ]
            canonical: Dict[str, Set[str]] = {}
        else:
            stance_tokens = _E9_SCAN_STANCES
            candidate_grips = [
                {8, 6, 5}, {6, 5, 4}, {5, 4, 3}, {10, 8, 6},
                {9, 8, 6, 5}, {9, 6, 5, 4}, {8, 6, 4},
            ]
            canonical = {}
            for roman, tokens in _E9_CANONICAL.items():
                stance = resolve_stance(neck, tokens, roles)
                if stance is not None:
                    canonical[roman] = stance

        valid_stances: List[Set[str]] = []
        for tokens in stance_tokens:
            stance = resolve_stance(neck, tokens, roles)
            if stance is not None and stance not in valid_stances:
                valid_stances.append(stance)

        ROMAN_MAJ = {
            0: "I", 1: "bII", 2: "II", 3: "bIII", 4: "III", 5: "IV",
            6: "bV", 7: "V", 8: "bVI", 9: "VI", 10: "bVII", 11: "VII"
        }
        ROMAN_MIN = {
            0: "i", 1: "bii", 2: "ii", 3: "biii", 4: "iii", 5: "iv",
            6: "bv", 7: "v", 8: "bvi", 9: "vi", 10: "bvii", 11: "vii"
        }

        best_chord_map: Dict[Tuple[str, str], Tuple[int, RelativeMoveOption]] = {}

        for ctrls in valid_stances:
            ctrl_affects: Dict[str, Set[int]] = {}
            for c_id in ctrls:
                c_obj = neck.pedals.get(c_id) or neck.knee_levers.get(c_id)
                ctrl_affects[c_id] = {s for s, delta in c_obj.changes.items() if delta != 0} if c_obj else set()

            states = FretboardResolver.resolve_neck_state(
                neck=neck,
                fret=current_fret,
                engaged_levers=ctrls,
            )
            state_by_str = {s.string_number: s for s in states}

            for grip in candidate_grips:
                if not all(s in state_by_str for s in grip):
                    continue

                if ctrls:
                    if any(not (aff & grip) for aff in ctrl_affects.values()):
                        continue

                grip_states = [state_by_str[s] for s in grip]
                pitches = [s.active_midi for s in grip_states]
                bass_state = max(grip_states, key=lambda s: s.string_number)

                match = ChordIdentifier.identify_chord(pitches, bass_state.active_midi)
                if not match:
                    continue
                root, chord_type = match  # data, never parsed from the display tag (A1)
                # Reject incomplete dyads/power chords pretending to be full triads.
                if chord_type not in CHORD_FORMULAS or root not in NOTE_TO_SEMITONE:
                    continue

                clean_root = format_chord_root(root)
                delta_semi = (NOTE_TO_SEMITONE[root] - tonic_pc) % 12
                roman, pill_label, cat = _roman_for(chord_type, delta_semi, clean_root, ROMAN_MAJ, ROMAN_MIN)

                if filter_mode == "i_iv_v":
                    if roman not in ("I", "IV", "V", "V7"):
                        continue
                elif filter_mode == "diatonic":
                    if roman not in ("I", "ii", "iii", "IV", "V", "V7", "vi", "vii°", "#I°", "I 6/9"):
                        continue
                elif filter_mode == "dominants":
                    if cat not in ("dominant", "primary") and roman not in ("V7", "I7", "II7", "VI7", "IV", "ii"):
                        continue

                # SCORING ENGINE:
                # 1. Canonical pedal combinations receive top priority
                # 2. Full 3-string closed triads win over loose shapes
                # 3. Penalize higher pedal counts only among identical chords
                score = len(ctrls) * 5
                if roman in canonical and ctrls == canonical[roman]:
                    score -= _CANONICAL_BONUS[roman]

                if grip == {8, 6, 5}:
                    score -= 30
                elif grip == {6, 5, 4}:
                    score -= 20

                key = (roman, clean_root)
                if key in best_chord_map:
                    if score >= best_chord_map[key][0]:
                        continue

                grip_desc = "-".join(map(str, sorted(grip, reverse=True)))
                ctrl_desc = " + ".join(sorted(ctrls)) if ctrls else "Open"
                chord_name = _chord_name(clean_root, chord_type)
                desc = f"{roman} {chord_name} ({ctrl_desc} on strings {grip_desc})"

                opt = RelativeMoveOption(
                    label=pill_label,
                    chord_name=chord_name,
                    target_fret=current_fret,
                    delta_frets=0,
                    controllers=set(ctrls),
                    target_strings=set(grip),
                    description=desc,
                    roman_degree=roman,
                    category=cat,
                    chord_root=clean_root,
                    chord_type=chord_type,
                )
                best_chord_map[key] = (score, opt)

        def _degree_order(opt: RelativeMoveOption) -> int:
            order_dict = {
                "I": 0, "I 6/9": 1, "I7": 2, "#I°": 3,
                "ii": 4, "iii": 5, "IV": 6, "V": 7, "V7": 8,
                "vi": 9, "vii°": 10
            }
            return order_dict.get(opt.roman_degree, 20)

        results = [v[1] for v in best_chord_map.values()]
        results.sort(key=_degree_order)
        return results

    @classmethod
    def _verified_moves(cls, neck: Neck, current_fret: int, specs) -> List[RelativeMoveOption]:
        """specs: (label, delta, tokens, strings, root, chord_type, chord_name, description)."""
        roles = detect_roles(neck)
        moves: List[RelativeMoveOption] = []
        for label, delta, tokens, strings, root, chord_type, chord_name, desc in specs:
            target = current_fret + delta
            if not 0 <= target <= 24:
                continue
            stance = resolve_stance(neck, tokens, roles)
            if stance is None or not grip_matches_chord(neck, target, stance, strings, root, chord_type):
                continue
            moves.append(
                RelativeMoveOption(
                    label=label,
                    chord_name=chord_name,
                    target_fret=target,
                    delta_frets=delta,
                    controllers=stance,
                    target_strings=set(strings),
                    description=desc.format(fret=target),
                    chord_root=root,
                    chord_type=chord_type,
                )
            )
        return moves

    @classmethod
    def get_e9_relative_movements(
        cls, current_fret: int, active_levers: Set[str], neck: Optional[Neck] = None
    ) -> List[RelativeMoveOption]:
        """Patricia Warnock's E9 relative movement formulas (verified on the neck)."""
        neck = neck if neck is not None else _default_neck()
        base_pc = (4 + current_fret) % 12
        root = _root_name(base_pc)
        v_root = _root_name(base_pc + 7)
        d_delta = -4 if current_fret - 4 >= 0 else 8
        d_sign = f"+{d_delta}" if d_delta > 0 else f"{d_delta}"
        specs = [
            ("+3 Frets (A + LKL)", 3, ("A", "F"), {6, 5, 4}, root, "Major", f"{root} Maj (I)",
             "Slide +3 to Fret {fret} with A pedal & F lever for " + f"{root} Major (I)"),
            ("+2 Frets (A + B)", 2, ("A", "B"), {6, 5, 4}, v_root, "Major", f"{v_root} Maj (V)",
             "Slide +2 to Fret {fret} with A & B pedals for Dominant " + f"{v_root} Major (V)"),
            ("-2 Frets (B + C Minor)", -2, ("B", "C"), {6, 5, 4}, root, "Minor", f"{root}m (i)",
             "Slide -2 to Fret {fret} with B & C pedals for " + f"{root} minor (i)"),
            (f"{d_sign} Frets (D Lever Minor)", d_delta, ("D",), {6, 5, 4}, root, "Minor", f"{root}m (i)",
             f"Slide {d_sign} to Fret " + "{fret}" + f" with D lever for {root} minor (i)"),
        ]
        return cls._verified_moves(neck, current_fret, specs)

    @classmethod
    def get_c6_relative_movements(cls, current_fret: int, neck: Optional[Neck] = None) -> List[RelativeMoveOption]:
        """Petria Barndo's C6 relative movement formulas (verified on the neck)."""
        neck = neck if neck is not None else _default_neck(c6=True)
        base_pc = (0 + current_fret) % 12
        c_name = _root_name(base_pc)
        iv_name = _root_name(base_pc + 5)
        rel_min = _root_name(base_pc + 9)
        specs = [
            ("Same Fret (Pedal 6)", 0, ("C6P6",), {4, 3, 2}, iv_name, "Major", f"{iv_name} Maj (IV)",
             f"Same fret {iv_name} Major with Pedal 6 on strings 4-3-2"),
            ("+7 Frets (Pedal 6)", 7, ("C6P6",), {4, 3, 2}, c_name, "Major", f"{c_name} Maj (1st Inv)",
             f"Slide +7 with Pedal 6 for {c_name} Major 1st Inversion"),
            ("+3 Frets (Pedal 8)", 3, ("C6P8",), {9, 8, 7}, c_name, "Major", f"{c_name} Maj (2nd Inv)",
             f"Slide +3 with Pedal 8 for {c_name} Major 2nd Inversion"),
            ("-3 Frets (Pedal 6 Minor)", -3, ("C6P6",), {7, 6, 5}, rel_min, "Minor", f"{rel_min}m (vi)",
             f"Slide -3 with Pedal 6 for {rel_min} minor"),
            ("+5 Frets (Pedal 7 Maj6)", 5, ("C6P7",), {5, 4, 3, 2}, c_name, "Major 6th", f"{c_name}6",
             f"Slide +5 with Pedal 7 for {c_name} Major 6 block"),
        ]
        return cls._verified_moves(neck, current_fret, specs)
