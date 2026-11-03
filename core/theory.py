"""Music theory primitives for pitch, intervals, chord formulas, and scale formulas."""

from typing import Dict, List, Optional, Tuple

NOTE_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

NOTE_TO_SEMITONE: Dict[str, int] = {
    "C": 0, "B#": 0,
    "C#": 1, "Db": 1,
    "D": 2,
    "D#": 3, "Eb": 3,
    "E": 4, "Fb": 4,
    "F": 5, "E#": 5,
    "F#": 6, "Gb": 6,
    "G": 7,
    "G#": 8, "Ab": 8,
    "A": 9,
    "A#": 10, "Bb": 10,
    "B": 11, "Cb": 11,
}

INTERVAL_MAP: Dict[int, str] = {
    0: "R",
    1: "b9",
    2: "9",
    3: "b3",
    4: "3",
    5: "11",
    6: "b5",
    7: "5",
    8: "#5",
    9: "6",
    10: "b7",
    11: "7",
}

CHORD_FORMULAS: Dict[str, Dict[int, str]] = {
    "Major": {0: "R", 4: "3", 7: "5"},
    "Minor": {0: "R", 3: "b3", 7: "5"},
    "Dominant 7th": {0: "R", 4: "3", 7: "5", 10: "b7"},
    "Major 7th": {0: "R", 4: "3", 7: "5", 11: "7"},
    "Minor 7th": {0: "R", 3: "b3", 7: "5", 10: "b7"},
    "Major 6th": {0: "R", 4: "3", 7: "5", 9: "6"},
    "Minor 6th": {0: "R", 3: "b3", 7: "5", 9: "6"},
    "Dominant 9th": {0: "R", 2: "9", 4: "3", 7: "5", 10: "b7"},
    "Diminished": {0: "R", 3: "b3", 6: "b5"},
    "Diminished 7th": {0: "R", 3: "b3", 6: "b5", 9: "bb7"},
    "Augmented": {0: "R", 4: "3", 8: "#5"},
    "Sus4": {0: "R", 5: "4", 7: "5"},
    "Half-Diminished": {0: "R", 3: "b3", 6: "b5", 10: "b7"},
    "6/9": {0: "R", 2: "9", 4: "3", 7: "5", 9: "6"},
}

# Standard scale formulas mapping semitone offset -> scale degree label
SCALE_FORMULAS: Dict[str, Dict[int, str]] = {
    "Major (Ionian)": {0: "1", 2: "2", 4: "3", 5: "4", 7: "5", 9: "6", 11: "7"},
    "Major Pentatonic": {0: "1", 2: "2", 4: "3", 7: "5", 9: "6"},
    "Country / Major Blues": {0: "1", 2: "2", 3: "b3", 4: "3", 7: "5", 9: "6"},
    "Mixolydian (Dominant)": {0: "1", 2: "2", 4: "3", 5: "4", 7: "5", 9: "6", 10: "b7"},
    "Natural Minor (Aeolian)": {0: "1", 2: "2", 3: "b3", 5: "4", 7: "5", 8: "b6", 10: "b7"},
    "Minor Pentatonic": {0: "1", 3: "b3", 5: "4", 7: "5", 10: "b7"},
    "Minor Blues": {0: "1", 3: "b3", 5: "4", 6: "b5", 7: "5", 10: "b7"},
    "Dorian": {0: "1", 2: "2", 3: "b3", 5: "4", 7: "5", 9: "6", 10: "b7"},
    "Harmonic Minor": {0: "1", 2: "2", 3: "b3", 5: "4", 7: "5", 8: "b6", 11: "7"},
    "Melodic Minor (Jazz)": {0: "1", 2: "2", 3: "b3", 5: "4", 7: "5", 9: "6", 11: "7"},
    "Bebop Dominant": {0: "1", 2: "2", 4: "3", 5: "4", 7: "5", 9: "6", 10: "b7", 11: "7"},
    "Whole Tone": {0: "1", 2: "2", 4: "3", 6: "#4", 8: "#5", 10: "b7"},
}

NASHVILLE_SCALE_DEGREES: Dict[int, str] = {
    0: "1",
    1: "b2",
    2: "2",
    3: "b3",
    4: "3",
    5: "4",
    6: "b5",
    7: "5",
    8: "b6",
    9: "6",
    10: "b7",
    11: "7",
}


