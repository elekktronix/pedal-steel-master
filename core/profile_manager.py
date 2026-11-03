"""User Profile and Copedant Persistence Manager."""

import json
from pathlib import Path
from typing import List, Optional

from core.models import Neck


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
    def list_user_profiles(cls) -> List[str]:
        cls.ensure_storage_dir()
        profiles = []
        for p in cls.STORAGE_DIR.glob("*.json"):
            # Exclude internal session state file from user profile lists
            if p.name != "active_guitar_setup.json":
                profiles.append(p.stem)
        return sorted(profiles)

    @classmethod
    def save_user_profile(cls, name: str, neck: Neck) -> Path:
        cls.ensure_storage_dir()
        safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).rstrip()
        filepath = cls.STORAGE_DIR / f"{safe_name}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(neck.to_dict(), f, indent=2)
        return filepath

    @classmethod
    def load_user_profile(cls, name: str) -> Optional[Neck]:
        cls.ensure_storage_dir()
        safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).rstrip()
        filepath = cls.STORAGE_DIR / f"{safe_name}.json"
        if not filepath.exists():
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Neck.from_dict(data)

    @classmethod
    def delete_user_profile(cls, name: str) -> bool:
        cls.ensure_storage_dir()
        safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).rstrip()
        filepath = cls.STORAGE_DIR / f"{safe_name}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False