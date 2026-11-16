"""Tests for the 2026-11-16 audit fixes (B1-B19, docs/architecture/09-audit-2026-11-16.md).

Run: .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import presets  # noqa: E402
from core.audio import MidiAudioEngine  # noqa: E402
from core.models import half_stop_controllers, has_franklin_p1, set_franklin_p1  # noqa: E402
from core.profile_manager import ProfileManager, factory_guitar, prepare_loaded_guitar  # noqa: E402
from core.progression_studio import StudioStep, stance_is_playable, tab_steps  # noqa: E402
from core.resolver import FretboardResolver  # noqa: E402
from core.stances import grip_matches_chord, grip_pitch_classes, resolve_stance  # noqa: E402
from core.theory import CHORD_FORMULAS, NOTE_TO_SEMITONE  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication([])

U12_HS = "GFI 12U 7P-5KL-3HS"


def _neck(name):
    return next(n for n in factory_guitar().necks if n.name == name)


def _delete(w) -> None:
    from PySide6.QtCore import QCoreApplication, QEvent

    try:
        w.close()
        w.deleteLater()
    except RuntimeError:
        return
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
class LoadMigrationTests(unittest.TestCase):  # B1 / A2
    def test_every_load_path_renames_vl(self):
        for neck in factory_guitar().necks:
            with self.subTest(neck=neck.name):
                self.assertNotIn("VL", neck.knee_levers)
                self.assertFalse(any(c.replace("_HALF", "") == "VL" for s in neck.splits for c in s.controllers))
        raw = presets.build_standard_d10_guitar()
        self.assertTrue(any("VL" in n.knee_levers for n in raw.necks))  # the presets still use VL
        prepared = prepare_loaded_guitar(raw)
        self.assertFalse(any("VL" in n.knee_levers for n in prepared.necks))
        self.assertIn("RKR2", _neck("BE E9 3P-5KL-1HS").knee_levers)  # not retired: kept

    def test_migration_does_not_change_pitches(self):
        raw = next(n for n in presets.build_standard_d10_guitar().necks if n.name == U12_HS)
        mig = _neck(U12_HS)
        for fret, ctrls_raw, ctrls_mig in ((3, {"P1_HALF", "VL"}, {"P1_HALF", "LKV"}), (5, {"P1", "VL"}, {"P1", "LKV"})):
            a = [s.active_midi for s in FretboardResolver.resolve_neck_state(raw, fret, ctrls_raw)]
            b = [s.active_midi for s in FretboardResolver.resolve_neck_state(mig, fret, ctrls_mig)]
            self.assertEqual(a, b)


class StanceIsPlayableTests(unittest.TestCase):  # B1 / B3
    def test_checks_controllers_half_rules_and_strings(self):
        neck = _neck(U12_HS)
        st = StudioStep(root="C", chord_type="Major")
        st.set_stance(3, {"P3_HALF", "LKL"}, {6, 5, 4}, pinned=True)
        self.assertTrue(stance_is_playable(neck, st))
        neck.half_stops = [h for h in neck.half_stops if h.controller_id != "P3"]
        self.assertNotIn("P3", half_stop_controllers(neck))
        self.assertFalse(stance_is_playable(neck, st))  # stale half token
        st.set_stance(3, {"P9"}, {6, 5, 4})
        self.assertFalse(stance_is_playable(neck, st))  # missing controller
        st.set_stance(3, set(), {14, 5})
        self.assertFalse(stance_is_playable(neck, st))  # missing string
        self.assertTrue(stance_is_playable(neck, StudioStep()))


class AudioTests(unittest.TestCase):  # B2 / B4
    def setUp(self):
        self.msgs = []
        self.engine = MidiAudioEngine(send=self.msgs.append)
        self.engine.wait_idle()

    def tearDown(self):
        self.engine.close()

    def test_bend_range_is_set_on_every_channel(self):
        from core.audio import ALL_CHANNELS, BEND_RANGE_SEMITONES

        ccs = {}
        for m in self.msgs:
            if m & 0xF0 == 0xB0:
                ccs.setdefault(m & 0x0F, []).append(((m >> 8) & 0x7F, (m >> 16) & 0x7F))
        for ch in ALL_CHANNELS:
            seq = ccs.get(ch, [])
            i = seq.index((101, 0))
            self.assertEqual(seq[i:i + 6], [(101, 0), (100, 0), (6, int(BEND_RANGE_SEMITONES)), (38, 0),
                                            (101, 127), (100, 127)])
        self.assertTrue(self.engine.glide_string_pitch(5, 3.0))  # C6 P8 / RKR+P1 pulls glide

    def test_stop_drops_queued_notes(self):
        self.msgs.clear()
        for i in range(4):
            self.engine.play_note(60 + i, 5, delay=0.3 + 0.1 * i)
        self.engine.play_click(delay=0.4)
        self.engine.silence_all()
        self.engine.wait_idle()
        import time
        time.sleep(0.8)  # past every queued delay
        ons = [m for m in self.msgs if m & 0xF0 == 0x90]
        self.assertEqual(ons, [])


class AtomicWriteTests(unittest.TestCase):  # B8
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(ProfileManager, "STORAGE_DIR", Path(self._tmp.name) / "profiles")
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_failed_write_keeps_old_file_and_leaves_no_temp(self):
        from core.storage import atomic_write_json

        path = Path(self._tmp.name) / "x.json"
        atomic_write_json(path, {"a": 1})
        with self.assertRaises(TypeError):
            atomic_write_json(path, {"a": object()})  # not serialisable mid-write
        self.assertEqual(path.read_text(encoding="utf-8").replace(" ", "").replace("\n", ""), '{"a":1}')
        self.assertEqual([p.name for p in Path(self._tmp.name).iterdir()], ["x.json"])

    def test_profile_save_round_trip_and_reserved_names(self):
        g = factory_guitar()
        ProfileManager.save_profile("Mine", g)
        self.assertEqual(ProfileManager.list_user_profiles(), ["Mine"])
        self.assertEqual(len(ProfileManager.load_profile("Mine").necks), len(g.necks))
        for bad in ("CON", "nul", "COM1", "lpt9"):
            with self.subTest(name=bad), self.assertRaises(ValueError):
                ProfileManager.save_profile(bad, g)
        self.assertFalse(ProfileManager.profile_exists("CON"))


class FranklinCoreTests(unittest.TestCase):  # B6
    def test_insert_and_remove_renumber_rules(self):
        neck = _neck(U12_HS)
        before = [s.active_midi for s in FretboardResolver.resolve_neck_state(neck, 3, {"P3_HALF", "LKL"})]
        self.assertTrue(set_franklin_p1(neck, True, {5: -1}))
        self.assertTrue(has_franklin_p1(neck))
        self.assertIn("P4", half_stop_controllers(neck))  # P3's half-stop moved with it
        after = [s.active_midi for s in FretboardResolver.resolve_neck_state(neck, 3, {"P4_HALF", "LKL"})]
        self.assertEqual(before, after)
        self.assertFalse(set_franklin_p1(neck, True))  # already there
        self.assertTrue(set_franklin_p1(neck, False))
        self.assertEqual(sorted(neck.pedals), [f"P{i}" for i in range(1, 8)])
        self.assertIn("P3", half_stop_controllers(neck))


class EngineTests(unittest.TestCase):
    def test_classify_movement_uses_roles(self):  # B9
        from core.voicing_solver import VoicingSolver

        neck = _neck("10-String E9 Chromatic")
        self.assertEqual(VoicingSolver.classify_movement(3, [], 5, ["P1", "P2"], neck=neck), "Hold Pedals & Slide")
        set_franklin_p1(neck, True)
        self.assertEqual(VoicingSolver.classify_movement(3, [], 5, ["P2", "P3"], neck=neck), "Hold Pedals & Slide")
        self.assertEqual(VoicingSolver.classify_movement(3, [], 5, ["P1", "P2"], neck=neck), "Position Shift")

    def test_chord_identifier_families_and_ties_resolved_on_c6(self):  # B10
        from core.chord_identifier import ChordIdentifier
        from core.theory import CHORD_FORMULAS

        neck = _neck("10-String C6")
        # Every 4-string grip of the open C6 neck (C-E-G-A family) at every fret: the label must be
        # a CHORD_FORMULAS key and the same reading in every key (the 6 chord, not the m7).
        for fret in range(0, 12):
            states = {s.string_number: s for s in FretboardResolver.resolve_neck_state(neck, fret, set())}
            for grip in ([6, 5, 4, 3], [5, 4, 3, 2], [7, 6, 5, 4]):
                gs = [states[s] for s in grip]
                bass = max(gs, key=lambda s: s.string_number)
                pcs = {s.pitch_class for s in gs}
                if len(pcs) != 4:
                    continue
                tag, family = ChordIdentifier.identify_voicing([s.active_midi for s in gs], bass.active_midi,
                                                               show_inversion=False)
                with self.subTest(fret=fret, grip=grip, tag=tag):
                    self.assertIn(family, CHORD_FORMULAS)
                    self.assertEqual(family, "Major 6th")
        g9 = ChordIdentifier.identify_voicing([55, 59, 62, 65, 69], 43)
        self.assertEqual(g9[1], "Dominant 9th")
        self.assertEqual(ChordIdentifier.identify_voicing([60, 62, 64, 67, 69], 48)[1], "6/9")

    def test_chromatic_e9_grips_sound_their_chords(self):  # B11
        from core.voicing_solver import VoicingSolver

        neck = _neck("10-String E9 Chromatic")
        ab = resolve_stance(neck, ["A", "B"])
        cases = [([9, 8, 6, 5], set(), "Dominant 7th", True), ([9, 6, 5, 4], set(), "Dominant 7th", True),
                 ([9, 6, 5], set(), "Dominant 7th", False), ([7, 6, 5], ab, "Minor", True),
                 ([8, 7, 6, 5], ab, "Minor 7th", True)]
        for grip, ctrls, ctype, need_root in cases:
            root = "E" if not ctrls else "F#"
            with self.subTest(grip=grip):
                self.assertIn(grip, VoicingSolver.get_candidate_grips(neck))
                self.assertTrue(grip_matches_chord(neck, 0, ctrls, grip, root, ctype, require_root=need_root))

    def test_solver_offers_half_stop_stances_on_request(self):  # B13
        from core.voicing_solver import VoicingSolver

        neck = _neck(U12_HS)
        plain = VoicingSolver.candidate_stances(neck)
        with_half = VoicingSolver.candidate_stances(neck, include_half_stops=True)
        self.assertFalse(any(c.endswith("_HALF") for st in plain for c in st))
        halves = {c for st in with_half for c in st if c.endswith("_HALF")}
        self.assertEqual(halves, {"P1_HALF", "P3_HALF", "P7_HALF"})
        found = False
        for ctype in ("Major", "Minor", "Dominant 7th"):
            for root in ("C", "F", "G", "A", "D"):
                for m in VoicingSolver.find_all_voicings(neck, root, ctype, max_fret=7, include_half_stops=True):
                    if any(c.endswith("_HALF") for c in m.engaged_levers):
                        found = True
                        # The solver's promise: every grip note, resolved with the half-stop, is a
                        # chord tone. (It accepts fewer distinct tones than grip_matches_chord.)
                        pcs = grip_pitch_classes(neck, m.fret, m.engaged_levers, m.grip_strings)
                        tones = {(NOTE_TO_SEMITONE[root] + k) % 12 for k in CHORD_FORMULAS[ctype]}
                        self.assertLessEqual(pcs, tones, (root, ctype, m.fret, m.engaged_levers, m.grip_strings))
        self.assertTrue(found)

    def test_progression_searches_each_chord_once_and_random_is_seeded(self):  # B5 / B12
        from core.voice_leader import (ChordProgression, ChordSlot, ProgressionMeasure, VoiceLeadingConstraints,
                                       VoiceLeadingEngine)
        from core.voicing_solver import VoicingSolver

        neck = _neck("10-String E9 Chromatic")
        chords = [("E", "Major"), ("A", "Major"), ("E", "Major"), ("B", "Dominant 7th")] * 3
        prog = ChordProgression(name="blues", measures=[
            ProgressionMeasure(measure_id=i, slots=[ChordSlot(beat=1, root=r, chord_type=t)])
            for i, (r, t) in enumerate(chords)])
        real = VoicingSolver.find_all_voicings
        with mock.patch.object(VoicingSolver, "find_all_voicings", side_effect=real) as spy:
            VoiceLeadingEngine.solve_progression(neck, prog, VoiceLeadingConstraints())
        self.assertLessEqual(spy.call_count, 3 * 3)  # 3 distinct chords (with relaxation retries)
        cons = VoiceLeadingConstraints(trajectory="random")
        a = VoiceLeadingEngine.solve_progression(neck, prog, cons, rng=random.Random(7))
        b = VoiceLeadingEngine.solve_progression(neck, prog, cons, rng=random.Random(7))
        self.assertEqual([(v.fret, v.engaged_levers) for v in a], [(v.fret, v.engaged_levers) for v in b])

    def test_tab_shows_half_stop_names(self):  # B16
        st = StudioStep(root="C", chord_type="Major")
        st.set_stance(3, {"P3_HALF", "LKL"}, {6, 5, 4})
        (ts,) = tab_steps([st], {"LKL": "F lever"})
        self.assertIn("P3½", ts.engaged_levers)
        self.assertNotIn("P3_HALF", " ".join(ts.engaged_levers))


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class FakeAudio:
    def __init__(self):
        self.use_compensated_temperament = False
        self.calls = []

    def glide_string_pitch(self, *a, **k):
        return True

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append((name, a, k))


class AuditWindowTests(unittest.TestCase):
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

    def _window(self, neck_name=None):
        from ui.main_window import MainWindow

        w = MainWindow()
        self.addCleanup(_delete, w)
        if neck_name:
            w._select_copedant_index(next(i for i, n in enumerate(w.guitar.necks) if n.name == neck_name))
        return w

    def _editor(self, w):
        from ui.copedant_editor_dialog import CopedantEditorDialog

        dlg = CopedantEditorDialog(neck=w.guitar.necks[w.current_neck_idx], guitar=w.guitar,
                                   current_neck_idx=w.current_neck_idx, parent=w)
        self.addCleanup(_delete, dlg)
        return dlg

    def test_noop_editor_apply_keeps_captured_half_stop(self):  # B1
        w = self._window(U12_HS)
        st = w.studio  # hidden dock: no voice-leading of the default steps (keeps the test fast)
        w.apply_stance(3, {"P3_HALF", "LKL"}, {6, 5, 4}, play=False)
        st.btn_capture.click()
        cap = st.steps[st.selected]
        self.assertEqual((cap.controllers, cap.pinned), (["LKL", "P3_HALF"], True))
        dlg = self._editor(w)
        dlg._apply_and_close()  # Apply with no edits
        w._on_copedant_modified()
        cap = next(s for s in st.steps if s.pinned and "P3_HALF" in s.controllers)
        self.assertEqual((cap.fret, cap.grip), (3, [4, 5, 6]))

    def test_disabled_rule_drops_half_token(self):  # B3
        w = self._window(U12_HS)
        neck = w.guitar.necks[w.current_neck_idx]
        for h in neck.half_stops:
            if h.controller_id == "P3":
                h.is_active = False
        w._load_current_neck()
        w.apply_stance(3, {"P3_HALF", "LKL"}, {6, 5, 4}, play=False)
        self.assertEqual(w.canvas.engaged_levers, {"LKL"})
        self.assertEqual(w.lever_panel.dropped_half_stops, {"P3"})
        self.assertIn("half-stop", w.statusBar().currentMessage())
        w.apply_stance(3, {"P1_HALF"}, {6, 5, 4}, play=False)  # P1 still has a rule
        self.assertEqual(w.canvas.engaged_levers, {"P1_HALF"})

    def test_lever_without_half_stop_toggles_at_once(self):  # B14
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        w = self._window("10-String E9 Chromatic")
        btn = w.lever_panel.pedal_buttons["P1"]
        self.assertFalse(btn.has_half_stop)
        QTest.mouseClick(btn, Qt.LeftButton)
        self.assertEqual(btn.state, 2)  # no 240 ms wait
        self.assertIn("P1", w.canvas.engaged_levers)
        QTest.mouseClick(btn, Qt.LeftButton)
        self.assertEqual(btn.state, 0)

    def test_franklin_toggle_leaves_no_dialog(self):  # B6
        from PySide6.QtCore import QCoreApplication, QEvent
        from ui.copedant_editor_dialog import CopedantEditorDialog

        w = self._window("10-String C6")
        w._toggle_c6_menu_pedal_offset(True)
        self.assertTrue(has_franklin_p1(w.guitar.necks[w.current_neck_idx]))
        w._toggle_c6_menu_pedal_offset(False)
        self.assertFalse(has_franklin_p1(w.guitar.necks[w.current_neck_idx]))
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertEqual(w.findChildren(CopedantEditorDialog), [])

    def test_editor_tabs_share_half_stops_and_detect_once(self):  # B7
        from ui.copedant_editor_dialog import QMessageBox

        w = self._window("10-String E9 Chromatic")
        dlg = self._editor(w)
        self.assertEqual(dlg.neck.half_stops, [])
        dlg._add_half_stop_rule()  # an LKL row in tab 4, not yet in the model
        dlg.tabs.setCurrentWidget(dlg.tab_splits)
        with mock.patch.object(QMessageBox, "information"):
            dlg._auto_detect_splits()
        combo = dlg.splits_table.cellWidget(0, 1)
        self.assertIn("LKL_HALF", [combo.itemData(i) for i in range(combo.count())])
        dlg.tabs.setCurrentWidget(dlg.tab_half_stops)
        self.assertEqual(dlg.half_stops_table.rowCount(), 1)  # survived the round trip
        with mock.patch.object(QMessageBox, "information"):
            dlg._auto_detect_half_stops()
            rows = dlg.half_stops_table.rowCount()
            self.assertGreater(rows, 0)
            dlg._auto_detect_half_stops()
            self.assertEqual(dlg.half_stops_table.rowCount(), rows)
            dlg._auto_detect_splits()
            split_rows = dlg.splits_table.rowCount()
            dlg._auto_detect_splits()
            self.assertEqual(dlg.splits_table.rowCount(), split_rows)


if __name__ == "__main__":
    unittest.main()
