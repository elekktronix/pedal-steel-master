"""Tests for E-11 (audio scheduler + swells), E-12 (session), E-13 (theme), D-34, D-38.

Run: .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.audio import SEQUENCE_CHANNEL, MidiAudioEngine, channel_for_string  # noqa: E402
from core.pearls_engine import PearlsEngine  # noqa: E402
from core.profile_manager import ProfileManager  # noqa: E402
from core import presets  # noqa: E402

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

_APP = QApplication.instance() or QApplication([])


def destroy_window(w) -> None:
    """Closes a MainWindow and really deletes it (deleteLater needs an event loop to run)."""
    from PySide6.QtCore import QCoreApplication, QEvent

    try:
        w.close()
        w.deleteLater()
    except RuntimeError:
        return  # already deleted
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

from ui.themes import ThemeManager, to_light_stylesheet  # noqa: E402


def _decode(msgs):
    """[(kind, channel, data1, value)] for note on/off and pitch bend messages."""
    out = []
    for m in msgs:
        status, ch = m & 0xF0, m & 0x0F
        d1, d2 = (m >> 8) & 0x7F, (m >> 16) & 0x7F
        if status == 0x90:
            out.append(("on", ch, d1, d2))
        elif status == 0x80:
            out.append(("off", ch, d1, 0))
        elif status == 0xE0:
            out.append(("bend", ch, 0, ((d2 << 7) | d1) - 8192))
    return out


class AudioSchedulerTests(unittest.TestCase):  # E-11 / D-35
    def setUp(self):
        self.msgs = []
        self.engine = MidiAudioEngine(send=self.msgs.append)
        self.engine.wait_idle()
        self.msgs.clear()

    def tearDown(self):
        self.engine.close()

    def test_pocket_strikes_bass_first_on_string_channels(self):
        self.engine.play_pocket({8: 52, 6: 56, 5: 59}, roll=True)
        self.engine.wait_idle()
        ons = [(ch, note) for kind, ch, note, _ in _decode(self.msgs) if kind == "on"]
        self.assertEqual(ons, [(channel_for_string(8), 52), (channel_for_string(6), 56), (channel_for_string(5), 59)])

    def test_glide_reaches_target_and_respects_range(self):
        self.engine.play_pocket({5: 59})
        self.assertTrue(self.engine.glide_string_pitch(5, 2.0, duration_sec=0.02))
        self.assertFalse(self.engine.glide_string_pitch(5, 3.0))
        self.engine.wait_idle()
        bends = [v for kind, ch, _, v in _decode(self.msgs) if kind == "bend" and ch == channel_for_string(5)]
        self.assertEqual(bends[-1], 8191)
        self.assertGreater(len(bends), 10)  # it actually glides in steps

    def test_new_strike_cancels_running_glide(self):
        self.engine.play_pocket({5: 59})
        self.engine.glide_string_pitch(5, 2.0, duration_sec=0.3)
        self.engine.play_pocket({5: 61})  # re-strike right away
        self.engine.wait_idle()
        events = [e for e in _decode(self.msgs) if e[1] == channel_for_string(5)]
        last_on = max(i for i, e in enumerate(events) if e[0] == "on")
        self.assertFalse([e for e in events[last_on + 1:] if e[0] == "bend"])

    def test_click_uses_percussion_channel(self):  # permutation trainer metronome
        from core.audio import CLICK_SOUNDS, PERCUSSION_CHANNEL

        self.engine.play_click(accent=True, sound="Woodblock")
        self.engine.play_click(accent=False, sound="Woodblock")
        self.engine.wait_idle()
        ons = [(ch, note) for kind, ch, note, _ in _decode(self.msgs) if kind == "on"]
        hi, lo = CLICK_SOUNDS["Woodblock"]
        self.assertEqual(ons, [(PERCUSSION_CHANNEL, hi), (PERCUSSION_CHANNEL, lo)])
        self.assertNotIn(PERCUSSION_CHANNEL, [channel_for_string(s) for s in range(1, 15)])

    def test_scale_sequence_releases_notes(self):
        self.engine.play_scale_sequence([60, 62, 64], delay=0.01)
        self.engine.wait_idle()
        events = [e for e in _decode(self.msgs) if e[1] == SEQUENCE_CHANNEL and e[0] in ("on", "off")]
        self.assertEqual([e[0] for e in events], ["on", "off", "on", "off", "on", "off"])


class ThemeTests(unittest.TestCase):  # E-13
    def test_light_mapping(self):
        qss = ("QPushButton { background-color: #2b303c; color: #e0e6ed; } "
               "QPushButton:checked { background-color: #0d6efd; color: #ffffff; }")
        light = to_light_stylesheet(qss)
        self.assertNotIn("#2b303c", light)          # dark surface lightened
        self.assertNotIn("#e0e6ed", light)          # light text darkened
        self.assertIn("background-color: #0d6efd; color: #ffffff", light)  # accent untouched
        self.assertEqual(to_light_stylesheet(light), light)  # idempotent

    def test_manager_maps_and_restores(self):
        tm = ThemeManager.for_app(_APP)
        try:
            btn = QPushButton("x")
            dark = "background-color: #212529; color: #ffde7a;"
            btn.setStyleSheet(dark)
            tm.set_dark(False)
            self.assertNotEqual(btn.styleSheet(), dark)
            btn.setStyleSheet("background-color: #343a40;")  # set while light, before first show
            btn.show()  # Qt polishes before showing -> mapped
            self.assertNotEqual(btn.styleSheet(), "background-color: #343a40;")
            btn.setStyleSheet("background-color: #212529;")  # set while light on a shown widget
            self.assertNotEqual(btn.styleSheet(), "background-color: #212529;")
            tm.set_dark(True)
            self.assertEqual(btn.styleSheet(), "background-color: #212529;")
        finally:
            tm.set_dark(True)


class PearlsTests(unittest.TestCase):  # D-34
    def test_no_rows_identical_to_open(self):
        steps = PearlsEngine.generate_scale_run("G", "Strings 3 & 5 (6ths / 3rds)")
        by_fret = {}
        for s in steps:
            by_fret.setdefault(s.fret, []).append(s.notes)
        for fret, notes in by_fret.items():
            self.assertEqual(len(notes), len(set(notes)), f"duplicate pairs at fret {fret}")


class ProfileNamingTests(unittest.TestCase):  # D-38
    def test_unique_profile_name(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ProfileManager, "STORAGE_DIR", Path(d)):
            ProfileManager.save_user_profile("BE E9 Copy", presets.build_be_e9_3p_5kl_1hs())
            self.assertEqual(ProfileManager.unique_profile_name("BE E9 (Copy)"), "BE E9 Copy 2")
            self.assertEqual(ProfileManager.unique_profile_name("Fresh"), "Fresh")


class FakeAudio:
    def __init__(self):
        self.use_compensated_temperament = False
        self.calls = []

    def set_compensated_temperament(self, enabled):
        self.use_compensated_temperament = enabled

    def glide_string_pitch(self, string_num, semitone_delta, duration_sec=0.12, cents_offset=0.0):
        self.calls.append(("glide", string_num, semitone_delta))
        return abs(semitone_delta) <= 2

    def play_note(self, pitch, string_num=None, velocity=95, cents_offset=0.0):
        self.calls.append(("note", string_num, pitch))

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append((name, a, k))


class MainWindowFeatureTests(unittest.TestCase):
    def setUp(self):
        import core.session as session
        import core.settings as settings

        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(ProfileManager, "STORAGE_DIR", tmp / "profiles"),
            mock.patch.object(settings, "SETTINGS_FILE", tmp / "app_settings.json"),
            mock.patch.object(settings, "LEGACY_SETTINGS_FILE", tmp / "legacy.json"),
            mock.patch.object(settings, "SETTINGS_DIR", tmp),
            mock.patch.object(session, "SESSION_FILE", tmp / "session.json"),
            mock.patch("ui.main_window.MidiAudioEngine", FakeAudio),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()

    def _window(self):
        from ui.main_window import MainWindow

        w = MainWindow()
        self.addCleanup(destroy_window, w)
        return w

    def test_session_round_trip(self):  # E-12
        w = self._window()
        c6_idx = next(i for i, n in enumerate(w.guitar.necks) if n.name == "10-String C6")
        w._select_copedant_index(c6_idx)
        w.harmonic_panel.set_target("Bb", "Minor 7th")
        w.apply_stance(5, {"P6"}, {7, 6, 5, 4}, play=False)
        w._set_display_mode("notes")
        destroy_window(w)

        w2 = self._window()
        try:
            self.assertEqual(w2.current_neck_idx, c6_idx)
            self.assertEqual(w2.canvas.bar_fret, 5)
            self.assertEqual(w2.canvas.engaged_levers, {"P6"})
            self.assertEqual(w2.lever_panel.active_controllers, {"P6"})
            self.assertEqual(w2.canvas.active_pocket, {7, 6, 5, 4})
            self.assertEqual((w2.harmonic_panel.get_root(), w2.harmonic_panel.get_chord_type()), ("A#", "Minor 7th"))
            self.assertEqual(w2.canvas.display_mode, "notes")
        finally:
            w2.close()

    def test_corrupt_session_is_ignored(self):  # E-12
        import core.session as session

        session.SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        session.SESSION_FILE.write_text("{not json", encoding="utf-8")
        w = self._window()
        try:
            self.assertEqual(w.canvas.bar_fret, 0)
        finally:
            w.close()

    def test_lever_toggle_swells_ringing_strings(self):  # E-11
        w = self._window()
        try:
            w.apply_stance(0, set(), {6, 5, 4}, play=True)  # strike strings 6, 5, 4
            w.audio.calls.clear()
            w.lever_panel.pedal_buttons["P1"]._set_state(2)  # A pedal: string 5 B -> C#
            glides = {c[1]: c[2] for c in w.audio.calls if c[0] == "glide"}
            self.assertEqual(glides.get(5), 2)
            self.assertEqual(glides.get(4), 0)
            self.assertFalse([c for c in w.audio.calls if c[0] == "note"])
        finally:
            w.close()

    def test_triad_grip_sets_target_and_stance(self):  # E-19
        w = self._window()
        try:
            w._on_triad_grip_selected(3, {"P1"}, {6, 5, 4}, "G", "Dominant 9th")
            self.assertEqual((w.harmonic_panel.get_root(), w.harmonic_panel.get_chord_type()), ("G", "Dominant 9th"))
            self.assertEqual((w.canvas.bar_fret, w.canvas.engaged_levers, w.canvas.active_pocket), (3, {"P1"}, {6, 5, 4}))
            self.assertEqual(w.lever_panel.active_controllers, {"P1"})
        finally:
            w.close()

    def test_permutation_trainer_is_modeless_and_follows_fretboard(self):
        w = self._window()
        try:
            w._open_permutation_trainer()
            dlg = w._perm_trainer
            self.assertFalse(dlg.isModal())
            self.assertEqual(w.canvas.active_pocket, {8, 7, 6, 5})  # opened on the book's strings
            self.assertEqual(set(dlg.lane_index), {8, 7, 6, 5})

            w.apply_stance(3, {"P1"}, {6, 5, 4, 3}, play=False)  # change the main fretboard
            self.assertEqual(set(dlg.lane_index), {6, 5, 4, 3})
            self.assertEqual({e.string_number for e in dlg.events}, {6, 5, 4, 3})

            dlg.combo_click.setCurrentText("Claves")
            w.audio.calls.clear()
            dlg._toggle_workout()  # first tick plays immediately: click, then the note
            names = [c[0] for c in w.audio.calls]
            self.assertEqual(names[:2], ["play_click", "note"])
            self.assertEqual(w.audio.calls[0][2], {"accent": True, "sound": "Claves"})
            self.assertEqual(dlg.timer.interval(), 600)
            dlg.spin_tempo.setValue(200)  # tempo applies while running
            self.assertEqual(dlg.timer.interval(), 300)
            self.assertEqual(w.settings["perm_click_sound"], "Claves")

            w._open_permutation_trainer()  # re-opening reuses the same window
            self.assertIs(w._perm_trainer, dlg)
            dlg.close()
            self.assertFalse(dlg.timer.isActive())
        finally:
            w.close()

    def test_light_theme_restyles_inline_widgets(self):  # E-13
        w = self._window()
        try:
            dark_qss = w.btn_pop_chord.styleSheet()
            w._set_theme("light")
            self.assertNotEqual(w.btn_pop_chord.styleSheet(), dark_qss)
            self.assertFalse(w.canvas.is_dark_mode)
            w._set_theme("dark")
            self.assertEqual(w.btn_pop_chord.styleSheet(), dark_qss)
        finally:
            w.close()


class CompareAndSpellingWindowTests(unittest.TestCase):  # E-25 follow-ups
    setUp = MainWindowFeatureTests.setUp
    tearDown = MainWindowFeatureTests.tearDown
    _window = MainWindowFeatureTests._window

    def test_compare_window_is_modeless_and_follows_active_neck(self):
        from copy import deepcopy

        w = self._window()
        base_idx = w.current_neck_idx
        copy = deepcopy(w.guitar.necks[base_idx])
        copy.name = copy.name + " copy"
        copy.knee_levers[sorted(copy.knee_levers)[0]].changes[3] = 1
        w.guitar.necks.append(copy)
        w._open_copedant_compare()
        dlg = w._compare_dlg
        self.assertIsNotNone(dlg)
        self.assertFalse(dlg.isModal())
        self.assertEqual(dlg.combo_mod.currentData(), len(w.guitar.necks) - 1)
        w._open_copedant_compare()  # second open reuses the window
        self.assertIs(w._compare_dlg, dlg)
        # Switching the active neck in the main window updates the dialog.
        w._select_copedant_index(len(w.guitar.necks) - 1)
        self.assertEqual(dlg.active_neck_idx, len(w.guitar.necks) - 1)
        self.assertTrue(dlg.can_apply(gained=True))
        # A lost way switches back to the baseline and applies the stance there.
        dlg.activate_neck_requested.emit(base_idx)
        self.assertEqual(w.current_neck_idx, base_idx)
        self.assertEqual(dlg.active_neck_idx, base_idx)
        dlg.close()

    def test_chord_atlas_is_modeless_and_follows_neck_and_pocket(self):  # E-27
        from core.chord_atlas import GRIP_SOURCE_CURRENT

        w = self._window()
        w._open_chord_atlas()
        dlg = w._atlas_dlg
        self.assertFalse(dlg.isModal())
        self.assertIs(dlg.neck, w.guitar.necks[w.current_neck_idx])
        c6_idx = next(i for i, n in enumerate(w.guitar.necks) if n.name == "10-String C6")
        w._select_copedant_index(c6_idx)
        self.assertIs(dlg.neck, w.guitar.necks[c6_idx])  # follows the active neck
        dlg.set_grip_source(GRIP_SOURCE_CURRENT)
        w.apply_stance(0, set(), {7, 6, 5}, play=False)  # pocket on the fretboard
        self.assertEqual(dlg.current_pocket, {7, 6, 5})
        self.assertTrue(dlg.entries)
        self.assertTrue(all(s.strings == (7, 6, 5) for e in dlg.entries for s in e.sightings))
        dlg.close()

    def test_chord_finder_opens_atlas_find_mode(self):  # E-28
        from ui.chord_atlas_dialog import MODE_FIND

        w = self._window()
        self.assertFalse(hasattr(w, "voicing_finder"))
        w.harmonic_panel.set_target("A", "Minor")
        w.harmonic_panel.find_voicings_requested.emit()
        dlg = w._atlas_dlg
        self.assertEqual(dlg.mode, MODE_FIND)
        self.assertEqual((dlg.combo_find_root.currentText(), dlg.combo_find_type.currentText()), ("A", "Minor"))
        self.assertTrue(dlg.positions)
        dlg._on_position_double_clicked(0)
        p = dlg.positions[0]
        self.assertEqual(w.canvas.bar_fret, p.fret)
        self.assertEqual(w.canvas.active_pocket, set(p.sighting.strings))
        self.assertEqual((w.harmonic_panel.get_root(), w.harmonic_panel.get_chord_type()), ("A", "Minor"))
        w._open_chord_finder()  # reuses the same window
        self.assertIs(w._atlas_dlg, dlg)
        dlg.close()

    def test_note_spelling_preference_is_global(self):
        from core.theory import get_accidental_preference, set_accidental_preference

        self.addCleanup(set_accidental_preference, "sharps")
        w = self._window()
        w.harmonic_panel.set_target("D#", "Major")
        w._set_note_spelling("flats")
        self.assertEqual(get_accidental_preference(), "flats")
        self.assertEqual(w.settings["note_spelling"], "flats")
        self.assertEqual(w.harmonic_panel.get_root(), "Eb")
        names = {s.string_number: s.active_note_name for s in w.canvas.active_states}
        self.assertTrue(names[2].startswith("Eb") or names[2].startswith("E"), names)
        w.harmonic_panel.set_target("A#", "Minor")  # sharp input lands on the flat item
        self.assertEqual(w.harmonic_panel.get_root(), "Bb")
        w._set_note_spelling("sharps")
        self.assertEqual(w.harmonic_panel.get_root(), "A#")

    def test_circle_keeps_key_names_and_key_aware_toggle(self):
        from core.theory import is_key_aware_spelling, set_accidental_preference, set_key_aware_spelling

        self.addCleanup(set_accidental_preference, "sharps")
        self.addCleanup(set_key_aware_spelling, True)
        w = self._window()
        cw = w.circle_widget
        cw.set_key_center("C#")                     # any spelling maps onto the wheel's key name
        self.assertEqual(cw.combo_key.currentText(), "Db")
        w._set_note_spelling("sharps")
        self.assertEqual(cw.combo_key.currentText(), "Db")   # traditional circle names are not respelled
        self.assertTrue(w.action_key_aware_spelling.isChecked())
        w.action_key_aware_spelling.setChecked(False)
        self.assertFalse(is_key_aware_spelling())
        self.assertFalse(w.settings["key_aware_spelling"])
        labels = [d["button"].text() for d in cw.family_buttons_data]
        self.assertTrue(any("C#" in s for s in labels), labels)   # I of Db now spelled C#
        cw.highlight_chord("C#", "Major")
        cw.set_key_center("Db")
        self.assertTrue(any(d["root"] == "C#" for d in cw.family_buttons_data))


if __name__ == "__main__":
    unittest.main()
