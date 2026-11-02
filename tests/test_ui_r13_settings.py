from __future__ import annotations

import pytest
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


def _dialog(**kwargs: object) -> SettingsDialog:
    data = AppData()
    return SettingsDialog(
        data.alert_policy,
        data.exercise_preferences,
        data.history_preferences,
        data.interface_language,
        break_preferences=BreakPreferences(),
        **kwargs,
    )


def test_break_spin_boxes_share_one_width(application: QApplication) -> None:
    dialog = _dialog()
    spins = [
        dialog.movement_interval_minutes,
        dialog.movement_duration_minutes,
        dialog.eye_interval_minutes,
        dialog.eye_duration_seconds,
        dialog.hydration_interval_minutes,
        dialog.hydration_duration_seconds,
        dialog.reset_interval_minutes,
        dialog.reset_duration_minutes,
    ]
    assert len({spin.minimumWidth() for spin in spins}) == 1
    assert len({spin.maximumWidth() for spin in spins}) == 1
    assert spins[0].minimumWidth() == max(s.sizeHint().width() for s in spins)
    dialog.close()


def test_startup_error_carries_details(application: QApplication) -> None:
    message = "Vulture could not read the system startup setting."
    dialog = _dialog(
        startup_setting_available=False,
        startup_setting_error=message,
        startup_setting_details="dbus down",
    )
    assert dialog.startup_error_label.text() == message
    assert dialog.startup_error_label.toolTip() == "dbus down"
    assert dialog.startup_error_label.accessibleDescription() == "dbus down"
    dialog.close()
