"""Jeff Newman 'Strings of Pearls' Harmonized Scale & Twin-Track Slide Engine."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from core.models import Neck
from core.resolver import FretboardResolver
from core.stances import detect_roles, resolve_stance
from core.theory import NOTE_NAMES_SHARP, NOTE_TO_SEMITONE, SCALE_FORMULAS


@dataclass
class PearlStep:
    degree_label: str        # e.g., "1 (Tonic)", "2", "3", "4", "5"
    fret: int
    controllers: Set[str]    # {"P1", "P2"}, {"LKL"}, {"LKR"}, set()
    string_pair: Tuple[int, int]  # e.g., (3, 5), (4, 5), (5, 8)
    notes: Tuple[str, str]        # e.g., ("G", "B")
    interval_desc: str       # "Major 3rd", "Minor 6th", "Unison / Octave"
    fret_delta: int = 0      # Shift from previous step


class PearlsEngine:
    # Supported twin-track string pairs
    TWIN_TRACKS: Dict[str, Tuple[int, int]] = {
        "Strings 3 & 5 (6ths / 3rds)": (3, 5),
        "Strings 4 & 5 (3rds / 4ths)": (4, 5),
        "Strings 5 & 8 (Melody Track)": (5, 8),
        "Strings 5 & 6 (Close 3rds)": (5, 6),
    }

    @classmethod
    def generate_scale_run(
        cls,
        key_root: str,
        track_name: str = "Strings 3 & 5 (6ths / 3rds)",
        scale_type: str = "Major (Ionian)",
        max_fret: int = 22,
        neck: Optional[Neck] = None,
    ) -> List[PearlStep]:
        """Calculates consecutive physical slide steps along the fretboard for the selected pair.

        Pitches come from the resolver for the given neck (standard E9 if none), and the A/B/F/D
        stances are mapped to that neck's controllers by function (D-23).
        """
        if key_root not in NOTE_TO_SEMITONE:
            return []
        if neck is None:
            from core import presets

            neck = presets.build_standard_emmons_e9_10()

        string_pair = cls.TWIN_TRACKS.get(track_name, (3, 5))
        key_pc = NOTE_TO_SEMITONE[key_root]
        scale_dict = SCALE_FORMULAS.get(scale_type, SCALE_FORMULAS["Major (Ionian)"])

        pearl_steps: List[PearlStep] = []
        prev_fret: Optional[int] = None

        # Candidate stances for twin tracks: Open, Pedal A, Pedal B, Pedals A+B, F Lever, D Lever
        roles = detect_roles(neck)
        stances: List[Tuple[str, Set[str]]] = []
        for stance_name, tokens in [
            ("Open", ()), ("A Pedal", ("A",)), ("B Pedal", ("B",)),
            ("A & B", ("A", "B")), ("F Lever", ("F",)), ("D Lever", ("D",)),
        ]:
            stance = resolve_stance(neck, tokens, roles)
            if stance is None:
                continue
            # Skip stances that don't change either string of the pair: they would only
            # duplicate the open row (D-34).
            controllers = {**neck.pedals, **neck.knee_levers}
            if stance and not any(controllers[c].changes.get(s, 0) for c in stance for s in string_pair):
                continue
            stances.append((stance_name, stance))
        if any(s not in {sp.string_number for sp in neck.open_tuning} for s in string_pair):
            return []

        # Scan each fret 0 to max_fret
        for fret in range(0, max_fret + 1):
            for stance_name, ctrls in stances:
                states = {
                    s.string_number: s
                    for s in FretboardResolver.resolve_neck_state(neck, fret, ctrls)
                }
                p1_pitch = states[string_pair[0]].active_midi
                p2_pitch = states[string_pair[1]].active_midi

                p1_pc = p1_pitch % 12
                p2_pc = p2_pitch % 12

                # Check if both pitches belong to the parent scale
                deg1_offset = (p1_pc - key_pc) % 12
                deg2_offset = (p2_pc - key_pc) % 12

                if deg1_offset in scale_dict and deg2_offset in scale_dict:
                    deg_lbl = scale_dict[deg2_offset]
                    n1 = NOTE_NAMES_SHARP[p1_pc]
                    n2 = NOTE_NAMES_SHARP[p2_pc]

                    interval_semitones = abs(p1_pitch - p2_pitch) % 12
                    int_desc = cls._get_interval_name(interval_semitones)

                    delta = 0 if prev_fret is None else (fret - prev_fret)

                    # Deduplicate redundant steps at the same fret
                    if not any(s.fret == fret and s.controllers == ctrls for s in pearl_steps):
                        pearl_steps.append(
                            PearlStep(
                                degree_label=f"Degree {deg_lbl}",
                                fret=fret,
                                controllers=set(ctrls),
                                string_pair=string_pair,
                                notes=(n1, n2),
                                interval_desc=int_desc,
                                fret_delta=delta,
                            )
                        )
                        prev_fret = fret

        pearl_steps.sort(key=lambda s: (s.fret, len(s.controllers)))
        return pearl_steps

    @staticmethod
    def _get_interval_name(semitones: int) -> str:
        mapping = {
            0: "Octave / Unison",
            3: "Minor 3rd",
            4: "Major 3rd",
            5: "Perfect 4th",
            7: "Perfect 5th",
            8: "Minor 6th",
            9: "Major 6th",
        }
        return mapping.get(semitones, f"{semitones} Semitones")