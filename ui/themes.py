"""UI themes and QSS stylesheets for Dark and Light modes."""

DARK_THEME_QSS = """
QMainWindow, QDialog, QWidget {
    background-color: #1e1e20;
    color: #e0e0e0;
}
QGroupBox {
    border: 1px solid #3c3f46;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: bold;
    color: #c5c8d0;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}
QMenuBar {
    background-color: #25262a;
    color: #e0e0e0;
    border-bottom: 1px solid #3a3c42;
}
QMenuBar::item:selected {
    background-color: #3b3e47;
}
QMenu {
    background-color: #25262a;
    color: #e0e0e0;
    border: 1px solid #454750;
}
QMenu::item:selected {
    background-color: #0d6efd;
    color: #ffffff;
}
QComboBox, QSpinBox, QLineEdit {
    background-color: #2b2c31;
    color: #ffffff;
    border: 1px solid #444750;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 22px;
}
QComboBox QAbstractItemView {
    background-color: #2b2c31;
    color: #ffffff;
    selection-background-color: #0d6efd;
}
QPushButton {
    background-color: #2b2e35;
    color: #e0e0e0;
    border: 1px solid #454b57;
    border-radius: 4px;
    padding: 4px 8px;
}
QPushButton:hover {
    background-color: #383d47;
    border-color: #656d7e;
}
QPushButton:checked {
    background-color: #0d6efd;
    color: #ffffff;
    border: 1px solid #58a6ff;
    font-weight: bold;
}
QPushButton:checked:hover {
    background-color: #0b5ed7;
    border-color: #79b8ff;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #3c3e44;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #0d6efd;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #e0e0e0;
    width: 16px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 8px;
}
QTableWidget {
    background-color: #242528;
    color: #e0e0e0;
    gridline-color: #383a40;
    border: 1px solid #3c3e44;
}
QHeaderView::section {
    background-color: #2d2e33;
    color: #d0d2d8;
    padding: 4px;
    border: 1px solid #383a40;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
"""

LIGHT_THEME_QSS = """
QMainWindow, QDialog, QWidget {
    background-color: #f4f5f7;
    color: #212529;
    font-family: 'Segoe UI', Arial, sans-serif;
}

QGroupBox {
    font-weight: bold;
    border: 1px solid #ced4da;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 12px;
    background-color: #ffffff;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #343a40;
}

/* Crisp Light-Mode Checkboxes */
QCheckBox {
    spacing: 6px;
    color: #212529;
    font-size: 11px;
}

QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1.5px solid #6c757d;
    border-radius: 3px;
    background-color: #ffffff;
}

QCheckBox::indicator:hover {
    border-color: #0d6efd;
    background-color: #f8f9fa;
}

QCheckBox::indicator:checked {
    background-color: #0d6efd;
    border-color: #0d6efd;
    image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>');
}

QPushButton {
    background-color: #e9ecef;
    border: 1px solid #ced4da;
    border-radius: 4px;
    padding: 5px 12px;
    color: #212529;
}

QPushButton:hover {
    background-color: #dee2e6;
    border-color: #adb5bd;
}

QPushButton:checked {
    background-color: #0d6efd;
    color: #ffffff;
    border-color: #0a58ca;
}

QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    gridline-color: #e9ecef;
    color: #212529;
}

QHeaderView::section {
    background-color: #e9ecef;
    border: 1px solid #ced4da;
    padding: 4px;
    font-weight: bold;
    color: #495057;
}

QComboBox, QSpinBox {
    background-color: #ffffff;
    border: 1px solid #ced4da;
    border-radius: 4px;
    padding: 4px 8px;
    color: #212529;
}
"""



# ---------------------------------------------------------------------------
# Light-mode adaptation of inline widget stylesheets (E-13)
# ---------------------------------------------------------------------------
# Many widgets set inline stylesheets with dark-mode colors. Rather than duplicating every
# stylesheet, ThemeManager rewrites inline QSS on the fly while light mode is active:
#   * dark backgrounds (any hue) -> light tint of the same hue
#   * light text on a remapped/absent background -> dark text of the same hue
#   * accent colors (blue/green/amber/red buttons, mid lightness) and their text are untouched
# The original stylesheet is kept on the widget so switching back to dark restores it exactly.

import colorsys
import re

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QWidget

_NAMED = {"white": "#ffffff", "black": "#000000"}
_COLOR_RE = r"(#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|\bwhite\b|\bblack\b)"
_DECL_RE = re.compile(
    r"(?P<prop>(?<![\w-])(?:background-color|background|alternate-background-color|color|selection-color))"
    r"(?P<sep>\s*:\s*)(?P<val>[^;{}]*)",
    re.IGNORECASE,
)
_BG_PROPS = {"background-color", "background", "alternate-background-color"}


def _to_rgb(token: str):
    h = _NAMED.get(token.lower(), token).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _to_hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb)


