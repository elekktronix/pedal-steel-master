"""Chord Atlas (E-27): every chord a copedant can play at one bar position, and every way to play it.

Built on the Compare Copedants scan (core.copedant_compare): the neck is scanned once at fret 0
over every ergonomic stance (plus half-stop variants) and every grip of 3-5 strings within a
6-string span. Roots are stored as pitch classes; the display transposes them to any fret. All
filters (chord types, shells, controllers, max controllers, grips) run on the stored result, so
changing a filter never re-scans. Every way is checked with `stances.grip_matches_chord`.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from core.copedant_compare import (
    _stance_pcs,
    REFERENCE_FRET,
    ChordSighting,
    all_grips,
    candidate_stances,
    chord_group,
    has_idle_controller,
    scan_chords,
    sighting_sort_key,
)
from core.grip_presets import C6_GRIP_CARDS, E9_CONSOLIDATED_TRIADS, U12_GRIP_CARDS
from core.models import Neck, NeckType
from core.stances import grip_matches_chord, is_c6_neck
from core.ergonomics import ErgonomicsEngine, ErgonomicStance
from core.theory import CHORD_FORMULAS, NOTE_NAMES_SHARP, NOTE_TO_SEMITONE, spell_pc
from core.voicing_solver import VoicingSolver

ATLAS_GRIP_SIZES = (3, 4, 5)
ATLAS_MAX_SPAN = 6

GRIP_SOURCE_ALL = "All string groups"
GRIP_SOURCE_POCKETS = "Pocket presets (grip bar)"
GRIP_SOURCE_SOLVER = "Voicing finder grips"
GRIP_SOURCE_CURRENT = "Current pocket (fretboard)"
GRIP_SOURCE_CUSTOM = "Custom…"


@dataclass
class AtlasEntry:
    """One chord (root at fret 0 + type) and every way to play it."""
    root_pc: int
    chord_type: str
    sightings: List[ChordSighting]

    @property
    def best(self) -> Optional[ChordSighting]:
        return self.sightings[0] if self.sightings else None


@dataclass
class ChordAtlas:
    neck_name: str
    entries: List[AtlasEntry]
    stance_count: int
    grip_count: int
    stances: List[Tuple[str, ...]] = field(default_factory=list)
    # stance -> {string number: sounding MIDI at fret 0}; reused by find_chord (no re-resolve).
    stance_midis: Dict[Tuple[str, ...], Dict[int, int]] = field(default_factory=dict, repr=False)
    grips: List[Tuple[int, ...]] = field(default_factory=list, repr=False)


def _entry_sort_key(e: AtlasEntry):
    groups = list(("Triads", "6ths & 7ths", "Extensions"))
    b = e.best
    return (groups.index(chord_group(e.chord_type)), e.root_pc,
            list(CHORD_FORMULAS).index(e.chord_type), sighting_sort_key(b) if b else ())


def build_atlas(
    neck: Neck,
    grip_sizes: Iterable[int] = ATLAS_GRIP_SIZES,
    max_span: int = ATLAS_MAX_SPAN,
    verify: bool = True,
) -> ChordAtlas:
    """Scans the neck once. `verify` re-checks every way through the resolver."""
    stances = candidate_stances(neck)
    grips = all_grips(neck.string_count, sizes=tuple(grip_sizes), max_span=max_span)
    scan = scan_chords(neck, fret=REFERENCE_FRET, grips=grips, stances=stances)
    entries: List[AtlasEntry] = []
    for (root_pc, ctype), sightings in scan.items():
        ways = sorted(sightings, key=sighting_sort_key)
        if verify:
            ways = [s for s in ways if grip_matches_chord(
                neck, REFERENCE_FRET, s.controllers, s.strings, NOTE_NAMES_SHARP[root_pc], ctype)]
        if ways:
            entries.append(AtlasEntry(root_pc, ctype, ways))
    entries.sort(key=_entry_sort_key)
    midis = {st: stance_midis(neck, st) for st in stances}
    return ChordAtlas(neck.name, entries, len(stances), len(grips), stances, midis, grips)


def stance_midis(neck: Neck, stance: Tuple[str, ...]) -> Dict[int, int]:
    """string number -> sounding MIDI at fret 0 for a stance (through the resolver)."""
    return _stance_pcs(neck, stance, REFERENCE_FRET)


# ---------------------------------------------------------------------------
# Find mode: every position of one chord on the neck (replaces the Voicing Finder's search)
# ---------------------------------------------------------------------------
THIRD_LABELS = ("3", "b3", "4")


@dataclass
class ChordPosition:
    """One place to play the target chord: bar fret + stance + grip."""
    fret: int
    sighting: ChordSighting          # root_pc is the root at fret 0 (as everywhere in the atlas)
    ergonomics: ErgonomicStance
    formula: Tuple[str, ...]         # interval label per string, lowest pitch first
    missing: Tuple[str, ...]         # chord tones that do not sound (omitted / no-5th shell)
    score: float


def _ergonomics(controllers: Tuple[str, ...]) -> ErgonomicStance:
    return ErgonomicsEngine.evaluate_stance({c.replace("_HALF", "") for c in controllers})


def find_chord(
    atlas: ChordAtlas,
    root: str,
    chord_type: str,
    omitted: Iterable[str] = (),
    allow_no_fifth: bool = False,
    max_fret: int = 15,
    grips: Optional[Iterable[Tuple[int, ...]]] = None,
    min_fret: int = 0,
) -> List[ChordPosition]:
    """Every fret (0..max_fret) + stance + grip that sounds `root chord_type`.

    Match rule (same as the atlas): the grip's pitch classes must be exactly the chord's tones
    minus `omitted` (labels such as "R", "5" or "b7": an omitted tone must not sound). With
    `allow_no_fifth`, a chord of 4+ tones may also leave out its 5th. Positions are found by
    transposing the fret-0 stance pitches, so nothing is re-resolved. `grips` limits the search
    to those string groups (default: every scanned grip).
    """
    if root not in NOTE_TO_SEMITONE or chord_type not in CHORD_FORMULAS:
        return []
    formula = CHORD_FORMULAS[chord_type]
    omitted = set(omitted)
    need = frozenset(st for st, lbl in formula.items() if lbl not in omitted)
    if not need:
        return []
    shell_ok = allow_no_fifth and len(formula) >= 4 and formula.get(7) == "5" and 7 in need and len(need) > 1
    targets = {need: False}
    if shell_ok:
        targets[need - {7}] = True
    target_pc = NOTE_TO_SEMITONE[root]
    root_required = 0 in need

    ergo_cache: Dict[Tuple[str, ...], ErgonomicStance] = {}
    out: List[ChordPosition] = []
    grip_list = list(grips) if grips is not None else atlas.grips
    for st, midis in atlas.stance_midis.items():
        for grip in grip_list:
            if any(s not in midis for s in grip):
                continue
            ms = [midis[s] for s in grip]
            pcs = {m % 12 for m in ms}
            candidates = pcs if root_required else range(12)
            for r in candidates:
                rel = frozenset((p - r) % 12 for p in pcs)
                if rel not in targets:
                    continue
                if len(rel) < min(len(need), len(grip)) - (1 if targets[rel] else 0):
                    continue
                if has_idle_controller(st, grip, atlas.stance_midis):
                    break  # a lever that doesn't touch the grip: the simpler stance already has it
                lowest = min(ms)
                sighting = ChordSighting(r, chord_type, st, grip, targets[rel], (lowest - r) % 12)
                ordered = sorted(ms)
                labels = tuple(formula[(m - r) % 12] for m in ordered)
                missing = tuple(lbl for s_, lbl in sorted(formula.items()) if s_ not in rel)
                if st not in ergo_cache:
                    ergo_cache[st] = _ergonomics(st)
                ergo = ergo_cache[st]
                score = (14.0 * len(rel) + (5.0 if 0 in rel else 0.0)
                         + (6.0 if any(formula.get(x) in THIRD_LABELS for x in rel) else 0.0)
                         + (3.0 if len(rel) == len(grip) else 0.0) - ergo.penalty)
                f0 = (target_pc - r) % 12
                for fret in range(f0, max_fret + 1, 12):
                    if fret >= min_fret:
                        out.append(ChordPosition(fret, sighting, ergo, labels, missing, score))
    return out


# ---------------------------------------------------------------------------
# Circle-of-Fifths radar (E-29): nearby IV / V / V7 / vi / ii moves, with the atlas match rule
# ---------------------------------------------------------------------------
RADAR_TARGETS: List[Tuple[str, int, str]] = [
    ("IV (Subdominant)", 5, "Major"),
    ("V (Dominant)", 7, "Major"),
    ("V7 (Dominant 7th)", 7, "Dominant 7th"),
    ("vi (Relative Minor)", 9, "Minor"),
    ("ii (Supertonic)", 2, "Minor"),
]
MOVE_SAME_FRET = "Same-Fret Pedal Drop"
MOVE_HOLD_SLIDE = "Hold Pedals & Slide"
MOVE_OPEN_SHIFT = "Open Bar Shift"
MOVE_POSITION_SHIFT = "Position Shift"


@dataclass
class NeighborMove:
    relationship: str
    root: str                        # display spelling (global preference)
    chord_type: str
    fret: int
    delta_frets: int
    controllers: Tuple[str, ...]
    strings: Tuple[int, ...]
    movement: str
    how: str
    position: ChordPosition


def _grip_distance(a: Tuple[int, ...], b: Tuple[int, ...]) -> int:
    return abs(max(a) - max(b)) + abs(min(a) - min(b)) + (0 if len(a) == len(b) else 1)


def _classify_move(origin_fret: int, origin_ctrls: Set[str], p: ChordPosition) -> Tuple[str, str]:
    delta = p.fret - origin_fret
    ctrls = set(p.sighting.controllers)
    names = " + ".join(c.replace("_HALF", " (half)") for c in p.sighting.controllers) or "open"
    strings = "-".join(map(str, p.sighting.strings))
    step = f"{delta:+d}"
    if delta == 0:
        change = f"engage {names}" if ctrls != origin_ctrls else "same pedals"
        return MOVE_SAME_FRET, f"Stay at fret {p.fret} | {change} | strings {strings}"
    if ctrls == origin_ctrls and ctrls:
        return MOVE_HOLD_SLIDE, f"Slide {step} to fret {p.fret} | hold {names} | strings {strings}"
    if not ctrls:
        return MOVE_OPEN_SHIFT, f"Slide {step} to fret {p.fret} | open bar | strings {strings}"
    return MOVE_POSITION_SHIFT, f"Move {step} to fret {p.fret} with {names} | strings {strings}"


def find_neighbors(
    atlas: ChordAtlas,
    origin_root: str,
    origin_fret: int,
    origin_strings: Iterable[int],
    origin_controllers: Iterable[str],
    allowed_moves: Optional[Iterable[str]] = None,
    allow_no_fifth: bool = False,
    max_results: int = 12,
) -> List[NeighborMove]:
    """Closest IV, V, V7, vi and ii voicings from a voicing (frets origin-9..origin+9).

    Each target must sound all its tones (atlas rule; `allow_no_fifth` lets a V7 drop its 5th),
    so a plain triad is never offered as a V7. Grips are tried on the same strings first, then on
    nearby grips of the same size or one string more. Awkward stances are skipped.
    """
    if origin_root not in NOTE_TO_SEMITONE:
        return []
    origin = tuple(sorted(set(origin_strings), reverse=True))
    origin_ctrls = {c for c in origin_controllers}
    allowed = set(allowed_moves) if allowed_moves is not None else None
    near = sorted(
        (g for g in atlas.grips
         if len(g) in (len(origin), len(origin) + 1) and _grip_distance(g, origin) <= 3 and g != origin),
        key=lambda g: _grip_distance(g, origin))
    lo, hi = max(0, origin_fret - 9), min(24, origin_fret + 9)
    root_pc = NOTE_TO_SEMITONE[origin_root]

    moves: List[NeighborMove] = []
    for relationship, offset, ctype in RADAR_TARGETS:
        name = spell_pc(root_pc + offset)
        found: List[ChordPosition] = []
        for grips in ([origin], near):
            found = [p for p in find_chord(atlas, name, ctype, allow_no_fifth=allow_no_fifth,
                                           max_fret=hi, min_fret=lo, grips=grips)
                     if p.ergonomics.difficulty.name != "AWKWARD"]
            if found:
                break
        for p in found:
            movement, how = _classify_move(origin_fret, origin_ctrls, p)
            if allowed is not None and movement not in allowed:
                continue
            moves.append(NeighborMove(relationship, name, ctype, p.fret, p.fret - origin_fret,
                                      p.sighting.controllers, p.sighting.strings, movement, how, p))

    moves.sort(key=lambda m: (abs(m.delta_frets) > 2, abs(m.delta_frets), len(m.controllers),
                              _grip_distance(m.strings, origin), m.position.ergonomics.penalty))
    unique: List[NeighborMove] = []
    seen = set()
    for m in moves:
        key = (m.relationship, m.movement, m.fret, m.controllers)
        if key not in seen:
            seen.add(key)
            unique.append(m)
    # The closest move for every relationship first, then fill up with the next closest.
    best = {}
    for m in unique:
        best.setdefault(m.relationship, m)
    picked = list(best.values())
    picked += [m for m in unique if m not in picked][:max(0, max_results - len(picked))]
    order = [r for r, _, _ in RADAR_TARGETS]
    rank = {id(m): i for i, m in enumerate(unique)}
    return sorted(picked, key=lambda m: (order.index(m.relationship), rank[id(m)]))


def sort_positions(positions: List[ChordPosition], by: str = "easiest") -> List[ChordPosition]:
    """'easiest': ergonomic penalty, fewest controllers, best score, fret. 'fret': fret, then easiest."""
    def easiest(p: ChordPosition):
        return (p.ergonomics.penalty, len(p.sighting.controllers), -p.score, p.fret, p.sighting.strings)
    if by == "fret":
        return sorted(positions, key=lambda p: (p.fret,) + easiest(p))
    return sorted(positions, key=easiest)


def filter_atlas(
    atlas: ChordAtlas,
    keep: Callable[[ChordSighting], bool],
    chord_types: Optional[Iterable[str]] = None,
    root_pc: Optional[int] = None,
) -> List[AtlasEntry]:
    """Entries whose type/root pass, with only the ways that pass `keep` (core.copedant_compare.sighting_filter)."""
    types = set(chord_types) if chord_types is not None else None
    out: List[AtlasEntry] = []
    for e in atlas.entries:
        if types is not None and e.chord_type not in types:
            continue
        if root_pc is not None and e.root_pc != root_pc:
            continue
        ways = [s for s in e.sightings if keep(s)]
        if ways:
            out.append(AtlasEntry(e.root_pc, e.chord_type, ways))
    return out


def by_stance(entries: Iterable[AtlasEntry]) -> Dict[Tuple[str, ...], List[Tuple[AtlasEntry, ChordSighting]]]:
    """stance -> [(chord, way)], stances ordered by number of controllers then name."""
    out: Dict[Tuple[str, ...], List[Tuple[AtlasEntry, ChordSighting]]] = {}
    for e in entries:
        for s in e.sightings:
            out.setdefault(s.controllers, []).append((e, s))
    return dict(sorted(out.items(), key=lambda kv: (len(kv[0]), kv[0])))


def coverage(entries: Iterable[AtlasEntry], tonic_pc: int) -> Dict[str, Dict[int, int]]:
    """chord type -> {semitones above the tonic: number of ways}. Answers "which chords on which
    degree can I play at this bar position?"."""
    out: Dict[str, Dict[int, int]] = {}
    for e in entries:
        out.setdefault(e.chord_type, {})[(e.root_pc - tonic_pc) % 12] = len(e.sightings)
    return dict(sorted(out.items(), key=lambda kv: list(CHORD_FORMULAS).index(kv[0])))


