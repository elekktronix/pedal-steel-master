"""Voice Leading Engine: parses chord progressions (.cp/.json/.cprog) and solves smooth bar motion."""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from core.models import Neck
from core.theory import CHORD_FORMULAS, NOTE_TO_SEMITONE
from core.voicing_solver import VoicingMatch, VoicingSolver

SolvedVoicing = VoicingMatch

CHORD_TYPE_MAP = {
    "Minor 7": "Minor 7th",
    "m7": "Minor 7th",
    "Major 7": "Major 7th",
    "maj7": "Major 7th",
    "7": "Dominant 7th",
    "Dominant 7": "Dominant 7th",
    "Dominant 7th": "Dominant 7th",
    "Major": "Major",
    "Minor": "Minor",
    "Diminished": "Diminished",
    "dim": "Diminished",
    "m7b5": "Half-Diminished",
    "Half-Diminished": "Half-Diminished",
}


def normalize_chord_type(raw_type: str) -> str:
    if raw_type in CHORD_FORMULAS:
        return raw_type
    mapped = CHORD_TYPE_MAP.get(raw_type)
    if mapped and mapped in CHORD_FORMULAS:
        return mapped
    variants = [
        raw_type + "th",
        raw_type.replace(" 7", " 7th"),
        raw_type.replace(" 7th", " 7"),
    ]
    for v in variants:
        if v in CHORD_FORMULAS:
            return v
    return "Major"


@dataclass
class ChordSlot:
    beat: int
    root: Optional[str] = None
    chord_type: Optional[str] = None


@dataclass
class ProgressionMeasure:
    measure_id: int
    slots: List[ChordSlot] = field(default_factory=list)

    @property
    def primary_chord(self) -> Optional[Tuple[str, str]]:
        for slot in self.slots:
            if slot.root and slot.chord_type:
                return (slot.root, slot.chord_type)
        return None


@dataclass
class ChordProgression:
    name: str
    tonal_center: str = "C"
    time_signature: str = "4/4"
    tempo: int = 120
    measures: List[ProgressionMeasure] = field(default_factory=list)

    @classmethod
    def from_json_file(cls, filepath: str) -> "ChordProgression":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "ChordProgression":
        prog = cls(
            name=data.get("name", "Untitled Progression"),
            tonal_center=data.get("tonalCenter", "C"),
            time_signature=data.get("timeSignature", "4/4"),
            tempo=data.get("tempo", 120),
        )

        for m_data in data.get("measures", []):
            measure = ProgressionMeasure(measure_id=int(m_data.get("id", 0)))
            for s_data in m_data.get("slots", []):
                beat = int(s_data.get("beat", 1))
                chord_info = s_data.get("chord")
                if chord_info:
                    raw_type = chord_info.get("type", "Major")
                    norm_type = normalize_chord_type(raw_type)
                    measure.slots.append(
                        ChordSlot(
                            beat=beat,
                            root=chord_info.get("root", "C"),
                            chord_type=norm_type,
                        )
                    )
                else:
                    measure.slots.append(ChordSlot(beat=beat))
            prog.measures.append(measure)

        return prog


@dataclass
class VoiceLeadingConstraints:
    min_fret: int = 0
    max_fret: int = 12
    max_fret_jump: int = 3
    trajectory: str = "minimal"  # "up", "down", "up_down", "down_up", "minimal", "random"
    start_fret: Optional[int] = None
    target_pocket: Optional[Set[int]] = None


