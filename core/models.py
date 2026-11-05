"""Data models for copedant configurations, mechanical half-stops, changer splits, and pedal steel guitars."""

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Dict, List, Optional, Set, Tuple


class NeckType(str, Enum):
    E9 = "E9"
    C6 = "C6"
    UNIVERSAL_12 = "Universal 12"
    CUSTOM = "Custom"


@dataclass
class StringPitch:
    string_number: int  # 1-indexed (1 is highest pitch in standard tuning)
    midi_note: int
    note_name: str

    def to_dict(self) -> dict:
        return {
            "string_number": int(self.string_number),
            "midi_note": int(self.midi_note),
            "note_name": str(self.note_name),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StringPitch":
        return cls(
            string_number=int(data["string_number"]),
            midi_note=int(data["midi_note"]),
            note_name=str(data["note_name"]),
        )

    @classmethod
    def from_name(cls, string_number: int, note_name: str, octave: int) -> "StringPitch":
        from core.theory import note_to_midi
        midi = note_to_midi(note_name, octave)
        return cls(string_number=string_number, midi_note=midi, note_name=f"{note_name}{octave}")


@dataclass
class CopedantChange:
    """Defines a pedal or knee lever change across strings."""
    id: str                 # "P1", "P2", "LKL", "LKR", etc.
    label: str              # User-facing label e.g., "Pedal A"
    changes: Dict[int, int] # {string_number: semitone_delta} (e.g., {5: 2, 10: 2})

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "label": str(self.label),
            "changes": {int(k): int(v) for k, v in self.changes.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CopedantChange":
        raw_changes = data.get("changes", {})
        parsed_changes = {int(k): int(v) for k, v in raw_changes.items()}
        return cls(
            id=str(data.get("id", "")),
            label=str(data.get("label", "")),
            changes=parsed_changes,
        )


@dataclass
class HalfStopRule:
    """Intermediate feel-stop on a SINGLE controller (e.g. LKL depressing halfway to F)."""
    controller_id: str        # e.g., "LKL", "LKV", "P1"
    string_number: int        # e.g., 4, 5
    semitone_delta: int       # e.g., +1 on an E->F# raise, -1 on a B->A drop
    is_active: bool = True    # Enabled in this copedant profile
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "controller_id": str(self.controller_id),
            "string_number": int(self.string_number),
            "semitone_delta": int(self.semitone_delta),
            "is_active": bool(self.is_active),
            "description": str(self.description),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HalfStopRule":
        return cls(
            controller_id=str(data.get("controller_id", "")),
            string_number=int(data.get("string_number", 1)),
            semitone_delta=int(data.get("semitone_delta", 1)),
            is_active=bool(data.get("is_active", True)),
            description=str(data.get("description", "")),
        )


@dataclass
class SplitRule:
    """Mechanical changer split override when TWO OR MORE controllers are pressed simultaneously."""
    string_number: int              # e.g., 5
    controllers: List[str]          # e.g., ["P1", "LKR"] (Pedal A + Lower)
    semitone_delta: int             # Resulting net offset from open string (e.g., 0 or +1)
    is_active: bool = True          # Include / Exclude toggle
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "string_number": int(self.string_number),
            "controllers": [str(c) for c in self.controllers],
            "semitone_delta": int(self.semitone_delta),
            "is_active": bool(self.is_active),
            "description": str(self.description),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SplitRule":
        return cls(
            string_number=int(data.get("string_number", 1)),
            controllers=[str(c) for c in data.get("controllers", [])],
            semitone_delta=int(data.get("semitone_delta", 0)),
            is_active=bool(data.get("is_active", True)),
            description=str(data.get("description", "")),
        )


@dataclass
class Neck:
    name: str
    neck_type: NeckType
    string_count: int
    open_tuning: List[StringPitch]
    pedals: Dict[str, CopedantChange] = field(default_factory=dict)
    knee_levers: Dict[str, CopedantChange] = field(default_factory=dict)
    half_stops: List[HalfStopRule] = field(default_factory=list)
    splits: List[SplitRule] = field(default_factory=list)
    description: str = ""
    author: str = "PSG Compass"
    author_bio: str = ""
    social_media: str = ""
    # Name of the user profile file this neck was loaded from / is linked to ("" = not a profile).
    source_profile: str = ""
    # Changer configuration: the most raises / lowers the changer can hold on one string.
    changer_raises: int = 3
    changer_lowers: int = 3

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source_profile": self.source_profile,
            "neck_type": self.neck_type.value if hasattr(self.neck_type, "value") else str(self.neck_type),
            "string_count": int(self.string_count),
            "description": self.description,
            "author": self.author,
            "author_bio": self.author_bio,
            "social_media": self.social_media,
            "open_tuning": [s.to_dict() for s in self.open_tuning],
            "pedals": {k: v.to_dict() for k, v in self.pedals.items()},
            "knee_levers": {k: v.to_dict() for k, v in self.knee_levers.items()},
            "half_stops": [h.to_dict() for h in getattr(self, "half_stops", [])],
            "splits": [s.to_dict() for s in getattr(self, "splits", [])],
            "changer": {"raises": int(self.changer_raises), "lowers": int(self.changer_lowers)},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Neck":
        tuning = [StringPitch.from_dict(s) for s in data.get("open_tuning", [])]
        pedals = {k: CopedantChange.from_dict(v) for k, v in data.get("pedals", {}).items()}
        levers = {k: CopedantChange.from_dict(v) for k, v in data.get("knee_levers", {}).items()}
        half_stops = [
            HalfStopRule.from_dict(h) if isinstance(h, dict) else h
            for h in data.get("half_stops", [])
        ]
        splits = [
            SplitRule.from_dict(s) if isinstance(s, dict) else s
            for s in data.get("splits", [])
        ]
        return cls(
            name=data.get("name", "Custom Neck"),
            neck_type=NeckType(data.get("neck_type", "E9")),
            string_count=int(data.get("string_count", len(tuning))),
            open_tuning=tuning,
            pedals=pedals,
            knee_levers=levers,
            half_stops=half_stops,
            splits=splits,
            description=data.get("description", ""),
            author=data.get("author", "PSG Compass"),
            author_bio=data.get("author_bio", ""),
            social_media=data.get("social_media", ""),
            source_profile=str(data.get("source_profile", "")),
            changer_raises=int(data.get("changer", {}).get("raises", DEFAULT_CHANGER[0])),
            changer_lowers=int(data.get("changer", {}).get("lowers", DEFAULT_CHANGER[1])),
        )

    @classmethod
    def from_compass_json(cls, data: dict) -> "Neck":
        from core.theory import note_to_midi

        meta = data.get("metadata", {})
        name = data.get("name", "Imported Copedant")
        desc = meta.get("description", "")
        author = meta.get("author", "PSG Compass")
        bio = meta.get("authorBio", "")
        social = meta.get("socialMedia", "")

        tuning: List[StringPitch] = []
        for s in data.get("strings", []):
            s_num = int(s["id"])
            note_str = s["openNote"]
            pitch_part = note_str[:-1]
            octave = int(note_str[-1])
            midi = note_to_midi(pitch_part, octave)
            tuning.append(StringPitch(string_number=s_num, midi_note=midi, note_name=note_str))

        string_count = len(tuning)
        if string_count >= 12 or "12" in name:
            n_type = NeckType.UNIVERSAL_12
        elif "C6" in name:
            n_type = NeckType.C6
        else:
            n_type = NeckType.E9

        pedals: Dict[str, CopedantChange] = {}
        for p in data.get("pedals", []):
            p_id = p.get("id")
            p_name = p.get("name", p_id)
            raw_changes = p.get("changes", {})
            parsed_changes = {int(k): int(v) for k, v in raw_changes.items() if int(v) != 0}
            pedals[p_id] = CopedantChange(id=p_id, label=p_name, changes=parsed_changes)

        knee_levers: Dict[str, CopedantChange] = {}
        for kl in data.get("kneeLevers", []):
            kl_id = kl.get("id")
            kl_name = kl.get("name", kl_id)
            raw_changes = kl.get("changes", {})
            parsed_changes = {int(k): int(v) for k, v in raw_changes.items() if int(v) != 0}
            if parsed_changes or kl.get("active", False):
                knee_levers[kl_id] = CopedantChange(id=kl_id, label=kl_name, changes=parsed_changes)

        splits: List[SplitRule] = []
        for ds in data.get("detectedSplits", []):
            s_num = int(ds.get("stringId"))
            ctrls = [c.get("id") for c in ds.get("conflictingControls", [])]
            delta = int(ds.get("manualSemitoneChange", 0))
            is_inc = ds.get("isIncludedInCalculation", "include").lower() == "include"
            desc_rule = f"{' + '.join(ctrls)} split on Str {s_num}"
            splits.append(
                SplitRule(
                    string_number=s_num,
                    controllers=ctrls,
                    semitone_delta=delta,
                    is_active=is_inc,
                    description=desc_rule,
                )
            )

        return cls(
            name=name,
            neck_type=n_type,
            string_count=string_count,
            open_tuning=tuning,
            pedals=pedals,
            knee_levers=knee_levers,
            half_stops=[],
            splits=splits,
            description=desc,
            author=author,
            author_bio=bio,
            social_media=social,
        )


HALF_SUFFIX = "_HALF"


# ---------------------------------------------------------------------------
# Changer configuration
# ---------------------------------------------------------------------------
# (raises, lowers) per string. Each pedal or lever that raises a string needs its own raise
# finger on that string's changer; each one that lowers needs a lower finger. Half-stops and
# split tuning screws work on an existing pull, so they need no extra finger.
DEFAULT_CHANGER: Tuple[int, int] = (3, 3)
CHANGER_PRESETS: List[Tuple[int, int]] = [(3, 3), (4, 2), (3, 2), (2, 2), (4, 3), (4, 4)]
CHANGER_LIMIT_RANGE = (0, 8)


def changer_label(raises: int, lowers: int) -> str:
    return f"{raises} up – {lowers} down"


@dataclass
class ChangerViolation:
    string_number: int
    direction: str            # "raise" or "lower"
    controllers: List[str]    # the controllers pulling that way on this string
    limit: int

    @property
    def message(self) -> str:
        n = len(self.controllers)
        return (f"String {self.string_number}: {n} {self.direction}s ({', '.join(self.controllers)}), "
                f"the changer holds {self.limit}")


def changer_usage(neck: "Neck") -> Dict[int, Tuple[List[str], List[str]]]:
    """string number -> (controllers that raise it, controllers that lower it)."""
    usage: Dict[int, Tuple[List[str], List[str]]] = {sp.string_number: ([], []) for sp in neck.open_tuning}
    for ctrl in list(neck.pedals.values()) + list(neck.knee_levers.values()):
        for s_num, delta in ctrl.changes.items():
            if s_num in usage and delta:
                usage[s_num][0 if delta > 0 else 1].append(ctrl.id)
    return usage


def changer_violations(neck: "Neck") -> List[ChangerViolation]:
    """Every string that needs more raises or lowers than the neck's changer configuration holds."""
    out: List[ChangerViolation] = []
    for s_num, (ups, downs) in sorted(changer_usage(neck).items()):
        if len(ups) > neck.changer_raises:
            out.append(ChangerViolation(s_num, "raise", ups, neck.changer_raises))
        if len(downs) > neck.changer_lowers:
            out.append(ChangerViolation(s_num, "lower", downs, neck.changer_lowers))
    return out

# Knee lever IDs removed by the copedant editor on load (legacy variants).
RETIRED_KNEE_LEVER_IDS = {"VL2", "LKR2", "RKL2", "VR", "VR2", "RKRHS"}


def _remap_token(token: str, mapping: Dict[str, str]) -> str:
    """Maps a controller token, preserving a trailing '_HALF' engagement suffix."""
    if token.endswith(HALF_SUFFIX):
        base = token[: -len(HALF_SUFFIX)]
        return mapping.get(base, base) + HALF_SUFFIX
    return mapping.get(token, token)


def _remap_label(label: str, old_id: str, new_id: str) -> str:
    """Keeps custom labels, but renumbers labels that merely echo the controller ID
    (e.g. 'P1' -> 'P2', 'P1 (A)' -> 'P2 (A)', 'Pedal 1 (A)' -> 'Pedal 2 (A)')."""
    if old_id == new_id or not label:
        return label or new_id
    if label == old_id:
        return new_id
    if label.startswith(old_id + " "):
        return new_id + label[len(old_id):]
    old_num, new_num = old_id[1:], new_id[1:]
    prefix = f"Pedal {old_num}"
    if old_id.startswith("P") and new_id.startswith("P") and old_num.isdigit() and new_num.isdigit():
        if label == prefix or label.startswith(prefix + " "):
            return f"Pedal {new_num}" + label[len(prefix):]
    return label


def remap_controller_ids(neck: Neck, mapping: Dict[str, str]) -> None:
    """Renames controller IDs everywhere they are referenced (pedals, knee levers, split rules,
    half-stop rules). The mapping is applied simultaneously, so shifts like
    {"P1": "P2", "P2": "P3"} are safe. Labels that merely echo the old ID are renumbered.
    """
    mapping = {k: v for k, v in mapping.items() if k != v}
    if not mapping:
        return

    def _remap_group(group: Dict[str, CopedantChange]) -> Dict[str, CopedantChange]:
        out: Dict[str, CopedantChange] = {}
        for old_id, ctrl in group.items():
            new_id = mapping.get(old_id, old_id)
            if new_id in out:
                raise ValueError(f"Controller ID collision while remapping: {new_id}")
            out[new_id] = CopedantChange(
                id=new_id,
                label=_remap_label(ctrl.label, old_id, new_id),
                changes=dict(ctrl.changes),
            )
        return out

    neck.pedals = _remap_group(neck.pedals)
    neck.knee_levers = _remap_group(neck.knee_levers)
    for rule in neck.splits:
        rule.controllers = [_remap_token(c, mapping) for c in rule.controllers]
    for rule in neck.half_stops:
        rule.controller_id = _remap_token(rule.controller_id, mapping)


def migrate_legacy_ids(neck: Neck) -> None:
    """Normalizes legacy controller IDs in place: 'VL' becomes 'LKV' (with all split/half-stop
    references), and retired knee lever variants are removed together with the rules that
    referenced them.
    """
    if "VL" in neck.knee_levers and "LKV" not in neck.knee_levers:
        remap_controller_ids(neck, {"VL": "LKV"})
        lkv = neck.knee_levers["LKV"]
        if lkv.label == "VL":
            lkv.label = "LKV"

    retired = {r for r in RETIRED_KNEE_LEVER_IDS if r in neck.knee_levers}
    if retired:
        for r_id in retired:
            del neck.knee_levers[r_id]

        def _uses_retired(token: str) -> bool:
            return token.replace(HALF_SUFFIX, "") in retired

        neck.splits = [s for s in neck.splits if not any(_uses_retired(c) for c in s.controllers)]
        neck.half_stops = [h for h in neck.half_stops if not _uses_retired(h.controller_id)]


def migrate_half_stop_tokens(neck: Neck) -> bool:
    """Converts legacy pseudo-controller split tokens like 'P3HS' into the engagement token
    'P3_HALF' when 'P3HS' is not a real controller but 'P3' is. Adds default +/-1 half-stop
    rules (pulls of 2+ semitones) for affected controllers that have none, so the half-stop
    can actually be engaged. Returns True if anything changed.
    """
    defined = set(neck.pedals) | set(neck.knee_levers)
    converted: Set[str] = set()

    def _fix(token: str) -> str:
        if token in defined or not token.endswith("HS") or token.endswith(HALF_SUFFIX):
            return token
        base = token[:-2]
        if base in defined:
            converted.add(base)
            return base + HALF_SUFFIX
        return token

    for rule in neck.splits:
        rule.controllers = [_fix(c) for c in rule.controllers]

    has_rules = {h.controller_id for h in neck.half_stops}
    for base in sorted(converted - has_rules):
        ctrl = neck.pedals.get(base) or neck.knee_levers.get(base)
        for s_num, delta in sorted(ctrl.changes.items()):
            if abs(delta) >= 2:
                neck.half_stops.append(
                    HalfStopRule(
                        controller_id=base,
                        string_number=s_num,
                        semitone_delta=1 if delta > 0 else -1,
                        is_active=True,
                        description=f"{base} half-stop (migrated)",
                    )
                )
    return bool(converted)


def shift_pedal_ids(neck: Neck, offset: int) -> None:
    """Renumbers every numeric pedal ID by `offset` (e.g. +1 to make room for a Franklin P1),
    remapping all split and half-stop references."""
    mapping: Dict[str, str] = {}
    for p_id in neck.pedals:
        if p_id.startswith("P") and p_id[1:].isdigit():
            new_num = int(p_id[1:]) + offset
            if new_num < 1:
                raise ValueError(f"Cannot shift {p_id} by {offset}")
            mapping[p_id] = f"P{new_num}"
    remap_controller_ids(neck, mapping)


def undefined_rule_controllers(neck: Neck) -> Set[str]:
    """Controller IDs referenced by split/half-stop rules that do not exist on the neck."""
    defined = set(neck.pedals) | set(neck.knee_levers)
    referenced = {c.replace(HALF_SUFFIX, "") for s in neck.splits for c in s.controllers}
    referenced |= {h.controller_id.replace(HALF_SUFFIX, "") for h in neck.half_stops}
    return referenced - defined


def detect_potential_splits(neck: Neck) -> List[SplitRule]:
    """Scans for strings with 2 or more conflicting pulls (Simultaneous Controller Splits)."""
    from itertools import combinations

    string_pulls: Dict[int, List[Tuple[str, int]]] = {
        sp.string_number: [] for sp in neck.open_tuning
    }

    all_controllers = {**neck.pedals, **neck.knee_levers}
    for cid, ctrl in all_controllers.items():
        for s_num, delta in ctrl.changes.items():
            if s_num in string_pulls and delta != 0:
                string_pulls[s_num].append((cid, delta))

    existing_map = {
        (r.string_number, frozenset(r.controllers)): r for r in getattr(neck, "splits", [])
    }

    detected_rules: List[SplitRule] = []

    for sp in neck.open_tuning:
        s_num = sp.string_number
        pulls = string_pulls.get(s_num, [])
        if len(pulls) < 2:
            continue

        pulls.sort(key=lambda x: x[0])

        for (c1, d1), (c2, d2) in combinations(pulls, 2):
            ctrl_pair = frozenset([c1, c2])
            if (s_num, ctrl_pair) in existing_map:
                detected_rules.append(existing_map[(s_num, ctrl_pair)])
            else:
                default_delta = 0 if (d1 + d2) == 0 else (1 if (d1 + d2) > 0 else -1)
                desc = f"Changer Split: {c1} ({'+' if d1>0 else ''}{d1}) + {c2} ({'+' if d2>0 else ''}{d2})"
                detected_rules.append(
                    SplitRule(
                        string_number=s_num,
                        controllers=[c1, c2],
                        semitone_delta=default_delta,
                        is_active=True,
                        description=desc,
                    )
                )

    return detected_rules


def detect_potential_half_stops(neck: Neck) -> List[HalfStopRule]:
    """Identifies single controllers with pulls of 2+ semitones (e.g. E->F# or B->A)."""
    detected: List[HalfStopRule] = []
    all_controllers = {**neck.pedals, **neck.knee_levers}
    existing = {(r.controller_id, r.string_number) for r in getattr(neck, "half_stops", [])}

    for cid, ctrl in all_controllers.items():
        for s_num, delta in ctrl.changes.items():
            if abs(delta) >= 2 and (cid, s_num) not in existing:
                half_delta = 1 if delta > 0 else -1
                detected.append(
                    HalfStopRule(
                        controller_id=cid,
                        string_number=s_num,
                        semitone_delta=half_delta,
                        is_active=True,
                        description=f"Intermediate feel stop on {cid} ({'+' if half_delta>0 else ''}{half_delta} st)",
                    )
                )
    return detected


@dataclass
class SteelGuitar:
    """A profile: a named group of necks (tunings). `profile` is the user-profile file it belongs
    to, or "" for the built-in factory profile (see core/profile_manager.py)."""
    name: str
    necks: List[Neck]
    profile: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "profile": self.profile,
            "necks": [neck.to_dict() for neck in self.necks],
        }

    def save_to_file(self, filepath: str) -> None:
        payload = self.to_dict()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    @classmethod
    def load_from_file(cls, filepath: str) -> "SteelGuitar":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        necks = [Neck.from_dict(n) for n in data["necks"]]
        return cls(name=data["name"], necks=necks, profile=str(data.get("profile", "")))