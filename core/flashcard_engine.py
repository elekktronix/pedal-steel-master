"""Engine for Jeff Newman's 'Steak or Biscuits' Timed Star Map Flashcard Drill."""

from dataclasses import dataclass, field
import random
import time
from typing import List, Optional, Set, Tuple

from core.star_map_engine import StarMapEngine, StarMapLandmark
from core.theory import NOTE_NAMES_SHARP


@dataclass
class FlashcardPrompt:
    root_name: str
    chord_type: str
    ordered_landmarks: List[StarMapLandmark] = field(default_factory=list)
    time_limit_sec: int = 30


@dataclass
class DrillResult:
    is_success: bool
    verdict: str           # "STEAK!" or "BISCUITS!"
    elapsed_sec: float
    expected_sequence: List[str]
    user_sequence: List[str]
    accuracy_pct: float
    streak: int


class FlashcardEngine:
    MAJOR_ROOT_POOL = ["C", "F", "G", "D", "A", "E", "Bb", "Eb", "Ab"]

    @classmethod
    def generate_prompt(cls, time_limit: int = 30, preferred_root: Optional[str] = None) -> FlashcardPrompt:
        """Generates a random or targeted landmark challenge across 0-24 frets."""
        root = preferred_root if preferred_root else random.choice(cls.MAJOR_ROOT_POOL)
        landmarks = StarMapEngine.calculate_major_star_map(root)
        return FlashcardPrompt(
            root_name=root,
            chord_type="Major",
            ordered_landmarks=landmarks,
            time_limit_sec=time_limit,
        )

    @classmethod
    def evaluate_attempt(
        cls,
        prompt: FlashcardPrompt,
        user_clicks: List[Tuple[int, Set[str]]],  # (fret, controllers)
        elapsed_sec: float,
        current_streak: int = 0,
    ) -> DrillResult:
        """Evaluates whether the user clicked the landmarks in strict left-to-right order."""
        expected_lms = prompt.ordered_landmarks
        expected_labels = [lm.label for lm in expected_lms]

        # Match user clicks against expected sequence
        matched_count = 0
        user_labels: List[str] = []

        for i, (click_fret, click_ctrls) in enumerate(user_clicks):
            if i < len(expected_lms):
                exp = expected_lms[i]
                if click_fret == exp.fret and set(click_ctrls) == set(exp.controllers):
                    matched_count += 1
                    user_labels.append(exp.label)
                else:
                    ctrl_str = "+".join(sorted(click_ctrls)) if click_ctrls else "Open"
                    user_labels.append(f"F{click_fret} ({ctrl_str}) [Incorrect]")

        accuracy = (matched_count / len(expected_lms) * 100.0) if expected_lms else 0.0
        time_ok = elapsed_sec <= prompt.time_limit_sec
        is_success = (matched_count == len(expected_lms)) and time_ok

        if is_success:
            verdict = "🥩 STEAK! You know your neck cold."
            new_streak = current_streak + 1
        else:
            if not time_ok:
                verdict = "🍪 BISCUITS! Out of time. Don't guess—learn the patterns."
            else:
                verdict = "🍪 BISCUITS! Landmark order or pedals were incorrect."
            new_streak = 0

        return DrillResult(
            is_success=is_success,
            verdict=verdict,
            elapsed_sec=elapsed_sec,
            expected_sequence=expected_labels,
            user_sequence=user_labels,
            accuracy_pct=accuracy,
            streak=new_streak,
        )