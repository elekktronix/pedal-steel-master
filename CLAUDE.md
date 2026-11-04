# CLAUDE.md — Pedal Steel Master

PySide6 desktop app (Windows-first) that visualizes pedal steel copedants, resolves the sounding pitch for any bar/pedal/lever stance, and runs chord, scale and voice-leading engines on top of that.

- Run: `.venv\Scripts\python.exe main.py`
- Tests: `.venv\Scripts\python.exe -m unittest discover -s tests -v` (stdlib `unittest`; pytest is not installed). The suite takes about 40 s. **Always run it with a timeout**, e.g. via `-X faulthandler` and `faulthandler.dump_traceback_later(220, exit=True)`, so a hang prints a stack instead of blocking.

## Read the architecture docs on demand, not up front

The docs in `docs/architecture/` are split so you only load what the task needs. Read `00-critical-rules.md` before changing any code. Read the others only when the task touches that area:

| Task touches | Read |
|---|---|
| Any code change | `docs/architecture/00-critical-rules.md` |
| `core/models.py`, `core/presets.py`, JSON formats, controller IDs | `docs/architecture/01-domain-model.md` |
| `core/resolver.py`, `core/ergonomics.py`, `core/stances.py`, splits, half-stops | `docs/architecture/02-pitch-resolution.md` |
| Any other `core/*_engine.py`, `voicing_solver`, `voice_leader`, `relative_moves`, presets content | `docs/architecture/03-theory-engines.md` |
| `ui/main_window.py`, signals, panels, dialogs | `docs/architecture/04-ui-state-and-data-flow.md` |
| Settings, profiles, `active_guitar_setup.json`, PDF, MIDI audio | `docs/architecture/05-persistence-and-audio.md` |
| Fixing a bug | `docs/architecture/06-defect-register.md` (look up the D-xx ID) |
| Planning or refactoring | `docs/architecture/07-enhancements.md` (E-xx IDs) |

`docs/architecture/README.md` holds the overview and the module map (including which modules are dead).

## Working preferences

- **Keep context light.** Don't read the whole codebase or every doc. Use the table above and targeted Grep or Read calls.
- **Reference IDs.** Name the defect or enhancement you're working on (e.g. "fixes D-07") in your summary and in commit messages.
- **Keep the docs in sync.** When a change alters behavior described in `docs/architecture/`, update that section in the same change. Mark fixed defects in `06-defect-register.md` instead of deleting them.
- **Minimal, targeted diffs.** Don't rewrite whole files, reformat untouched code, or "fix" dead modules (listed in the README). Don't refactor beyond the task without asking.
- **Verify musically.** Any change to pitch logic, presets or landmarks must be checked by resolving it through `FretboardResolver` (add or extend a test in `tests/`). Never trust a chord label without resolving it.
- **No citation markers** (`[cite: N]`) or similar artifacts in source files.
- **`core/` stays Qt-free.** Domain operations that mutate a `Neck` (renaming or renumbering controllers, migrations) belong in `core/`, not in dialogs.
- **Qt tests must really delete the windows and dialogs they create** (`deleteLater()` followed by `QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)`, as in the `destroy_window` / `_delete_widget` helpers). Leftover widgets make every later app-stylesheet change slower, and they once made the suite take 160 s or time out.
- Never create a second `ThemeManager`; use `ThemeManager.for_app(app)`.
- Don't commit or push unless asked.

## Hard rules (summary; full list in 00-critical-rules.md)

- Strings are 1-indexed, and string 1 is the highest pitch.
- Controller IDs are positional (`P1` = leftmost pedal). Labels are cosmetic and never drive logic.
- Half-stop engagement is the token `"<ID>_HALF"`. Split rules may list half tokens.
- Renaming or renumbering controllers must go through `core.models.remap_controller_ids` so splits and half-stops follow.
- `~/.psg_visualizer/profiles/active_guitar_setup.json` overrides `core/presets.py` at startup.
- Engines name controllers by **functional role** (`core/stances.py`: `A`, `B`, `C`, `F`, `D`, `BL`, `C6P4`…`C6P8`), never by hard-coded ID. Verify shapes with `grip_matches_chord`.
- Programmatic stance changes go through `MainWindow.apply_stance(...)`; never set lever buttons directly.
