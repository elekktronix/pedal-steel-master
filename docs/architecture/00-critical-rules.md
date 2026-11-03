# 00 — Critical Rules (paste into every AI chat)

These are invariants the code depends on. Breaking one causes silent wrong pitches or data loss, not crashes.

## A. Identity and numbering

1. **Strings are 1-indexed, and 1 is the highest-pitched string** (nearest the player's face). The bass string has the highest number. "Lowest string" in comments sometimes means "lowest number"; check before editing.
2. **Controller IDs are positional; labels are cosmetic.** `P1` is the leftmost pedal. On the BE C6 preset, `P1` carries the label "P4". Engine code that hard-codes `"P5"`/`"P6"` means the **ID**, not the label. Never match on labels for logic (the exception is the existing "Franklin" label check; see rule 10).
3. Knee lever IDs: `LKL`, `LKV`, `LKR`, `LKL2`, `CKL`, `CKV`, `CKR`, `RKL`, `RKR` (`STANDARDIZED_KNEE_LEVERS` in `ui/copedant_editor_dialog.py`). Legacy `VL` exists in presets (`BE E9`, `GFI 12U`) and is **renamed to `LKV` when the copedant editor opens**, using `core.models.migrate_legacy_ids`, which also rewrites split and half-stop references. Engines never depend on either name: they use functional roles (rule 8a), so `VL` and `LKV` both resolve to role `BL`.
4. `ErgonomicsEngine` treats any ID starting with `"P"` as a foot pedal and parses the digits as its position. Knee IDs it doesn't recognize (`VL`, `RKR2`, `CK*`) are **not** checked for knee clashes.

## B. Pitch resolution (see 02)

5. **Sounding MIDI = open MIDI + bar fret + controller delta.** Controller delta comes from exactly one source, in this priority:
   1. one controller pulls the string → its delta (or its half-stop delta);
   2. two or more pull, and an **active** `SplitRule` whose `controllers` set **equals** the set of pulling controllers → the rule's `semitone_delta` **replaces** the sum;
   3. otherwise → the **sum** of the deltas.
6. A split rule matches **only on exact set equality** with the controllers *that actually pull that string*. Engaged controllers that don't touch the string are ignored. A two-controller rule never fires when three controllers pull the same string.
7. **Half-stop engagement is encoded as the string `"<ID>_HALF"`** inside `engaged_levers`. Its delta is the matching active `HalfStopRule.semitone_delta`, or ±1 by default. Split rules may list half tokens (`["LKL", "P3_HALF"]`). Matching tries the **engagement-aware set first** and then falls back to the base-ID set, so a half-engaged P3 plus LKL uses a `P3_HALF` rule if one exists and otherwise the full P3+LKL rule. A half-stop can only be engaged in the UI if the neck has an active `HalfStopRule` for that controller.
8. `FretboardResolver.resolve_neck_state` is the **only** pitch calculator. Never compute pitches from hard-coded tunings.
8a. **Engines name controllers by functional role, not by ID** (`core/stances.py`): E9 `A`, `B`, `C`, `F`, `D`, `BL`; C6 `C6P4`…`C6P8`. Map them with `resolve_stance(neck, tokens)`, which returns `None` if the neck lacks the controller (skip the shape). Every static shape table must be checked with `grip_matches_chord`, either at runtime or in tests.

## C. State ownership (see 04)

9. **`MainWindow` owns the current stance**, and the canonical copy lives on `FretboardCanvas`: `bar_fret`, `engaged_levers`, `active_pocket`, plus target root, chord or scale. Panels hold mirrors. **Every programmatic stance change goes through `MainWindow.apply_stance(fret, controllers, pocket, play=, banner=)`**, which syncs the canvas, fret widgets and `LeverTogglePanel.set_active_controllers()` (buttons, state and badge), and refreshes dependent views once. Never set lever buttons directly.
10. Franklin-pedal detection is `"Franklin" in neck.pedals["P1"].label`. The C6 "+1 offset" toggle and the editor's "insert Franklin P1" both **renumber pedal IDs**. **All controller renames and renumbers must go through `core.models.remap_controller_ids` / `shift_pedal_ids`**, which remap splits and half-stops (including `_HALF` tokens) and renumber labels that echo the ID. Engine code that hard-codes pedal IDs is *not* remapped.
11. `self.guitar.necks[self.current_neck_idx]` is "the active neck". Loading a user profile **adds it as its own neck entry** (`Neck.source_profile` = profile name; shown with 📁). Loading it again refreshes that entry. It never overwrites a factory or other neck.

## D. Persistence (see 05)

12. On startup, `~/.psg_visualizer/profiles/active_guitar_setup.json` **wins over `core/presets.py`** if it exists. Changes to presets in code do not reach existing users until that file is deleted or migrated. Load-time migrations live in core (`migrate_half_stop_tokens` runs on startup, file import and profile load).
13. `active_guitar_setup.json` lives in the profiles folder but is excluded from the profile list by filename. Don't rename it.
14. Editor Apply writes a profile file **only for profile-linked necks** (`neck.source_profile`). Factory and imported necks persist only through `active_guitar_setup.json`. The editor keeps a working copy per neck, and Apply commits every neck edited in that session. Duplicate and Save-as-Profile add a linked neck **immediately**, and the editor sets `guitar_changed` so MainWindow refreshes even on Cancel.
15. JSON formats: `SteelGuitar` = `{name, necks:[Neck.to_dict()]}`; a user profile = a single `Neck.to_dict()`; a PSG Compass import is detected by having both `"strings"` and `"pedals"` keys. Dict keys for string numbers become **strings** in JSON and are cast back with `int()` in `from_dict`. Keep that cast.

## E. Coding conventions to keep

16. `core/` must stay free of Qt (move `core/half_stop_dialog.py` out, or delete it).
17. Engines return dataclasses (`VoicingMatch`, `ScaleBox`, `StarMapLandmark`, `RelativeMoveOption`, `PearlStep`). UI code reads attributes; don't swap these for tuples or dicts.
18. Chord type names are the keys of `theory.CHORD_FORMULAS` (`"Major"`, `"Minor"`, `"Dominant 7th"`, `"Half-Diminished"`, …). Unknown types raise `UnknownChordTypeError`; never fall back to Major. Root names come from `NOTE_TO_SEMITONE` (sharps **and** flats). Convert with `theory.to_root_name()` when a widget needs a specific spelling. Carry chord root and type as data fields; never parse them back out of display labels.
19. Chord interval labels come from the formula dicts (`"R"`, `"3"`, `"b3"`, `"5"`, `"b7"`, …). Scale degree labels use `"1"`, `"2"`, …. The canvas colors nodes by these strings. Don't rename them.
20. When asking an AI to edit code, forbid citation markers (`[cite: N]`). They have already leaked into source files and can be valid Python syntax that fails at runtime.
