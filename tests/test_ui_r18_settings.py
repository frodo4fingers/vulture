from __future__ import annotations

import re

import pytest
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFormLayout,
    QLabel,
    QSpinBox,
)

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


def _dialog() -> SettingsDialog:
    data = AppData()
    return SettingsDialog(
        data.alert_policy,
        data.exercise_preferences,
        data.history_preferences,
        data.interface_language,
        break_preferences=BreakPreferences(),
    )


def _channels(dialog: SettingsDialog) -> list[tuple[QSpinBox, QSpinBox]]:
    return [
        (dialog.movement_interval_minutes, dialog.movement_duration_minutes),
        (dialog.eye_interval_minutes, dialog.eye_duration_seconds),
        (dialog.hydration_interval_minutes, dialog.hydration_duration_seconds),
        (dialog.reset_interval_minutes, dialog.reset_duration_minutes),
    ]


def _headings(dialog: SettingsDialog) -> list:
    return [
        dialog.break_reminders_enabled,
        dialog.movement_reminders_enabled,
        dialog.eye_reminders_enabled,
        dialog.hydration_reminders_enabled,
        dialog.reset_reminders_enabled,
    ]


def test_each_break_type_is_one_row_with_both_spin_boxes(
    application: QApplication,
) -> None:
    dialog = _dialog()
    controls = [
        dialog.movement_controls,
        dialog.eye_controls,
        dialog.hydration_controls,
        dialog.reset_controls,
    ]
    for controls_widget, (interval, length) in zip(
        controls, _channels(dialog)
    ):
        form = controls_widget.layout().itemAt(0).layout()
        assert isinstance(form, QFormLayout)
        assert form.rowCount() == 1
        field = form.itemAt(0, QFormLayout.ItemRole.FieldRole).widget()
        assert interval.parentWidget() is field
        assert length.parentWidget() is field
        label = form.itemAt(0, QFormLayout.ItemRole.LabelRole).widget()
        assert label.text() == "Every"
        assert label.buddy() is interval
    dialog.close()


def test_interval_and_length_spin_boxes_share_widths(
    application: QApplication,
) -> None:
    dialog = _dialog()
    channels = _channels(dialog)
    for column in zip(*channels):
        assert len({spin.minimumWidth() for spin in column}) == 1
        assert len({spin.maximumWidth() for spin in column}) == 1
    dialog.close()


def test_length_spin_boxes_are_named_by_channel(
    application: QApplication,
) -> None:
    dialog = _dialog()
    names = [length.accessibleName() for _, length in _channels(dialog)]
    assert names == [
        "Movement break length",
        "Eye break length",
        "Water break length",
        "Longer reset length",
    ]
    dialog.close()


def test_interval_spins_name_their_break(application: QApplication) -> None:
    dialog = _dialog()
    names = [interval.accessibleName() for interval, _ in _channels(dialog)]
    assert names == [
        "Movement break interval",
        "Eye break interval",
        "Water break interval",
        "Longer reset interval",
    ]
    dialog.close()


@pytest.mark.parametrize(
    "language",
    [
        InterfaceLanguage.ENGLISH,
        InterfaceLanguage.GERMAN,
        InterfaceLanguage.SPANISH,
    ],
)
def test_break_headings_have_unique_mnemonics(
    application: QApplication, language: InterfaceLanguage
) -> None:
    set_language(language)
    dialog = _dialog()
    keys = [
        match.group(1).lower()
        for heading in _headings(dialog)
        if (match := re.search(r"(?<!&)&(\w)", heading.text()))
    ]
    assert len(keys) == 5
    assert len(set(keys)) == 5
    # No other label or button (Save, Cancel included) shares a key.
    for widget in (
        *dialog.findChildren(QLabel),
        *dialog.findChildren(QAbstractButton),
    ):
        if widget in _headings(dialog):
            continue
        for key in re.findall(r"(?<!&)&(\w)", widget.text()):
            assert key.lower() not in keys
    dialog.close()


def test_changed_length_still_saves(application: QApplication) -> None:
    dialog = _dialog()
    dialog.movement_duration_minutes.setValue(4)
    dialog.eye_duration_seconds.setValue(30)
    dialog.hydration_duration_seconds.setValue(60)
    dialog.reset_duration_minutes.setValue(7)
    dialog._validate_and_accept()
    saved = dialog.values()[5]
    assert saved.movement_duration_minutes == 4
    assert saved.eye_duration_seconds == 30
    assert saved.hydration_duration_seconds == 60
    assert saved.reset_duration_minutes == 7
    dialog.close()
