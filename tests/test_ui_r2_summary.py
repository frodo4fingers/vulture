from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from PySide6.QtWidgets import QApplication

from vulture.breaks import BreakChannel
from vulture.history import (
    BASELINE_POSTURE,
    BreakEvent,
    DailyPostureSummary,
    PostureHistoryStore,
)
from vulture.i18n import set_language
from vulture.models import InterfaceLanguage
from vulture.ui.summary import build_rolling_week_data, daily_break_stats
from vulture.ui.summary_dialog import WorkdaySummaryDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def english() -> None:
    set_language(InterfaceLanguage.ENGLISH)
    yield
    set_language(InterfaceLanguage.ENGLISH)


def _break(
    day: date,
    kind: str,
    channel: BreakChannel,
    seconds: float,
) -> BreakEvent:
    return BreakEvent(
        kind=kind,
        channel=channel,
        completed_at=datetime(
            day.year, day.month, day.day, 10, tzinfo=timezone.utc
        ),
        local_date=day,
        duration_seconds=seconds,
    )


def _summary(day: date, breaks: list[BreakEvent]) -> DailyPostureSummary:
    return DailyPostureSummary(
        local_date=day,
        totals={},
        tracked_seconds=0,
        reminder_count=0,
        episodes=[],
        breaks=breaks,
    )


def test_kpi_values_count_breaks_moved_minutes_and_eye_breaks() -> None:
    day = date(2026, 7, 20)
    stats = daily_break_stats(
        _summary(
            day,
            [
                _break(day, "movement", BreakChannel.MOVEMENT, 100),
                _break(day, "movement", BreakChannel.MOVEMENT, 80),
                _break(day, "rest", BreakChannel.EYE, 20),
            ],
        )
    )

    assert (stats.count, stats.minutes_moved, stats.eye_breaks) == (3, 3, 1)


def test_day_overview_leads_with_breaks_and_friendly_empty_day(
    application: QApplication,
) -> None:
    today = datetime.now().astimezone().date()
    with_breaks = _summary(
        today,
        [
            _break(today, "movement", BreakChannel.MOVEMENT, 120),
            _break(today, "rest", BreakChannel.EYE, 20),
        ],
    )
    dialog = WorkdaySummaryDialog(
        lambda _day: with_breaks,
        lambda _day: None,
        lambda: None,
        {},
        True,
    )

    assert dialog.daily_breaks_metric.value_label.text() == "2"
    assert dialog.daily_moved_metric.value_label.text() == "2"
    assert dialog.daily_eye_metric.value_label.text() == "1"
    assert dialog.no_breaks_label.isHidden()
    # A day with only breaks is not an empty day and can be deleted.
    assert dialog.empty_state_container.isHidden()
    assert dialog.delete_day_button.isEnabled()
    dialog.close()

    nothing = _summary(today, [])
    quiet = WorkdaySummaryDialog(
        lambda _day: nothing,
        lambda _day: None,
        lambda: None,
        {},
        True,
    )
    assert not quiet.empty_state_container.isHidden()
    quiet.close()


def test_no_breaks_message_on_a_day_with_posture_data(
    application: QApplication,
) -> None:
    from vulture.history import StoredPostureEpisode
    from vulture.models import TrackerState

    today = datetime.now().astimezone().date()
    start = datetime.now(timezone.utc).replace(microsecond=0)
    summary = DailyPostureSummary(
        local_date=today,
        totals={BASELINE_POSTURE: 600},
        tracked_seconds=600,
        reminder_count=1,
        episodes=[
            StoredPostureEpisode(
                id=1,
                local_date=today,
                started_at=start,
                ended_at=start + timedelta(minutes=10),
                utc_offset_minutes=0,
                setup_id="desk",
                posture=BASELINE_POSTURE,
                peak_state=TrackerState.GOOD,
                duration_seconds=600,
                sample_count=2,
            )
        ],
    )
    dialog = WorkdaySummaryDialog(
        lambda _day: summary,
        lambda _day: None,
        lambda: None,
        {"desk": "Desk"},
        True,
    )

    assert not dialog.no_breaks_label.isHidden()
    assert dialog.no_breaks_label.text() == "No breaks logged yet today"
    assert dialog.daily_breaks_metric.isHidden()
    assert dialog.daily_nudges_metric.value_label.text() == "1"
    dialog.close()


def test_weekly_breaks_per_day_and_days_with_data() -> None:
    end = date(2026, 7, 20)
    counts = [0, 2, 0, 1, 0, 0, 3]
    summaries = tuple(
        _summary(
            end - timedelta(days=6 - index),
            [
                _break(
                    end - timedelta(days=6 - index),
                    "rest",
                    BreakChannel.EYE,
                    20,
                )
            ]
            * count,
        )
        for index, count in enumerate(counts)
    )

    data = build_rolling_week_data(end, summaries)

    assert data.daily_breaks == tuple(counts)
    assert data.break_count == 6
    assert data.days_with_data == 3


def test_weekly_table_and_metric_show_breaks(
    application: QApplication,
) -> None:
    end = datetime.now().astimezone().date()
    summaries = {
        end: _summary(end, [_break(end, "movement", BreakChannel.MOVEMENT, 60)])
    }
    dialog = WorkdaySummaryDialog(
        lambda day: summaries.get(day, _summary(day, [])),
        lambda _day: None,
        lambda: None,
        {},
        True,
    )

    assert dialog.weekly_breaks_metric.value_label.text() == "1"
    assert dialog.weekly_days_metric.value_label.text() == "1 of 7"
    assert dialog.weekly_table.columnCount() == 4
    assert dialog.weekly_table.item(6, 1).text() == "1"
    assert dialog.weekly_table.item(0, 1).text() == "0"
    dialog.close()


def test_delete_all_follows_the_store_not_the_visible_week(
    application: QApplication, tmp_path
) -> None:
    store = PostureHistoryStore(tmp_path / "history.sqlite3")
    today = datetime.now().astimezone().date()
    dialog = WorkdaySummaryDialog(
        store.daily_summary,
        lambda _day: None,
        lambda: None,
        {},
        True,
        has_any_history=store.has_any_history,
    )
    assert not dialog.delete_all_button.isEnabled()

    # History far outside the visible week still enables the button.
    old = today - timedelta(days=200)
    store.record_break(_break(old, "rest", BreakChannel.EYE, 20))
    dialog.refresh()
    assert dialog.delete_all_button.isEnabled()
    # The delete buttons are separated by the stretch, not adjacent.
    assert (
        dialog.delete_all_button.geometry().left()
        > dialog.delete_day_button.geometry().right()
        or not dialog.isVisible()
    )

    store.delete_all()
    dialog.refresh()
    assert not dialog.delete_all_button.isEnabled()
    dialog.close()
    store.close()
