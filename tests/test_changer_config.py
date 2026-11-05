"""Changer configuration (E-26) and saved profiles in the copedant editor's dropdown (D-42).

Run: .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import presets  # noqa: E402
from core.models import (  # noqa: E402
    DEFAULT_CHANGER,
    Neck,
    changer_usage,
    changer_violations,
)
from tests.test_core_integrity import TempProfileDirMixin  # noqa: E402


def overloaded_e9() -> Neck:
    """Standard E9 with 4 raises on string 4 (P3, LKL + P1, RKL)."""
    neck = presets.build_standard_emmons_e9_10()
    neck.pedals["P1"].changes[4] = 1
    neck.knee_levers["RKL"].changes[4] = 1
    return neck


class ChangerModelTests(unittest.TestCase):
    def test_factory_presets_fit_the_default_changer(self):
        for neck in presets.build_standard_d10_guitar().necks:
            self.assertEqual((neck.changer_raises, neck.changer_lowers), DEFAULT_CHANGER)
            self.assertEqual(changer_violations(neck), [], neck.name)

    def test_usage_counts_controllers_per_direction(self):
        ups, downs = changer_usage(presets.build_standard_emmons_e9_10())[4]
        self.assertEqual(sorted(ups), ["LKL", "P3"])
        self.assertEqual(downs, ["LKR"])

    def test_violation_and_custom_limits(self):
        neck = overloaded_e9()
        v = changer_violations(neck)
        self.assertEqual(len(v), 1)
        self.assertEqual((v[0].string_number, v[0].direction, v[0].limit), (4, "raise", 3))
        self.assertEqual(sorted(v[0].controllers), ["LKL", "P1", "P3", "RKL"])
        self.assertIn("String 4", v[0].message)
        neck.changer_raises, neck.changer_lowers = 4, 2
        self.assertEqual(changer_violations(neck), [])
        neck.changer_lowers = 0
        self.assertEqual({x.direction for x in changer_violations(neck)}, {"lower"})

    def test_serialization_round_trip_and_default(self):
        neck = presets.build_standard_emmons_e9_10()
        neck.changer_raises, neck.changer_lowers = 4, 2
        data = neck.to_dict()
        self.assertEqual(data["changer"], {"raises": 4, "lowers": 2})
        back = Neck.from_dict(data)
        self.assertEqual((back.changer_raises, back.changer_lowers), (4, 2))
        del data["changer"]  # files saved before E-26
        old = Neck.from_dict(data)
        self.assertEqual((old.changer_raises, old.changer_lowers), DEFAULT_CHANGER)


def _delete_widget(w):
    from PySide6.QtCore import QCoreApplication, QEvent
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


class EditorChangerTests(TempProfileDirMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _editor(self, guitar, idx=0):
        from ui.copedant_editor_dialog import CopedantEditorDialog
        dlg = CopedantEditorDialog(neck=guitar.necks[idx], guitar=guitar, current_neck_idx=idx)
        self.addCleanup(_delete_widget, dlg)
        return dlg

    def test_controls_load_and_presets_set_limits(self):
        guitar = presets.build_standard_d10_guitar()
        dlg = self._editor(guitar)
        self.assertEqual((dlg.spin_raises.value(), dlg.spin_lowers.value()), (3, 3))
        self.assertIn("3 up", dlg.combo_changer.currentText())
        row = next(i for i in range(dlg.combo_changer.count()) if dlg.combo_changer.itemData(i) == (4, 2))
        dlg.combo_changer.setCurrentIndex(row)
        self.assertEqual((dlg.neck.changer_raises, dlg.neck.changer_lowers), (4, 2))
        self.assertEqual((dlg.spin_raises.value(), dlg.spin_lowers.value()), (4, 2))
        dlg.spin_lowers.setValue(5)
        self.assertEqual(dlg.combo_changer.currentText(), "Custom")
        self.assertEqual(dlg.neck.changer_lowers, 5)
        self.assertIn("✔", dlg.lbl_changer_status.text())

    def test_apply_is_blocked_until_the_changer_fits(self):
        guitar = presets.build_standard_d10_guitar()
        original = deepcopy(guitar.necks[0])
        dlg = self._editor(guitar)
        dlg._adjust_changer_delta(dlg.neck.pedals["P1"], 4, 1)
        dlg._adjust_changer_delta(dlg.neck.knee_levers["RKL"], 4, 1)  # 4th raise on string 4
        self.assertIn("⚠", dlg.lbl_changer_status.text())
        self.assertIn(("P1", 4), dlg._over_limit)
        with mock.patch("ui.copedant_editor_dialog.QMessageBox.warning") as warn:
            dlg._apply_and_close()
        warn.assert_called_once()
        self.assertIn("String 4", warn.call_args[0][2])
        self.assertEqual(guitar.necks[0].to_dict(), original.to_dict())  # nothing applied
        self.assertNotEqual(dlg.result(), dlg.DialogCode.Accepted)

        dlg.spin_raises.setValue(4)  # a 4-raise changer holds it
        with mock.patch("ui.copedant_editor_dialog.QMessageBox.warning") as warn:
            dlg._apply_and_close()
        warn.assert_not_called()
        self.assertEqual(guitar.necks[0].changer_raises, 4)
        self.assertEqual(guitar.necks[0].pedals["P1"].changes[4], 1)

    def test_apply_checks_every_edited_neck(self):
        guitar = presets.build_standard_d10_guitar()
        dlg = self._editor(guitar, 0)
        dlg._adjust_changer_delta(dlg.neck.pedals["P1"], 4, 1)
        dlg._adjust_changer_delta(dlg.neck.knee_levers["RKL"], 4, 1)
        dlg.combo_copedant.setCurrentIndex(1)  # leave the overloaded neck
        self.assertEqual(dlg.current_neck_idx, 1)
        with mock.patch("ui.copedant_editor_dialog.QMessageBox.warning") as warn:
            dlg._apply_and_close()
        warn.assert_called_once()
        self.assertEqual(dlg.current_neck_idx, 0)  # switched back to show the problem


class EditorProfileListTests(TempProfileDirMixin, unittest.TestCase):  # D-42
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_copy_to_profile_adds_the_edited_tuning(self):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        from core.models import SteelGuitar
        from core.profile_manager import ProfileManager
        from ui.copedant_editor_dialog import CopedantEditorDialog

        ProfileManager.save_profile("My Rig", SteelGuitar("x", [presets.build_standard_c6_10()]))
        guitar = presets.build_standard_d10_guitar()
        n_before = len(guitar.necks)
        dlg = CopedantEditorDialog(neck=guitar.necks[0], guitar=guitar, current_neck_idx=0)
        self.addCleanup(_delete_widget, dlg)
        items = [dlg.combo_copedant.itemText(i) for i in range(dlg.combo_copedant.count())]
        self.assertEqual(len(items), n_before)  # the editor lists only the open profile's tunings
        dlg.edit_author.setText("Edited")
        with mock.patch.object(QInputDialog, "getItem", return_value=("My Rig", True)), \
                mock.patch.object(QMessageBox, "information"):
            dlg._copy_to_profile()
        rig = ProfileManager.load_profile("My Rig")
        self.assertEqual(len(rig.necks), 2)
        self.assertEqual(rig.necks[-1].author, "Edited")
        self.assertEqual(len(guitar.necks), n_before)  # the open profile is unchanged


if __name__ == "__main__":
    unittest.main()
