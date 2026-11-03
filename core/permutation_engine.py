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


# The 24 Mathematical Right-Hand Picking Permutations (Franklin, pp. 37-39)
FRANKLIN_24_PERMUTATIONS: Dict[int, Tuple[str, str, Tuple[str, str, str, str]]] = {
    1:  ("T - T - I - M", "Thumb Double-Tap Start", ("T", "T", "I", "M")),
    2:  ("T - I - M - T", "Standard Forward Roll",   ("T", "I", "M", "T")),
    3:  ("I - M - T - T", "Inside-Out Drag",         ("I", "M", "T", "T")),
    4:  ("M - T - I - M", "Middle Lead Cross-Pick",  ("M", "T", "I", "M")),
    5:  ("M - M - I - T", "Middle Double-Tap",       ("M", "M", "I", "T")),
    6:  ("M - I - T - M", "Outside-In Roll",         ("M", "I", "T", "M")),
    7:  ("I - T - M - I", "Index Lead Interlock",    ("I", "T", "M", "I")),
    8:  ("T - M - I - T", "Thumb-Middle Pinch Jump", ("T", "M", "I", "T")),
    9:  ("M - T - I - T", "Bounce Alternation",      ("M", "T", "I", "T")),
    10: ("I - M - T - M", "Gallop Inversion",        ("I", "M", "T", "M")),
    11: ("M - T - M - T", "Strict Tremolo Rock",     ("M", "T", "M", "T")),
    12: ("T - M - T - I", "Syncopated Pivot",        ("T", "M", "T", "I")),
    13: ("T - M - T - M", "Pendulum Pivot",          ("T", "M", "T", "M")),
    14: ("M - T - M - I", "Reverse Pendulum",        ("M", "T", "M", "I")),
    15: ("T - M - I - M", "Double-Middle Roll",      ("T", "M", "I", "M")),
    16: ("I - T - M - T", "Stride Interlock",        ("I", "T", "M", "T")),
    17: ("M - I - T - I", "Double-Index Bounce",     ("M", "I", "T", "I")),
    18: ("M - T - I - M", "Outside Cycle",           ("M", "T", "I", "M")),
    19: ("T - I - M - M", "Inside Double-Middle",    ("T", "I", "M", "M")),
    20: ("T - M - I - T", "Reverse Cross Jump",      ("T", "M", "I", "T")),
    21: ("T - I - M - T", "Forward Cycle Anchor",    ("T", "I", "M", "T")),
    22: ("I - M - I - T", "Index Alternate Bounce",  ("I", "M", "I", "T")),
    23: ("M - I - T - M", "Rapid Middle Return",     ("M", "I", "T", "M")),
    24: ("I - T - T - M", "Inside Thumb Split",      ("I", "T", "T", "M")),
}

# Standard string assignment mapping for a 4-string group (e.g., 4, 5, 6, 8)
# Low string to high string: Thumb handles lowest two, Index middle, Middle top[cite: 16]
FINGER_TO_STRING_OFFSET: Dict[str, int] = {
    "T": 0,  # Lower bass strings
    "I": 2,  # Middle string
    "M": 3,  # Top string
}


class PermutationEngine:
    @classmethod
    def get_permutation_info(cls, perm_id: int) -> Tuple[str, str, Tuple[str, str, str, str]]:
        return FRANKLIN_24_PERMUTATIONS.get(
            perm_id, ("T - I - M - T", "Standard Forward Roll", ("T", "I", "M", "T"))
        )

    @classmethod
    def generate_sequence(
        cls,
        perm_id: int,
        target_strings: List[int],
        cycles: int = 4,
    ) -> List[PickEvent]:
        """Generates sequential picking events assigning fingers to physical strings."""
        if len(target_strings) < 4:
            # Fallback if grip has fewer than 4 strings
            sorted_strs = sorted(target_strings)
            while len(sorted_strs) < 4:
                sorted_strs.append(sorted_strs[-1])
        else:
            sorted_strs = sorted(target_strings)[:4]

        # sorted_strs[0] is lowest string (highest number e.g. 8)
        # sorted_strs[3] is highest string (lowest number e.g. 4)
        _, _, pattern = cls.get_permutation_info(perm_id)

        events: List[PickEvent] = []
        step_counter = 0

        for cycle in range(cycles):
            for beat_idx, finger in enumerate(pattern):
                # Map finger to relative string within the 4-string pocket
                if finger == "T":
                    # Alternate thumb between lowest and second-lowest string if consecutive
                    if beat_idx > 0 and pattern[beat_idx - 1] == "T":
                        str_num = sorted_strs[1]
                    else:
                        str_num = sorted_strs[0]
                elif finger == "I":
                    str_num = sorted_strs[2]
                else:  # "M"
                    str_num = sorted_strs[3]

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