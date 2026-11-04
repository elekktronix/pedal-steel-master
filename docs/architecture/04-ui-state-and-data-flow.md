# 04 — UI State & Data Flow (`ui/*`)

## Pattern

`MainWindow` is a **mediator**. Child widgets emit Qt signals and `MainWindow` handlers apply the change everywhere. Some dialogs bypass this by calling `parent_window._private_method()` directly; see "Coupling violations" below.

## Who owns what

| State | Canonical owner | Mirrors (must be kept in sync) |
|---|---|---|
| Guitar and neck list | `MainWindow.guitar` | `combo_copedant`, "Select Copedant" menu, the copedant editor's own combo |
| Active neck index | `MainWindow.current_neck_idx` (not persisted, resets to 0) | combo and menu check state |
| Bar fret | `FretboardCanvas.bar_fret` | `fret_slider`, `fret_spin` |
| Engaged controllers (incl. `_HALF`) | `FretboardCanvas.engaged_levers` | `LeverTogglePanel.active_controllers`, each `HalfStopLeverButton.state` (0/1/2), feasibility badge |
| Pocket (picked strings) | `FretboardCanvas.active_pocket` | `GripPocketBar` highlights, `ScaleFinderWidget.active_pocket`, `CircleOfFifthsWidget.active_pocket` |
| Harmonic target | `HarmonicTargetPanel` combos → `canvas.target_root/target_chord` | up-the-neck dropdown, voicing finder combos |
| Scale target | `ScaleFinderWidget` → `canvas.target_root/target_scale` | — |
| Resolved strings | `FretboardCanvas.active_states` (recomputed in `update_state()`) | read directly by MainWindow, the permutation trainer, etc. |
| Detected chord label | `FretboardCanvas.detected_chord_label` (overwritten by `set_explicit_banner`) | — |
| Preferences | `MainWindow.settings` dict → `app_settings.json` | menu check states, NNS button |
| Sequencer steps | `ProgressionSequencerWidget.steps: List[TabStep]` | its table |

`FretboardCanvas.update_state()` is the **recompute hub**. Every setter (`set_neck`, `set_bar_fret`, `set_engaged_levers`, `set_active_pocket`, `set_chord_analysis`, `set_scale_analysis`, `set_show_*`) calls it. It re-runs the resolver and `ChordIdentifier` and then repaints.

## Main flows

### 1. User toggles a lever
```
HalfStopLeverButton click (240 ms single/double click timer)
  single: 0→1 if has_half_stop else 0→2;  any→0      double: toggles 0↔2
  → state_changed(id, state) → LeverTogglePanel._on_controller_state_changed
      active_controllers: remove id & id_HALF; add id_HALF (1) or id (2)
      update badge (ErgonomicsEngine)
  → levers_changed(set) → MainWindow._on_levers_changed
      canvas.set_engaged_levers → update_state
      relative_moves_widget.update_state (full rescan)
      stance inspector refresh (if open & live sync)
      circle widget update_current_stance (if visible: runs find_all_voicings for 7 chords)
```
`has_half_stop` is true only if the neck has an **active `HalfStopRule` for that controller**.

### 2. Bar fret changes (slider, spinbox, canvas click or drag)
`_on_bar_fret_changed` syncs the slider and spinbox with signals blocked, then calls `canvas.set_bar_fret`. That emits `fret_changed`, which re-enters `_on_bar_fret_changed` and stops there because the value is unchanged. It then refreshes the hub, the inspector and the circle.

