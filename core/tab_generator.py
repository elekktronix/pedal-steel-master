"""ASCII Tablature Generator with pedal/lever annotations and Franklin T-I-M pick notation."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class TabStep:
    fret: int
    engaged_levers: List[str] = field(default_factory=list)
    grip_strings: Set[int] = field(default_factory=set)
    chord_label: str = ""
    pick_finger: Optional[str] = None  # "T", "I", "M", or None for pinch block


class TabGenerator:
    @classmethod
    def assign_pick_finger(cls, string_num: int, all_strings: List[int]) -> str:
        """Assigns Thumb (T), Index (I), or Middle (M) pick based on physical string position."""
        sorted_strs = sorted(all_strings)  # Lowest string number is highest physical pitch
        if len(sorted_strs) <= 1:
            return "T" if string_num >= 6 else "I"

        idx = sorted_strs.index(string_num)
        # Lowest 1-2 strings get Thumb, middle gets Index, top gets Middle
        if idx >= len(sorted_strs) - 1 and len(sorted_strs) >= 3:
            return "T"
        elif idx == 0:
            return "M"
        else:
            return "I"

    @classmethod
    def generate_ascii_tab(
        cls,
        string_count: int,
        steps: List[TabStep],
        steps_per_system: int = 8,
        include_picks: bool = True,
    ) -> str:
        """Generates formatted ASCII tablature with Chord Header, Pick Row, String Lines, and Pedal Footer."""
        if not steps:
            return "No steps captured."

        lines: List[str] = []
        total_steps = len(steps)

        for sys_idx in range(0, total_steps, steps_per_system):
            chunk = steps[sys_idx : sys_idx + steps_per_system]
            col_width = 12

            # 1. Chord & Nashville Label Header
            chord_line = "Chord: "
            for s in chunk:
                lbl = s.chord_label if s.chord_label else ""
                chord_line += f"{lbl:<{col_width}}"
            lines.append(chord_line)

            # 2. Franklin T-I-M Pick Assignment Line
            if include_picks:
                pick_line = "Pick:  "
                for s in chunk:
                    if s.pick_finger:
                        f_str = s.pick_finger
                    elif len(s.grip_strings) > 1:
                        f_str = "Pinch"
                    elif len(s.grip_strings) == 1:
                        f_str = cls.assign_pick_finger(list(s.grip_strings)[0], list(s.grip_strings))
                    else:
                        f_str = "-"
                    pick_line += f"{f_str:<{col_width}}"
                lines.append(pick_line)

            # 3. String Lines (1 down to string_count)
            for str_num in range(1, string_count + 1):
                s_prefix = f"{str_num:2d} |---"
                str_row = s_prefix
                for s in chunk:
                    if str_num in s.grip_strings:
                        cell = f"-{s.fret:<2d}-------"
                    else:
                        cell = "----------"
                    str_row += cell[:col_width]
                str_row += "|"
                lines.append(str_row)

            # 4. Pedals / Levers Footer Line
            pedal_line = "Ped:   "
            for s in chunk:
                lev_str = "+".join(s.engaged_levers) if s.engaged_levers else ""
                pedal_line += f"{lev_str:<{col_width}}"
            lines.append(pedal_line)
            lines.append("")

        return "\n".join(lines)