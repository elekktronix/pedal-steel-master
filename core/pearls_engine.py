"""Jeff Newman 'Strings of Pearls' Harmonized Scale & Twin-Track Slide Engine."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
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
    ) -> List[PearlStep]:
        """Calculates consecutive physical slide steps along the fretboard for the selected pair."""
        if key_root not in NOTE_TO_SEMITONE:
            return []

        string_pair = cls.TWIN_TRACKS.get(track_name, (3, 5))
        key_pc = NOTE_TO_SEMITONE[key_root]
        scale_dict = SCALE_FORMULAS.get(scale_type, SCALE_FORMULAS["Major (Ionian)"])

        pearl_steps: List[PearlStep] = []
        prev_fret: Optional[int] = None

        # Candidate controller stances for twin tracks on E9:
        # Open, Pedal A, Pedal B, Pedals A+B, LKL (F Lever), LKR (D Lever)
        stances: List[Tuple[str, Set[str]]] = [
            ("Open", set()),
            ("A Pedal", {"P1"}),
            ("B Pedal", {"P2"}),
            ("A & B", {"P1", "P2"}),
            ("F Lever", {"LKL"}),
            ("D Lever", {"LKR"}),
        ]

        # Scan each fret 0 to max_fret
        for fret in range(0, max_fret + 1):
            for stance_name, ctrls in stances:
                # Calculate sounding pitch on string_pair[0] and string_pair[1]
                # E9 Standard open pitches (MIDI): Str 3 = G#4 (68), Str 4 = E4 (64), Str 5 = B3 (59), Str 8 = E3 (52)
                p1_base = cls._get_e9_string_base_midi(string_pair[0]) + fret
                p2_base = cls._get_e9_string_base_midi(string_pair[1]) + fret

                p1_pitch = p1_base + cls._get_controller_delta(string_pair[0], ctrls)
                p2_pitch = p2_base + cls._get_controller_delta(string_pair[1], ctrls)

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
    def _get_e9_string_base_midi(str_num: int) -> int:
        open_e9 = {
            1: 66,  # F#4
            2: 63,  # D#4
            3: 68,  # G#4
            4: 64,  # E4
            5: 59,  # B3
            6: 56,  # G#3
            7: 54,  # F#3
            8: 52,  # E3
            9: 50,  # D3
            10: 47, # B2
        }
        return open_e9.get(str_num, 60)

    @staticmethod
    def _get_controller_delta(str_num: int, controllers: Set[str]) -> int:
        delta = 0
        if "P1" in controllers and str_num in (5, 10):
            delta += 2  # Pedal A raises B to C#
        if "P2" in controllers and str_num in (3, 6):
            delta += 1  # Pedal B raises G# to A
        if "LKL" in controllers and str_num in (4, 8):
            delta += 1  # F Lever raises E to F
        if "LKR" in controllers and str_num in (4, 8):
            delta -= 1  # D Lever lowers E to Eb
        return delta

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