"""Engine for Up-The-Neck Chord Navigation across E9 and C6 pedal steel necks.

Shapes are declared with functional role tokens (core.stances: "A", "B", "F", "D", ...), mapped to
the neck's actual controller IDs, and every landmark is verified with the resolver: a landmark is
only returned if its strings really sound the requested chord on that neck (D-14, D-23).
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from core.models import Neck
from core.stances import detect_roles, grip_matches_chord, is_c6_neck, resolve_stance
from core.theory import NOTE_TO_SEMITONE

ENHARMONIC_FLAT_NAMES: Dict[str, str] = {
    "A#": "Bb",
    "D#": "Eb",
    "G#": "Ab",
}


def format_root(name: str) -> str:
    return ENHARMONIC_FLAT_NAMES.get(name, name)


@dataclass
class StarMapLandmark:
    label: str               # e.g., "0 (Open)", "3AF", "5D", "7AB"
    fret: int                # 0-24
    controllers: List[str]   # actual controller IDs on the neck, e.g. ["P1", "LKL"]
    target_strings: Set[int] # e.g., {8, 6, 5}
    description: str         # e.g., "G Major: Open Root Position at Fret 3"
    strings_desc: str        # e.g., "Strings 8, 6, 5"
    fret_offset: int = 0     # frets above the chord's base shape (same meaning for every tuning/quality)


# Shape table entries: (fret offset from base, tag, role tokens, strings, description)
_Shape = Tuple[int, str, Tuple[str, ...], Set[int], str]

# E9 major: base fret = (root - E) mod 12 (open E chord on strings 8-6-5).
E9_MAJOR_SHAPES: List[_Shape] = [
    (0, "Open", (), {8, 6, 5}, "Open Root Position"),
    (3, "AF", ("A", "F"), {6, 5, 4}, "Pedal A + F-Lever"),
    (5, "D", ("D",), {7, 5, 4}, "D-Lever (5-1-3 Triad)"),
    (7, "AB", ("A", "B"), {8, 6, 5}, "Pedals A & B Down"),
]
# E9 minor (Newman): base fret = (root - 1) mod 12, A-pedal minor on strings 6-5-4.
E9_MINOR_SHAPES: List[_Shape] = [
    (0, "A-Pedal", ("A",), {6, 5, 4}, "Pedal A Minor Shape"),
    (5, "D-Lever", ("D",), {6, 5, 4}, "D-Lever Minor Triad"),
    (7, "BC-Min", ("B", "C"), {6, 5, 4}, "Pedals B & C Minor"),
]
# C6 major: base fret = root mod 12 (open C chord).
C6_MAJOR_SHAPES: List[_Shape] = [
    (0, "Open Root", (), {7, 6, 5, 3}, "Root Position (7-6-5-3)"),
    (0, "1st Inv", (), {6, 5, 3}, "1st Inversion (6-5-3)"),
    (0, "2nd Inv", (), {5, 3, 2}, "2nd Inversion (5-3-2)"),
    (7, "Str 9-8-7", (), {9, 8, 7}, "Open 4th Shape (9-8-7)"),
]
# C6 minor: base fret = (root - A) mod 12 (open A minor chord).
C6_MINOR_SHAPES: List[_Shape] = [
    (0, "Open Root", (), {8, 7, 6}, "Root Minor Triad (8-7-6)"),
    (0, "1st Inv", (), {7, 6, 4}, "1st Inversion Minor (7-6-4)"),
    (0, "2nd Inv", (), {6, 4, 3}, "2nd Inversion Minor (6-4-3)"),
    (0, "Upper Root", (), {4, 3, 2}, "Upper Root Minor (4-3-2)"),
]


def _default_neck(c6: bool) -> Neck:
    from core import presets

    return presets.build_standard_c6_10() if c6 else presets.build_standard_emmons_e9_10()


class StarMapEngine:
    @classmethod
    def calculate_landmarks(
        cls,
        root: str,
        chord_type: str = "Major",
        neck: Optional[Neck] = None,
    ) -> List[StarMapLandmark]:
        """Up-The-Neck landmarks for the neck's tuning (standard E9 if no neck is given)."""
        clean_root = format_root(root)
        if clean_root not in NOTE_TO_SEMITONE:
            return []
        root_pc = NOTE_TO_SEMITONE[clean_root]

        q_low = chord_type.strip().lower()
        is_minor = q_low.startswith("min") or q_low in ("m", "-")
        quality = "Minor" if is_minor else "Major"

        c6 = is_c6_neck(neck) if neck is not None else False
        neck = neck if neck is not None else _default_neck(c6)

        if c6:
            shapes = C6_MINOR_SHAPES if is_minor else C6_MAJOR_SHAPES
            base = (root_pc - 9) % 12 if is_minor else root_pc % 12
        else:
            shapes = E9_MINOR_SHAPES if is_minor else E9_MAJOR_SHAPES
            base = (root_pc - 1) % 12 if is_minor else (root_pc - 4) % 12

        roles = detect_roles(neck)
        name = f"{clean_root}m" if is_minor else f"{clean_root} Major"
        landmarks: List[StarMapLandmark] = []
        seen = set()

        for oct_shift in (-12, 0, 12):
            for offset, tag, tokens, strings, desc in shapes:
                fret = base + offset + oct_shift
                if not 0 <= fret <= 24:
                    continue
                stance = resolve_stance(neck, tokens, roles)
                if stance is None:
                    continue  # this copedant lacks a controller for the shape
                if not grip_matches_chord(neck, fret, stance, strings, clean_root, quality):
                    continue  # never return a landmark that does not sound the chord
                key = (fret, frozenset(stance), frozenset(strings))
                if key in seen:
                    continue
                seen.add(key)

                if tag == "Open" or c6 or is_minor:
                    lbl = f"{fret} ({tag})"
                else:
                    lbl = f"{fret}{tag}"
                landmarks.append(
                    StarMapLandmark(
                        label=lbl,
                        fret=fret,
                        controllers=sorted(stance),
                        target_strings=set(strings),
                        description=f"{name}: {desc} at Fret {fret}",
                        strings_desc="Strings " + ", ".join(map(str, sorted(strings, reverse=True))),
                        fret_offset=offset,
                    )
                )

        landmarks.sort(key=lambda lm: (lm.fret, lm.fret_offset))
        return landmarks

    @classmethod
    def calculate_major_star_map(cls, root: str, neck: Optional[Neck] = None) -> List[StarMapLandmark]:
        return cls.calculate_landmarks(root, "Major", neck)

    @classmethod
    def calculate_minor_anchors(cls, root: str, neck: Optional[Neck] = None) -> List[StarMapLandmark]:
        return cls.calculate_landmarks(root, "Minor", neck)
