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

    def test_scale_in_user_range_resolves(self):  # E-30
        from core.resolver import FretboardResolver
        from core.theory import NOTE_TO_SEMITONE, SCALE_FORMULAS

        for build in E9_NECKS + C6_NECKS:
            neck = build()
            box = ScaleSolver.find_scale_in_range(neck, "G", "Major (Ionian)", 6, 3)  # swapped on purpose
            self.assertEqual((box.min_fret, box.max_fret), (3, 6), neck.name)
            self.assertEqual(set(box.covered_degrees), set(SCALE_FORMULAS["Major (Ionian)"].values()), neck.name)
            notes = [n for ns in box.notes_by_string.values() for n in ns]
            self.assertEqual(len(notes), box.total_notes)
            for n in notes:
                self.assertTrue(3 <= n.fret <= 6)
                st = next(s for s in FretboardResolver.resolve_neck_state(neck, n.fret, set(n.engaged_levers))
                          if s.string_number == n.string_number)
                self.assertEqual(st.active_midi, n.midi_note, (neck.name, n))
                interval = (st.active_midi - NOTE_TO_SEMITONE["G"]) % 12
                self.assertEqual(SCALE_FORMULAS["Major (Ionian)"][interval], n.degree_label)
                self.assertEqual(n.is_root, interval == 0)
            run = [n.midi_note for n in box.ascending_run]
            self.assertEqual(run, sorted(set(run)))
            self.assertTrue(all(any(r is n for n in notes) for r in box.ascending_run))
        self.assertIsNone(ScaleSolver.find_scale_in_range(neck, "G", "Nope", 3, 6))

    def test_scale_run_is_playable_path(self):  # E-30 phase 2
        def greedy(notes):  # the pre-E-30 order: lowest pitch first, bass strings preferred
            out, last = [], -1
            for n in sorted(notes, key=lambda n: (n.midi_note, -n.string_number, len(n.engaged_levers))):
                if n.midi_note > last:
                    out.append(n)
                    last = n.midi_note
            return out

        for build in E9_NECKS + C6_NECKS:
            neck = build()
            for scale in ("Major (Ionian)", "Minor Pentatonic", "Dorian"):
                for lo, hi in ((3, 6), (5, 9), (10, 13)):
                    box = ScaleSolver.find_scale_in_range(neck, "A", scale, lo, hi)
                    notes = [n for ns in box.notes_by_string.values() for n in ns]
                    run = box.ascending_run
                    self.assertEqual([n.midi_note for n in run], sorted({n.midi_note for n in notes}))
                    self.assertLessEqual(ScaleSolver.run_cost(run), ScaleSolver.run_cost(greedy(notes)) + 1e-9,
                                         (neck.name, scale, lo, hi))

        box = ScaleSolver.find_scale_in_range(presets.build_standard_emmons_e9_10(), "G", "Major (Ionian)", 3, 6)
        up = box.ascending_run
        self.assertEqual(ScaleSolver.build_run(box, ScaleSolver.RUN_DOWN), up[::-1])
        both = ScaleSolver.build_run(box, ScaleSolver.RUN_UP_DOWN)
        self.assertEqual(len(both), 2 * len(up) - 1)  # the top note is not repeated
        self.assertIs(both[len(up) - 1], up[-1])
        r2r = ScaleSolver.build_run(box, root_to_root=True)
        self.assertTrue(r2r[0].is_root and r2r[-1].is_root)
        self.assertLess(len(r2r), len(up))

    def test_scale_chord_theory(self):  # E-31
        from core.scale_chords import chords_in_scale, scales_for_chord
        from core.theory import CHORD_FORMULAS, NOTE_TO_SEMITONE, SCALE_FORMULAS

        triads = [(c.numeral, c.symbol) for c in chords_in_scale("G", "Major (Ionian)", sevenths=False)]
        self.assertEqual(triads, [("I", "G"), ("ii", "Am"), ("iii", "Bm"), ("IV", "C"), ("V", "D"),
                                  ("vi", "Em"), ("vii°", "F#dim")])
        sevenths = [c.numeral for c in chords_in_scale("G", "Major (Ionian)", sevenths=True)]
        self.assertEqual(sevenths, ["Imaj7", "ii7", "iii7", "IVmaj7", "V7", "vi7", "viiø7"])
        self.assertEqual([c.symbol for c in chords_in_scale("A", "Minor Pentatonic")], ["Am", "Am7", "C"])
        for root in ("C", "F#", "Bb"):
            for scale, formula in SCALE_FORMULAS.items():
                spcs = {(NOTE_TO_SEMITONE[root] + k) % 12 for k in formula}
                for c in chords_in_scale(root, scale):
                    self.assertLessEqual(c.pcs, spcs, (root, scale, c.symbol))
                    self.assertEqual(c.pcs, {(c.root_pc + k) % 12 for k in CHORD_FORMULAS[c.chord_type]})

        fits = scales_for_chord("G", "Dominant 7th")
        self.assertEqual((fits[0].root_name, fits[0].scale_name), ("G", "Mixolydian (Dominant)"))
        names = {(f.root_name, f.scale_name): f.chord_degree for f in fits}
        self.assertEqual(names[("C", "Major (Ionian)")], "5")
        self.assertEqual(names[("D", "Dorian")], "4")
        self.assertNotIn(("G", "Major (Ionian)"), names)  # F# is not the b7
        g7 = {7, 11, 2, 5}
        for f in fits:
            spcs = {(NOTE_TO_SEMITONE[f.root_name] + k) % 12 for k in SCALE_FORMULAS[f.scale_name]}
            self.assertLessEqual(g7, spcs)
        self.assertEqual(scales_for_chord("G", "Nope"), [])

    def test_controller_display_names(self):  # E-30 phase 2
        from core.stances import controller_display_names, describe_controllers

        e9 = controller_display_names(presets.build_standard_emmons_e9_10())
        self.assertEqual((e9["P1"], e9["P2"], e9["LKL"]), ("A", "B", "F lever"))
        self.assertEqual(describe_controllers(["LKL", "P1"], e9), "A + F lever")
        self.assertEqual(describe_controllers([], e9), "Open")
        self.assertEqual(describe_controllers(["P3_HALF"], e9), "C (half)")
        be_c6 = controller_display_names(presets.build_be_c6_5p_4kl())
        self.assertEqual([be_c6[f"P{i}"] for i in range(1, 6)], ["P4", "P5", "P6", "P7", "P8"])
        self.assertNotIn("lever", " ".join(controller_display_names(presets.build_standard_c6_10()).values()))


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

    def test_seventh_chords_fall_back_to_the_full_chord(self):  # D-47
        neck = presets.build_standard_emmons_e9_10()
        prog = ChordProgression.from_dict({"measures": [
            {"id": 0, "slots": [{"beat": 1, "chord": {"root": "G", "type": "Major 7th"}}]}]})
        v = VoiceLeadingEngine.solve_progression(neck, prog, VoiceLeadingConstraints(max_fret=12))[0]
        self.assertIsNotNone(v)
        self.assertTrue(grip_matches_chord(neck, v.fret, v.engaged_levers, v.grip_strings, "G", "Major 7th",
                                           require_root=False))


