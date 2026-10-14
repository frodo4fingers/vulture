from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication, QScrollArea

from tests.test_ui_r4 import _rest, _stopped_after, clock  # noqa: F401
from vulture.breaks import ManualBreakChoice
from vulture.exercises import load_exercise_catalog
from vulture.i18n import set_language
from vulture.history import DailyPostureSummary
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


@pytest.mark.parametrize(
    ("language", "stop"),
    [
        (InterfaceLanguage.ENGLISH, "Stop if"),
        (InterfaceLanguage.GERMAN, "Hören Sie auf"),
        (InterfaceLanguage.SPANISH, "Deténgase"),
    ],
)
def test_walk_safety_says_stop_not_skip(
    language: InterfaceLanguage, stop: str
) -> None:
    # While the timer runs Stop early is the only exit, so the advice
    # must name that action rather than Skip.
    catalog = load_exercise_catalog(language=language)
    walk = next(e for e in catalog.exercises if e.id == "easy-walk")
    assert walk.safety.startswith(stop)


def test_stop_early_tooltip_admits_short_breaks_do_not_count(
    application: QApplication,
) -> None:
    dialog = _rest()
    assert dialog.stop_button.toolTip() == (
        "Ends the break now. A very short break is not counted."
    )
    dialog.close()


def test_short_stop_note_names_the_eye_break_floor(
    application: QApplication, clock: list[float]
) -> None:
    dialog = _rest(ManualBreakChoice.EYE_REST)  # 20 s: the floor is 5 s
    _stopped_after(dialog, clock, 2)
    assert dialog.completion_note.text() == (
        "No problem — breaks under 5 seconds aren't counted. "
        "The next one comes soon."
    )
    dialog.close()


def test_day_and_week_tabs_scroll_instead_of_squeezing(
    application: QApplication,
) -> None:
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
    for index, page in (
        (dialog.day_tab_index, dialog.day_page),
        (dialog.week_tab_index, dialog.week_page),
    ):
        host = dialog.period_tabs.widget(index)
        assert isinstance(host, QScrollArea)
        assert host.widget() is page
    dialog.close()
