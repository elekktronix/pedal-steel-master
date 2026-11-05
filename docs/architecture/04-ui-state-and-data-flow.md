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
| Harmonic target | `HarmonicTargetPanel` combos → `canvas.target_root/target_chord` | up-the-neck dropdown, Chord Atlas Find-mode combos (via `target_changed`) |
| Scale target | `ScaleFinderWidget` → `canvas.target_root/target_scale` (sent only while the finder is shown) | — |
| Scale map overlay (E-30) | `FretboardCanvas.scale_overlay`, `overlay_label_mode` (`step`/`degree`/`note`, setting `scale_overlay_label`), `overlay_active_step`, `overlay_run`, `overlay_loop_ids`, `scale_ghost`, `overlay_quiz`/`overlay_revealed`/`overlay_wrong` | `ScaleFinderWidget` (fret range, run, loop, quiz) |
| Resolved strings | `FretboardCanvas.active_states` (recomputed in `update_state()`) | read directly by MainWindow, the permutation trainer, etc. |
| Detected chord label | `FretboardCanvas.detected_chord_label` (overwritten by `set_explicit_banner`) | — |
| Preferences | `MainWindow.settings` dict → `app_settings.json` | menu check states, NNS button |
| Progression (E-32) | `ProgressionStudioWidget.progression: StudioProgression` (chords, beats, stances, styles) | its step cards, chord text and step editor |

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
Used by the star-map ribbon and dialog, scale steps, circle chords, voicing finder, Progression Studio steps (`stance_requested` → `apply_stance(..., play=False, banner=)`, then `_play_studio_step`), relative moves, pearls and flashcards.
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
`_load_current_neck` pushes the neck to the canvas, lever panel (rebuilds buttons and clears engagement), grip bar (resets to the default pocket), scale finder, circle, sequencer and voice leader. It then re-fires the harmonic target and refreshes the ribbon and hub.
- The **Profile** selector, the Profiles dialog (`open_requested(profile, tuning_index)`) and the Tuning Browser call `switch_profile(key, tuning_index)`, which saves the open profile, asks before dropping Factory edits, replaces `self.guitar` and reloads the neck. The **Tuning** selector lists only the open profile's tunings.
- **Main-window layout** (top to bottom): Profile / Tuning / 🔎 / ⚙️ Copedant / 📁 Profiles bar, tool ribbon, fretboard canvas, **bar position slider + mechanical feasibility badge** (`LeverTogglePanel.feasibility_bar`, re-parented into the bar row), **pedals / knee levers / pluck** (`LeverTogglePanel`), Up-The-Neck navigator, Same Fret Hub and Relative Move Assistant, then **String Grips** (`GripPocketBar`: compact chips grouped as 4-note / Triads / Dyads, names in tooltips and a "Selected:" caption) beside the Harmonic Target panel.
- **Editor:** `_open_copedant_editor` checks `exec()`. On Accept it follows `dialog.current_neck_idx` and calls `_on_copedant_modified` (save `active_guitar_setup.json`, refresh combo, reload). On Cancel with `dialog.guitar_changed` it saves and refreshes the combo.

### 5. Harmonic target
`HarmonicTargetPanel._on_change` emits `target_changed(root, type)`, or `(None, None)` when the root is "None". The handler calls `canvas.set_chord_analysis`, syncs the up-the-neck dropdown **by pitch class**, and rebuilds the star-map ribbon and hub. `set_target` accepts any enharmonic spelling (`to_root_name`).

