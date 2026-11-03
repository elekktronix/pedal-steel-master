"""User Profile and Copedant Persistence Manager."""

import json
from pathlib import Path
from typing import List, Optional

from core.models import Neck

ACTIVE_SETUP_FILENAME = "active_guitar_setup.json"


class ProfileManager:
    STORAGE_DIR: Path = Path.home() / ".psg_visualizer" / "profiles"

    @classmethod
    def ensure_storage_dir(cls) -> Path:
        cls.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        return cls.STORAGE_DIR

    @classmethod
    def get_storage_dir(cls) -> Path:
        return cls.ensure_storage_dir()

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
        return sorted(profiles)

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
    def save_user_profile(cls, name: str, neck: Neck) -> Path:
        filepath = cls._profile_path(name)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(neck.to_dict(), f, indent=2)
        return filepath

    @classmethod
    def load_user_profile(cls, name: str) -> Optional[Neck]:
        try:
            filepath = cls._profile_path(name)
        except ValueError:
            return None
        if not filepath.exists():
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        neck = Neck.from_dict(data)
        # A neck loaded from a profile is always linked back to that profile file.
        neck.source_profile = filepath.stem
        return neck

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
