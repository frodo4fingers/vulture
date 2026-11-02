from __future__ import annotations

import pytest
from PySide6.QtWidgets import QAbstractButton, QApplication, QDialog

from tests.test_ui import make_profile
from tests.test_ui_r2_summary import _summary
from vulture.breaks import ManualBreakChoice, manual_break_prompt
from vulture.i18n import set_language
from vulture.models import BreakPreferences, InterfaceLanguage
from vulture.ui.break_options import RestBreakDialog
from vulture.ui.calibration import (
    CalibrationDialog,
    CalibrationStepSelectionDialog,
)
from vulture.ui.summary_dialog import WorkdaySummaryDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def english() -> None:
    set_language(InterfaceLanguage.ENGLISH)
    yield


def _assert_one_unique_mnemonic_each(buttons: list[QAbstractButton]) -> None:
    keys = []
    for button in buttons:
        assert button.text().count("&") == 1, button.text()
        keys.append(button.text().split("&")[1][0].lower())
    assert len(keys) == len(set(keys))


def _all_mnemonic_buttons(dialog: QDialog) -> list[QAbstractButton]:
    return [
        b for b in dialog.findChildren(QAbstractButton) if "&" in b.text()
    ]


def test_step_selection_opens_at_content_height(
    application: QApplication,
) -> None:
    dialog = CalibrationStepSelectionDialog(make_profile())
    assert dialog.selected_step().category is None  # the baseline
    assert dialog.height() < 600
    assert dialog.height() >= dialog.layout().totalHeightForWidth(
        dialog.width()
    )

    # The baseline warning appears on the first confirm; it must still fit.
    dialog.show()
    dialog.confirm_button.click()
    assert not dialog.baseline_warning.isHidden()
    assert dialog.height() >= dialog.layout().totalHeightForWidth(
        dialog.width()
    )
    dialog.close()


def test_break_panel_buttons_have_one_unique_mnemonic(
    application: QApplication,
) -> None:
    panel = RestBreakDialog(
        manual_break_prompt(ManualBreakChoice.STAND, BreakPreferences()),
        (ManualBreakChoice.GUIDED_MOVEMENT,),
    )
    buttons = [
        panel.start_button,
        panel.done_button,
        panel.stop_button,
        panel.not_now_button,
    ]
    _assert_one_unique_mnemonic_each(buttons)
    panel.close()


def test_calibration_buttons_have_one_unique_mnemonic(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog()
    _assert_one_unique_mnemonic_each(
        [dialog.start_button, dialog.skip_button, dialog.cancel_button]
    )
    dialog.close()


def test_summary_buttons_have_one_unique_mnemonic(
    application: QApplication,
) -> None:
    dialog = WorkdaySummaryDialog(
        lambda day: _summary(day, []), lambda _day: None, lambda: None, {}, True
    )
    buttons = _all_mnemonic_buttons(dialog)
    assert any(b.text() == "&Refresh" for b in buttons)
    _assert_one_unique_mnemonic_each(buttons)
    dialog.close()
