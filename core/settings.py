"""Application settings and user preferences manager.

Settings live in ~/.psg_visualizer/app_settings.json (D-32). The legacy file next to the source
tree (<repo>/app_settings.json) is read once as a fallback so existing preferences carry over.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

log = logging.getLogger(__name__)

SETTINGS_DIR = Path.home() / ".psg_visualizer"
SETTINGS_FILE = SETTINGS_DIR / "app_settings.json"
LEGACY_SETTINGS_FILE = Path(__file__).resolve().parents[1] / "app_settings.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "theme": "dark",
    "show_inversions": True,
    "show_scale_box": True,
    "scale_overlay_label": "step",     # scale map circles: "step", "degree" or "note"
    "show_nashville": True,
    "use_newman_tuning": False,
    "pedal_swells": True,
    "note_spelling": "sharps",         # "sharps" or "flats": how note and chord names are displayed
    "key_aware_spelling": True,        # circle of fifths / triad explorer spell by key signature
    "perm_click_sound": "Woodblock",   # permutation trainer metronome (CLICK_SOUNDS key, "Chirp (WAV)" or "Off")
    "perm_click_mode": "Every note",   # or "Beat 1 only"
}


def load_settings() -> Dict[str, Any]:
    for candidate in (SETTINGS_FILE, LEGACY_SETTINGS_FILE):
        if candidate.exists():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {**DEFAULT_SETTINGS, **data}
            except Exception:
                log.exception("Failed to load settings from %s", candidate)
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: Dict[str, Any]) -> None:
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({**DEFAULT_SETTINGS, **settings}, f, indent=2)
    except Exception:
        log.exception("Failed to save settings to %s", SETTINGS_FILE)
