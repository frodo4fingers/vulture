from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication

from vulture.history import DailyPostureSummary, HistoryStorageError
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


def _failing_delete(_day: date) -> None:
    raise HistoryStorageError("database is locked")


def test_delete_failure_shows_raw_error_in_details_caption(
    application: QApplication,
) -> None:
    summary = DailyPostureSummary(
        local_date=date(2026, 7, 20),
        totals={},
        tracked_seconds=3600,
        reminder_count=0,
        episodes=[],
        breaks=[],
    )
    dialog = WorkdaySummaryDialog(
        lambda _day: summary, _failing_delete, lambda: None, {}, True
    )
    dialog.show()
    caption = dialog.delete_confirmation_details
    assert caption.isHidden()

    dialog._delete_selected_day()
    dialog._confirm_history_delete()

    assert "could not be deleted" in dialog.delete_confirmation.text()
    assert dialog.delete_confirmation.toolTip() == "database is locked"
    assert caption.text() == "database is locked"
    assert caption.isVisible()
    dialog.close()


def test_new_delete_confirmation_hides_details_caption(
    application: QApplication,
) -> None:
    summary = DailyPostureSummary(
        local_date=date(2026, 7, 20),
        totals={},
        tracked_seconds=3600,
        reminder_count=0,
        episodes=[],
        breaks=[],
    )
    dialog = WorkdaySummaryDialog(
        lambda _day: summary, _failing_delete, lambda: None, {}, True
    )
    dialog.show()
    dialog._delete_selected_day()
    dialog._confirm_history_delete()
    caption = dialog.delete_confirmation_details
    assert caption.isVisible()

    dialog._delete_all_history()

    assert caption.text() == ""
    assert caption.isHidden()
    dialog.close()
