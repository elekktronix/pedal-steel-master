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

    def play_note(self, pitch, string_num=None, velocity=95, cents_offset=0.0, delay=0.0):
        self.calls.append(("note", string_num, pitch) if not delay else ("note", string_num, pitch, delay))

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

    def test_scale_finder_draws_numbered_scale_map(self):  # E-30
        import core.settings as settings

        w = self._window()
        sf, canvas = w.scale_finder, w.canvas
        self.assertEqual(canvas.scale_overlay, [])  # nothing drawn while the finder is hidden
        pocket = set(canvas.active_pocket)

        sf.show()
        sf.set_fret_range(5, 8)
        self.assertEqual((canvas.target_root, canvas.target_scale), ("G", "Major (Ionian)"))
        self.assertEqual(canvas.box_highlight_range, (5, 8))
        run = sf.active_box.ascending_run
        self.assertTrue(run)
        self.assertTrue(all(5 <= n.fret <= 8 for n, _ in canvas.scale_overlay))
        self.assertEqual(sorted(s for _, s in canvas.scale_overlay if s is not None), list(range(len(run))))

        sf.select_step(2)
        self.assertEqual(canvas.overlay_active_step, 2)
        self.assertEqual(canvas.bar_fret, run[2].fret)
        self.assertEqual(canvas.engaged_levers, set(run[2].engaged_levers))
        self.assertEqual(canvas.active_pocket, pocket)  # stepping no longer narrows the pocket

        # Clicking a numbered circle jumps to its step.
        canvas.resize(1200, 400)
        board_w = canvas.width() - canvas.left_margin - canvas.right_margin
        board_h = canvas.height() - canvas.top_margin - canvas.bottom_margin
        geo = list(canvas._overlay_geometry(board_w / canvas.num_frets, board_h / (canvas.neck.string_count - 1)))
        x, y, _, note, step = next(g for g in geo if g[4] == 4)
        self.assertIs(canvas._overlay_hit(x, y)[0], note)
        canvas.overlay_step_clicked.emit(step)  # what mousePressEvent emits for that hit
        self.assertEqual(sf.active_step_idx, 4)

        degree_btn = next(b for b in sf.label_group.buttons() if b.property("mode") == "degree")
        degree_btn.setChecked(True)
        self.assertEqual(canvas.overlay_label_mode, "degree")
        self.assertEqual(settings.load_settings()["scale_overlay_label"], "degree")

        # Phase 2: order options, role names, change column, tempo.
        self.assertEqual(sf.table_staircase.rowCount(), len(run))
        self.assertEqual(sf.table_staircase.item(0, 6).text(), "Start")
        self.assertNotIn("P1", " ".join(sf.table_staircase.item(r, 5).text() for r in range(len(run))))
        sf.direction_combo.setCurrentIndex(sf.direction_combo.findData("updown"))
        self.assertEqual(len(sf.run), 2 * len(run) - 1)
        self.assertEqual(len(canvas.overlay_run), len(sf.run))
        sf.select_step(len(run))  # first step on the way back down
        self.assertIs(canvas.overlay_run[canvas.overlay_active_step], run[-2])
        sf.direction_combo.setCurrentIndex(sf.direction_combo.findData("down"))
        self.assertEqual([n.midi_note for n in sf.run], sorted((n.midi_note for n in run), reverse=True))
        sf.spin_tempo.setValue(120)
        self.assertEqual(sf._walk_interval_ms(), 500)

        sf.hide()
        self.assertEqual(canvas.scale_overlay, [])
        self.assertIsNone(canvas.box_highlight_range)

    def test_scale_finder_learning_aids(self):  # E-30 phase 3
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest

        from core.resolver import FretboardResolver

        w = self._window()
        sf, canvas = w.scale_finder, w.canvas
        sf.show()
        sf.set_fret_range(3, 6)
        run = sf.run

        # Degree legend: one chip per scale degree.
        self.assertEqual(sf.degree_legend_layout.count(), 7)

        # Whole neck: faint notes only outside the range, each one resolving to its pitch.
        sf.cb_whole_neck.setChecked(True)
        self.assertTrue(canvas.scale_ghost)
        self.assertTrue(all(not (3 <= n.fret <= 6) for n in canvas.scale_ghost))
        for n in canvas.scale_ghost[::7]:
            st = next(s for s in FretboardResolver.resolve_neck_state(canvas.neck, n.fret, set(n.engaged_levers))
                      if s.string_number == n.string_number)
            self.assertEqual(st.active_midi, n.midi_note)
        sf.cb_whole_neck.setChecked(False)
        self.assertEqual(canvas.scale_ghost, [])

        # Loop steps 3..5: transport wraps inside the loop, the canvas fades the rest.
        sf.set_loop(3, 5)
        self.assertEqual(sf.loop_bounds(), (2, 4))
        self.assertEqual(canvas.overlay_loop_ids, {id(n) for n in run[2:5]})
        seen = []
        for _ in range(4):
            sf.next_step()
            seen.append(sf.active_step_idx)
        self.assertEqual(seen, [2, 3, 4, 2])
        # Play Run plays the loop one note per beat, lights each circle, and can be stopped.
        w.audio.calls.clear()
        sf._play_box_run()
        self.assertTrue(sf.is_playing_run)
        self.assertIn("Stop", sf.btn_play_run.text())
        sf._play_tick()
        sf._play_tick()
        self.assertEqual(canvas.overlay_active_step, 4)
        played = [c[2] for c in w.audio.calls if c[0] == "note"]
        self.assertEqual(played, [n.midi_note for n in run[2:5]])
        sf._play_tick()  # past the end: stops by itself
        self.assertFalse(sf.is_playing_run)
        self.assertIn("Play", sf.btn_play_run.text())
        sf._play_box_run()
        sf._play_box_run()  # second click = Stop Run
        self.assertFalse(sf.is_playing_run)
        self.assertEqual(canvas.overlay_active_step, sf.active_step_idx)

        # Quiz, find the degree: circles go blank, the list hides, answers are scored.
        sf._rng.seed(3)
        sf.quiz_combo.setCurrentIndex(sf.quiz_combo.findData("name"))
        self.assertTrue(canvas.overlay_quiz)
        self.assertTrue(sf.table_staircase.isHidden())
        target = sf.quiz_target
        self.assertIn(target, run[2:5])
        wrong = next(n for n in sf._overlay_notes if n.degree_label != target.degree_label)
        sf.answer_quiz(wrong)
        self.assertEqual(canvas.overlay_wrong, id(wrong))
        self.assertEqual((sf.quiz_correct, sf.quiz_attempts), (0, 1))

        # A real click on a matching circle (any octave of the degree counts).
        canvas.resize(1200, 400)
        board_w = canvas.width() - canvas.left_margin - canvas.right_margin
        board_h = canvas.height() - canvas.top_margin - canvas.bottom_margin
        geo = canvas._overlay_geometry(board_w / canvas.num_frets, board_h / (canvas.neck.string_count - 1))
        x, y, _, right, _ = next(g for g in geo if g[3].degree_label == target.degree_label)
        QTest.mouseClick(canvas, Qt.LeftButton, Qt.NoModifier, QPoint(int(x), int(y)))
        self.assertEqual((sf.quiz_correct, sf.quiz_attempts, sf.quiz_streak), (1, 2, 1))
        self.assertEqual(canvas.overlay_revealed,
                         {id(n) for n in sf._overlay_notes if n.degree_label == target.degree_label})
        self.assertTrue(sf.quiz_timer.isActive())
        sf.answer_quiz(right)  # ignored while waiting for the next question
        self.assertEqual(sf.quiz_attempts, 2)
        sf.quiz_timer.stop()
        sf._next_question()
        self.assertNotEqual(sf.quiz_target.degree_label, target.degree_label)
        self.assertEqual(canvas.overlay_revealed, set())

        # Quiz by ear: the target is played and only that exact pitch is right.
        w.audio.calls.clear()
        sf.quiz_combo.setCurrentIndex(sf.quiz_combo.findData("ear"))
        target = sf.quiz_target
        self.assertIn(("note", None, target.midi_note), w.audio.calls)
        octave = next((n for n in sf._overlay_notes
                       if n.degree_label == target.degree_label and n.midi_note != target.midi_note), None)
        if octave:
            sf.answer_quiz(octave)
            self.assertEqual(sf.quiz_correct, 0)
        sf.answer_quiz(target)
        self.assertEqual(sf.quiz_correct, 1)

        sf.hide()  # ends the quiz and clears the fretboard
        self.assertEqual(sf.quiz_mode, "off")
        self.assertFalse(canvas.overlay_quiz)
        self.assertEqual(canvas.scale_overlay, [])
        self.assertTrue(sf.btn_next.isEnabled())

    def test_scale_chord_link(self):  # E-31
        from core.resolver import FretboardResolver
        from core.stances import grip_matches_chord
        from core.theory import NOTE_TO_SEMITONE

        w = self._window()
        sf, canvas = w.scale_finder, w.canvas
        sf.show()
        sf.set_fret_range(3, 6)  # G major
        self.assertEqual(sf.triad_layout.count(), 7)
        self.assertEqual(sf.seventh_layout.count(), 7)
        for lay in (sf.triad_layout, sf.seventh_layout):  # no stale widgets left visible after a rebuild
            self.assertTrue(all(lay.itemAt(i).widget().parent() is not None for i in range(lay.count())))

        # Scale -> chord: ii (Am) rings A, C, E; every ringed circle really sounds a chord tone.
        self.assertTrue(sf.select_chord("A", "Minor"))
        am = {NOTE_TO_SEMITONE[n] for n in ("A", "C", "E")}
        self.assertEqual(canvas.overlay_chord_pcs, am)
        ringed = [n for n, _ in canvas.scale_overlay if n.midi_note % 12 in am]
        self.assertTrue(ringed)
        for n in ringed:
            st = next(s for s in FretboardResolver.resolve_neck_state(canvas.neck, n.fret, set(n.engaged_levers))
                      if s.string_number == n.string_number)
            self.assertIn(st.pitch_class, am)

        # ... and Find voicings opens the Chord Atlas on Am in the same frets.
        sf.btn_find_chord.click()
        dlg = w._atlas_dlg
        self.assertEqual((dlg.combo_find_root.currentText(), dlg.combo_find_type.currentText()), ("A", "Minor"))
        self.assertEqual((dlg.spin_min_fret.value(), dlg.spin_max_fret.value()), (3, 6))
        self.assertTrue(dlg.positions)
        self.assertTrue(all(3 <= p.fret <= 6 for p in dlg.positions))
        for p in dlg.positions[:10]:
            self.assertTrue(grip_matches_chord(canvas.neck, p.fret, p.sighting.controllers, p.sighting.strings,
                                               "A", "Minor", require_root=False))

        # Chord -> scale: "Scales that fit" lists G Mixolydian for G7 and opens it around the voicing.
        dlg.set_find_target("G", "Dominant 7th")
        dlg.set_find_fret_range(0, 15)
        dlg.table_pos.selectRow(0)
        fret = dlg.positions[0].fret
        dlg._fill_scales_menu()
        actions = {a.text().split("   ")[0]: a for a in dlg.scales_menu.actions() if a.isEnabled() and a.text()}
        self.assertIn("G Mixolydian (Dominant)", actions)
        self.assertIn("C Major (Ionian)", actions)
        sf.hide()
        actions["G Mixolydian (Dominant)"].trigger()
        self.assertTrue(sf.isVisible())
        self.assertEqual((sf.root_combo.currentText(), sf.scale_combo.currentText()), ("G", "Mixolydian (Dominant)"))
        lo = max(0, min(21, fret - 1))
        self.assertEqual((sf.spin_from.value(), sf.spin_to.value()), (lo, lo + 3))
        self.assertEqual((sf.selected_chord.symbol, sf.selected_chord.numeral), ("G7", "I7"))
        self.assertEqual(canvas.overlay_chord_pcs, {7, 11, 2, 5})

        # Clicking the selected chord again clears the rings.
        btn = next(b for b in sf.chord_group.buttons() if b.isChecked())
        btn.click()
        self.assertIsNone(sf.selected_chord)
        self.assertEqual(canvas.overlay_chord_pcs, set())

    def _studio_window(self):
        w = self._window()
        w.show()
        w.dock_studio.show()
        st = w.studio
        st.combo_count_in.setCurrentIndex(st.combo_count_in.findData(0))
        st.combo_click.setCurrentText("Woodblock")
        return w, st

    def test_studio_starts_on_beat_one_and_keeps_time(self):  # E-32, D-43, D-44
        import time as _time
        from PySide6.QtCore import QEventLoop, Qt, QTimer

        w, st = self._studio_window()
        st.load_cadence("country")
        self.assertTrue(all(s.has_stance for s in st.steps))
        w.audio.calls.clear()
        st.play()
        first = st.steps[0]
        # Beat 1 happens on the click of Play: stance on the fretboard, click and chord queued together.
        self.assertEqual((w.canvas.bar_fret, w.canvas.engaged_levers, w.canvas.active_pocket),
                         (first.fret, set(first.controllers), set(first.grip)))
        self.assertEqual([c[0] for c in w.audio.calls[:2]], ["play_click", "play_pocket"])
        self.assertTrue(w.audio.calls[0][2]["accent"])
        self.assertEqual(st.beat_timer.timerType(), Qt.PreciseTimer)
        st.stop()
        self.assertIn("silence_all", [c[0] for c in w.audio.calls])

        # Real timing at 300 BPM: every click lands on the beat grid (no CoarseTimer drift).
        st.spin_bpm.setValue(300)
        clicks = []
        st.click_requested.connect(lambda *_: clicks.append(_time.perf_counter()))
        st.play()
        loop = QEventLoop()
        QTimer.singleShot(200 * 9 + 60, loop.quit)
        loop.exec()
        st.stop()
        self.assertGreaterEqual(len(clicks), 9)
        errors = [abs((t - clicks[0]) - k * 0.2) for k, t in enumerate(clicks)]
        self.assertLess(max(errors), 0.025, errors)

    def test_studio_count_in_loop_range_and_end(self):  # E-32
        w, st = self._studio_window()
        st.load_cadence("country")  # 4 bars of 4/4
        st.combo_count_in.setCurrentIndex(st.combo_count_in.findData(1))
        st.cb_loop.setChecked(False)
        fret_before = w.canvas.bar_fret
        st.play()
        st.beat_timer.stop()
        for _ in range(3):  # count-in beats 2-4: nothing applied yet
            st._on_beat()
            st.beat_timer.stop()
            self.assertIsNone(st.playing_idx)
        self.assertEqual(w.canvas.bar_fret, fret_before)
        st._on_beat()
        st.beat_timer.stop()
        self.assertEqual(st.playing_idx, 0)
        for _ in range(16):
            st._on_beat()
            st.beat_timer.stop()
        self.assertFalse(st.is_playing)  # stopped at the end of bar 4 (no loop)

        st.cb_loop.setChecked(True)
        st.spin_loop_from.setValue(2)
        st.spin_loop_to.setValue(3)
        st.combo_count_in.setCurrentIndex(st.combo_count_in.findData(0))
        st.play()
        played = [st.playing_idx]
        for _ in range(12):
            st.beat_timer.stop()
            st._on_beat()
            played.append(st.playing_idx)
        st.stop()
        self.assertEqual(played[0], 1)
        self.assertEqual(played[::4], [1, 2, 1, 2])

    def test_studio_editing_capture_neck_switch_and_files(self):  # E-32, D-45
        from core.stances import grip_matches_chord

        w, st = self._studio_window()
        neck = w.guitar.necks[w.current_neck_idx]

        # Typed chords; every step is voiced and sounds its chord.
        st.edit_chords.setText("| Am7 D7 | Gmaj7 |")
        st._apply_text()
        self.assertEqual([(s.symbol, s.beats) for s in st.steps], [("Am7", 2), ("D7", 2), ("Gmaj7", 4)])
        for s in st.steps:
            self.assertTrue(grip_matches_chord(neck, s.fret, s.controllers, s.grip, s.root, s.chord_type,
                                               require_root=False), s.symbol)

        # Editing a chord re-voices that step for the new chord (no stale voicing).
        st.select_step(2, audition=False)
        st.combo_type.setCurrentText("Minor")
        s = st.steps[2]
        self.assertEqual(s.symbol, "Gm")
        self.assertTrue(grip_matches_chord(neck, s.fret, s.controllers, s.grip, "G", "Minor", require_root=False))

        # Capture the fretboard: C (A+B at fret 3) becomes a pinned step after the selection.
        w.apply_stance(3, {"P1", "P2"}, {8, 6, 5}, play=False)
        st.btn_capture.click()
        cap = st.steps[3]
        self.assertEqual((cap.symbol, cap.fret, cap.controllers, cap.pinned), ("C", 3, ["P1", "P2"], True))
        st.select_step(0, audition=False)
        st.btn_use_stance.click()  # Am7 with C-E-G: a rootless Am7, so it is accepted as is
        self.assertTrue(st.steps[0].pinned)
        self.assertNotIn("doesn't sound", st.lbl_status.text())
        st.select_step(1, audition=False)
        st.btn_use_stance.click()  # D7 with C-E-G: kept (pinned) but flagged
        self.assertTrue(st.steps[1].pinned)
        self.assertIn("doesn't sound D7", st.lbl_status.text())

        # Circle of fifths auto-add appends a pinned step.
        w._on_circle_chord_triggered("G", "Major", True)
        self.assertEqual((st.steps[-1].symbol, st.steps[-1].pinned), ("G", True))

        # Arpeggio: the notes are queued with growing delays on their own strings.
        st.select_step(3, audition=False)
        st.combo_style.setCurrentIndex(st.combo_style.findData("arpeggio"))
        w.audio.calls.clear()
        st.select_step(3, audition=True)
        delays = [c[3] for c in w.audio.calls if c[0] == "note" and len(c) == 4]
        self.assertTrue(delays and delays == sorted(delays))
        self.assertIn("A+B", st.tab_text())

        # Save and load keep chords, beats, stances, pins and styles.
        path = str(Path(self._tmp.name) / "prog.cp")
        st.save_file(path)
        saved = [x.to_dict() for x in st.steps]
        st._clear_steps()
        st.load_file(path)
        self.assertEqual([x.to_dict() for x in st.steps], saved)

        # Another neck: stances are re-voiced with that neck's controllers, never replayed.
        c6_idx = next(i for i, n in enumerate(w.guitar.necks) if n.name == "10-String C6")
        w._select_copedant_index(c6_idx)
        c6 = w.guitar.necks[c6_idx]
        for s in st.steps:
            if s.has_chord and s.has_stance:
                self.assertTrue(set(s.controllers) <= set(c6.pedals) | set(c6.knee_levers))
                self.assertTrue(grip_matches_chord(c6, s.fret, s.controllers, s.grip, s.root, s.chord_type,
                                                   require_root=False), s.symbol)
        symbols = [s.symbol for s in st.steps]

        # The progression survives a restart (session).
        destroy_window(w)
        w2 = self._window()
        self.assertEqual([s.symbol for s in w2.studio.steps], symbols)
        self.assertTrue(all(s.has_stance for s in w2.studio.steps if s.has_chord))

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