class ProgressionStudioTests(unittest.TestCase):  # E-32
    def test_chord_text(self):
        from core.progression_studio import format_progression_text, parse_chord_symbol, parse_progression_text

        cases = {"Am7": ("A", "Minor 7th"), "F#m7b5": ("F#", "Half-Diminished"), "Bbmaj7": ("Bb", "Major 7th"),
                 "C+": ("C", "Augmented"), "Edim7": ("E", "Diminished 7th"), "G/B": ("G", "Major"),
                 "C6/9": ("C", "6/9"), "Dsus4": ("D", "Sus4"), "E7#9": ("E", "Dominant 7#9"), "cm": ("C", "Minor"),
                 "GΔ7": ("G", "Major 7th"), "Bø7": ("B", "Half-Diminished")}
        for text, want in cases.items():
            self.assertEqual(parse_chord_symbol(text), want, text)
        for bad in ("H7", "Gweird", ""):
            with self.assertRaises(ValueError):
                parse_chord_symbol(bad)

        steps = parse_progression_text("| G | C | Am D7 | % - |", 4)
        self.assertEqual([(s.symbol, s.beats) for s in steps],
                         [("G", 4), ("C", 4), ("Am", 2), ("D7", 2), ("D7", 2), ("Rest", 2)])
        again = parse_progression_text(format_progression_text(steps, 4), 4)
        self.assertEqual([(s.root, s.chord_type, s.beats) for s in again],
                         [(s.root, s.chord_type, s.beats) for s in steps])
        self.assertEqual([s.beats for s in parse_progression_text("Am7:2 D7:2 G", 3)], [2, 2, 3])
        self.assertEqual([s.beats for s in parse_progression_text("| A B C |", 4)], [2, 1, 1])

    def test_generated_progressions(self):
        import random

        from core.progression_studio import cadence_progression, dice_progression
        from core.theory import NOTE_TO_SEMITONE

        self.assertEqual([s.symbol for s in cadence_progression("major_251", "C").steps], ["Dm7", "G7", "Cmaj7", "Cmaj7"])
        self.assertEqual([s.symbol for s in cadence_progression("minor_251", "A").steps], ["Bm7b5", "E7", "Am7", "Am7"])
        blues = cadence_progression("blues12", "G").steps
        self.assertEqual(len(blues), 12)
        self.assertEqual([s.symbol for s in blues[8:10]], ["D7", "C7"])
        prog, text = dice_progression("G", rng=random.Random(4))
        self.assertEqual(len(prog.steps), 4)
        for v7, target in (prog.steps[0:2], prog.steps[2:4]):  # each target is approached by its own V7
            self.assertEqual(v7.chord_type, "Dominant 7th")
            self.assertEqual((NOTE_TO_SEMITONE[v7.root] - NOTE_TO_SEMITONE[target.root]) % 12, 7)
        self.assertIn("→", text)

    def test_file_round_trip_and_legacy_cp(self):
        from core.progression_studio import STYLE_ARPEGGIO, StudioProgression, parse_progression_text

        prog = StudioProgression(name="t", key="G", time_signature="3/4", tempo=90,
                                 steps=parse_progression_text("| G | C D | Em |", 3), neck_name="N")
        prog.steps[0].set_stance(3, ["P1"], [8, 6, 5], pinned=True)
        prog.steps[1].style = STYLE_ARPEGGIO
        back = StudioProgression.from_dict(prog.to_dict())
        self.assertEqual([s.to_dict() for s in back.steps], [s.to_dict() for s in prog.steps])
        self.assertEqual((back.time_signature, back.tempo, back.neck_name), ("3/4", 90, "N"))

        # Without the "studio" block (another app, or an old voice-leader file): chords per beat slot.
        legacy = {k: v for k, v in prog.to_dict().items() if k != "studio"}
        steps = StudioProgression.from_dict(legacy).steps
        self.assertEqual([(s.symbol, s.beats) for s in steps], [("G", 3), ("C", 2), ("D", 1), ("Em", 3)])
        old_vl = {"timeSignature": "4/4", "measures": [
            {"id": 0, "slots": [{"beat": 1, "chord": {"root": "C", "type": "Minor 7"}}]},
            {"id": 1, "slots": [{"beat": 1}]},
            {"id": 2, "slots": [{"beat": 3, "chord": {"root": "F", "type": "Dominant 7"}}]},
        ]}
        self.assertEqual([(s.symbol, s.beats) for s in StudioProgression.from_dict(old_vl).steps],
                         [("Cm7", 4), ("Rest", 4), ("Rest", 2), ("F7", 2)])

    def test_fill_stances_sounds_every_chord_and_keeps_pins(self):
        from core.progression_studio import cadence_progression, fill_stances, parse_progression_text

        for build in E9_NECKS + C6_NECKS:
            neck = build()
            for steps in (cadence_progression("blues12", "G").steps, cadence_progression("major_251", "F").steps,
                          parse_progression_text("G Em C D7 - G", 4)):
                unsolved = fill_stances(neck, steps, VoiceLeadingConstraints(0, 12, 3, "minimal", 3))
                for i, s in enumerate(steps):
                    if s.is_rest or i in unsolved:
                        continue
                    self.assertTrue(grip_matches_chord(neck, s.fret, s.controllers, s.grip, s.root, s.chord_type,
                                                       require_root=False), (neck.name, s.symbol, s.fret, s.controllers))
                    self.assertFalse(s.pinned)

        neck = presets.build_standard_emmons_e9_10()
        steps = parse_progression_text("G C D G", 4)
        steps[1].set_stance(3, ["P1", "P2"], [8, 6, 5], pinned=True)  # C at fret 3 with A+B
        fill_stances(neck, steps, VoiceLeadingConstraints(0, 12, 3, "up", 0))
        self.assertEqual((steps[1].fret, steps[1].controllers, steps[1].pinned), (3, ["P1", "P2"], True))
        self.assertTrue(all(s.has_stance for s in steps))
        # A different chord clears a stance (it can never be replayed for the wrong chord); the same keeps it.
        steps[1].set_chord("C", "Major")
        self.assertTrue(steps[1].has_stance)
        steps[1].set_chord("A", "Minor")
        self.assertFalse(steps[1].has_stance or steps[1].pinned)

    def test_identify_grip_and_presets(self):
        from core.progression_studio import identify_grip_chord, preset_progression
        from core.progression_presets import PROGRESSION_PRESETS

        e9 = presets.build_standard_emmons_e9_10()
        self.assertEqual(identify_grip_chord(e9, 3, [], [8, 6, 5]), ("G", "Major"))
        self.assertEqual(identify_grip_chord(e9, 3, ["P1", "P2"], [8, 6, 5]), ("C", "Major"))
        self.assertEqual(identify_grip_chord(e9, 3, [], [8, 6, 5], hint=("E", "Minor")), ("G", "Major"))  # hint must fit
        self.assertIsNone(identify_grip_chord(e9, 3, [], [8, 6]))
        for ctrl, grip, fret in (([], [8, 6, 5, 4], 3), (["P2"], [5, 4, 3], 7)):
            chord = identify_grip_chord(e9, fret, ctrl, grip)
            if chord:
                self.assertTrue(grip_matches_chord(e9, fret, ctrl, grip, *chord, require_root=False))

        be_c6 = presets.build_be_c6_5p_4kl()
        for p in PROGRESSION_PRESETS:
            neck = be_c6 if p.neck_type == "C6" else e9
            prog = preset_progression(p, neck)
            self.assertIsNotNone(prog, p.name)
            for s in prog.steps:
                self.assertTrue(s.pinned and s.has_stance)
                self.assertTrue(set(s.controllers) <= set(neck.pedals) | set(neck.knee_levers))
                if s.has_chord:
                    self.assertTrue(grip_matches_chord(neck, s.fret, s.controllers, s.grip, s.root, s.chord_type,
                                                       require_root=False), (p.name, s.symbol))

    def test_playback_plan_and_tab(self):
        from core.progression_studio import (
            STYLE_ARPEGGIO, PlaybackPlan, StudioProgression, arpeggio_strings, parse_progression_text, tab_steps,
        )
        from core.stances import controller_display_names
        from core.tab_generator import TabGenerator

        prog = StudioProgression(steps=parse_progression_text("G C:2 D:2 G", 4))
        plan = PlaybackPlan.build(prog, 0, 3, count_in_bars=1, loop=False)
        events = [plan.at(k) for k in range(18)]
        self.assertEqual([e.count_in for e in events[:5]], [True] * 4 + [False])
        self.assertEqual([k for k, e in enumerate(events) if e.step is not None], [4, 8, 10, 12])
        self.assertEqual([k for k, e in enumerate(events) if e.accent], [0, 4, 8, 12])
        self.assertTrue(events[16].done and not events[15].done)
        loop = PlaybackPlan.build(prog, 1, 2, count_in_bars=0, loop=True)  # C D, starting mid-song
        self.assertEqual([loop.at(k).step for k in range(6)], [1, None, 2, None, 1, None])
        self.assertTrue(loop.at(0).accent and not loop.at(2).accent)  # C starts bar 2, D on beat 3

        neck = presets.build_standard_emmons_e9_10()
        prog.steps[0].set_stance(3, [], [8, 6, 5])
        prog.steps[1].set_stance(3, ["P1", "P2"], [8, 6, 5])
        prog.steps[1].style = STYLE_ARPEGGIO
        self.assertEqual(len(arpeggio_strings(prog.steps[1])), 8)  # one 4-note cycle per beat
        tabs = tab_steps(prog.steps, controller_display_names(neck))
        self.assertEqual(len(tabs), 1 + 4)  # block G, then one arpeggio cycle (unvoiced steps skipped)
        self.assertEqual([t.chord_label for t in tabs[:2]], ["G", "C"])
        self.assertTrue(all(t.pick_finger for t in tabs[1:]))
        text = TabGenerator.generate_ascii_tab(neck.string_count, tabs)
        self.assertIn("A+B", text)


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
