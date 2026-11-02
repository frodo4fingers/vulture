from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QSizePolicy

from vulture.i18n import set_language
from vulture.models import AppData, BreakPreferences, InterfaceLanguage
from vulture.ui.settings import SettingsDialog
from vulture.ui.theme import CaptionLabel


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def english() -> None:
    set_language(InterfaceLanguage.ENGLISH)
    yield
    set_language(InterfaceLanguage.ENGLISH)


def _settings() -> SettingsDialog:
    data = AppData()
    return SettingsDialog(
        data.alert_policy,
        data.exercise_preferences,
        data.history_preferences,
        data.interface_language,
        break_preferences=BreakPreferences(),
    )


def test_spin_boxes_stay_compact_and_captions_unclipped(
    application: QApplication,
) -> None:
    dialog = _settings()
    dialog.resize(960, 640)
    dialog.show()
    application.processEvents()
    spin = dialog.warning_seconds
    assert spin.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed
    assert spin.width() < 200
    captions = [
        label
        for label in dialog.findChildren(CaptionLabel)
        if label.isVisible() and label.wordWrap()
    ]
    assert captions
    for label in captions:
        assert label.height() >= label.heightForWidth(label.width()), (
            label.text()
        )
    dialog.close()


def test_exercise_accessibility_caption_exists(
    application: QApplication,
) -> None:
    dialog = _settings()
    captions = [label.text() for label in dialog.findChildren(QLabel)]
    assert (
        "Strength movements also need standing balance. Both stay off "
        "while seated-only is on."
    ) in captions
    dialog.close()


def test_notification_delay_floor_follows_nudge_delay(
    application: QApplication,
) -> None:
    dialog = _settings()
    dialog.warning_seconds.setValue(100)
    dialog.alert_seconds.setValue(5)
    assert dialog.alert_seconds.minimum() == 101
    assert dialog.alert_seconds.value() >= 101
    dialog.warning_seconds.setValue(10)
    assert dialog.alert_seconds.minimum() == 11
    dialog.close()
