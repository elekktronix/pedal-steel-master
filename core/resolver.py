"""Resolver computing sounding notes, harmonic chord intervals, scale degrees,
mechanical changer split overrides, and intermediate half-stops.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from core.models import Neck
from core.theory import (
    CHORD_FORMULAS,
    NOTE_TO_SEMITONE,
    SCALE_FORMULAS,
    get_interval,
    get_pitch_class,
    midi_to_note_name,
)


@dataclass
class ActiveStringState:
    string_number: int
    open_midi: int
    active_midi: int
    active_note_name: str
    pitch_class: int
    interval_label: Optional[str] = None
    is_chord_tone: bool = False
    is_split_applied: bool = False   # True ONLY when a 2+ controller split override governs this string
    is_half_stop: bool = False       # True when an intermediate half-stop is actively engaged


class FretboardResolver:
    @staticmethod
    def resolve_neck_state(
        neck: Neck,
        fret: int,
        engaged_levers: Set[str],
        target_root_name: Optional[str] = None,
        target_chord_type: Optional[str] = None,
        target_scale_name: Optional[str] = None,
    ) -> List[ActiveStringState]:
        """Calculates sounding pitch honoring mechanical changer split overrides
        and intermediate half-stop clicks, then maps harmony.
        """
        active_strings: List[ActiveStringState] = []

        target_formula: Optional[Dict[int, str]] = None
        root_pc: Optional[int] = None

        if target_root_name and target_root_name != "None":
            root_pc = NOTE_TO_SEMITONE.get(target_root_name.strip().capitalize())
            if target_scale_name and target_scale_name in SCALE_FORMULAS:
                target_formula = SCALE_FORMULAS[target_scale_name]
            elif target_chord_type and target_chord_type in CHORD_FORMULAS:
                target_formula = CHORD_FORMULAS[target_chord_type]

        all_controllers = {**neck.pedals, **neck.knee_levers}

        # 1. Harvest active half-stops: (controller_id, string_num) -> semitone_delta
        active_half_stops: Dict[Tuple[str, int], int] = {}
        for rule in getattr(neck, "half_stops", []):
            if rule.is_active:
                active_half_stops[(rule.controller_id, rule.string_number)] = int(rule.semitone_delta)

        # 2. Harvest active changer splits: (string_num, frozenset(controllers)) -> semitone_delta
        active_splits: Dict[Tuple[int, frozenset], int] = {}
        for rule in getattr(neck, "splits", []):
            if rule.is_active and len(rule.controllers) >= 2:
                ctrl_set = frozenset(rule.controllers)
                active_splits[(rule.string_number, ctrl_set)] = int(rule.semitone_delta)

        # 3. Harvest active pulls for each string
        # string_num -> list of (base_controller_id, semitone_delta, is_half_stop)
        string_pulls: Dict[int, List[Tuple[str, int, bool]]] = {
            sp.string_number: [] for sp in neck.open_tuning
        }

        for lever_id in engaged_levers:
            is_half = lever_id.endswith("_HALF")
            base_id = lever_id.replace("_HALF", "")

            if base_id not in all_controllers:
                continue

            ctrl_obj = all_controllers[base_id]
            for string_idx, full_delta in ctrl_obj.changes.items():
                if string_idx not in string_pulls:
                    continue

                if is_half:
                    custom_half = active_half_stops.get((base_id, string_idx))
                    if custom_half is not None:
                        effective_delta = custom_half
                    else:
                        effective_delta = 1 if full_delta > 0 else (-1 if full_delta < 0 else 0)
                else:
                    effective_delta = full_delta

                string_pulls[string_idx].append((base_id, effective_delta, is_half))

        # 4. Calculate pitch for every string
        for sp in neck.open_tuning:
            str_num = sp.string_number
            pulls = string_pulls.get(str_num, [])

            split_applied = False
            has_half_stop = any(p[2] for p in pulls)
            total_pull_delta = 0

            # Only test for split overrides if 2 or more controllers pull on the string simultaneously
            if len(pulls) >= 2:
                base_engaged = frozenset(p[0] for p in pulls)
                if (str_num, base_engaged) in active_splits:
                    total_pull_delta = active_splits[(str_num, base_engaged)]
                    split_applied = True
                else:
                    total_pull_delta = sum(p[1] for p in pulls)
            elif len(pulls) == 1:
                total_pull_delta = pulls[0][1]
                split_applied = False  # Single controller (full or half) is NEVER a changer split!

            active_midi = sp.midi_note + fret + total_pull_delta
            pc = get_pitch_class(active_midi)
            note_name = midi_to_note_name(active_midi)

            interval_label = None
            is_match = False

            if target_formula is not None and root_pc is not None:
                interval_st = get_interval(root_pc, pc)
                if interval_st in target_formula:
                    interval_label = target_formula[interval_st]
                    is_match = True

            active_strings.append(
                ActiveStringState(
                    string_number=str_num,
                    open_midi=sp.midi_note,
                    active_midi=active_midi,
                    active_note_name=note_name,
                    pitch_class=pc,
                    interval_label=interval_label,
                    is_chord_tone=is_match,
                    is_split_applied=split_applied,
                    is_half_stop=has_half_stop,
                )
            )

        return active_strings