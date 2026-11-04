# Pedal Steel Master — System Architecture & Business Logic

Baseline snapshot of commit `04557c1` (2026-11-03). This is the source of truth for design decisions.
If code and this document disagree, either fix the code or update this document on purpose. Never let them drift silently.

## How to use these docs in an AI chat

The docs are split so you only paste what the task touches. **Always paste `00-critical-rules.md`.** Add the others as needed:

| If the task touches… | Paste |
|---|---|
| Anything at all | `00-critical-rules.md` (≈2 pages) |
| `core/models.py`, presets, JSON files, IDs | `01-domain-model.md` |
| Pitch math, pedals/levers, splits, half-stops | `02-pitch-resolution.md` |
| Voicing/scale/star-map/relative-moves/voice-leader engines | `03-theory-engines.md` |
| `ui/main_window.py`, signals, panels, dialogs | `04-ui-state-and-data-flow.md` |
| Files on disk, settings, profiles, PDF, MIDI audio | `05-persistence-and-audio.md` |
| Fixing bugs | `06-defect-register.md` (and the doc for the area) |
| Planning work | `07-enhancements.md` |

## One-paragraph system summary

A PySide6 desktop app (Windows-first) for visualizing a pedal steel guitar. A **Neck** (tuning + pedals + knee levers + split/half-stop rules) is the core model. The **FretboardResolver** turns (neck, bar fret, engaged controllers) into the sounding pitch for each string. Everything else consumes those resolved pitches. Theory engines search for chord voicings, scale boxes, landmarks and voice-leading paths. The fretboard canvas draws the result, and an ad-hoc MIDI engine plays it. `MainWindow` is a mediator that owns the current neck and wires roughly 15 panels and dialogs together through Qt signals. State is saved to JSON under `~/.psg_visualizer/profiles/` and to `app_settings.json`.

## Layer map

```
main.py ──► ui/main_window.py (MainWindow: mediator + "current stance" owner)
              │
              ├── ui/* panels & dialogs ──(Qt signals)──► MainWindow handlers
              │
              ▼
           core/*  (pure Python, no Qt)
              │
   models.py ─┼─► resolver.py ─┬─► stances.py (functional roles + shape verification)
   theory.py ─┘                │      └─► star_map_engine, relative_moves, scale_engine,
                               │          pearls_engine, progression_presets, audio (Newman cents)
                               ├─► voicing_solver.py ─► voice_leader.py
                               ├─► relative_moves.py (+ chord_identifier.py)
                               ├─► exporter.py (PDF)
                               └─► ui/fretboard_canvas.py
   Pure helpers: permutation_engine.py, tab_generator.py, flashcard_engine.py (via star map)
   Side effects: audio.py (winmm MIDI), settings.py, profile_manager.py; logging → ~/.psg_visualizer/app.log
```

## Module inventory (live vs. dead)

| Status | Modules |
|---|---|
| Live core | models, theory, resolver, stances, presets, ergonomics, chord_identifier, voicing_solver, voice_leader, scale_engine, relative_moves, star_map_engine, pearls_engine, flashcard_engine, permutation_engine, triad_explorer, copedant_compare, chord_atlas, tab_generator, progression_presets, progression_studio, grip_presets, circle_of_fifths, exporter, audio, settings, profile_manager |
| Live UI | main_window, main_menu_builder, fretboard_canvas, lever_panel, grip_pocket_bar, harmonic_target_panel, relative_moves_widget, progression_studio_widget, metronome_chirp, scale_finder_widget, circle_of_fifths_widget, stance_chord_inspector_dialog, copedant_editor_dialog, manage_profiles_dialog, star_map_widget, pearls_widget, flashcard_dialog, permutation_trainer_dialog, triad_explorer_dialog, copedant_compare_dialog, chord_atlas_dialog, chord_filter_bar, profile_prompts, themes |
| Tests | `tests/test_core_integrity.py` (data integrity, editor, profiles), `tests/test_engines.py` (engines, content correctness, MainWindow integration) |

The legacy standalone split/half-stop dialogs and `presets_old.py` were deleted (D-29). `ui/voicing_dialog.py` (Voicing Finder window) was removed in E-28; its search and radar live in the Chord Atlas. `ui/voice_leader_dialog.py` and `ui/progression_panel.py` were removed in E-32; both live on in the Progression Studio. Split and half-stop editing lives in **`ui/copedant_editor_dialog.py` tabs 3 and 4**.

## Terminology

- **Copedant**: the code's spelling of *copedent* (the tuning/changer chart). Keep the code's spelling in identifiers.
- **Controller**: any pedal (`P1`…`Pn`) or knee lever (`LKL`, `LKV`, `LKR`, `RKL`, `RKR`, …).
- **Stance**: bar fret plus a set of engaged controllers.
- **Pocket / grip**: the set of string numbers being picked.
- **Split**: an override of the net pitch change when two or more controllers pull the same string.
- **Half-stop**: an intermediate detent on a single controller (encoded as `"<ID>_HALF"`).
- **Landmark**: a named fret/controller/grip position (Newman "star map").
