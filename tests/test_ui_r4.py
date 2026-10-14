from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from PySide6.QtCharts import QBarCategoryAxis
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox

import vulture.ui.break_options as break_options
from tests.test_ui import (
    _make_window,
    _teardown_window,
    make_history_episode,
    make_profile,
)
from vulture.breaks import ManualBreakChoice, manual_break_prompt
from vulture.exercises import load_exercise_catalog
from vulture.history import BASELINE_POSTURE, DailyPostureSummary
from vulture.i18n import set_language
from vulture.models import BreakPreferences, InterfaceLanguage
from vulture.ui.break_options import (
    STOP_EARLY_FLOOR_SECONDS,
    STOP_EARLY_FLOOR_SHARE,
    RestBreakDialog,
    RestBreakOutcome,
)
from vulture.ui.calibration import CalibrationStepSelectionDialog, SetupDialog
from vulture.ui.exercises import ExerciseDialog, general_safety
from vulture.ui.summary import SUMMARY_DAY_CHART_MIN_HEIGHT, PostureAreaChart
from vulture.ui.summary_dialog import WorkdaySummaryDialog
from vulture.ui.theme import flat_action_style

NO_PROBLEM = (
    "No problem — breaks under 30 seconds aren't counted. "
    "The next one comes soon."
)


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def english() -> None:
    set_language(InterfaceLanguage.ENGLISH)
    yield
    set_language(InterfaceLanguage.ENGLISH)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [100.0]
    monkeypatch.setattr(break_options.time, "monotonic", lambda: now[0])
    return now


def _rest(
    choice: ManualBreakChoice = ManualBreakChoice.COFFEE, **kwargs
) -> RestBreakDialog:
    prompt = manual_break_prompt(choice, BreakPreferences())
    return RestBreakDialog(
        prompt, (ManualBreakChoice.STAND,), **kwargs
    )


def _today_breaks(window) -> list:
    return window.history_store.daily_summary(
        datetime.now().astimezone().date()
    ).breaks


def _stopped_after(
    dialog: RestBreakDialog, clock: list[float], seconds: float
) -> None:
    dialog.show()
    dialog.start_button.click()
    clock[0] += seconds
    dialog.stop_button.click()


# 1. Day chart ----------------------------------------------------------


def _day_summary(start_hour: int, start_minute: int, minutes: int):
    start = datetime(
        2026, 7, 20, start_hour, start_minute, tzinfo=timezone.utc
    )
    return DailyPostureSummary(
        local_date=date(2026, 7, 20),
        totals={BASELINE_POSTURE: minutes * 60},
        tracked_seconds=minutes * 60,
        reminder_count=0,
        episodes=[
            make_history_episode(
                1,
                start,
                start + timedelta(minutes=minutes),
                BASELINE_POSTURE,
            )
        ],
    )


def _x_axis(chart: PostureAreaChart) -> QBarCategoryAxis:
    (axis,) = [
        a for a in chart.chart().axes() if isinstance(a, QBarCategoryAxis)
    ]
    return axis


def test_day_chart_labels_whole_hours_horizontally(
    application: QApplication,
) -> None:
    chart = PostureAreaChart()
    chart.set_summary(_day_summary(8, 0, 60))
    axis = _x_axis(chart)

    assert axis.labelsAngle() == 0
    # Hour buckets read "08"; the others are unique runs of spaces, because
    # the axis drops duplicate categories.
    assert axis.categories() == ["08", "  ", "   ", "    "]
    assert chart.minimumHeight() == SUMMARY_DAY_CHART_MIN_HEIGHT == 260


def test_day_chart_without_a_leading_hour_bucket(
    application: QApplication,
) -> None:
    chart = PostureAreaChart()
    chart.set_summary(_day_summary(8, 30, 60))
    categories = _x_axis(chart).categories()

    assert categories == [" ", "  ", "09", "    "]
    assert len(set(categories)) == len(categories)


def test_day_chart_over_many_hours_has_two_digit_hours_only(
    application: QApplication,
) -> None:
    chart = PostureAreaChart()
    chart.set_summary(_day_summary(7, 0, 4 * 60))
    categories = _x_axis(chart).categories()

    assert len(categories) == 16
    assert len(set(categories)) == 16
    assert [c for c in categories if c.strip()] == ["07", "08", "09", "10"]
    assert all(c == c.strip() or not c.strip() for c in categories)


# 2. Delete buttons -----------------------------------------------------


