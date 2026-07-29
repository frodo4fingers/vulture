from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from pydantic import Field

from vulture.i18n import tr
from vulture.models import (
    ReminderEvent,
    StrictModel,
    TrackerState,
)
from vulture.tracking import PostureAssessment


BASELINE_POSTURE = "baseline"
VALID_TRACKING_STATES = {
    TrackerState.GOOD,
    TrackerState.WARNING,
    TrackerState.ALERT,
}
STATE_RANK = {
    TrackerState.GOOD: 0,
    TrackerState.WARNING: 1,
    TrackerState.ALERT: 2,
}


class HistoryStorageError(RuntimeError):
    pass


class StoredPostureEpisode(StrictModel):
    id: int
    local_date: date
    started_at: datetime
    ended_at: datetime
    utc_offset_minutes: int
    setup_id: str
    posture: str
    peak_state: TrackerState
    duration_seconds: float = Field(ge=0)
    sample_count: int = Field(ge=1)


class DailyPostureSummary(StrictModel):
    local_date: date
    totals: dict[str, float]
    tracked_seconds: float = Field(ge=0)
    reminder_count: int = Field(ge=0)
    episodes: list[StoredPostureEpisode]


class ActivePostureEpisode(StrictModel):
    database_id: int
    local_date: date
    started_at: datetime
    ended_at: datetime
    utc_offset_minutes: int
    setup_id: str
    posture: str
    peak_state: TrackerState
    duration_seconds: float = Field(default=0.0, ge=0)
    sample_count: int = Field(default=1, ge=1)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("History timestamps must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _local_metadata(value: datetime) -> tuple[date, int]:
    local = value.astimezone()
    offset = local.utcoffset() or timedelta()
    return local.date(), round(offset.total_seconds() / 60)


class PostureHistoryStore:
    SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path
        self._closed = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path, timeout=3.0)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA busy_timeout = 3000")
            self._connection.execute("PRAGMA journal_mode = DELETE")
            self._connection.execute("PRAGMA synchronous = NORMAL")
            self._connection.execute("PRAGMA secure_delete = ON")
            self._initialize_schema()
            if os.name != "nt":
                self.path.chmod(0o600)
        except (OSError, sqlite3.Error) as error:
            raise HistoryStorageError(
                tr(
                    "Could not initialize posture history at {path}: {error}",
                    path=self.path,
                    error=error,
                )
            ) from error

    def _initialize_schema(self) -> None:
        version = int(
            self._connection.execute("PRAGMA user_version").fetchone()[0]
        )
        if version not in (0, self.SCHEMA_VERSION):
            raise HistoryStorageError(
                tr(
                    "Unsupported posture history schema version {version}.",
                    version=version,
                )
            )
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS posture_episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                local_date TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL,
                utc_offset_minutes INTEGER NOT NULL,
                setup_id TEXT NOT NULL,
                posture TEXT NOT NULL,
                peak_state TEXT NOT NULL,
                duration_seconds REAL NOT NULL CHECK (duration_seconds >= 0),
                sample_count INTEGER NOT NULL CHECK (sample_count >= 1)
            );
            CREATE INDEX IF NOT EXISTS idx_posture_episodes_date
                ON posture_episodes(local_date, started_at);

            CREATE TABLE IF NOT EXISTS reminder_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                local_date TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                utc_offset_minutes INTEGER NOT NULL,
                setup_id TEXT NOT NULL,
                category TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_reminder_events_date
                ON reminder_events(local_date, occurred_at);
            """
        )
        if version == 0:
            self._connection.execute(
                f"PRAGMA user_version = {self.SCHEMA_VERSION}"
            )
        self._connection.commit()

    def create_episode(self, episode: ActivePostureEpisode) -> int:
        try:
            cursor = self._connection.execute(
                """
                INSERT INTO posture_episodes (
                    local_date,
                    started_at,
                    ended_at,
                    utc_offset_minutes,
                    setup_id,
                    posture,
                    peak_state,
                    duration_seconds,
                    sample_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode.local_date.isoformat(),
                    _as_utc(episode.started_at).isoformat(),
                    _as_utc(episode.ended_at).isoformat(),
                    episode.utc_offset_minutes,
                    episode.setup_id,
                    episode.posture,
                    episode.peak_state.value,
                    episode.duration_seconds,
                    episode.sample_count,
                ),
            )
            self._connection.commit()
            return int(cursor.lastrowid)
        except sqlite3.Error as error:
            raise HistoryStorageError(
                tr(
                    "Could not start a posture history episode: {error}",
                    error=error,
                )
            ) from error

    def update_episode(self, episode: ActivePostureEpisode) -> None:
        try:
            self._connection.execute(
                """
                UPDATE posture_episodes
                SET ended_at = ?,
                    peak_state = ?,
                    duration_seconds = ?,
                    sample_count = ?
                WHERE id = ?
                """,
                (
                    _as_utc(episode.ended_at).isoformat(),
                    episode.peak_state.value,
                    episode.duration_seconds,
                    episode.sample_count,
                    episode.database_id,
                ),
            )
            self._connection.commit()
        except sqlite3.Error as error:
            raise HistoryStorageError(
                tr(
                    "Could not update posture history: {error}",
                    error=error,
                )
            ) from error

    def delete_episode(self, episode_id: int) -> None:
        try:
            self._connection.execute(
                "DELETE FROM posture_episodes WHERE id = ?",
                (episode_id,),
            )
            self._connection.commit()
        except sqlite3.Error as error:
            raise HistoryStorageError(
                tr(
                    "Could not remove an empty posture episode: {error}",
                    error=error,
                )
            ) from error

    def record_reminder(self, event: ReminderEvent) -> None:
        local_date, offset_minutes = _local_metadata(event.occurred_at)
        try:
            self._connection.execute(
                """
                INSERT INTO reminder_events (
                    local_date,
                    occurred_at,
                    utc_offset_minutes,
                    setup_id,
                    category
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    local_date.isoformat(),
                    _as_utc(event.occurred_at).isoformat(),
                    offset_minutes,
                    event.setup_id,
                    event.category.value,
                ),
            )
            self._connection.commit()
        except sqlite3.Error as error:
            raise HistoryStorageError(
                tr(
                    "Could not save a posture reminder event: {error}",
                    error=error,
                )
            ) from error

    def daily_summary(self, local_date: date) -> DailyPostureSummary:
        try:
            total_rows = self._connection.execute(
                """
                SELECT posture, SUM(duration_seconds) AS duration
                FROM posture_episodes
                WHERE local_date = ? AND duration_seconds > 0
                GROUP BY posture
                """,
                (local_date.isoformat(),),
            ).fetchall()
            totals = {
                str(row["posture"]): float(row["duration"] or 0.0)
                for row in total_rows
            }
            episode_rows = self._connection.execute(
                """
                SELECT id,
                       local_date,
                       started_at,
                       ended_at,
                       utc_offset_minutes,
                       setup_id,
                       posture,
                       peak_state,
                       duration_seconds,
                       sample_count
                FROM posture_episodes
                WHERE local_date = ? AND duration_seconds > 0
                ORDER BY started_at ASC
                LIMIT 1000
                """,
                (local_date.isoformat(),),
            ).fetchall()
            reminder_count = int(
                self._connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM reminder_events
                    WHERE local_date = ?
                    """,
                    (local_date.isoformat(),),
                ).fetchone()[0]
            )
        except sqlite3.Error as error:
            raise HistoryStorageError(
                tr(
                    "Could not read the workday summary: {error}",
                    error=error,
                )
            ) from error

        episodes = [
            StoredPostureEpisode(
                id=int(row["id"]),
                local_date=date.fromisoformat(str(row["local_date"])),
                started_at=datetime.fromisoformat(str(row["started_at"])),
                ended_at=datetime.fromisoformat(str(row["ended_at"])),
                utc_offset_minutes=int(row["utc_offset_minutes"]),
                setup_id=str(row["setup_id"]),
                posture=str(row["posture"]),
                peak_state=TrackerState(str(row["peak_state"])),
                duration_seconds=float(row["duration_seconds"]),
                sample_count=int(row["sample_count"]),
            )
            for row in episode_rows
        ]
        return DailyPostureSummary(
            local_date=local_date,
            totals=totals,
            tracked_seconds=sum(totals.values()),
            reminder_count=reminder_count,
            episodes=episodes,
        )

    def delete_day(self, local_date: date) -> None:
        try:
            with self._connection:
                self._connection.execute(
                    "DELETE FROM posture_episodes WHERE local_date = ?",
                    (local_date.isoformat(),),
                )
                self._connection.execute(
                    "DELETE FROM reminder_events WHERE local_date = ?",
                    (local_date.isoformat(),),
                )
        except sqlite3.Error as error:
            raise HistoryStorageError(
                tr(
                    "Could not delete the selected workday: {error}",
                    error=error,
                )
            ) from error

    def delete_all(self) -> None:
        try:
            with self._connection:
                self._connection.execute("DELETE FROM posture_episodes")
                self._connection.execute("DELETE FROM reminder_events")
            self._connection.execute("VACUUM")
        except sqlite3.Error as error:
            raise HistoryStorageError(
                tr(
                    "Could not delete posture history: {error}",
                    error=error,
                )
            ) from error

    def prune(self, retention_days: int) -> None:
        cutoff = datetime.now().astimezone().date() - timedelta(
            days=max(1, retention_days) - 1
        )
        try:
            with self._connection:
                self._connection.execute(
                    "DELETE FROM posture_episodes WHERE local_date < ?",
                    (cutoff.isoformat(),),
                )
                self._connection.execute(
                    "DELETE FROM reminder_events WHERE local_date < ?",
                    (cutoff.isoformat(),),
                )
        except sqlite3.Error as error:
            raise HistoryStorageError(
                tr(
                    "Could not prune posture history: {error}",
                    error=error,
                )
            ) from error

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._connection.close()
            self._closed = True
        except sqlite3.Error as error:
            raise HistoryStorageError(
                tr(
                    "Could not close posture history: {error}",
                    error=error,
                )
            ) from error


