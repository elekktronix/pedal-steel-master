# 03 — Theory & Practice Engines (`core/*`)

Each engine is a class of `@classmethod`s with no instance state. **Copedant-aware** means it resolves pitches through `FretboardResolver` for the actual `Neck`, and names controllers by functional role (`core/stances.py`) rather than hard-coded IDs.

| Engine | Entry point(s) | Output | Copedant-aware? | Consumers |
|---|---|---|---|---|
| `stances` | `detect_roles`, `resolve_stance`, `grip_matches_chord`, `is_c6_neck` | role map / ID set / bool | ✅ (it *is* the adapter) | star map, relative moves, scale, pearls, presets, audio |
| `theory` | formulas, `note_to_midi`, `get_nashville_chord_symbol`, `to_root_name` | dicts / str | n/a | everything |
| `chord_identifier.ChordIdentifier` | `identify_voicing(pitches, bass, show_inversion, grip)` | `(display_tag, family)` | n/a (pitch-only) | canvas, relative_moves, stance inspector |
| `voicing_solver.VoicingSolver` | `find_all_voicings`, `find_circle_neighbors`, `get_triad_substitution`, `classify_movement` | `List[VoicingMatch]`, `List[NeighborVoicing]` | ✅ | voicing dialog, circle widget, voice leader, main |
| `voice_leader.VoiceLeadingEngine` | `solve_progression(neck, prog, constraints)` | one `Optional[VoicingMatch]` per measure | ✅ | voice leader dialog |
| `scale_engine.ScaleSolver` | `find_scale_boxes(neck, root, scale, span, max_fret)` | `List[ScaleBox]` (≤5) | ✅ (role combos) | scale finder |
| `relative_moves.RelativeMovesEngine` | `get_all_same_fret_chords`, `get_same_fret_diatonic_hub`, `get_e9_relative_movements`, `get_c6_relative_movements` | `List[RelativeMoveOption]` | ✅ (role stances, verified) | relative moves widget |
| `star_map_engine.StarMapEngine` | `calculate_landmarks(root, type, neck)` | `List[StarMapLandmark]` | ✅ (role stances, verified) | main ribbon, star-map dialog, flashcards |
| `pearls_engine.PearlsEngine` | `generate_scale_run(key, track, scale, max_fret, neck)` | `List[PearlStep]` | ✅ | pearls dialog |
| `flashcard_engine.FlashcardEngine` | `generate_prompt(time_limit, root, neck)`, `evaluate_attempt` | `FlashcardPrompt`, `DrillResult` | ✅ (via star map) | flashcard dialog |
| `permutation_engine.PermutationEngine` | `generate_sequence(perm_id, strings, cycles)` | `List[PickEvent]` | n/a | permutation trainer, sequencer arpeggiate |
| `tab_generator.TabGenerator` | `generate_ascii_tab(string_count, steps)` | str | n/a | sequencer |
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

- `NOTE_TO_SEMITONE` accepts sharps, flats and B#/E#/Cb/Fb. `to_root_name(name, spellings)` respells any enharmonic root into a given spelling list. UI combos use it, so flats are accepted everywhere.
- `CHORD_FORMULAS` has 14 chords (now including `Half-Diminished` and `6/9`). The labels are not identical to `INTERVAL_MAP`: Sus4 uses `"4"` and Dim7 uses `"bb7"`.
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
- `find_circle_neighbors` locates the key **by pitch class** (so C#, D#, G#, A# and Gb work), then searches IV, V, V7, vi and ii.
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

## scale_engine.py

For each anchor window it resolves every (fret, combo) **once** (cached) and keeps the scale tones per string, preferring the variant with the fewest controllers. Boxes are scored and up to 5 are picked greedily, at least 2 frets apart. The combos are role tokens: E9 uses open, A, B, A+B, F, D, A+F and B+RKL; C6 uses open, the five C6 pedals, P4+P5, P5+P6, RKL and RKR. They are resolved per neck.

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

## pearls_engine.py, flashcard_engine.py, permutation_engine.py, tab_generator.py

- **Pearls:** scans frets 0–22 under the open, A, B, A+B, F and D stances (resolved per neck), using resolver pitches for the chosen string pair. Both notes must be in the scale.
- **Flashcards:** a prompt is the major star map of a random root **for the given neck**, clicked in strict left-to-right order within the time limit.
- **Permutations:** 24 unique T/I/M patterns. Entries 18, 20, 21 and 23 were duplicates and were replaced with unused three-finger patterns. **The table and names are not verified against Franklin's book** (see D-36). `generate_sequence` sorts strings **bass first**, so the thumb plays the lowest-pitched string. Grips with fewer than 4 strings keep the thumb on the bass.
- **Tab:** every column is exactly `col_width` (12) characters wide, in the header, pick, string and pedal rows alike.

## progression_presets.py

The presets store **role tokens** in `TabStep.engaged_levers` plus a `chords` list of `(root, chord_type)` per step. `resolve_preset_steps(preset, neck)` maps them onto a neck, or returns `None` if a controller is missing. `tests/test_engines.py` verifies **every step on every matching factory neck**. E9 presets use the 8-6-5 triad and 6-5-4 pedal-minor pockets. C6 presets use the 7-6-5-4 block, with dominant 7ths from Pedal 8 (the A7 shape moved up the neck).
