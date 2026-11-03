"""Circle of Fifths harmonic theory and key relationship mappings."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

CIRCLE_KEYS_CLOCKWISE = ["C", "G", "D", "A", "E", "B", "F#", "Db", "Ab", "Eb", "Bb", "F"]

# Relative minor for each major key slice
RELATIVE_MINORS = {
    "C": "A", "G": "E", "D": "B", "A": "F#",
    "E": "C#", "B": "G#", "F#": "D#", "Db": "Bb",
    "Ab": "F", "Eb": "C", "Bb": "G", "F": "D",
}

# Diatonic scale intervals and chord types for standard major keys
DIATONIC_ROLES = [
    ("I", 0, "Major"),
    ("ii", 2, "Minor"),
    ("iii", 4, "Minor"),
    ("IV", 5, "Major"),
    ("V", 7, "Major"),
    ("vi", 9, "Minor"),
    ("vii°", 11, "Diminished"),
]

# Semitone offsets for calculating root names
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
SEMITONE_TO_SHARP = {
    0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E", 5: "F",
    6: "F#", 7: "G", 8: "G#", 9: "A", 10: "A#", 11: "B",
}
SEMITONE_TO_FLAT = {
    0: "C", 1: "Db", 2: "D", 3: "Eb", 4: "E", 5: "F",
    6: "Gb", 7: "G", 8: "Ab", 9: "A", 10: "Bb", 11: "B",
}


@dataclass
class DiatonicChordInfo:
    role: str          # "I", "IV", "V", etc.
    root_name: str     # "G", "C", "D"
    chord_type: str    # "Major", "Minor", "Diminished"
    label: str         # "G (I)", "C (IV)"


class CircleOfFifthsEngine:
    @classmethod
    def get_diatonic_chords(cls, key_center: str) -> List[DiatonicChordInfo]:
        """Returns the 7 diatonic family chords for a given major key center."""
        from core.theory import NOTE_TO_SEMITONE

        if key_center not in NOTE_TO_SEMITONE:
            key_center = "C"

        root_pc = NOTE_TO_SEMITONE[key_center]
        prefer_flat = key_center in {"F", "Bb", "Eb", "Ab", "Db"}
        naming_table = SEMITONE_TO_FLAT if prefer_flat else SEMITONE_TO_SHARP

        chords = []
        for role, semitone_offset, c_type in DIATONIC_ROLES:
            chord_pc = (root_pc + semitone_offset) % 12
            chord_root = naming_table[chord_pc]
            chords.append(
                DiatonicChordInfo(
                    role=role,
                    root_name=chord_root,
                    chord_type=c_type,
                    label=f"{chord_root} ({role})",
                )
            )
        return chords