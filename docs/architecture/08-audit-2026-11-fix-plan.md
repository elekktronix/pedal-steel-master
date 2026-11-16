# 08 — Audit fix plan (external audit, 2026-11-12)

Status (2026-11-16): **in progress. P1 items done** (moved to `06-defect-register.md` as D-49–D-52; tests in `tests/test_audit_a.py`). The 2026-11-16 audit fixes (`09`, B-items) also closed parts of A3 and A5. P2, P3 and the docs batch are open.

| Item | Status |
|---|---|
| A1 | ✅ Fixed (D-49) |
| A2 | ✅ Fixed (D-50). Open questions decided: `RKR2` kept and grouped with the right knee; `LKL2` left knee; `CKL/CKV/CKR` a centre group (one at a time, not with both side knees busy). |
| A3 | ◐ Partly: Auto-Detect Splits no longer duplicates rows (B7). Remove paths, 3-controller rules and Control 1 == Control 2 are open. |
| A4 | Open |
| A5 | ◐ Half: `close()` clears the scheduler queue (B2). Newman cents order is open. |
| A6, A8, A9, A11, A12 | Open |
| A7 | ✅ Fixed (D-51): no voicing passes the filter → nothing moves, status bar explains |
| A10 | ✅ Fixed (D-52) |
| Docs batch | Open (05 now describes the startup settings, not yet in the key list) |

Source: an external audit (Argon) of `core/` and `ui/`, then re-checked against the code on 2026-11-12. Every item below was confirmed by reading the current source unless marked otherwise. The audit's line numbers were off, so the locations here are current ones (verify again before editing, they drift).

Proposed IDs continue the defect register (last used: D-48). Move each item into `06-defect-register.md` when it is fixed, and mark it fixed there instead of deleting it. Per `CLAUDE.md`: minimal diffs, resolve musical changes through `FretboardResolver` in a test, keep `core/` Qt-free.

Suggested order: **P1 first (A1, A2, A7, A10), then P2, then the docs batch.**

---

## Code defects

### A1 (P1) — Same-fret chord options mislabel aug / m6 / m7b5 and leak display tags
- **Where:** `core/relative_moves.py` `get_all_same_fret_chords` (the `identify_voicing` call and the `is_dim` / `is_minor` / `is_dom` ... chain); `core/chord_identifier.py` (Major 6 candidate hardcodes `• Root (R)` / `• Inversion`; triad and 7th candidates append `group_tag`).
- **Problem:** the function gets `(raw_tag, family)` but ignores `family` and substring-parses `raw_tag`. Consequences:
  - `Eaug` matches none of the checks, falls to the `else` branch and is labelled a major triad (`I (E)`).
  - `Am6` matches `"m" in q_low` and becomes a plain minor triad, colliding with the real minor triad in `best_chord_map[(roman, clean_root)]`.
  - `m7b5` goes into the `dim` branch and is shown with `°`.
  - `chord_name` is built from the parsed tag, so it can read `"E Maj • Group 2"` or `"C 6 • Root (R)"`.
  - This is the same class of bug as D-28 and violates the rule against parsing display text (Critical Rule 18).
- **Plan:** branch on `family` (through `_FAMILY_TO_CHORD_TYPE` / `CHORD_FORMULAS`) for roman numeral, category and pill label. Build `chord_name` from root plus the formula suffix, never from `raw_tag`. Give Augmented, Minor 6 and Half-Diminished their own roman/pill forms and categories. In `chord_identifier.py`, make the Major 6 tag honour `show_inversion` and drop the group tag from anything that feeds `chord_name` (or have `relative_moves` stop passing `grip_strings`).
- **Test:** extend `test_same_fret_options_carry_chord_type`: resolve an aug grip and an m6 grip through `FretboardResolver`; assert `chord_type`, that `Am6` and `Am` are separate options, and that no `chord_name` contains `•`.

