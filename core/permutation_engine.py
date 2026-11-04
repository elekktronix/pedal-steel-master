"""Paul Franklin's 24 Right-Hand Picking Permutations & Blocking Engine."""

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class PickEvent:
    step_index: int
    string_number: int
    finger: str          # "T" (Thumb), "I" (Index), "M" (Middle)
    note_name: str = ""
    is_downbeat: bool = False


# Paul Franklin's 24 picking permutations, transcribed from the chart in "Intervals" (p. 38) and the
# course handout (D-36). Each one plays the 4 strings of a group once each, in a different order:
# (fingering, book notes, fingers, order). The book demonstrates them on E9 strings 8-7-6-5 open
# (E F# G# B); `order` gives the string positions within the group, 0 = lowest pitch .. 3 = highest.
# Fingerings repeat (e.g. #2 and #21 are both T-I-M-T); the note order is what makes each unique.
FRANKLIN_24_PERMUTATIONS: Dict[int, Tuple[str, str, Tuple[str, str, str, str], Tuple[int, int, int, int]]] = {
    1:  ("T - T - I - M", "E F# G# B",  ("T", "T", "I", "M"), (0, 1, 2, 3)),
    2:  ("T - I - M - T", "F# G# B E",  ("T", "I", "M", "T"), (1, 2, 3, 0)),
    3:  ("I - M - T - T", "G# B E F#",  ("I", "M", "T", "T"), (2, 3, 0, 1)),
    4:  ("M - T - I - M", "B E F# G#",  ("M", "T", "I", "M"), (3, 0, 1, 2)),
    5:  ("M - M - I - T", "B G# F# E",  ("M", "M", "I", "T"), (3, 2, 1, 0)),
    6:  ("M - I - T - M", "G# F# E B",  ("M", "I", "T", "M"), (2, 1, 0, 3)),
    7:  ("I - T - M - I", "F# E B G#",  ("I", "T", "M", "I"), (1, 0, 3, 2)),
    8:  ("T - M - I - T", "E B G# F#",  ("T", "M", "I", "T"), (0, 3, 2, 1)),
    9:  ("M - T - I - T", "B F# G# E",  ("M", "T", "I", "T"), (3, 1, 2, 0)),
    10: ("I - M - T - M", "F# G# E B",  ("I", "M", "T", "M"), (1, 2, 0, 3)),
    11: ("M - T - M - T", "G# E B F#",  ("M", "T", "M", "T"), (2, 0, 3, 1)),
    12: ("T - M - T - I", "E B F# G#",  ("T", "M", "T", "I"), (0, 3, 1, 2)),
    13: ("T - M - T - M", "F# B E G#",  ("T", "M", "T", "M"), (1, 3, 0, 2)),
    14: ("M - T - M - I", "B E G# F#",  ("M", "T", "M", "I"), (3, 0, 2, 1)),
    15: ("T - M - I - M", "E G# F# B",  ("T", "M", "I", "M"), (0, 2, 1, 3)),
    16: ("I - T - M - T", "G# F# B E",  ("I", "T", "M", "T"), (2, 1, 3, 0)),
    17: ("M - I - T - I", "B G# E F#",  ("M", "I", "T", "I"), (3, 2, 0, 1)),
    18: ("M - T - I - M", "G# E F# B",  ("M", "T", "I", "M"), (2, 0, 1, 3)),
    19: ("T - I - M - M", "E F# B G#",  ("T", "I", "M", "M"), (0, 1, 3, 2)),
    20: ("T - M - I - T", "F# B G# E",  ("T", "M", "I", "T"), (1, 3, 2, 0)),
    21: ("T - I - M - T", "E G# B F#",  ("T", "I", "M", "T"), (0, 2, 3, 1)),
    22: ("I - M - I - T", "G# B F# E",  ("I", "M", "I", "T"), (2, 3, 1, 0)),
    23: ("M - I - T - M", "B F# E G#",  ("M", "I", "T", "M"), (3, 1, 0, 2)),
    24: ("I - T - T - M", "F# E G# B",  ("I", "T", "T", "M"), (1, 0, 2, 3)),
}


class PermutationEngine:
    @classmethod
    def get_permutation_info(cls, perm_id: int) -> Tuple[str, str, Tuple[str, str, str, str], Tuple[int, int, int, int]]:
        return FRANKLIN_24_PERMUTATIONS.get(perm_id, FRANKLIN_24_PERMUTATIONS[1])

    @classmethod
    def generate_sequence(
        cls,
        perm_id: int,
        target_strings: List[int],
        cycles: int = 4,
    ) -> List[PickEvent]:
        """Generates sequential picking events assigning fingers to physical strings."""
        # String numbers grow toward the bass, so sort descending: index 0 = lowest pitch (D-13).
        bass_first = sorted(set(target_strings), reverse=True)
        if not bass_first:
            return []
        if len(bass_first) >= 4:
            sorted_strs = bass_first[:4]
        elif len(bass_first) == 3:
            sorted_strs = [bass_first[0], bass_first[0], bass_first[1], bass_first[2]]  # thumb stays on bass
        elif len(bass_first) == 2:
            sorted_strs = [bass_first[0], bass_first[0], bass_first[1], bass_first[1]]
        else:
            sorted_strs = bass_first * 4

        # sorted_strs[0] is the lowest-pitched string, sorted_strs[3] the highest (book: strings 8..5).
        _, _, pattern, order = cls.get_permutation_info(perm_id)

        events: List[PickEvent] = []
        step_counter = 0

        for cycle in range(cycles):
            for beat_idx, (finger, position) in enumerate(zip(pattern, order)):
                str_num = sorted_strs[position]
                events.append(
                    PickEvent(
                        step_index=step_counter,
                        string_number=str_num,
                        finger=finger,
                        is_downbeat=(beat_idx == 0),
                    )
                )
                step_counter += 1

        return events