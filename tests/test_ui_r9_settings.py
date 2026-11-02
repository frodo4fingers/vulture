from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QToolButton

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


def _settings() -> SettingsDialog:
    data = AppData()
    return SettingsDialog(
        data.alert_policy,
        data.exercise_preferences,
        data.history_preferences,
        data.interface_language,
        break_preferences=BreakPreferences(),
    )


def test_seated_only_disables_balance_and_strength(
    application: QApplication,
) -> None:
    dialog = _settings()
    dialog.seated_only.setChecked(False)
    dialog.allow_balance.setChecked(True)
    assert dialog.allow_strength.isEnabled()
    dialog.seated_only.setChecked(True)
    assert not dialog.allow_balance.isEnabled()
    assert not dialog.allow_strength.isEnabled()
    dialog.close()


def test_strength_needs_balance(application: QApplication) -> None:
    dialog = _settings()
    dialog.seated_only.setChecked(False)
    dialog.allow_balance.setChecked(False)
    assert not dialog.allow_strength.isEnabled()
    dialog.allow_balance.setChecked(True)
    assert dialog.allow_strength.isEnabled()
    dialog.close()


def test_disabling_keeps_the_saved_strength_choice(
    application: QApplication,
) -> None:
    dialog = _settings()
    dialog.seated_only.setChecked(False)
    dialog.allow_balance.setChecked(True)
    dialog.allow_strength.setChecked(True)
    dialog.allow_balance.setChecked(False)
    assert not dialog.allow_strength.isEnabled()
    assert dialog.allow_strength.isChecked()
    dialog.allow_balance.setChecked(True)
    dialog.seated_only.setChecked(True)
    assert not dialog.allow_strength.isEnabled()
    assert dialog.allow_strength.isChecked()
    dialog.close()


def test_evidence_disclosure_sits_above_exercise_options(
    application: QApplication,
) -> None:
    dialog = _settings()
    toggle = next(
        button
        for button in dialog.findChildren(QToolButton)
        if button.text() == "Why these intervals?"
    )
    layout = dialog.seated_only.parentWidget().layout()
    assert layout.indexOf(toggle) != -1
    assert layout.indexOf(toggle) < layout.indexOf(dialog.seated_only)
    assert dialog.seated_only.text() == "Only suggest seated guided movements"
    dialog.close()
