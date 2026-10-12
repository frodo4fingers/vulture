from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from PySide6.QtWidgets import QApplication

from vulture.history import BASELINE_POSTURE, DailyPostureSummary
from vulture.i18n import set_language
from vulture.models import InterfaceLanguage, TrackerState
from vulture.history import StoredPostureEpisode
from vulture.ui.summary import (
    SUMMARY_CHART_BUCKET_SECONDS,
    build_posture_area_data,
    ui_locale,
)
from vulture.ui.summary_dialog import WorkdaySummaryDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def english() -> None:
    set_language(InterfaceLanguage.ENGLISH)
    yield
    set_language(InterfaceLanguage.ENGLISH)


def _summary(minutes: int) -> DailyPostureSummary:
    workday = date(2026, 7, 20)
    start = datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)
    if not minutes:
        return DailyPostureSummary(
            local_date=workday,
            totals={},
            tracked_seconds=0,
            reminder_count=0,
            episodes=[],
        )
    return DailyPostureSummary(
        local_date=workday,
        totals={BASELINE_POSTURE: minutes * 60},
        tracked_seconds=minutes * 60,
        reminder_count=0,
        episodes=[
            StoredPostureEpisode(
                id=1,
                local_date=workday,
                started_at=start,
                ended_at=start + timedelta(minutes=minutes),
                utc_offset_minutes=0,
                setup_id="desk",
                posture=BASELINE_POSTURE,
                peak_state=TrackerState.GOOD,
                duration_seconds=minutes * 60,
                sample_count=2,
            )
        ],
    )


def _dialog(summary: DailyPostureSummary, *, recording: bool = True):
    return WorkdaySummaryDialog(
        lambda _day: summary,
        lambda _day: None,
        lambda: None,
        {"desk": "Desk"},
        recording,
    )


def test_columns_stop_at_the_last_bucket_with_data() -> None:
    data = build_posture_area_data(_summary(20))

    assert data is not None
    assert len(data.bucket_hours) == 2
    assert data.end_hour - data.start_hour == 2 * SUMMARY_CHART_BUCKET_SECONDS / 3_600


def test_ui_locale_follows_the_interface_language() -> None:
    assert ui_locale().name() == "en_US"
    set_language(InterfaceLanguage.GERMAN)
    assert ui_locale().name() == "de_DE"


def test_day_chart_is_stacked_columns_with_legend_and_text_summary(
    application: QApplication,
) -> None:
    dialog = _dialog(_summary(30))
    chart = dialog.posture_chart

    assert [posture for posture, _bars in chart._bar_sets] == [BASELINE_POSTURE]
    assert chart.chart().legend().isVisible()
    assert "Within baseline" in chart.accessibleDescription()
    assert chart.accessibleDescription() != "Tracked posture time"
    dialog.close()


def test_recording_notice_only_when_recording_is_off(
    application: QApplication,
) -> None:
    on = _dialog(_summary(30))
    off = _dialog(_summary(30), recording=False)

    assert on.recording_label.isHidden()
    assert not off.recording_label.isHidden()
    on.close()
    off.close()


def test_empty_history_disables_delete_and_keeps_date_unfocused(
    application: QApplication,
) -> None:
    empty = _dialog(_summary(0))
    full = _dialog(_summary(30))
    empty.show()

    assert not empty.delete_all_button.isEnabled()
    assert full.delete_all_button.isEnabled()
    assert empty.focusWidget() is not empty.date_edit
    empty.close()
    full.close()
