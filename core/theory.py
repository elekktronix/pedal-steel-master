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


def get_nashville_chord_symbol(chord_label: str, key_root: str) -> str:
    """Calculates the Nashville Number symbol (e.g., '1', '2-', '4', '5', '5⁷', '6-')
    for any chord label relative to the parent key center.
    """
    if not chord_label or not key_root or key_root not in NOTE_TO_SEMITONE:
        return ""

    root, quality = extract_root_and_quality(chord_label)
    if not root or root not in NOTE_TO_SEMITONE:
        return ""

    semitone_delta = (NOTE_TO_SEMITONE[root] - NOTE_TO_SEMITONE[key_root]) % 12
    base_degree = NASHVILLE_SCALE_DEGREES.get(semitone_delta, str(semitone_delta + 1))

    q_lower = quality.lower()
    is_major = "maj" in q_lower or "major" in q_lower
    is_dim = "dim" in q_lower or "°" in q_lower
    is_half_dim = "m7b5" in q_lower or "ø" in q_lower
    is_dom7 = ("7" in q_lower or "dom" in q_lower or "9" in q_lower) and not is_major and "m" not in q_lower
    is_minor = ("min" in q_lower or "m" in q_lower or "-" in q_lower) and not is_major and not is_dom7 and not is_dim

    if is_dim:
        return f"{base_degree}°"
    elif is_half_dim:
        return f"{base_degree}ø"
    elif is_minor:
        return f"{base_degree}-"
    elif is_dom7:
        return f"{base_degree}⁷"
    else:
        return base_degree

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