"""Links between scales and chords (E-31): the chords built inside a scale, and the scales that
contain a chord. Pure pitch-class theory; fretboard positions come from the resolver-backed
engines (scale_engine, chord_atlas)."""

from dataclasses import dataclass
from typing import FrozenSet, List, Optional

from core.theory import CHORD_FORMULAS, CHORD_SYMBOL_SUFFIX, NOTE_TO_SEMITONE, SCALE_FORMULAS, spell_pc

TRIAD_TYPES = ("Major", "Minor", "Diminished", "Augmented")
SEVENTH_TYPES = ("Major 7th", "Dominant 7th", "Minor 7th", "Half-Diminished", "Diminished 7th")

_ROMAN = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V", "6": "VI", "7": "VII"}
_LOWER = {"Minor", "Diminished", "Minor 7th", "Half-Diminished", "Diminished 7th"}
_NUMERAL_SUFFIX = {
    "Diminished": "°", "Augmented": "+", "Major 7th": "maj7", "Dominant 7th": "7",
    "Minor 7th": "7", "Half-Diminished": "ø7", "Diminished 7th": "°7",
}


@dataclass(frozen=True)
class ScaleChord:
    root_pc: int
    root_name: str          # spelled with the user's preference
    chord_type: str         # a CHORD_FORMULAS key
    degree: str             # scale degree of the chord root ("1", "b3", ...)
    numeral: str            # "I", "ii", "bIII", "vii°", "V7", "iiø7"
    symbol: str             # "G", "Am", "F#dim", "D7"
    pcs: FrozenSet[int]     # pitch classes of the chord tones

    @property
    def is_seventh(self) -> bool:
        return self.chord_type in SEVENTH_TYPES


@dataclass(frozen=True)
class ChordScale:
    root_name: str
    scale_name: str
    chord_degree: str       # degree of the chord root inside this scale
    extra_notes: int        # scale notes that are not chord tones (fewer = closer fit)


def _pcs(root_pc: int, formula) -> FrozenSet[int]:
    return frozenset((root_pc + semis) % 12 for semis in formula)


def roman_numeral(degree: str, chord_type: str) -> str:
    acc = degree[:-1] if degree[-1:].isdigit() else ""
    base = _ROMAN.get(degree[-1:], degree)
    base = base.lower() if chord_type in _LOWER else base
    return f"{acc}{base}{_NUMERAL_SUFFIX.get(chord_type, '')}"


def chord_symbol(root_name: str, chord_type: str) -> str:
    return f"{root_name}{CHORD_SYMBOL_SUFFIX.get(chord_type, '')}"


def chords_in_scale(root_name: str, scale_name: str, sevenths: Optional[bool] = None) -> List[ScaleChord]:
    """Every triad (and seventh chord) whose tones all belong to the scale, rooted on a scale degree,
    in degree order. sevenths=None returns both, True only sevenths, False only triads."""
    root_pc = NOTE_TO_SEMITONE.get(root_name)
    formula = SCALE_FORMULAS.get(scale_name)
    if root_pc is None or formula is None:
        return []
    scale_pcs = _pcs(root_pc, formula)
    types = (TRIAD_TYPES if sevenths is not True else ()) + (SEVENTH_TYPES if sevenths is not False else ())
    out: List[ScaleChord] = []
    for semis in sorted(formula):
        degree = formula[semis]
        pc = (root_pc + semis) % 12
        for ctype in types:
            pcs = _pcs(pc, CHORD_FORMULAS[ctype])
            if pcs <= scale_pcs:
                name = spell_pc(pc)
                out.append(ScaleChord(pc, name, ctype, degree, roman_numeral(degree, ctype),
                                      chord_symbol(name, ctype), pcs))
    return out


def scales_for_chord(root_name: str, chord_type: str) -> List[ChordScale]:
    """Every (root, scale) whose notes include all the chord's tones. Scales on the chord's own root
    come first, then the closest fits (fewest notes beyond the chord)."""
    root_pc = NOTE_TO_SEMITONE.get(root_name)
    formula = CHORD_FORMULAS.get(chord_type)
    if root_pc is None or formula is None:
        return []
    chord_pcs = _pcs(root_pc, formula)
    found = []
    for scale_root in range(12):
        for scale_name, sformula in SCALE_FORMULAS.items():
            spcs = _pcs(scale_root, sformula)
            if chord_pcs <= spcs:
                degree = sformula[(root_pc - scale_root) % 12]
                found.append(ChordScale(spell_pc(scale_root), scale_name, degree, len(spcs - chord_pcs)))
    order = list(SCALE_FORMULAS)
    found.sort(key=lambda c: (c.chord_degree != "1", c.extra_notes, order.index(c.scale_name), c.root_name))
    return found
