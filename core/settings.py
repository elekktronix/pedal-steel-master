"""Application settings and user preferences manager."""

import json
import os
from typing import Any, Dict

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app_settings.json")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "theme": "dark",
    "show_inversions": True,
    "show_scale_box": True,
}


def load_settings() -> Dict[str, Any]:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**DEFAULT_SETTINGS, **data}
        except Exception as e:
            print(f"[Settings] Failed to load settings: {e}")
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: Dict[str, Any]) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"[Settings] Failed to save settings: {e}")