def _lightness(token: str) -> float:
    return colorsys.rgb_to_hls(*_to_rgb(token))[1]


def light_background(token: str) -> str:
    """Dark background -> light tint with the same hue (lightness mirrored into 0.86..0.98)."""
    h, l, s = colorsys.rgb_to_hls(*_to_rgb(token))
    return _to_hex(colorsys.hls_to_rgb(h, 0.98 - l * 0.35, min(s, 0.6)))


def dark_foreground(token: str) -> str:
    """Light/mid text (lightness > 0.45) -> dark text with the same hue (lightness 0.15..0.37)."""
    h, l, s = colorsys.rgb_to_hls(*_to_rgb(token))
    return _to_hex(colorsys.hls_to_rgb(h, 0.15 + (1.0 - l) * 0.4, s))


def _remap_block(body: str) -> str:
    """Remaps one declaration block (text between braces, or a bare declaration list)."""
    bg_tokens = []
    for m in _DECL_RE.finditer(body):
        if m.group("prop").lower() in _BG_PROPS:
            bg_tokens += re.findall(_COLOR_RE, m.group("val"))
    # Text is recoloured only if the block's own background is absent or was a dark (remapped) one.
    bg_is_dark_or_absent = not bg_tokens or all(_lightness(c) < 0.35 for c in bg_tokens)

    def _decl(m):
        prop = m.group("prop").lower()
        val = m.group("val")
        if prop in _BG_PROPS:
            val = re.sub(_COLOR_RE, lambda c: light_background(c.group(0)) if _lightness(c.group(0)) < 0.35 else c.group(0), val)
        elif bg_is_dark_or_absent:
            val = re.sub(_COLOR_RE, lambda c: dark_foreground(c.group(0)) if _lightness(c.group(0)) > 0.45 else c.group(0), val)
        return f"{m.group('prop')}{m.group('sep')}{val}"

    return _DECL_RE.sub(_decl, body)


def to_light_stylesheet(qss: str) -> str:
    """Light-mode version of a dark-mode inline stylesheet (idempotent)."""
    if "{" not in qss:
        return _remap_block(qss)
    return re.sub(r"\{([^{}]*)\}", lambda m: "{" + _remap_block(m.group(1)) + "}", qss)


class ThemeManager(QObject):
    """Keeps inline widget stylesheets consistent with the active theme (installed app-wide)."""

    ORIG = "_psg_dark_qss"
    MAPPED = "_psg_light_qss"
    _instances: dict = {}

    @classmethod
    def for_app(cls, app: QApplication) -> "ThemeManager":
        """The single manager for an application. Two managers would fight over the same widgets."""
        mgr = cls._instances.get(id(app))
        if mgr is None:
            mgr = cls(app)
            cls._instances[id(app)] = mgr
        return mgr

    def __init__(self, app: QApplication):
        super().__init__(app)
        self.app = app
        self.is_dark = True
        # Changing a stylesheet sends StyleChange to the widget AND all its descendants. Handling
        # those re-entrantly nests handlers per tree level, so widgets are queued and processed
        # iteratively instead.
        self._pending: dict = {}  # id(widget) -> widget; de-duplicated work queue
        self._busy = False
        app.installEventFilter(self)

    def set_dark(self, is_dark: bool):
        self.is_dark = is_dark
        for w in self.app.allWidgets():
            self._pending[id(w)] = w
        self._drain()

    def eventFilter(self, obj, event):
        # StyleChange: a stylesheet was set. Polish: sent before a widget is first shown; needed
        # because Qt skips StyleChange for repeated setStyleSheet calls on never-shown widgets.
        if event.type() in (QEvent.StyleChange, QEvent.Polish) and isinstance(obj, QWidget):
            self._pending[id(obj)] = obj
            if not self._busy:
                self._drain()
        return False

    def _drain(self):
        self._busy = True
        try:
            while self._pending:
                _, w = self._pending.popitem()
                try:
                    self._apply(w)
                except RuntimeError:
                    pass  # widget was deleted on the C++ side
        finally:
            self._busy = False

    def _apply(self, w: QWidget):
        current = w.styleSheet()
        mapped = w.property(self.MAPPED)
        if mapped is not None and current == mapped:
            # The widget still shows our light mapping.
            if self.is_dark:
                original = w.property(self.ORIG)
                w.setProperty(self.ORIG, None)
                w.setProperty(self.MAPPED, None)
                w.setStyleSheet(original or "")
            return
        # A fresh stylesheet set by application code (or none).
        w.setProperty(self.ORIG, None)
        w.setProperty(self.MAPPED, None)
        if self.is_dark or not current:
            return
        light = to_light_stylesheet(current)
        if light != current:
            w.setProperty(self.ORIG, current)
            w.setProperty(self.MAPPED, light)
            w.setStyleSheet(light)
