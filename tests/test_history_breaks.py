from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

from vulture.breaks import BreakChannel
from vulture.history import (
    BreakEvent,
    PostureHistoryStore,
    WorkdayRecorder,
)
from vulture.models import PostureCategory, ReminderEvent


def break_event(
    day: date,
    *,
    kind: str = "movement",
    channel: BreakChannel = BreakChannel.MOVEMENT,
    exercise_id: str | None = "shoulder-roll",
    minute: int = 0,
) -> BreakEvent:
    return BreakEvent(
        kind=kind,
        channel=channel,
        exercise_id=exercise_id,
        completed_at=datetime(
            day.year, day.month, day.day, 12, minute, tzinfo=timezone.utc
        ),
        local_date=day,
        duration_seconds=45.5,
    )


def test_break_round_trip_orders_by_completion(tmp_path) -> None:
    store = PostureHistoryStore(tmp_path / "history.sqlite3")
    day = date(2026, 7, 20)
    later = break_event(
        day,
        kind="rest",
        channel=BreakChannel.EYE,
        exercise_id=None,
        minute=30,
    )
    earlier = break_event(day, minute=5)
    store.record_break(later)
    store.record_break(earlier)
    store.record_break(break_event(date(2026, 7, 21)))

    summary = store.daily_summary(day)

    assert summary.breaks == [earlier, later]
    assert summary.breaks[1].exercise_id is None
    assert store.daily_summary(date(2026, 7, 22)).breaks == []
    store.close()


def test_delete_day_and_delete_all_clear_breaks(tmp_path) -> None:
    store = PostureHistoryStore(tmp_path / "history.sqlite3")
    first, second = date(2026, 7, 20), date(2026, 7, 21)
    store.record_break(break_event(first))
    store.record_break(break_event(second))

    store.delete_day(first)
    assert store.daily_summary(first).breaks == []
    assert len(store.daily_summary(second).breaks) == 1

    store.delete_all()
    assert store.daily_summary(second).breaks == []
    assert not store.has_any_history()
    store.close()


def test_prune_removes_old_breaks_only(tmp_path) -> None:
    store = PostureHistoryStore(tmp_path / "history.sqlite3")
    today = datetime.now().astimezone().date()
    old = today - timedelta(days=30)
    store.record_break(break_event(old))
    store.record_break(break_event(today))

    store.prune(retention_days=7)

    assert store.daily_summary(old).breaks == []
    assert len(store.daily_summary(today).breaks) == 1
    store.close()


def test_existing_v1_file_without_break_table_gains_it(tmp_path) -> None:
    path = tmp_path / "history.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE reminder_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            local_date TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            utc_offset_minutes INTEGER NOT NULL,
            setup_id TEXT NOT NULL,
            category TEXT NOT NULL
        );
        INSERT INTO reminder_events VALUES
            (1, '2026-07-20', '2026-07-20T09:00:00+00:00', 0, 'desk',
             'forward_head');
        PRAGMA user_version = 1;
        """
    )
    connection.commit()
    connection.close()

    store = PostureHistoryStore(path)
    day = date(2026, 7, 20)
    store.record_break(break_event(day))

    summary = store.daily_summary(day)
    assert summary.reminder_count == 1
    assert len(summary.breaks) == 1
    version = store._connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == PostureHistoryStore.SCHEMA_VERSION
    store.close()


def test_has_any_history_sees_each_kind_of_row(tmp_path) -> None:
    now = datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)
    day = now.astimezone().date()

    store = PostureHistoryStore(tmp_path / "empty.sqlite3")
    assert not store.has_any_history()
    store.close()

    store = PostureHistoryStore(tmp_path / "breaks.sqlite3")
    store.record_break(break_event(day))
    assert store.has_any_history()
    store.close()

    store = PostureHistoryStore(tmp_path / "reminders.sqlite3")
    store.record_reminder(
        ReminderEvent(
            occurred_at=now,
            setup_id="desk",
            category=PostureCategory.FORWARD_HEAD,
        )
    )
    assert store.has_any_history()
    store.close()


def test_recorder_forwards_breaks_only_when_enabled(tmp_path) -> None:
    store = PostureHistoryStore(tmp_path / "history.sqlite3")
    recorder = WorkdayRecorder(store, enabled=False)
    day = date(2026, 7, 20)

    recorder.record_break(break_event(day))
    assert store.daily_summary(day).breaks == []

    recorder.set_enabled(True)
    recorder.record_break(break_event(day))
    assert len(store.daily_summary(day).breaks) == 1
    store.close()
