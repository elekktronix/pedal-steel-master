"""Harmonic reverse-detection engine to identify chord voicings, Franklin string groups,
and inversions from pitch and string sets.
"""

from typing import Dict, List, Optional, Set, Tuple
from core.theory import NOTE_TO_SEMITONE, spell_pc

FRANKLIN_GROUPS: Dict[Tuple[int, ...], str] = {
    (3, 4, 5): "Group 1",
    (4, 5, 6): "Group 2",
    (5, 6, 8): "Group 3",
    (6, 8, 10): "Group 4",
}


class ChordIdentifier:
    @classmethod
    def get_inversion_label(cls, root_pc: int, bass_pc: int) -> str:
        if root_pc == bass_pc:
            return "Root Position (1-3-5)"

        bass_interval = (bass_pc - root_pc) % 12
        if bass_interval in (3, 4):
            return "1st Inversion (3-5-1)" if bass_interval == 4 else "1st Inversion (b3-5-1)"
        elif bass_interval in (6, 7, 8):
            return "2nd Inversion (5-1-3)" if bass_interval == 7 else "2nd Inversion (5-1-b3)"
        elif bass_interval in (9, 10, 11):
            return "3rd Inversion (7th in Bass)"
        return "Inversion"

    @classmethod
    def identify_voicing(
        cls,
        pitches: List[int],
        bass_pitch: int,
        show_inversion: bool = True,
        grip_strings: Optional[Set[int]] = None,
    ) -> Optional[Tuple[str, str]]:
        if not pitches:
            return None

        pitch_classes = sorted(list({p % 12 for p in pitches}))
        bass_pc = bass_pitch % 12

        # Detect Franklin Foundation Group
        group_tag = ""
        if grip_strings:
            sorted_strings = tuple(sorted(grip_strings))
            if sorted_strings in FRANKLIN_GROUPS:
                group_tag = f" • {FRANKLIN_GROUPS[sorted_strings]}"

        candidates: List[Tuple[int, str, str, str]] = []  # (priority, display_tag, chord_type, root_name)

        for root_pc in range(12):
            root_name = spell_pc(root_pc)  # display spelling follows the global preference
            semitones = {(pc - root_pc) % 12 for pc in pitch_classes}

            # A chord MUST contain its root (0) to be identified with this root
            if 0 not in semitones:
                continue

            inv = cls.get_inversion_label(root_pc, bass_pc) if show_inversion else ""
            inv_str = f" [{inv}]" if inv else ""
            is_root_in_bass = (bass_pc == root_pc)
            bass_bonus = 2 if is_root_in_bass else 0

            # 1. Exact 4-Note Chords
            if semitones == {0, 4, 7, 11}:
                candidates.append((10 + bass_bonus, f"{root_name}maj7{group_tag}{inv_str}", "Major 7th", root_name))
            elif semitones == {0, 3, 7, 10}:
                candidates.append((10 + bass_bonus, f"{root_name}m7{group_tag}{inv_str}", "Minor 7th", root_name))
            elif semitones == {0, 4, 7, 10}:
                candidates.append((10 + bass_bonus, f"{root_name}7{group_tag}{inv_str}", "Dominant 7th", root_name))
            elif semitones == {0, 4, 7, 9}:
                inv_6 = "Root (R)" if is_root_in_bass else "Inversion"
                candidates.append((10 + bass_bonus, f"{root_name}6 • {inv_6}", "Major 6", root_name))
            elif semitones == {0, 3, 7, 9}:
                candidates.append((10 + bass_bonus, f"{root_name}m6", "Minor 6", root_name))
            elif semitones == {0, 3, 6, 10}:
                candidates.append((10 + bass_bonus, f"{root_name}m7b5", "Half-Diminished", root_name))
            elif semitones == {0, 3, 6, 9}:
                candidates.append((10 + bass_bonus, f"{root_name}dim7", "Diminished 7th", root_name))

            # 2. Exact 3-Note Triads (Highest priority for 3-note grips)
            elif semitones == {0, 4, 7}:
                candidates.append((8 + bass_bonus, f"{root_name} Maj{group_tag}{inv_str}", "Major", root_name))
            elif semitones == {0, 3, 7}:
                candidates.append((8 + bass_bonus, f"{root_name}m{group_tag}{inv_str}", "Minor", root_name))
            elif semitones == {0, 3, 6}:
                candidates.append((8 + bass_bonus, f"{root_name}dim", "Diminished", root_name))
            elif semitones == {0, 4, 8}:
                candidates.append((8 + bass_bonus, f"{root_name}aug", "Augmented", root_name))
            elif semitones == {0, 5, 7}:
                candidates.append((8 + bass_bonus, f"{root_name}sus4", "Sus4", root_name))

            # 3. 3-Note Shell 7ths (Where root is present)
            elif semitones == {0, 3, 10}:
                candidates.append((6 + bass_bonus, f"{root_name}m7{group_tag}{inv_str}", "Minor 7th", root_name))
            elif semitones == {0, 4, 10}:
                candidates.append((6 + bass_bonus, f"{root_name}7{group_tag}{inv_str}", "Dominant 7th", root_name))
            elif semitones == {0, 4, 11}:
                candidates.append((6 + bass_bonus, f"{root_name}maj7{group_tag}{inv_str}", "Major 7th", root_name))

            # 4. 2-Note Dyads
            elif semitones == {0, 7}:
                candidates.append((4 + bass_bonus, f"{root_name} (5th Dyad)", "Dyad", root_name))
            elif semitones == {0, 4}:
                candidates.append((4 + bass_bonus, f"{root_name} (3rd Dyad)", "Dyad", root_name))
            elif semitones == {0, 3}:
                candidates.append((4 + bass_bonus, f"{root_name}m (b3 Dyad)", "Dyad", root_name))

        if not candidates:
            return None

        # Sort by priority score (descending)
        candidates.sort(key=lambda c: c[0], reverse=True)
        best = candidates[0]
        return (best[1], best[2])