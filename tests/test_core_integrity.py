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
    def test_profile_holds_several_tunings(self):
        from core.models import SteelGuitar

        guitar = SteelGuitar("x", [presets.build_standard_emmons_e9_10(), presets.build_standard_c6_10()])
        ProfileManager.save_profile("My D10", guitar)
        loaded = ProfileManager.load_profile("My D10")
        self.assertEqual(loaded.profile, "My D10")
        self.assertEqual([n.name for n in loaded.necks], [n.name for n in guitar.necks])
        for a, b in zip(loaded.necks, guitar.necks):
            self.assertEqual(all_stance_notes(a), all_stance_notes(b))
        self.assertEqual(ProfileManager.list_user_profiles(), ["My D10"])
        self.assertEqual(guitar.profile, "")  # saving does not change the guitar

    def test_legacy_single_neck_profile_loads_as_one_tuning(self):
        import json

        c6 = presets.build_standard_c6_10()
        path = ProfileManager.ensure_storage_dir() / "Old C6.json"
        path.write_text(json.dumps(c6.to_dict()), encoding="utf-8")
        loaded = ProfileManager.load_profile("Old C6")
        self.assertEqual(len(loaded.necks), 1)
        self.assertEqual(all_stance_notes(loaded.necks[0]), all_stance_notes(c6))

    def test_invalid_names_are_rejected(self):
        from core.models import SteelGuitar

        guitar = SteelGuitar("x", [presets.build_standard_c6_10()])
        for bad in ("", "!!!", "active_guitar_setup"):
            with self.subTest(name=bad), self.assertRaises(ValueError):
                ProfileManager.save_profile(bad, guitar)

    def test_add_tuning_rename_and_list_all(self):
        from core.profile_manager import FACTORY_PROFILE

        e9 = presets.build_standard_emmons_e9_10()
        self.assertEqual(ProfileManager.add_tuning_to_profile("Mine", e9), e9.name)
        self.assertEqual(ProfileManager.add_tuning_to_profile("Mine", e9), f"{e9.name} (2)")
        self.assertEqual(ProfileManager.rename_profile("Mine", "Gig Rig"), "Gig Rig")
        self.assertEqual(ProfileManager.list_user_profiles(), ["Gig Rig"])
        tunings = dict(ProfileManager.list_all_tunings())
        self.assertEqual(len(tunings[FACTORY_PROFILE]), len(presets.build_standard_d10_guitar().necks))
        self.assertEqual(len(tunings["Gig Rig"]), 2)

    def test_startup_profile_and_tuning(self):
        from core.profile_manager import FACTORY_PROFILE, load_startup_guitar
        from core.models import SteelGuitar

        ProfileManager.save_profile("Gig", SteelGuitar("x", [presets.build_standard_emmons_e9_10(),
                                                             presets.build_standard_c6_10()]))
        guitar, tuning = load_startup_guitar(
            {"startup_mode": "profile", "startup_profile": "Gig", "startup_tuning": "10-String C6"})
        self.assertEqual((guitar.profile, tuning), ("Gig", "10-String C6"))
        # A missing startup profile falls back to the last session, then to Factory.
        guitar, tuning = load_startup_guitar({"startup_mode": "profile", "startup_profile": "Gone"})
        self.assertEqual((guitar.profile, tuning), (FACTORY_PROFILE, ""))
        # The last session remembers which profile was open.
        saved = ProfileManager.load_profile("Gig")
        saved.save_to_file(str(ProfileManager.active_setup_path()))
        guitar, _ = load_startup_guitar({"startup_mode": "last"})
        self.assertEqual(guitar.profile, "Gig")


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

    def test_duplicate_adds_a_tuning_to_the_open_profile(self):
        guitar = presets.build_standard_d10_guitar()
        n_before = len(guitar.necks)
        dlg = self._editor(guitar, 1)
        dlg._duplicate_copedant()
        self.assertEqual(len(guitar.necks), n_before + 1)
        self.assertEqual(guitar.necks[-1].name, f"{guitar.necks[1].name} (Copy)")
        self.assertEqual(ProfileManager.list_user_profiles(), [])
        items = [dlg.combo_copedant.itemText(i) for i in range(dlg.combo_copedant.count())]
        self.assertEqual(len(items), n_before + 1)  # only the open profile's tunings


@unittest.skipUnless(HAVE_QT, "PySide6 not available")
class ProfileDialogTests(TempProfileDirMixin, unittest.TestCase):
    def test_save_profile_does_not_crash_and_leaves_open_setup(self):  # D-20
        from PySide6.QtWidgets import QInputDialog
        from ui.manage_profiles_dialog import ProfileManagerDialog

        guitar = presets.build_standard_d10_guitar()
        before = [n.to_dict() for n in guitar.necks]
        dlg = ProfileManagerDialog(guitar, settings={})
        self.addCleanup(_delete_widget, dlg)
        saved = []
        dlg.saved_as.connect(saved.append)
        with mock.patch.object(QInputDialog, "getText", return_value=("My Setup", True)), \
                mock.patch.object(QMessageBox, "information"):
            dlg._save_profile()
        self.assertEqual(ProfileManager.list_user_profiles(), ["My Setup"])
        self.assertEqual(len(ProfileManager.load_profile("My Setup").necks), len(guitar.necks))
        self.assertEqual(saved, ["My Setup"])
        self.assertEqual([n.to_dict() for n in guitar.necks], before)

    def test_startup_controls_write_settings(self):
        import core.settings as settings
        from ui.manage_profiles_dialog import ProfileManagerDialog

        guitar = presets.build_standard_d10_guitar()
        prefs = {}
        with mock.patch.object(settings, "SETTINGS_FILE", Path(self._tmp.name) / "s.json"), \
                mock.patch.object(settings, "SETTINGS_DIR", Path(self._tmp.name)), \
                mock.patch("ui.manage_profiles_dialog.save_settings") as save:
            dlg = ProfileManagerDialog(guitar, settings=prefs)
            self.addCleanup(_delete_widget, dlg)
            dlg.radio_profile.setChecked(True)
            dlg.combo_startup_tuning.setCurrentIndex(1)
        self.assertTrue(save.called)
        self.assertEqual(prefs["startup_mode"], "profile")
        self.assertEqual(prefs["startup_profile"], "")
        self.assertEqual(prefs["startup_tuning"], guitar.necks[1].name)


