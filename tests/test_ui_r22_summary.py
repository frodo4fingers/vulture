from __future__ import annotations

import re
from datetime import date

import pytest
from PySide6.QtWidgets import QAbstractButton, QApplication

from vulture.history import DailyPostureSummary
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


@pytest.mark.parametrize("language", list(InterfaceLanguage))
@pytest.mark.parametrize("scope", ["day", "all"])
def test_confirm_button_is_distinct_with_unique_mnemonics(
    application: QApplication, language: InterfaceLanguage, scope: str
) -> None:
    set_language(language)
    summary = DailyPostureSummary(
        local_date=date(2026, 7, 20),
        totals={},
        tracked_seconds=0,
        reminder_count=0,
        episodes=[],
    )
    dialog = WorkdaySummaryDialog(
        lambda _day: summary, lambda _day: None, lambda: None, {}, True
    )
    dialog.show()
    if scope == "day":
        dialog._delete_selected_day()
    else:
        dialog._delete_all_history()

    confirm = dialog.confirm_delete_button.text()
    assert confirm not in (
        dialog.delete_day_button.text(),
        dialog.delete_all_button.text(),
    )
    keys = [
        m.group(1).lower()
        for button in dialog.findChildren(QAbstractButton)
        if button.isVisibleTo(dialog)
        and (m := re.search(r"(?<!&)&(\w)", button.text()))
    ]
    assert len(keys) == len(set(keys)), keys
    dialog.close()


@pytest.mark.parametrize("language", list(InterfaceLanguage))
def test_empty_state_shows_its_whole_text(
    application: QApplication, language: InterfaceLanguage
) -> None:
    set_language(language)
    summary = DailyPostureSummary(
        local_date=date(2026, 7, 20),
        totals={},
        tracked_seconds=0,
        reminder_count=0,
        episodes=[],
    )
    dialog = WorkdaySummaryDialog(
        lambda _day: summary, lambda _day: None, lambda: None, {}, True
    )
    dialog.show()
    application.processEvents()

    label = dialog.empty_state
    assert label.isVisibleTo(dialog)
    assert label.height() >= label.heightForWidth(label.width())
    dialog.close()
