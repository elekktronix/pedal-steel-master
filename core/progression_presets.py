"""Prebuilt pedal steel practice progressions for E9 and C6 necks.

`engaged_levers` holds *role tokens* (core.stances: "A", "B", "C", "D", "C6P8", ...), not controller
IDs. Use `resolve_preset_steps(preset, neck)` to map them onto a neck. Every step is verified by
tests/test_engines.py to sound the chord in its label on the standard preset neck (D-10).
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import List, Optional

from core.models import Neck
from core.stances import detect_roles, resolve_stance
from core.tab_generator import TabStep


@dataclass
class ProgressionPreset:
    name: str
    neck_type: str  # "E9" or "C6"
    key: str
    description: str
    steps: List[TabStep]
    # Chord root + CHORD_FORMULAS type for each step (used for verification)
    chords: Optional[List[tuple]] = None


def _step(fret: int, roles: List[str], grip: set, label: str) -> TabStep:
    return TabStep(fret=fret, engaged_levers=list(roles), grip_strings=set(grip), chord_label=label)


TRIAD = {8, 6, 5}     # E9 root-position triad pocket (E-G#-B open)
MINOR = {6, 5, 4}     # E9 pedal-minor pocket
BLOCK = {7, 6, 5, 4}  # C6 4-note comping block (C-E-G-A open)

PROGRESSION_PRESETS: List[ProgressionPreset] = [
    # ---------------- E9 CHROMATIC PRESETS ----------------
    ProgressionPreset(
        name="I - IV - V Classic 3-Fret Pocket (Key of G)",
        neck_type="E9",
        key="G",
        description="The quintessential pedal steel move. Stays in one pocket (strings 8, 6, 5) using pedals A & B.",
        steps=[
            _step(3, [], TRIAD, "G (I)"),
            _step(3, ["A", "B"], TRIAD, "C (IV)"),
            _step(5, ["A", "B"], TRIAD, "D (V)"),
            _step(3, [], TRIAD, "G (I)"),
        ],
        chords=[("G", "Major"), ("C", "Major"), ("D", "Major"), ("G", "Major")],
    ),
    ProgressionPreset(
        name="I - IV - V Open Nut Stance (Key of E)",
        neck_type="E9",
        key="E",
        description="Open E chord moving to IV and V using pedals A & B at frets 0 and 2.",
        steps=[
            _step(0, [], TRIAD, "E (I)"),
            _step(0, ["A", "B"], TRIAD, "A (IV)"),
            _step(2, ["A", "B"], TRIAD, "B (V)"),
            _step(0, [], TRIAD, "E (I)"),
        ],
        chords=[("E", "Major"), ("A", "Major"), ("B", "Major"), ("E", "Major")],
    ),
    ProgressionPreset(
        name="I - vi - ii - V Country Ballad (Key of G)",
        neck_type="E9",
        key="G",
        description="Classic four-chord country turnaround. The minors stay at fret 3 using the A pedal and B+C pedals.",
        steps=[
            _step(3, [], TRIAD, "G (I)"),
            _step(3, ["A"], MINOR, "Em (vi)"),
            _step(3, ["B", "C"], MINOR, "Am (ii)"),
            _step(5, ["A", "B"], TRIAD, "D (V)"),
            _step(3, [], TRIAD, "G (I)"),
        ],
        chords=[("G", "Major"), ("E", "Minor"), ("A", "Minor"), ("D", "Major"), ("G", "Major")],
    ),
    ProgressionPreset(
        name="Honky Tonk Turnaround V - IV - I - V (Key of A)",
        neck_type="E9",
        key="A",
        description="Standard Nashville lead-in turnaround moving down frets into the tonic.",
        steps=[
            _step(7, ["A", "B"], TRIAD, "E (V)"),
            _step(5, ["A", "B"], TRIAD, "D (IV)"),
            _step(5, [], TRIAD, "A (I)"),
            _step(7, ["A", "B"], TRIAD, "E (V)"),
        ],
        chords=[("E", "Major"), ("D", "Major"), ("A", "Major"), ("E", "Major")],
    ),
    ProgressionPreset(
        name="Country Waltz I - IV - I - V (Key of C)",
        neck_type="E9",
        key="C",
        description="Higher-register 3/4 ballad pacing at the 8th fret pocket.",
        steps=[
            _step(8, [], TRIAD, "C (I)"),
            _step(8, ["A", "B"], TRIAD, "F (IV)"),
            _step(8, [], TRIAD, "C (I)"),
            _step(10, ["A", "B"], TRIAD, "G (V)"),
            _step(8, [], TRIAD, "C (I)"),
        ],
        chords=[("C", "Major"), ("F", "Major"), ("C", "Major"), ("G", "Major"), ("C", "Major")],
    ),
    # ---------------- C6 WESTERN SWING PRESETS ----------------
    # Dominant 7ths use Pedal 8 (C -> C#) on the 7-6-5-4 block: A7 shape (C# E G A) moved up the neck.
    ProgressionPreset(
        name="ii - V - I Standard Swing Cadence (Key of C)",
        neck_type="C6",
        key="C",
        description="Fundamental Western Swing cadence: open Dm7 block at fret 5, Pedal 8 dominant at fret 10, C6 at 12.",
        steps=[
            _step(5, [], BLOCK, "Dm7 (ii)"),
            _step(10, ["C6P8"], BLOCK, "G7 (V)"),
            _step(12, [], BLOCK, "C6 (I)"),
        ],
        chords=[("D", "Minor 7th"), ("G", "Dominant 7th"), ("C", "Major 6th")],
    ),
    ProgressionPreset(
        name="Bob Wills Turnaround I - VI7 - ii - V7 (Key of C)",
        neck_type="C6",
        key="C",
        description="Classic Texas Playboys turnaround cycling through the secondary dominant (Pedal 8 dominants).",
        steps=[
            _step(12, [], BLOCK, "C6 (I)"),
            _step(12, ["C6P8"], BLOCK, "A7 (VI)"),
            _step(5, [], BLOCK, "Dm7 (ii)"),
            _step(10, ["C6P8"], BLOCK, "G7 (V)"),
            _step(12, [], BLOCK, "C6 (I)"),
        ],
        chords=[("C", "Major 6th"), ("A", "Dominant 7th"), ("D", "Minor 7th"), ("G", "Dominant 7th"), ("C", "Major 6th")],
    ),
    ProgressionPreset(
        name="12-Bar Western Swing Blues (Key of C)",
        neck_type="C6",
        key="C",
        description="Standard 12-bar blues using the 7-6-5-4 block: C6 at 12, dominants with Pedal 8 (F7 at 8, G7 at 10, C7 at 15).",
        steps=[
            _step(12, [], BLOCK, "C6"),
            _step(8, ["C6P8"], BLOCK, "F7"),
            _step(12, [], BLOCK, "C6"),
            _step(15, ["C6P8"], BLOCK, "C7"),
            _step(8, ["C6P8"], BLOCK, "F7"),
            _step(8, ["C6P8"], BLOCK, "F7"),
            _step(12, [], BLOCK, "C6"),
            _step(12, [], BLOCK, "C6"),
            _step(10, ["C6P8"], BLOCK, "G7"),
            _step(8, ["C6P8"], BLOCK, "F7"),
            _step(12, [], BLOCK, "C6"),
            _step(10, ["C6P8"], BLOCK, "G7"),
        ],
        chords=[
            ("C", "Major 6th"), ("F", "Dominant 7th"), ("C", "Major 6th"), ("C", "Dominant 7th"),
            ("F", "Dominant 7th"), ("F", "Dominant 7th"), ("C", "Major 6th"), ("C", "Major 6th"),
            ("G", "Dominant 7th"), ("F", "Dominant 7th"), ("C", "Major 6th"), ("G", "Dominant 7th"),
        ],
    ),
]


def resolve_preset_steps(preset: ProgressionPreset, neck: Neck) -> Optional[List[TabStep]]:
    """Copies the preset's steps with role tokens mapped to the neck's controller IDs.
    Returns None if the neck lacks a controller the preset needs."""
    roles = detect_roles(neck)
    steps: List[TabStep] = []
    for s in preset.steps:
        stance = resolve_stance(neck, s.engaged_levers, roles)
        if stance is None:
            return None
        step = deepcopy(s)
        step.engaged_levers = sorted(stance)
        steps.append(step)
    return steps
