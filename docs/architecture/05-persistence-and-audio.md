# 05 — Persistence, Settings, Export & Audio

## Files on disk

| Path | Written by | Read by | Content |
|---|---|---|---|
| `~/.psg_visualizer/app_settings.json` | `core/settings.save_settings` on every preference toggle | `MainWindow.__init__` (falls back once to the legacy, now untracked `<repo>/app_settings.json`) | `{theme, show_inversions, show_scale_box, show_nashville, use_newman_tuning, pedal_swells, note_spelling, key_aware_spelling, perm_click_sound, perm_click_mode, studio_click_sound, studio_count_in}` (`note_spelling` = `"sharps"`/`"flats"`, applied with `theory.set_accidental_preference` at startup; `key_aware_spelling` (default true) with `theory.set_key_aware_spelling`) |
| `~/.psg_visualizer/session.json` | `MainWindow.closeEvent` (`core/session.save_session`) | `MainWindow.__init__` (`load_session`; an unreadable file is ignored with a warning) | neck, fret, controllers, pocket, target, display mode, geometry/state (base64), `studio_visible` (falls back to the old `sequencer_visible`), `studio` (the Progression Studio's progression, `StudioProgression.to_dict`; stances are kept only on the same neck) |
| `~/.psg_visualizer/app.log` (+ rotations) | `logging` (configured in `main.py`) | you | INFO and above, including tracebacks of handled errors |
| `~/.psg_visualizer/profiles/active_guitar_setup.json` | `MainWindow._save_active_guitar_setup` (close, copedant edits, profile switch), editor `_persist_active_guitar` | `load_startup_guitar` when resuming the last session (falls back to Factory on any exception) | `SteelGuitar` with `profile` = the open profile ("" = Factory) |
| `~/.psg_visualizer/profiles/<name>.json` | `MainWindow._save_active_guitar_setup` while that profile is open; Profiles dialog Save As / Rename / Import; editor Copy to Profile; File → Import Setup | Profile selector, Profiles dialog, Tuning Browser, startup | `SteelGuitar` (all the profile's tunings). Legacy files with one `Neck` load as a one-tuning profile and are rewritten on the next save |
| User-chosen `*.json` | File → Export Setup | File → Import Setup | `SteelGuitar` |
| User-chosen `*.json` (one copedant) | Copedant → Export Current Copedant (`export_neck`) | Copedant → Import; Profiles dialog → Import | single `Neck.to_dict()` with `source_profile` blanked |
| User-chosen `*.json` (one profile) | Profiles dialog → Export (`ProfileManager.export_profile`) | Profiles dialog → Import; File → Import Setup as Profile | `SteelGuitar` with `profile` blanked |
| User-chosen `*.cop / *.json` | — | Copedant → Import (adds tunings to the open profile); Profiles dialog → Import and File → Import Setup (create one new profile) | read by `profile_manager.read_necks_file`: a single `Neck`, a full setup (`necks` list; every neck is taken) or PSG Compass JSON |
| User-chosen `*.cp / *.json / *.cprog` | Progression Studio Save | Progression Studio Load ▸ Open file | `.cp` measures/slots (readable by the old format) plus a `studio` block with the exact steps (`StudioProgression.to_dict`) |
| User-chosen `*.pdf` | File → Export PDF | — | ReportLab sheet |
| `%TEMP%/psg_metronome_chirp_{hi,lo}.wav` | `MetronomeChirp` (first use) | `QSoundEffect` | generated clicks |

### Settings rules
- `DEFAULT_SETTINGS` holds every key; saved files are merged over the defaults.
- Load and save errors are logged, and the app continues with the defaults.

### Profile rules
- A **profile** is a group of tunings (`SteelGuitar`). **Factory** (`FACTORY_PROFILE = ""`, `factory_guitar()`) is the presets in `core/presets.py` and is never written to a profile file. **User profiles** are `<name>.json` files. The main window's **Profile** selector switches profiles; the **Tuning** selector lists only the open profile's tunings.
- File name = `ProfileManager.sanitize_name` (`[alnum space _ -]`, stripped). Empty names and `active_guitar_setup` raise `ValueError`. Different names can still collide after sanitizing (`"BE E9 (Copy)"` → `"BE E9 Copy"`). Save As asks before overwriting (`choose_profile_name`); Rename refuses a taken name.
- `list_user_profiles` = every `*.json` except `active_guitar_setup.json`, sorted case-insensitively.
- **Saving:** the open user profile is written whenever the working setup is (`MainWindow._save_active_guitar_setup`): after copedant edits, before switching profiles and on close. Factory edits are kept only in `active_guitar_setup.json`; the selector shows "Factory (modified)", and switching away (or closing while a startup profile is set) offers Save as Profile / Discard / Cancel.
- **Import / export (JSON only):** `read_necks_file` detects the format (Compass = `strings` + `pedals`; setup = `necks` list; neck = `open_tuning`), migrates half-stop tokens, and clears `source_profile`; anything else raises `ValueError`. `ProfileManager.import_profile_file` puts every neck of the file into **one** new profile under `unique_profile_name` and **never overwrites** a profile. Copedant → Import adds the necks to the open profile.
- **Tuning Browser** (🔎 next to the Tuning selector, Copedant → Browse All Tunings): every tuning of every profile (`list_all_tunings`; the open profile shows its live tunings). Open switches to that profile and tuning; Add to Open Profile copies the tuning in under a unique name (`unique_neck_name`).
- `add_tuning_to_profile(name, neck)` (editor Copy to Profile) appends a copy to another user profile, creating it if needed.

### Startup / shutdown
Settings `startup_mode` (`"last"` / `"profile"`), `startup_profile` (`""` = Factory) and `startup_tuning` (neck name) choose what opens. They are set in the Profiles dialog ("At startup") or with Copedant → Open This Tuning at Startup. A forced startup tuning wins over the session's tuning, and the session stance is restored only on the session's own profile and tuning.
```
startup:  ensure ~/.psg_visualizer/profiles → load settings → MidiAudioEngine()
          → load_startup_guitar(settings): startup profile ? open it
                                             : active_guitar_setup.json ? load : factory_guitar()
          → current_neck_idx = startup tuning or 0 → build UI → menu → theme → load neck
shutdown: save active_guitar_setup.json → close pop-outs → audio.close()
```
The last session (neck, stance, target, window layout) is restored at startup (E-12), and the Newman temperament flag is applied.

## PDF export (`core/exporter.py`)
A landscape letter page with three parts: a header (neck, fret, controllers, grip, target), a copedant matrix table (open note, MIDI, delta per controller), and a table of sounding strings at the current stance, resolved through `FretboardResolver`. It does not show splits or half-stops. The `voicing_matches` parameter is accepted and ignored (E-17). Export and import errors are shown in a message box and logged.

## Audio (`core/audio.py`, `MidiAudioEngine`)

- **Windows only.** It uses `ctypes.windll.winmm` with the MIDI mapper. On other platforms every call is a silent no-op.
- **Channel map:** `channel_for_string(s)` = `STRING_CHANNELS[(s−1) % 14]` with `STRING_CHANNELS = 0–8, 10–14`. Channel 9 (`PERCUSSION_CHANNEL`, GM drums) never carries a string; it is used only by `play_click(accent, sound, delay=0)` for metronome clicks (permutation trainer, Progression Studio) (`CLICK_SOUNDS`: name → accent/normal GM drum note). Clicks go through the same scheduler as the notes, so a click and a note queued together sound together, which a `QSoundEffect` sample does not guarantee. `SEQUENCE_CHANNEL = 15` is for scale runs and notes without a string.
- On open, every used channel gets GM program 25 (steel acoustic guitar), sustain on (CC64=127) and centered pitch bend.
- **One scheduler thread** (`_Scheduler`, a timed heap queue) performs all MIDI output and owns all engine state. Public methods only enqueue. `MidiAudioEngine(send=fn)` injects a raw-message sink, which tests use. `wait_idle()` drains the queue.
- `play_note(pitch, string_num=None, velocity, cents_offset, delay=0)`: queued `delay` seconds ahead (Progression Studio arpeggios). Note-off for that channel's previous note, then bend (cents if temperament is on), then note-on. A strike cancels any running glide on that channel.
- `play_pocket(pitches, roll, velocity, cents)`: **pass `{string: midi}`** (MainWindow does). A list is still mapped to strings 1..n by position.
- `play_scale_sequence`: on the sequence channel, releasing each previous note, plus a final note-off.
- **Newman temperament:** `compute_newman_cents(neck, engaged, strings)` applies only to a 10-string neck in standard E9 open tuning. Open strings use the string table. A string pulled by a fully engaged `A`/`B`/`C`/`F`/`D` role controller uses that role's offset. Any other pull, or a half-stop, gets 0. MainWindow applies it to pockets, node clicks and arpeggios when enabled.
- `glide_string_pitch(string, semitone_delta, duration_sec=0.12, cents_offset=0)`: a 16-step cosine-eased bend relative to the struck pitch. It returns `False` beyond the ±2-semitone GM bend range. A newer glide or strike on the same channel cancels it (generation counter). Used for pedal/bar swells.
- Thread safety: no locks are needed, because only the scheduler thread touches MIDI and engine state.
