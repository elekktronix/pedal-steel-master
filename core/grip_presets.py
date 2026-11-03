"""Consolidated grip and pocket presets for E9, C6, and Universal 12 pedal steel tunings."""

from typing import List, Set, Tuple

# Paul Franklin 4 Foundation Groups (Consolidated, High-to-Low String Numbering)
FRANKLIN_E9_GROUPS: List[Tuple[str, str, Set[int]]] = [
    ("10 - 8 - 6", "Group 4 (Bass Triad)", {10, 8, 6}),
    ("8 - 6 - 5", "Group 3 (Low Triad)", {8, 6, 5}),
    ("6 - 5 - 4", "Group 2 (Mid Triad)", {6, 5, 4}),
    ("5 - 4 - 3", "Group 1 (Top Triad)", {5, 4, 3}),
]

# Consolidated E9 Triad Groupings: Ordered by highest string first (10 down to 1)
E9_CONSOLIDATED_TRIADS: List[Tuple[str, str, Set[int]]] = [
    ("10 - 8 - 6", "Group 4 (Bass Triad)", {10, 8, 6}),
    ("8 - 6 - 5", "Group 3 (Low Triad)", {8, 6, 5}),
    ("8 - 6 - 4", "Standard Open Grip", {8, 6, 4}),
    ("6 - 5 - 4", "Group 2 (Mid Triad)", {6, 5, 4}),
    ("5 - 4 - 3", "Group 1 (Top Triad)", {5, 4, 3}),
    ("4 - 3 - 1", "Top Treble Voicing", {4, 3, 1}),
]

# Alias for backwards compatibility with any inspector modules
E9_GRIP_CARDS = E9_CONSOLIDATED_TRIADS

# Jeff Newman 2-Note Dyads: Placed at end, High-to-Low String Numbering (e.g. 8 - 5)
NEWMAN_DYAD_POCKETS: List[Tuple[str, str, Set[int]]] = [
    ("8 - 5", "Newman Melody Track", {8, 5}),
    ("6 - 5", "Mid Harmony Track", {6, 5}),
    ("5 - 4", "Newman Upper Dyad", {5, 4}),
    ("5 - 3", "Franklin/Newman 6th", {5, 3}),
]

# C6th Chord Chart & C6 Essay Open Chords (High-to-Low String Numbering)
C6_GRIP_CARDS: List[Tuple[str, str, Set[int]]] = [
    ("7 - 6 - 5", "Root Triad (R)", {7, 6, 5}),
    ("6 - 5 - 3", "1st Inversion (F)", {6, 5, 3}),
    ("5 - 3 - 2", "2nd Inversion (S)", {5, 3, 2}),
    ("4 - 3 - 2", "Am / Upper Triad", {4, 3, 2}),
    ("8 - 7 - 6 - 5", "Am7 Open Block", {8, 7, 6, 5}),
    ("7 - 6 - 5 - 4", "C6 Root Block", {7, 6, 5, 4}),
    ("9 - 8 - 7 - 4", "F Open Spread", {9, 8, 7, 4}),
    ("6 - 5 - 4 - 3", "C6 Comping Inv", {6, 5, 4, 3}),
    ("5 - 4 - 3 - 2", "Upper 4-Way Block", {5, 4, 3, 2}),
    ("4 - 3 - 2 - 1", "6/9 Swing Grip", {4, 3, 2, 1}),
    ("10 - 7 - 5", "Deep Bass Pocket", {10, 7, 5}),
]

# 12-String Universal Pockets (High-to-Low String Numbering)
U12_GRIP_CARDS: List[Tuple[str, str, Set[int]]] = [
    ("8 - 6 - 4", "Standard Open Triad", {8, 6, 4}),
    ("6 - 5 - 4", "Middle Inversion", {6, 5, 4}),
    ("5 - 4 - 3", "High Triad (A+B)", {5, 4, 3}),
    ("4 - 3 - 1", "Top Treble Voicing", {4, 3, 1}),
    ("10 - 8 - 6 - 5", "Middle 4-Block", {10, 8, 6, 5}),
    ("11 - 9 - 8 - 6", "Low E9 4-Block", {11, 9, 8, 6}),
    ("12 - 11 - 9", "Low Root / 5th", {12, 11, 9}),
    ("12 - 11 - 9 - 6", "4-Octave Spread", {12, 11, 9, 6}),
    ("12 - 10 - 8 - 6", "Walking Bass Grip", {12, 10, 8, 6}),
    ("12 - 11 - 10 - 9", "Low 4-Block", {12, 11, 10, 9}),
    ("12 - 9 - 8 - 4", "Wide Open Shell", {12, 9, 8, 4}),
]