def test_delete_buttons_have_mnemonics_and_confirm_reuses_them(
    application: QApplication,
) -> None:
    workday = date(2026, 7, 20)
    summary = DailyPostureSummary(
        local_date=workday,
        totals={},
        tracked_seconds=0,
        reminder_count=0,
        episodes=[],
    )
    dialog = WorkdaySummaryDialog(
        lambda _day: summary, lambda _day: None, lambda: None, {}, True
    )

    assert dialog.delete_day_button.text() == "&Delete selected day"
    assert dialog.delete_all_button.text() == "Delete all &history"
    assert dialog.cancel_delete_button.text() == "&Cancel"

    dialog._delete_selected_day()
    assert dialog.confirm_delete_button.text() == "&Delete selected day"
    assert dialog.cancel_delete_button.text() == "&Cancel"
    dialog._cancel_history_delete()

    dialog._delete_all_history()
    assert dialog.confirm_delete_button.text() == "Delete all &history"
    dialog.close()


# 3. Stop-early floor ---------------------------------------------------


def test_stop_early_floor_constants() -> None:
    assert STOP_EARLY_FLOOR_SECONDS == 30
    assert STOP_EARLY_FLOOR_SHARE == 0.25


def test_stop_early_below_the_floor_is_dismissed(
    application: QApplication, clock: list[float]
) -> None:
    dialog = _rest()  # a five-minute break: the floor is 30 s
    _stopped_after(dialog, clock, 29)

    assert dialog.outcome == RestBreakOutcome.DISMISSED
    assert dialog.completed_seconds == 0
    assert dialog.completion_note.text() == NO_PROBLEM
    assert dialog.completion_note.isVisible()
    dialog._ack_timer.timeout.emit()
    assert not dialog.isVisible()
    assert dialog.outcome == RestBreakOutcome.DISMISSED


def test_stop_early_at_or_above_the_floor_counts(
    application: QApplication, clock: list[float]
) -> None:
    dialog = _rest()
    _stopped_after(dialog, clock, 30)

    assert dialog.outcome == RestBreakOutcome.COMPLETED
    assert dialog.completed_seconds == pytest.approx(30)
    assert dialog.completion_note.text() != NO_PROBLEM
    dialog._ack_timer.timeout.emit()


@pytest.mark.parametrize(
    ("seconds", "counts"), [(4, False), (6, True)]
)
def test_short_eye_break_floor_is_a_quarter_of_its_time(
    application: QApplication,
    clock: list[float],
    seconds: float,
    counts: bool,
) -> None:
    dialog = _rest(ManualBreakChoice.EYE_REST)
    assert dialog.prompt.duration_seconds == 20  # floor: 5 s, not 30 s
    _stopped_after(dialog, clock, seconds)

    if counts:
        assert dialog.outcome == RestBreakOutcome.COMPLETED
        assert dialog.completed_seconds == pytest.approx(seconds)
    else:
        assert dialog.outcome == RestBreakOutcome.DISMISSED
        assert dialog.completed_seconds == 0
    dialog._ack_timer.timeout.emit()


def test_movement_stopped_below_the_floor_is_dismissed(
    application: QApplication, clock: list[float]
) -> None:
    catalog = load_exercise_catalog()
    exercise = next(e for e in catalog.exercises if e.id == "easy-walk")
    dialog = ExerciseDialog(
        exercise, catalog, alternative_choices=(ManualBreakChoice.STAND,)
    )
    _stopped_after(dialog, clock, 10)

    assert dialog.outcome == RestBreakOutcome.DISMISSED
    assert dialog.completed_seconds == 0
    assert dialog.completion_note.text() == NO_PROBLEM
    dialog._ack_timer.timeout.emit()


def _walk_window(window, application):
    window._pending_exercise = next(
        e for e in window.catalog.exercises if e.id == "easy-walk"
    )
    window._present_exercise()
    application.processEvents()
    return window._exercise_dialog


def test_window_records_nothing_for_a_movement_stopped_too_soon(
    application: QApplication, tmp_path: Path, clock: list[float]
) -> None:
    window = _make_window(tmp_path)
    dialog = _walk_window(window, application)
    dialog.start_button.click()
    clock[0] += 10
    dialog.stop_button.click()
    dialog._ack_timer.timeout.emit()
    application.processEvents()

    assert _today_breaks(window) == []
    _teardown_window(window, application)


def test_window_records_a_movement_stopped_after_the_floor(
    application: QApplication, tmp_path: Path, clock: list[float]
) -> None:
    window = _make_window(tmp_path)
    dialog = _walk_window(window, application)
    dialog.start_button.click()
    clock[0] += 40
    dialog.stop_button.click()
    dialog._ack_timer.timeout.emit()
    application.processEvents()

    (event,) = _today_breaks(window)
    assert event.duration_seconds == pytest.approx(40)
    _teardown_window(window, application)


