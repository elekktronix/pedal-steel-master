"""Harmonic reverse-detection engine to identify chord voicings, Franklin string groups,
and inversions from pitch and string sets.
"""

from typing import Dict, List, Optional, Set, Tuple
from core.theory import CHORD_FORMULAS, CHORD_SYMBOL_SUFFIX, NOTE_TO_SEMITONE, spell_pc

FRANKLIN_GROUPS: Dict[Tuple[int, ...], str] = {
    (3, 4, 5): "Group 1",
    (4, 5, 6): "Group 2",
    (5, 6, 8): "Group 3",
    (6, 8, 10): "Group 4",
}


# Tie-break between equally ranked readings: the one whose bass is its root, then its third, then
# its fifth wins. So C-E-G-A over E or G reads C6 and F-A-C-D over A reads F6: the same rule in
# every key, not the lowest root pitch class (B10).
_BASS_RANK = {0: 0, 3: 1, 4: 1, 6: 2, 7: 2, 8: 2}


def _bass_rank(root_pc: int, bass_pc: int) -> int:
    return _BASS_RANK.get((bass_pc - root_pc) % 12, 3)


# Preferred order for the generic fallback (chords the hand-written table does not cover, B10).
_FALLBACK_ORDER = ["Dominant 9th", "Major 9th", "Minor 9th", "6/9", "Dominant 7th", "Major 7th",
                   "Minor 7th", "Major 6th", "Minor 6th"]


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
        """(display tag, family) for the canvas and inspector. The tag is for display only; code
        that needs the chord should call `identify_chord` instead (Critical Rule 18, A1)."""
        best = cls._best(pitches, bass_pitch, show_inversion, grip_strings)
        return (best[0], best[1]) if best else None

    @classmethod
    def identify_chord(cls, pitches: List[int], bass_pitch: int) -> Optional[Tuple[str, str]]:
        """(root name, family) as data: the root spelled by the global preference, the family a
        CHORD_FORMULAS key or "Dyad". Never parse the display tag for this (A1)."""
        best = cls._best(pitches, bass_pitch, False, None)
        return (best[2], best[1]) if best else None

    @classmethod
    def _best(
        cls,
        pitches: List[int],
        bass_pitch: int,
        show_inversion: bool,
        grip_strings: Optional[Set[int]],
    ) -> Optional[Tuple[str, str, str]]:
        """(display tag, family, root name) of the best reading, or None."""
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
                candidates.append((10 + bass_bonus, f"{root_name}6{group_tag}{inv_str}", "Major 6th", root_name))
            elif semitones == {0, 3, 7, 9}:
                candidates.append((10 + bass_bonus, f"{root_name}m6", "Minor 6th", root_name))
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
            return cls._identify_generic(pitch_classes, bass_pc, inv_root=show_inversion)

        # Priority first; ties go to the reading whose bass is its root, third, then fifth (B10).
        candidates.sort(key=lambda c: (-c[0], _bass_rank(NOTE_TO_SEMITONE[c[3]], bass_pc)))
        best = candidates[0]
        return (best[1], best[2], best[3])

    @classmethod
    def _identify_generic(cls, pitch_classes: List[int], bass_pc: int,
                          inv_root: bool = True) -> Optional[Tuple[str, str, str]]:
        """Fallback for chords the table above does not list (e.g. 5-note G9, C6/9): match the pitch
        classes against CHORD_FORMULAS, exact sets before ones missing only the 5th. Roots are tried
        bass first. The family is always a CHORD_FORMULAS key (Critical Rule 18)."""
        pcs = set(pitch_classes)
        if len(pcs) < 4:
            return None
        roots = ([bass_pc] if bass_pc in pcs else []) + sorted(pc for pc in pcs if pc != bass_pc)
        types = [t for t in _FALLBACK_ORDER if t in CHORD_FORMULAS]
        types += [t for t in CHORD_FORMULAS if t not in types]
        for exact in (True, False):
            for rpc in roots:
                for ctype in types:
                    tones = {(rpc + k) % 12 for k in CHORD_FORMULAS[ctype]}
                    if (exact and tones == pcs) or (not exact and pcs < tones and tones - pcs == {(rpc + 7) % 12}):
                        name = spell_pc(rpc)
                        inv = cls.get_inversion_label(rpc, bass_pc) if inv_root and rpc != bass_pc else ""
                        tag = f"{name}{CHORD_SYMBOL_SUFFIX.get(ctype, '')}" + (f" [{inv}]" if inv else "")
                        return tag, ctype, name
        return None