class WorkdayRecorder:
    def __init__(
        self,
        store: PostureHistoryStore,
        *,
        enabled: bool = True,
        maximum_gap_seconds: float = 2.0,
    ) -> None:
        self.store = store
        self.enabled = enabled
        self.maximum_gap_seconds = maximum_gap_seconds
        self._active: ActivePostureEpisode | None = None
        self._last_seen_at: datetime | None = None

    def record(
        self,
        assessment: PostureAssessment,
        setup_id: str,
    ) -> None:
        if not self.enabled or assessment.state not in VALID_TRACKING_STATES:
            self.suspend()
            return

        captured_at = _as_utc(assessment.assessed_at)
        posture = (
            assessment.category.value
            if assessment.category is not None
            else BASELINE_POSTURE
        )
        if self._active is None or self._last_seen_at is None:
            self._start_episode(
                captured_at,
                setup_id,
                posture,
                assessment.state,
            )
            return

        elapsed = (captured_at - self._last_seen_at).total_seconds()
        if elapsed <= 0:
            self._update_peak_state(assessment.state)
            return
        if elapsed > self.maximum_gap_seconds:
            self.suspend()
            self._start_episode(
                captured_at,
                setup_id,
                posture,
                assessment.state,
            )
            return

        same_episode = (
            self._active.setup_id == setup_id
            and self._active.posture == posture
        )
        self._add_interval(self._last_seen_at, captured_at)
        if not same_episode:
            self._finalize()
            self._start_episode(
                captured_at,
                setup_id,
                posture,
                assessment.state,
            )
            return

        self._active.sample_count += 1
        self._update_peak_state(assessment.state)
        self._last_seen_at = captured_at

    def record_reminder(self, event: ReminderEvent) -> None:
        if self.enabled:
            self.store.record_reminder(event)

    def checkpoint(self) -> None:
        if self._active is not None:
            self.store.update_episode(self._active)

    def suspend(self) -> None:
        self._finalize()

    def set_enabled(self, enabled: bool) -> None:
        if not enabled:
            self.suspend()
        self.enabled = enabled

    def close(self) -> None:
        self.suspend()
        self.store.close()

    def _start_episode(
        self,
        captured_at: datetime,
        setup_id: str,
        posture: str,
        state: TrackerState,
        *,
        peak_state: TrackerState | None = None,
    ) -> None:
        local_date, offset_minutes = _local_metadata(captured_at)
        episode = ActivePostureEpisode(
            database_id=0,
            local_date=local_date,
            started_at=captured_at,
            ended_at=captured_at,
            utc_offset_minutes=offset_minutes,
            setup_id=setup_id,
            posture=posture,
            peak_state=peak_state or state,
        )
        episode.database_id = self.store.create_episode(episode)
        self._active = episode
        self._last_seen_at = captured_at

    def _add_interval(
        self,
        started_at: datetime,
        ended_at: datetime,
    ) -> None:
        cursor = started_at
        while cursor.astimezone().date() != ended_at.astimezone().date():
            local_cursor = cursor.astimezone()
            next_date = local_cursor.date() + timedelta(days=1)
            local_midnight = datetime.combine(
                next_date,
                time.min,
                tzinfo=local_cursor.tzinfo,
            )
            boundary = local_midnight.astimezone(timezone.utc)
            self._add_segment(cursor, boundary)
            active = self._active
            if active is None:
                return
            setup_id = active.setup_id
            posture = active.posture
            peak_state = active.peak_state
            self._finalize()
            self._start_episode(
                boundary,
                setup_id,
                posture,
                peak_state,
                peak_state=peak_state,
            )
            cursor = boundary
        self._add_segment(cursor, ended_at)

    def _add_segment(
        self,
        started_at: datetime,
        ended_at: datetime,
    ) -> None:
        if self._active is None:
            return
        seconds = max(0.0, (ended_at - started_at).total_seconds())
        self._active.duration_seconds += seconds
        self._active.ended_at = ended_at
        self._last_seen_at = ended_at

    def _update_peak_state(self, state: TrackerState) -> None:
        if self._active is None:
            return
        if STATE_RANK[state] > STATE_RANK[self._active.peak_state]:
            self._active.peak_state = state

    def _finalize(self) -> None:
        active = self._active
        self._active = None
        self._last_seen_at = None
        if active is None:
            return
        if active.duration_seconds <= 0:
            self.store.delete_episode(active.database_id)
        else:
            self.store.update_episode(active)