def test_window_records_nothing_for_a_rest_break_stopped_too_soon(
    application: QApplication, tmp_path: Path, clock: list[float]
) -> None:
    window = _make_window(tmp_path)
    window._present_manual_break(ManualBreakChoice.COFFEE)
    dialog = window._rest_break_dialog
    dialog.start_button.click()
    clock[0] += 5
    dialog.stop_button.click()
    dialog._ack_timer.timeout.emit()
    application.processEvents()

    assert _today_breaks(window) == []
    _teardown_window(window, application)


# 4. Acknowledgement ----------------------------------------------------


def test_ack_note_takes_the_countdowns_place(
    application: QApplication, clock: list[float]
) -> None:
    dialog = _rest(breaks_today=2)
    layout = dialog.layout()
    assert layout.indexOf(dialog.completion_note) == (
        layout.indexOf(dialog.countdown_block) + 1
    )

    _stopped_after(dialog, clock, 90)
    assert dialog.countdown_block.isHidden()
    assert dialog.completion_note.isVisible()
    assert dialog.remaining_seconds() is None
    dialog._ack_timer.timeout.emit()


def test_remaining_seconds_is_a_number_only_while_the_timer_runs(
    application: QApplication, clock: list[float]
) -> None:
    dialog = _rest()
    dialog.show()
    dialog.start_button.click()
    assert dialog.remaining_seconds() is not None
    clock[0] += 60
    dialog.stop_button.click()
    assert dialog.remaining_seconds() is None
    dialog.reject()


def test_escape_during_the_ack_closes_early_and_keeps_the_outcome(
    application: QApplication, clock: list[float]
) -> None:
    dialog = _rest()
    _stopped_after(dialog, clock, 90)
    assert dialog._ack_timer.isActive()

    dialog.reject()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.outcome == RestBreakOutcome.COMPLETED
    assert not dialog.isVisible()
    assert not dialog._ack_timer.isActive()


def test_escape_before_the_ack_still_rejects(
    application: QApplication,
) -> None:
    dialog = _rest()
    dialog.show()
    dialog.reject()

    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.outcome == RestBreakOutcome.DISMISSED


def test_clicking_the_ack_note_closes_early(
    application: QApplication, clock: list[float]
) -> None:
    dialog = _rest()
    _stopped_after(dialog, clock, 90)
    assert dialog.completion_note.isVisible()

    QTest.mouseClick(dialog.completion_note, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.outcome == RestBreakOutcome.COMPLETED
    assert not dialog.isVisible()


def test_clicking_the_note_does_nothing_outside_the_ack(
    application: QApplication,
) -> None:
    dialog = _rest()
    dialog.show()
    QTest.mouseClick(dialog.completion_note, Qt.MouseButton.LeftButton)

    assert dialog.isVisible()
    dialog.reject()


# 5. General safety -----------------------------------------------------


def test_walking_drops_the_bounce_sentence_but_seated_keeps_it() -> None:
    catalog = load_exercise_catalog()
    by_id = {e.id: e for e in catalog.exercises}
    assert "aerobic" in by_id["easy-walk"].tags

    walking = general_safety(catalog, by_id["easy-walk"])
    seated = general_safety(catalog, by_id["seated-chest-stretch"])

    assert "bounce" not in walking
    assert "chair" not in walking
    assert walking == (
        "Move slowly, breathe normally, and stay within a comfortable range."
    )
    assert "bounce" in seated
    assert "chair" in seated


# 6. Pause button -------------------------------------------------------


def test_pause_button_is_an_outlined_flat_action(
    application: QApplication,
) -> None:
    catalog = load_exercise_catalog()
    exercise = next(e for e in catalog.exercises if e.id == "easy-walk")
    dialog = ExerciseDialog(
        exercise, catalog, alternative_choices=(ManualBreakChoice.STAND,)
    )

    assert not dialog.playback_button.autoRaise()
    assert dialog.playback_button.styleSheet() == flat_action_style()
    dialog.close()


# 7. Setup and step selection -------------------------------------------


def test_step_selection_confirm_button_is_primary(
    application: QApplication,
) -> None:
    dialog = CalibrationStepSelectionDialog(make_profile())

    assert dialog.confirm_button.styleSheet()
    assert not dialog.confirm_button.isDefault()
    assert not dialog.confirm_button.autoDefault()
    dialog.close()


def test_setup_dialog_has_save_and_no_cancel(
    application: QApplication,
) -> None:
    dialog = SetupDialog()
    buttons = dialog.findChild(QDialogButtonBox)

    assert buttons.standardButtons() == QDialogButtonBox.StandardButton.Save
    assert buttons.button(QDialogButtonBox.StandardButton.Cancel) is None
    assert buttons.button(QDialogButtonBox.StandardButton.Save) is not None
    dialog.close()
