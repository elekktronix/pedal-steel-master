"""E-18 (extended chord types) and E-19 (triads over a chord), checked against Franklin's
"Intervals" (pp. 24-28) and through the resolver.

Run: .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import presets  # noqa: E402
from core.resolver import FretboardResolver  # noqa: E402
from core.theory import CHORD_FORMULAS, CHORD_SYMBOL_SUFFIX, NOTE_TO_SEMITONE, get_nashville_chord_symbol  # noqa: E402
from core.triad_explorer import (  # noqa: E402
    SUPPORTED_CHORD_TYPES,
    explore,
    find_triad_grips,
    grip_intervals_over_chord,
)
from core.voice_leader import normalize_chord_type  # noqa: E402


def sounds(root, chord_type):
    return {t.triad_name: t.sounds_like for t in explore(root, chord_type)}


class ExtendedChordTypeTests(unittest.TestCase):  # E-18
    def test_every_type_has_symbol_and_nashville_suffix(self):
        for ctype in CHORD_FORMULAS:
            self.assertIn(ctype, CHORD_SYMBOL_SUFFIX, ctype)
            self.assertNotEqual(get_nashville_chord_symbol("G", "C", family=ctype), "", ctype)
        self.assertEqual(get_nashville_chord_symbol("G", "C", family="Dominant 13th"), "5⁷")
        self.assertEqual(get_nashville_chord_symbol("D", "C", family="Minor 9th"), "2-")

    def test_new_formulas_spell_correctly(self):
        def notes(root, ctype):
            r = NOTE_TO_SEMITONE[root]
            return sorted((r + pc) % 12 for pc in CHORD_FORMULAS[ctype])

        pc = NOTE_TO_SEMITONE
        self.assertEqual(notes("G", "Dominant 13th"), sorted(pc[n] for n in ("G", "B", "D", "F", "A", "E")))
        self.assertEqual(notes("G", "Dominant 7#9"), sorted(pc[n] for n in ("G", "B", "D", "F", "Bb")))
        self.assertEqual(notes("C", "Major 9th"), sorted(pc[n] for n in ("C", "E", "G", "B", "D")))
        self.assertEqual(notes("G", "Major 7th #5"), sorted(pc[n] for n in ("G", "B", "D#", "F#")))

    def test_aliases(self):
        for alias, ctype in [("maj9", "Major 9th"), ("m9", "Minor 9th"), ("11", "Dominant 11th"),
                             ("13", "Dominant 13th"), ("13sus4", "Dominant 13sus4"), ("7b9", "Dominant 7b9"),
                             ("7#9", "Dominant 7#9"), ("7b5", "Dominant 7b5"), ("7#5", "Dominant 7#5"),
                             ("maj7#5", "Major 7th #5"), ("Dominant 11", "Dominant 11th")]:
            self.assertEqual(normalize_chord_type(alias), ctype)

    def test_resolver_labels_extensions(self):
        neck = presets.build_standard_emmons_e9_10()
        # Open E9 over E13: string 1 (F#) is the 9, string 7 (F#) the 9, string 9 (D) the b7, C# none open.
        states = FretboardResolver.resolve_neck_state(neck, 0, set(), target_root_name="E",
                                                      target_chord_type="Dominant 13th")
        labels = {s.string_number: s.interval_label for s in states}
        self.assertEqual((labels[1], labels[9], labels[8]), ("9", "b7", "R"))
        states = FretboardResolver.resolve_neck_state(neck, 0, {"P1"}, target_root_name="E",
                                                      target_chord_type="Dominant 13th")
        self.assertEqual({s.string_number: s.interval_label for s in states}[5], "13")  # A pedal: C#


class TriadExplorerTests(unittest.TestCase):  # E-19
    def test_book_examples_over_g7(self):  # pp. 24-27
        s = sounds("G", "Dominant 7th")
        self.assertEqual((s["Bdim"], s["Dm"], s["F"], s["Am"], s["C"]), ("G7", "G9", "G11", "G13sus4", "G13sus4"))
        # Altered: the Ab melodic minor triads
        self.assertEqual((s["Abm"], s["Bbm"], s["Baug"], s["Db"], s["Eb"], s["Fdim"], s["Gdim"]),
                         ("G7#5b9", "G7b5#9", "G7#5", "G7b5b9", "G7#5#9", "G7b9", "G7b5#9"))

    def test_book_examples_from_third_and_fifth_over_g(self):  # p. 28
        s = sounds("G", "Major")
        self.assertEqual((s["B"], s["Bm"], s["Bdim"]), ("Gmaj7#5", "Gmaj7", "G7"))
        self.assertEqual((s["D"], s["Dm"], s["Ddim"]), ("Gmaj9", "G9", "G7b9"))
        self.assertEqual(s["Em"], "G6")  # p. 21

    def test_intervals_are_the_real_triad_tones(self):
        names = {"R": 0, "b9": 1, "9": 2, "#9": 3, "b3": 3, "3": 4, "11": 5, "#11": 6, "b5": 6, "5": 7,
                 "#5": 8, "b13": 8, "6": 9, "13": 9, "b7": 10, "7": 11}
        for ctype in SUPPORTED_CHORD_TYPES:
            for root in ("C", "F#", "Bb"):
                for t in explore(root, ctype):
                    rel = sorted(names[i] for i in t.intervals)
                    triad = sorted((NOTE_TO_SEMITONE[t.triad_root] + k - NOTE_TO_SEMITONE[root]) % 12
                                   for k in CHORD_FORMULAS[t.triad_type])
                    self.assertEqual(rel, triad, f"{t.triad_name} over {root} {ctype}")
                    if t.sounds_like_type:  # the target must contain every triad tone
                        self.assertTrue(set(triad) <= set(CHORD_FORMULAS[t.sounds_like_type]), t.sounds_like)

    def test_unsupported_type_is_empty(self):
        self.assertEqual(explore("C", "Diminished 7th"), [])
        self.assertEqual(explore("H", "Major"), [])

    def test_grips_sound_the_triad(self):
        for build in (presets.build_standard_emmons_e9_10, presets.build_standard_c6_10):
            neck = build()
            for t in explore("G", "Dominant 7th"):
                grips = find_triad_grips(neck, t)
                self.assertTrue(grips, f"{neck.name}: no grip for {t.triad_name}")
                for m in grips:
                    states = FretboardResolver.resolve_neck_state(neck, m.fret, set(m.engaged_levers))
                    pcs = {s.active_midi % 12 for s in states if s.string_number in m.grip_strings}
                    want = {(NOTE_TO_SEMITONE[t.triad_root] + k) % 12 for k in CHORD_FORMULAS[t.triad_type]}
                    self.assertEqual(pcs, want, f"{neck.name} {t.triad_name} fret {m.fret} {m.engaged_levers}")
                    over = grip_intervals_over_chord(t, m.voicing_formula).split(" - ")
                    self.assertTrue(set(over) <= set(t.intervals), over)


class TriadExplorerDialogTests(unittest.TestCase):
    def test_click_grip_emits_stance_and_target(self):
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication

        from ui.triad_explorer_dialog import TriadExplorerDialog

        from core.theory import set_accidental_preference

        app = QApplication.instance() or QApplication([])  # noqa: F841
        set_accidental_preference("flats")  # the root combo follows the global spelling
        self.addCleanup(set_accidental_preference, "sharps")
        dlg = TriadExplorerDialog(presets.build_standard_emmons_e9_10(), root="A#", chord_type="Dominant 7th")
        try:
            self.assertEqual(dlg.combo_root.currentText(), "Bb")
            row = next(i for i, t in enumerate(dlg.triads) if t.sounds_like == "Bb9")  # Fm over Bb7
            dlg.table.selectRow(row)
            got = []
            dlg.grip_selected.connect(lambda *a: got.append(a))
            dlg._on_grip_clicked(dlg.list_grips.item(0))
            fret, controllers, strings, root, ctype = got[0]
            self.assertEqual((root, ctype), ("Bb", "Dominant 9th"))
            self.assertEqual(len(strings), 3)
        finally:
            dlg.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
