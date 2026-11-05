"""Profiles as groups of tunings in the main window: Factory / user profile switching, startup
default tuning, the tuning browser, and the layout under the fretboard (Copedant button, bar row
with the feasibility badge, compact string grips).

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
from core.models import SteelGuitar  # noqa: E402
from core.profile_manager import FACTORY_PROFILE, ProfileManager  # noqa: E402
from core.resolver import FretboardResolver  # noqa: E402

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

_APP = QApplication.instance() or QApplication([])

from tests.test_features import FakeAudio, destroy_window  # noqa: E402


class ProfileWindowTests(unittest.TestCase):
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

    def _gig_profile(self):
        guitar = SteelGuitar("x", [presets.build_standard_c6_10(), presets.build_standard_emmons_e9_10()])
        ProfileManager.save_profile("Gig", guitar)
        return guitar

    def test_layout_under_the_fretboard(self):
        w = self._window()
        self.assertEqual(w.btn_edit_copedant.text(), "⚙️ Copedant")
        layout = w.centralWidget().layout()
        order = [layout.itemAt(i).widget() or layout.itemAt(i).layout() for i in range(layout.count())]
        canvas_at = order.index(w.canvas)
        bar_row = order[canvas_at + 1]
        bar_widgets = [bar_row.itemAt(i).widget() for i in range(bar_row.count())]
        self.assertIn(w.fret_slider, bar_widgets)
        self.assertIn(w.lever_panel.feasibility_bar, bar_widgets)
        self.assertIs(order[canvas_at + 2], w.lever_panel)
        self.assertGreater(order.index(w.star_map_box), canvas_at + 2)

    def test_grip_chips_grouped_and_named(self):
        w = self._window()
        e9 = next(i for i, n in enumerate(w.guitar.necks) if n.name == presets.build_standard_emmons_e9_10().name)
        w._select_copedant_index(e9)
        texts = [b.text() for b, _ in w.grip_bar.grip_buttons]
        self.assertIn("8-6-5", texts)
        self.assertIn("8-5", texts)
        w.grip_bar.apply_pocket({8, 6, 5})
        self.assertIn("Group 3", w.grip_bar.lbl_selected.text())
        w.grip_bar.apply_pocket({9, 2})
        self.assertIn("Custom pocket (strings 9-2)", w.grip_bar.lbl_selected.text())

    def test_switch_profile_and_back_to_factory(self):
        self._gig_profile()
        w = self._window()
        self.assertEqual(w.guitar.profile, FACTORY_PROFILE)
        self.assertEqual(w.combo_profile.currentData(), FACTORY_PROFILE)
        self.assertEqual(w.combo_profile.findData("Gig"), 1)

        w.combo_profile.setCurrentIndex(1)  # the Profile selector opens the group
        self.assertEqual(w.guitar.profile, "Gig")
        self.assertEqual(w.combo_copedant.count(), 2)  # only Gig's tunings in the Tuning selector
        # Edits to a user profile are saved to its file.
        w.guitar.necks[0].author = "Me"
        w._on_copedant_modified()
        self.assertEqual(ProfileManager.load_profile("Gig").necks[0].author, "Me")

        self.assertTrue(w.switch_profile(FACTORY_PROFILE, 1))
        self.assertEqual(len(w.guitar.necks), len(presets.build_standard_d10_guitar().necks))
        self.assertEqual(w.current_neck_idx, 1)

    def test_leaving_modified_factory_asks_first(self):
        self._gig_profile()
        w = self._window()
        w.guitar.necks[0].author = "Changed"
        with mock.patch.object(QMessageBox, "exec"), mock.patch.object(QMessageBox, "clickedButton", return_value=None):
            self.assertFalse(w.switch_profile("Gig"))  # Cancel keeps the factory edits
        self.assertEqual(w.guitar.profile, FACTORY_PROFILE)
        self.assertEqual(w.combo_profile.currentData(), FACTORY_PROFILE)
        self.assertIn("modified", w.combo_profile.currentText())
        with mock.patch.object(w, "_confirm_leave_profile", return_value=True):
            self.assertTrue(w.switch_profile("Gig"))
        self.assertEqual(w.guitar.profile, "Gig")

    def test_startup_default_profile_and_tuning(self):
        import core.settings as settings

        self._gig_profile()
        settings.save_settings({"startup_mode": "profile", "startup_profile": "Gig",
                                "startup_tuning": presets.build_standard_emmons_e9_10().name})
        w = self._window()
        self.assertEqual(w.guitar.profile, "Gig")
        self.assertEqual(w.guitar.necks[w.current_neck_idx].name, presets.build_standard_emmons_e9_10().name)
        self.assertEqual(w.combo_copedant.currentIndex(), 1)
        # The resolved pitches are the profile's own copedant (E9 string 3 = G#4, MIDI 68).
        strings = FretboardResolver.resolve_neck_state(w.guitar.necks[w.current_neck_idx], 0, set())
        self.assertEqual(next(s.active_midi for s in strings if s.string_number == 3), 68)

    def test_set_current_tuning_as_startup(self):
        w = self._window()
        w._select_copedant_index(2)
        with mock.patch.object(QMessageBox, "information"):
            w._set_current_tuning_as_startup()
        self.assertEqual(w.settings["startup_mode"], "profile")
        self.assertEqual(w.settings["startup_profile"], FACTORY_PROFILE)
        self.assertEqual(w.settings["startup_tuning"], w.guitar.necks[2].name)

    def test_tuning_browser_lists_all_and_copies(self):
        from ui.tuning_browser_dialog import TuningBrowserDialog

        self._gig_profile()
        w = self._window()
        dlg = TuningBrowserDialog(w.guitar)
        self.addCleanup(destroy_window, dlg)
        self.assertEqual(dlg.tree.topLevelItemCount(), 2)  # Factory + Gig
        gig = dlg.tree.topLevelItem(1)
        self.assertEqual(gig.childCount(), 2)
        dlg.copy_requested.connect(w._add_tuning_to_open_profile)
        n_before = len(w.guitar.necks)
        dlg.tree.setCurrentItem(gig.child(0))
        dlg._copy()
        self.assertEqual(len(w.guitar.necks), n_before + 1)
        self.assertEqual(w.current_neck_idx, n_before)
        self.assertEqual(w.guitar.necks[-1].name, "10-String C6 (2)")  # unique within the profile

        dlg.edit_filter.setText("zzz-no-match")
        self.assertTrue(all(dlg.tree.topLevelItem(i).isHidden() for i in range(2)))


if __name__ == "__main__":
    unittest.main()
