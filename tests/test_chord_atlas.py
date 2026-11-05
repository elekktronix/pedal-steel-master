"""E-27 Chord Atlas: every chord a copedant can play at one bar position.

Every way the atlas lists is checked through the resolver (grip_matches_chord), on the E9, C6 and
Universal 12 (with half-stops) factory necks. The interactive dialog skips this re-check for speed.

Run: .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import presets  # noqa: E402
from core.chord_atlas import (  # noqa: E402
    GRIP_SOURCE_ALL,
    GRIP_SOURCE_CURRENT,
    GRIP_SOURCE_CUSTOM,
    GRIP_SOURCE_POCKETS,
    GRIP_SOURCE_SOLVER,
    build_atlas,
    by_stance,
    coverage,
    filter_atlas,
    grips_for_config,
    parse_grip_list,
    pocket_presets,
)
from core.copedant_compare import ChordSighting, inversion_index, inversion_name, sighting_filter  # noqa: E402
from core.stances import grip_matches_chord  # noqa: E402
from core.theory import NOTE_NAMES_SHARP  # noqa: E402

_ATLAS = {}


def atlas(builder):
    if builder not in _ATLAS:
        _ATLAS[builder] = (builder(), build_atlas(builder(), verify=False))
    return _ATLAS[builder]


def entry(a, root_pc, ctype):
    return next((e for e in a.entries if (e.root_pc, e.chord_type) == (root_pc, ctype)), None)


class AtlasEngineTests(unittest.TestCase):
    def test_every_way_sounds_its_chord(self):
        for builder in (presets.build_standard_emmons_e9_10, presets.build_standard_c6_10,
                        presets.build_gfi_12u_7p_5kl_3hs):
            neck, a = atlas(builder)
            with self.subTest(neck=neck.name):
                self.assertTrue(a.entries)
                for e in a.entries:
                    for s in e.sightings:
                        self.assertTrue(grip_matches_chord(neck, 0, s.controllers, s.strings,
                                                           NOTE_NAMES_SHARP[e.root_pc], e.chord_type),
                                        (e.chord_type, e.root_pc, s))

    def test_no_way_holds_a_lever_that_changes_nothing(self):
        """A controller that doesn't move any grip string makes a duplicate way (C on C6 5-3-2
        was listed with LKL, LKR, RKR, P4, P8 ...). Checked through the resolver, atlas and Find."""
        from core.chord_atlas import find_chord
        from core.copedant_compare import _stance_pcs

        def idle(neck, s):
            base = _stance_pcs(neck, s.controllers, 0)
            for c in s.controllers:
                sub = _stance_pcs(neck, tuple(x for x in s.controllers if x != c), 0)
                if all(sub[n] == base[n] for n in s.strings):
                    return c
            return None

        for builder in (presets.build_standard_emmons_e9_10, presets.build_standard_c6_10,
                        presets.build_be_e9_3p_5kl_1hs, presets.build_be_c6_5p_4kl):
            neck, a = atlas(builder)
            with self.subTest(neck=neck.name):
                ways = {s for e in a.entries for s in e.sightings}
                ways |= {p.sighting for r in ("C", "G", "F") for t in ("Major", "Minor", "Dominant 7th")
                         for p in find_chord(a, r, t)}
                for s in ways:
                    self.assertIsNone(idle(neck, s), s)

        neck, a = atlas(presets.build_standard_c6_10)
        c = [p for p in find_chord(a, "C", "Major") if p.sighting.strings == (5, 3, 2)]
        self.assertEqual({p.sighting.controllers for p in c}, {()})
        self.assertIn(ChordSighting(0, "Major", (), (5, 3, 2)), entry(a, 0, "Major").sightings)
        _, e9 = atlas(presets.build_standard_emmons_e9_10)
        self.assertIn(ChordSighting(9, "Major", ("P1", "P2"), (8, 6, 5)), entry(e9, 9, "Major").sightings)

    def test_known_e9_chords(self):
        _, a = atlas(presets.build_standard_emmons_e9_10)
        e_major = entry(a, 4, "Major")
        self.assertIn(ChordSighting(4, "Major", (), (8, 6, 5)), e_major.sightings)
        self.assertEqual(e_major.best.controllers, ())  # the open grip is the easiest way
        a_major = entry(a, 9, "Major")
        self.assertIn(ChordSighting(9, "Major", ("P1", "P2"), (8, 6, 5)), a_major.sightings)
        c_sharp_minor = entry(a, 1, "Minor")
        self.assertTrue(any(s.controllers == ("P1",) for s in c_sharp_minor.sightings))  # A pedal = vi

    def test_filters_views_and_coverage(self):
        _, a = atlas(presets.build_standard_emmons_e9_10)
        keep = sighting_filter(allowed_controllers={"P1", "P2"}, include_shells=False,
                               grips=[(8, 6, 5)])
        out = filter_atlas(a, keep, chord_types=["Major", "Minor"])
        self.assertTrue(out)
        for e in out:
            self.assertIn(e.chord_type, ("Major", "Minor"))
            for s in e.sightings:
                self.assertEqual(s.strings, (8, 6, 5))
                self.assertTrue(set(s.controllers) <= {"P1", "P2"})
        self.assertEqual({(e.root_pc, e.chord_type) for e in out},
                         {(4, "Major"), (9, "Major"), (1, "Minor")})  # I, IV (A+B), vi (A)
        only_a = filter_atlas(a, keep, root_pc=9)
        self.assertEqual({e.root_pc for e in only_a}, {9})
        stances = by_stance(out)
        self.assertEqual(list(stances)[0], ())  # open first
        cov = coverage(out, tonic_pc=4)
        self.assertEqual(set(cov["Major"]), {0, 5})  # I and IV of E
        self.assertEqual(set(cov["Minor"]), {9})      # vi

    def test_grip_configurations(self):
        e9 = presets.build_standard_emmons_e9_10()
        self.assertIn((8, 6, 5), pocket_presets(e9))
        self.assertEqual(parse_grip_list("8-6-5, 6 5 4; 10/8/6, 3-1, 11-9-8", 10), [(8, 6, 5), (6, 5, 4), (10, 8, 6)])
        all3 = grips_for_config(e9, GRIP_SOURCE_ALL, [3], 5)
        self.assertTrue(all(len(g) == 3 and g[0] - g[-1] <= 4 for g in all3))
        self.assertNotIn((10, 6, 5), all3)
        self.assertEqual(grips_for_config(e9, GRIP_SOURCE_CURRENT, [3, 4], 5, current_pocket={4, 5, 6}), [(6, 5, 4)])
        self.assertEqual(grips_for_config(e9, GRIP_SOURCE_CUSTOM, [3], 5, custom="10-8-6"), [(10, 8, 6)])
        self.assertTrue(grips_for_config(e9, GRIP_SOURCE_SOLVER, [3, 4, 5], 6))
        self.assertTrue(grips_for_config(e9, GRIP_SOURCE_POCKETS, [3], 6))


class InversionTests(unittest.TestCase):
    def test_open_e9_triad_inversions(self):
        _, a = atlas(presets.build_standard_emmons_e9_10)
        e_major = {s.strings: s for s in entry(a, 4, "Major").sightings if s.controllers == ()}
        self.assertEqual(e_major[(8, 6, 5)].inversion, 0)   # E-G#-B
        self.assertEqual(e_major[(6, 5, 4)].inversion, 1)   # G#-B-E
        self.assertEqual(e_major[(5, 4, 3)].inversion, 2)   # B-E-G#
        self.assertEqual(e_major[(10, 8, 6)].inversion, 2)  # B-E-G#
        a_major = {s.strings: s for s in entry(a, 9, "Major").sightings if s.controllers == ("P1", "P2")}
        self.assertEqual(a_major[(8, 6, 5)].inversion, 2)   # E-A-C#: A pedals give A in 2nd inversion
        self.assertEqual(inversion_name("Major", 7), "2nd inversion (5 in bass)")

    def test_bass_is_the_lowest_resolved_pitch_for_every_way(self):
        from core.resolver import FretboardResolver

        neck, a = atlas(presets.build_standard_emmons_e9_10)
        cache = {}
        for e in a.entries:
            for s in e.sightings:
                if s.controllers not in cache:
                    cache[s.controllers] = {x.string_number: x.active_midi for x in
                                            FretboardResolver.resolve_neck_state(neck, 0, set(s.controllers))}
                bass = min(cache[s.controllers][n] for n in s.strings)
                self.assertEqual(s.bass_interval, (bass - e.root_pc) % 12, s)
                self.assertGreaterEqual(s.inversion, 0, s)

    def test_inversion_rules(self):
        self.assertEqual(inversion_index("Dominant 7th", 10), 3)   # b7 in bass
        self.assertEqual(inversion_index("Major 6th", 9), 3)       # C6 over A
        self.assertEqual(inversion_index("Sus4", 5), 1)            # the 4 replaces the 3rd
        self.assertEqual(inversion_index("Diminished", 6), 2)
        self.assertEqual(inversion_index("Dominant 9th", 2), 4)    # extension in bass
        self.assertEqual(inversion_index("6/9", 2), 4)
        self.assertEqual(inversion_index("Major", -1), -1)

    def test_inversion_filter(self):
        _, a = atlas(presets.build_standard_emmons_e9_10)
        out = filter_atlas(a, sighting_filter(inversions={1}), chord_types=["Major", "Minor"])
        self.assertTrue(out)
        self.assertTrue(all(s.inversion == 1 for e in out for s in e.sightings))


class FindModeTests(unittest.TestCase):  # E-28
    def _check_positions(self, neck, positions, root, ctype, must_sound):
        from core.resolver import FretboardResolver
        from core.theory import CHORD_FORMULAS, NOTE_TO_SEMITONE

        formula = CHORD_FORMULAS[ctype]
        root_pc = NOTE_TO_SEMITONE[root]
        for p in positions:
            s = p.sighting
            states = {x.string_number: x.active_midi for x in
                      FretboardResolver.resolve_neck_state(neck, p.fret, set(s.controllers))}
            midis = [states[n] for n in s.strings]
            rel = {(m - root_pc) % 12 for m in midis}
            self.assertTrue(rel <= set(formula), (p.fret, s))  # only chord tones
            self.assertTrue({k for k, lbl in formula.items() if lbl in must_sound} <= rel, (p.fret, s))
            self.assertEqual(p.formula, tuple(formula[(m - root_pc) % 12] for m in sorted(midis)))
            self.assertEqual(s.bass_interval, (min(midis) - root_pc) % 12)
            self.assertTrue(0 <= p.fret <= 15)

    def test_positions_sound_the_chord_at_their_fret(self):
        from core.chord_atlas import find_chord, sort_positions

        neck, a = atlas(presets.build_standard_emmons_e9_10)
        g = sort_positions(find_chord(a, "G", "Major"))
        self.assertTrue(g)
        self._check_positions(neck, g, "G", "Major", {"R", "3", "5"})
        keys = {(p.fret, p.sighting.controllers, p.sighting.strings) for p in g}
        self.assertIn((3, (), (8, 6, 5)), keys)             # open grip at fret 3
        self.assertIn((10, ("P1", "P2"), (8, 6, 5)), keys)  # A+B at fret 10
        self.assertEqual(g[0].sighting.controllers, ())     # easiest first: open bar

        b7 = find_chord(a, "B", "Dominant 7th")
        self._check_positions(neck, b7, "B", "Dominant 7th", {"R", "3", "5", "b7"})
        self.assertIn((7, (), (9, 6, 5, 4)), {(p.fret, p.sighting.controllers, p.sighting.strings) for p in b7})

    def test_left_out_tones_and_shells(self):
        from core.chord_atlas import find_chord

        neck, a = atlas(presets.build_standard_emmons_e9_10)
        rootless = find_chord(a, "B", "Dominant 7th", omitted={"R"})
        self._check_positions(neck, rootless, "B", "Dominant 7th", {"3", "5", "b7"})
        self.assertTrue(all("R" in p.missing and "R" not in p.formula for p in rootless))
        self.assertIn((0, ("P2",), (3, 2, 1)),
                      {(p.fret, p.sighting.controllers, p.sighting.strings) for p in rootless})  # A-D#-F#
        no_fifth = find_chord(a, "B", "Dominant 7th", omitted={"5"})
        self._check_positions(neck, no_fifth, "B", "Dominant 7th", {"R", "3", "b7"})
        self.assertTrue(all(p.missing == ("5",) for p in no_fifth))
        shells = find_chord(a, "B", "Dominant 7th", allow_no_fifth=True)
        self.assertGreater(len(shells), len(find_chord(a, "B", "Dominant 7th")))
        self.assertTrue({(p.fret, p.sighting.strings) for p in no_fifth}
                        <= {(p.fret, p.sighting.strings) for p in shells})
        self.assertEqual(find_chord(a, "B", "Major", omitted={"R", "3", "5"}), [])
        self.assertTrue(all(p.fret <= 5 for p in find_chord(a, "G", "Major", max_fret=5)))

    def test_covers_every_exact_voicing_of_the_old_finder(self):
        """Every voicing the old VoicingSolver found that sounds every chord tone is found here too.
        (It also listed incomplete grips, e.g. a plain B triad as "B7"; Find mode does not. It also
        listed levers that don't touch the grip; those are compared as the simpler stance.)"""
        from core.chord_atlas import find_chord
        from core.copedant_compare import has_idle_controller
        from core.stances import grip_pitch_classes
        from core.theory import CHORD_FORMULAS, NOTE_TO_SEMITONE
        from core.voicing_solver import VoicingSolver

        neck, a = atlas(presets.build_standard_emmons_e9_10)

        def simplest(stance, grip):
            while has_idle_controller(stance, grip, a.stance_midis):
                base = a.stance_midis[stance]
                stance = next(sub for c in stance
                              for sub in [tuple(x for x in stance if x != c)]
                              if sub in a.stance_midis
                              and all(a.stance_midis[sub][n] == base[n] for n in grip))
            return stance

        for root, ctype in (("G", "Major"), ("B", "Dominant 7th"), ("C#", "Minor")):
            ours = {(p.fret, p.sighting.controllers, p.sighting.strings) for p in find_chord(a, root, ctype)}
            for m in VoicingSolver.find_all_voicings(neck, root, ctype, max_fret=15):
                tones = {(NOTE_TO_SEMITONE[root] + k) % 12 for k in CHORD_FORMULAS[ctype]}
                if grip_pitch_classes(neck, m.fret, m.engaged_levers, m.grip_strings) == tones:
                    grip = tuple(sorted(m.grip_strings, reverse=True))
                    key = (m.fret, simplest(tuple(sorted(m.engaged_levers)), grip), grip)
                    self.assertIn(key, ours, (root, ctype))


class ControllerMatchTests(unittest.TestCase):
    def test_modes(self):
        from core.copedant_compare import controllers_match

        sel = {"P1", "P2"}
        self.assertTrue(controllers_match({"P1", "P2"}, sel, "exact"))
        self.assertFalse(controllers_match({"P2"}, sel, "exact"))
        self.assertFalse(controllers_match({"P1", "P2", "LKL"}, sel, "exact"))
        self.assertTrue(controllers_match({"P1", "P2", "LKL"}, sel, "include"))
        self.assertFalse(controllers_match({"P2"}, sel, "include"))
        self.assertTrue(controllers_match(set(), sel, "only"))
        self.assertTrue(controllers_match({"P2"}, sel, "only"))
        self.assertFalse(controllers_match({"P2", "LKL"}, sel, "only"))


class RadarTests(unittest.TestCase):  # E-29
    def test_moves_sound_their_whole_chord(self):
        from core.chord_atlas import RADAR_TARGETS, find_neighbors
        from core.stances import grip_pitch_classes
        from core.theory import CHORD_FORMULAS, NOTE_TO_SEMITONE

        neck, a = atlas(presets.build_standard_emmons_e9_10)
        for origin in [("E", 0, (8, 6, 5), ()), ("A", 0, (8, 6, 5), ("P1", "P2")), ("G", 3, (6, 5, 4), ())]:
            moves = find_neighbors(a, *origin)
            self.assertTrue(moves, origin)
            self.assertEqual({m.relationship for m in moves}, {r for r, _, _ in RADAR_TARGETS}, origin)
            for m in moves:
                tones = {(NOTE_TO_SEMITONE[m.root] + k) % 12 for k in CHORD_FORMULAS[m.chord_type]}
                pcs = grip_pitch_classes(neck, m.fret, m.controllers, m.strings)
                self.assertEqual(pcs, tones, (origin, m.relationship, m.fret, m.controllers, m.strings))
                self.assertLessEqual(abs(m.delta_frets), 9)

    def test_classic_e9_moves(self):
        from core.chord_atlas import find_neighbors

        _, a = atlas(presets.build_standard_emmons_e9_10)
        moves = find_neighbors(a, "E", 0, (8, 6, 5), ())
        iv = [m for m in moves if m.relationship.startswith("IV")]
        self.assertEqual((iv[0].fret, iv[0].controllers, iv[0].strings), (0, ("P1", "P2"), (8, 6, 5)))  # A+B
        v = [m for m in moves if m.relationship.startswith("V (")]
        self.assertTrue(any((m.fret, m.controllers) == (2, ("P1", "P2")) for m in v))  # A+B two frets up
        v7 = [m for m in moves if m.relationship.startswith("V7")]
        self.assertTrue(all(len(m.strings) >= 4 for m in v7))  # a triad is never a V7
        shells = find_neighbors(a, "E", 0, (8, 6, 5), (), allow_no_fifth=True)
        self.assertTrue(any(m.relationship.startswith("V7") for m in shells))

    def test_move_filters(self):
        from core.chord_atlas import MOVE_SAME_FRET, find_neighbors

        _, a = atlas(presets.build_standard_emmons_e9_10)
        same = find_neighbors(a, "E", 0, (8, 6, 5), (), allowed_moves={MOVE_SAME_FRET})
        self.assertTrue(same)
        self.assertTrue(all(m.delta_frets == 0 and m.movement == MOVE_SAME_FRET for m in same))


def _delete_widget(w):
    from PySide6.QtCore import QCoreApplication, QEvent
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


class AtlasDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _dialog(self, **kw):
        from ui.chord_atlas_dialog import ChordAtlasDialog
        dlg = ChordAtlasDialog(presets.build_standard_emmons_e9_10(), **kw)
        self.addCleanup(_delete_widget, dlg)
        return dlg

    def test_views_filters_and_audition(self):
        dlg = self._dialog(current_pocket={8, 6, 5})
        self.assertGreater(dlg.tree_chords.topLevelItemCount(), 10)
        self.assertGreater(dlg.tree_stances.topLevelItemCount(), 5)
        self.assertGreater(dlg.table_cov.rowCount(), 0)

        dlg.set_grip_source(GRIP_SOURCE_CURRENT)
        dlg.filter_bar.set_chord_types(["Major", "Minor"])
        dlg.filter_bar.set_controller_match("only")  # open, P1, P2 or P1+P2
        dlg.filter_bar.set_controller_filter({"P1", "P2"})
        self.assertEqual({(e.root_pc, e.chord_type) for e in dlg.entries}, {(4, "Major"), (9, "Major"), (1, "Minor")})

        dlg.spin_fret.setValue(3)  # key of G: G, C, Em
        self.assertIn("G", dlg.lbl_key.text())
        self.assertTrue(dlg.select_chord(9, "Major"))
        item = dlg.tree_chords.currentItem()
        self.assertTrue(item.text(0).startswith("C"))
        self.assertGreater(item.childCount(), 0)  # filled when expanded
        got = []
        dlg.stance_selected.connect(lambda *a: got.append(a))
        dlg._on_item_double_clicked(item.child(0))
        fret, ctrls, strings, root, ctype = got[0]
        self.assertEqual((fret, ctrls, strings, root, ctype), (3, {"P1", "P2"}, {8, 6, 5}, "C", "Major"))
        self.assertTrue(grip_matches_chord(dlg.neck, fret, ctrls, strings, root, ctype))

        dlg.filter_bar.set_inversions({2})  # 2nd inversion only: C (A+B) on 8-6-5 is E-A-C#
        self.assertIn("2nd inversion", dlg.filter_bar.btn_inversions.text())
        self.assertTrue(all(s.inversion == 2 for e in dlg.entries for s in e.sightings))
        self.assertIn((9, "Major"), {(e.root_pc, e.chord_type) for e in dlg.entries})
        dlg.filter_bar.set_inversions({0, 1, 2, 3, 4})
        self.assertIsNone(dlg.filter_bar.selected_inversions())

        dlg.set_current_pocket({5, 4, 3})
        self.assertTrue(all(s.strings == (5, 4, 3) for e in dlg.entries for s in e.sightings))
        dlg.set_grip_source(GRIP_SOURCE_CUSTOM, custom="10-8-6")
        self.assertTrue(all(s.strings == (10, 8, 6) for e in dlg.entries for s in e.sightings))

    def test_find_mode_table_audition_and_radar(self):
        from ui.chord_atlas_dialog import MODE_FIND

        dlg = self._dialog(mode=MODE_FIND, find_root="G", find_chord_type="Major")
        self.assertEqual(dlg.mode, MODE_FIND)
        self.assertFalse(dlg.filter_bar.btn_types.isVisibleTo(dlg))
        self.assertGreater(dlg.table_pos.rowCount(), 5)
        self.assertEqual(dlg.table_pos.item(0, 0).text(), "3")  # open G at fret 3 is easiest
        got = []
        dlg.stance_selected.connect(lambda *a: got.append(a))
        dlg._on_position_double_clicked(0)
        fret, ctrls, strings, root, ctype = got[0]
        self.assertEqual((fret, root, ctype), (3, "G", "Major"))
        self.assertTrue(grip_matches_chord(dlg.neck, fret, ctrls, strings, root, ctype))

        dlg.update_radar_now()  # debounced in the UI
        self.assertGreater(dlg.table_radar.rowCount(), 0)
        got.clear()
        dlg._on_radar_double_clicked(0)
        fret, ctrls, strings, root, ctype = got[0]
        n = dlg._radar_neighbors[0]
        self.assertEqual((fret, root, ctype), (n.fret, n.root, n.chord_type))
        self.assertTrue(grip_matches_chord(dlg.neck, fret, ctrls, strings, root, ctype))

        # Controller match modes on Find results (A+B = P1 + P2 on this neck)
        dlg.filter_bar.set_controller_filter({"P1", "P2"})
        dlg.filter_bar.set_controller_match("exact")
        self.assertTrue(dlg.positions)
        self.assertTrue(all(set(p.sighting.controllers) == {"P1", "P2"} for p in dlg.positions))
        dlg.filter_bar.set_controller_match("include")
        self.assertTrue(all({"P1", "P2"} <= set(p.sighting.controllers) for p in dlg.positions))
        self.assertTrue(any(len(p.sighting.controllers) > 2 for p in dlg.positions))
        dlg.filter_bar.set_controller_match("only")
        self.assertTrue(any(p.sighting.controllers == () for p in dlg.positions))
        dlg.filter_bar.set_controller_filter(set())

        targets = []
        dlg.target_changed.connect(lambda *a: targets.append(a))
        dlg.combo_find_type.setCurrentText("Dominant 7th")
        self.assertEqual(targets[-1], ("G", "Dominant 7th"))
        self.assertEqual(sorted(dlg.tone_checks), sorted(["R", "3", "5", "b7"]))
        dlg.set_omitted_tones({"R"})
        self.assertTrue(dlg.positions)
        self.assertTrue(all("R" in p.missing for p in dlg.positions))
        dlg.filter_bar.set_controller_filter({"P2"})
        self.assertTrue(all(set(p.sighting.controllers) <= {"P2"} for p in dlg.positions))
        dlg.set_mode("explore")
        self.assertIs(dlg.stack.currentWidget(), dlg.tabs)

    def test_coverage_cell_jumps_to_chord(self):
        dlg = self._dialog()
        types = [dlg.table_cov.verticalHeaderItem(r).text() for r in range(dlg.table_cov.rowCount())]
        row = next(i for i, t in enumerate(types) if t.startswith("Major "))
        dlg._on_coverage_double_clicked(row, 5)  # IV of E = A
        self.assertIs(dlg.tabs.currentWidget(), dlg.tree_chords)
        self.assertTrue(dlg.tree_chords.currentItem().text(0).startswith("A "))


if __name__ == "__main__":
    unittest.main()
