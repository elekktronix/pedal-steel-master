"""Voicing solver with physical ergonomics, interval omissions, controller filtering,
Franklin triad substitutions, C6 open chord presets, and diminished matrix resolution.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from core.ergonomics import ErgonomicsEngine, ErgonomicStance, StanceDifficulty
from core.models import Neck
from core.resolver import FretboardResolver
from core.theory import CHORD_FORMULAS, NOTE_NAMES_SHARP, NOTE_TO_SEMITONE


@dataclass
class VoicingMatch:
    fret: int
    engaged_levers: List[str]
    grip_strings: List[int]
    grip_key: str
    bass_note: str
    bass_interval: str
    voicing_formula: str
    score: float
    ergonomics: ErgonomicStance


# Alias for backward compatibility
SolvedVoicing = VoicingMatch


@dataclass
class NeighborVoicing:
    relationship: str          # "IV (Subdominant)", "V (Dominant)", "V7 (Dominant 7th)", etc.
    chord_name: str            # "C Maj", "D7"
    fret: int
    delta_frets: int           # 0, +2, +7
    engaged_levers: List[str]
    grip_strings: List[int]
    movement_type: str         # "Same-Fret Pedal Drop", "Hold Pedals & Slide", "Open Bar Shift", etc.
    transition_summary: str    # "Slide +2 frets | Hold P1+P2"


class VoicingSolver:
    STANDARD_E9_GRIPS = [
        [10, 8, 6], [8, 6, 5], [8, 6, 4], [6, 5, 4],
        [5, 4, 3], [4, 3, 1], [10, 8, 6, 5], [8, 6, 5, 4],
        [6, 5, 4, 3], [5, 4, 3, 2], [8, 6, 5, 4, 3],
    ]

    STANDARD_C6_GRIPS = [
        # 4-note comping blocks (Petria Barndo / C6 Essay)
        [8, 7, 6, 5],
        [7, 6, 5, 4],
        [6, 5, 4, 3],
        [5, 4, 3, 2],
        [4, 3, 2, 1],
        # 3-note foundational triads
        [7, 6, 5],
        [6, 5, 3],
        [5, 3, 2],
        [4, 3, 2],
        [3, 2, 1],
        [10, 7, 5],
    ]

    STANDARD_U12_GRIPS = [
        # Upper E9 Pockets
        [8, 6, 5], [8, 6, 4], [6, 5, 4], [5, 4, 3], [4, 3, 1],
        [8, 6, 5, 4], [6, 5, 4, 3], [5, 4, 3, 2],
        # Universal Middle & Lower Pockets
        [10, 8, 6], [11, 9, 6], [11, 10, 8], [11, 9, 8, 6],
        # Low String 12 Grips
        [12, 11, 9], [12, 10, 8], [12, 11, 9, 6],
        [12, 10, 8, 6], [12, 11, 10, 8], [12, 11, 10, 9],
    ]

    @classmethod
    def get_candidate_grips(cls, neck: Neck) -> List[List[int]]:
        if neck.string_count >= 12 or neck.neck_type.value == "Universal 12":
            presets = cls.STANDARD_U12_GRIPS
        elif "C6" in neck.name or neck.neck_type.value == "C6":
            presets = cls.STANDARD_C6_GRIPS
        else:
            presets = cls.STANDARD_E9_GRIPS

        return [g for g in presets if max(g) <= neck.string_count]

    @classmethod
    def _generate_candidate_stances(cls, neck: Neck) -> List[Set[str]]:
        available_pedals = sorted(list(neck.pedals.keys()))
        available_levers = sorted(list(neck.knee_levers.keys()))

        pedal_options: List[Set[str]] = [set()]
        for p in available_pedals:
            pedal_options.append({p})

        for i in range(len(available_pedals)):
            for j in range(i + 1, len(available_pedals)):
                candidate = {available_pedals[i], available_pedals[j]}
                if ErgonomicsEngine.evaluate_stance(candidate).is_possible:
                    pedal_options.append(candidate)

        knee_options: List[Set[str]] = [set()]
        for lev in available_levers:
            knee_options.append({lev})

        for i in range(len(available_levers)):
            for j in range(i + 1, len(available_levers)):
                candidate = {available_levers[i], available_levers[j]}
                if ErgonomicsEngine.evaluate_stance(candidate).is_possible:
                    knee_options.append(candidate)

        stances: List[Set[str]] = []
        for p_set in pedal_options:
            for k_set in knee_options:
                combined = p_set | k_set
                if ErgonomicsEngine.evaluate_stance(combined).is_possible:
                    stances.append(combined)

        return stances

    @classmethod
    def classify_movement(
        cls,
        origin_fret: int,
        origin_levers: List[str],
        target_fret: int,
        target_levers: List[str],
    ) -> str:
        """Classifies the mechanical transition between two pedal steel stances."""
        delta = target_fret - origin_fret
        orig_set = set(origin_levers or [])
        target_set = set(target_levers or [])

        if delta == 0:
            return "Same-Fret Pedal Drop"
        elif (delta == 2 and "P1" in target_set and "P2" in target_set) or (
            delta != 0 and target_set == orig_set and len(target_set) > 0
        ):
            return "Hold Pedals & Slide"
        elif delta != 0 and len(target_set) == 0:
            return "Open Bar Shift"
        else:
            return "Position Shift"

    @classmethod
    def find_all_voicings(
        cls,
        neck: Neck,
        root_name: str,
        chord_type: str,
        max_fret: int = 15,
        filter_awkward: bool = False,
        omitted_intervals: Optional[Set[str]] = None,
        max_controllers: Optional[int] = None,
        allowed_controllers_only: Optional[Set[str]] = None,
    ) -> List[VoicingMatch]:
        if root_name not in NOTE_TO_SEMITONE or chord_type not in CHORD_FORMULAS:
            return []

        omitted = omitted_intervals or set()
        full_formula = CHORD_FORMULAS[chord_type]
        target_intervals = {v for v in full_formula.values() if v not in omitted}

        if not target_intervals:
            return []

        candidate_stances = cls._generate_candidate_stances(neck)
        candidate_grips = cls.get_candidate_grips(neck)

        matches: List[VoicingMatch] = []
        seen_keys = set()

        for fret in range(0, max_fret + 1):
            for levers in candidate_stances:
                if max_controllers is not None and len(levers) > max_controllers:
                    continue

                if allowed_controllers_only is not None and not levers.issubset(allowed_controllers_only):
                    continue

                ergo = ErgonomicsEngine.evaluate_stance(levers)
                if not ergo.is_possible:
                    continue
                if filter_awkward and ergo.difficulty == StanceDifficulty.AWKWARD:
                    continue

                states = FretboardResolver.resolve_neck_state(
                    neck=neck,
                    fret=fret,
                    engaged_levers=levers,
                    target_root_name=root_name,
                    target_chord_type=chord_type,
                )
                state_by_str = {s.string_number: s for s in states}

                for grip in candidate_grips:
                    grip_states = [state_by_str[s] for s in grip if s in state_by_str]
                    if len(grip_states) != len(grip):
                        continue

                    if not all(s.is_chord_tone and (s.interval_label not in omitted) for s in grip_states):
                        continue

                    present_intervals = {s.interval_label for s in grip_states}
                    required_unique = min(len(target_intervals), min(len(grip), 3))
                    if len(present_intervals) < required_unique:
                        continue

                    has_third_in_target = any(lbl in target_intervals for lbl in ("3", "b3", "4"))
                    if has_third_in_target and not any(lbl in present_intervals for lbl in ("3", "b3", "4")):
                        continue

                    grip_key = "-".join(map(str, sorted(grip, reverse=True)))
                    levers_key = "+".join(sorted(list(levers)))
                    unique_id = (fret, levers_key, grip_key)
                    if unique_id in seen_keys:
                        continue
                    seen_keys.add(unique_id)

                    bass = max(grip_states, key=lambda s: s.string_number)
                    sorted_tones = sorted(grip_states, key=lambda s: s.string_number, reverse=True)
                    formula_str = " - ".join(s.interval_label for s in sorted_tones if s.interval_label)

                    score = len(present_intervals) * 14.0
                    if "R" in present_intervals:
                        score += 5.0
                    if any(t in present_intervals for t in ("3", "b3")):
                        score += 6.0
                    if len(grip_states) == len(present_intervals):
                        score += 3.0

                    score -= ergo.penalty

                    matches.append(
                        VoicingMatch(
                            fret=fret,
                            engaged_levers=sorted(list(levers)),
                            grip_strings=sorted(grip),
                            grip_key=grip_key,
                            bass_note=bass.active_note_name,
                            bass_interval=bass.interval_label or "",
                            voicing_formula=formula_str,
                            score=score,
                            ergonomics=ergo,
                        )
                    )

        matches.sort(key=lambda m: (-m.score, m.fret, len(m.engaged_levers)))
        return matches

    @classmethod
    def find_circle_neighbors(
        cls,
        neck: Neck,
        origin_root: str,
        origin_fret: int,
        origin_grip: List[int],
        origin_levers: Optional[List[str]] = None,
        allowed_mechanics: Optional[Set[str]] = None,
    ) -> List[NeighborVoicing]:
        """Finds closest matching voicings for Circle of Fifths neighbors including V7."""
        from core.circle_of_fifths import CIRCLE_KEYS_CLOCKWISE, RELATIVE_MINORS

        if origin_root not in NOTE_TO_SEMITONE:
            return []

        # Locate the key by pitch class so enharmonic spellings (C#, D#, G#, A#, Gb) work (D-18).
        origin_pc = NOTE_TO_SEMITONE[origin_root]
        c_idx = next(i for i, k in enumerate(CIRCLE_KEYS_CLOCKWISE) if NOTE_TO_SEMITONE[k] == origin_pc)
        circle_key = CIRCLE_KEYS_CLOCKWISE[c_idx]

        v_root = CIRCLE_KEYS_CLOCKWISE[(c_idx + 1) % 12]
        iv_root = CIRCLE_KEYS_CLOCKWISE[(c_idx - 1) % 12]
        vi_root = RELATIVE_MINORS.get(circle_key, "")
        ii_root = CIRCLE_KEYS_CLOCKWISE[(c_idx + 2) % 12]

        targets = [
            ("IV (Subdominant)", iv_root, "Major"),
            ("V (Dominant)", v_root, "Major"),
            ("V7 (Dominant 7th)", v_root, "Dominant 7th"),
            ("vi (Relative Minor)", vi_root, "Minor"),
            ("ii (Supertonic)", ii_root, "Minor"),
        ]

        orig_levers_set = set(origin_levers or [])
        neighbors: List[NeighborVoicing] = []

        for role, root, chord_type in targets:
            if not root:
                continue

            matches = cls.find_all_voicings(
                neck=neck,
                root_name=root,
                chord_type=chord_type,
                max_fret=min(24, origin_fret + 9),
                filter_awkward=True,
            )

            pocket_matches = [m for m in matches if m.grip_strings == origin_grip]
            candidate_pool = pocket_matches if pocket_matches else matches

            for m in candidate_pool:
                delta = m.fret - origin_fret
                m_levers_set = set(m.engaged_levers)

                if delta == 0 and m_levers_set != orig_levers_set:
                    movement = "Same-Fret Pedal Drop"
                    action = f"Stay at Fret {m.fret} | Engage {', '.join(m.engaged_levers) if m.engaged_levers else 'Open'}"
                elif delta != 0 and m_levers_set == orig_levers_set and len(m_levers_set) > 0:
                    delta_str = f"+{delta}" if delta > 0 else f"{delta}"
                    movement = "Hold Pedals & Slide"
                    action = f"Slide {delta_str} frets to F{m.fret} | HOLD {', '.join(m.engaged_levers)}"
                elif delta == 2 and "P1" in m.engaged_levers and "P2" in m.engaged_levers:
                    movement = "Hold Pedals & Slide"
                    action = f"Slide +2 to F{m.fret} | Keep P1+P2 down"
                elif delta != 0 and len(m_levers_set) == 0:
                    delta_str = f"+{delta}" if delta > 0 else f"{delta}"
                    movement = "Open Bar Shift"
                    action = f"Slide {delta_str} frets to F{m.fret} | Open Bar"
                else:
                    delta_str = f"+{delta}" if delta > 0 else f"{delta}"
                    lev = f"with {', '.join(m.engaged_levers)}" if m.engaged_levers else "Open"
                    movement = "Position Shift"
                    action = f"Move {delta_str} frets to F{m.fret} {lev}"

                if allowed_mechanics is not None and movement not in allowed_mechanics:
                    continue

                neighbors.append(
                    NeighborVoicing(
                        relationship=role,
                        chord_name=f"{root} {chord_type[:3] if chord_type != 'Dominant 7th' else '7'}",
                        fret=m.fret,
                        delta_frets=delta,
                        engaged_levers=m.engaged_levers,
                        grip_strings=m.grip_strings,
                        movement_type=movement,
                        transition_summary=action,
                    )
                )

        neighbors.sort(key=lambda n: (abs(n.delta_frets) > 2, abs(n.delta_frets), len(n.engaged_levers)))

        deduped: List[NeighborVoicing] = []
        seen_keys = set()
        for n in neighbors:
            key = (n.relationship, n.movement_type, n.fret, tuple(n.engaged_levers))
            if key not in seen_keys:
                deduped.append(n)
                seen_keys.add(key)

        return deduped[:12]

    @classmethod
    def get_triad_substitution(cls, root_name: str, chord_type: str) -> Optional[Tuple[str, str, str]]:
        """Calculates Paul Franklin's Triad-Over-Root substitution.
        Returns: (substitute_triad_name, interval_relation, explanation)
        """
        if root_name not in NOTE_TO_SEMITONE:
            return None

        root_pc = NOTE_TO_SEMITONE[root_name]

        # 1. Major 7th: Minor triad off the 3rd (e.g. Cmaj7 -> Em over C)
        if chord_type in ("Major 7th", "Maj7", "maj7"):
            third_note = NOTE_NAMES_SHARP[(root_pc + 4) % 12]
            return (f"{third_note}m", "Minor triad on 3rd", f"Play {third_note}m triad over {root_name} bass to suggest {root_name}maj7")

        # 2. Dominant 9th: Minor triad off the 5th (e.g. G9 -> Dm over G)
        if chord_type in ("Dominant 9th", "Dom 9", "9"):
            fifth_note = NOTE_NAMES_SHARP[(root_pc + 7) % 12]
            return (f"{fifth_note}m", "Minor triad on 5th", f"Play {fifth_note}m triad (5-b7-9) over {root_name} bass for {root_name}9")

        # 3. Dominant 11th: Major triad off the b7th (e.g. G11 -> F over G)
        if chord_type in ("Dominant 11th", "Dom 11", "11"):
            b7_note = NOTE_NAMES_SHARP[(root_pc + 10) % 12]
            return (f"{b7_note}", "Major triad on b7th", f"Play {b7_note} triad (b7-9-11) over {root_name} bass for {root_name}11")

        # 4. Dominant 13th: Minor triad off the 9th (e.g. G13 -> Am over G)
        if chord_type in ("Dominant 13th", "Dom 13", "13"):
            ninth_note = NOTE_NAMES_SHARP[(root_pc + 2) % 12]
            return (f"{ninth_note}m", "Minor triad on 9th", f"Play {ninth_note}m triad (9-11-13) over {root_name} bass for {root_name}13")

        # 5. Altered Dominant 7(b9#5): Minor triad off the b9th
        if "alt" in chord_type.lower() or "b9#5" in chord_type or "7#9" in chord_type:
            b9_note = NOTE_NAMES_SHARP[(root_pc + 1) % 12]
            return (f"{b9_note}m", "Minor triad on b9th", f"Play {b9_note}m triad (b9-3-#5) over {root_name} bass for {root_name}7alt")

        # 6. Minor 7th: Major triad off the b3rd (e.g. Dm7 -> F over D)
        if chord_type in ("Minor 7th", "m7", "min7"):
            b3_note = NOTE_NAMES_SHARP[(root_pc + 3) % 12]
            return (f"{b3_note}", "Major triad on b3rd", f"Play {b3_note} triad over {root_name} bass to suggest {root_name}m7")

        return None
