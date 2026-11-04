# 05 — Persistence, Settings, Export & Audio

## Files on disk

| Path | Written by | Read by | Content |
|---|---|---|---|
| `~/.psg_visualizer/app_settings.json` | `core/settings.save_settings` on every preference toggle | `MainWindow.__init__` (falls back once to the legacy, now untracked `<repo>/app_settings.json`) | `{theme, show_inversions, show_scale_box, show_nashville, use_newman_tuning, pedal_swells, note_spelling, key_aware_spelling, perm_click_sound, perm_click_mode}` (`note_spelling` = `"sharps"`/`"flats"`, applied with `theory.set_accidental_preference` at startup; `key_aware_spelling` (default true) with `theory.set_key_aware_spelling`) |
| `~/.psg_visualizer/session.json` | `MainWindow.closeEvent` (`core/session.save_session`) | `MainWindow.__init__` (`load_session`; an unreadable file is ignored with a warning) | neck, fret, controllers, pocket, target, display mode, geometry/state (base64), sequencer visibility |
| `~/.psg_visualizer/app.log` (+ rotations) | `logging` (configured in `main.py`) | you | INFO and above, including tracebacks of handled errors |
| `~/.psg_visualizer/profiles/active_guitar_setup.json` | `MainWindow.closeEvent`, `_on_copedant_modified`, editor `_persist_active_guitar` | `MainWindow.__init__` (falls back to presets on any exception) | `SteelGuitar` |
| `~/.psg_visualizer/profiles/<name>.json` | editor Apply (linked necks only), Duplicate, Save-as; Profiles dialog Save | profile combo, Profiles dialog | single `Neck` (with `source_profile`) |
| User-chosen `*.json` | File → Export Setup | File → Import Setup | `SteelGuitar` |
| User-chosen `*.cop / *.json` | — | Copedant → Import | `Neck` or PSG Compass JSON |
| User-chosen `*.cp / *.json / *.cprog` | Voice Leader save | Voice Leader load | `ChordProgression` |
| User-chosen `*.pdf` | File → Export PDF | — | ReportLab sheet |
| `%TEMP%/psg_metronome_chirp_{hi,lo}.wav` | `MetronomeChirp` (first use) | `QSoundEffect` | generated clicks |

### Settings rules
- `DEFAULT_SETTINGS` holds every key; saved files are merged over the defaults.
- Load and save errors are logged, and the app continues with the defaults.

### Profile rules
- File name = `ProfileManager.sanitize_name` (`[alnum space _ -]`, stripped). Empty names and `active_guitar_setup` raise `ValueError`. Different names can still collide after sanitizing (`"BE E9 (Copy)"` → `"BE E9 Copy"`). The Profiles dialog and the editor's Save-as ask before overwriting; Apply on a linked neck overwrites its own file.
- `list_user_profiles` = every `*.json` except `active_guitar_setup.json`.
- Loading a profile **adds a linked neck entry** (`source_profile`, shown with 📁) and never overwrites another neck (rule C-11). The link is persisted in `active_guitar_setup.json`. Edits reach the profile file through editor Apply.

### Startup / shutdown
```
startup:  ensure ~/.psg_visualizer/profiles → load settings → MidiAudioEngine()
          → active_guitar_setup.json ? load : build_standard_d10_guitar()
          → current_neck_idx = 0 → build UI → menu → theme → load neck
shutdown: save active_guitar_setup.json → close pop-outs → audio.close()
```
The last session (neck, stance, target, window layout) is restored at startup (E-12), and the Newman temperament flag is applied.

## PDF export (`core/exporter.py`)
A landscape letter page with three parts: a header (neck, fret, controllers, grip, target), a copedant matrix table (open note, MIDI, delta per controller), and a table of sounding strings at the current stance, resolved through `FretboardResolver`. It does not show splits or half-stops. The `voicing_matches` parameter is accepted and ignored (E-17). Export and import errors are shown in a message box and logged.

## Audio (`core/audio.py`, `MidiAudioEngine`)

- **Windows only.** It uses `ctypes.windll.winmm` with the MIDI mapper. On other platforms every call is a silent no-op.
- **Channel map:** `channel_for_string(s)` = `STRING_CHANNELS[(s−1) % 14]` with `STRING_CHANNELS = 0–8, 10–14`. Channel 9 (`PERCUSSION_CHANNEL`, GM drums) never carries a string; it is used only by `play_click(accent, sound)` for metronome clicks (`CLICK_SOUNDS`: name → accent/normal GM drum note). Clicks go through the same scheduler as the notes, so a click and a note queued together sound together, which a `QSoundEffect` sample does not guarantee. `SEQUENCE_CHANNEL = 15` is for scale runs and notes without a string.
- On open, every used channel gets GM program 25 (steel acoustic guitar), sustain on (CC64=127) and centered pitch bend.
- **One scheduler thread** (`_Scheduler`, a timed heap queue) performs all MIDI output and owns all engine state. Public methods only enqueue. `MidiAudioEngine(send=fn)` injects a raw-message sink, which tests use. `wait_idle()` drains the queue.
- `play_note(pitch, string_num=None, velocity, cents_offset)`: note-off for that channel's previous note, then bend (cents if temperament is on), then note-on. A strike cancels any running glide on that channel.
- `play_pocket(pitches, roll, velocity, cents)`: **pass `{string: midi}`** (MainWindow does). A list is still mapped to strings 1..n by position.
- `play_scale_sequence`: on the sequence channel, releasing each previous note, plus a final note-off.
- **Newman temperament:** `compute_newman_cents(neck, engaged, strings)` applies only to a 10-string neck in standard E9 open tuning. Open strings use the string table. A string pulled by a fully engaged `A`/`B`/`C`/`F`/`D` role controller uses that role's offset. Any other pull, or a half-stop, gets 0. MainWindow applies it to pockets, node clicks and arpeggios when enabled.
- `glide_string_pitch(string, semitone_delta, duration_sec=0.12, cents_offset=0)`: a 16-step cosine-eased bend relative to the struck pitch. It returns `False` beyond the ±2-semitone GM bend range. A newer glide or strike on the same channel cancels it (generation counter). Used for pedal/bar swells.
- Thread safety: no locks are needed, because only the scheduler thread touches MIDI and engine state.
