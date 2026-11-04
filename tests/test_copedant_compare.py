"""E-25 Compare Copedants: diffing two copedants and the chords each change adds or removes.

Every reported way to play a chord is checked through the resolver (grip_matches_chord).

Run: .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import presets  # noqa: E402
from core.copedant_compare import (  # noqa: E402
    ChordSighting,
    all_grips,
    apply_item,
    candidate_stances,
    compare_copedants,
    describe_delta,
    diff_copedants,
    filter_report,
    root_name,
    scan_chords,
)
from core.models import HalfStopRule, SplitRule, migrate_half_stop_tokens, migrate_legacy_ids  # noqa: E402
from core.resolver import FretboardResolver  # noqa: E402
from core.stances import grip_matches_chord  # noqa: E402
from core.theory import NOTE_NAMES_SHARP, midi_to_note_name, set_accidental_preference  # noqa: E402


def e9():
    return presets.build_standard_emmons_e9_10()


def matches(neck, s: ChordSighting) -> bool:
    return grip_matches_chord(neck, 0, s.controllers, s.strings, NOTE_NAMES_SHARP[s.root_pc], s.chord_type)


def delta_keys(report):
    return {(d.root_pc, d.chord_type, tuple(d.gained), tuple(d.lost)) for d in report.deltas}


class DiffTests(unittest.TestCase):
    def test_identical_necks_have_no_changes(self):
        cmp = compare_copedants(e9(), e9())
        self.assertEqual(cmp.items, [])
        self.assertEqual(cmp.total.deltas, [])
        self.assertEqual(cmp.per_item, [])

    def test_legacy_rename_is_not_a_change(self):
        legacy = presets.build_be_e9_3p_5kl_1hs()  # uses "VL"
        migrated = deepcopy(legacy)
        migrate_legacy_ids(migrated)
        migrate_half_stop_tokens(migrated)
        self.assertIn("VL", diff_copedants(legacy, migrated)[0].description)  # raw IDs differ...
        saved = deepcopy(legacy)
        migrate_legacy_ids(saved)
        migrate_half_stop_tokens(saved)
        self.assertEqual(diff_copedants(saved, migrated), [])  # ...so the editor migrates both sides

    def test_diff_finds_each_kind(self):
        base = e9()
        mod = deepcopy(base)
        mod.knee_levers["LKR"].changes[6] = -1                  # pull added
        mod.pedals["P1"].changes[5] = 1                         # pull changed
        del mod.knee_levers["RKR"]                              # controller removed
        mod.splits.append(SplitRule(6, ["P2", "LKR"], 0))       # split added
        mod.splits[0].semitone_delta = 1                        # split changed (P3+LKL on 4)
        mod.half_stops.append(HalfStopRule("P3", 4, 1))         # half-stop added
        mod.open_tuning[8].midi_note += 1                       # string 9 D -> D#
        kinds = {(i.kind, i.controller_id, i.string_number) for i in diff_copedants(base, mod)}
        self.assertTrue({
            ("pull_added", "LKR", 6),
            ("pull_changed", "P1", 5),
            ("controller_removed", "RKR", 0),
            ("split_added", "LKR+P2", 6),
            ("split_changed", "LKL+P3", 4),
            ("half_stop_added", "P3", 4),
            ("tuning_changed", "", 9),
        } <= kinds, kinds)
        self.assertEqual(len(kinds), 7)

    def test_apply_item_applies_only_that_change(self):
        base = e9()
        mod = deepcopy(base)
        mod.knee_levers["LKR"].changes[6] = -1
        mod.splits.append(SplitRule(6, ["P2", "LKR"], 1))
        for item in diff_copedants(base, mod):
            variant = apply_item(base, mod, item)
            self.assertEqual(len(diff_copedants(variant, mod)), 1)
            self.assertEqual([i.kind for i in diff_copedants(base, variant)], [item.kind])
        split_item = next(i for i in diff_copedants(base, mod) if i.kind == "split_added")
        variant = apply_item(base, mod, split_item)
        self.assertNotIn(6, variant.knee_levers["LKR"].changes)  # the split alone does nothing yet
        both = apply_item(apply_item(base, mod, diff_copedants(base, mod)[0]), mod, split_item)
        g = {s.string_number: s.active_midi for s in FretboardResolver.resolve_neck_state(both, 0, {"P2", "LKR"})}
        self.assertEqual(g[6], base.open_tuning[5].midi_note + 1)  # split: P2 wins (A), not the sum (G#)


class ScanTests(unittest.TestCase):
    def test_grips_and_stances(self):
        grips = all_grips(10)
        self.assertIn((8, 6, 5), grips)
        self.assertIn((6, 5, 4, 3), grips)
        self.assertNotIn((10, 6, 5), grips)  # wider than 5 strings
        neck = deepcopy(e9())
        neck.half_stops.append(HalfStopRule("P3", 4, 1))
        self.assertIn(("P3_HALF",), candidate_stances(neck))

    def test_open_e_major_and_scan_is_verified(self):
        neck = e9()
        scan = scan_chords(neck)
        self.assertIn(ChordSighting(4, "Major", (), (8, 6, 5)), scan[(4, "Major")])
        for sightings in list(scan.values())[:40]:
            for s in list(sightings)[:5]:
                self.assertTrue(matches(neck, s), s)


class CompareTests(unittest.TestCase):
    def test_removing_pedal_b_loses_a_major_on_8_6_5(self):
        base = e9()
        mod = deepcopy(base)
        del mod.pedals["P2"]
        cmp = compare_copedants(base, mod)
        a_major = next(d for d in cmp.total.deltas if (d.root_pc, d.chord_type) == (9, "Major"))
        want = ChordSighting(9, "Major", ("P1", "P2"), (8, 6, 5))
        self.assertIn(want, a_major.lost)
        self.assertTrue(matches(base, want))
        self.assertEqual(a_major.gained, [])
        self.assertTrue(all(d.gained == [] for d in cmp.total.deltas))  # removing a pedal adds nothing

    def test_new_lkr_pull_gains_are_real(self):
        base = e9()
        mod = deepcopy(base)
        mod.knee_levers["LKR"].changes[6] = -1  # LKR also lowers G# -> G
        cmp = compare_copedants(base, mod)
        self.assertTrue(any(d.status in ("new_chord", "new_ways") for d in cmp.total.deltas))
        for d in cmp.total.deltas:
            for s in d.gained:
                self.assertIn("LKR", s.controllers)
                self.assertTrue(matches(mod, s), s)
                self.assertFalse(matches(base, s), s)
            for s in d.lost:
                self.assertTrue(matches(base, s), s)
                self.assertFalse(matches(mod, s), s)
        # One change: its own report is the total, and nothing is a combined effect.
        self.assertEqual(len(cmp.per_item), 1)
        self.assertEqual(delta_keys(cmp.per_item[0][1]), delta_keys(cmp.total))
        self.assertEqual(cmp.interactions.deltas, [])
        # LKR now gives B-D-G on strings 10-9-6: a G major triad (was B-D-G#, G#dim).
        g = ChordSighting(7, "Major", ("LKR",), (10, 9, 6))
        self.assertFalse(matches(base, g))
        self.assertTrue(any(g in d.gained for d in cmp.total.deltas if (d.root_pc, d.chord_type) == (7, "Major")))
        text = describe_delta(cmp.total.deltas[0], mod, fret=3)
        self.assertTrue(text)

    def test_per_item_plus_interactions_explain_total(self):
        base = e9()
        mod = deepcopy(base)
        mod.knee_levers["LKR"].changes[6] = -1
        mod.pedals["P1"].changes[3] = 1
        cmp = compare_copedants(base, mod)
        self.assertEqual(len(cmp.per_item), 2)
        gained = set().union(*(s.gained for _, r in cmp.per_item for s in r.deltas))
        lost = set().union(*(s.lost for _, r in cmp.per_item for s in r.deltas))
        inter_g = {s for d in cmp.interactions.deltas for s in d.gained}
        inter_l = {s for d in cmp.interactions.deltas for s in d.lost}
        for d in cmp.total.deltas:
            for s in d.gained:
                self.assertTrue(s in gained or s in inter_g, s)
            for s in d.lost:
                self.assertTrue(s in lost or s in inter_l, s)
        # A stance that needs both changes is a combined effect.
        self.assertTrue(all({"LKR", "P1"} <= set(s.controllers) for s in inter_g), inter_g)

    def test_c6_pedal_change(self):
        base = presets.build_standard_c6_10()
        mod = deepcopy(base)
        pid = sorted(mod.pedals)[0]
        string = next(iter(mod.pedals[pid].changes))
        del mod.pedals[pid].changes[string]
        cmp = compare_copedants(base, mod)
        self.assertEqual(len(cmp.items), 1)
        self.assertTrue(cmp.total.deltas)
        for d in cmp.total.deltas:
            for s in d.lost:
                self.assertTrue(matches(base, s), s)
            for s in d.gained:
                self.assertTrue(matches(mod, s), s)


class FilterAndSpellingTests(unittest.TestCase):
    def setUp(self):
        base = e9()
        mod = deepcopy(base)
        mod.knee_levers["LKR"].changes[6] = -1
        self.base, self.mod = base, mod
        self.cmp = compare_copedants(base, mod)

    def test_controller_filter_keeps_only_those_controllers(self):
        rep = filter_report(self.cmp.total, allowed_controllers={"LKR", "P1"})
        self.assertTrue(rep.deltas)
        for d in rep.deltas:
            for s in d.gained + d.lost:
                self.assertTrue(set(s.controllers) <= {"LKR", "P1"}, s)
        # G major on LKR, strings 10-9-6, is new *within* {LKR, P1} only if open/P1/LKR/P1+LKR had no G major.
        g = next(d for d in rep.deltas if (d.root_pc, d.chord_type) == (7, "Major"))
        had = any(set(s.controllers) <= {"LKR", "P1"} for s in rep.base_scan[(7, "Major")])
        self.assertEqual(g.status, "new_ways" if had else "new_chord")

    def test_type_and_shell_filters(self):
        rep = filter_report(self.cmp.total, chord_types=["Major", "Minor"], include_shells=False)
        self.assertTrue(rep.deltas)
        self.assertTrue(all(d.chord_type in ("Major", "Minor") for d in rep.deltas))
        self.assertTrue(all(not s.is_shell for d in rep.deltas for s in d.gained + d.lost))
        one = filter_report(self.cmp.total, max_controllers=1)
        self.assertTrue(all(len(s.controllers) <= 1 for d in one.deltas for s in d.gained + d.lost))

    def test_global_spelling(self):
        self.addCleanup(set_accidental_preference, "sharps")
        self.assertEqual(root_name(3), "D#")
        set_accidental_preference("flats")
        self.assertEqual(root_name(3), "Eb")
        self.assertEqual(midi_to_note_name(63), "Eb4")
        # The fretboard (resolver) and the compare window now agree: string 2 of E9 is Eb.
        s2 = next(s for s in FretboardResolver.resolve_neck_state(e9(), 0, set()) if s.string_number == 2)
        self.assertEqual(s2.active_note_name, "Eb4")
        from core.chord_identifier import ChordIdentifier
        tag, family = ChordIdentifier.identify_voicing([63, 67, 70], 63, show_inversion=False)
        self.assertTrue(tag.startswith("Eb"), tag)


class KeyAwareSpellingTests(unittest.TestCase):
    def tearDown(self):
        from core.theory import set_key_aware_spelling
        set_accidental_preference("sharps")
        set_key_aware_spelling(True)

    def test_circle_of_fifths(self):
        from core.circle_of_fifths import CircleOfFifthsEngine
        from core.theory import set_key_aware_spelling

        def names(key):
            return [d.root_name for d in CircleOfFifthsEngine.get_diatonic_chords(key)]

        set_accidental_preference("sharps")
        self.assertIn("Bb", names("F"))            # key signature wins by default
        set_key_aware_spelling(False)
        self.assertIn("A#", names("F"))            # global preference
        set_accidental_preference("flats")
        self.assertEqual(names("B")[1:3], ["Db", "Eb"])  # ii and iii of B major, spelled with flats

    def test_triad_explorer(self):
        from core.theory import NOTE_NAMES_FLAT, set_key_aware_spelling
        from core.triad_explorer import explore

        set_accidental_preference("sharps")
        self.assertIn("Abm", {t.triad_name for t in explore("G", "Dominant 7th")})  # book spelling
        set_key_aware_spelling(False)
        roots = {t.triad_root for t in explore("G", "Dominant 7th")}
        self.assertTrue(roots <= set(NOTE_NAMES_SHARP), roots)
        set_accidental_preference("flats")
        roots = {t.triad_root for t in explore("G", "Dominant 7th")}
        self.assertTrue(roots <= set(NOTE_NAMES_FLAT), roots)


def _delete_widget(w):
    from PySide6.QtCore import QCoreApplication, QEvent
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


class CompareDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_menu_mode_and_double_click(self):
        from core.models import SteelGuitar
        from ui.copedant_compare_dialog import CopedantCompareDialog

        base = e9()
        mod = deepcopy(base)
        mod.name = "E9 copy"
        mod.knee_levers["LKR"].changes[6] = -1
        guitar = SteelGuitar(name="t", necks=[base, mod])
        dlg = CopedantCompareDialog(base, mod, guitar=guitar, base_idx=0, modified_idx=1, active_neck_idx=1)
        self.addCleanup(_delete_widget, dlg)
        self.assertEqual(dlg.list_scope.count(), 2)  # total + one change
        self.assertIn("LKR", dlg.controller_buttons)
        dlg.set_chord_types(["Major", "Minor"])
        self.assertEqual(sorted(dlg.selected_chord_types()), ["Major", "Minor"])
        dlg.set_controller_filter({"LKR"})
        dlg.spin_fret.setValue(3)
        dlg.list_scope.setCurrentRow(1)
        got = []
        dlg.stance_selected.connect(lambda *a: got.append(a))
        leaf = None
        for i in range(dlg.tree.topLevelItemCount()):
            top = dlg.tree.topLevelItem(i)
            for j in range(top.childCount()):
                chord = top.child(j)
                for k in range(chord.childCount()):
                    payload = chord.child(k).data(0, 0x0100)
                    if payload and payload[1]:
                        leaf = chord.child(k)
                        break
                if leaf:
                    break
            if leaf:
                break
        self.assertIsNotNone(leaf)
        dlg._on_item_double_clicked(leaf)
        fret, ctrls, strings, root, ctype = got[0]
        self.assertEqual(fret, 3)
        self.assertTrue(grip_matches_chord(mod, fret, ctrls, strings, root, ctype))
        self.assertTrue(ctrls <= {"LKR"})
        self.assertIn(ctype, ("Major", "Minor"))
        self.assertFalse(dlg.can_apply(gained=False))  # baseline is not the active neck
        # A lost way asks MainWindow to activate the baseline first; nothing is applied if it doesn't.
        requested = []
        dlg.activate_neck_requested.connect(requested.append)
        dlg.set_controller_filter(set())
        dlg.set_chord_types(["Major", "Minor", "Diminished", "Augmented", "Sus4"])
        lost_leaf = None
        for i in range(dlg.tree.topLevelItemCount()):
            top = dlg.tree.topLevelItem(i)
            for j in range(top.childCount()):
                for k in range(top.child(j).childCount()):
                    p = top.child(j).child(k).data(0, 0x0100)
                    if p and not p[1] and lost_leaf is None:
                        lost_leaf = top.child(j).child(k)
        self.assertIsNotNone(lost_leaf)
        got.clear()
        dlg._on_item_double_clicked(lost_leaf)
        self.assertEqual(requested, [0])
        self.assertEqual(got, [])
        dlg.set_active_neck(0)  # MainWindow switched: combos keep their selection
        self.assertTrue(dlg.can_apply(gained=False))
        dlg.combo_mod.setCurrentIndex(0)  # identical necks
        self.assertIn("identical", dlg.lbl_summary.text())

    def test_editor_compare_to_saved(self):
        from ui.copedant_compare_dialog import CopedantCompareDialog
        from ui.copedant_editor_dialog import CopedantEditorDialog

        legacy = presets.build_be_e9_3p_5kl_1hs()
        editor = CopedantEditorDialog(legacy)
        self.addCleanup(_delete_widget, editor)
        self.assertEqual(diff_copedants(editor.saved_neck_for_compare(), editor.neck), [])
        editor.neck.knee_levers["LKR"].changes[6] = -1
        dlg = CopedantCompareDialog(editor.saved_neck_for_compare(), deepcopy(editor.neck))
        self.addCleanup(_delete_widget, dlg)
        self.assertEqual(len(dlg.comparison.items), 1)
        self.assertFalse(dlg.can_apply(gained=True))


if __name__ == "__main__":
    unittest.main()
