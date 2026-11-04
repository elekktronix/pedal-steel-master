"""Application entry point."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtWidgets import QApplication, QSplashScreen
from ui.app_icon import app_icon, set_windows_app_id, splash_pixmap
from ui.main_window import MainWindow

LOG_FILE = Path.home() / ".psg_visualizer" / "app.log"


def configure_logging() -> None:
    """Logs to ~/.psg_visualizer/app.log (rotating) and to stderr (D-33)."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(logging.WARNING)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console)


def main():
    configure_logging()
    set_windows_app_id()  # taskbar shows the app's icon, not python.exe's
    app = QApplication(sys.argv)
    app.setApplicationName("Pedal Steel Master")
    app.setWindowIcon(app_icon())  # inherited by every window and dialog
    splash = QSplashScreen(splash_pixmap())
    splash.show()
    app.processEvents()
    window = MainWindow()
    window.show()
    splash.finish(window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