### A2 (P1) — Unmigrated `VL` / `RKR2` bypass knee-clash detection on a fresh launch
- **Where:** `core/profile_manager.py` `prepare_loaded_guitar` (calls only `migrate_half_stop_tokens`) and `factory_guitar`; `core/presets.py` (`VL` in the BE E9 and GFI 12U builders, `RKR2` "RKRHS" in BE E9); `core/ergonomics.py` `LEFT_KNEE_LEVERS` / `RIGHT_KNEE_LEVERS`; `core/models.py` `migrate_legacy_ids`.
- **Problem:** only `CopedantEditorDialog` calls `migrate_legacy_ids`. Until the user opens the editor and applies, `VL` and `RKR2` are unknown to `ErgonomicsEngine`, so impossible stances (LKL+VL, LKR+VL, RKL+RKR2, RKR+RKR2) count as feasible in the solver, Chord Atlas, compare and voice leading. Applying in the editor then renames `VL` to `LKV` and changes the chord vocabulary. `ErgonomicsEngine` also has no clash rules for `LKL2`, `CKL`, `CKV`, `CKR` (`STANDARDIZED_KNEE_LEVERS`).
- **Plan:** call `migrate_legacy_ids` before `migrate_half_stop_tokens` in `prepare_loaded_guitar` and in the factory path, so every load path is migrated. Prefer fixing the presets to use the standard IDs at the source (`LKV`), if no saved profile depends on `VL`. Then extend the ergonomics sets from `STANDARDIZED_KNEE_LEVERS`.
- **Open questions (decide before coding):** (1) is `RKR2` in `RETIRED_KNEE_LEVER_IDS`? If so, loading will now remove the BE E9 `RKR + RKR2` split, which changes that preset's vocabulary. Decide whether that is intended. (2) which side (left/right knee) the centre levers `CKL/CKV/CKR` and `LKL2` belong to.
- **Test:** load every factory preset and a legacy profile through `prepare_loaded_guitar`; assert no `VL` / `RKR2` IDs remain and `undefined_rule_controllers` is empty; assert `evaluate_stance({"LKL","LKV"})` is impossible on a fresh load; re-run the preset landmark tests (vocabulary change).

### A3 (P2) — Copedant editor leaves dangling references and duplicates auto-detected splits
- **Where:** `ui/copedant_editor_dialog.py`: `_remove_string` (about line 1077), `_remove_pedal`, `_on_lever_toggled`, `_auto_detect_splits` (468), `_save_splits_from_ui` (474), `_insert_split_row` (419).
- **Confirmed:**
  - `_auto_detect_splits` inserts every rule `detect_potential_splits` returns without clearing the table. That function returns existing rules plus new ones, so each click duplicates the rows.
  - `_remove_string` pops the tuning and rebuilds the matrix only. It leaves that string's pulls in pedals/levers and its rules in splits and half-stops.
  - `_insert_split_row` shows only `controllers[0]` and `[1]`, and `_save_splits_from_ui` writes exactly two, so a 3-controller rule is silently cut to two on Apply. Nothing stops Control 1 == Control 2.
- **Not re-read individually:** the pedal-removal and lever-uncheck paths. Same fix class; confirm when implementing.
- **Plan:** (a) clear `splits_table` before inserting auto-detected rules (or dedupe by `(string, frozenset(controllers))`). (b) put a pruning helper in `core/models.py` (stays Qt-free): drop pulls on removed strings, drop rules referencing removed strings or controllers (strip `_HALF`), and call it from the remove paths, then refresh both tables. (c) reject rows where Control 1 == Control 2 in `_save_splits_from_ui`, and either support 3 controllers in the table or preserve the extra controller and warn. Pick one and document it (a rule in `01-domain-model.md` already says rules need at least 2 controllers).
- **Test:** auto-detect twice and assert the row count is unchanged; remove the last string and assert `undefined_rule_controllers` is empty and no rule references the string; round-trip a 3-controller rule.

