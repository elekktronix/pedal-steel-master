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
- **E-16** Performance: cache `resolve_neck_state` by key, give `Neck` a `version` counter that bumps on edit, and run heavy searches (voice leader, Chord Atlas radar) in a `QThreadPool` with a progress indicator.
- **E-17** PDF: add tables for splits, half-stops and voicing matches (the parameter already exists).

## Phase 6 — Ideas from Franklin's *Intervals* book

These were reviewed against the app on 2026-11-04. The book's open-position pedal/lever chord list (p. 12) and string groups 1–4 already match the app (`test_franklin_pedal_chords`).

- ✅ **E-18 (done)** Extended chord types in `theory.CHORD_FORMULAS`: maj9, 11, 13, 13sus4, 7b9, 7#9, 7b5, 7#5, maj7#5. The book's triad-substitution pages (pp. 24–28) produce these sounds, and the app cannot name them yet. Prerequisite for E-19.
- ✅ **E-19 (done: `core/triad_explorer.py`, "🔺 Triads Over Chord")** "Triads over a chord" explorer (pp. 20–28). Choose a backing chord (e.g. G7). List the triads built on its 3rd, 5th, b7 and 9, and the altered triads from the melodic minor a half-step up, with what each sounds like (G9, G11, G13sus, G7#5b9…), then click one to show its grips on the neck. Built on `voicing_solver` plus `grip_matches_chord`.
- **E-20** Triad pairs (p. 24): two triads with no common tones used as a 6-note scale. This can be added as a mode of the scale finder.
- **E-21** Cadence drills (pp. 33–36):
  - progression presets for the minor 2-5-1 (Dm7b5–G7–Cm7) and 3-6-2-5-1;
  - a secondary dominant before every diatonic chord;
  - Franklin's "roll the dice" randomizer: two random degrees, then a 2-5-1 into each.
- **E-22** Unison finder drill (p. 13): highlight a note on string 10; the player clicks every unison and octave on the other strings. This fits the flashcard dialog.
- **E-23** Interval-function tooltips on the lever panel (pp. 8–11), e.g. "A: 5ths → 6ths, forms 6m". Derived from roles, so they stay correct on any copedant.
- **E-24** Permutations on any 4-note shape (p. 39 etude): allow the trainer to take 4 notes across frets and stances, not just the current pocket, and mark approach notes.

## Phase 7 — Copedant design

- ✅ **E-25 (done: `core/copedant_compare.py`, `ui/copedant_compare_dialog.py`)** Compare Copedants. It shows which chords a copedant change adds or removes (e.g. "NEW chord: G (b3) — with LKR, strings 10-9-6"), in total, per change, and as combined effects. There are two entry points: Copedant ▸ Compare Copedants… (any two necks; double-click puts a way on the fretboard when it belongs to the active neck) and the editor's "🔍 Compare to Saved" button. Follow-ups (also done):
  - the window is modeless and follows the active neck; double-clicking a way on the other neck switches to it and plays it;
  - filters for chord types, no-5th shells, max controllers and "only using" pedals/levers, with statuses recomputed inside the filter;
  - a global sharps/flats preference (Preferences ▸ Note Spelling) shared by the fretboard, the chord badge and the compare window.
- ✅ **E-26 (done)** Changer configuration per copedant (default 3 up – 3 down; presets 4/2, 3/2, 2/2, 4/3, 4/4 or custom). The editor shows per-string usage, outlines over-limit pulls and refuses Apply while any string needs more raises or lowers than the changer holds (`core.models.changer_violations`).
- ✅ **E-27 (done: `core/chord_atlas.py`, `ui/chord_atlas_dialog.py`)** Chord Atlas: every chord the selected copedant can play at one bar position, with every way to play it (stance + grip). It uses the Compare Copedants format and filters, adds grip configurations (pocket presets, voicing-finder grips, current pocket, custom groups, sizes, span), and shows By chord / By stance / Coverage (chord type × degree) views. It is modeless and follows the active neck and pocket; double-click auditions.
- ✅ **E-28 (done)** Merged the Voicing Finder & Position Solver into the Chord Atlas: Find mode (every position of one chord on frets 0..N, with ergonomics, inversion, intervals and tones to leave out), the Circle-of-Fifths radar for any selected way, and every Finder entry point (toolbar, harmonic panel, View menu) opening Find mode. `ui/voicing_dialog.py` was removed. Browsing now uses one engine, so Explore and Find can't disagree; `VoicingSolver` still serves the voice leader, triad explorer, circle of fifths and the radar (unifying those is a possible follow-up).
- ✅ **E-29 (done)** The Chord Atlas radar runs on the atlas match rule (`chord_atlas.find_neighbors`): every suggested IV/V/V7/vi/ii sounds its whole chord, and it is about 7x faster. The pedal/lever filter gained match modes (exactly / including / only these and open); Exactly these is the default.

## Phase 8 — Scale finder usability

- ✅ **E-30 Phase 1 (done)** Scale map on the fretboard. The finder takes a user fret range (From/To; `ScaleSolver.find_scale_in_range`) instead of a fixed 3/4-fret span; the old automatic boxes became "Suggested positions" chips (4-fret) that fill the range. Every scale tone in the range is drawn at its own fret (`FretboardCanvas.scale_overlay`, which replaces the bar nodes while shown), coloured by degree and labelled by step number, degree or note (radio buttons, saved as `scale_overlay_label`). Orange dot = needs a pedal or lever; dashed = the same pitch on another string. The current step is enlarged and earlier steps are dimmed; clicking a circle jumps to its step; hovering shows string, fret and controllers. Fixed along the way: the scale was never sent to the canvas until a dropdown changed; stepping narrowed the pocket to one string; the finder drew on the canvas while hidden; suggestion buttons drifted right after each rebuild (stretches piled up).
- ✅ **E-30 Phase 2 (done)** Playable step order (`ScaleSolver.playable_run`: dynamic programming over each pitch's spots, costing bar travel, controller changes, string skips and backtracking); order options Up / Down / Up & back and Root to root (`build_run`); role names instead of controller IDs (`stances.controller_display_names`) in the step list, banner and fretboard tooltips; the text grid tab is gone, leaving one step list with a "Change from previous step" column (bar move, string, press/release); tempo (BPM) for auto-walk; ergonomically impossible combos are skipped.
- ✅ **E-30 Phase 3 (done)** Learning aids. **Degree legend**: colour chips per scale degree with the note name, using `fretboard_canvas.degree_color` (shared with the canvas). **Whole neck (faint)**: the scale over frets 0–24 drawn small and faint outside the range (`find_scale_in_range(…, 0, 24)` filtered to frets outside it); hover shows details, click plays. **Loop steps** a..b: Prev/Next wrap inside the loop, Auto-Walk repeats it until stopped, Play Run plays it, the quiz draws from it; steps outside are faded on the canvas and greyed in the list. **Quiz**: *Find the degree* (click any circle with the named degree, any octave) or *Find by ear* (the note is played; only that exact pitch counts). Circles go blank grey, the step list and status line are hidden, a wrong click is marked ✗ and named, a right click reveals every spot of the answer, then the next question follows after 1.1 s; score, percentage and streak are shown; Replay and Skip. Hiding the finder ends the quiz.
- **E-30 fixes after real-app testing.** Play Run is now a stoppable widget timer at the Tempo (⏹ Stop Run), lighting each circle; "Circles show" is a segmented button group (the dark theme drew no indicator on a checked radio button, so the choice looked ignored); chips and buttons removed on a rebuild are hidden before `deleteLater` (a removed chip was drawn at its default 640×480 geometry over the window until the next event-loop pass).
- ✅ **E-31 (done: `core/scale_chords.py`)** Scale ↔ chord link. The Scale Finder lists the scale's triads and sevenths as numeral + symbol chips (`I G`, `ii Am`, `V7 D7`, `viiø7 F#m7b5`); clicking one rings its tones in gold on the scale map (other scale notes dimmed, whole-neck ghosts too) and enables "Find voicings in these frets", which opens the Chord Atlas Find mode for that chord limited to the scale's fret range (Find mode gained a From fret). The Chord Atlas gained "Scales that fit ▾" (own-root scales, then scales where the chord sits on another degree); picking one opens the Scale Finder on that scale with the chord ringed and, when a voicing is selected, the range fret-1..fret+2 around it.
- ✅ **E-32 (done: `core/progression_studio.py`, `ui/progression_studio_widget.py`)** Progression Studio: the Voice Leader window and the Progression Sequencer dock merged into one bottom dock (both old files removed; `MetronomeChirp` moved to `ui/metronome_chirp.py`). Steps hold a chord **and** a stance, a duration in beats (several chords per bar) and a play style (block, roll, Franklin-permutation arpeggio). Input: typed chords (`| Am7 D7 | Gmaj7 |`, `:n`, `%`, `-`), Load ▸ E9/C6 practice presets (pinned stances), cadences in the key, 🎲 dice, `.cp` files; capture the fretboard as a new pinned step or into the selected step (chord recognised from the grip); circle-of-fifths auto-add. Voicing: chords are voiced automatically around pinned/voiced steps; 🧭 Re-voice applies a shape (smooth, up, down, up-down, down-up, random), fret range, max jump and start fret to every unpinned chord. Transport: BPM, time signature, count-in, MIDI click (beat 1 accented), loop with a step range, ⏮/⏭, starts on beat 1 immediately, PreciseTimer beat grid. Tab with role names and arpeggio pick fingers. The progression is saved in the session. Fixes D-43 to D-47.

## Working agreement for future AI sessions

1. Paste `00-critical-rules.md` plus the doc for the area you're touching.
2. Name the defect or enhancement ID you're working on.
3. Ask for a **diff limited to the named files**. Forbid rewriting whole files you didn't name.
4. After each change, run `pytest` (once E-01 exists) and update `06`/`07` and any affected section of `01`–`05`.
