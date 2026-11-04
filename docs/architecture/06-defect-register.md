# 06 — Defect Register

**Severity:** **P0** = crash or user-data corruption · **P1** = wrong musical output or a broken feature · **P2** = latent, UX or code health.
The IDs are stable. Reference them in commits ("fix D-07") and keep this file current. Fixed defects stay listed so their regression tests can be traced.

**Status:** all baseline defects are fixed, plus D-34, D-35, D-37 and D-38. Open: D-36, D-39, D-40.

## Open

| ID | Sev | Location | Issue | Suggested fix |
|---|---|---|---|---|
| D-36 | P2 | `core/permutation_engine.py` | The 24 patterns are unique, but neither the table nor the names have been checked against Franklin's book. The replacements for 18, 20, 21 and 23 are placeholders. | Check against the source and correct the patterns and names. |
| D-39 | P2 | `ui/copedant_editor_dialog.py`, `ui/voice_leader_dialog.py` | Light mode (E-13) only adapts *stylesheets*. Colors set through `QColor` (the editor's matrix header items) and the voice leader's always-light measure cards are not theme-aware. | Move them to stylesheets, or read colors from the active theme. |
| D-40 | P2 | `ui/themes.py` | A theme switch re-styles every widget (about 0.9 s with all pop-outs created). | Acceptable for a menu action. If it grows, cache the light QSS per original string. |

## Fixed

| ID | Sev | Original defect | Resolution | Tests |
|---|---|---|---|---|
| D-01 | P1 | Pocket pitches mapped to strings 1..n by list position; string 10 on MIDI drum channel 9; strings 11–12 shared channels; scale sequences never released notes. | `STRING_CHANNELS` (0–8, 10–14) + `SEQUENCE_CHANNEL` 15. `_play_pocket` passes `{string: midi}`. Node clicks and the permutation trainer send the string number. Sequences send note-offs. State is locked. | `AudioTests`, `MainWindowTests.test_play_pocket_uses_string_numbers` |
| D-02 | P0 | Loading a profile overwrote the factory neck slot; edits never went back to the profile. | `Neck.source_profile`; a profile opens as its own linked neck entry; editor Apply writes back. | `test_core_integrity` |
| D-03 | P1 | Programmatic stance changes didn't update `LeverTogglePanel` state or the badge, so the next click emitted a stale set. | `MainWindow.apply_stance()` + `LeverTogglePanel.set_active_controllers()` replace 7 duplicated handlers. | `test_apply_stance_syncs_lever_panel` |
| D-04 | P1 | Voice-leader "apply" used `setChecked` on non-checkable buttons. | New `VoiceLeaderDialog.voicing_applied` signal → `apply_stance`. | (through D-03 path) |
| D-05 | P1 | Flat roots (Db/Eb/Ab/Bb) snapped back in the up-the-neck dropdown. | `theory.to_root_name()`; the harmonic panel and voicing finder accept any spelling; the dropdown syncs by pitch class. | `test_flat_root_in_up_neck_dropdown_sticks`, `test_root_respelling` |
| D-06 | P2 | `get_c6_diminished_matrix_matches` raised `AttributeError`. | Removed (unused). | — |
| D-07 | P0 | The editor's VL→LKV rename left splits dangling, and unknown IDs fell back to P1 on save. | `migrate_legacy_ids` remaps rules; dropdowns keep "⚠ X (undefined)" values. | `test_core_integrity` |
| D-08 | P0 | 12U-3HS splits referenced nonexistent `P1HS`-style controllers. | `HalfStopRule`s + `P1_HALF` split tokens; engagement-aware matching; load-time `migrate_half_stop_tokens`. | `test_core_integrity` |
| D-09 | P0 | Franklin P1 insert and offset renumbered pedals without remapping rules. | `remap_controller_ids` / `shift_pedal_ids`; labels kept. | `test_core_integrity` |
| D-10 | P1 | Preset chord labels didn't match the sounding chords (E9 Em/Am; every C6 "7" chord). | Presets rebuilt with role tokens and solver-found voicings (C6 dominants via Pedal 8). The sequencer maps presets onto the active neck and refuses mismatched tunings. | `test_progression_presets_sound_their_labels` (5 necks) |
| D-11 | P1 | Unknown chord types silently became Major. | `Half-Diminished` and `6/9` added; alias map extended; `UnknownChordTypeError`. | `test_normalize_is_strict` |
| D-12 | P1 | `solve_progression` returned a misaligned list when a chord was unsolvable. | DP over solvable steps; always one entry per measure. | `test_results_align_with_measures` |
| D-13 | P1 | Thumb assigned to the highest-pitched string; only 20 of the 24 permutations were unique. | Bass-first ordering; 4 duplicates replaced (see D-36). | `test_permutations_unique_and_thumb_on_bass` |
| D-14 | P1 | C6 "Upper Min" sounded C major; "1st Inv" was really 2nd inversion. | Correct C6 minor shapes; every landmark verified with the resolver. | `test_star_map_landmarks_sound_their_chord`, `test_c6_minor_upper_shape_is_minor` |
| D-15 | P1 | The Franklin hub's iii used RKL (it sounds Bsus4). | iii = D lever; every hub entry verified on the neck. | `test_franklin_hub_iii_uses_d_lever` |
| D-16 | P2 | ASCII tab columns drifted (cells 10 wide, headers 12). | All columns `col_width`. | `test_tab_columns_align` |
| D-17 | P1 | Nashville substring parsing ("Dominant 7th" → 1-). | Family-based suffixes; prefix parser fallback; the canvas passes the family. | `test_nashville` |
| D-18 | P1 | Circle neighbors fell back to C for C#/D#/G#/A#/Gb. | Key located by pitch class. | `test_circle_neighbors_for_sharp_keys` |
| D-19 | P1 | Newman temperament had no effect and wasn't applied at startup. | `compute_newman_cents` (role-based, standard 10-string E9 only) is applied to pockets, node clicks and arpeggios; the setting is applied at startup. | `test_newman_cents` |
| D-20 | P0 | The Profiles dialog's Save crashed (`save_neck_profile` didn't exist). | Fixed call; name validation; overwrite confirm. | `test_core_integrity` |
| D-21 | P2 | PDF export and setup import/export crashed on I/O or parse errors. | try/except + message box + log. | — |
| D-22 | P0 | The editor lost edits on neck switch; Duplicate mutated on cancel; every Apply wrote a profile. | Per-neck working copies; linked-only profile writes; `guitar_changed`. | `test_core_integrity` |
| D-23 | P1 | Engines hard-coded E9/C6 controller IDs (BE C6 broken; dialogs always E9). | `core/stances.py` functional roles; star map, relative moves, scale combos, pearls, flashcards, presets and Newman cents all role-based; dialogs receive the active neck. | `RoleTests`, `test_barndo_moves_use_pedal_function_on_be_c6`, `test_scale_boxes_on_be_c6_use_pedals` |
| D-24 | P2 | "All" selected strings 1–14 whatever the neck had. | Uses the neck's string count. | `test_all_button_respects_string_count` |
| D-25 | P2 | The badge read a nonexistent `stance.reason`. | Shows `clash_reasons`. | `test_badge_shows_clash_reason` |
| D-26 | P2 | Profile names could be empty or collide silently. | `sanitize_name` validation and overwrite confirmation (remaining collision risk tracked as D-38). | `test_invalid_names_are_rejected` |
| D-27 | P2 | `Signal(str,str)` turned `None` into `''`. | `Signal(object, object)`. | `test_none_root_clears_analysis` |
| D-28 | P1 | The relative-moves widget parsed chord types from display text (maj7 → Dom7, dim → Minor). | `RelativeMoveOption.chord_root/chord_type`. | `test_same_fret_options_carry_chord_type` |
| D-29 | P2 | Dead modules, including `[cite]` artifacts. | Deleted `core/presets_old.py`, `core/half_stop_dialog.py`, `ui/half_stop_dialog.py`, `ui/split_manager_dialog.py`, `ui/pocket_panel.py` and `split_tuner_dialog.py`; removed `[cite]` comments. | — |
| D-30 | P2 | `requirements.txt` was UTF-16 and included unused WebEngine/Pdf. | UTF-8; Essentials, Addons, shiboken6 and reportlab (pillow and charset-normalizer come in through reportlab). | `pip install --dry-run` |
| D-31 | P2 | Refresh fan-out; the scale solver resolved the neck per string; the circle widget re-searched on every lever change. | `apply_stance` batches refreshes; the scale solver caches per (fret, combo); the circle caches voicings per neck and window (≈460 ms → 6 ms per lever change). | timing check |
| D-32 | P2 | Incomplete defaults; settings file tracked in the repo. | Complete `DEFAULT_SETTINGS`; settings saved to `~/.psg_visualizer/app_settings.json`; the repo file is read once as a legacy fallback and is now untracked and git-ignored. | — |
| D-33 | P2 | No tests, `print`-only diagnostics, silent `except: pass`. | 41 `unittest` tests; `logging` to `~/.psg_visualizer/app.log` (configured in `main.py`); remaining silent excepts now log. | `tests/` |
| D-34 | P2 | Pearls stances that don't touch the string pair duplicated the open row. | Such stances are skipped. | `PearlsTests` |
| D-35 | P2 | `glide_string_pitch` was unused; one thread per note. | Single scheduler thread (E-11); pedal/bar swells wired to lever and fret changes. | `AudioSchedulerTests`, `test_lever_toggle_swells_ringing_strings` |
| D-37 | P2 | Unused `get_c6_open_chords` / `get_newman_minor_anchors`. | Removed. | — |
| D-38 | P2 | Names that sanitize to the same file were only confirmed, not prevented. | `ProfileManager.unique_profile_name` + `ui/profile_prompts.choose_profile_name`: Overwrite / Save as "Name 2" / Cancel. | `ProfileNamingTests` |
