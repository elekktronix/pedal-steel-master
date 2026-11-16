"""Pedal steel physical ergonomics and mechanical clashing engine."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Set, Tuple


class StanceDifficulty(Enum):
    NATURAL = "Natural"        # Open bar or single pedal/lever
    STANDARD = "Standard"      # Standard split (e.g., A+B) or single pedal + single lever
    AWKWARD = "Awkward"        # High physical strain (e.g., 2 pedals + 2 opposing knees)
    IMPOSSIBLE = "Impossible"  # Anatomically or mechanically impossible


@dataclass
class ErgonomicStance:
    is_possible: bool
    difficulty: StanceDifficulty
    penalty: float
    description: str
    clash_reasons: List[str]


class ErgonomicsEngine:
    # Every knee lever ID belongs to one knee (A2). LKL2 is a second left-knee-left lever; legacy VL
    # is the left-knee vertical (renamed LKV on load); RKR2 is BE E9's "RKRHS", the RKR half-travel
    # modelled as its own lever, so it clashes with RKR and RKL.
    LEFT_KNEE_LEVERS = {"LKL", "LKR", "LKV", "LKL2", "VL"}
    RIGHT_KNEE_LEVERS = {"RKL", "RKR", "RKV", "RKR2"}
    # Centre levers are pushed by whichever knee is free: only one at a time, and not while both
    # side knees are already busy.
    CENTER_KNEE_LEVERS = {"CKL", "CKV", "CKR"}

    @staticmethod
    def _parse_pedal_number(pid: str) -> Optional[int]:
        match = re.search(r"\d+", pid)
        return int(match.group()) if match else None

    @classmethod
    def evaluate_stance(cls, engaged_controllers: Set[str]) -> ErgonomicStance:
        """Evaluates anatomical and mechanical feasibility of engaged pedals and knee levers.

        Assumes the standard pedal steel posture:
        - Right foot: Volume pedal
        - Left foot: Pedal rack (P1, P2, P3, P4...)
        - Left knee: LKL, LKR, LKV
        - Right knee: RKL, RKR, RKV
        """
        clash_reasons: List[str] = []
        controllers = set(engaged_controllers)

        if not controllers:
            return ErgonomicStance(
                is_possible=True,
                difficulty=StanceDifficulty.NATURAL,
                penalty=0.0,
                description="Open Bar (No Pedals/Levers)",
                clash_reasons=[],
            )

        # 1. Evaluate Foot Pedals
        pedals = [c for c in controllers if c.startswith("P")]
        pedal_nums = sorted([num for p in pedals if (num := cls._parse_pedal_number(p)) is not None])

        if len(pedal_nums) > 2:
            clash_reasons.append(
                f"Foot overload: Left foot cannot simultaneously press {len(pedal_nums)} pedals ({', '.join(pedals)})."
            )
        elif len(pedal_nums) == 2:
            # Check adjacency for two-pedal splits
            p1, p2 = pedal_nums[0], pedal_nums[1]
            if abs(p1 - p2) > 1:
                clash_reasons.append(
                    f"Pedal gap clash: Left foot cannot bridge non-adjacent pedals P{p1} and P{p2}."
                )

        # 2. Evaluate Left Knee Levers
        lk_active = controllers & cls.LEFT_KNEE_LEVERS
        if len(lk_active) > 1:
            clash_reasons.append(
                f"Left knee clash: Cannot push opposing levers ({', '.join(sorted(lk_active))}) simultaneously."
            )

        # 3. Evaluate Right Knee Levers
        rk_active = controllers & cls.RIGHT_KNEE_LEVERS
        if len(rk_active) > 1:
            clash_reasons.append(
                f"Right knee clash: Cannot push opposing levers ({', '.join(sorted(rk_active))}) simultaneously."
            )

        # 4. Centre knee levers
        ck_active = controllers & cls.CENTER_KNEE_LEVERS
        if len(ck_active) > 1:
            clash_reasons.append(
                f"Centre knee clash: Cannot push more than one centre lever ({', '.join(sorted(ck_active))})."
            )
        elif ck_active and lk_active and rk_active:
            clash_reasons.append(
                f"Knee overload: {next(iter(ck_active))} needs a knee, but both knees are already engaged."
            )

        # If any physical impossibility was detected:
        if clash_reasons:
            return ErgonomicStance(
                is_possible=False,
                difficulty=StanceDifficulty.IMPOSSIBLE,
                penalty=1000.0,
                description="Mechanically Impossible",
                clash_reasons=clash_reasons,
            )

        # 4. Evaluate Playable Stance Difficulty & Comfort Penalties
        contact_points = 0
        if pedal_nums:
            contact_points += 1 if len(pedal_nums) == 1 else 1.5  # Split pedal takes more balance
        if lk_active:
            contact_points += 1
        if rk_active:
            contact_points += 1
        if ck_active:
            contact_points += 1

        # Calculate penalty and ergonomics tier
        if contact_points <= 1:
            return ErgonomicStance(
                is_possible=True,
                difficulty=StanceDifficulty.NATURAL,
                penalty=0.0,
                description="Natural / Single Action",
                clash_reasons=[],
            )
        elif contact_points <= 2.5:
            # Standard combinations like P1+P2, P1+LKL, P2+RKL
            return ErgonomicStance(
                is_possible=True,
                difficulty=StanceDifficulty.STANDARD,
                penalty=3.0 if len(pedal_nums) == 2 else 1.5,
                description="Standard Stance",
                clash_reasons=[],
            )
        else:
            # High physical coordination: 2 foot pedals + left knee + right knee
            return ErgonomicStance(
                is_possible=True,
                difficulty=StanceDifficulty.AWKWARD,
                penalty=12.0,
                description="Awkward / Multi-Limb Balance Stance",
                clash_reasons=[],
            )