### 6. Copedant editor (modal)
The editor keeps `_working: {neck_idx: deepcopy}`, so switching necks in its combo keeps unapplied edits (`_sync_ui_to_neck`). Opening a neck runs `migrate_legacy_ids` and `migrate_half_stop_tokens`. Matrix edits mutate the working copy immediately. Split and half-stop rows live as table widgets until flushed. Dropdowns keep unknown values as "⚠ X (undefined)" and never fall back to the first item. The Franklin toggle and insert go through `shift_pedal_ids`. Apply first checks the **changer configuration** of every working copy (E-26). If any string needs more raises or lowers than its neck's changer holds, Apply is refused: the editor switches to that neck's matrix and lists the strings. The Matrix tab's "Changer Configuration" box (preset combo + raises/lowers spin boxes) edits `changer_raises`/`changer_lowers`. A status line and a "Changer ↑/↓" column show the usage per string, and over-limit pulls are outlined in red. Edits that exceed the limit are allowed while you work; only Apply is blocked. Otherwise Apply commits all working copies, persists the active setup and accepts; MainWindow then saves the open user profile. The editor's Tuning combo lists only the open profile's tunings (item data `("neck", idx)`). **Duplicate Tuning** appends a copy to the open profile immediately and sets `guitar_changed`. **Copy to Profile…** appends a copy of the working neck to another user profile file (or a new one). **🔍 Compare to Saved** (E-25) flushes the UI, then opens `CopedantCompareDialog(saved_neck_for_compare(), copy of the working neck)`. `saved_neck_for_compare` runs the same migrations on the saved neck, so a `VL`→`LKV` rename isn't reported. In this mode the dialog cannot put stances on the canvas.

