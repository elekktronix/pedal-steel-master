"""Tests for the 2026-11-12 audit fix plan, P1 items (A1, A2, A7, A10;
docs/architecture/08-audit-2026-11-fix-plan.md).

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

from core.ergonomics import ErgonomicsEngine  # noqa: E402
from core.profile_manager import ProfileManager, factory_guitar  # noqa: E402
from core.relative_moves import RelativeMovesEngine  # noqa: E402
from core.stances import grip_matches_chord  # noqa: E402
from core.theory import CHORD_FORMULAS  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication([])

E9 = "10-String E9 Chromatic"


def _delete(w) -> None:
    from PySide6.QtCore import QCoreApplication, QEvent

    try:
        w.close()
        w.deleteLater()
    except RuntimeError:
        return
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


class SameFretFamilyTests(unittest.TestCase):  # A1
    def test_options_are_labelled_by_chord_type_and_resolve(self):
        seen = set()
        for neck in factory_guitar().necks:
            for fret in range(0, 12):
                opts = RelativeMovesEngine.get_all_same_fret_chords(neck, fret, "all")
                keys = [(o.roman_degree, o.chord_root) for o in opts]
                self.assertEqual(len(keys), len(set(keys)))
                for o in opts:
                    with self.subTest(neck=neck.name, fret=fret, label=o.label):
                        seen.add(o.chord_type)
                        self.assertIn(o.chord_type, CHORD_FORMULAS)
                        self.assertNotIn("•", o.chord_name)
                        self.assertNotIn("Group", o.chord_name)
                        # Resolved through FretboardResolver: the option sounds what it names.
                        self.assertTrue(grip_matches_chord(neck, fret, o.controllers, o.target_strings,
                                                           o.chord_root, o.chord_type, require_root=False))
                        if o.chord_type == "Augmented":
                            self.assertTrue(o.roman_degree.endswith("+") and o.chord_name.endswith("+"))
                        if o.chord_type == "Minor 6th":
                            self.assertTrue(o.roman_degree.endswith("6") and o.chord_name.endswith("m6"))
                        if o.chord_type == "Half-Diminished":
                            self.assertTrue(o.roman_degree.endswith("ø7") and o.chord_name.endswith("m7b5"))
                            self.assertNotIn("°", o.label)
        self.assertTrue({"Augmented", "Minor 6th", "Half-Diminished", "Minor"} <= seen)

    def test_m6_and_minor_are_separate_options(self):
        neck = next(n for n in factory_guitar().necks if n.name == E9)
        opts = RelativeMovesEngine.get_all_same_fret_chords(neck, 0, "all")
        m6 = [o for o in opts if o.chord_type == "Minor 6th"]
        self.assertTrue(m6)
        for o in m6:
            plain = [p for p in opts if p.chord_root == o.chord_root and p.chord_type == "Minor"]
            for p in plain:
                self.assertNotEqual(p.roman_degree, o.roman_degree)


class KneeGroupTests(unittest.TestCase):  # A2
    def test_every_knee_lever_belongs_to_a_knee(self):
        possible = lambda c: ErgonomicsEngine.evaluate_stance(set(c)).is_possible  # noqa: E731
        for combo in ({"LKL", "LKV"}, {"LKR", "LKV"}, {"LKL", "VL"}, {"LKL", "LKL2"}, {"RKL", "RKR2"},
                      {"RKR", "RKR2"}, {"CKL", "CKR"}, {"LKL", "RKL", "CKV"}):
            with self.subTest(combo=combo):
                self.assertFalse(possible(combo))
        for combo in ({"LKL", "RKR2"}, {"LKL", "CKV"}, {"RKR", "CKL"}, {"P1", "P2", "LKL", "RKR"}):
            with self.subTest(combo=combo):
                self.assertTrue(possible(combo))

    def test_fresh_load_has_no_impossible_candidates(self):
        from core.voicing_solver import VoicingSolver

        neck = next(n for n in factory_guitar().necks if n.name == "BE E9 3P-5KL-1HS")
        stances = VoicingSolver.candidate_stances(neck)
        self.assertTrue(any("RKR2" in s for s in stances))  # still usable on its own
        for bad in ({"LKL", "LKV"}, {"RKR", "RKR2"}, {"RKL", "RKR2"}):
            for s in stances:
                self.assertFalse(bad <= set(s), (bad, s))


class FakeAudio:
    def __init__(self):
        self.use_compensated_temperament = False
        self.calls = []

    def glide_string_pitch(self, *a, **k):
        return True

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append((name, a, k))


class AuditAWindowTests(unittest.TestCase):
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
        self.addCleanup(_delete, w)
        w._select_copedant_index(next(i for i, n in enumerate(w.guitar.necks) if n.name == E9))
        return w

    def test_circle_click_honours_mechanics_filter(self):  # A7
        w = self._window()
        cw = w.circle_widget
        w.apply_stance(5, set(), {8, 6, 5}, play=False)
        for key, btn in cw.movement_buttons.items():
            btn.setChecked(key == "Same-Fret Pedal Drop")
        allowed = cw.get_allowed_mechanics()
        moved = 0
        for root, ctype in (("A", "Major"), ("D", "Major"), ("E", "Dominant 7th"), ("F#", "Minor")):
            with self.subTest(chord=(root, ctype)):
                w.apply_stance(5, set(), {8, 6, 5}, play=False)
                expected = cw.pick_voicing(root, ctype, 5, set(), {8, 6, 5}, allowed)
                w._on_circle_chord_triggered(root, ctype, False, allowed)
                if expected is None:
                    self.assertEqual(w.canvas.bar_fret, 5)
                    self.assertIn("allowed movements", w.statusBar().currentMessage())
                else:
                    m, mech = expected
                    moved += 1
                    self.assertEqual(mech, "Same-Fret Pedal Drop")
                    self.assertEqual(w.canvas.bar_fret, 5)
                    self.assertEqual(set(w.canvas.engaged_levers), set(m.engaged_levers))
        self.assertGreater(moved, 0)

    def test_scale_and_trainer_notes_carry_newman_cents(self):  # A10
        w = self._window()
        w.audio.use_compensated_temperament = True
        w.audio.calls.clear()
        w.scale_finder.play_note_requested.emit(59, 5, [])  # open B on string 5: +8 cents
        (call,) = [c for c in w.audio.calls if c[0] == "play_note"]
        self.assertEqual(call[1], (59, 5))
        self.assertEqual(call[2]["cents_offset"], 8.0)

        w.apply_stance(0, set(), {8, 7, 6, 5}, play=False)
        w._open_permutation_trainer()
        trainer = w._perm_trainer
        self.addCleanup(_delete, trainer)
        trainer.combo_click.setCurrentIndex(0)
        w.audio.calls.clear()
        trainer.current_event_idx = 0
        trainer._on_tick()
        notes = [c for c in w.audio.calls if c[0] == "play_note"]
        self.assertTrue(notes)
        s_num = notes[0][1][1]
        self.assertIn("cents_offset", notes[0][2])
        self.assertEqual(notes[0][2]["cents_offset"], w._current_cents([s_num]).get(s_num, 0.0))
        self.assertNotEqual(notes[0][2]["cents_offset"], 0.0)


if __name__ == "__main__":
    unittest.main()
