"""Compare Copedants (E-25): what a copedant change adds to or removes from the chord vocabulary.

Every stance moves up and down the neck as a unit, so chord availability does not depend on the
bar position. The scan therefore runs once at fret 0 and stores chord roots as pitch classes. The
display transposes them to any bar fret (`describe_delta(..., fret=N)`).

A *sighting* is one way to play a chord: a stance (controllers, possibly `<ID>_HALF` tokens)
plus a grip (3 or 4 strings within a 5-string span). Every pitch goes through
`FretboardResolver.resolve_neck_state` (splits and half-stops included), and every reported
sighting is re-checked with `stances.grip_matches_chord`.
"""

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from core.models import CopedantChange, HalfStopRule, Neck, SplitRule, StringPitch
from core.resolver import FretboardResolver
from core.stances import grip_matches_chord, is_c6_neck
from core.theory import (
    CHORD_FORMULAS,
    CHORD_SYMBOL_SUFFIX,
    NOTE_NAMES_SHARP,
    get_nashville_chord_symbol,
    midi_to_note_name,
    spell_pc,
)
from core.voicing_solver import VoicingSolver

logger = logging.getLogger(__name__)

REFERENCE_FRET = 0

# UI filter groups over CHORD_FORMULAS keys.
CHORD_GROUPS: Dict[str, Tuple[str, ...]] = {
    "Triads": ("Major", "Minor", "Diminished", "Augmented", "Sus4"),
    "6ths & 7ths": (
        "Major 6th", "Minor 6th", "Dominant 7th", "Major 7th", "Minor 7th",
        "Half-Diminished", "Diminished 7th", "Major 7th #5", "Dominant 7b5", "Dominant 7#5",
    ),
}
CHORD_GROUPS["Extensions"] = tuple(
    t for t in CHORD_FORMULAS if not any(t in g for g in CHORD_GROUPS.values())
)

# Inversions: which chord tone is in the bass, counted in stacked thirds
# (R = root position, 3rd/sus4 = 1st, 5th = 2nd, 7th/6th = 3rd, anything higher = extension).
INVERSION_NAMES = {0: "Root position", 1: "1st inversion", 2: "2nd inversion", 3: "3rd inversion",
                   4: "Extension in bass"}
INVERSION_SHORT = {0: "root pos.", 1: "1st inv.", 2: "2nd inv.", 3: "3rd inv.", 4: "ext. in bass"}
_LABEL_DEGREE = {
    "R": 0,
    "b3": 1, "3": 1, "4": 1,
    "b5": 2, "5": 2, "#5": 2,
    "6": 3, "bb7": 3, "b7": 3, "7": 3,
    "9": 4, "b9": 4, "#9": 4, "11": 4, "13": 4,
}


def inversion_index(chord_type: str, bass_interval: int) -> int:
    """0 root position, 1 first, 2 second, 3 third inversion, 4 an extension (9/11/13) in the bass;
    -1 if unknown. In a 6th chord the 6 counts as the 4th voice (C6 over A = 3rd inversion)."""
    if bass_interval < 0:
        return -1
    label = CHORD_FORMULAS.get(chord_type, {}).get(bass_interval % 12)
    if chord_type == "6/9" and label == "9":
        return 4
    return _LABEL_DEGREE.get(label, -1)


def inversion_name(chord_type: str, bass_interval: int) -> str:
    idx = inversion_index(chord_type, bass_interval)
    if idx < 0:
        return ""
    name = INVERSION_NAMES[idx]
    label = CHORD_FORMULAS.get(chord_type, {}).get(bass_interval % 12, "")
    return f"{name} ({label} in bass)" if idx else name


