from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QWidget


def center_window(window: QWidget, available_geometry: QRect | None = None) -> None:
    if available_geometry is None:
        screen = window.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available_geometry = screen.availableGeometry()
    frame = window.frameGeometry()
    frame.moveCenter(available_geometry.center())
    window.move(frame.topLeft())