def extract_root_and_quality(chord_label: str) -> Tuple[str, str]:
    """Safely extracts the root note (e.g., 'C#', 'Bb', 'E') and remaining quality string."""
    clean = chord_label.strip()
    if not clean:
        return ("", "")

    # Match two-character roots first ('C#', 'Bb', etc.), then single characters
    for r in sorted(NOTE_TO_SEMITONE.keys(), key=len, reverse=True):
        if clean.startswith(r):
            return (r, clean[len(r):].strip())

    return ("", "")


# Chord family (CHORD_FORMULAS key / ChordIdentifier family) -> Nashville quality suffix
_NASHVILLE_FAMILY_SUFFIX: Dict[str, str] = {
    "Major": "", "Major 7th": "", "Major 6th": "", "Major 6": "", "6/9": "", "Dyad": "",
    "Minor": "-", "Minor 7th": "-", "Minor 6th": "-", "Minor 6": "-",
    "Dominant 7th": "⁷", "Dominant 9th": "⁷",
    "Diminished": "°", "Diminished 7th": "°",
    "Half-Diminished": "ø",
    "Augmented": "+",
    "Sus4": "sus",
}


def _quality_suffix_from_text(quality: str) -> str:
    """Parses a chord quality string ('m7', 'Maj • Group 2', 'Dominant 7th', 'dim7', ...)."""
    q = quality.split("•")[0].split("[")[0].strip().lower()
    if q.startswith(("maj", "major", "Δ")):
        return ""
    if q.startswith(("m7b5", "half", "ø")):
        return "ø"
    if q.startswith(("dim", "°")):
        return "°"
    if q.startswith(("aug", "+")):
        return "+"
    if q.startswith("sus"):
        return "sus"
    if q.startswith(("min", "m", "-")):
        return "-"
    if q.startswith(("dom", "7", "9", "11", "13")):
        return "⁷"
    return ""


def get_nashville_chord_symbol(chord_label: str, key_root: str, family: Optional[str] = None) -> str:
    """Nashville Number symbol (e.g. '1', '2-', '5⁷', '7°') for a chord relative to a key.

    Pass `family` (a CHORD_FORMULAS key or ChordIdentifier family) when known; otherwise the
    quality is parsed from the label text after the root.
    """
    if not chord_label or not key_root or key_root not in NOTE_TO_SEMITONE:
        return ""

    root, quality = extract_root_and_quality(chord_label)
    if not root or root not in NOTE_TO_SEMITONE:
        return ""

    semitone_delta = (NOTE_TO_SEMITONE[root] - NOTE_TO_SEMITONE[key_root]) % 12
    base_degree = NASHVILLE_SCALE_DEGREES.get(semitone_delta, str(semitone_delta + 1))

    if family is not None and family in _NASHVILLE_FAMILY_SUFFIX:
        suffix = _NASHVILLE_FAMILY_SUFFIX[family]
    else:
        suffix = _quality_suffix_from_text(quality)
    return f"{base_degree}{suffix}"


def to_root_name(name: Optional[str], spellings: List[str] = NOTE_NAMES_SHARP) -> Optional[str]:
    """Respells any enharmonic root ('Db', 'C#', 'B#') into the given spelling list, or None."""
    if not name:
        return None
    pc = NOTE_TO_SEMITONE.get(name.strip()[:1].upper() + name.strip()[1:])
    if pc is None:
        return None
    for candidate in spellings:
        if NOTE_TO_SEMITONE.get(candidate) == pc:
            return candidate
    return None


def note_to_midi(name: str, octave: int) -> int:
    clean_name = name.strip().capitalize()
    if clean_name not in NOTE_TO_SEMITONE:
        raise ValueError(f"Invalid note name: {name}")
    return (octave + 1) * 12 + NOTE_TO_SEMITONE[clean_name]


def midi_to_note_name(midi: int, prefer_flat: bool = False) -> str:
    pitch_class = midi % 12
    octave = (midi // 12) - 1
    table = NOTE_NAMES_FLAT if prefer_flat else NOTE_NAMES_SHARP
    return f"{table[pitch_class]}{octave}"


def get_pitch_class(midi: int) -> int:
    return midi % 12


def get_interval(root_midi_or_pc: int, note_midi_or_pc: int) -> int:
    return (note_midi_or_pc - root_midi_or_pc) % 12