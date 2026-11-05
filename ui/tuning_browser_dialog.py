"""Browse every tuning in every profile (factory and user), filter them, open one or copy it
into the open profile."""

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from core.models import Neck, SteelGuitar
from core.profile_manager import FACTORY_PROFILE, ProfileManager, profile_label

log = logging.getLogger(__name__)


class TuningBrowserDialog(QDialog):
    """Emits `open_requested(profile key, tuning index)` and `copy_requested(Neck)` (a tuning
    from another profile to add to the open one)."""

    open_requested = Signal(str, int)
    copy_requested = Signal(object)

    def __init__(self, current: SteelGuitar, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Browse All Tunings")
        self.resize(760, 520)
        self.current = current
        self._init_ui()
        self._populate()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel("<b>Filter:</b>"))
        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText("Tuning name, type (E9, C6...) or string count")
        self.edit_filter.setClearButtonEnabled(True)
        self.edit_filter.textChanged.connect(self._apply_filter)
        row.addWidget(self.edit_filter, stretch=1)
        layout.addLayout(row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tuning", "Type", "Strings", "Pedals", "Levers", "Author"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.tree.itemDoubleClicked.connect(lambda *_: self._open())
        self.tree.currentItemChanged.connect(self._update_buttons)
        layout.addWidget(self.tree, stretch=1)

        btns = QHBoxLayout()
        self.btn_open = QPushButton("Open")
        self.btn_open.setToolTip("Switch to this tuning's profile and select it")
        self.btn_open.setStyleSheet("background-color: #007bff; color: white; font-weight: bold; min-height: 28px;")
        self.btn_open.clicked.connect(self._open)
        btns.addWidget(self.btn_open)
        self.btn_copy = QPushButton("➕ Add to Open Profile")
        self.btn_copy.setToolTip("Copy this tuning into the profile that is open now")
        self.btn_copy.clicked.connect(self._copy)
        btns.addWidget(self.btn_copy)
        btns.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        btns.addWidget(close)
        layout.addLayout(btns)

    def _populate(self):
        self.tree.clear()
        for key, necks in ProfileManager.list_all_tunings(current=self.current):
            label = ("🏭 " if key == FACTORY_PROFILE else "📁 ") + profile_label(key)
            if key == self.current.profile:
                label += "   (open)"
            top = QTreeWidgetItem([label, "", str(len(necks)) + " tunings"])
            top.setData(0, Qt.UserRole, None)
            font = top.font(0)
            font.setBold(True)
            top.setFont(0, font)
            self.tree.addTopLevelItem(top)
            for idx, neck in enumerate(necks):
                item = QTreeWidgetItem([
                    neck.name, neck.neck_type.value, str(neck.string_count),
                    str(len(neck.pedals)), str(len(neck.knee_levers)), neck.author or "",
                ])
                item.setData(0, Qt.UserRole, (key, idx, neck))
                top.addChild(item)
            top.setExpanded(True)
        self._update_buttons()

    def _apply_filter(self, text: str):
        words = text.lower().split()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            visible = 0
            for j in range(top.childCount()):
                child = top.child(j)
                hay = " ".join(child.text(c) for c in range(6)).lower() + " " + top.text(0).lower()
                show = all(w in hay for w in words)
                child.setHidden(not show)
                visible += show
            top.setHidden(visible == 0)

    def _selected(self) -> Optional[tuple]:
        item = self.tree.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    def _update_buttons(self, *_):
        sel = self._selected()
        self.btn_open.setEnabled(sel is not None)
        self.btn_copy.setEnabled(sel is not None and sel[0] != self.current.profile)

    def _open(self):
        sel = self._selected()
        if sel:
            self.open_requested.emit(sel[0], sel[1])
            self.accept()

    def _copy(self):
        sel = self._selected()
        if sel and sel[0] != self.current.profile:
            self.copy_requested.emit(sel[2])
            self.accept()