### 3. Programmatic "apply stance" — `MainWindow.apply_stance(fret, controllers, pocket=None, *, play=True, banner=None)`
Used by the star-map ribbon and dialog, scale steps, circle chords, voicing finder, sequencer steps, relative moves, pearls, flashcards and the voice leader (via its `voicing_applied` signal).
```
_batch_depth += 1
  canvas.set_bar_fret(f); _sync_fret_widgets(f)        (dependent refreshes deferred)
  active = lever_panel.set_active_controllers(ctrls)    (buttons 0/1/2, own state, badge; no signal)
  canvas.set_engaged_levers(active)
  grip_bar.apply_pocket(pocket) → canvas.set_active_pocket → grip_bar.sync_highlights
  canvas.set_explicit_banner(banner)
_batch_depth -= 1
_refresh_stance_dependents()  → relative-moves hub, stance inspector, circle (if visible) — once
_play_pocket()                → audio.play_pocket({string: midi}, cents=Newman cents if enabled)
```
Controllers may include `"<ID>_HALF"` (button state 1). IDs the neck doesn't have are dropped.

### 4. Neck switch (combo, menu, import, editor apply)
`_load_current_neck` pushes the neck to the canvas, lever panel (rebuilds buttons and clears engagement), grip bar (resets to the default pocket), voicing finder, scale finder, circle, sequencer and voice leader. It then re-fires the harmonic target and refreshes the ribbon and hub.
- A **profile** chosen in the combo (or the Profiles dialog) runs `_load_named_profile`, which appends it as a linked neck (or refreshes the existing linked entry) and selects it.
- **Editor:** `_open_copedant_editor` checks `exec()`. On Accept it follows `dialog.current_neck_idx` and calls `_on_copedant_modified` (save `active_guitar_setup.json`, refresh combo, reload). On Cancel with `dialog.guitar_changed` it saves and refreshes the combo.

### 5. Harmonic target
`HarmonicTargetPanel._on_change` emits `target_changed(root, type)`, or `(None, None)` when the root is "None". The handler calls `canvas.set_chord_analysis`, syncs the up-the-neck dropdown **by pitch class**, and rebuilds the star-map ribbon and hub. `set_target` accepts any enharmonic spelling (`to_root_name`).

### 6. Copedant editor (modal)
The editor keeps `_working: {neck_idx: deepcopy}`, so switching necks in its combo keeps unapplied edits (`_sync_ui_to_neck`). Opening a neck runs `migrate_legacy_ids` and `migrate_half_stop_tokens`. Matrix edits mutate the working copy immediately. Split and half-stop rows live as table widgets until flushed. Dropdowns keep unknown values as "⚠ X (undefined)" and never fall back to the first item. The Franklin toggle and insert go through `shift_pedal_ids`. Apply commits all working copies, writes profile files only for linked necks, persists the active setup and accepts. **Duplicate** and **Save as Profile** (into a new name) append a linked neck immediately and set `guitar_changed`.

### 7. Session restore (E-12)
At the end of `MainWindow.__init__`, `_restore_session(load_session())` runs. It restores the neck (matched by name first, then index), the harmonic target, the display mode, the stance (through `apply_stance(play=False)`), window geometry and dock state, and sequencer visibility. `closeEvent` saves `_capture_session()` first. Invalid entries are skipped. The sequencer dock needs `objectName` for `restoreState`.

### 8. Pedal/bar swells (E-11)
`_play_pocket` remembers `{string: struck midi}` for `SWELL_WINDOW_SEC` (4 s). On a **manual** lever toggle (`_on_levers_changed`) or bar move (`_on_bar_fret_changed` outside a batch), `_swell_sounding_strings()` bends each ringing string to its new pitch with `audio.glide_string_pitch`. Targets beyond ±2 semitones re-strike the string softly (velocity 60). This is controlled by the "Pedal & Bar Swells" preference (`settings["pedal_swells"]`). `apply_stance` never glides; it re-plucks.

### 9. Theme (E-13)
`_apply_theme` sets the app QSS (`DARK_THEME_QSS`/`LIGHT_THEME_QSS`), then `ThemeManager.for_app(app).set_dark(...)`, the canvas and the circle widget. **There is exactly one `ThemeManager` per application (`for_app`); two would fight over the same widgets forever.** In light mode, every inline stylesheet is rewritten as it's set: `StyleChange` and `Polish` events are queued and processed iteratively, never re-entrantly. The dark original is kept in a widget property and restored on switching back. Inline styles can therefore stay written in dark-mode colors.