# ---------------------------------------------------------------------------
# Grip configurations
# ---------------------------------------------------------------------------
def pocket_presets(neck: Neck) -> List[Tuple[int, ...]]:
    """The grip bar's pocket cards for this tuning (3+ strings, existing on the neck), bass first."""
    if neck.string_count >= 12 or neck.neck_type == NeckType.UNIVERSAL_12:
        cards = U12_GRIP_CARDS
    elif is_c6_neck(neck):
        cards = C6_GRIP_CARDS
    else:
        cards = E9_CONSOLIDATED_TRIADS
    return [tuple(sorted(p, reverse=True)) for _, _, p in cards
            if len(p) >= 3 and max(p) <= neck.string_count]


def solver_grips(neck: Neck) -> List[Tuple[int, ...]]:
    return [tuple(sorted(g, reverse=True)) for g in VoicingSolver.get_candidate_grips(neck)]


def parse_grip_list(text: str, string_count: int) -> List[Tuple[int, ...]]:
    """'8-6-5, 6 5 4; 10/8/6' -> [(8, 6, 5), (6, 5, 4), (10, 8, 6)]. Invalid groups are skipped."""
    out: List[Tuple[int, ...]] = []
    for chunk in text.replace(";", ",").split(","):
        nums = [int(x) for x in chunk.replace("-", " ").replace("/", " ").split() if x.isdigit()]
        strings = sorted(set(nums), reverse=True)
        if len(strings) >= 3 and all(1 <= s <= string_count for s in strings):
            out.append(tuple(strings))
    return out


def grips_for_config(
    neck: Neck,
    source: str,
    sizes: Iterable[int],
    max_span: int,
    current_pocket: Optional[Set[int]] = None,
    custom: str = "",
) -> List[Tuple[int, ...]]:
    """String groups allowed by a grip configuration: a source plus size and span limits."""
    if source == GRIP_SOURCE_POCKETS:
        base = pocket_presets(neck)
    elif source == GRIP_SOURCE_SOLVER:
        base = solver_grips(neck)
    elif source == GRIP_SOURCE_CURRENT:
        base = [tuple(sorted(current_pocket, reverse=True))] if current_pocket and len(current_pocket) >= 3 else []
    elif source == GRIP_SOURCE_CUSTOM:
        base = parse_grip_list(custom, neck.string_count)
    else:
        base = all_grips(neck.string_count, sizes=ATLAS_GRIP_SIZES, max_span=ATLAS_MAX_SPAN)
    sizes = set(sizes)
    return [g for g in base if len(g) in sizes and (max(g) - min(g)) <= max_span - 1]
