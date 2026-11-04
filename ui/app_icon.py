"""App icon (a pedal steel guitar) for every window, the Windows taskbar and the splash screen.

Sources: assets/icons/app_icon.svg (48 px and up) and app_icon_small.svg (16-32 px, bolder shapes).
Both are rendered to pixmaps here, so no SVG icon-engine plugin is needed at runtime.
Regenerate the Windows .ico (for shortcuts / packaging) with:  python -m ui.app_icon
"""

import logging
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

log = logging.getLogger(__name__)

ICON_DIR = Path(__file__).resolve().parents[1] / "assets" / "icons"
ICON_SVG = ICON_DIR / "app_icon.svg"
ICON_SMALL_SVG = ICON_DIR / "app_icon_small.svg"
ICON_ICO = ICON_DIR / "app_icon.ico"
SMALL_SIZES = (16, 20, 24, 32)
LARGE_SIZES = (48, 64, 128, 256)
APP_USER_MODEL_ID = "PedalSteelMaster.App"


def _svg_for(size: int) -> Path:
    return ICON_SMALL_SVG if size <= 32 else ICON_SVG


def render_icon_image(size: int) -> QImage:
    """The icon at `size` px (transparent corners); a null image if the SVG is missing."""
    path = _svg_for(size)
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        log.warning("App icon not found or invalid: %s", path)
        return QImage()
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return img


def app_icon() -> QIcon:
    """Multi-size QIcon: the small variant for 16-32 px, the detailed one above."""
    icon = QIcon()
    for size in SMALL_SIZES + LARGE_SIZES:
        img = render_icon_image(size)
        if not img.isNull():
            icon.addPixmap(QPixmap.fromImage(img))
    return icon


def set_windows_app_id() -> None:
    """Gives the process its own taskbar identity on Windows, so the taskbar shows this app's icon
    instead of python.exe's. Call before the first window is shown."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        log.debug("Could not set the AppUserModelID", exc_info=True)


def splash_pixmap(width: int = 440, height: int = 300) -> QPixmap:
    """Splash card shown while the main window builds: the icon, the app name and 'Loading…'."""
    pm = QPixmap(width, height)
    pm.fill(QColor("#0e1a30"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    icon = render_icon_image(176)
    if not icon.isNull():
        p.drawImage((width - 176) // 2, 22, icon)
    p.setPen(QColor("#ffffff"))
    p.setFont(QFont("Segoe UI", 18, QFont.Bold))
    p.drawText(QRectF(0, 206, width, 36), Qt.AlignCenter, "Pedal Steel Master")
    p.setPen(QColor("#9fb3d1"))
    p.setFont(QFont("Segoe UI", 10))
    p.drawText(QRectF(0, 246, width, 24), Qt.AlignCenter, "Loading…")
    p.end()
    return pm


def write_ico(path: Path = ICON_ICO) -> Path:
    """Writes a multi-size Windows .ico (PNG-compressed entries, 16-256 px)."""
    entries = []
    for size in SMALL_SIZES + LARGE_SIZES:
        img = render_icon_image(size)
        if img.isNull():
            continue
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        buf.close()
        entries.append((size, bytes(data)))
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = len(header) + 16 * len(entries)
    directory, blobs = b"", b""
    for size, png in entries:
        directory += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    path.write_bytes(header + directory + blobs)
    return path


if __name__ == "__main__":
    from PySide6.QtGui import QGuiApplication

    _app = QGuiApplication(sys.argv)
    print(f"Wrote {write_ico()}")