## Signal catalogue (live)

| Emitter.signal | Args | Handler |
|---|---|---|
| `FretboardCanvas.fret_changed` | int | `MainWindow._on_bar_fret_changed` |
| `FretboardCanvas.pocket_changed` | set | `MainWindow._on_canvas_pocket_changed` → grip bar highlights only |
| `FretboardCanvas.node_clicked` | int midi, int string | `_on_node_clicked` → `audio.play_note` on that string's channel |
| `LeverTogglePanel.levers_changed` | set | `_on_levers_changed` |
| `LeverTogglePanel.pinch/roll/arpeggiate/all_strings/clear_pocket_requested` | — | play or pocket helpers (`All` = every string of the neck) |
| `GripPocketBar.pocket_changed` | set | `_on_grip_bar_pocket_changed` → canvas, scale finder, circle |
| `HarmonicTargetPanel.target_changed / reset_requested / find_voicings_requested` | object,object (`None,None` = no target) / — / — | `_on_harmonic_target_changed` / `lever_panel.reset_all` / toggle voicing finder |
| `RelativeMovesWidget.move_applied` | int,set,set,str,str | `_apply_relative_move` |
| `VoicingFinderWidget.voicing_applied / target_changed` | int,list,list / str,str | `_apply_solved_voicing` / `harmonic_panel.set_target` |
| `ScaleFinderWidget.scale_step_applied, box_highlight_requested, clear_highlight_requested, box_shading_toggled, play_note(s)_requested, target_changed` | various | `_apply_scale_step`, canvas box, settings, audio, `canvas.set_scale_analysis` |
| `CircleOfFifthsWidget.chord_triggered` | str,str,bool,set | `_on_circle_chord_triggered` (the 4th arg, allowed mechanics, is dropped) |
| `ProgressionSequencerWidget.step_activated` | int,list,set | `_apply_sequencer_step` |
| `VoiceLeaderDialog.voicing_path_applied` / `voicing_applied` | list[(idx, VoicingMatch)] / int,list,list | `_apply_voice_leader_path` / `_apply_solved_voicing` |
| `StanceChordInspectorDialog.grip_applied` | set | `_apply_pocket_preset` |
| `StarMapWidget.landmark_selected`, `StringsOfPearlsDialog.step_selected`, `FlashcardDrillDialog.landmark_verified` | int,set,set | `_on_star_map_dialog_selected` |
| `CopedantEditorDialog.neck_updated` | — | `_on_copedant_modified` |
| `ProfileManagerDialog.profile_selected` | str | `_load_named_profile` |

## Windows and dialog lifetimes

- **Created once at startup and toggled with show/hide** (`Qt.Window` children): voicing finder, scale finder, circle of fifths. The sequencer is a `QDockWidget`.
- **Lazily created and cached:** voice leader, stance inspector.
- **Modal, created per open:** copedant editor, profile manager, star map, pearls, flashcards, permutation trainer. Star map, pearls and flashcards receive the active neck.
- The sequencer gets `set_neck(neck)` on every neck switch; presets are mapped onto that neck with `resolve_preset_steps` and refused for the other tuning.

## Coupling violations (cleanup targets)

- Calls into `parent_window._play_pocket` / `_apply_pocket_preset` / `.audio` / `.canvas.active_states`: pearls, stance inspector, permutation trainer, voice leader.
- `MainWindow._toggle_c6_menu_pedal_offset` builds an invisible editor dialog and calls its private methods.
- `lever_panel` imports `STANDARDIZED_KNEE_LEVERS` from `copedant_editor_dialog`. This domain constant belongs in `core`.
- Inline stylesheets hard-code dark colors in about 20 places, so light theme only partly applies.
