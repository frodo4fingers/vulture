from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from vulture.history import (
    BASELINE_POSTURE,
    PostureHistoryStore,
    WorkdayRecorder,
)
from vulture.models import PostureCategory, ReminderEvent, TrackerState
from vulture.tracking import PostureAssessment


def assessment(
    assessed_at: datetime,
    category: PostureCategory | None = None,
    state: TrackerState = TrackerState.GOOD,
) -> PostureAssessment:
    return PostureAssessment(
        assessed_at=assessed_at,
        state=state,
        category=category,
        message="test",
    )


def test_recorder_aggregates_categories_and_reminders(tmp_path) -> None:
    store = PostureHistoryStore(tmp_path / "history.sqlite3")
    recorder = WorkdayRecorder(store)
    start = datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)

    recorder.record(assessment(start), "desk")
    recorder.record(assessment(start + timedelta(seconds=1)), "desk")
    recorder.record(
        assessment(
            start + timedelta(seconds=2),
            PostureCategory.FORWARD_HEAD,
        ),
        "desk",
    )
    recorder.record(
        assessment(
            start + timedelta(seconds=4),
            PostureCategory.FORWARD_HEAD,
            TrackerState.WARNING,
        ),
        "desk",
    )
    alert_at = start + timedelta(seconds=5)
    recorder.record(
        assessment(
            alert_at,
            PostureCategory.FORWARD_HEAD,
            TrackerState.ALERT,
        ),
        "desk",
    )
    recorder.record_reminder(
        ReminderEvent(
            occurred_at=alert_at,
            setup_id="desk",
            category=PostureCategory.FORWARD_HEAD,
        )
    )
    recorder.suspend()

    summary = store.daily_summary(start.astimezone().date())
    assert summary.totals[BASELINE_POSTURE] == 2
    assert summary.totals[PostureCategory.FORWARD_HEAD.value] == 3
    assert summary.reminder_count == 1
    assert summary.episodes[-1].peak_state == TrackerState.ALERT
    store.close()


def test_tracking_gap_adds_no_unseen_time(tmp_path) -> None:
    store = PostureHistoryStore(tmp_path / "history.sqlite3")
    recorder = WorkdayRecorder(store, maximum_gap_seconds=2)
    start = datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)

    recorder.record(assessment(start), "desk")
    recorder.record(assessment(start + timedelta(seconds=1)), "desk")
    recorder.record(assessment(start + timedelta(seconds=10)), "desk")
    recorder.record(assessment(start + timedelta(seconds=11)), "desk")
    recorder.suspend()

    summary = store.daily_summary(start.astimezone().date())
    assert summary.totals[BASELINE_POSTURE] == 2
    assert len(summary.episodes) == 2
    store.close()


def test_interval_is_split_at_local_midnight(tmp_path) -> None:
    local_timezone = datetime.now().astimezone().tzinfo
    before_midnight = datetime.combine(
        datetime.now().date(),
        time(23, 59, 59),
        tzinfo=local_timezone,
    )
    after_midnight = before_midnight + timedelta(seconds=2)
    store = PostureHistoryStore(tmp_path / "history.sqlite3")
    recorder = WorkdayRecorder(store)

    recorder.record(assessment(before_midnight), "desk")
    recorder.record(assessment(after_midnight), "desk")
    recorder.suspend()

    before = store.daily_summary(before_midnight.date())
    after = store.daily_summary(after_midnight.date())
    assert before.totals[BASELINE_POSTURE] == 1
    assert after.totals[BASELINE_POSTURE] == 1
    store.close()


def test_delete_day_removes_episodes_and_reminders(tmp_path) -> None:
    store = PostureHistoryStore(tmp_path / "history.sqlite3")
    recorder = WorkdayRecorder(store)
    start = datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)
    local_date = start.astimezone().date()

    recorder.record(assessment(start), "desk")
    recorder.record(assessment(start + timedelta(seconds=1)), "desk")
    recorder.record_reminder(
        ReminderEvent(
            occurred_at=start,
            setup_id="desk",
            category=PostureCategory.GENERAL_DEVIATION,
        )
    )
    recorder.suspend()
    store.delete_day(local_date)

    summary = store.daily_summary(local_date)
    assert summary.tracked_seconds == 0
    assert summary.reminder_count == 0
    assert summary.episodes == []
    store.close()
