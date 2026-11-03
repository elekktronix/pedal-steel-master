"""Prebuilt pedal steel practice progressions for E9 and C6 necks."""

from dataclasses import dataclass
from typing import Dict, List, Set

from core.tab_generator import TabStep


@dataclass
class ProgressionPreset:
    name: str
    neck_type: str  # "E9" or "C6"
    key: str
    description: str
    steps: List[TabStep]


PROGRESSION_PRESETS: List[ProgressionPreset] = [
    # ---------------- E9 CHROMATIC PRESETS ----------------
    ProgressionPreset(
        name="I - IV - V Classic 3-Fret Pocket (Key of G)",
        neck_type="E9",
        key="G",
        description="The quintessential pedal steel move. Stays in one pocket (strings 8, 6, 5) using pedals A & B.",
        steps=[
            TabStep(fret=3, engaged_levers=[], grip_strings={8, 6, 4}, chord_label="G (I)"),
            TabStep(fret=3, engaged_levers=["P1", "P2"], grip_strings={8, 6, 5}, chord_label="C (IV)"),
            TabStep(fret=5, engaged_levers=["P1", "P2"], grip_strings={8, 6, 5}, chord_label="D (V)"),
            TabStep(fret=3, engaged_levers=[], grip_strings={8, 6, 4}, chord_label="G (I)"),
        ],
    ),
    ProgressionPreset(
        name="I - IV - V Open Nut Stance (Key of E)",
        neck_type="E9",
        key="E",
        description="Open E chord moving to IV and V using pedals A & B at frets 0 and 2.",
        steps=[
            TabStep(fret=0, engaged_levers=[], grip_strings={8, 6, 4}, chord_label="E (I)"),
            TabStep(fret=0, engaged_levers=["P1", "P2"], grip_strings={8, 6, 5}, chord_label="A (IV)"),
            TabStep(fret=2, engaged_levers=["P1", "P2"], grip_strings={8, 6, 5}, chord_label="B (V)"),
            TabStep(fret=0, engaged_levers=[], grip_strings={8, 6, 4}, chord_label="E (I)"),
        ],
    ),
    ProgressionPreset(
        name="I - vi - ii - V Country Ballad (Key of G)",
        neck_type="E9",
        key="G",
        description="Classic four-chord country turnaround with minor movement.",
        steps=[
            TabStep(fret=3, engaged_levers=[], grip_strings={8, 6, 4}, chord_label="G (I)"),
            TabStep(fret=0, engaged_levers=[], grip_strings={8, 6, 4}, chord_label="Em (vi)"),
            TabStep(fret=5, engaged_levers=["P1", "P2"], grip_strings={6, 5, 4}, chord_label="Am (ii)"),
            TabStep(fret=5, engaged_levers=["P1", "P2"], grip_strings={8, 6, 5}, chord_label="D (V)"),
            TabStep(fret=3, engaged_levers=[], grip_strings={8, 6, 4}, chord_label="G (I)"),
        ],
    ),
    ProgressionPreset(
        name="Honky Tonk Turnaround V - IV - I - V (Key of A)",
        neck_type="E9",
        key="A",
        description="Standard Nashville lead-in turnaround moving down frets into the tonic.",
        steps=[
            TabStep(fret=7, engaged_levers=["P1", "P2"], grip_strings={8, 6, 5}, chord_label="E (V)"),
            TabStep(fret=5, engaged_levers=["P1", "P2"], grip_strings={8, 6, 5}, chord_label="D (IV)"),
            TabStep(fret=5, engaged_levers=[], grip_strings={8, 6, 4}, chord_label="A (I)"),
            TabStep(fret=7, engaged_levers=["P1", "P2"], grip_strings={8, 6, 5}, chord_label="E (V)"),
        ],
    ),
    ProgressionPreset(
        name="Country Waltz I - IV - I - V (Key of C)",
        neck_type="E9",
        key="C",
        description="Higher-register 3/4 ballad pacing at the 8th fret pocket.",
        steps=[
            TabStep(fret=8, engaged_levers=[], grip_strings={8, 6, 4}, chord_label="C (I)"),
            TabStep(fret=8, engaged_levers=["P1", "P2"], grip_strings={8, 6, 5}, chord_label="F (IV)"),
            TabStep(fret=8, engaged_levers=[], grip_strings={8, 6, 4}, chord_label="C (I)"),
            TabStep(fret=10, engaged_levers=["P1", "P2"], grip_strings={8, 6, 5}, chord_label="G (V)"),
            TabStep(fret=8, engaged_levers=[], grip_strings={8, 6, 4}, chord_label="C (I)"),
        ],
    ),
    # ---------------- C6 WESTERN SWING PRESETS ----------------
    ProgressionPreset(
        name="ii - V - I Standard Swing Cadence (Key of C)",
        neck_type="C6",
        key="C",
        description="Fundamental jazz and Western Swing progression using closed 4-note comping blocks.",
        steps=[
            TabStep(fret=2, engaged_levers=[], grip_strings={7, 6, 5, 4}, chord_label="Dm7 (ii)"),
            TabStep(fret=7, engaged_levers=[], grip_strings={6, 5, 4, 3}, chord_label="G7 (V)"),
            TabStep(fret=0, engaged_levers=[], grip_strings={7, 6, 5, 4}, chord_label="C6 (I)"),
        ],
    ),
    ProgressionPreset(
        name="Bob Wills Turnaround I - VI7 - ii - V7 (Key of C)",
        neck_type="C6",
        key="C",
        description="Classic Texas Playboys turnaround cycling through the secondary dominant.",
        steps=[
            TabStep(fret=0, engaged_levers=[], grip_strings={7, 6, 5, 4}, chord_label="C6 (I)"),
            TabStep(fret=9, engaged_levers=[], grip_strings={6, 5, 4, 3}, chord_label="A7 (VI)"),
            TabStep(fret=2, engaged_levers=[], grip_strings={7, 6, 5, 4}, chord_label="Dm7 (ii)"),
            TabStep(fret=7, engaged_levers=[], grip_strings={6, 5, 4, 3}, chord_label="G7 (V)"),
            TabStep(fret=0, engaged_levers=[], grip_strings={7, 6, 5, 4}, chord_label="C6 (I)"),
        ],
    ),
    ProgressionPreset(
        name="12-Bar Western Swing Blues (Key of C)",
        neck_type="C6",
        key="C",
        description="Standard 12-bar blues progression using comping block grips.",
        steps=[
            TabStep(fret=0, engaged_levers=[], grip_strings={7, 6, 5, 4}, chord_label="C6"),
            TabStep(fret=5, engaged_levers=[], grip_strings={6, 5, 4, 3}, chord_label="F7"),
            TabStep(fret=0, engaged_levers=[], grip_strings={7, 6, 5, 4}, chord_label="C6"),
            TabStep(fret=0, engaged_levers=[], grip_strings={7, 6, 5, 4}, chord_label="C7"),
            TabStep(fret=5, engaged_levers=[], grip_strings={6, 5, 4, 3}, chord_label="F7"),
            TabStep(fret=5, engaged_levers=[], grip_strings={6, 5, 4, 3}, chord_label="F7"),
            TabStep(fret=0, engaged_levers=[], grip_strings={7, 6, 5, 4}, chord_label="C6"),
            TabStep(fret=0, engaged_levers=[], grip_strings={7, 6, 5, 4}, chord_label="C6"),
            TabStep(fret=7, engaged_levers=[], grip_strings={6, 5, 4, 3}, chord_label="G7"),
            TabStep(fret=5, engaged_levers=[], grip_strings={6, 5, 4, 3}, chord_label="F7"),
            TabStep(fret=0, engaged_levers=[], grip_strings={7, 6, 5, 4}, chord_label="C6"),
            TabStep(fret=7, engaged_levers=[], grip_strings={6, 5, 4, 3}, chord_label="G7"),
        ],
    ),
]