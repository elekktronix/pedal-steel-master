# 03 — Theory & Practice Engines (`core/*`)

Each engine is a class of `@classmethod`s with no instance state. **Copedant-aware** means it resolves pitches through `FretboardResolver` for the actual `Neck`, and names controllers by functional role (`core/stances.py`) rather than hard-coded IDs.

| Engine | Entry point(s) | Output | Copedant-aware? | Consumers |
|---|---|---|---|---|
| `stances` | `detect_roles`, `resolve_stance`, `grip_matches_chord`, `is_c6_neck`, `controller_display_names`, `describe_controllers` | role map / ID set / bool / ID → name / text | ✅ (it *is* the adapter) | star map, relative moves, scale, pearls, presets, audio |
| `theory` | formulas, `note_to_midi`, `get_nashville_chord_symbol`, `to_root_name` | dicts / str | n/a | everything |
| `chord_identifier.ChordIdentifier` | `identify_voicing(pitches, bass, show_inversion, grip)` | `(display_tag, family)` | n/a (pitch-only) | canvas, relative_moves, stance inspector |
| `voicing_solver.VoicingSolver` | `find_all_voicings`, `find_circle_neighbors`, `get_triad_substitution`, `classify_movement` | `List[VoicingMatch]`, `List[NeighborVoicing]` | ✅ | circle widget, voice leader, triad explorer, main (`find_circle_neighbors` is no longer used by the UI) |
| `voice_leader.VoiceLeadingEngine` | `solve_progression(neck, prog, constraints)` | one `Optional[VoicingMatch]` per measure | ✅ | voice leader dialog |
| `scale_chords` (E-31) | `chords_in_scale(root, scale, sevenths=None)`, `scales_for_chord(root, chord_type)` | `List[ScaleChord]` / `List[ChordScale]` | n/a (pitch classes only) | scale finder chord rows, Chord Atlas "Scales that fit" |
| `scale_engine.ScaleSolver` | `find_scale_boxes(neck, root, scale, span, max_fret)`, `find_scale_in_range(neck, root, scale, min_fret, max_fret)` | `List[ScaleBox]` (≤5) / `ScaleBox` or `None` | ✅ (role combos) | scale finder |
| `relative_moves.RelativeMovesEngine` | `get_all_same_fret_chords`, `get_same_fret_diatonic_hub`, `get_e9_relative_movements`, `get_c6_relative_movements` | `List[RelativeMoveOption]` | ✅ (role stances, verified) | relative moves widget |
| `star_map_engine.StarMapEngine` | `calculate_landmarks(root, type, neck)` | `List[StarMapLandmark]` | ✅ (role stances, verified) | main ribbon, star-map dialog, flashcards |
| `pearls_engine.PearlsEngine` | `generate_scale_run(key, track, scale, max_fret, neck)` | `List[PearlStep]` | ✅ | pearls dialog |
| `flashcard_engine.FlashcardEngine` | `generate_prompt(time_limit, root, neck)`, `evaluate_attempt` | `FlashcardPrompt`, `DrillResult` | ✅ (via star map) | flashcard dialog |
| `triad_explorer` (E-19) | `explore(root, chord_type)`, `find_triad_grips(neck, triad)`, `grip_intervals_over_chord` | `List[TriadOverChord]`, `List[VoicingMatch]` | ✅ (grips re-checked with `grip_matches_chord`) | triad explorer dialog |
| `copedant_compare` (E-25) | `diff_copedants(base, mod)`, `compare_copedants(base, mod)`, `scan_chords(neck)` | `List[CopedantDiffItem]`, `CopedantComparison` | ✅ (resolver; every reported way re-checked with `grip_matches_chord`) | compare dialog (menu + copedant editor) |
| `chord_atlas` (E-27/E-28) | `build_atlas(neck)`, `filter_atlas`, `by_stance`, `coverage`, `grips_for_config`, `find_chord`, `sort_positions`, `find_neighbors` | `ChordAtlas` / `List[AtlasEntry]` | ✅ (compare scan; every way checked with `grip_matches_chord` in tests) | chord atlas dialog |
| `permutation_engine.PermutationEngine` | `generate_sequence(perm_id, strings, cycles)` | `List[PickEvent]` | n/a | permutation trainer, sequencer arpeggiate |
| `tab_generator.TabGenerator` | `generate_ascii_tab(string_count, steps)` | str | n/a | Progression Studio |
| `progression_studio` (E-32) | `StudioProgression`, `parse_progression_text`, `cadence_progression`, `dice_progression`, `preset_progression`, `fill_stances`, `identify_grip_chord`, `tab_steps`, `PlaybackPlan` | dataclasses / step lists | ✅ (presets via roles; voicings via the voice leader) | Progression Studio |
| `progression_presets` | `PROGRESSION_PRESETS`, `resolve_preset_steps(preset, neck)` | presets with role tokens → steps with IDs | ✅ | sequencer |
| `circle_of_fifths.CircleOfFifthsEngine` | `get_diatonic_chords(key)` | `List[DiatonicChordInfo]` | n/a | circle widget |
| `exporter.CopedantPdfExporter` | `export_neck_sheet(...)` | PDF file | ✅ | main (File menu) |

