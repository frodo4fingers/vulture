from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QSpinBox, QToolButton

from vulture.models import AppData, BreakPreferences
from vulture.ui.settings import SettingsDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _dialog(**kwargs) -> SettingsDialog:
    data = AppData()
    return SettingsDialog(
        data.alert_policy,
        data.exercise_preferences,
        data.history_preferences,
        data.interface_language,
        break_preferences=BreakPreferences(),
        **kwargs,
    )


def test_calibration_sound_cues_default_and_toggle(
    application: QApplication,
) -> None:
    assert AppData().calibration_sound_cues is True
    dialog = _dialog(calibration_sound_cues=False)
    assert not dialog.calibration_sound_cues.isChecked()
    dialog.calibration_sound_cues.setChecked(True)
    assert dialog.calibration_sound_cues.isChecked()


def test_settings_are_split_into_tabs_with_whole_second_spinboxes(
    application: QApplication,
) -> None:
    dialog = _dialog()
    assert [
        dialog.tabs.tabText(index) for index in range(dialog.tabs.count())
    ] == ["Posture", "Breaks", "Privacy && data", "General"]
    for spin in (
        dialog.warning_seconds,
        dialog.alert_seconds,
        dialog.transition_buffer_seconds,
    ):
        assert isinstance(spin, QSpinBox)
    dialog._validate_and_accept()
    assert dialog.values()[0].warning_after_seconds == 8


def test_break_shuffle_lists_are_collapsed_until_customized(
    application: QApplication,
) -> None:
    dialog = _dialog()
    dialog.show()
    application.processEvents()
    dialog.tabs.setCurrentIndex(1)
    application.processEvents()
    assert not dialog.suggest_standing.isVisible()
    toggles = [
        button
        for button in dialog.findChildren(QToolButton)
        if button.isCheckable()
    ]
    assert toggles
    toggles[0].setChecked(True)
    application.processEvents()
    assert dialog.suggest_standing.isVisible()
    dialog.close()
