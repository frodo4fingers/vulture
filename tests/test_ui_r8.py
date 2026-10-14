from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from tests.test_ui import make_profile
from tests.test_ui_r4 import _rest
from vulture.i18n import set_language
from vulture.models import AppData, BreakPreferences, InterfaceLanguage
from vulture.ui.break_options import COMPLETION_ACK_MS, ack_interval_ms
from vulture.ui.calibration import CalibrationStepSelectionDialog
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


def test_exercise_options_live_on_breaks_and_seated_rules_out_balance(
    application: QApplication,
) -> None:
    dialog = _settings()
    breaks = next(
        index
        for index in range(dialog.tabs.count())
        if dialog.tabs.tabText(index) == "Breaks"
    )
    assert dialog.tabs.widget(breaks).isAncestorOf(dialog.seated_only)

    dialog.allow_balance.setChecked(True)
    dialog.seated_only.setChecked(True)
    assert not dialog.allow_balance.isEnabled()
    # The saved choice survives for when seated-only is turned off.
    assert dialog.allow_balance.isChecked()
    dialog.seated_only.setChecked(False)
    assert dialog.allow_balance.isEnabled()
    dialog.close()


def test_break_progress_bar_has_a_visible_track(
    application: QApplication,
) -> None:
    dialog = _rest()
    style = dialog.progress.styleSheet()
    assert "QProgressBar {" in style and "background-color" in style
    assert "QProgressBar::chunk" in style
    dialog.close()


def test_long_acknowledgements_stay_longer() -> None:
    assert ack_interval_ms("Nice work — break done.") == COMPLETION_ACK_MS
    long_note = " ".join(["word"] * 17)
    assert ack_interval_ms(long_note) == 1000 + 250 * 17 > COMPLETION_ACK_MS


def test_baseline_wipe_is_stated_once(application: QApplication) -> None:
    dialog = CalibrationStepSelectionDialog(make_profile())
    assert dialog.selected_step().category is None  # the baseline
    assert "removes" not in dialog.description.text()
    assert "comfortable baseline" in dialog.baseline_warning.text()
    dialog.close()
