"""Profiles and copedant files.

A *profile* is a named group of tunings (a `SteelGuitar`): the built-in **Factory** profile (the
presets in core/presets.py, key `FACTORY_PROFILE`) or a **user profile** stored as
`~/.psg_visualizer/profiles/<name>.json` in the `SteelGuitar` format. Older user-profile files that
hold a single `Neck` are read as a profile with one tuning and rewritten in the group format the
next time they are saved.
"""

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.models import Neck, SteelGuitar, migrate_half_stop_tokens

log = logging.getLogger(__name__)

ACTIVE_SETUP_FILENAME = "active_guitar_setup.json"
COPEDANT_FILE_FILTER = "Copedant files (*.json *.cop);;All Files (*.*)"
FACTORY_PROFILE = ""  # profile key of the built-in factory presets
FACTORY_PROFILE_LABEL = "Factory"


def factory_guitar() -> SteelGuitar:
    """A fresh copy of the factory profile (default tunings)."""
    from core.presets import build_standard_d10_guitar

    guitar = build_standard_d10_guitar()
    guitar.profile = FACTORY_PROFILE
    return guitar


def profile_label(profile: str) -> str:
    return profile or FACTORY_PROFILE_LABEL


def prepare_loaded_guitar(guitar: SteelGuitar) -> SteelGuitar:
    """Load-time migrations for every neck of a profile or setup (half-stop tokens). The old
    per-neck profile link (`Neck.source_profile`) is no longer used and is cleared."""
    for neck in guitar.necks:
        migrate_half_stop_tokens(neck)
        neck.source_profile = ""
    return guitar


def same_tunings(a: SteelGuitar, b: SteelGuitar) -> bool:
    return [n.to_dict() for n in a.necks] == [n.to_dict() for n in b.necks]


def unique_neck_name(guitar: SteelGuitar, name: str) -> str:
    """`name`, or `name (2)`, `name (3)`, ... so it does not repeat a tuning name in `guitar`."""
    existing = {n.name for n in guitar.necks}
    candidate, n = name, 2
    while candidate in existing:
        candidate = f"{name} ({n})"
        n += 1
    return candidate