def all_stance_notes(neck: Neck):
    """Sounding note of every string under no controller, each controller, and each half-stop and
    split combination, through the resolver (so a round trip is checked musically)."""
    stances = [set()] + [{c} for c in list(neck.pedals) + list(neck.knee_levers)]
    stances += [{f"{h.controller_id}_HALF"} for h in neck.half_stops if h.is_active]
    stances += [set(s.controllers) for s in neck.splits]
    return [[(st.string_number, st.active_midi) for st in
             FretboardResolver.resolve_neck_state(neck, 3, stance)] for stance in stances]


class CopedantFileTests(TempProfileDirMixin, unittest.TestCase):
    """Export / import of single copedants and profiles (JSON, `Neck.to_dict`)."""

    def _path(self, name):
        return Path(self._tmp.name) / name

    def test_export_import_round_trip_sounds_the_same(self):
        from core.profile_manager import export_neck, read_necks_file

        for neck in presets.build_standard_d10_guitar().necks:
            with self.subTest(neck=neck.name):
                neck.source_profile = "Local Link"
                path = self._path("cop.json")
                export_neck(neck, path)
                (back,) = read_necks_file(path)
                self.assertEqual(back.source_profile, "")
                expected = neck.to_dict()
                expected["source_profile"] = ""
                self.assertEqual(back.to_dict(), expected)
                self.assertEqual(all_stance_notes(back), all_stance_notes(neck))

    def test_reads_setup_files_and_rejects_others(self):
        import json
        from core.profile_manager import read_necks_file

        guitar = presets.build_standard_d10_guitar()
        guitar.save_to_file(str(self._path("setup.json")))
        self.assertEqual([n.name for n in read_necks_file(self._path("setup.json"))],
                         [n.name for n in guitar.necks])
        for bad in ([1, 2], {"hello": 1}, {"necks": []}):
            self._path("bad.json").write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_necks_file(self._path("bad.json"))

    def test_import_profile_file_never_overwrites(self):
        from core.models import SteelGuitar

        e9 = presets.build_standard_emmons_e9_10()
        safe = ProfileManager.sanitize_name(e9.name)
        ProfileManager.save_profile(safe, SteelGuitar("x", [e9]))
        ProfileManager.export_profile(safe, self._path("e9.json"))
        name = ProfileManager.import_profile_file(self._path("e9.json"))
        self.assertEqual(name, f"{safe} 2")
        (imported,) = ProfileManager.load_profile(name).necks
        self.assertEqual(all_stance_notes(imported), all_stance_notes(e9))
        self.assertEqual(len(ProfileManager.list_user_profiles()), 2)

        # A full setup becomes one profile holding every tuning.
        guitar = presets.build_standard_d10_guitar()
        guitar.save_to_file(str(self._path("setup.json")))
        name = ProfileManager.import_profile_file(self._path("setup.json"))
        self.assertEqual(name, "setup")
        self.assertEqual(len(ProfileManager.load_profile(name).necks), len(guitar.necks))
        with self.assertRaises(FileNotFoundError):
            ProfileManager.export_profile("Nope", self._path("x.json"))


@unittest.skipUnless(HAVE_QT, "PySide6 not available")
class ProfileDialogFileTests(TempProfileDirMixin, unittest.TestCase):
    def test_dialog_import_and_export_buttons(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from core.profile_manager import export_neck
        from ui.manage_profiles_dialog import ProfileManagerDialog

        src = Path(self._tmp.name) / "c6.json"
        c6 = presets.build_standard_c6_10()
        export_neck(c6, src)
        dlg = ProfileManagerDialog(presets.build_standard_d10_guitar(), settings={})
        self.addCleanup(_delete_widget, dlg)
        with mock.patch.object(QFileDialog, "getOpenFileName", return_value=(str(src), "")),                 mock.patch.object(QMessageBox, "information"):
            dlg._import_profiles()
        name = ProfileManager.sanitize_name(c6.name)
        self.assertEqual(ProfileManager.list_user_profiles(), [name])
        self.assertEqual(dlg._selected_key(), name)
        self.assertEqual(dlg.list_tunings.count(), 1)

        out = Path(self._tmp.name) / "out.json"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(out), "")),                 mock.patch.object(QMessageBox, "information"):
            dlg._export_selected()
        from core.profile_manager import read_necks_file
        (back,) = read_necks_file(out)
        self.assertEqual(all_stance_notes(back), all_stance_notes(c6))


if __name__ == "__main__":
    unittest.main()
