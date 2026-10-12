from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from tests.test_ui import _install_test_setup, _make_window, _teardown_window
from tests.test_ui_r2_summary import _break, _summary
from vulture.breaks import BreakChannel, ManualBreakChoice
from vulture.exercises import load_exercise_catalog
from vulture.i18n import set_language
from vulture.models import InterfaceLanguage
from vulture.ui.break_options import RestBreakDialog, completion_message
from vulture.ui.calibration import CalibrationStepSelectionDialog
from vulture.ui.exercises import general_safety
from vulture.ui.summary import break_headline, build_rolling_week_data
from vulture.ui.summary_dialog import WorkdaySummaryDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def english() -> None:
    set_language(InterfaceLanguage.ENGLISH)
    yield
    set_language(InterfaceLanguage.ENGLISH)


@pytest.mark.parametrize(
    ("count", "period", "expected"),
    [
        (1, "today", "1 break, 5 min moved today."),
        (3, "today", "3 breaks, 5 min moved today."),
        (1, "day", "1 break, 5 min moved that day."),
        (3, "day", "3 breaks, 5 min moved that day."),
        (1, "week", "1 break, 5 min moved this week."),
        (3, "week", "3 breaks, 5 min moved this week."),
    ],
)
def test_break_headline_is_singular_for_one_break(
    count: int, period: str, expected: str
) -> None:
    assert break_headline(count, 5, period) == expected


def test_completion_message_has_a_first_break_variant() -> None:
    assert completion_message(1) == "Nice work — first break today."
    assert completion_message(2) == "Nice work — that's 2 breaks today."
    assert completion_message(None) == "Nice work — break done."


def test_general_safety_fits_the_exercise() -> None:
    catalog = load_exercise_catalog()
    by_id = {e.id: e for e in catalog.exercises}
    sentences = [s.strip() for s in catalog.global_safety.split(". ")]
    chair = sentences[0]

    seated = general_safety(catalog, by_id["seated-chest-stretch"])
    walking = general_safety(catalog, by_id["easy-walk"])

    # The stop sentence repeats the per-exercise caution: always dropped.
    assert "Stop for pain" not in seated
    assert "Stop for pain" not in walking
    # The chair sentence only suits seated exercises.
    assert seated.startswith(chair)
    assert "chair" not in walking
    assert walking.startswith("Move slowly")


def test_exercise_dialog_shows_the_fitted_safety_text(
    application: QApplication, tmp_path: Path
) -> None:
    window = _make_window(tmp_path)
    window._pending_exercise = next(
        e for e in window.catalog.exercises if e.id == "easy-walk"
    )
    window._present_exercise()
    application.processEvents()

    dialog = window._exercise_dialog
    assert dialog.global_safety.text() == general_safety(
        window.catalog, dialog.exercise
    )
    assert "chair" not in dialog.global_safety.text()
    _teardown_window(window, application)


def test_summary_tiles_name_their_value_and_zero_tiles_hide(
    application: QApplication,
) -> None:
    today = datetime.now().astimezone().date()
    summary = _summary(
        today, [_break(today, "movement", BreakChannel.MOVEMENT, 120)]
    )
    dialog = WorkdaySummaryDialog(
        lambda _day: summary, lambda _day: None, lambda: None, {}, True
    )

    assert dialog.windowTitle() == "Workday summary"
    assert dialog.daily_breaks_metric.accessibleName() == "Breaks: 1"
    assert dialog.daily_moved_metric.accessibleName() == "Minutes moved: 2"
    assert not dialog.daily_breaks_metric.isHidden()
    assert not dialog.daily_moved_metric.isHidden()
    # No eye break happened, so its tile is not shown as a zero.
    assert dialog.daily_eye_metric.isHidden()
    assert dialog.daily_headline.text() == "1 break, 2 min moved today."
    dialog.close()


def test_empty_week_shows_a_message_instead_of_zero_tiles(
    application: QApplication,
) -> None:
    dialog = WorkdaySummaryDialog(
        lambda day: _summary(day, []),
        lambda _day: None,
        lambda: None,
        {},
        True,
    )

    assert not dialog.weekly_no_breaks_label.isHidden()
    assert dialog.weekly_no_breaks_label.text() == (
        "No breaks recorded this week yet."
    )
    assert dialog.weekly_breaks_metric.isHidden()
    assert dialog.weekly_moved_metric.isHidden()
    dialog.close()


def test_rolling_week_sums_minutes_moved() -> None:
    end = date(2026, 7, 20)
    day = _summary(
        end,
        [
            _break(end, "movement", BreakChannel.MOVEMENT, 120),
            _break(end, "movement", BreakChannel.MOVEMENT, 120),
        ],
    )

    earlier = tuple(
        _summary(end - timedelta(days=offset), [])
        for offset in range(6, 0, -1)
    )
    data = build_rolling_week_data(end, (*earlier, day))

    assert data.break_count == 2
    assert data.minutes_moved == 4


def test_footer_disclaimer_is_first_run_only(
    application: QApplication, tmp_path: Path
) -> None:
    window = _make_window(tmp_path)
    window._refresh_setup_combo()
    assert not window.footer_disclaimer.isHidden()

    _install_test_setup(window, calibration=None)
    assert window.footer_disclaimer.isHidden()

    # Closing a panel must not bring it back once a setup exists.
    window._show_notice("Saved data unavailable", "Disk is read-only.")
    application.processEvents()
    window._dismiss_side_panel()
    application.processEvents()
    assert window.footer_disclaimer.isHidden()
    _teardown_window(window, application)


def test_primary_actions_use_colour_not_default_buttons(
    application: QApplication, tmp_path: Path
) -> None:
    window = _make_window(tmp_path)
    button = window.first_run_add_button

    assert not button.isDefault()
    assert not button.autoDefault()
    assert button.styleSheet()
    _teardown_window(window, application)


def test_move_now_rests_the_eyes_when_the_eye_break_is_next(
    application: QApplication, tmp_path: Path
) -> None:
    window = _make_window(tmp_path)
    window._update_break_countdown()
    assert window.move_now_button.text() == "&Rest eyes now"

    window.move_now_button.click()
    application.processEvents()

    dialog = window._rest_break_dialog
    assert isinstance(dialog, RestBreakDialog)
    assert dialog.prompt.channel is BreakChannel.EYE
    assert window._exercise_dialog is None
    _teardown_window(window, application)


def test_break_mode_hides_the_header_action_and_move_now(
    application: QApplication, tmp_path: Path
) -> None:
    window = _make_window(tmp_path)
    window._present_manual_break(ManualBreakChoice.STAND)
    application.processEvents()

    assert window.side_panel_close_button.isHidden()
    assert window.move_now_button.isHidden()

    # Esc stays the way out of a movement.
    window._dismiss_side_panel()
    application.processEvents()
    assert not window.side_panel_close_button.isHidden()
    assert not window.move_now_button.isHidden()

    window._offer_exercise()
    application.processEvents()
    assert window.side_panel_close_button.isHidden()
    window._dismiss_shortcut.activated.emit()
    application.processEvents()
    assert window._exercise_dialog is None
    assert window._pending_exercise is not None
    _teardown_window(window, application)


def test_step_selection_confirm_button_has_a_mnemonic(
    application: QApplication,
) -> None:
    from tests.test_ui import make_profile

    dialog = CalibrationStepSelectionDialog(make_profile())

    assert dialog.confirm_button.text() == "&Redo this step"
    dialog.close()