def export_neck(neck: Neck, path) -> None:
    """Writes one copedant as `Neck.to_dict()` JSON (the profile format). The profile link is
    local to this machine, so it is left out; Import Copedant and Import Profile read the file."""
    data = neck.to_dict()
    data["source_profile"] = ""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def read_necks_file(path) -> List[Neck]:
    """Every neck in a copedant file: a single `Neck` (profile / exported copedant), a full setup
    (`{"name", "necks": [...]}`) or a PSG Compass copedant. Half-stop tokens are migrated and the
    necks are not linked to any profile. Raises ValueError if the file holds no copedant."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Not a copedant file (expected a JSON object).")
    if "strings" in data and "pedals" in data:
        necks = [Neck.from_compass_json(data)]
    elif isinstance(data.get("necks"), list):
        necks = [Neck.from_dict(n) for n in data["necks"]]
    elif "open_tuning" in data:
        necks = [Neck.from_dict(data)]
    else:
        raise ValueError("Not a copedant file (no strings / open tuning found).")
    necks = [n for n in necks if n.open_tuning]
    if not necks:
        raise ValueError("The file contains no copedant with strings.")
    for n in necks:
        migrate_half_stop_tokens(n)
        n.source_profile = ""
    return necks


class ProfileManager:
    STORAGE_DIR: Path = Path.home() / ".psg_visualizer" / "profiles"

    @classmethod
    def ensure_storage_dir(cls) -> Path:
        cls.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        return cls.STORAGE_DIR

    @classmethod
    def get_storage_dir(cls) -> Path:
        return cls.ensure_storage_dir()

    @classmethod
    def active_setup_path(cls) -> Path:
        return cls.ensure_storage_dir() / ACTIVE_SETUP_FILENAME

    @staticmethod
    def sanitize_name(name: str) -> str:
        """File-system safe profile name (alnum, space, underscore, hyphen). May be empty."""
        return "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip()

    @classmethod
    def _profile_path(cls, name: str) -> Path:
        safe_name = cls.sanitize_name(name)
        if not safe_name or f"{safe_name}.json" == ACTIVE_SETUP_FILENAME:
            raise ValueError(f"Invalid profile name: {name!r}")
        return cls.ensure_storage_dir() / f"{safe_name}.json"

    @classmethod
    def list_user_profiles(cls) -> List[str]:
        cls.ensure_storage_dir()
        profiles = []
        for p in cls.STORAGE_DIR.glob("*.json"):
            # Exclude internal session state file from user profile lists
            if p.name != ACTIVE_SETUP_FILENAME:
                profiles.append(p.stem)
        return sorted(profiles, key=str.lower)

    @classmethod
    def profile_exists(cls, name: str) -> bool:
        try:
            return cls._profile_path(name).exists()
        except ValueError:
            return False

    @classmethod
    def unique_profile_name(cls, name: str) -> str:
        """Sanitized name that does not collide with an existing profile ('Name', 'Name 2', ...)."""
        base = cls.sanitize_name(name)
        if not base:
            raise ValueError(f"Invalid profile name: {name!r}")
        candidate, n = base, 2
        while cls.profile_exists(candidate):
            candidate = f"{base} {n}"
            n += 1
        return candidate

    @classmethod
    def save_profile(cls, name: str, guitar: SteelGuitar) -> Path:
        """Writes the tunings of `guitar` as user profile `name` (group format). `guitar` is not changed."""
        filepath = cls._profile_path(name)
        data = SteelGuitar(name=filepath.stem, necks=guitar.necks, profile=filepath.stem).to_dict()
        for neck_data in data["necks"]:
            neck_data["source_profile"] = ""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return filepath

    @classmethod
    def load_profile(cls, name: str) -> Optional[SteelGuitar]:
        """User profile `name` as a `SteelGuitar` (`profile` = name), or None if there is no such
        file. A legacy single-neck profile file becomes a profile with one tuning. Raises on a
        file that cannot be read."""
        try:
            filepath = cls._profile_path(name)
        except ValueError:
            return None
        if not filepath.exists():
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("necks"), list):
            necks = [Neck.from_dict(n) for n in data["necks"]]
        elif isinstance(data, dict) and "open_tuning" in data:
            necks = [Neck.from_dict(data)]
        else:
            raise ValueError(f"Profile '{filepath.stem}' is not a valid profile file.")
        return prepare_loaded_guitar(SteelGuitar(name=filepath.stem, necks=necks, profile=filepath.stem))

    @classmethod
    def load_any_profile(cls, name: str) -> Optional[SteelGuitar]:
        """The factory profile for `FACTORY_PROFILE`, else the user profile (see `load_profile`)."""
        return factory_guitar() if name == FACTORY_PROFILE else cls.load_profile(name)

    @classmethod
    def add_tuning_to_profile(cls, name: str, neck: Neck) -> str:
        """Appends a copy of `neck` to user profile `name` (created if missing). Returns the name
        the tuning got in that profile (made unique within it)."""
        guitar = cls.load_profile(name) or SteelGuitar(name=name, necks=[], profile=name)
        copy = deepcopy(neck)
        copy.source_profile = ""
        copy.name = unique_neck_name(guitar, copy.name)
        guitar.necks.append(copy)
        cls.save_profile(name, guitar)
        return copy.name

    @classmethod
    def list_all_tunings(cls, current: Optional[SteelGuitar] = None) -> List[Tuple[str, List[Neck]]]:
        """[(profile key, tunings)] for the factory profile and every user profile. When `current`
        is given, its live (possibly unsaved) tunings stand in for the profile it belongs to.
        Unreadable profile files are skipped and logged."""
        result = []
        for key in [FACTORY_PROFILE] + cls.list_user_profiles():
            if current is not None and current.profile == key:
                result.append((key, list(current.necks)))
                continue
            try:
                guitar = cls.load_any_profile(key)
            except Exception:
                log.exception("Could not read profile %r", key)
                continue
            if guitar is not None:
                result.append((key, guitar.necks))
        return result

    @classmethod
    def import_profile_file(cls, path) -> str:
        """Copies every tuning in a copedant or setup file (see `read_necks_file`) into one new
        user profile under a free name (never overwrites). Returns the profile name."""
        necks = read_necks_file(path)
        base = necks[0].name if len(necks) == 1 else Path(path).stem
        name = cls.unique_profile_name(cls.sanitize_name(base) or "Imported Profile")
        cls.save_profile(name, SteelGuitar(name=name, necks=necks, profile=name))
        return name

    @classmethod
    def export_profile(cls, name: str, path) -> None:
        """Writes user profile `name` (all its tunings) to `path` in the setup format."""
        guitar = cls.load_profile(name)
        if guitar is None:
            raise FileNotFoundError(f"Profile '{name}' not found.")
        data = guitar.to_dict()
        data["profile"] = ""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def rename_profile(cls, old: str, new: str) -> str:
        """Renames user profile `old` to `new` (sanitized). Raises ValueError if the new name is
        invalid or taken, FileNotFoundError if `old` does not exist. Returns the new name."""
        guitar = cls.load_profile(old)
        if guitar is None:
            raise FileNotFoundError(f"Profile '{old}' not found.")
        new_safe = cls.sanitize_name(new)
        if not new_safe:
            raise ValueError(f"Invalid profile name: {new!r}")
        if new_safe == cls.sanitize_name(old):
            return new_safe
        if cls.profile_exists(new_safe):
            raise ValueError(f"A profile named '{new_safe}' already exists.")
        cls.save_profile(new_safe, guitar)
        cls.delete_user_profile(old)
        return new_safe

    @classmethod
    def delete_user_profile(cls, name: str) -> bool:
        try:
            filepath = cls._profile_path(name)
        except ValueError:
            return False
        if filepath.exists():
            filepath.unlink()
            return True
        return False


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
STARTUP_LAST_SESSION = "last"
STARTUP_PROFILE = "profile"


def load_startup_guitar(settings: Dict[str, Any]) -> Tuple[SteelGuitar, str]:
    """The profile to open at startup and the tuning name to select ("" = no preference).

    `settings["startup_mode"] == "profile"`: open `startup_profile` ("" = factory) and select
    `startup_tuning`. Otherwise (or if that profile cannot be read) resume the last session from
    `active_guitar_setup.json`, falling back to the factory profile."""
    if settings.get("startup_mode") == STARTUP_PROFILE:
        name = settings.get("startup_profile", FACTORY_PROFILE) or FACTORY_PROFILE
        try:
            guitar = ProfileManager.load_any_profile(name)
        except Exception:
            log.exception("Could not open startup profile %r", name)
            guitar = None
        if guitar is not None and guitar.necks:
            return guitar, str(settings.get("startup_tuning", "") or "")
        log.warning("Startup profile %r not found; resuming the last session", name)

    path = ProfileManager.active_setup_path()
    if path.exists():
        try:
            guitar = SteelGuitar.load_from_file(str(path))
            if guitar.necks:
                if guitar.profile and not ProfileManager.profile_exists(guitar.profile):
                    guitar.profile = FACTORY_PROFILE  # its profile file was deleted
                return prepare_loaded_guitar(guitar), ""
        except Exception:
            log.exception("Could not load %s; using factory presets", path)
    return factory_guitar(), ""
