# 01 — Domain Model (`core/models.py`, `core/presets.py`)

## Entities

```
SteelGuitar
 ├─ name: str
 └─ necks: List[Neck]                      # the "copedant dropdown" list
Neck
 ├─ name, neck_type: NeckType(E9|C6|Universal 12|Custom), string_count
 ├─ open_tuning: List[StringPitch]          # ordered by string_number 1..N (assumed contiguous)
 ├─ pedals:      Dict[id, CopedantChange]   # ids "P1".."Pn"
 ├─ knee_levers: Dict[id, CopedantChange]   # ids "LKL","LKV","LKR","RKL","RKR",...
 ├─ half_stops:  List[HalfStopRule]         # (controller_id, string) -> intermediate delta
 ├─ splits:      List[SplitRule]            # (string, {controllers}) -> net delta override
 ├─ description, author, author_bio, social_media   # metadata only
 ├─ source_profile: str                     # legacy per-neck profile link; unused, cleared on load
 └─ changer_raises, changer_lowers: int     # changer configuration (E-26), default 3 up – 3 down
StringPitch    { string_number, midi_note, note_name }   # note_name like "G#3" (sharps)
CopedantChange { id, label, changes: Dict[string_number -> semitone_delta] }   # zero deltas omitted
HalfStopRule   { controller_id, string_number, semitone_delta, is_active, description }
SplitRule      { string_number, controllers: List[str] (>=2), semitone_delta, is_active, description }
```

### Field semantics

- `CopedantChange.changes` is **relative** (semitones from the open string). The editor removes a key when its delta reaches 0.
- `SplitRule.semitone_delta` is the **net offset from the open string** with all listed controllers engaged. It is not an offset applied on top of the sum.
- `HalfStopRule.semitone_delta` is the net offset from the open string when the controller is half-engaged.
- `is_active=False` rules are kept in the data but ignored by the resolver ("Include/Exclude" in PSG Compass).
- **Changer configuration (E-26):** `changer_raises` / `changer_lowers` are the most controllers that may raise / lower one string. Every pedal or lever with a positive delta on a string uses one raise finger; a negative delta uses one lower finger. Half-stops and splits use no extra finger. `changer_usage(neck)` lists the controllers per string and direction, and `changer_violations(neck)` returns a `ChangerViolation(string_number, direction, controllers, limit)` for each string over the limit. `CHANGER_PRESETS` are the configurations offered in the editor; `DEFAULT_CHANGER = (3, 3)`. Every factory preset fits the default (tested).
- `neck_type` decides which engine path runs. Many places **also** check `"C6" in neck.name` as a fallback, so renaming a neck can change its behavior.

## Serialization

| Method | Format |
|---|---|
| `Neck.to_dict / from_dict` | Native format. String-number dict keys are cast back to `int`. Missing `half_stops`/`splits` default to `[]`. `"changer": {"raises", "lowers"}`; files saved without it load as 3 up – 3 down. An unknown `neck_type` raises `ValueError`. |
| `Neck.from_compass_json` | PSG Compass export: `strings[].openNote`, `pedals[]`, `kneeLevers[]`, `detectedSplits[]`. Zero deltas are dropped. A knee lever with no changes is kept only if `active` is true. `neck_type` is inferred from string count or name. Half-stops are **not** imported. |
| `SteelGuitar.save_to_file / load_from_file` | `{name, necks:[...]}` |

## ID maintenance helpers (`core/models.py`)

- `remap_controller_ids(neck, mapping)`: simultaneous rename across pedals, levers, splits and half-stops; keeps `_HALF` suffixes; renumbers labels that echo the old ID (`P1 (A)`→`P2 (A)`) and keeps custom labels.
- `shift_pedal_ids(neck, ±n)`: Franklin insert and removal.
- `migrate_legacy_ids(neck)`: `VL`→`LKV`; removes retired lever variants and the rules that use them.
- `migrate_half_stop_tokens(neck)`: `P3HS`→`P3_HALF`, and adds default half-stop rules when missing.
- `undefined_rule_controllers(neck)`: validation helper.

## Rule detection helpers

- `detect_potential_splits(neck)` returns **every pairwise** conflict on strings pulled by 2 or more controllers. It reuses existing rules where the (string, pair) matches, and otherwise creates defaults (`0` if the deltas cancel, else ±1). It **does not** return existing rules for 3+ controllers or rules that no longer match.
- `detect_potential_half_stops(neck)` returns only **new** candidates (pulls of ±2 or more that don't already have a rule), defaulting to ±1.
- The two helpers are asymmetric: splits returns existing plus new, half-stops returns new only. The editor's "Auto-Detect" **appends** both kinds to the table, so pressing it twice duplicates split rows.

## Factory presets (`build_standard_d10_guitar()`)

| # | Name | Type | Strings | Pedal IDs | Knee IDs | Notes |
|---|---|---|---|---|---|---|
| 0 | 10-String E9 Chromatic | E9 | 10 | P1–P3 (A,B,C) | LKL, LKR, LKV, RKL, RKR | Default neck. 4 splits. |
| 1 | 10-String C6 | C6 | 10 | **P4–P8** | LKL/LKV/LKR (empty), RKL, RKR | IDs match the C6 pedal names in the engines. |
| 2 | BE E9 3P-5KL-1HS | E9 | 10 | P1–P3 | LKL, **VL**, LKR, RKL, RKR, **RKR2** | Half-stop modeled as a separate lever `RKR2` (label "RKRHS"), not a `HalfStopRule`. |
| 3 | BE C6 5P-4KL | C6 | 10 | **P1–P5 labelled P4–P8** | LKL, LKR, RKL, RKR | Engines that hard-code P5–P8 hit the wrong pedals here. |
| 4 | GFI 12U 7P-5KL | U12 | 12 | P1–P7 | LKL, VL, LKR, RKL, RKR | 14 splits. |
| 5 | GFI 12U 7P-5KL-3HS | U12 | 12 | same as #4 | same | Adds `HalfStopRule`s on P1/P3/P7 and engagement-aware splits (`["VL","P1_HALF"]` …). Older saved setups with `P1HS` tokens are converted at load by `migrate_half_stop_tokens` (D-08, fixed). |

`core/presets_old.py` is dead legacy code. `core/grip_presets.py` and `core/progression_presets.py` hold static UI content (grip cards and practice progressions). See 03 for their correctness issues.

## Invariants the code assumes but does not enforce

- `open_tuning[i].string_number == i + 1` (the canvas, exporter and editor index by position).
- `string_count == len(open_tuning)`.
- Every controller ID in `splits` and `half_stops` (with `_HALF` stripped) exists in `pedals ∪ knee_levers`. Check with `undefined_rule_controllers(neck)`; every factory preset passes (tested). The editor keeps unknown IDs as "⚠ X (undefined)" entries instead of rewriting them.
- Split `controllers` lists have at least 2 entries. The editor silently drops rows with fewer.
