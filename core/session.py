"""Session persistence (E-12): the last-used neck, stance, harmonic target and window layout.

Stored in ~/.psg_visualizer/session.json. The file is advisory: anything missing or invalid is
ignored and the app falls back to its defaults.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

log = logging.getLogger(__name__)

SESSION_FILE = Path.home() / ".psg_visualizer" / "session.json"


def load_session() -> Dict[str, Any]:
    try:
        if SESSION_FILE.exists():
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        log.warning("Ignoring unreadable session file %s: %s", SESSION_FILE, e)
    return {}


def save_session(session: Dict[str, Any]) -> None:
    try:
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
    except Exception:
        log.exception("Failed to save session to %s", SESSION_FILE)
