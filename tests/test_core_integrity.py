"""Regression tests for copedant data integrity (defects D-02, D-07, D-08, D-09, D-20, D-22).

Run: .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import presets  # noqa: E402
from core.models import (  # noqa: E402
    CopedantChange,
    Neck,
    NeckType,
    SplitRule,
    StringPitch,
    migrate_half_stop_tokens,
    migrate_legacy_ids,
    shift_pedal_ids,
    undefined_rule_controllers,
)
from core.profile_manager import ProfileManager  # noqa: E402
from core.resolver import FretboardResolver  # noqa: E402


def note(neck: Neck, string: int, levers, fret: int = 0) -> str:
    states = FretboardResolver.resolve_neck_state(neck, fret, set(levers))
    return next(s.active_note_name for s in states if s.string_number == string)


def split_semantics(neck: Neck):
    """Rules expressed by the *changes* of their controllers, independent of controller IDs."""
    ctrls = {**neck.pedals, **neck.knee_levers}

    def key(token):
        base = token.replace("_HALF", "")
        half = token.endswith("_HALF")
        return (tuple(sorted(ctrls[base].changes.items())), half)

    return sorted(
        (s.string_number, tuple(sorted(key(c) for c in s.controllers)), s.semitone_delta, s.is_active)
        for s in neck.splits
    )


class TempProfileDirMixin:
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(ProfileManager, "STORAGE_DIR", Path(self._tmp.name) / "profiles")
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# Core model / resolver
# ---------------------------------------------------------------------------
class PresetIntegrityTests(unittest.TestCase):
    def test_all_factory_rules_reference_defined_controllers(self):
        for neck in presets.build_standard_d10_guitar().necks:
            with self.subTest(neck=neck.name):
                self.assertEqual(undefined_rule_controllers(neck), set())

    def test_12u_half_stop_splits_fire(self):  # D-08
        u = presets.build_gfi_12u_7p_5kl_3hs()
        self.assertEqual(note(u, 5, {"P1_HALF", "VL"}), "B3")   # half-stop rule: cancel
        self.assertEqual(note(u, 5, {"P1", "VL"}), "C4")        # full rule unchanged
        self.assertEqual(note(u, 4, {"P3_HALF", "LKL"}), "F4")  # half-stop rule: +1
        self.assertEqual(note(u, 5, {"P1_HALF"}), "C4")         # single half-stop +1
        self.assertEqual(note(u, 9, {"RKR", "P1_HALF"}), "D3")  # compound raise +3

    def test_base_split_still_applies_to_half_engagement_without_specific_rule(self):
        e9 = presets.build_standard_emmons_e9_10()
        # No half-specific rule: the full P3+LKL rule (stop at F#) still governs, as before.
        self.assertEqual(note(e9, 4, {"P3_HALF", "LKL"}), "F#4")

    def test_legacy_hs_tokens_are_migrated(self):  # D-08 for persisted setups
        neck = presets.build_gfi_12u_7p_5kl_3hs()
        neck.half_stops = []
        for s in neck.splits:
            s.controllers = [c.replace("_HALF", "HS") for c in s.controllers]
        self.assertEqual(undefined_rule_controllers(neck), {"P1HS", "P3HS", "P7HS"})
        self.assertTrue(migrate_half_stop_tokens(neck))
        self.assertEqual(undefined_rule_controllers(neck), set())
        self.assertEqual({h.controller_id for h in neck.half_stops}, {"P1", "P3", "P7"})
        self.assertEqual(note(neck, 5, {"P1_HALF", "VL"}), "B3")
        self.assertFalse(migrate_half_stop_tokens(neck))  # idempotent

    def test_roundtrip_keeps_source_profile_and_half_stops(self):
        neck = presets.build_gfi_12u_7p_5kl_3hs()
        neck.source_profile = "My 12U"
        again = Neck.from_dict(neck.to_dict())
        self.assertEqual(again.to_dict(), neck.to_dict())


class ControllerRemapTests(unittest.TestCase):
    def test_vl_rename_keeps_splits_and_pitches(self):  # D-07
        neck = presets.build_be_e9_3p_5kl_1hs()
        before = {(s, frozenset(c)): note(neck, s, c) for s in (5, 10) for c in ({"P1", "VL"}, {"P3", "VL"})}
        semantics = split_semantics(neck)

        migrate_legacy_ids(neck)

        self.assertNotIn("VL", neck.knee_levers)
        self.assertEqual(neck.knee_levers["LKV"].label, "LKV")
        self.assertEqual(undefined_rule_controllers(neck), set())
        self.assertEqual(split_semantics(neck), semantics)
        for (s, ctrls), expected in before.items():
            renamed = {"LKV" if c == "VL" else c for c in ctrls}
            self.assertEqual(note(neck, s, renamed), expected)

    def test_pedal_shift_round_trip_preserves_rules_and_labels(self):  # D-09
        neck = presets.build_be_c6_5p_4kl()
        original = neck.to_dict()
        semantics = split_semantics(neck)

        shift_pedal_ids(neck, +1)
        self.assertEqual(sorted(neck.pedals), ["P2", "P3", "P4", "P5", "P6"])
        self.assertEqual(neck.pedals["P2"].label, "P4")  # custom label kept
        self.assertEqual(split_semantics(neck), semantics)
        self.assertEqual(undefined_rule_controllers(neck), set())

        shift_pedal_ids(neck, -1)
        self.assertEqual(neck.to_dict(), original)

    def test_label_echoing_id_is_renumbered(self):
        neck = presets.build_standard_emmons_e9_10()
        shift_pedal_ids(neck, +1)
        self.assertEqual(neck.pedals["P2"].label, "Pedal 2 (A)")
        self.assertEqual(neck.pedals["P4"].label, "Pedal 4 (C)")


class ProfileManagerTests(TempProfileDirMixin, unittest.TestCase):
    def test_save_load_links_profile(self):
        neck = presets.build_standard_c6_10()
        ProfileManager.save_user_profile("My C6", neck)
        loaded = ProfileManager.load_user_profile("My C6")
        self.assertEqual(loaded.source_profile, "My C6")
        self.assertEqual(ProfileManager.list_user_profiles(), ["My C6"])

    def test_invalid_names_are_rejected(self):
        neck = presets.build_standard_c6_10()
        for bad in ("", "!!!", "active_guitar_setup"):
            with self.subTest(name=bad), self.assertRaises(ValueError):
                ProfileManager.save_user_profile(bad, neck)


# ---------------------------------------------------------------------------
# Qt dialogs (offscreen)
# ---------------------------------------------------------------------------
try:
    from PySide6.QtWidgets import QApplication, QMessageBox

    _APP = QApplication.instance() or QApplication([])

    def _delete_widget(w) -> None:
        """Really frees a dialog (deleteLater needs an event loop), so later tests stay fast."""
        from PySide6.QtCore import QCoreApplication, QEvent

        try:
            w.deleteLater()
        except RuntimeError:
            return
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    HAVE_QT = True
except Exception:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not available")
class CopedantEditorTests(TempProfileDirMixin, unittest.TestCase):
    def _editor(self, guitar, idx):
        from ui.copedant_editor_dialog import CopedantEditorDialog

        dlg = CopedantEditorDialog(neck=guitar.necks[idx], guitar=guitar, current_neck_idx=idx)
        self.addCleanup(_delete_widget, dlg)
        return dlg

    def test_apply_on_be_e9_keeps_split_semantics(self):  # D-07
        guitar = presets.build_standard_d10_guitar()
        idx = next(i for i, n in enumerate(guitar.necks) if n.name.startswith("BE E9"))
        semantics = split_semantics(guitar.necks[idx])
        dlg = self._editor(guitar, idx)
        dlg._apply_and_close()
        applied = guitar.necks[idx]
        self.assertEqual(undefined_rule_controllers(applied), set())
        self.assertEqual(split_semantics(applied), semantics)

    def test_apply_on_12u_3hs_keeps_half_stop_splits(self):  # D-07 + D-08
        guitar = presets.build_standard_d10_guitar()
        idx = next(i for i, n in enumerate(guitar.necks) if n.name.endswith("3HS"))
        dlg = self._editor(guitar, idx)
        dlg._apply_and_close()
        applied = guitar.necks[idx]
        self.assertEqual(undefined_rule_controllers(applied), set())
        self.assertEqual(note(applied, 5, {"P1_HALF", "LKV"}), "B3")
        self.assertEqual(note(applied, 5, {"P1", "LKV"}), "C4")

    def test_unknown_controller_is_preserved_not_rewritten(self):  # D-07
        guitar = presets.build_standard_d10_guitar()
        guitar.necks[0].splits.append(SplitRule(5, ["P1", "GHOST"], 0, description="dangling"))
        dlg = self._editor(guitar, 0)
        dlg._apply_and_close()
        self.assertIn(["P1", "GHOST"], [s.controllers for s in guitar.necks[0].splits])

    def test_franklin_toggle_remaps_rules(self):  # D-09
        guitar = presets.build_standard_d10_guitar()
        idx = next(i for i, n in enumerate(guitar.necks) if n.name.startswith("BE C6"))
        semantics = split_semantics(guitar.necks[idx])
        dlg = self._editor(guitar, idx)
        dlg._toggle_c6_pedal_offset(True)
        dlg._apply_and_close()
        neck = guitar.necks[idx]
        self.assertIn("Franklin", neck.pedals["P1"].label)
        self.assertEqual(split_semantics(neck), semantics)
        self.assertEqual(undefined_rule_controllers(neck), set())

    def test_switching_necks_keeps_unapplied_edits(self):  # D-22
        guitar = presets.build_standard_d10_guitar()
        dlg = self._editor(guitar, 0)
        dlg.edit_author.setText("Edited Author")
        dlg.combo_copedant.setCurrentIndex(1)  # switch away...
        dlg.combo_copedant.setCurrentIndex(0)  # ...and back
        self.assertEqual(dlg.edit_author.text(), "Edited Author")
        dlg._apply_and_close()
        self.assertEqual(guitar.necks[0].author, "Edited Author")

    def test_apply_on_factory_neck_writes_no_profile(self):  # D-22
        guitar = presets.build_standard_d10_guitar()
        dlg = self._editor(guitar, 0)
        dlg._apply_and_close()
        self.assertEqual(ProfileManager.list_user_profiles(), [])

    def test_apply_on_linked_neck_updates_its_profile(self):  # D-02 / D-22
        guitar = presets.build_standard_d10_guitar()
        linked = deepcopy(guitar.necks[1])
        linked.source_profile = "My C6"
        guitar.necks.append(linked)
        dlg = self._editor(guitar, len(guitar.necks) - 1)
        dlg.edit_author.setText("Me")
        dlg._apply_and_close()
        self.assertEqual(ProfileManager.load_user_profile("My C6").author, "Me")
        self.assertEqual(guitar.necks[1].author, presets.build_standard_c6_10().author)


@unittest.skipUnless(HAVE_QT, "PySide6 not available")
class ProfileDialogTests(TempProfileDirMixin, unittest.TestCase):
    def test_save_profile_does_not_crash_and_leaves_active_neck(self):  # D-20
        from ui.manage_profiles_dialog import ProfileManagerDialog

        neck = presets.build_standard_emmons_e9_10()
        before = neck.to_dict()
        dlg = ProfileManagerDialog(current_neck=neck)
        self.addCleanup(_delete_widget, dlg)
        dlg.txt_profile_name.setText("My E9")
        with mock.patch.object(QMessageBox, "information"):
            dlg._save_profile()
        self.assertEqual(ProfileManager.list_user_profiles(), ["My E9"])
        self.assertEqual(ProfileManager.load_user_profile("My E9").source_profile, "My E9")
        self.assertEqual(neck.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
