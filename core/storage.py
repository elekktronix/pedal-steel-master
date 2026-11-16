"""Crash-safe JSON writes (B8).

Every settings, session, setup and profile file goes through `atomic_write_json`: the JSON is
written to a temp file in the target folder and then moved over the target in one step, so a
crash or power loss mid-write leaves either the old file or the new one, never a truncated file.
The temp file ends in `.tmp`, so `ProfileManager.list_user_profiles` (which globs `*.json`) never
lists it.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path, payload: Any, indent: int = 2) -> None:
    """Writes `payload` as JSON to `path` atomically. Raises on failure (the target is unchanged)."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
