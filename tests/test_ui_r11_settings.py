from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from vulture.i18n import set_language
from vulture.models import AppData, BreakPreferences, InterfaceLanguage
from vulture.ui.settings import SettingsDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def english() -> None:
    set_language(InterfaceLanguage.ENGLISH)
    yield
    set_language(InterfaceLanguage.ENGLISH)


def test_break_group_fields_start_at_the_same_x(
    application: QApplication,
) -> None:
    data = AppData()
    dialog = SettingsDialog(
        data.alert_policy,
        data.exercise_preferences,
        data.history_preferences,
        data.interface_language,
        break_preferences=BreakPreferences(),
    )
    dialog.resize(960, 640)
    dialog.show()
    for index in range(dialog.tabs.count()):
        if dialog.tabs.widget(index).isAncestorOf(dialog.eye_controls):
            dialog.tabs.setCurrentIndex(index)
    application.processEvents()
    fields = [
        dialog.movement_interval_minutes,
        dialog.eye_interval_minutes,
        dialog.hydration_interval_minutes,
        dialog.reset_interval_minutes,
    ]
    assert all(field.isVisible() for field in fields)
    xs = {field.mapTo(dialog, QPoint(0, 0)).x() for field in fields}
    assert len(xs) == 1, xs
    dialog.close()
