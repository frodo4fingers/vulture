from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from PySide6.QtWidgets import QApplication

from vulture.breaks import BreakChannel
from vulture.history import (
    BreakEvent,
    DailyPostureSummary,
    HistoryStorageError,
)
from vulture.i18n import set_language
from vulture.models import InterfaceLanguage
from vulture.ui.summary_dialog import WorkdaySummaryDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def english() -> None:
    set_language(InterfaceLanguage.ENGLISH)
    yield
    set_language(InterfaceLanguage.ENGLISH)


def _summary(breaks: list[BreakEvent]) -> DailyPostureSummary:
    return DailyPostureSummary(
        local_date=date(2026, 7, 20),
        totals={},
        tracked_seconds=3600,
        reminder_count=2,
        episodes=[],
        breaks=breaks,
    )


def test_storage_error_sets_accessible_description_and_refresh_clears_it(
    application: QApplication,
) -> None:
    dialog = WorkdaySummaryDialog(
        lambda _day: _summary([]), lambda _day: None, lambda: None, {}, True
    )

    dialog._show_storage_error(HistoryStorageError("disk I/O error"))

    assert dialog.empty_state.accessibleDescription() == "disk I/O error"

    dialog.refresh()

    assert dialog.empty_state.accessibleDescription() == ""
    dialog.close()


def test_summary_tiles_share_one_width_and_rows_are_a_deliberate_hierarchy(
    application: QApplication,
) -> None:
    day = date(2026, 7, 20)
    breaks = [
        BreakEvent(
            kind="movement",
            channel=BreakChannel.MOVEMENT,
            completed_at=datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
            local_date=day,
            duration_seconds=120,
        )
    ]
    dialog = WorkdaySummaryDialog(
        lambda _day: _summary(breaks),
        lambda _day: None,
        lambda: None,
        {},
        True,
    )
    dialog.show()
    application.processEvents()

    headline = [dialog.daily_breaks_metric, dialog.daily_moved_metric]
    quiet = [dialog.daily_nudges_metric, dialog.daily_tracked_metric]
    assert all(tile.isVisible() for tile in headline + quiet)
    assert len({tile.width() for tile in headline + quiet}) == 1
    assert len({tile.height() for tile in headline}) == 1
    assert len({tile.height() for tile in quiet}) == 1
    assert headline[0].height() > quiet[0].height()
    dialog.close()
