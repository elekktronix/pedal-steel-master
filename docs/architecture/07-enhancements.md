# 07 — Suggested Enhancements (prioritized)

The order is chosen so each step makes the next one safer. Steps 1–3 also stop future AI edits from silently breaking the music logic.

**Progress (2026-11-03):** E-01 partially done: tests exist and all presets and landmarks are verified; there's no runtime `validate_neck` panel yet. E-02, E-03 and E-06 are done (`core/stances.py` roles). E-07 is done for the star map, Franklin hub, Warnock/Barndo moves, pearls and progression presets. E-15 is done except for ruff and pre-commit. E-16 is partly done (caching and batching; no resolver memoization or worker threads). **E-11 (audio scheduler + swells), E-12 (session) and E-13 (light theme via `ThemeManager`) are done**; see D-39 for the light-mode gaps.

## Phase 1 — Safety net (do first)

**E-01 Neck validation + golden tests.** Add `core/validation.py: validate_neck(neck) -> List[Issue]` with these checks:
- string numbers are contiguous 1..N and `string_count` matches;
- every split and half-stop controller ID exists;
- every split has at least 2 controllers;
- no duplicate (string, controller-set) splits;
- pedal IDs follow the `P\d+` pattern.

Run it on load, on import and on editor Apply (warn, don't block). Add `tests/`:
- `test_resolver.py`: hand-verified stances on every preset (e.g. E9 F3 P1+P2 on 8-6-5 is G C E).
- `test_presets.py`: every factory preset passes `validate_neck`; every progression preset step resolves to its label (this catches D-10 automatically).
- `test_star_map.py`: every landmark resolves to its root and quality.
- `test_roundtrip.py`: `Neck.from_dict(n.to_dict()) == n` and SteelGuitar files.

The scratch checks used to build `06` can be the first tests.

**E-02 Logging.** Replace `print` and `except: pass` with the `logging` module, writing to `~/.psg_visualizer/app.log` (already git-ignored).

## Phase 2 — Single sources of truth

**E-03 One `apply_stance`.** `MainWindow.apply_stance(fret, controllers, pocket, *, play=True, banner=None)` plus `LeverTogglePanel.set_active_controllers()`. Delete the 7 duplicate handlers and route every dialog's "apply" through a signal to it. Fixes D-03 and D-04.

**E-04 A `StanceState` model.** Move fret, controllers, pocket and target off the canvas into a small `QObject` with a single `changed` signal (with a debounce). The canvas, panels and dialogs subscribe to it. This removes the mirrors listed in 04 and the refresh fan-out (D-31).

**E-05 A controller registry in core.** Move `STANDARDIZED_KNEE_LEVERS` into core with metadata (limb: left foot, left knee, right knee, center knee; physical order). `ErgonomicsEngine`, the lever panel and the editor all read it. Add a `migrate_ids(neck)` that handles `VL→LKV` and pedal renumbering for **all** references (D-07, D-09).

**E-06 Semantic controller roles.** Store roles per neck (`roles: {"A": "P1", "B": "P2", "C": "P3", "F": "LKL", "D": "LKR", "franklin": None}`) instead of guessing from labels and changes (`_resolve_e9_controllers`) or hard-coding IDs. The star map, relative moves, scale combos and Newman temperament all look roles up. Fixes D-23 and makes BE C6 work.

## Phase 3 — Musical correctness

**E-07 Resolver-driven content.** Generate landmarks, Warnock/Barndo moves, pearls and the Franklin hub as **shape templates (strings + role-controllers + fret offset)**, then check each one with the resolver and `ChordIdentifier` and drop any that fail. Then nothing can be mislabeled (D-10, D-14, D-15).

**E-08 Formula coverage.** Add m7b5, 9, 11, 13, add9, 6/9, 7sus4 and 7#9 to `CHORD_FORMULAS` and `ChordIdentifier` (rootless or omitted-5 aware). Make `normalize_chord_type` strict (D-11).

**E-09 Split model v2.** Decide how half-stops and splits combine (engagement-aware keys) and how 3+ controller conflicts resolve (per-neck policy). Migrate 12U-3HS and BE E9 (`RKR2`) to real `HalfStopRule`s (D-08).

**E-10 Spelling-aware note names.** Show flats in flat keys (`prefer_flat` from the key center) on the canvas, tables and PDF. Accept any enharmonic root in every combo (D-05, D-18).

## Phase 4 — Audio

**E-11 Rewrite `MidiAudioEngine`.** Build a single worker thread with a queue (no thread per note). Use the channel map from D-01, note-off scheduling, and per-string pitch bend that applies Newman cents for the active controllers. Use `glide_string_pitch` when a controller is toggled while a pocket is sounding (pedal-steel "swells"). Add a cross-platform fallback such as `mido`/`python-rtmidi` or a built-in SoundFont synth.

## Phase 5 — UX and housekeeping

- **E-12** Persist the session: neck index, fret, controllers, pocket, target and window/dock geometry (`QSettings`).
- **E-13** Theme tokens: replace the about 20 inline dark stylesheets with QSS classes driven by `themes.py`, so light mode works everywhere.
- **E-14** Editor: per-neck working copy with a dirty indicator and "discard changes?" prompt. Undo/redo for matrix edits. Show a validation panel using E-01.
- **E-15** Delete the dead modules (D-29). Fix `requirements.txt` (D-30). Add `ruff` with a pre-commit hook that rejects `[cite:` markers.
- **E-16** Performance: cache `resolve_neck_state` by key, give `Neck` a `version` counter that bumps on edit, and run heavy searches (voice leader, voicing finder) in a `QThreadPool` with a progress indicator.
- **E-17** PDF: add tables for splits, half-stops and voicing matches (the parameter already exists).

## Working agreement for future AI sessions

1. Paste `00-critical-rules.md` plus the doc for the area you're touching.
2. Name the defect or enhancement ID you're working on.
3. Ask for a **diff limited to the named files**. Forbid rewriting whole files you didn't name.
4. After each change, run `pytest` (once E-01 exists) and update `06`/`07` and any affected section of `01`–`05`.