### 6a. Note spelling (Preferences ▸ ♯/♭ Note Spelling)
`_set_note_spelling(pref)` calls `theory.set_accidental_preference` and saves `note_spelling`. It respells, in place and with signals blocked, every live `QComboBox` item that is a bare note name (except combos with the `keepSpelling` property, i.e. the circle of fifths' key dropdown), and repopulates the up-the-neck dropdown. It then refreshes the canvas (`update_state`) and the dependent views (`harmonic_panel._on_change`), and calls `on_note_spelling_changed()` on any top-level window that has it (the compare window does). Widgets built later read `note_names()` directly. `set_target` maps any spelling onto the combo's spelling (`to_root_name(root, note_names())`). The checkable "Key-aware tools spell by key signature" item in the same menu calls `_set_key_aware_spelling`, which saves `key_aware_spelling` and refreshes the circle of fifths. The triad explorer reads the setting when it opens.

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
| `ChordAtlasDialog.target_changed` (Find-mode target) | str,str | `harmonic_panel.set_target` (radar moves go through `stance_selected`) |
| `ScaleFinderWidget.scale_step_applied, box_highlight_requested, clear_highlight_requested, box_shading_toggled, play_note_requested, target_changed` | various | `_apply_scale_step` (`apply_stance` with banner; the pocket is left alone), canvas box, settings, `audio.play_note`, `canvas.set_scale_analysis`. Play Run is a widget timer (one note per Tempo beat, lighting each circle via `overlay_step_changed`), so it can be stopped; `play_notes_requested` was removed. |
| `ScaleFinderWidget.overlay_changed / overlay_cleared / overlay_step_changed / overlay_label_mode_changed` (E-30) | list,list / — / int / str | `canvas.set_scale_overlay` / `clear_scale_overlay` / `set_overlay_active_step` / `_on_scale_overlay_label_changed` (canvas + settings). The finder publishes on show and on every change while shown, and clears the overlay and shading on hide. |
| `FretboardCanvas.overlay_step_clicked` (E-30) | int | `scale_finder.select_step` (clicking a circle that is not a step plays it via `node_clicked`) |
| `ScaleFinderWidget.ghost_changed / overlay_loop_changed / overlay_quiz_changed / overlay_reveal_requested / overlay_wrong_marked` (E-30 phase 3) | list / int,int / bool / list / object | `canvas.set_scale_ghost` / `set_overlay_loop` (-1 = none) / `set_overlay_quiz` / `reveal_overlay_notes` / `mark_overlay_wrong`. `clear_scale_overlay` resets all of them. |
| `ScaleFinderWidget.overlay_chord_changed / find_chord_requested` (E-31) | list (pitch classes) / str,str,int,int | `canvas.set_overlay_chord` (gold rings, other notes dimmed) / `_find_scale_chord_voicings` → `_open_chord_atlas` Find mode + `set_find_fret_range` |
| `ChordAtlasDialog.scale_requested` (E-31) | str,str,str,str,int (scale root, scale, chord root, chord type, fret or -1) | `_open_scale_for_chord`: `scale_finder.set_target`, range fret-1..fret+2 when a voicing is selected, `select_chord`, show |
| `FretboardCanvas.quiz_note_clicked` (E-30 phase 3) | object (BoxNote) | `scale_finder.answer_quiz` (replaces `overlay_step_clicked` while the quiz runs; ghosts are not clickable then) |
| `CircleOfFifthsWidget.chord_triggered` | str,str,bool,set | `_on_circle_chord_triggered` (the 4th arg, allowed mechanics, is dropped) |
| `ProgressionStudioWidget.stance_requested` (E-32) | int,list,list,str | `apply_stance(fret, controllers, grip, play=False, banner=)` |
| `ProgressionStudioWidget.play_step_requested` | str,list,float (style, strings in play order, seconds between notes) | `_play_studio_step`: block/roll → `_play_pocket(roll=)`; arpeggio → `audio.play_note(..., delay=i*dt)` per string |
| `ProgressionStudioWidget.click_requested / silence_requested` | bool,str / — | `audio.play_click(accent, sound)` / `audio.silence_all` |
| `ProgressionStudioWidget.capture_requested` | bool (replace the selected step) | `_capture_into_studio`: `identify_grip_chord` (harmonic target as hint) → `studio.add_captured_step` |
| Circle of fifths "Auto-Add to Progression Studio" | — | `studio.add_chord_step` (pinned) |
| `StanceChordInspectorDialog.grip_applied` | set | `_apply_pocket_preset` |
| `StarMapWidget.landmark_selected`, `StringsOfPearlsDialog.step_selected`, `FlashcardDrillDialog.landmark_verified` | int,set,set | `_on_star_map_dialog_selected` |
| `CopedantEditorDialog.neck_updated` | — | `_on_copedant_modified` |
| `TriadExplorerDialog.grip_selected`, `CopedantCompareDialog.stance_selected` | int,set,set,str,str | `_on_triad_grip_selected` (`set_target`, then `apply_stance`) |
| `CopedantCompareDialog.activate_neck_requested` | int | `_select_copedant_index` |
| `ProfileManagerDialog.open_requested` | str, int | `switch_profile` |
| `ProfileManagerDialog.saved_as` | str | `_on_profile_saved_as` (the open setup now belongs to that profile) |
| `TuningBrowserDialog.open_requested` / `copy_requested` | str, int / Neck | `switch_profile` / `_add_tuning_to_open_profile` |

## Windows and dialog lifetimes

- **Created once at startup and toggled with show/hide** (`Qt.Window` children): scale finder, circle of fifths. (The voicing finder window was retired in E-28: "🔍 Chord Finder", the harmonic panel's Find button and View ▸ Chord Finder open the Chord Atlas in Find mode.) The sequencer is a `QDockWidget`.
- **Lazily created and cached:** stance inspector.
- **Dock:** the Progression Studio (`dock_progression_studio`, bottom area by default; the old `dock_sequencer` name is not reused so a saved window state can't squeeze it into the side). The Voice Leader window and the Sequencer dock were removed in E-32.
- **Modeless, one instance (`MainWindow._perm_trainer`, deleted on close):** permutation trainer. It follows `canvas.pocket_changed` live (it plays the 4 lowest pocket strings), reads the notes from `canvas.active_states` on every tick, and opening it with fewer than 4 pocket strings first selects the book's group 8-7-6-5. Tempo changes apply while running (`Qt.PreciseTimer`). The click sound and mode are selectable and persisted (`perm_click_sound`, `perm_click_mode`). Hiding or closing it stops the workout.
- **Modeless, one instance (`MainWindow._compare_dlg`, deleted on close):** Compare Copedants (E-25), opened from Copedant ▸ Compare Copedants…. The baseline is the active neck; the modified side defaults to a copy of it or the next neck. The main window stays usable. `_load_current_neck` calls `dlg.set_active_neck(idx, guitar)`, which re-scans only if the selected neck objects changed. Double-clicking a way on the inactive neck emits `activate_neck_requested(idx)` (→ `_select_copedant_index`) and then `stance_selected` (→ `_on_triad_grip_selected`). Filters: a sticky chord-type menu, no-5th shells, max controllers, gains/losses, and "only using" controller toggles. Opened from the editor's "Compare to Saved" instead, the dialog is modal and applies nothing.
- **Modeless, one instance (`MainWindow._atlas_dlg`, deleted on close):** Chord Atlas (E-27), opened from Copedant ▸ Chord Atlas…. It shows the neck combo ("Follow active neck" on by default; picking another neck turns it off), "Show at fret", a root filter, the shared `ChordFilterBar` and grip configuration (source, 3/4/5 strings, max span, custom groups). Its views are By chord, By stance and Coverage; chord and stance rows fill their children lazily on expand. `_load_current_neck` calls `set_active_neck`, and `canvas.pocket_changed` feeds `set_current_pocket`. Double-click behaves as in Compare (`activate_neck_requested`, then `stance_selected` → `_on_triad_grip_selected`). Atlases are cached per neck object. **Mode** combo: *Explore a position* (the views above) or *Find a chord* (E-28): root + type, "tones that must sound" checkboxes (untick for rootless/shell voicings), up-to-fret, hide awkward, sort; a positions table with Fret / Pedals / Ergonomics / Strings / Inversion / Intervals / Missing. `MainWindow._open_chord_finder` opens it in Find mode on the harmonic target (`set_find_target`); Find-mode combo changes emit `target_changed`. The **Circle-of-Fifths radar** (bottom, checkable) uses `chord_atlas.find_neighbors` (strict atlas matching, E-29) on the selected way or position, debounced 250 ms. Double-clicking a move emits `stance_selected` with the move's chord, so the harmonic target follows. The positions table is filled with column auto-sizing off (resize-to-contents made every `setItem` re-measure: 16 ms per cell). The filter controls (chord-type menu, inversions, shells, max controllers, pedal/lever toggles with a match mode: Exactly these (default) / Including these / Only these (and open)) live in `ui/chord_filter_bar.py` and are shared with Compare Copedants.
- **Modal, created per open:** copedant editor, profile manager, star map, pearls, flashcards, triad explorer (E-19: `grip_selected` → `MainWindow._on_triad_grip_selected`, which sets the harmonic target and then calls `apply_stance`). Star map, pearls and flashcards receive the active neck.
- The Progression Studio gets `set_neck(neck)` on every neck switch. If the neck's name or controllers changed it stops, clears every stance (pinned too) and re-voices the chords for the new neck. Presets are mapped onto the neck with `resolve_preset_steps` and refused for the other tuning.
- **Studio transport:** a single-shot `Qt.PreciseTimer` re-armed against an absolute beat grid (`t0 + k·60/BPM`); a BPM change keeps the last beat and re-anchors. Play runs beat 1 (or the first count-in click) immediately; clicks and notes go through the MIDI scheduler. Editing the progression stops playback; hiding the dock stops it too.

## Coupling violations (cleanup targets)

- Calls into `parent_window._play_pocket` / `_apply_pocket_preset` / `.audio` / `.canvas.active_states`: pearls, stance inspector, permutation trainer, voice leader.
- `MainWindow._toggle_c6_menu_pedal_offset` builds an invisible editor dialog and calls its private methods.
- `lever_panel` imports `STANDARDIZED_KNEE_LEVERS` from `copedant_editor_dialog`. This domain constant belongs in `core`.
- Inline stylesheets hard-code dark colors in about 20 places, so light theme only partly applies.
