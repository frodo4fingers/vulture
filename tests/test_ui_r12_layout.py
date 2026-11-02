from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from vulture.history import DailyPostureSummary, HistoryStorageError
from vulture.i18n import set_language
from vulture.models import InterfaceLanguage
from vulture.ui.summary_dialog import WorkdaySummaryDialog

from tests.test_ui import _make_window, _teardown_window


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def english() -> None:
    set_language(InterfaceLanguage.ENGLISH)
    yield
    set_language(InterfaceLanguage.ENGLISH)


def test_storage_error_shows_one_calm_sentence_with_raw_tooltip(
    application: QApplication,
) -> None:
    empty = DailyPostureSummary(
        local_date=date(2026, 7, 20),
        totals={},
        tracked_seconds=0,
        reminder_count=0,
        episodes=[],
    )
    dialog = WorkdaySummaryDialog(
        lambda _day: empty, lambda _day: None, lambda: None, {}, True
    )

    dialog._show_storage_error(HistoryStorageError("disk I/O error"))

    assert dialog.empty_state.text() == (
        "The workday summary could not be loaded right now."
    )
    assert dialog.empty_state.toolTip() == "disk I/O error"

    dialog.refresh()

    assert dialog.empty_state.toolTip() == ""
    dialog.close()


def test_empty_card_clears_the_privacy_note_at_960x640(
    application: QApplication,
    tmp_path,
) -> None:
    window = _make_window(tmp_path)
    window.resize(960, 640)
    window.show()
    application.processEvents()

    card = window.first_run_panel
    note = window.privacy_note
    assert card.isVisible()
    assert note.isVisible()
    card_bottom = card.mapTo(window, QPoint(0, 0)).y() + card.height()
    note_top = note.mapTo(window, QPoint(0, 0)).y()
    assert window.height() == 640
    assert card_bottom + 8 <= note_top

    _teardown_window(window, application)
