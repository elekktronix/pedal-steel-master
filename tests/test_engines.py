"""Regression tests for the P1/P2 defect batch (see docs/architecture/06-defect-register.md).

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

from core import presets  # noqa: E402
from core.audio import STRING_CHANNELS, channel_for_string, compute_newman_cents  # noqa: E402
from core.permutation_engine import FRANKLIN_24_PERMUTATIONS, PermutationEngine  # noqa: E402
from core.progression_presets import PROGRESSION_PRESETS, resolve_preset_steps  # noqa: E402
from core.relative_moves import RelativeMovesEngine  # noqa: E402
from core.scale_engine import ScaleSolver  # noqa: E402
from core.stances import detect_roles, grip_matches_chord  # noqa: E402
from core.star_map_engine import StarMapEngine  # noqa: E402
from core.tab_generator import TabGenerator, TabStep  # noqa: E402
from core.theory import CHORD_FORMULAS, NOTE_NAMES_SHARP, get_nashville_chord_symbol, to_root_name  # noqa: E402
from core.voice_leader import (  # noqa: E402
    ChordProgression,
    UnknownChordTypeError,
    VoiceLeadingConstraints,
    VoiceLeadingEngine,
    normalize_chord_type,
)
from core.voicing_solver import VoicingSolver  # noqa: E402

E9_NECKS = [presets.build_standard_emmons_e9_10, presets.build_be_e9_3p_5kl_1hs, presets.build_gfi_12u_7p_5kl]
C6_NECKS = [presets.build_standard_c6_10, presets.build_be_c6_5p_4kl]


class RoleTests(unittest.TestCase):
    def test_roles_by_function(self):  # D-23
        self.assertEqual(detect_roles(presets.build_standard_emmons_e9_10())["A"], "P1")
        self.assertEqual(detect_roles(presets.build_be_e9_3p_5kl_1hs())["BL"], "VL")
        be_c6 = detect_roles(presets.build_be_c6_5p_4kl())
        self.assertEqual((be_c6["C6P6"], be_c6["C6P8"]), ("P3", "P5"))  # IDs P1-P5 labelled P4-P8

    def test_franklin_pedal_chords(self):  # Franklin, "Intervals" p. 12: open-position pedal/lever chords
        from core.chord_identifier import FRANKLIN_GROUPS
        from core.stances import resolve_stance

        claims = [((), "E", "Major", (1, 2, 3, 4)), (("A",), "C#", "Minor", (1, 2, 3, 4)),
                  (("B",), "E", "Sus4", (1, 2, 3, 4)), (("A", "B"), "A", "Major", (1, 2, 3, 4)),
                  (("B", "C"), "F#", "Minor", (1, 2)), (("F",), "F", "Diminished", (1, 2, 3, 4)),
                  (("D",), "G#", "Minor", (1, 2, 3, 4))]
        for build in E9_NECKS[:2]:  # the book's string groups use 10-string numbering
            neck = build()
            for tokens, root, chord, groups in claims:
                ids = set(resolve_stance(neck, list(tokens)))
                for strings, group in FRANKLIN_GROUPS.items():
                    expected = int(group.split()[-1]) in groups
                    ok = grip_matches_chord(neck, 0, ids, set(strings), root, chord, require_root=False)
                    self.assertEqual(ok, expected, f"{neck.name}: {tokens} {group} {root} {chord}")


class ContentCorrectnessTests(unittest.TestCase):
    def test_progression_presets_sound_their_labels(self):  # D-10
        for preset in PROGRESSION_PRESETS:
            builders = E9_NECKS if preset.neck_type == "E9" else C6_NECKS
            self.assertEqual(len(preset.chords), len(preset.steps))
            for build in builders:
                neck = build()
                steps = resolve_preset_steps(preset, neck)
                self.assertIsNotNone(steps, f"{preset.name} on {neck.name}")
                for step, (root, ctype) in zip(steps, preset.chords):
                    with self.subTest(preset=preset.name, neck=neck.name, step=step.chord_label):
                        self.assertTrue(
                            grip_matches_chord(neck, step.fret, step.engaged_levers, step.grip_strings, root, ctype)
                        )

    def test_star_map_landmarks_sound_their_chord(self):  # D-14, D-23
        for build in E9_NECKS + C6_NECKS:
            neck = build()
            for root in ("C", "E", "G", "Bb", "F#"):
                for quality in ("Major", "Minor"):
                    lms = StarMapEngine.calculate_landmarks(root, quality, neck)
                    with self.subTest(neck=neck.name, root=root, quality=quality):
                        self.assertTrue(lms)
                        for lm in lms:
                            self.assertTrue(
                                grip_matches_chord(neck, lm.fret, lm.controllers, lm.target_strings,
                                                   root if root != "F#" else "F#", quality),
                                lm.label,
                            )

    def test_c6_minor_upper_shape_is_minor(self):  # D-14
        neck = presets.build_standard_c6_10()
        labels = {lm.label for lm in StarMapEngine.calculate_minor_anchors("A", neck)}
        self.assertIn("0 (Upper Root)", labels)
        self.assertNotIn("7 (Upper Min)", labels)

    def test_franklin_hub_iii_uses_d_lever(self):  # D-15
        neck = presets.build_standard_emmons_e9_10()
        hub = {o.roman_degree: o for o in RelativeMovesEngine.get_same_fret_diatonic_hub(0, neck)}
        self.assertEqual(hub["iii"].controllers, {"LKR"})
        self.assertEqual(set(hub), {"I", "ii", "iii", "IV", "vi", "#I°", "I 6/9"})

    def test_barndo_moves_use_pedal_function_on_be_c6(self):  # D-23
        moves = RelativeMovesEngine.get_c6_relative_movements(5, presets.build_be_c6_5p_4kl())
        self.assertEqual(len(moves), 5)
        self.assertEqual(moves[0].controllers, {"P3"})  # "Pedal 6" (E -> Eb) is P3 on BE C6

    def test_same_fret_options_carry_chord_type(self):  # D-28
        opts = RelativeMovesEngine.get_all_same_fret_chords(presets.build_standard_emmons_e9_10(), 3, "all")
        self.assertTrue(opts)
        for o in opts:
            self.assertIn(o.chord_type, CHORD_FORMULAS, o.label)
            self.assertTrue(o.chord_root)

    def test_scale_boxes_on_be_c6_use_pedals(self):  # D-23
        boxes = ScaleSolver.find_scale_boxes(presets.build_be_c6_5p_4kl(), "G", "Major (Ionian)")
        used = {c for b in boxes for n in b.ascending_run for c in n.engaged_levers}
        self.assertTrue(boxes)
        self.assertTrue(used & {"P1", "P2", "P3", "P4", "P5"})


class TheoryTests(unittest.TestCase):
    def test_nashville(self):  # D-17
        cases = {
            "C Dominant 7th": "1⁷", "C Augmented": "1+", "C Minor 7th": "1-", "Cm7": "1-",
            "C Maj • Group 2": "1", "C7 • Group 1 [Root Position (1-3-5)]": "1⁷", "Cdim7": "1°",
            "Cm7b5": "1ø", "Csus4": "1sus", "G": "5",
        }
        for label, expected in cases.items():
            with self.subTest(label=label):
                self.assertEqual(get_nashville_chord_symbol(label, "C"), expected)
        self.assertEqual(get_nashville_chord_symbol("G7", "C", family="Dominant 7th"), "5⁷")

    def test_root_respelling(self):  # D-05
        self.assertEqual(to_root_name("Bb"), "A#")
        self.assertEqual(to_root_name("C#", ["C", "Db", "D"]), "Db")
        self.assertIsNone(to_root_name("H"))

    def test_circle_neighbors_for_sharp_keys(self):  # D-18
        neck = presets.build_standard_emmons_e9_10()
        n = VoicingSolver.find_circle_neighbors(neck, "C#", 0, [8, 6, 5])
        roots = {x.chord_name.split()[0] for x in n}
        self.assertTrue(roots & {"F#", "Ab", "G#"}, roots)  # IV = F#, V = Ab/G#
        self.assertNotIn("G", roots)  # would appear if C were (wrongly) used as the key


class VoiceLeaderTests(unittest.TestCase):
    def test_normalize_is_strict(self):  # D-11
        expected = {
            "m7b5": "Half-Diminished", "Half-Diminished": "Half-Diminished", "m6": "Minor 6th",
            "dim7": "Diminished 7th", "aug": "Augmented", "sus4": "Sus4", "9": "Dominant 9th",
            "Minor 7": "Minor 7th", "7": "Dominant 7th", "m": "Minor", "M7": "Major 7th",
        }
        for raw, norm in expected.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_chord_type(raw), norm)
        with self.assertRaises(UnknownChordTypeError):
            normalize_chord_type("weird13#11")

    def test_results_align_with_measures(self):  # D-12
        prog = ChordProgression.from_dict({"measures": [
            {"id": 0, "slots": [{"beat": 1, "chord": {"root": "C", "type": "Major"}}]},
            {"id": 1, "slots": [{"beat": 1}]},
            {"id": 2, "slots": [{"beat": 1, "chord": {"root": "X", "type": "Major"}}]},
            {"id": 3, "slots": [{"beat": 1, "chord": {"root": "G", "type": "Major"}}]},
        ]})
        res = VoiceLeadingEngine.solve_progression(
            presets.build_standard_emmons_e9_10(), prog, VoiceLeadingConstraints(max_fret=12)
        )
        self.assertEqual(len(res), 4)
        self.assertIsNotNone(res[0])
        self.assertIsNone(res[1])
        self.assertIsNone(res[2])
        self.assertIsNotNone(res[3])


class PracticeEngineTests(unittest.TestCase):
    def test_permutations_unique_and_thumb_on_bass(self):  # D-13, D-36
        orders = [v[3] for v in FRANKLIN_24_PERMUTATIONS.values()]
        self.assertEqual(len(set(orders)), 24)
        self.assertTrue(all(sorted(o) == [0, 1, 2, 3] for o in orders))  # every string once
        events = PermutationEngine.generate_sequence(2, [8, 6, 5, 4], cycles=1)  # #2: T-I-M-T
        self.assertEqual([(e.finger, e.string_number) for e in events], [("T", 6), ("I", 5), ("M", 4), ("T", 8)])
        self.assertEqual(PermutationEngine.generate_sequence(2, [], cycles=1), [])

    def test_permutations_match_franklin_chart(self):  # D-36: Intervals p. 38, open E9 strings 8-7-6-5
        from core.resolver import FretboardResolver

        chart = {
            1: "E F# G# B", 2: "F# G# B E", 3: "G# B E F#", 4: "B E F# G#", 5: "B G# F# E", 6: "G# F# E B",
            7: "F# E B G#", 8: "E B G# F#", 9: "B F# G# E", 10: "F# G# E B", 11: "G# E B F#", 12: "E B F# G#",
            13: "F# B E G#", 14: "B E G# F#", 15: "E G# F# B", 16: "G# F# B E", 17: "B G# E F#", 18: "G# E F# B",
            19: "E F# B G#", 20: "F# B G# E", 21: "E G# B F#", 22: "G# B F# E", 23: "B F# E G#", 24: "F# E G# B",
        }
        neck = presets.build_standard_emmons_e9_10()
        names = {s.string_number: s.active_note_name.rstrip("0123456789")
                 for s in FretboardResolver.resolve_neck_state(neck, 0, set())}
        for pid, notes in chart.items():
            events = PermutationEngine.generate_sequence(pid, [5, 6, 7, 8], cycles=1)
            self.assertEqual(" ".join(names[e.string_number] for e in events), notes, f"permutation #{pid}")
        fingers = {pid: "".join(v[2]) for pid, v in FRANKLIN_24_PERMUTATIONS.items()}
        self.assertEqual((fingers[18], fingers[20], fingers[21], fingers[23]), ("MTIM", "TMIT", "TIMT", "MITM"))

    def test_tab_columns_align(self):  # D-16
        txt = TabGenerator.generate_ascii_tab(10, [TabStep(3, [], {8, 6, 5}, "G"), TabStep(12, ["P1"], {8}, "C")])
        lines = [ln for ln in txt.splitlines() if ln]
        widths = {len(ln.rstrip()) for ln in lines if ln.lstrip()[:2].strip().isdigit()}
        self.assertEqual(len(widths), 1)  # every string row has the same width
        header = lines[0]
        row8 = next(ln for ln in lines if ln.startswith(" 8 |"))
        prefix = len("Chord: ")
        self.assertEqual(header.index("C", prefix), row8.index("12") - 1)  # 2nd column starts at the same offset


class AudioTests(unittest.TestCase):
    def test_channel_map_skips_drums(self):  # D-01
        chans = [channel_for_string(s) for s in range(1, 15)]
        self.assertNotIn(9, chans)
        self.assertEqual(len(set(chans)), 14)
        self.assertNotIn(9, STRING_CHANNELS)

    def test_newman_cents(self):  # D-19
        e9 = presets.build_standard_emmons_e9_10()
        cents = compute_newman_cents(e9, {"P1"}, [5, 4, 10])
        self.assertEqual(cents, {5: -6.0, 4: 10.0, 10: -6.0})
        self.assertEqual(compute_newman_cents(presets.build_standard_c6_10(), set(), [1]), {})


# ---------------------------------------------------------------------------
# MainWindow integration (offscreen, fake audio, temp storage)
# ---------------------------------------------------------------------------
try:
    from PySide6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
    HAVE_QT = True
except Exception:  # pragma: no cover
    HAVE_QT = False


class FakeAudio:
    def __init__(self):
        self.use_compensated_temperament = False
        self.calls = []

    def set_compensated_temperament(self, enabled):
        self.use_compensated_temperament = enabled

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append((name, a, k))


@unittest.skipUnless(HAVE_QT, "PySide6 not available")
class MainWindowTests(unittest.TestCase):
    def setUp(self):
        from core.profile_manager import ProfileManager
        import core.session as session
        import core.settings as settings

        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(session, "SESSION_FILE", tmp / "session.json"),
            mock.patch.object(ProfileManager, "STORAGE_DIR", tmp / "profiles"),
            mock.patch.object(settings, "SETTINGS_FILE", tmp / "app_settings.json"),
            mock.patch.object(settings, "LEGACY_SETTINGS_FILE", tmp / "legacy.json"),
            mock.patch.object(settings, "SETTINGS_DIR", tmp),
            mock.patch("ui.main_window.MidiAudioEngine", FakeAudio),
        ]
        for p in self._patches:
            p.start()
        from ui.main_window import MainWindow

        self.w = MainWindow()

    def tearDown(self):
        from PySide6.QtCore import QCoreApplication, QEvent

        self.w.close()
        self.w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)  # really free the window
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()

    def test_apply_stance_syncs_lever_panel(self):  # D-03
        w = self.w
        w.apply_stance(3, {"P1", "LKL"}, {6, 5, 4}, play=False)
        self.assertEqual(w.lever_panel.active_controllers, {"P1", "LKL"})
        self.assertEqual(w.lever_panel.pedal_buttons["P1"].state, 2)
        # A manual click afterwards must add to the applied stance, not replace it.
        w.lever_panel.pedal_buttons["P2"]._set_state(2)
        self.assertEqual(w.canvas.engaged_levers, {"P1", "LKL", "P2"})
        self.assertEqual(w.lever_panel.active_controllers, {"P1", "LKL", "P2"})

    def test_badge_shows_clash_reason(self):  # D-25
        w = self.w
        w.apply_stance(0, {"LKL", "LKR"}, play=False)
        self.assertIn("Left knee clash", w.lever_panel.lbl_feasibility_badge.text())

    def test_flat_root_in_up_neck_dropdown_sticks(self):  # D-05 (spelling follows Preferences > Note Spelling)
        from core.theory import set_accidental_preference

        w = self.w
        self.addCleanup(set_accidental_preference, "sharps")
        with mock.patch("ui.main_window.save_settings"):
            w._set_note_spelling("flats")
        idx = w.combo_up_neck_chord.findText("Bb Major")
        self.assertGreaterEqual(idx, 0)
        w.combo_up_neck_chord.setCurrentIndex(idx)
        self.assertEqual(w.combo_up_neck_chord.currentText(), "Bb Major")
        self.assertEqual(w.harmonic_panel.get_root(), "Bb")
        with mock.patch("ui.main_window.save_settings"):
            w._set_note_spelling("sharps")
        self.assertEqual(w.combo_up_neck_chord.currentText(), "A# Major")  # selection kept, respelled
        self.assertEqual(w.harmonic_panel.get_root(), "A#")

    def test_none_root_clears_analysis(self):  # D-27
        w = self.w
        w.harmonic_panel.combo_root.setCurrentText("None")
        self.assertIsNone(w.canvas.target_root)

    def test_play_pocket_uses_string_numbers(self):  # D-01
        w = self.w
        w.apply_stance(0, set(), {8, 6, 5}, play=False)
        w.audio.calls.clear()
        w._play_pocket()
        name, args, kwargs = w.audio.calls[-1]
        self.assertEqual(name, "play_pocket")
        self.assertEqual(set(args[0]), {8, 6, 5})

    def test_all_button_respects_string_count(self):  # D-24
        w = self.w
        w.lever_panel.all_strings_requested.emit()
        self.assertEqual(w.canvas.active_pocket, set(range(1, 11)))


if __name__ == "__main__":
    unittest.main()