---

## stances.py — roles and shape verification (the copedant adapter)

- **Roles are detected by function** on the open tuning (pitch class of each string), never by ID or label:
  - E9 roles:
    - `A` raises a B string +2 and leaves E and G# strings alone;
    - `B` raises G# +1;
    - `C` raises both E and B by +2;
    - `F` is a knee lever raising E +1;
    - `D` is a knee lever lowering E −1;
    - `BL` is a knee lever lowering B −1.
  - C6 roles (standard pedal numbering):
    - `C6P4` raises A→B;
    - `C6P5` lowers G→F#;
    - `C6P6` lowers E→Eb;
    - `C6P7` raises C→D and A→B;
    - `C6P8` takes C→A, or raises C# and D#.

  If several controllers qualify, the first one by position wins.
- `resolve_stance(neck, tokens)` maps role tokens to IDs. A token that isn't a role name is treated as a literal controller ID (e.g. `"RKL"`). It returns `None` if anything is missing, and callers skip the shape.
- `grip_matches_chord(neck, fret, ctrls, strings, root, type, require_root=True)` is the **verification rule**. It requires that:
  - every string sounds a chord tone;
  - the root is present (unless `require_root=False`);
  - the grip has at least `min(#tones, #strings)` distinct tones.

  Every static shape table (star map, Franklin hub, Warnock/Barndo moves, progression presets) is filtered or tested with it.

## theory.py

- **Global display spelling:** `set_accidental_preference("sharps"|"flats")` (from the `note_spelling` setting) drives `note_names()`, `spell_pc()`, `respell()` and the default of `midi_to_note_name()`. The resolver's `active_note_name`, the `ChordIdentifier` root, relative-moves and star-map roots (`format_chord_root` / `format_root`), pearls, the compare engine and the root dropdowns all follow it. By default, key-aware spellers keep the theory spelling: the circle of fifths spells diatonic chords by key signature, and the triad explorer spells by the backing root's accidental. `set_key_aware_spelling(False)` (setting `key_aware_spelling`) makes them use the global preference too. The circle wheel and its key dropdown always keep the traditional key names (`F#`, `Db`, `Ab`…) and compare roots **by pitch class**, so either spelling highlights correctly. Engines accept either spelling through `NOTE_TO_SEMITONE`.
- `NOTE_TO_SEMITONE` accepts sharps, flats and B#/E#/Cb/Fb. `to_root_name(name, spellings)` respells any enharmonic root into a given spelling list. UI combos use it, so flats are accepted everywhere.
- `CHORD_FORMULAS` has 24 chords. E-18 added `Major 9th`, `Minor 9th`, `Dominant 11th` (9sus4, no 3rd), `Dominant 13th` (no 11), `Dominant 13sus4`, `Dominant 7b9`, `Dominant 7#9`, `Dominant 7b5`, `Dominant 7#5` and `Major 7th #5`. The labels are not identical to `INTERVAL_MAP`: Sus4 uses `"4"`, Dim7 uses `"bb7"`, and the extensions use `"9"`, `"b9"`, `"#9"`, `"11"` and `"13"`. Every key needs an entry in `CHORD_SYMBOL_SUFFIX` (display suffix such as `"13sus4"`) and in `_NASHVILLE_FAMILY_SUFFIX`; `voice_leader.CHORD_TYPE_MAP` has the short aliases (`maj9`, `13`, `7#9`…). Tests enforce this. The canvas colors 9/11/13 labels **before** its `"3" in lbl` test, so `"13"` isn't colored as a 3rd.
- `SCALE_FORMULAS` has 12 scales (semitone → degree label `"1"`…`"7"`).
- `get_nashville_chord_symbol(label, key, family=None)` prefers the chord **family** (ChordIdentifier family or CHORD_FORMULAS key). Otherwise it parses the text after the root by prefix: `maj`→"", `m7b5`→ø, `dim`→°, `aug`→+, `sus`→sus, `m`/`min`→"-", `dom`/`7`/`9`/`11`/`13`→⁷. The canvas passes the family.

