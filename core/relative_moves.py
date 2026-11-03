"""Engine for Same-Fret Harmony (Diatonic, I-IV-V, Dominants, and Full Copedant Scan)
and Relative Fret Movements (Warnock / Barndo).
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from core.chord_identifier import ChordIdentifier
from core.models import Neck, NeckType
from core.resolver import FretboardResolver
from core.theory import NOTE_NAMES_SHARP, NOTE_TO_SEMITONE

ENHARMONIC_FLAT_NAMES: Dict[str, str] = {
    "A#": "Bb",
    "D#": "Eb",
    "G#": "Ab",
}


def format_chord_root(name: str) -> str:
    return ENHARMONIC_FLAT_NAMES.get(name, name)


def _safe_extract_root_and_quality(chord_label: str) -> Tuple[str, str]:
    clean = chord_label.strip()
    if not clean:
        return ("", "")
    for r in sorted(NOTE_TO_SEMITONE.keys(), key=len, reverse=True):
        if clean.startswith(r):
            return (r, clean[len(r):].strip())
    return ("", "")


@dataclass
class RelativeMoveOption:
    label: str               # e.g., "I (G)", "IV (C)", "V7 (D7)"
    chord_name: str          # e.g., "G Maj", "C Maj", "D7"
    target_fret: int
    delta_frets: int
    controllers: Set[str]    # e.g., {"P1", "P2"}
    target_strings: Set[int]
    description: str
    roman_degree: str = ""   # e.g., "I", "IV", "V7", "ii", "vi"
    category: str = "diatonic"


class RelativeMovesEngine:
    @classmethod
    def get_same_fret_diatonic_hub(cls, current_fret: int) -> List[RelativeMoveOption]:
        """Franklin's original 7 Same-Fret Diatonic etude chords."""
        base_pc = (4 + current_fret) % 12
        root_name = format_chord_root(NOTE_NAMES_SHARP[base_pc])

        ii_name = format_chord_root(NOTE_NAMES_SHARP[(base_pc + 2) % 12])
        iii_name = format_chord_root(NOTE_NAMES_SHARP[(base_pc + 4) % 12])
        iv_name = format_chord_root(NOTE_NAMES_SHARP[(base_pc + 5) % 12])
        vi_name = format_chord_root(NOTE_NAMES_SHARP[(base_pc + 9) % 12])
        sharp1_name = format_chord_root(NOTE_NAMES_SHARP[(base_pc + 1) % 12])

        return [
            RelativeMoveOption(f"I ({root_name})", f"{root_name} Maj", current_fret, 0, set(), {8, 6, 5}, f"Tonic I Major at Fret {current_fret}", "I", "primary"),
            RelativeMoveOption(f"ii ({ii_name}m)", f"{ii_name}m", current_fret, 0, {"P2", "P3"}, {6, 5, 4}, "Supertonic ii Minor (P2+P3)", "ii", "diatonic"),
            RelativeMoveOption(f"iii ({iii_name}m)", f"{iii_name}m", current_fret, 0, {"RKL"}, {8, 6, 5}, "Mediant iii Minor (RKL lowered Es)", "iii", "diatonic"),
            RelativeMoveOption(f"IV ({iv_name})", f"{iv_name} Maj", current_fret, 0, {"P1", "P2"}, {8, 6, 5}, "Subdominant IV Major (A&B pedals)", "IV", "primary"),
            RelativeMoveOption(f"vi ({vi_name}m)", f"{vi_name}m", current_fret, 0, {"P1"}, {6, 5, 4}, "Submediant vi Minor (A pedal)", "vi", "diatonic"),
            RelativeMoveOption(f"#I° ({sharp1_name}°)", f"{sharp1_name}dim", current_fret, 0, {"LKL"}, {6, 5, 4}, "#1 Diminished passing (LKL raised Es)", "#I°", "dim"),
            RelativeMoveOption(f"I 6/9 ({root_name}6/9)", f"{root_name}6/9", current_fret, 0, {"P3"}, {6, 5, 4}, "Tonic 6/9 color chord (P3 pedal)", "I 6/9", "color"),
        ]

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
            return cls.get_same_fret_diatonic_hub(current_fret)

        is_c6 = (neck.neck_type == NeckType.C6 or "C6" in neck.name)
        tonic_pc = (0 + current_fret) % 12 if is_c6 else (4 + current_fret) % 12
        tonic_name = format_chord_root(NOTE_NAMES_SHARP[tonic_pc])

        if is_c6:
            candidate_stances: List[Tuple[str, Set[str]]] = [
                ("Open", set()),
                ("P5", {"P5"}),
                ("P6", {"P6"}),
                ("P7", {"P7"}),
                ("P8", {"P8"}),
                ("P5+P6", {"P5", "P6"}),
                ("P6+P7", {"P6", "P7"}),
                ("P7+P8", {"P7", "P8"}),
            ]
            candidate_grips = [
                {7, 6, 5}, {6, 5, 4}, {5, 4, 3}, {4, 3, 2},
                {8, 7, 6, 5}, {7, 6, 5, 4}, {6, 5, 4, 3},
            ]
        else:
            candidate_stances = [
                ("Open", set()),
                ("P1+P2", {"P1", "P2"}),    # Priority 1 for IV Major
                ("P2+LKR", {"P2", "LKR"}),  # Priority 1 for V7 Dominant
                ("P1", {"P1"}),            # vi Minor
                ("P2", {"P2"}),
                ("P3", {"P3"}),            # 6/9
                ("LKL", {"LKL"}),          # #I dim
                ("LKV", {"LKV"}),
                ("LKR", {"LKR"}),
                ("RKL", {"RKL"}),          # iii Minor
                ("RKR", {"RKR"}),
                ("P2+P3", {"P2", "P3"}),    # ii Minor
                ("P1+P3", {"P1", "P3"}),
                ("P1+LKL", {"P1", "LKL"}),
                ("P2+LKL", {"P2", "LKL"}),
                ("P1+LKR", {"P1", "LKR"}),
                ("P3+LKR", {"P3", "LKR"}),
                ("P3+LKL", {"P3", "LKL"}),
                ("P1+RKL", {"P1", "RKL"}),
                ("P2+RKL", {"P2", "RKL"}),
            ]
            candidate_grips = [
                {8, 6, 5}, {6, 5, 4}, {5, 4, 3}, {10, 8, 6},
                {9, 8, 6, 5}, {9, 6, 5, 4}, {8, 6, 4},
            ]

        available_ctrls = set(neck.pedals.keys()) | set(neck.knee_levers.keys())
        valid_stances = [s for s in candidate_stances if s[1].issubset(available_ctrls)]

        ROMAN_MAJ = {
            0: "I", 1: "bII", 2: "II", 3: "bIII", 4: "III", 5: "IV",
            6: "bV", 7: "V", 8: "bVI", 9: "VI", 10: "bVII", 11: "VII"
        }
        ROMAN_MIN = {
            0: "i", 1: "bii", 2: "ii", 3: "biii", 4: "iii", 5: "iv",
            6: "bv", 7: "v", 8: "bvi", 9: "vi", 10: "bvii", 11: "vii"
        }

        best_chord_map: Dict[Tuple[str, str], Tuple[int, RelativeMoveOption]] = {}

        for stance_name, ctrls in valid_stances:
            ctrl_affects: Dict[str, Set[int]] = {}
            for c_id in ctrls:
                c_obj = neck.pedals.get(c_id) or neck.knee_levers.get(c_id)
                if c_obj:
                    ctrl_affects[c_id] = {s for s, delta in c_obj.changes.items() if delta != 0}
                else:
                    ctrl_affects[c_id] = set()

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

                match = ChordIdentifier.identify_voicing(
                    pitches=pitches,
                    bass_pitch=bass_state.active_midi,
                    show_inversion=False,
                    grip_strings=set(grip),
                )
                if not match:
                    continue

                raw_tag, family = match

                # REJECT incomplete dyads/power chords from pretending to be full major triads
                if "Dyad" in family or "5th" in family:
                    continue

                root, quality = _safe_extract_root_and_quality(raw_tag)
                if not root or root not in NOTE_TO_SEMITONE:
                    continue

                clean_root = format_chord_root(root)
                root_pc = NOTE_TO_SEMITONE[root]
                delta_semi = (root_pc - tonic_pc) % 12

                q_clean = quality.strip()
                q_low = q_clean.lower()

                is_dim = "dim" in q_low or "°" in q_low or "m7b5" in q_low
                is_minor = ("min" in q_low or "m" in q_low) and "maj" not in q_low and not is_dim
                is_dom = ("7" in q_clean or "9" in q_clean or "dom" in q_low) and not is_minor and "maj" not in q_low and not is_dim
                is_sus = "sus" in q_low
                is_69 = "6/9" in q_clean
                is_maj6 = "6" in q_clean and not is_69
                is_maj7 = "maj7" in q_low

                if is_dim:
                    roman = f"{ROMAN_MIN[delta_semi]}°"
                    pill_label = f"{roman} ({clean_root}°)"
                    cat = "dim"
                elif is_minor:
                    roman = f"{ROMAN_MIN[delta_semi]}7" if "7" in q_clean else ROMAN_MIN[delta_semi]
                    pill_label = f"{roman} ({clean_root}m)"
                    cat = "diatonic" if roman in ("ii", "iii", "vi") else "minor"
                elif is_dom:
                    roman = f"{ROMAN_MAJ[delta_semi]}7"
                    pill_label = f"{roman} ({clean_root}7)"
                    cat = "primary" if roman == "V7" else "dominant"
                elif is_sus:
                    roman = f"{ROMAN_MAJ[delta_semi]}sus"
                    pill_label = f"{roman} ({clean_root}sus)"
                    cat = "color"
                elif is_69:
                    roman = f"{ROMAN_MAJ[delta_semi]} 6/9"
                    pill_label = f"{roman} ({clean_root}6/9)"
                    cat = "color"
                elif is_maj6:
                    roman = f"{ROMAN_MAJ[delta_semi]}6"
                    pill_label = f"{roman} ({clean_root}6)"
                    cat = "color"
                elif is_maj7:
                    roman = f"{ROMAN_MAJ[delta_semi]}maj7"
                    pill_label = f"{roman} ({clean_root}maj7)"
                    cat = "color"
                else:
                    roman = ROMAN_MAJ[delta_semi]
                    pill_label = f"{roman} ({clean_root})"
                    cat = "primary" if roman in ("I", "IV", "V") else "diatonic"

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

                # Enforce textbook steel pedal combinations
                if roman == "IV" and ctrls == {"P1", "P2"}:
                    score -= 500  # P1+P2 is the definitive IV chord
                elif roman == "V7" and ctrls == {"P2", "LKR"}:
                    score -= 500  # P2+LKR is the definitive V7 chord
                elif roman == "I" and len(ctrls) == 0:
                    score -= 500  # Open bar is the definitive I chord
                elif roman == "vi" and ctrls == {"P1"}:
                    score -= 400  # P1 is the definitive vi chord
                elif roman == "ii" and ctrls == {"P2", "P3"}:
                    score -= 400  # P2+P3 is the definitive ii chord
                elif roman == "iii" and ctrls == {"RKL"}:
                    score -= 400  # RKL is the definitive iii chord

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
                desc = f"{roman} {clean_root} {quality} ({ctrl_desc} on strings {grip_desc})"

                opt = RelativeMoveOption(
                    label=pill_label,
                    chord_name=f"{clean_root} {quality}",
                    target_fret=current_fret,
                    delta_frets=0,
                    controllers=set(ctrls),
                    target_strings=set(grip),
                    description=desc,
                    roman_degree=roman,
                    category=cat,
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
    def get_e9_relative_movements(cls, current_fret: int, active_levers: Set[str]) -> List[RelativeMoveOption]:
        """Calculates Patricia Warnock's E9 relative movement formulas."""
        base_pc = (4 + current_fret) % 12
        root_name = format_chord_root(NOTE_NAMES_SHARP[base_pc])
        moves: List[RelativeMoveOption] = []

        f_af = current_fret + 3
        if f_af <= 24:
            moves.append(
                RelativeMoveOption(
                    label="+3 Frets (A + LKL)",
                    chord_name=f"{root_name} Maj (I)",
                    target_fret=f_af,
                    delta_frets=3,
                    controllers={"P1", "LKL"},
                    target_strings={6, 5, 4},
                    description=f"Slide +3 to Fret {f_af} with A pedal & F lever for {root_name} Major (I)",
                )
            )

        f_ab = current_fret + 2
        if f_ab <= 24:
            v_name = format_chord_root(NOTE_NAMES_SHARP[(base_pc + 7) % 12])
            moves.append(
                RelativeMoveOption(
                    label="+2 Frets (A + B)",
                    chord_name=f"{v_name} Maj (V)",
                    target_fret=f_ab,
                    delta_frets=2,
                    controllers={"P1", "P2"},
                    target_strings={6, 5, 4},
                    description=f"Slide +2 to Fret {f_ab} with A & B pedals for Dominant {v_name} Major (V)",
                )
            )

        f_bc = current_fret - 2
        if f_bc >= 0:
            moves.append(
                RelativeMoveOption(
                    label="-2 Frets (B + C Minor)",
                    chord_name=f"{root_name}m (i)",
                    target_fret=f_bc,
                    delta_frets=-2,
                    controllers={"P2", "P3"},
                    target_strings={6, 5, 4},
                    description=f"Slide -2 to Fret {f_bc} with B & C pedals for {root_name} minor (i)",
                )
            )

        f_d = current_fret - 4 if (current_fret - 4 >= 0) else (current_fret + 8)
        delta_d = f_d - current_fret
        if 0 <= f_d <= 24:
            sign_str = f"+{delta_d}" if delta_d > 0 else f"{delta_d}"
            moves.append(
                RelativeMoveOption(
                    label=f"{sign_str} Frets (D Lever Minor)",
                    chord_name=f"{root_name}m (i)",
                    target_fret=f_d,
                    delta_frets=delta_d,
                    controllers={"LKR"},
                    target_strings={6, 5, 4},
                    description=f"Slide {sign_str} to Fret {f_d} with D lever for {root_name} minor (i)",
                )
            )

        return moves

    @classmethod
    def get_c6_relative_movements(cls, current_fret: int) -> List[RelativeMoveOption]:
        """Calculates Petria Barndo's C6 relative movement formulas."""
        base_pc = (0 + current_fret) % 12
        moves: List[RelativeMoveOption] = []

        iv_name = format_chord_root(NOTE_NAMES_SHARP[(base_pc + 5) % 12])
        moves.append(
            RelativeMoveOption(
                label="Same Fret (Pedal 6)",
                chord_name=f"{iv_name} Maj (IV)",
                target_fret=current_fret,
                delta_frets=0,
                controllers={"P6"},
                target_strings={4, 3, 2},
                description=f"Same fret {iv_name} Major with Pedal 6 on strings 4-3-2",
            )
        )

        f_p6_up = current_fret + 7
        if f_p6_up <= 24:
            c_name = format_chord_root(NOTE_NAMES_SHARP[base_pc])
            moves.append(
                RelativeMoveOption(
                    label="+7 Frets (Pedal 6)",
                    chord_name=f"{c_name} Maj (1st Inv)",
                    target_fret=f_p6_up,
                    delta_frets=7,
                    controllers={"P6"},
                    target_strings={4, 3, 2},
                    description=f"Slide +7 with Pedal 6 for {c_name} Major 1st Inversion",
                )
            )

        f_p8 = current_fret + 3
        if f_p8 <= 24:
            c_name = format_chord_root(NOTE_NAMES_SHARP[base_pc])
            moves.append(
                RelativeMoveOption(
                    label="+3 Frets (Pedal 8)",
                    chord_name=f"{c_name} Maj (2nd Inv)",
                    target_fret=f_p8,
                    delta_frets=3,
                    controllers={"P8"},
                    target_strings={9, 8, 7},
                    description=f"Slide +3 with Pedal 8 for {c_name} Major 2nd Inversion",
                )
            )

        f_p6_min = current_fret - 3
        if f_p6_min >= 0:
            rel_min = format_chord_root(NOTE_NAMES_SHARP[(base_pc + 9) % 12])
            moves.append(
                RelativeMoveOption(
                    label="-3 Frets (Pedal 6 Minor)",
                    chord_name=f"{rel_min}m (vi)",
                    target_fret=f_p6_min,
                    delta_frets=-3,
                    controllers={"P6"},
                    target_strings={7, 6, 5},
                    description=f"Slide -3 with Pedal 6 for {rel_min} minor",
                )
            )

        f_p7 = current_fret + 5
        if f_p7 <= 24:
            c6_name = format_chord_root(NOTE_NAMES_SHARP[base_pc])
            moves.append(
                RelativeMoveOption(
                    label="+5 Frets (Pedal 7 Maj6)",
                    chord_name=f"{c6_name}6",
                    target_fret=f_p7,
                    delta_frets=5,
                    controllers={"P7"},
                    target_strings={5, 4, 3, 2},
                    description=f"Slide +5 with Pedal 7 for {c6_name} Major 6 block",
                )
            )

        return moves