STATUS_ORDER = ("new_chord", "lost_chord", "new_ways", "fewer_ways", "changed_ways")
STATUS_TITLES = {
    "new_chord": "New chords",
    "lost_chord": "Lost chords",
    "new_ways": "More ways to play",
    "fewer_ways": "Fewer ways to play",
    "changed_ways": "Ways changed",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class CopedantDiffItem:
    """One atomic difference between two copedants."""
    kind: str                       # controller_added/_removed, pull_added/_removed/_changed,
                                    # split_*, half_stop_*, tuning_changed
    description: str
    controller_id: str = ""
    string_number: int = 0
    old_delta: Optional[int] = None
    new_delta: Optional[int] = None
    key: tuple = field(default=(), repr=False)   # lookup key used by apply_item


@dataclass(frozen=True)
class ChordSighting:
    root_pc: int                    # pitch class of the root at fret 0
    chord_type: str                 # CHORD_FORMULAS key
    controllers: Tuple[str, ...]    # sorted controller IDs / "<ID>_HALF" tokens
    strings: Tuple[int, ...]        # grip strings, bass (highest number) first
    is_shell: bool = False          # the 5th is omitted
    # Semitones from the root to the lowest-sounding note of the grip (resolved pitch, so pedal
    # pulls that cross strings are honoured). Not part of equality: the same stance + grip is the
    # same way to play the chord. -1 = unknown.
    bass_interval: int = field(default=-1, compare=False)

    @property
    def inversion(self) -> int:
        return inversion_index(self.chord_type, self.bass_interval)


@dataclass
class ChordDelta:
    root_pc: int
    chord_type: str
    status: str                     # one of STATUS_ORDER
    gained: List[ChordSighting]
    lost: List[ChordSighting]

    @property
    def headline(self) -> Optional[ChordSighting]:
        pool = self.gained or self.lost
        return pool[0] if pool else None


@dataclass
class ComparisonReport:
    scope: str
    deltas: List[ChordDelta]
    affected_stances: List[Tuple[str, ...]] = field(default_factory=list)
    # Full scans of both sides, so filter_report can recompute statuses inside a filter.
    base_scan: Dict[Tuple[int, str], Set["ChordSighting"]] = field(default_factory=dict, repr=False)
    mod_scan: Dict[Tuple[int, str], Set["ChordSighting"]] = field(default_factory=dict, repr=False)

    @property
    def gained_count(self) -> int:
        return sum(len(d.gained) for d in self.deltas)

    @property
    def lost_count(self) -> int:
        return sum(len(d.lost) for d in self.deltas)


@dataclass
class CopedantComparison:
    items: List[CopedantDiffItem]
    total: ComparisonReport
    per_item: List[Tuple[CopedantDiffItem, ComparisonReport]]
    interactions: ComparisonReport


# ---------------------------------------------------------------------------
# Diffing copedants
# ---------------------------------------------------------------------------
def _fmt_delta(d: Optional[int]) -> str:
    return "none" if d is None else f"{d:+d}"


def _group_of(neck: Neck, cid: str) -> Dict[str, CopedantChange]:
    return neck.pedals if cid in neck.pedals else neck.knee_levers


def _active_splits(neck: Neck) -> Dict[Tuple[int, FrozenSet[str]], SplitRule]:
    return {(s.string_number, frozenset(s.controllers)): s
            for s in neck.splits if s.is_active and len(s.controllers) >= 2}


def _active_half_stops(neck: Neck) -> Dict[Tuple[str, int], HalfStopRule]:
    return {(h.controller_id, h.string_number): h for h in neck.half_stops if h.is_active}


def diff_copedants(base: Neck, modified: Neck) -> List[CopedantDiffItem]:
    """Atomic differences, matched by controller ID (positional; labels are ignored)."""
    items: List[CopedantDiffItem] = []

    # 1. Open tuning
    b_tune = {sp.string_number: sp for sp in base.open_tuning}
    m_tune = {sp.string_number: sp for sp in modified.open_tuning}
    for s in sorted(set(b_tune) | set(m_tune)):
        b, m = b_tune.get(s), m_tune.get(s)
        if b and m and b.midi_note == m.midi_note:
            continue
        if b and m:
            desc = f"String {s} retuned {midi_to_note_name(b.midi_note)} → {midi_to_note_name(m.midi_note)}"
        elif m:
            desc = f"String {s} added ({midi_to_note_name(m.midi_note)})"
        else:
            desc = f"String {s} removed ({midi_to_note_name(b.midi_note)})"
        items.append(CopedantDiffItem(
            "tuning_changed", desc, string_number=s,
            old_delta=b.midi_note if b else None, new_delta=m.midi_note if m else None,
            key=("tuning", s),
        ))

    # 2. Controllers and their pulls
    for attr in ("pedals", "knee_levers"):
        b_grp, m_grp = getattr(base, attr), getattr(modified, attr)
        for cid in sorted(set(b_grp) | set(m_grp), key=lambda c: (len(c), c)):
            b, m = b_grp.get(cid), m_grp.get(cid)
            if b is None:
                pulls = ", ".join(f"str {s} {d:+d}" for s, d in sorted(m.changes.items()) if d)
                items.append(CopedantDiffItem("controller_added", f"{cid} added ({pulls or 'no pulls'})",
                                              controller_id=cid, key=(attr, cid)))
                continue
            if m is None:
                items.append(CopedantDiffItem("controller_removed", f"{cid} removed",
                                              controller_id=cid, key=(attr, cid)))
                continue
            b_ch = {s: d for s, d in b.changes.items() if d}
            m_ch = {s: d for s, d in m.changes.items() if d}
            for s in sorted(set(b_ch) | set(m_ch)):
                od, nd = b_ch.get(s), m_ch.get(s)
                if od == nd:
                    continue
                if od is None:
                    kind, desc = "pull_added", f"{cid}: new pull on string {s}, {nd:+d}"
                elif nd is None:
                    kind, desc = "pull_removed", f"{cid}: pull on string {s} removed (was {od:+d})"
                else:
                    kind, desc = "pull_changed", f"{cid}: string {s} changed {od:+d} → {nd:+d}"
                items.append(CopedantDiffItem(kind, desc, controller_id=cid, string_number=s,
                                              old_delta=od, new_delta=nd, key=(attr, cid, s)))

    # 3. Splits (active rules only)
    b_sp, m_sp = _active_splits(base), _active_splits(modified)
    for k in sorted(set(b_sp) | set(m_sp), key=lambda k: (k[0], sorted(k[1]))):
        b, m = b_sp.get(k), m_sp.get(k)
        if b and m and b.semitone_delta == m.semitone_delta:
            continue
        ctrls = "+".join(sorted(k[1]))
        od = b.semitone_delta if b else None
        nd = m.semitone_delta if m else None
        kind = "split_added" if b is None else ("split_removed" if m is None else "split_changed")
        desc = f"Split {ctrls} on string {k[0]}: {_fmt_delta(od)} → {_fmt_delta(nd)}"
        items.append(CopedantDiffItem(kind, desc, controller_id=ctrls, string_number=k[0],
                                      old_delta=od, new_delta=nd, key=("splits", k)))

    # 4. Half-stops (active rules only)
    b_hs, m_hs = _active_half_stops(base), _active_half_stops(modified)
    for k in sorted(set(b_hs) | set(m_hs)):
        b, m = b_hs.get(k), m_hs.get(k)
        if b and m and b.semitone_delta == m.semitone_delta:
            continue
        od = b.semitone_delta if b else None
        nd = m.semitone_delta if m else None
        kind = "half_stop_added" if b is None else ("half_stop_removed" if m is None else "half_stop_changed")
        desc = f"Half-stop {k[0]} on string {k[1]}: {_fmt_delta(od)} → {_fmt_delta(nd)}"
        items.append(CopedantDiffItem(kind, desc, controller_id=k[0], string_number=k[1],
                                      old_delta=od, new_delta=nd, key=("half_stops", k)))
    return items


def apply_item(base: Neck, modified: Neck, item: CopedantDiffItem) -> Neck:
    """A copy of `base` with only `item` (taken from `modified`) applied."""
    neck = deepcopy(base)
    tag = item.key[0] if item.key else ""

    if tag == "tuning":
        s = item.key[1]
        m = next((sp for sp in modified.open_tuning if sp.string_number == s), None)
        neck.open_tuning = [sp for sp in neck.open_tuning if sp.string_number != s]
        if m is not None:
            neck.open_tuning.append(StringPitch(m.string_number, m.midi_note, m.note_name))
        neck.open_tuning.sort(key=lambda sp: sp.string_number)
        neck.string_count = len(neck.open_tuning)

    elif tag in ("pedals", "knee_levers"):
        grp = getattr(neck, tag)
        cid = item.key[1]
        if len(item.key) == 2:  # whole controller added / removed
            src = getattr(modified, tag).get(cid)
            if src is None:
                grp.pop(cid, None)
            else:
                grp[cid] = deepcopy(src)
        else:
            s = item.key[2]
            ctrl = grp[cid]
            if item.new_delta is None:
                ctrl.changes.pop(s, None)
            else:
                ctrl.changes[s] = item.new_delta

    elif tag == "splits":
        s_num, ctrls = item.key[1]
        neck.splits = [r for r in neck.splits
                       if not (r.is_active and r.string_number == s_num and frozenset(r.controllers) == ctrls)]
        src = _active_splits(modified).get(item.key[1])
        if src is not None:
            neck.splits.append(deepcopy(src))

    elif tag == "half_stops":
        cid, s_num = item.key[1]
        neck.half_stops = [h for h in neck.half_stops
                           if not (h.is_active and h.controller_id == cid and h.string_number == s_num)]
        src = _active_half_stops(modified).get(item.key[1])
        if src is not None:
            neck.half_stops.append(deepcopy(src))
    return neck


# ---------------------------------------------------------------------------
# Chord scanning
# ---------------------------------------------------------------------------
def all_grips(string_count: int, sizes: Iterable[int] = (3, 4), max_span: int = 5) -> List[Tuple[int, ...]]:
    """Every string set of the given sizes whose outer strings are at most `max_span - 1` apart.
    Returned bass first (highest string number first)."""
    out: List[Tuple[int, ...]] = []
    strings = range(1, string_count + 1)
    for size in sizes:
        for combo in combinations(strings, size):
            if combo[-1] - combo[0] <= max_span - 1:
                out.append(tuple(sorted(combo, reverse=True)))
    return out


def candidate_stances(neck: Neck) -> List[Tuple[str, ...]]:
    """VoicingSolver's ergonomic stances, plus a `<ID>_HALF` variant for each controller with an
    active half-stop rule (rule 7)."""
    half_ids = {h.controller_id for h in neck.half_stops if h.is_active}
    seen: Set[Tuple[str, ...]] = set()
    out: List[Tuple[str, ...]] = []
    for st in VoicingSolver.candidate_stances(neck):
        variants = [set(st)]
        for cid in sorted(st & half_ids):
            variants.append((set(st) - {cid}) | {f"{cid}_HALF"})
        for v in variants:
            key = tuple(sorted(v))
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out


def _build_chord_lookup(chord_types: Optional[Iterable[str]] = None):
    """frozenset(semitones from root) -> [(chord_type, is_shell)]."""
    exact: Dict[FrozenSet[int], List[str]] = {}
    shell: Dict[FrozenSet[int], List[str]] = {}
    for ctype in (chord_types or CHORD_FORMULAS):
        formula = CHORD_FORMULAS[ctype]
        tones = frozenset(formula)
        exact.setdefault(tones, []).append(ctype)
        if len(tones) >= 4 and 7 in formula and formula[7] == "5":
            shell.setdefault(tones - {7}, []).append(ctype)
    return exact, shell


def _match_pcs(pcs: FrozenSet[int], grip_len: int, lookup) -> List[Tuple[int, str, bool]]:
    """(root_pc, chord_type, is_shell) for every chord this pitch-class set spells exactly.
    Shell (no-5th) matches are only used when no exact spelling exists for any root."""
    exact, shell = lookup
    hits: List[Tuple[int, str, bool]] = []
    for root in pcs:
        rel = frozenset((p - root) % 12 for p in pcs)
        for ctype in exact.get(rel, ()):
            hits.append((root, ctype, False))
    if hits:
        return hits
    for root in pcs:
        rel = frozenset((p - root) % 12 for p in pcs)
        for ctype in shell.get(rel, ()):
            # Same distinct-tone rule as grip_matches_chord.
            if len(pcs) >= min(len(CHORD_FORMULAS[ctype]), grip_len):
                hits.append((root, ctype, True))
    return hits


def _stance_pcs(neck: Neck, stance: Tuple[str, ...], fret: int) -> Dict[int, int]:
    """string number -> sounding MIDI note for this stance (pitch class = value % 12)."""
    states = FretboardResolver.resolve_neck_state(neck, fret, set(stance))
    return {s.string_number: s.active_midi for s in states}


def scan_chords(
    neck: Neck,
    fret: int = REFERENCE_FRET,
    grips: Optional[List[Tuple[int, ...]]] = None,
    chord_types: Optional[Iterable[str]] = None,
    stances: Optional[List[Tuple[str, ...]]] = None,
) -> Dict[Tuple[int, str], Set[ChordSighting]]:
    """(root_pc, chord_type) -> every sighting on this neck at `fret`."""
    grips = grips if grips is not None else all_grips(neck.string_count)
    lookup = _build_chord_lookup(chord_types)
    stances = stances if stances is not None else candidate_stances(neck)
    memo: Dict[Tuple[FrozenSet[int], int], List[Tuple[int, str, bool]]] = {}
    out: Dict[Tuple[int, str], Set[ChordSighting]] = {}
    for st in stances:
        midi_by_str = _stance_pcs(neck, st, fret)
        for grip in grips:
            if any(s not in midi_by_str for s in grip):
                continue
            pcs = frozenset(midi_by_str[s] % 12 for s in grip)
            bass_pc = min(midi_by_str[s] for s in grip) % 12
            mk = (pcs, len(grip))
            if mk not in memo:
                memo[mk] = _match_pcs(pcs, len(grip), lookup)
            for root_pc, ctype, is_shell in memo[mk]:
                root_at_fret0 = (root_pc - fret) % 12
                out.setdefault((root_at_fret0, ctype), set()).add(
                    ChordSighting(root_at_fret0, ctype, st, grip, is_shell, (bass_pc - root_pc) % 12))
    return out


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def sighting_sort_key(s: ChordSighting):
    return (len(s.controllers), s.is_shell, len(s.strings), s.controllers, s.strings)


def _verified(neck: Neck, sightings: Iterable[ChordSighting]) -> List[ChordSighting]:
    out = []
    for s in sightings:
        if grip_matches_chord(neck, REFERENCE_FRET, s.controllers, s.strings,
                              NOTE_NAMES_SHARP[s.root_pc], s.chord_type):
            out.append(s)
        else:  # would mean the matcher and the verification rule disagree
            logger.warning("Copedant compare: dropped unverified sighting %s on %s", s, neck.name)
    return sorted(out, key=sighting_sort_key)


def _status(had: bool, has: bool, gained, lost) -> str:
    if not had and has:
        return "new_chord"
    if had and not has:
        return "lost_chord"
    if gained and not lost:
        return "new_ways"
    if lost and not gained:
        return "fewer_ways"
    return "changed_ways"


def chord_group(chord_type: str) -> str:
    return next((g for g, types in CHORD_GROUPS.items() if chord_type in types), "Extensions")


_GROUP_RANK = {g: i for i, g in enumerate(CHORD_GROUPS)}


def _delta_sort_key(d: ChordDelta):
    h = d.headline
    return (STATUS_ORDER.index(d.status), _GROUP_RANK[chord_group(d.chord_type)],
            h.is_shell if h else True, len(h.controllers) if h else 99, d.root_pc, d.chord_type)


def _changed_stances(base_scan_pcs, mod_scan_pcs) -> List[Tuple[str, ...]]:
    keys = set(base_scan_pcs) | set(mod_scan_pcs)
    return sorted(k for k in keys if base_scan_pcs.get(k) != mod_scan_pcs.get(k))


def _diff_scans(
    scope: str,
    base: Neck,
    modified: Neck,
    base_scan: Dict[Tuple[int, str], Set[ChordSighting]],
    mod_scan: Dict[Tuple[int, str], Set[ChordSighting]],
    affected: List[Tuple[str, ...]],
) -> ComparisonReport:
    deltas: List[ChordDelta] = []
    for key in set(base_scan) | set(mod_scan):
        b = base_scan.get(key, set())
        m = mod_scan.get(key, set())
        if b == m:
            continue
        gained = _verified(modified, m - b)
        lost = _verified(base, b - m)
        if not gained and not lost:
            continue
        deltas.append(ChordDelta(key[0], key[1], _status(bool(b), bool(m), gained, lost), gained, lost))
    deltas.sort(key=_delta_sort_key)
    return ComparisonReport(scope, deltas, affected, base_scan, mod_scan)


def compare_copedants(
    base: Neck, modified: Neck, chord_types: Optional[Iterable[str]] = None
) -> CopedantComparison:
    """Total effect of every change, the effect of each change alone, and the combined effects
    that no single change explains."""
    chord_types = list(chord_types) if chord_types is not None else None
    items = diff_copedants(base, modified)

    def stance_pcs(neck: Neck):
        return {st: _stance_pcs(neck, st, REFERENCE_FRET) for st in candidate_stances(neck)}

    def scan(neck: Neck, pcs_map):
        return scan_chords(neck, grips=all_grips(neck.string_count),
                           chord_types=chord_types, stances=list(pcs_map))

    base_pcs = stance_pcs(base)
    base_scan = scan(base, base_pcs)

    if not items:
        empty = ComparisonReport("All changes", [])
        return CopedantComparison([], empty, [], ComparisonReport("Combined effects", []))

    mod_pcs = stance_pcs(modified)
    total = _diff_scans("All changes", base, modified, base_scan, scan(modified, mod_pcs),
                        _changed_stances(base_pcs, mod_pcs))

    per_item: List[Tuple[CopedantDiffItem, ComparisonReport]] = []
    explained_gain: Set[ChordSighting] = set()
    explained_loss: Set[ChordSighting] = set()
    for item in items:
        variant = apply_item(base, modified, item)
        v_pcs = stance_pcs(variant)
        rep = _diff_scans(item.description, base, variant, base_scan, scan(variant, v_pcs),
                          _changed_stances(base_pcs, v_pcs))
        per_item.append((item, rep))
        for d in rep.deltas:
            explained_gain.update(d.gained)
            explained_loss.update(d.lost)

    inter: List[ChordDelta] = []
    for d in total.deltas:
        g = [s for s in d.gained if s not in explained_gain]
        lo = [s for s in d.lost if s not in explained_loss]
        if g or lo:
            inter.append(ChordDelta(d.root_pc, d.chord_type, d.status, g, lo))
    interactions = ComparisonReport("Combined effects", inter, [], total.base_scan, total.mod_scan)
    return CopedantComparison(items, total, per_item, interactions)


# ---------------------------------------------------------------------------
# Filtering (drill-down)
# ---------------------------------------------------------------------------
def base_controllers(s: ChordSighting) -> Set[str]:
    """Controller IDs of a sighting with half-stop tokens folded onto their controller."""
    return {c.replace("_HALF", "") for c in s.controllers}


CONTROLLER_MATCH_EXACT = "exact"      # exactly the selected controllers
CONTROLLER_MATCH_INCLUDE = "include"  # the selected controllers, plus any others
CONTROLLER_MATCH_ONLY = "only"        # nothing but the selected controllers (open bar included)


def controllers_match(used: Set[str], selected: Set[str], mode: str) -> bool:
    if mode == CONTROLLER_MATCH_EXACT:
        return used == selected
    if mode == CONTROLLER_MATCH_INCLUDE:
        return selected <= used
    return used <= selected


def sighting_filter(
    allowed_controllers: Optional[Iterable[str]] = None,
    include_shells: bool = True,
    max_controllers: Optional[int] = None,
    grips: Optional[Iterable[Iterable[int]]] = None,
    inversions: Optional[Iterable[int]] = None,
    controller_match: str = CONTROLLER_MATCH_ONLY,
):
    """Predicate over sightings, shared by Compare Copedants and the Chord Atlas.
    `allowed_controllers` + `controller_match` filter on the controllers a way uses (half-stop
    tokens count as their controller): with {"P1", "P2"}, "exact" keeps P1+P2 only, "include"
    keeps P1+P2 plus anything (e.g. P1+P2+LKL), "only" keeps open, P1, P2 and P1+P2.
    `grips` keeps only those string sets."""
    allowed = set(allowed_controllers) if allowed_controllers is not None else None
    grip_set = {frozenset(g) for g in grips} if grips is not None else None
    inv_set = set(inversions) if inversions is not None else None

    def keep(s: ChordSighting) -> bool:
        if not include_shells and s.is_shell:
            return False
        if allowed is not None and not controllers_match(base_controllers(s), allowed, controller_match):
            return False
        if max_controllers is not None and len(s.controllers) > max_controllers:
            return False
        if grip_set is not None and frozenset(s.strings) not in grip_set:
            return False
        if inv_set is not None and s.inversion not in inv_set:
            return False
        return True

    return keep


def filter_report(
    report: ComparisonReport,
    chord_types: Optional[Iterable[str]] = None,
    allowed_controllers: Optional[Iterable[str]] = None,
    include_shells: bool = True,
    max_controllers: Optional[int] = None,
    grips: Optional[Iterable[Iterable[int]]] = None,
    inversions: Optional[Iterable[int]] = None,
    controller_match: str = CONTROLLER_MATCH_ONLY,
) -> ComparisonReport:
    """Keeps only the sightings that pass the filters (see `sighting_filter`); a chord whose
    sightings all drop out is removed."""
    types = set(chord_types) if chord_types is not None else None
    keep = sighting_filter(allowed_controllers, include_shells, max_controllers, grips, inversions,
                           controller_match)

    out: List[ChordDelta] = []
    for d in report.deltas:
        if types is not None and d.chord_type not in types:
            continue
        g = [s for s in d.gained if keep(s)]
        lo = [s for s in d.lost if keep(s)]
        if not (g or lo):
            continue
        key = (d.root_pc, d.chord_type)
        if report.base_scan or report.mod_scan:
            # Status within the filter: "new chord" = not playable before with these controllers.
            had = any(keep(s) for s in report.base_scan.get(key, ()))
            has = any(keep(s) for s in report.mod_scan.get(key, ()))
            status = _status(had, has, g, lo)
        else:
            status = d.status
        out.append(ChordDelta(d.root_pc, d.chord_type, status, g, lo))
    out.sort(key=_delta_sort_key)
    return ComparisonReport(report.scope, out, report.affected_stances, report.base_scan, report.mod_scan)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
def root_name(root_pc: int, fret: int = 0) -> str:
    """Display name in the global sharps/flats preference (theory.set_accidental_preference)."""
    return spell_pc(root_pc + fret)


def chord_symbol(root_pc: int, chord_type: str, fret: int = 0) -> str:
    return f"{root_name(root_pc, fret)}{CHORD_SYMBOL_SUFFIX.get(chord_type, '')}"


def neck_tonic_pc(neck: Neck) -> int:
    """Open-position key of the neck: C for C6, E otherwise (as in relative_moves)."""
    return 0 if is_c6_neck(neck) else 4


def nashville(neck: Neck, root_pc: int, chord_type: str, fret: int = 0) -> str:
    key = root_name(neck_tonic_pc(neck), fret)
    return get_nashville_chord_symbol(root_name(root_pc, fret), key, family=chord_type)


def format_controllers(controllers: Iterable[str]) -> str:
    parts = [c.replace("_HALF", " (half)") for c in controllers]
    return " + ".join(parts) if parts else "open (no pedals)"


def format_sighting(s: ChordSighting) -> str:
    shell = " (no 5th)" if s.is_shell else ""
    inv = INVERSION_SHORT.get(s.inversion)
    inv = f" · {inv}" if inv else ""
    return f"{format_controllers(s.controllers)}, strings {'-'.join(map(str, s.strings))}{shell}{inv}"


def describe_delta(delta: ChordDelta, neck: Neck, fret: int = 0) -> str:
    """One plain-language line, e.g. "NEW chord: C#m (6-) — P1 + LKR, strings 6-5-4 (+3 more ways)"."""
    name = f"{chord_symbol(delta.root_pc, delta.chord_type, fret)} ({nashville(neck, delta.root_pc, delta.chord_type, fret)})"
    lead = {
        "new_chord": "NEW chord",
        "lost_chord": "LOST chord",
        "new_ways": "More ways",
        "fewer_ways": "Fewer ways",
        "changed_ways": "Ways changed",
    }[delta.status]
    pool = delta.gained if delta.status in ("new_chord", "new_ways", "changed_ways") and delta.gained else delta.lost
    head = pool[0] if pool else None
    text = f"{lead}: {name}"
    if head:
        verb = "with" if pool is delta.gained else "was"
        text += f" — {verb} {format_sighting(head)}"
        if len(pool) > 1:
            text += f" (+{len(pool) - 1} more)"
    if delta.status == "changed_ways":
        text += f" [+{len(delta.gained)} / −{len(delta.lost)}]"
    return text