## chord_identifier.py

It tries all 12 roots. A root qualifies only if its pitch class is present. Exact pitch-class-set matches are scored: 4-note chords 10, triads 8, shell 7ths 6, dyads 4, plus 2 if the root is in the bass. **No match means `None`** (extensions and rootless voicings aren't recognized; see E-08). Families: `Major 7th`, `Minor 7th`, `Dominant 7th`, `Major 6`, `Minor 6`, `Half-Diminished`, `Diminished 7th`, `Major`, `Minor`, `Diminished`, `Augmented`, `Sus4`, `Dyad`.

## voicing_solver.py

`find_all_voicings(neck, root, chord_type, max_fret=15, filter_awkward, omitted_intervals, max_controllers, allowed_controllers_only)`:
1. Candidate stances: open, every single pedal, every feasible pedal pair, every single knee, every feasible knee pair, and every feasible combination of those (filtered by `ErgonomicsEngine`).
2. Grip candidates come from `STANDARD_E9_GRIPS`, `STANDARD_C6_GRIPS` or `STANDARD_U12_GRIPS`, chosen by `string_count ≥ 12`, then C6, else E9.
3. For each fret and stance, resolve the neck once. For each grip, keep it if every string is a non-omitted chord tone, there are enough unique intervals, and a third-like tone is present when the target has one.
4. Score = 14·unique + 5·has R + 6·has 3rd + 3·(no doubled tones) − ergonomic penalty.

Other functions:
- `find_circle_neighbors` (the Chord Atlas radar) locates the key **by pitch class** (so C#, D#, G#, A# and Gb work), then searches IV, V, V7, vi and ii.
- `get_triad_substitution`: Franklin triad-over-root table.
- Unused helpers still present: `get_c6_open_chords` and `get_newman_minor_anchors` (the latter duplicates star-map logic).

## voice_leader.py

- `.cp` JSON (`tonalCenter`, `tempo`, `measures[].slots[].chord{root,type}`). **Only the first chord per measure** is used (`primary_chord`).
- `normalize_chord_type` maps many aliases (`m7b5`, `ø`, `m6`, `dim7`, `aug`, `+`, `sus4`, `9`, `6`, `69`, …) and **raises `UnknownChordTypeError`** for anything it doesn't know. Loading an unknown type shows an error dialog instead of silently turning the chord into Major.
- `solve_progression` is a Viterbi DP over the voicing candidates of the *solvable* chord measures. The cost terms are:
  - start distance × 2000;
  - jump over `max_fret_jump`: 50000 per fret, else jump × 2;
  - trajectory penalties;
  - pedal changes × 3.

  It **always returns one entry per measure**: `None` for rests and for chords with no voicing.
- For types containing "7"/"9"/"dim" the 5th is left out first; if that finds nothing (Gmaj7 on E9 found none), the full chord is searched (D-47).

## progression_studio.py (E-32)

The Progression Studio's model, Qt-free. A `StudioProgression` (name, key, time signature, tempo, `neck_name`) holds `StudioStep`s: optional chord (`root`, CHORD_FORMULAS `chord_type`), `beats`, optional stance (`fret`, `controllers`, `grip`), `pinned`, `style` (`block` / `roll` / `arpeggio` with a Franklin `perm_id`) and a `label` for unnamed grips. Steps carry durations, so bars hold one chord or several.

- **Stale stances are impossible (D-45):** `set_chord` with a different chord clears the stance and the pin. Loading a progression made on another neck clears its stances.
- **Typed chords:** `parse_chord_symbol` ("Am7", "F#m7b5", "Bbmaj7", "C6/9", "G/B" with the bass ignored) and `parse_progression_text`: without `|` each chord is a bar; with `|` the chords of a bar share it (first chords get the extra beats); `:n` sets beats, `%` repeats, `-`/`N.C.` rests. `format_progression_text` is the inverse.
- **Generated:** `CADENCES` (ii–V–I, iiø–V–i, iii–vi–ii–V, I–vi–IV–V, I–IV–I–V, 12-bar blues) via `cadence_progression(kind, key)`; `dice_progression` (two rolled degrees, each approached by its own V7); `preset_progression` maps a practice preset onto the neck with its stances **pinned**.
- **Voice leading:** `fill_stances(neck, steps, constraints, only_missing)` runs `VoiceLeadingEngine` on each run of free chord steps between anchors (pinned stances; with `only_missing`, every voiced step), starting near the anchor before it. Returns the unsolvable indices.
- **Captured grips:** `identify_grip_chord(neck, fret, controllers, grip, hint)` resolves the grip; the hint (harmonic target) wins when the grip fits it, else bass-first roots, exact matches before ones missing only the 5th.
- **Files:** `to_dict` writes the voice leader's `.cp` format (chord per beat slot; a chord held into a bar is repeated on beat 1) plus a `studio` block with the exact steps; `from_dict` prefers that block, else reads the slots (each chord lasts to the next slot or the bar end; empty bars are rests).
- **Playback:** `PlaybackPlan.build(prog, first, last, count_in_bars, loop).at(k)` says, for beat k after Play, whether it is a count-in beat, accented (bar start), which step starts, or done. `arpeggio_strings` gives the permutation order (one cycle per beat); `tab_steps` turns voiced steps into `TabStep`s (arpeggios as one column per note with the pick finger).

## scale_engine.py

For each anchor window it resolves every (fret, combo) **once** (cached) and keeps the scale tones per string, preferring the variant with the fewest controllers. Boxes are scored and up to 5 are picked greedily, at least 2 frets apart. The combos are role tokens: E9 uses open, A, B, A+B, F, D, A+F and B+RKL; C6 uses open, the five C6 pedals, P4+P5, P5+P6, RKL and RKR. They are resolved per neck.

`find_scale_in_range` (E-30) harvests one user-chosen fret range (inclusive, clamped to 0–24, swapped if reversed) with the same per-string rule and the same strictly ascending run, but without the coverage filter. Both entry points share `_harvest_window`. The scale finder shows the range; `find_scale_boxes` (4-fret windows) only feeds its suggested positions.

Combos whose resolved controllers fail `ErgonomicsEngine.evaluate_stance` are dropped (E-30 phase 2).

**Step order (E-30 phase 2).** `ascending_run` is `playable_run(notes)`: one note per distinct pitch, low to high, where each pitch's spot (string, fret, controllers) is chosen by dynamic programming to minimise the summed `transition_cost`: 3 per fret of bar travel, 2 per controller pressed or released, 1.5 per string skipped beyond the neighbour, 2.5 for moving to a lower-pitched string while climbing, plus 0.5 per controller held for a note (`COST_*` class constants). `run_cost(run)` sums the transitions. `build_run(box, direction, root_to_root)` gives `"up"`, `"down"` (the up run reversed) or `"updown"` (up then back down without repeating the top note, so a `BoxNote` can appear twice), optionally trimmed to the lowest..highest root.

## scale_chords.py (E-31)

Pure pitch-class theory, no fretboard. `chords_in_scale` returns every triad (Major, Minor, Diminished, Augmented) and seventh (Major 7th, Dominant 7th, Minor 7th, Half-Diminished, Diminished 7th) rooted on a scale degree whose tones all lie in the scale, in degree order, as `ScaleChord(root_pc, root_name, chord_type, degree, numeral, symbol, pcs)`. Numerals follow the degree label (`b3` → `bIII`), lower case for minor-family chords, with `°`, `+`, `maj7`, `7`, `ø7`, `°7`. Non-diatonic scales simply yield what fits (blues on G: G, Gm, Em, Edim). `scales_for_chord` returns every (root, scale) containing the chord as `ChordScale(root_name, scale_name, chord_degree, extra_notes)`, own-root scales first, then the closest fits. Fretboard positions stay with the resolver-backed engines: the ringed notes come from the scale map and the voicings from `chord_atlas.find_chord`.

**Display names.** `stances.controller_display_names(neck)` maps controller IDs to player names: E9 roles on E9 necks (`A`, `B`, `C`, `F lever`, `D lever`, `Bb lever`), C6 roles on C6 necks (`P4`…`P8`), otherwise the label. `describe_controllers(ids, names)` joins them pedals first (`"A + F lever"`, `"Open"`, `"C (half)"`). Display only: logic still uses IDs.

## relative_moves.py

- `get_all_same_fret_chords(neck, fret, filter_mode)`: a fixed **role** stance list (E9 or C6) times fixed grips, through the resolver and `ChordIdentifier`. It rejects dyads and stances whose controllers don't touch the grip. The tonic is E (or C for C6) + fret. Options get a Roman numeral, a category, `chord_root` and `chord_type`. Canonical-stance bonuses: IV=A+B, V7=B+D, I=open, vi=A, ii=B+C, iii=D.
- `filter_mode="franklin"` → `get_same_fret_diatonic_hub(fret, neck)`: a static table with I, ii=B+C, iii=**D lever**, IV=A+B, vi=A, #I°=F and I6/9=C, where **each entry is verified** on the neck and dropped if it doesn't sound its chord.
- `get_e9_relative_movements(fret, levers, neck)` (Warnock) and `get_c6_relative_movements(fret, neck)` (Barndo) are role-based formulas, verified per neck. Each option carries `chord_root` and `chord_type`, and **UI code must use those fields instead of parsing `chord_name`**.

## star_map_engine.py

Shape tables use role tokens; the base fret is given per tuning and quality:

| Table | Base fret | Shapes (offset, tag, roles, strings) |
|---|---|---|
| E9 major | `(root−E)` | +0 open on 8-6-5; +3 A+F on 6-5-4; +5 D on 7-5-4; +7 A+B on 8-6-5 |
| E9 minor | `(root−1)` | +0 A on 6-5-4; +5 D on 6-5-4; +7 B+C on 6-5-4 |
| C6 major | `root` | open 7-6-5-3, 6-5-3, 5-3-2; +7 on 9-8-7 |
| C6 minor | `(root−A)` | 8-7-6 root, 7-6-4 1st inversion, 6-4-3 2nd inversion, 4-3-2 upper root |

- Shapes are tried at octave shifts −12, 0 and +12, kept within frets 0–24, and **verified with `grip_matches_chord`**.
- `fret_offset` always means "frets above the base shape".
- With `neck=None`, the standard E9 preset is used.

## triad_explorer.py (E-19; Franklin *Intervals* pp. 20–28)

- Supported backing types are listed in `CHORD_FAMILY` (major, dominant and minor families); any other type returns `[]`.
- **Groups:**
  - *Diatonic:* triads of the parent scale (Ionian, Mixolydian or Dorian).
  - *From the 3rd & 5th:* major, minor and diminished triads on the chord's 3rd and 5th.
  - *Altered* (dominants only): triads of the melodic minor a half-step above the root.
  - Duplicates keep their first group.
- **Sounds like:** the smallest `CHORD_FORMULAS` type, at most 2 extra tones, that contains root + implied tones (the backing chord's 7th; b3 if minor) + the triad. Ties go to the same family. Dominant backings only accept dominant types; otherwise, with a b7 and no natural 7, they get a composite name (`G7b5#9`). Anything else becomes a slash chord (`C/G`). The tests pin the book's examples (Dm over G7 → G9, Abm → G7#5b9, B over G → Gmaj7#5…).
- **Spelling:** follows the backing root's own accidental. Naturals use the parent key's signature; altered triads use flats.
- **Grips:** `find_triad_grips` runs `VoicingSolver.find_all_voicings` for the triad. It keeps 3-string grips that pass `grip_matches_chord`, takes the 40 best by score and returns them in fret order.
- **Dialog flow:** clicking a grip in the dialog emits `(fret, controllers, strings, root, type)`. MainWindow sets the harmonic target to the "sounds like" chord when it has a formula (the triad itself otherwise), so the canvas labels the tones over the backing chord, then calls `apply_stance`.

## copedant_compare.py (E-25)

- **Diff:** `diff_copedants` matches controllers by **ID** (labels are ignored). It produces one `CopedantDiffItem` per:
  - added or removed controller;
  - added, removed or changed pull (per string);
  - active split (keyed by string + controller set);
  - active half-stop (controller + string);
  - re-tuned, added or removed string.

  `apply_item(base, modified, item)` returns a copy of the baseline with only that item applied.
- **Scan:** every stance moves as a unit, so the scan runs once at **fret 0** and stores roots as pitch classes; the display transposes them. Stances are `VoicingSolver.candidate_stances` (ergonomic), plus an `<ID>_HALF` variant for each controller with an active half-stop rule. Grips are every 3- and 4-string set within a 5-string span (`all_grips`).
- **Match rule:** the grip's pitch-class set must equal a `CHORD_FORMULAS` set exactly, with the root present. When no exact spelling exists for any root, a no-5th shell of a chord with 4 or more tones is also accepted (`is_shell`), provided it has `min(#tones, #strings)` distinct tones. A set that spells two chords (C6 = Am7) is reported as both. **No idle controllers (D-48):** a way is skipped when dropping one of its controllers gives a scanned stance with the same resolved pitches on every grip string (`has_idle_controller`), so a lever that doesn't touch the grip never shows up as a separate way.
- **Compare:** `compare_copedants` diffs the sighting sets of the two necks per `(root_pc, chord_type)`. The status is `new_chord` or `lost_chord` when the chord isn't available at all on one side at the same bar position. Otherwise it is `new_ways`, `fewer_ways` or `changed_ways`. Each item is also scanned on its own (`per_item`). `interactions` holds the total's sightings that no single item explains, i.e. effects of changes working together.
- **Verification:** every gained sighting passes `grip_matches_chord` on the modified neck, and every lost one on the baseline. A failure is logged and dropped.
- **Filters:** `filter_report(report, chord_types, allowed_controllers, include_shells, max_controllers)` works on an already computed report, with no re-scan. `allowed_controllers` keeps only the sightings whose controllers (with `_HALF` folded onto the base ID) are a subset, open bar included. Each report carries the full `base_scan` and `mod_scan`, so the status is **recomputed inside the filter**: "new chord" then means the chord wasn't playable before with only those controllers.
- **Names:** `root_name` and `chord_symbol` use the global spelling (`theory.spell_pc`).
- **Inversions:** each sighting stores `bass_interval`, the semitones from the root to the grip's **lowest resolved pitch** (so pulls that cross strings count). It is excluded from equality, so the same stance + grip is still the same way. `inversion_index` counts in stacked thirds: R = 0 (root position); 3rd or the sus 4 = 1; 5th = 2; 7th or the 6 of a 6th chord = 3; 9/11/13 = 4 (extension in bass). `inversion_name` gives e.g. "2nd inversion (5 in bass)". `sighting_filter(inversions=...)` filters on it, and both dialogs offer it as the "Inversions" menu in `ChordFilterBar`.

## chord_atlas.py (E-27)

- **Scan:** `build_atlas(neck)` reuses the compare scan (`candidate_stances`, `scan_chords`, the same match rule) at fret 0. It covers every grip of **3-5 strings within a 6-string span** and stores one `AtlasEntry(root_pc, chord_type, sightings)` per chord, ways sorted easiest first. `verify=True` re-checks each way with `grip_matches_chord`, which takes about 2 s on a U12. The dialog passes `verify=False`, and `test_every_way_sounds_its_chord` checks every way on the E9, C6 and U12-3HS factory necks.
- **Filters** run on the stored atlas, with no re-scan: `filter_atlas(atlas, keep, chord_types, root_pc)`, where `keep` comes from `copedant_compare.sighting_filter(allowed_controllers, include_shells, max_controllers, grips)`. This is the same predicate that Compare's `filter_report` uses.
- **Grip configurations:** `grips_for_config(neck, source, sizes, max_span, current_pocket, custom)`. The sources are all string groups, the grip bar's pocket presets (`pocket_presets`, from `core/grip_presets.py`), the voicing finder grips (`VoicingSolver.get_candidate_grips`), the current fretboard pocket, or a custom list parsed by `parse_grip_list("8-6-5, 6-5-4")`.
- **Grip size vs. span:** "Notes per grip" (3/4/5) is the number of strings picked. "Max stretch" is the distance between the outer strings, counting skipped strings (8-6-5 = 4, 10-8-6 = 5).
- **Find mode (E-28, replaces the Voicing Finder's search):** `find_chord(atlas, root, chord_type, omitted, allow_no_fifth, max_fret)` returns one `ChordPosition(fret, sighting, ergonomics, formula, missing, score)` per fret + stance + grip, for frets 0..`max_fret`. It reuses `atlas.stance_midis` (the fret-0 pitches of every stance) and transposes them, so nothing is re-resolved: about 0.07 s on E9 and 0.4 s on U12.
  - **Match rule (the same as the atlas, so the modes can't disagree):** the grip's pitch classes must equal the chord tones minus `omitted`, so an omitted tone must **not** sound. Ways with an idle controller are skipped, as in the scan (D-48). `allow_no_fifth` (the "no-5th shells" box) also lets a 4+-tone chord drop its 5th. Unlike the old `find_all_voicings`, an incomplete grip (a plain triad) is not reported as a 7th chord; the tests check that every full-chord voicing the old finder found is still found.
  - `formula` lists the interval labels from the lowest pitch up. `sort_positions(..., "easiest" | "fret")`.
- **Radar (E-29):** `find_neighbors(atlas, origin_root, origin_fret, origin_strings, origin_controllers, allowed_moves, allow_no_fifth)` returns `NeighborMove`s for IV, V, V7, vi and ii within ±9 frets. Each target comes from `find_chord`, so it **must sound every tone** (`allow_no_fifth` lets V7 drop its 5th), and a plain triad is never offered as a V7 (the old `VoicingSolver.find_circle_neighbors` did that). Grips: the origin's strings first, then nearby grips of the same size or one string more (outer strings within 3 in total); awkward stances are skipped. The moves are: same fret (pedal change); hold pedals and slide; open-bar shift; position shift. The old hard-coded "P1+P2 slide +2" case is gone (it used IDs, not roles). The best move for each relationship is always kept, then the list fills to 12, grouped by relationship. About 0.03 s on E9 and 0.14 s on U12 (the old radar took 0.2 s and 1.1 s).
- **Controller filter modes:** `sighting_filter(..., controller_match=)` takes `"exact"` (exactly the selected controllers), `"include"` (the selection plus any others) or `"only"` (subsets of the selection, open bar included; the default in core, used by Compare's status logic). `ChordFilterBar` offers all three and defaults to **Exactly these**.
- **Views:** `by_stance(entries)` maps stance → (chord, way). `coverage(entries, tonic_pc)` maps chord type → {degree above the tonic: number of ways}.

## pearls_engine.py, flashcard_engine.py, permutation_engine.py, tab_generator.py

- **Pearls:** scans frets 0–22 under the open, A, B, A+B, F and D stances (resolved per neck), using resolver pitches for the chosen string pair. Both notes must be in the scale.
- **Flashcards:** a prompt is the major star map of a random root **for the given neck**, clicked in strict left-to-right order within the time limit.
- **Permutations:** the 24 entries are Franklin's chart (*Intervals* p. 38), D-36. Each is `(fingering, book notes, fingers, order)`. `order` holds the positions within the 4-string group (0 = lowest pitch), so every permutation plays each string once; on open E9 strings 8-7-6-5 they sound exactly the book's note sequences (tested through the resolver). Fingerings repeat between entries (#2 and #21 are both T-I-M-T); the order is what is unique. `generate_sequence` sorts strings **bass first** and uses the 4 lowest. Grips with 3 strings double the bass, and grips with 2 strings double both.
- **Tab:** every column is exactly `col_width` (12) characters wide, in the header, pick, string and pedal rows alike.

## progression_presets.py

The presets store **role tokens** in `TabStep.engaged_levers` plus a `chords` list of `(root, chord_type)` per step. `resolve_preset_steps(preset, neck)` maps them onto a neck, or returns `None` if a controller is missing. `tests/test_engines.py` verifies **every step on every matching factory neck**. E9 presets use the 8-6-5 triad and 6-5-4 pedal-minor pockets. C6 presets use the 7-6-5-4 block, with dominant 7ths from Pedal 8 (the A7 shape moved up the neck).
