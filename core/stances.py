"""Functional controller roles and resolver-backed shape validation.

Engines describe stances with *role tokens* ("A", "B", "D", "C6P6", ...) instead of hard-coded
controller IDs. Roles are detected from what each controller does to the open tuning, so they
work on any copedant (Franklin P1 shifts, BE C6 pedals P1-P5 labelled P4-P8, 'VL' vs 'LKV', ...).
Tokens that are not role names are treated as literal controller IDs.

Use `grip_matches_chord` to verify that a shape really sounds the chord it is labelled with.
"""

from typing import Callable, Dict, Iterable, List, Optional, Set

from core.models import CopedantChange, Neck
from core.resolver import FretboardResolver
from core.theory import CHORD_FORMULAS, NOTE_TO_SEMITONE

PC_C, PC_D, PC_E, PC_G, PC_GS, PC_A, PC_B = 0, 2, 4, 7, 8, 9, 11

# role -> (is_pedal, predicate(changes_by_open_pitch_class))
_RoleTest = Callable[[Dict[int, Set[int]]], bool]


def _deltas_by_pc(neck: Neck, ctrl: CopedantChange) -> Dict[int, Set[int]]:
    """Maps open-string pitch class -> set of deltas applied to strings with that pitch class."""
    pc_of = {sp.string_number: sp.midi_note % 12 for sp in neck.open_tuning}
    out: Dict[int, Set[int]] = {}
    for s_num, delta in ctrl.changes.items():
        if delta and s_num in pc_of:
            out.setdefault(pc_of[s_num], set()).add(delta)
    return out


def _has(d: Dict[int, Set[int]], pc: int, delta: int) -> bool:
    return delta in d.get(pc, set())


def _untouched(d: Dict[int, Set[int]], pc: int) -> bool:
    return pc not in d


ROLE_TESTS: Dict[str, tuple] = {
    # --- E9 (Emmons/Day naming) ---
    "A": (True, lambda d: _has(d, PC_B, 2) and _untouched(d, PC_E) and _untouched(d, PC_GS)),   # B -> C#
    "B": (True, lambda d: _has(d, PC_GS, 1) and _untouched(d, PC_E) and _untouched(d, PC_B)),   # G# -> A
    "C": (True, lambda d: _has(d, PC_E, 2) and _has(d, PC_B, 2)),                                # E -> F#, B -> C#
    "F": (False, lambda d: _has(d, PC_E, 1)),                                                    # E -> F lever
    "D": (False, lambda d: _has(d, PC_E, -1) and not _has(d, PC_E, 1)),                          # E -> Eb lever
    "BL": (False, lambda d: _has(d, PC_B, -1) and _untouched(d, PC_E)),                          # B -> Bb lever
    # --- C6 (standard pedal numbering P4..P8) ---
    "C6P4": (True, lambda d: _has(d, PC_A, 2) and not _has(d, PC_C, 2)),                         # A -> B
    "C6P5": (True, lambda d: _has(d, PC_G, -1)),                                                 # G -> F#
    "C6P6": (True, lambda d: _has(d, PC_E, -1)),                                                 # E -> Eb
    "C6P7": (True, lambda d: _has(d, PC_C, 2) and _has(d, PC_A, 2)),                             # C -> D, A -> B
    "C6P8": (True, lambda d: _has(d, PC_C, -3) or (_has(d, PC_C, 1) and _has(d, PC_D, 1))),      # C -> A / C#, D#
}
ROLE_NAMES = frozenset(ROLE_TESTS)


def _pedal_sort_key(cid: str):
    return (int(cid[1:]) if cid[1:].isdigit() else 999, cid)


def detect_roles(neck: Neck) -> Dict[str, str]:
    """Returns role -> controller ID for every role this neck provides (first match by position)."""
    roles: Dict[str, str] = {}
    pedal_ids = sorted(neck.pedals, key=_pedal_sort_key)
    lever_ids = sorted(neck.knee_levers)
    for role, (is_pedal, test) in ROLE_TESTS.items():
        pool = pedal_ids if is_pedal else lever_ids
        group = neck.pedals if is_pedal else neck.knee_levers
        for cid in pool:
            if test(_deltas_by_pc(neck, group[cid])):
                roles[role] = cid
                break
    return roles


def resolve_stance(neck: Neck, tokens: Iterable[str], roles: Optional[Dict[str, str]] = None) -> Optional[Set[str]]:
    """Maps role tokens / literal IDs to controller IDs. Returns None if any token is unavailable."""
    roles = detect_roles(neck) if roles is None else roles
    defined = set(neck.pedals) | set(neck.knee_levers)
    out: Set[str] = set()
    for tok in tokens:
        cid = roles.get(tok) if tok in ROLE_NAMES else (tok if tok in defined else None)
        if cid is None:
            return None
        out.add(cid)
    return out


def grip_pitch_classes(neck: Neck, fret: int, controllers: Iterable[str], strings: Iterable[int]) -> Optional[Set[int]]:
    states = {s.string_number: s for s in FretboardResolver.resolve_neck_state(neck, fret, set(controllers))}
    strings = list(strings)
    if not strings or any(s not in states for s in strings):
        return None
    return {states[s].pitch_class for s in strings}


def grip_matches_chord(
    neck: Neck,
    fret: int,
    controllers: Iterable[str],
    strings: Iterable[int],
    root: str,
    chord_type: str,
    require_root: bool = True,
) -> bool:
    """True if every grip string sounds a tone of `root chord_type`, the root is present (unless
    require_root=False), and the grip contains min(#chord tones, #strings) distinct tones."""
    if root not in NOTE_TO_SEMITONE or chord_type not in CHORD_FORMULAS or fret < 0:
        return False
    strings = list(strings)
    pcs = grip_pitch_classes(neck, fret, controllers, strings)
    if pcs is None:
        return False
    root_pc = NOTE_TO_SEMITONE[root]
    tones = {(root_pc + k) % 12 for k in CHORD_FORMULAS[chord_type]}
    if not pcs <= tones:
        return False
    if require_root and root_pc not in pcs:
        return False
    return len(pcs) >= min(len(tones), len(set(strings)))


def is_c6_neck(neck: Neck) -> bool:
    from core.models import NeckType

    return neck.neck_type == NeckType.C6 or "C6" in neck.name
