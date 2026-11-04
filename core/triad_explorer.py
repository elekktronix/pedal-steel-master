"""Triads over a chord (E-19): Paul Franklin, "Intervals" pp. 20-28.

For a backing chord (e.g. G7) this lists the triads that work over it and what each one
sounds like:

- **Diatonic:** the triads of the chord's parent scale (Ionian for major, Mixolydian for
  dominant, Dorian for minor). Over G7 these are the C harmonized-scale triads, so Dm sounds like
  G9, F like G11, Am like G13sus4 (p. 24/26).
- **From the 3rd and 5th:** major, minor and diminished triads built on the chord's 3rd and
  5th (p. 28). Over G these give Gmaj7#5 (B), Gmaj7 (Bm), G7 (Bdim), Gmaj9 (D), G9 (Dm), G7b9 (Ddim).
- **Altered (dominant only):** the triads of the melodic minor a half-step above the root
  (p. 27). Over G7 these are the Ab melodic minor triads, e.g. Abm gives G7#5b9.

"Sounds like" is the smallest CHORD_FORMULAS type that contains the backing root, the implied
chord tones (the backing chord's 7th; its b3 if minor) and the triad. Dominant chords that
only fit an altered spelling get a composite name (G7b5#9). Anything else is shown as a
slash chord (C/G). Pure Python; finding grips on a neck goes through VoicingSolver/resolver.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from core.theory import (
    CHORD_FORMULAS,
    CHORD_SYMBOL_SUFFIX,
    NOTE_NAMES_FLAT,
    NOTE_NAMES_SHARP,
    NOTE_TO_SEMITONE,
    SCALE_FORMULAS,
    is_key_aware_spelling,
    spell_pc,
)

TRIAD_TYPES: Dict[str, Tuple[int, int, int]] = {
    "Major": (0, 4, 7),
    "Minor": (0, 3, 7),
    "Diminished": (0, 3, 6),
    "Augmented": (0, 4, 8),
}
_TRIAD_SUFFIX = {"Major": "", "Minor": "m", "Diminished": "dim", "Augmented": "aug"}

# Backing chord family per supported CHORD_FORMULAS type.
CHORD_FAMILY: Dict[str, str] = {
    "Major": "major", "Major 6th": "major", "Major 7th": "major", "Major 9th": "major", "6/9": "major",
    "Dominant 7th": "dominant", "Dominant 9th": "dominant", "Dominant 11th": "dominant",
    "Dominant 13th": "dominant", "Dominant 13sus4": "dominant", "Dominant 7b9": "dominant",
    "Dominant 7#9": "dominant", "Dominant 7b5": "dominant", "Dominant 7#5": "dominant",
    "Minor": "minor", "Minor 7th": "minor", "Minor 6th": "minor", "Minor 9th": "minor",
}
SUPPORTED_CHORD_TYPES = list(CHORD_FAMILY)

# family -> (parent scale, semitones from the chord root to that scale's relative major)
_PARENT_SCALE = {
    "major": ("Major (Ionian)", 0),
    "dominant": ("Mixolydian (Dominant)", 5),
    "minor": ("Dorian", 10),
}

# Interval names over the backing root, by family (the book's spellings).
_INTERVAL_NAMES = {
    "major": {0: "R", 1: "b9", 2: "9", 3: "b3", 4: "3", 5: "11", 6: "#11", 7: "5", 8: "#5", 9: "6", 10: "b7", 11: "7"},
    "dominant": {0: "R", 1: "b9", 2: "9", 3: "#9", 4: "3", 5: "11", 6: "b5", 7: "5", 8: "#5", 9: "13", 10: "b7", 11: "7"},
    "minor": {0: "R", 1: "b9", 2: "9", 3: "b3", 4: "3", 5: "11", 6: "b5", 7: "5", 8: "b13", 9: "6", 10: "b7", 11: "7"},
}

_FLAT_MAJOR_KEYS = {5, 10, 3, 8, 1, 6}  # F, Bb, Eb, Ab, Db, Gb
_ALTERATIONS = ((6, "b5"), (8, "#5"), (1, "b9"), (3, "#9"))
MAX_EXTRA_TONES = 2


@dataclass
class TriadOverChord:
    category: str                 # "Diatonic", "From the 3rd & 5th", "Altered"
    triad_root: str               # spelled for the key, e.g. "Ab"
    triad_type: str               # TRIAD_TYPES key (also a CHORD_FORMULAS key)
    triad_name: str               # "Abm"
    built_on: str                 # interval of the backing root the triad starts on, e.g. "b9"
    intervals: Tuple[str, str, str]  # triad tones (root, 3rd, 5th) as intervals of the backing root
    sounds_like: str              # "G7#5b9"
    sounds_like_type: Optional[str]  # CHORD_FORMULAS key when the sound has one, else None
    color: str                    # "Stable", "Sus (11)", "Altered", "Tension"
    source: str                   # "C harmonized scale", "Ab melodic minor", ...


def _spell(pc: int, flats: bool) -> str:
    if not is_key_aware_spelling():  # Preferences > Note Spelling: key-aware tools off
        return spell_pc(pc)
    return (NOTE_NAMES_FLAT if flats else NOTE_NAMES_SHARP)[pc % 12]


def _triad_type_of(pcs: Tuple[int, int, int]) -> Optional[str]:
    rel = tuple((p - pcs[0]) % 12 for p in pcs)
    return next((name for name, shape in TRIAD_TYPES.items() if shape == rel), None)


def _scale_triads(scale_root_pc: int, scale_name: str) -> List[Tuple[int, str]]:
    """Diatonic triads of a 7-note scale: [(triad root pc, triad type)] by degree."""
    steps = sorted(SCALE_FORMULAS[scale_name])
    out = []
    for i in range(len(steps)):
        pcs = tuple((scale_root_pc + steps[(i + k) % len(steps)]) % 12 for k in (0, 2, 4))
        ttype = _triad_type_of(pcs)
        if ttype:
            out.append((pcs[0], ttype))
    return out


def _name_sound(root_name: str, family: str, tones: Set[int]) -> Tuple[Optional[str], Optional[str]]:
    """(display name, CHORD_FORMULAS key) of the smallest chord type containing `tones`."""
    best = None
    for idx, (ctype, formula) in enumerate(CHORD_FORMULAS.items()):
        pcs = set(formula)
        if not tones <= pcs:
            continue
        if family == "dominant" and CHORD_FAMILY.get(ctype) != "dominant":
            continue  # over G7, Bbm is G7b5#9, not Gm7b5 (its b3 is really a #9)
        extra = len(pcs - tones)
        if extra > MAX_EXTRA_TONES:
            continue
        rank = (extra, CHORD_FAMILY.get(ctype) != family, idx)  # fewest extras, then same family
        if best is None or rank < best[0]:
            best = (rank, ctype)
    if best:
        ctype = best[1]
        return f"{root_name}{CHORD_SYMBOL_SUFFIX.get(ctype, ' ' + ctype)}", ctype
    if family == "dominant" and 10 in tones and 11 not in tones:
        alts = "".join(lbl for pc, lbl in _ALTERATIONS if pc in tones)
        if alts:
            return f"{root_name}7{alts}", None
    return None, None


def explore(root_name: str, chord_type: str) -> List[TriadOverChord]:
    """All triads over `root_name` `chord_type`, grouped by category. Empty if unsupported."""
    if root_name not in NOTE_TO_SEMITONE or chord_type not in CHORD_FAMILY:
        return []
    family = CHORD_FAMILY[chord_type]
    root_pc = NOTE_TO_SEMITONE[root_name]
    names = _INTERVAL_NAMES[family]
    formula = CHORD_FORMULAS[chord_type]

    implied = {0} | {pc for pc in formula if pc in (10, 11)}
    if family == "minor":
        implied.add(3)

    scale_name, to_parent = _PARENT_SCALE[family]
    parent_major_pc = (root_pc + to_parent) % 12
    if "#" in root_name:
        key_flats = False  # follow the backing root's own accidental (F#maj7 -> F# triads)
    elif "b" in root_name[1:]:
        key_flats = True
    else:
        key_flats = parent_major_pc in _FLAT_MAJOR_KEYS
    parent_major = _spell(parent_major_pc, key_flats)
    source_by_family = {
        "major": f"{parent_major} harmonized scale",
        "dominant": f"{parent_major} harmonized scale (Mixolydian)",
        "minor": f"{parent_major} harmonized scale (Dorian)",
    }

    candidates: List[Tuple[str, int, str, bool, str]] = []  # (category, pc, type, flats, source)
    for pc, ttype in _scale_triads(root_pc, scale_name):
        candidates.append(("Diatonic", pc, ttype, key_flats, source_by_family[family]))

    chord_third = 3 if 3 in formula and family == "minor" else 4
    for interval in (chord_third, 7):
        for ttype in ("Major", "Minor", "Diminished"):
            candidates.append(("From the 3rd & 5th", (root_pc + interval) % 12, ttype, key_flats,
                               f"{ttype.lower()} triad on the {names[interval]}"))

    if family == "dominant":
        mm_root = (root_pc + 1) % 12
        mm_name = _spell(mm_root, True)
        for pc, ttype in _scale_triads(mm_root, "Melodic Minor (Jazz)"):
            candidates.append(("Altered", pc, ttype, True, f"{mm_name} melodic minor"))

    results: List[TriadOverChord] = []
    seen: Set[Tuple[int, str]] = set()
    for category, pc, ttype, flats, source in candidates:
        if (pc, ttype) in seen:
            continue
        seen.add((pc, ttype))
        rel = tuple((pc + s - root_pc) % 12 for s in TRIAD_TYPES[ttype])
        tones = implied | set(rel)
        sound, sound_type = _name_sound(root_name, family, tones)
        triad_root = _spell(pc, flats)
        triad_name = f"{triad_root}{_TRIAD_SUFFIX[ttype]}"
        if sound is None:
            sound = f"{triad_name}/{root_name}"

        rel_set = set(rel)
        if family == "dominant" and rel_set & {1, 3, 6, 8}:
            color = "Altered"
        elif family in ("major", "dominant") and 5 in rel_set:
            color = "Sus (11)"
        elif rel_set & {1, 6, 8} or (family == "major" and 10 in rel_set):
            color = "Tension"
        else:
            color = "Stable"

        results.append(TriadOverChord(
            category=category,
            triad_root=triad_root,
            triad_type=ttype,
            triad_name=triad_name,
            built_on=names[rel[0]],
            intervals=tuple(names[r] for r in rel),
            sounds_like=sound,
            sounds_like_type=sound_type,
            color=color,
            source=source,
        ))
    return results


def find_triad_grips(neck, triad: TriadOverChord, max_fret: int = 15, limit: int = 40) -> list:
    """The `limit` easiest three-string grips of `triad` on `neck` (best score: fewest and
    least awkward controllers), returned in fret order (VoicingMatch list).

    Pitches come from the resolver (via VoicingSolver), and each grip is re-checked with
    grip_matches_chord, so every result really sounds the triad.
    """
    from core.stances import grip_matches_chord
    from core.voicing_solver import VoicingSolver

    matches = VoicingSolver.find_all_voicings(neck, triad.triad_root, triad.triad_type, max_fret=max_fret)
    grips = [
        m for m in matches
        if len(m.grip_strings) == 3
        and grip_matches_chord(neck, m.fret, set(m.engaged_levers), set(m.grip_strings),
                               triad.triad_root, triad.triad_type)
    ]
    grips.sort(key=lambda m: (-m.score, len(m.engaged_levers), m.fret))
    return sorted(grips[:limit], key=lambda m: (m.fret, -m.score))


def grip_intervals_over_chord(triad: TriadOverChord, voicing_formula: str) -> str:
    """Relabels a grip's triad intervals ('5 - R - b3', bass first) as intervals of the backing
    chord (Dm over G7: '9 - 5 - b7')."""
    formula = CHORD_FORMULAS[triad.triad_type]
    mapping = dict(zip((formula[pc] for pc in sorted(formula)), triad.intervals))
    return " - ".join(mapping.get(x.strip(), x.strip()) for x in voicing_formula.split(" - "))
