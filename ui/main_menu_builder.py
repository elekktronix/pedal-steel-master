"""Menu builder decoupling all menubar actions and submenus from MainWindow."""

from PySide6.QtGui import QAction, QActionGroup


class MainMenuBuilder:
    @classmethod
    def build_menubar(cls, main_window):
        menubar = main_window.menuBar()

        # 1. File Menu
        file_menu = menubar.addMenu("&File")

        action_import = QAction("&Import Setup (JSON)...", main_window)
        action_import.triggered.connect(main_window._load_file)
        file_menu.addAction(action_import)

        action_export = QAction("&Export Setup (JSON)...", main_window)
        action_export.triggered.connect(main_window._save_file)
        file_menu.addAction(action_export)

        file_menu.addSeparator()

        action_pdf = QAction("📄 Export PDF Reference Sheet...", main_window)
        action_pdf.triggered.connect(main_window._export_pdf)
        file_menu.addAction(action_pdf)

        action_snap = QAction("📋 Copy Fretboard Image to Clipboard", main_window)
        action_snap.triggered.connect(main_window._copy_fretboard_snapshot)
        file_menu.addAction(action_snap)

        file_menu.addSeparator()

        action_exit = QAction("E&xit", main_window)
        action_exit.triggered.connect(main_window.close)
        file_menu.addAction(action_exit)

        # 2. View Menu (Sequencer dock toggle + tool popouts)
        view_menu = menubar.addMenu("&View")

        action_toggle_seq = main_window.dock_sequencer.toggleViewAction()
        action_toggle_seq.setText("Show Progression Sequencer Dock")
        view_menu.addAction(action_toggle_seq)

        action_pop_seq = QAction("⏏️ Pop Out Sequencer (Floating)", main_window)
        action_pop_seq.triggered.connect(main_window._pop_out_sequencer)
        view_menu.addAction(action_pop_seq)

        view_menu.addSeparator()

        action_stance_chords = QAction("🔎 Current Stance Chord Inspector...", main_window)
        action_stance_chords.triggered.connect(main_window._open_stance_chord_inspector)
        view_menu.addAction(action_stance_chords)

        action_voice_pop = QAction("🔍 Chord Finder (Chord Atlas: Find a chord)", main_window)
        action_voice_pop.triggered.connect(main_window._open_chord_finder)
        view_menu.addAction(action_voice_pop)

        action_scale_pop = QAction("🎼 Scale Finder & Builder Window", main_window)
        action_scale_pop.triggered.connect(main_window._toggle_scale_popout)
        view_menu.addAction(action_scale_pop)

        action_circle_pop = QAction("⭕ Circle of Fifths Songwriter Window", main_window)
        action_circle_pop.triggered.connect(main_window._toggle_circle_popout)
        view_menu.addAction(action_circle_pop)

        # 3. Copedant Menu
        copedant_menu = menubar.addMenu("&Copedant")
        main_window.copedant_select_menu = copedant_menu.addMenu("&Select Copedant")
        main_window._rebuild_copedant_menu()

        copedant_menu.addSeparator()

        action_import_cop = QAction("&Import Copedant (.cop / .json)...", main_window)
        action_import_cop.setShortcut("Ctrl+I")
        action_import_cop.triggered.connect(main_window._open_import_copedant_file)
        copedant_menu.addAction(action_import_cop)

        action_splits = QAction("Mechanical &Splits Manager...", main_window)
        action_splits.triggered.connect(main_window._open_splits_manager)
        copedant_menu.addAction(action_splits)

        action_compare = QAction("&Compare Copedants...", main_window)
        action_compare.triggered.connect(main_window._open_copedant_compare)
        copedant_menu.addAction(action_compare)

        action_atlas = QAction("Chord &Atlas (all chords on this copedant)...", main_window)
        action_atlas.triggered.connect(main_window._open_chord_atlas)
        copedant_menu.addAction(action_atlas)

        main_window.action_c6_franklin_offset = QAction("Offset C6 Pedals +1 (Franklin P1)", main_window, checkable=True)
        main_window.action_c6_franklin_offset.triggered.connect(main_window._toggle_c6_menu_pedal_offset)
        copedant_menu.addAction(main_window.action_c6_franklin_offset)

        # 4. Preferences Menu
        pref_menu = menubar.addMenu("&Preferences")

        display_menu = pref_menu.addMenu("Fretted Circle Display")
        main_window.disp_group = QActionGroup(main_window)
        main_window.disp_group.setExclusive(True)

        main_window.action_disp_intervals = QAction("Show Intervals (R, 3, 5)", main_window, checkable=True)
        main_window.action_disp_intervals.setChecked(True)
        main_window.action_disp_intervals.triggered.connect(lambda: main_window._set_display_mode("intervals"))
        main_window.disp_group.addAction(main_window.action_disp_intervals)
        display_menu.addAction(main_window.action_disp_intervals)

        main_window.action_disp_notes = QAction("Show Plucked Notes (E, G#, B)", main_window, checkable=True)
        main_window.action_disp_notes.triggered.connect(lambda: main_window._set_display_mode("notes"))
        main_window.disp_group.addAction(main_window.action_disp_notes)
        display_menu.addAction(main_window.action_disp_notes)

        spelling_menu = pref_menu.addMenu("♯/♭ Note Spelling")
        main_window.spelling_group = QActionGroup(main_window)
        main_window.spelling_group.setExclusive(True)
        current_spelling = main_window.settings.get("note_spelling", "sharps")
        for pref, label in (("sharps", "Sharps (C#, D#, F#, G#, A#)"), ("flats", "Flats (Db, Eb, Gb, Ab, Bb)")):
            act = QAction(label, main_window, checkable=True)
            act.setChecked(pref == current_spelling)
            act.triggered.connect(lambda _=False, p=pref: main_window._set_note_spelling(p))
            main_window.spelling_group.addAction(act)
            spelling_menu.addAction(act)
        spelling_menu.addSeparator()
        main_window.action_key_aware_spelling = QAction(
            "Key-aware tools spell by key signature (Circle of Fifths, Triads Over Chord)", main_window, checkable=True)
        main_window.action_key_aware_spelling.setToolTip(
            "On: diatonic and triad names follow the key (Bb in F, A# in B). Off: they use the sharps/flats choice above.")
        main_window.action_key_aware_spelling.setChecked(main_window.settings.get("key_aware_spelling", True))
        main_window.action_key_aware_spelling.toggled.connect(main_window._set_key_aware_spelling)
        spelling_menu.addAction(main_window.action_key_aware_spelling)

        temp_menu = pref_menu.addMenu("🎵 Audio Temperament")
        main_window.temp_group = QActionGroup(main_window)
        main_window.temp_group.setExclusive(True)

        main_window.action_12tet = QAction("Equal Temperament (12-TET)", main_window, checkable=True)
        main_window.action_12tet.setChecked(not main_window.settings.get("use_newman_tuning", False))
        main_window.action_12tet.triggered.connect(lambda: main_window._set_temperament(False))
        main_window.temp_group.addAction(main_window.action_12tet)
        temp_menu.addAction(main_window.action_12tet)

        main_window.action_newman_tune = QAction("Jeff Newman Compensated Tuning", main_window, checkable=True)
        main_window.action_newman_tune.setChecked(main_window.settings.get("use_newman_tuning", False))
        main_window.action_newman_tune.triggered.connect(lambda: main_window._set_temperament(True))
        main_window.temp_group.addAction(main_window.action_newman_tune)
        temp_menu.addAction(main_window.action_newman_tune)

        temp_menu.addSeparator()
        main_window.action_pedal_swells = QAction("Pedal && Bar Swells (bend ringing notes)", main_window, checkable=True)
        main_window.action_pedal_swells.setChecked(main_window.settings.get("pedal_swells", True))
        main_window.action_pedal_swells.toggled.connect(main_window._toggle_pedal_swells)
        temp_menu.addAction(main_window.action_pedal_swells)

        main_window.action_inversions = QAction("Show Chord Inversions Above Bar", main_window, checkable=True)
        main_window.action_inversions.setChecked(main_window.settings.get("show_inversions", True))
        main_window.action_inversions.triggered.connect(main_window._toggle_inversions_preference)
        pref_menu.addAction(main_window.action_inversions)

        main_window.action_nns = QAction("Show Nashville Numbers [1, 4, 5] Above Bar", main_window, checkable=True)
        main_window.action_nns.setChecked(main_window.settings.get("show_nashville", True))
        main_window.action_nns.triggered.connect(main_window._toggle_nns_menu_preference)
        pref_menu.addAction(main_window.action_nns)

        main_window.action_scale_box = QAction("Show Scale Pocket Box on Fretboard", main_window, checkable=True)
        main_window.action_scale_box.setChecked(main_window.settings.get("show_scale_box", True))
        main_window.action_scale_box.triggered.connect(main_window._toggle_scale_box_menu_preference)
        pref_menu.addAction(main_window.action_scale_box)

        pref_menu.addSeparator()

        theme_menu = pref_menu.addMenu("🎨 App Theme")
        main_window.theme_group = QActionGroup(main_window)
        main_window.theme_group.setExclusive(True)

        main_window.action_dark = QAction("Dark Mode", main_window, checkable=True)
        main_window.action_dark.setChecked(main_window.settings.get("theme", "dark") == "dark")
        main_window.action_dark.triggered.connect(lambda: main_window._set_theme("dark"))
        main_window.theme_group.addAction(main_window.action_dark)
        theme_menu.addAction(main_window.action_dark)

        main_window.action_light = QAction("Light Mode", main_window, checkable=True)
        main_window.action_light.setChecked(main_window.settings.get("theme", "dark") == "light")
        main_window.action_light.triggered.connect(lambda: main_window._set_theme("light"))
        main_window.theme_group.addAction(main_window.action_light)
        theme_menu.addAction(main_window.action_light)