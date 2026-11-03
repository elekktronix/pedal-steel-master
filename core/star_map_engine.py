"""Engine for Up-The-Neck Chord Navigation across E9 and C6 pedal steel necks,
dynamically resolving Franklin P1 vs standard pedal shifts.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from core.models import Neck, NeckType
from core.theory import NOTE_NAMES_SHARP, NOTE_TO_SEMITONE

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
    controllers: List[str]   # e.g., ["P2", "LKL"]
    target_strings: Set[int] # e.g., {8, 6, 5}
    description: str         # e.g., "G Major (Open Root)"
    strings_desc: str        # e.g., "Strings 8, 6, 5"
    fret_offset: int = 0


class StarMapEngine:
    @classmethod
    def calculate_landmarks(
        cls,
        root: str,
        chord_type: str = "Major",
        neck: Optional[Neck] = None,
    ) -> List[StarMapLandmark]:
        """Calculates authentic Up-The-Neck landmarks for the active tuning (E9 or C6)."""
        is_c6 = False
        if neck is not None:
            is_c6 = (neck.neck_type == NeckType.C6 or "C6" in neck.name)

        if is_c6:
            return cls._calculate_c6_landmarks(root, chord_type, neck)
        else:
            return cls._calculate_e9_landmarks(root, chord_type, neck)

    @classmethod
    def calculate_major_star_map(cls, root: str, neck: Optional[Neck] = None) -> List[StarMapLandmark]:
        return cls.calculate_landmarks(root, "Major", neck)

    @classmethod
    def calculate_minor_anchors(cls, root: str, neck: Optional[Neck] = None) -> List[StarMapLandmark]:
        return cls.calculate_landmarks(root, "Minor", neck)

    # -------------------------------------------------------------------------
    # Dynamic E9 Controller Resolver (Franklin P1 Support)
    # -------------------------------------------------------------------------
    @classmethod
    def _resolve_e9_controllers(cls, neck: Optional[Neck]) -> Tuple[str, str, str, str, str]:
        """Dynamically identifies Pedal A, B, C, F-Lever, and D-Lever regardless of
        whether the Franklin pedal is at P1 (shifting A->P2, B->P3, C->P4) or standard.
        """
        pedal_a = "P1"
        pedal_b = "P2"
        pedal_c = "P3"
        f_lever = "LKL"
        d_lever = "LKR"

        if neck:
            # Check if P1 is the Franklin pedal (label has Franklin or lowers string 5/6)
            has_franklin_p1 = False
            if "P1" in neck.pedals:
                p1 = neck.pedals["P1"]
                if "Franklin" in p1.label or (5 in p1.changes and p1.changes[5] < 0):
                    has_franklin_p1 = True

            # Scan pedals for exact changer actions
            for pid, p in neck.pedals.items():
                if p.changes.get(5) == 2 and (p.changes.get(10) == 2 or "A" in p.label):
                    pedal_a = pid
                elif p.changes.get(6) == 1 and (p.changes.get(3) == 1 or "B" in p.label):
                    pedal_b = pid
                elif p.changes.get(4) == 2 and (p.changes.get(5) == 2 or "C" in p.label):
                    pedal_c = pid

            # Fallback if labels/changes didn't explicitly match
            if has_franklin_p1 and pedal_a == "P1":
                pedal_a = "P2"
                pedal_b = "P3"
                pedal_c = "P4"

            # Scan knee levers for F-lever and D-lever
            for lid, l in neck.knee_levers.items():
                if l.changes.get(4) == 1 or l.changes.get(8) == 1:
                    f_lever = lid
                elif l.changes.get(4) == -1 or l.changes.get(8) == -1:
                    d_lever = lid

        return pedal_a, pedal_b, pedal_c, f_lever, d_lever

    # -------------------------------------------------------------------------
    # E9 Up-The-Neck Navigation
    # -------------------------------------------------------------------------
    @classmethod
    def _calculate_e9_landmarks(
        cls,
        root: str,
        chord_type: str,
        neck: Optional[Neck] = None,
    ) -> List[StarMapLandmark]:
        clean_root = format_root(root)
        root_pc = NOTE_TO_SEMITONE.get(clean_root, 4)

        q_low = chord_type.strip().lower()
        is_minor = q_low.startswith("min") or q_low in ("m", "-")

        pedal_a, pedal_b, pedal_c, f_lever, d_lever = cls._resolve_e9_controllers(neck)
        landmarks: List[StarMapLandmark] = []

        if not is_minor:
            # E9 Major: Base open fret is (root_pc - 4) % 12
            f_base = (root_pc - 4) % 12

            # Newman Major Formulas:
            # 1. Open: +0 frets (Strings 8, 6, 5) -> Root Position (E, G#, B)
            # 2. AF:   +3 frets (Strings 6, 5, 4 with Pedal A + F-lever) -> 1st Inversion
            # 3. D:    +5 frets (Strings 7, 5, 4 with D-lever) -> 2nd Inversion (B, E, G#)
            # 4. AB:   +7 frets (Strings 8, 6, 5 with Pedal A + Pedal B) -> 2nd Inversion
            offsets = [
                (0, "Open", [], {8, 6, 5}, "Open Root Position", "Strings 8, 6, 5"),
                (3, "AF", [pedal_a, f_lever], {6, 5, 4}, "Pedal A + F-Lever", "Strings 6, 5, 4"),
                (5, "D", [d_lever], {7, 5, 4}, "D-Lever (5-1-3 Triad)", "Strings 7, 5, 4"),
                (7, "AB", [pedal_a, pedal_b], {8, 6, 5}, "Pedals A & B Down", "Strings 8, 6, 5"),
            ]

            for oct_shift in (0, 12):
                for delta, tag, ctrls, strings, desc, s_desc in offsets:
                    fret = f_base + delta + oct_shift
                    if 0 <= fret <= 24:
                        lbl = f"{fret} ({tag})" if tag == "Open" else f"{fret}{tag}"
                        landmarks.append(
                            StarMapLandmark(
                                label=lbl,
                                fret=fret,
                                controllers=ctrls,
                                target_strings=strings,
                                description=f"{clean_root} Major: {desc} at Fret {fret}",
                                strings_desc=s_desc,
                                fret_offset=delta,
                            )
                        )
        else:
            # E9 Minor Connection (Jeff Newman):
            # For minor root R, pure minor triads exist at:
            # - Fret (root_pc - 1) % 12: Pedal A on strings 6, 5, 4 (2nd inv: 5-1-b3)
            # - Fret (root_pc + 4) % 12: D-Lever on strings 6, 5, 4 (root: 1-b3-5)
            # - Fret (root_pc + 6) % 12: Pedals B & C on strings 6, 5, 4 (1st inv: b3-5-1)
            # (No Fret 0 or Fret 12 for Em: fret 12 with D-lever voices G#m!)
            offsets_min = [
                ((root_pc - 1) % 12, "A-Pedal", [pedal_a], {6, 5, 4}, "Pedal A Minor Shape", "Strings 6, 5, 4"),
                ((root_pc + 4) % 12, "D-Lever", [d_lever], {6, 5, 4}, "D-Lever Minor Triad", "Strings 6, 5, 4"),
                ((root_pc + 6) % 12, "BC-Min", [pedal_b, pedal_c], {6, 5, 4}, "Pedals B & C Minor", "Strings 6, 5, 4"),
            ]

            for oct_shift in (0, 12):
                for base_f, tag, ctrls, strings, desc, s_desc in offsets_min:
                    fret = base_f + oct_shift
                    if 0 <= fret <= 24:
                        lbl = f"{fret} ({tag})"
                        landmarks.append(
                            StarMapLandmark(
                                label=lbl,
                                fret=fret,
                                controllers=ctrls,
                                target_strings=strings,
                                description=f"{clean_root}m: {desc} at Fret {fret}",
                                strings_desc=s_desc,
                                fret_offset=base_f,
                            )
                        )

        landmarks.sort(key=lambda lm: lm.fret)
        return landmarks

    # -------------------------------------------------------------------------
    # C6 Up-The-Neck Navigation (Pure Triad Inversions)
    # -------------------------------------------------------------------------
    @classmethod
    def _calculate_c6_landmarks(
        cls,
        root: str,
        chord_type: str,
        neck: Optional[Neck] = None,
    ) -> List[StarMapLandmark]:
        clean_root = format_root(root)
        root_pc = NOTE_TO_SEMITONE.get(clean_root, 0)

        q_low = chord_type.strip().lower()
        is_minor = q_low.startswith("min") or q_low in ("m", "-")

        landmarks: List[StarMapLandmark] = []

        if not is_minor:
            # C6 Open Tonic root is C (PC 0)
            f_base = (root_pc - 0) % 12

            # Pure C6 Major Triads (R-3-5 only, no 6th/7th coloration):
            # 1. Fret f_base: Strings 7, 6, 5, 3 (C, E, G, C) -> Root Position
            # 2. Fret f_base: Strings 6, 5, 3 (E, G, C) -> 1st Inversion
            # 3. Fret f_base: Strings 5, 3, 2 (G, C, E) -> 2nd Inversion
            # 4. Fret (f_base + 7) % 12: Strings 9, 8, 7 (C, E, G on F-A-C strings) -> Open 4th Shape
            c6_major_offsets = [
                (0, "Open Root", [], {7, 6, 5, 3}, "Root Position (7-6-5-3)", "Strings 7, 6, 5, 3"),
                (0, "1st Inv", [], {6, 5, 3}, "1st Inversion (6-5-3)", "Strings 6, 5, 3"),
                (0, "2nd Inv", [], {5, 3, 2}, "2nd Inversion (5-3-2)", "Strings 5, 3, 2"),
                (7, "Str 9-8-7", [], {9, 8, 7}, "Open 4th Shape (9-8-7)", "Strings 9, 8, 7"),
            ]

            for oct_shift in (0, 12):
                for delta, tag, ctrls, strings, desc, s_desc in c6_major_offsets:
                    fret = f_base + delta + oct_shift
                    if 0 <= fret <= 24:
                        lbl = f"{fret} ({tag})"
                        landmarks.append(
                            StarMapLandmark(
                                label=lbl,
                                fret=fret,
                                controllers=ctrls,
                                target_strings=strings,
                                description=f"{clean_root} Major: {desc} at Fret {fret}",
                                strings_desc=s_desc,
                                fret_offset=delta,
                            )
                        )
        else:
            # C6 Relative minor of open C is Am (PC 9)
            # Base fret for minor root: (root_pc - 9) % 12
            f_min_base = (root_pc - 9) % 12

            # Pure C6 Minor Triads (R-b3-5 only):
            # 1. Fret f_min: Strings 8, 7, 6 (A, C, E) -> Root Minor Triad
            # 2. Fret f_min: Strings 6, 4, 3 (E, A, C) -> 1st Inversion Minor
            # 3. Fret (f_min + 7) % 12: Strings 10, 9, 8 -> Inverted Minor
            c6_minor_offsets = [
                (0, "Open Root", [], {8, 7, 6}, "Root Minor Triad (8-7-6)", "Strings 8, 7, 6"),
                (0, "1st Inv", [], {6, 4, 3}, "1st Inversion Minor (6-4-3)", "Strings 6, 4, 3"),
                (7, "Upper Min", [], {10, 9, 8}, "Inverted Minor (10-9-8)", "Strings 10, 9, 8"),
            ]

            for oct_shift in (0, 12):
                for delta, tag, ctrls, strings, desc, s_desc in c6_minor_offsets:
                    fret = f_min_base + delta + oct_shift
                    if 0 <= fret <= 24:
                        lbl = f"{fret} ({tag})"
                        landmarks.append(
                            StarMapLandmark(
                                label=lbl,
                                fret=fret,
                                controllers=ctrls,
                                target_strings=strings,
                                description=f"{clean_root}m: {desc} at Fret {fret}",
                                strings_desc=s_desc,
                                fret_offset=delta,
                            )
                        )

        # Eliminate duplicate labels at the same fret
        seen = set()
        deduped = []
        for lm in landmarks:
            key = (lm.fret, tuple(lm.controllers), tuple(sorted(lm.target_strings)))
            if key not in seen:
                seen.add(key)
                deduped.append(lm)

        deduped.sort(key=lambda lm: lm.fret)
        return deduped