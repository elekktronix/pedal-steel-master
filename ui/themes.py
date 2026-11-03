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