### A4 (P2) — `.cp` import drops mid-bar rests; `PlaybackPlan.build` crashes on an empty progression
- **Where:** `core/progression_studio.py`: `steps_from_chord_progression` (filter `if s.root and s.chord_type`, about line 196) and `PlaybackPlan.build` (about line 473).
- **Problem:** a rest slot (`chord: None`) is filtered out, so a bar with G on beat 1 and a rest on beat 3 gives G for 4 beats instead of 2 + a 2-beat rest. `build` computes `starts[first]` on an empty list and raises `IndexError`.
- **Plan:** keep rest slots in the sorted slot list; when a chord is followed by a rest, give the chord the beats up to the rest and emit a `StudioStep(beats=...)` rest. Add `if not prog.steps` handling in `build` (return an empty plan, or have callers refuse to play an empty progression).
- **Test:** import `[{"beat":1,"chord":{...G}},{"beat":3,"chord":None}]` and assert two steps of 2 beats; round-trip with `to_dict`; `PlaybackPlan.build` on an empty progression does not raise.

### A5 (P3) — Non-deterministic Newman cents; queued notes play during `close()`
- **Where:** `core/audio.py` `compute_newman_cents` (line 79) and `MidiAudioEngine.close` (line 389).
- **Problem:** `pulling` follows the iteration order of `engaged` and the loop `break`s on the first controller with a role. If `engaged` is a set and two controllers with roles pull the same string, the offset depends on set order. `close()` schedules `_sustain_off` then `drain(0.5)` without clearing the queue, so notes queued for later (scales, arpeggios) still sound during shutdown. (The audit said `self._scheduler._queue`; check the `_Scheduler` API for a proper clear method rather than reaching into the private list.)
- **Plan:** iterate `pulling` in a stable order (sorted, or a fixed role priority), documented. Add a `clear()` to `_Scheduler` (under its condition lock) and call it in `close()` before the sustain-off.
- **Test:** two engaged controllers pulling one string return the same cents for every input order; `close()` with a far-future queued note sends no note-on.

### A6 (P2) — Stance inspector: double apply/play and stale string buttons
- **Where:** `ui/stance_chord_inspector_dialog.py` `_apply_and_play_grip` (about line 429), `_init_ui` (about line 132–153), dyad name slicing (line 317); `ui/main_window.py` (line 1316, `grip_applied` connected to `_apply_pocket_preset`).
- **Problem:** `grip_applied` is already wired to `_apply_pocket_preset`, and the dialog also calls `parent_window._apply_pocket_preset` and `_play_pocket` itself, so the preset is applied twice. The dialog is cached across neck switches but `string_check_buttons` is built once from the first neck's `string_count`, so a 10→12-string switch lacks buttons 11–12 and 12→10 leaves dead ones.
- **Plan:** drop the direct `_apply_pocket_preset` call and keep the mediator pattern. Pick one of: add a `played` signal that `MainWindow` connects to `_play_pocket(roll=False)`, or have `MainWindow` play after applying. Rebuild the string buttons from `neck.string_count` whenever the neck changes (e.g. in `refresh_scan`, only when the count differs). Use `rstrip("-0123456789")` for the dyad names.
- **Test:** a counting stub on `_apply_pocket_preset` sees one call per Apply; a neck switch from 10 to 12 strings yields 12 buttons.

### A7 (P1) — Circle of fifths ignores the "Movement Mechanics Allowed" filter
- **Where:** `ui/circle_of_fifths_widget.py` (signal `chord_triggered = Signal(str, str, bool, set)`, emitted with `allowed` at about line 626); `ui/main_window.py` `_on_circle_chord_triggered(self, root, chord_type, add_to_sequencer)` (about line 1042).
- **Problem:** the handler drops the 4th argument and takes `all_matches[0]`, so a button whose cue says it is reachable by "Hold Pedals & Slide" can jump to a different fret and stance than the cue promised.
- **Plan:** accept `allowed: set`, and filter `all_matches` with `VoicingSolver.classify_movement` against the current stance, using the same logic the widget uses for its cue labels (share one helper so the two cannot diverge). If nothing passes the filter, fall back to the old behaviour, or do nothing and say so in the status bar. Decide which.
- **Test:** with the filter set to Same-Fret, the chosen match has the same fret as the current bar; the chosen match always satisfies the cue shown on the button.