class VoiceLeadingEngine:
    @classmethod
    def solve_progression(
        cls,
        neck: Neck,
        progression: ChordProgression,
        constraints: VoiceLeadingConstraints,
    ) -> List[Optional[VoicingMatch]]:
        """Solves an optimal sequence of voicings strictly honoring boundaries and trajectories."""
        measures_with_chords = [
            (idx, m.primary_chord) for idx, m in enumerate(progression.measures) if m.primary_chord
        ]

        if not measures_with_chords:
            return [None] * len(progression.measures)

        candidates_per_step: List[List[VoicingMatch]] = []

        for _, chord in measures_with_chords:
            root, ctype = chord
            norm_type = normalize_chord_type(ctype)
            needs_omission = "7" in norm_type or "9" in norm_type or "dim" in norm_type.lower()

            voicings = VoicingSolver.find_all_voicings(
                neck=neck,
                root_name=root,
                chord_type=norm_type,
                max_fret=min(24, constraints.max_fret),
                filter_awkward=True,
                omitted_intervals={"5"} if needs_omission else None,
            )

            in_range = [
                v for v in voicings
                if constraints.min_fret <= v.fret <= constraints.max_fret
            ]

            if constraints.target_pocket:
                p_list = sorted(list(constraints.target_pocket))
                pocket_matched = [v for v in in_range if v.grip_strings == p_list]
                if pocket_matched:
                    in_range = pocket_matched

            if not in_range:
                relaxed = VoicingSolver.find_all_voicings(
                    neck=neck,
                    root_name=root,
                    chord_type=norm_type,
                    max_fret=min(24, constraints.max_fret),
                    filter_awkward=False,
                    omitted_intervals={"5"} if needs_omission else None,
                )
                in_range = [
                    v for v in relaxed
                    if constraints.min_fret <= v.fret <= constraints.max_fret
                ]

            candidates_per_step.append(in_range)

        num_steps = len(candidates_per_step)
        if num_steps == 0 or any(len(c) == 0 for c in candidates_per_step):
            return [c[0] if c else None for c in candidates_per_step]

        dp: List[Dict[int, Tuple[float, Optional[int]]]] = [{} for _ in range(num_steps)]

        target_start = constraints.start_fret if constraints.start_fret is not None else constraints.min_fret
        for i, v in enumerate(candidates_per_step[0]):
            fret_dist = abs(v.fret - target_start)
            dp[0][i] = (fret_dist * 2000.0, None)

        for t in range(1, num_steps):
            prev_candidates = candidates_per_step[t - 1]
            curr_candidates = candidates_per_step[t]

            for j, curr_v in enumerate(curr_candidates):
                best_cost = float("inf")
                best_prev_idx = None

                for i, prev_v in enumerate(prev_candidates):
                    if i not in dp[t - 1]:
                        continue

                    prev_cost = dp[t - 1][i][0]
                    fret_delta = curr_v.fret - prev_v.fret
                    jump_dist = abs(fret_delta)

                    if jump_dist > constraints.max_fret_jump:
                        jump_penalty = 50000.0 * (jump_dist - constraints.max_fret_jump)
                    else:
                        jump_penalty = jump_dist * 2.0

                    traj_cost = 0.0
                    midpoint = (num_steps - 1) / 2.0

                    if constraints.trajectory == "up":
                        if fret_delta < 0:
                            traj_cost += 5000.0
                        elif fret_delta == 0:
                            traj_cost += 20.0
                    elif constraints.trajectory == "down":
                        if fret_delta > 0:
                            traj_cost += 5000.0
                        elif fret_delta == 0:
                            traj_cost += 20.0
                    elif constraints.trajectory == "up_down":
                        if t <= midpoint and fret_delta < 0:
                            traj_cost += 5000.0
                        elif t > midpoint and fret_delta > 0:
                            traj_cost += 5000.0
                    elif constraints.trajectory == "down_up":
                        if t <= midpoint and fret_delta > 0:
                            traj_cost += 5000.0
                        elif t > midpoint and fret_delta < 0:
                            traj_cost += 5000.0
                    elif constraints.trajectory == "minimal":
                        traj_cost = jump_dist * 12.0
                    elif constraints.trajectory == "random":
                        import random
                        traj_cost = random.uniform(0.0, 40.0)

                    pedal_changes = len(set(prev_v.engaged_levers).symmetric_difference(set(curr_v.engaged_levers)))
                    total_cost = prev_cost + jump_penalty + traj_cost + (pedal_changes * 3.0)

                    if total_cost < best_cost:
                        best_cost = total_cost
                        best_prev_idx = i

                dp[t][j] = (best_cost, best_prev_idx)

        last_step = dp[-1]
        if not last_step:
            return [None] * len(progression.measures)

        best_last_idx = min(last_step.keys(), key=lambda idx: last_step[idx][0])
        path = [best_last_idx]

        for t in range(num_steps - 1, 0, -1):
            prev_idx = dp[t][path[-1]][1]
            path.append(prev_idx if prev_idx is not None else 0)

        path.reverse()

        solved_map: Dict[int, VoicingMatch] = {}
        for (step_idx, _), cand_idx in zip(measures_with_chords, path):
            solved_map[step_idx] = candidates_per_step[len(solved_map)][cand_idx]

        final_result: List[Optional[VoicingMatch]] = []
        for idx in range(len(progression.measures)):
            final_result.append(solved_map.get(idx))

        return final_result