### A8 (P3) — `MainWindow.closeEvent` leaves modeless windows open
- **Where:** `ui/main_window.py` `closeEvent` (about line 1608).
- **Problem:** closes the scale finder, circle widget and stance inspector but not `_compare_dlg`, `_atlas_dlg` or `_perm_trainer`. They are top-level `Qt.Window`s, so they can outlive the main window and keep the app from exiting after `audio.close()`.
- **Plan:** close them with the others (guard with `getattr(..., None)`), before `audio.close()`.
- **Test:** open each dialog, close the main window, assert none is visible. Follow the CLAUDE.md rule on really deleting Qt windows in tests.

### A9 (P3) — `_arpeggiate_active_pocket` uses GUI timers
- **Where:** `ui/main_window.py` (about line 735).
- **Problem:** one `QTimer.singleShot` per note with a lambda capturing state, instead of the engine's `delay` parameter used by `_play_studio_step`. `silence_all()` cannot cancel these.
- **Plan:** call `self.audio.play_note(..., delay=i * 0.1)` and drop the timers. Check `play_note`'s `delay` unit (seconds) first.
- **Test:** after `silence_all()` no pending arpeggio note sounds.

### A10 (P1) — Scale finder and permutation trainer play without Newman cents
- **Where:** `ui/scale_finder_widget.py` (`play_note_requested = Signal(int)`, emits at about lines 629, 886, 893, 907, 961), `ui/main_window.py` (line 962 connects it straight to `audio.play_note`), `ui/permutation_trainer_dialog.py` (about line 348, `play_note` without `cents_offset`).
- **Problem:** D-19 says compensated tuning applies to pockets, node clicks and arpeggios. Scale steps and permutation notes play in plain 12-TET even with Newman enabled, and the scale finder notes play on the sequence channel, with no string or cents info.
- **Plan:** extend the signal to carry `(midi, string_number)` where the scale note knows its string (check the scale engine's note type), and route it through a `MainWindow` slot that computes `self._current_cents([string])`. In the trainer, pass `cents_offset` from `parent_window._current_cents`.
- **Test:** with Newman on and a standard E9 neck, the cents passed for a string with a known offset are non-zero; the trainer call includes `cents_offset`.

### A11 (P3) — Note-spelling change does not refresh every open window
- **Where:** `ui/main_window.py` `_set_note_spelling` (about line 883). Only `chord_atlas_dialog` and `copedant_compare_dialog` define `on_note_spelling_changed`.
- **Problem:** the scale finder (legend chips, chord buttons, staircase table), stance inspector (chord names) and Progression Studio (step cards, chord text bar) keep the old spelling until touched.
- **Plan:** add `on_note_spelling_changed()` to those three widgets (re-run their existing refresh) and let the existing top-level loop find it. Check that the Progression Studio dock and scale finder are reached by that loop (docks may not be top-level; call them explicitly if not).
- **Test:** toggle sharps/flats with each window open; assert a visible note name changes.

### A12 (P3) — Small display and export issues
- **Octave stripping:** `ui/fretboard_canvas.py` lines 707 and 709 and `ui/stance_chord_inspector_dialog.py` line 317 use `active_note_name[:-1]`. Use `.rstrip("-0123456789")` as `_draw_scale_overlay` already does, so octave `-1` (a low tuning) does not leave a stray `-`.
- **Exporter ordering:** `core/exporter.py` lines 93 and 95 use `sorted(neck.pedals.keys())` and `sorted(neck.knee_levers.keys())`, which sorts lexicographically (`P1, P10, P2`) and alphabetically. Use positional pedal order (numeric part of the ID) and the `STANDARDIZED_KNEE_LEVERS` order, with unknown IDs last. A shared helper in `core/` can serve both the exporter and the editor.
- **Test:** an exporter ordering test with `P1..P10` and a mixed knee-lever set.

---

## Documentation fixes (one batch, no code)

All confirmed against the current tree. Line numbers are approximate.

| File | Fix |
|---|---|
| `02-pitch-resolution.md` (lines 33, 41) | Note names are not always sharps. `core/resolver.py` calls `midi_to_note_name(active_midi)` with the default, which follows the global `note_spelling` setting. Correct both lines. |
| `03-theory-engines.md` (line 77) | `find_circle_neighbors` is described as the Chord Atlas radar. The radar is `chord_atlas.find_neighbors` (E-29, see the later section). |
| `03-theory-engines.md` (line 79) | Remove "Unused helpers still present: `get_c6_open_chords` and `get_newman_minor_anchors`". Both were removed (D-37). |
| `03-theory-engines.md` (table, lines 10, 11, 21, 24) | Consumers "voice leader dialog" and "sequencer" were replaced by Progression Studio (E-32). Update the consumer column. |
| `00-critical-rules.md` (rule 16, line 38) | Drop the reference to `core/half_stop_dialog.py` (deleted, D-29). Keep the rule "`core/` stays Qt-free". |
| `01-domain-model.md` (line 67) | Remove the `core/presets_old.py` sentence (deleted, D-29). |
| `01-domain-model.md` (tree near the top) | Add `profile: str = ""` to the `SteelGuitar` node. |
| `04-ui-state-and-data-flow.md` (line 12) | `current_neck_idx` is persisted via `session.json` and `startup_tuning`, not "resets to 0". |
| `04-ui-state-and-data-flow.md` (lines 62, 122, 134, and the "sequencer visibility" mention at 77) | Remove the sequencer dock and voice leader dialog as live consumers. Keep the legacy `sequencer_visible` fallback only where it describes `session.json` compatibility. |
| `05-persistence-and-audio.md` (line 9) | Add `scale_overlay_label`, `startup_mode`, `startup_profile`, `startup_tuning` to the `app_settings.json` key list (see `core/settings.py` `DEFAULT_SETTINGS`). |
| `README.md` (Layer Map and module inventory) | Add `session` and `scale_chords` to the Live core row (and `session` to the Layer Map). The Tests row lists only 2 of 8 files: add `test_changer_config`, `test_chord_atlas`, `test_copedant_compare`, `test_features`, `test_profiles_ui`, `test_triad_explorer`. |
| `07-enhancements.md` (status header, E-08/E-10/E-12/E-21, line ~103) | Header still says 2026-11-03. E-10 is done (`note_spelling`, `key_aware_spelling`). E-12 is done, in `core/session.py` as `~/.psg_visualizer/session.json`, not `QSettings`. E-21 is done in `progression_studio` (`cadence_progression`, `dice_progression`). E-08: the extended formulas exist in `core/theory.py` (maj9, m9, 11, 13, 13sus4, 7b9, 7#9, 7b5, 7#5), so only `ChordIdentifier` recognition of them remains. Replace "run `pytest` (once E-01 exists)" with `python -m unittest discover -s tests -v`, as `CLAUDE.md` says. |

When item A1 or A10 changes behaviour, update the matching section of `03` / `04` / `05` in the same change.

---

## Not re-verified (check when picking these up)
- The `_remove_pedal` and `_on_lever_toggled` paths in A3 (same fix class as `_remove_string`).
- Whether `factory_guitar` has its own load path separate from `prepare_loaded_guitar` (A2).
- Whether `engaged` is always a set at every `compute_newman_cents` call site (A5). The fix is cheap either way.
