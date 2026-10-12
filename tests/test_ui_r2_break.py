from __future__ import annotations

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import vulture.ui.break_options as break_options
from vulture.breaks import ManualBreakChoice, manual_break_prompt
from vulture.exercises import load_exercise_catalog
from vulture.models import BreakPreferences
from vulture.ui.break_options import RestBreakDialog, RestBreakOutcome
from vulture.ui.exercises import (
    EvidenceDialog,
    ExerciseDialog,
    ExerciseOutcome,
)

CHOICES = (ManualBreakChoice.STAND, ManualBreakChoice.GUIDED_MOVEMENT)


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [100.0]
    monkeypatch.setattr(break_options.time, "monotonic", lambda: now[0])
    return now


def _exercise(exercise_id: str, **kwargs) -> ExerciseDialog:
    catalog = load_exercise_catalog()
    exercise = next(e for e in catalog.exercises if e.id == exercise_id)
    return ExerciseDialog(
        exercise, catalog, alternative_choices=CHOICES, **kwargs
    )


def _rest(**kwargs) -> RestBreakDialog:
    prompt = manual_break_prompt(ManualBreakChoice.COFFEE, BreakPreferences())
    return RestBreakDialog(prompt, CHOICES, **kwargs)


def _plain(text: str) -> str:
    return text.replace("&", "")


@pytest.mark.parametrize("make", [lambda: _exercise("easy-walk"), _rest])
def test_one_primary_then_not_now_menu(application, make) -> None:
    dialog = make()
    dialog.show()
    assert not dialog.start_button.isHidden()
    assert not dialog.not_now_button.isHidden()
    assert dialog.done_button.isHidden()
    assert dialog.stop_button.isHidden()
    assert _plain(dialog.start_button.text()) == "Start"
    items = [_plain(a.text()) for a in dialog.not_now_menu.actions()]
    assert "Skip" in items and "Swap…" in items
    assert not any(
        "Remind me later" in _plain(b.text())
        for b in dialog.findChildren(type(dialog.start_button))
    )
    dialog.reject()


def test_later_and_swap_keep_their_outcomes(application) -> None:
    later = _exercise("shoulder-roll")
    later.not_now_menu.actions()[0].trigger()
    assert later.outcome == ExerciseOutcome.POSTPONED

    swap = _exercise("shoulder-roll")
    swap.alternative_picker.actions()[1].trigger()
    assert swap.outcome == ExerciseOutcome.SWAPPED

    rest = _rest()
    rest.alternative_picker.actions()[0].trigger()
    assert rest.outcome == RestBreakOutcome.SWITCHED
    assert rest.selected_choice is ManualBreakChoice.STAND


def test_running_timer_offers_only_stop_early(application, clock) -> None:
    dialog = _exercise("easy-walk")
    dialog.show()
    assert dialog.remaining_seconds() is None
    dialog.start_button.click()
    assert dialog.not_now_button.isHidden()
    assert not dialog.stop_button.isHidden()
    assert dialog.done_button.isHidden()
    clock[0] += 120
    dialog._update_countdown()
    assert dialog.remaining_seconds() == 180
    assert dialog.countdown.accessibleName() == "Time remaining"
    clock[0] += 500
    dialog._update_countdown()
    assert not dialog.done_button.isHidden()
    assert dialog.stop_button.isHidden()
    dialog.reject()


def test_stop_early_records_elapsed_time(application, clock) -> None:
    dialog = _rest(breaks_today=4)
    dialog.show()
    dialog.start_button.click()
    clock[0] += 90
    dialog.stop_button.click()
    assert dialog.outcome == RestBreakOutcome.COMPLETED
    assert dialog.completed_seconds == pytest.approx(90)
    assert dialog.completion_note.text() == (
        "Nice work — that's 4 breaks today."
    )
    assert dialog.isVisible()
    dialog._ack_timer.timeout.emit()
    assert not dialog.isVisible()


def test_done_without_timer_records_suggested_time(application) -> None:
    dialog = _rest()
    dialog._finish()
    assert dialog.completed_seconds == dialog.prompt.duration_seconds
    assert dialog.completion_note.text() == "Nice work — break done."


def test_rep_dose_shows_done_after_start(application) -> None:
    dialog = _exercise("ankle-point-flex")
    dialog.show()
    assert dialog.done_button.isHidden()
    dialog.start_button.click()
    assert not dialog.done_button.isHidden()
    assert dialog.remaining_seconds() is None
    dialog.reject()


def test_contract_and_break_mode(application) -> None:
    rest = _rest()
    assert RestBreakDialog.wants_break_mode is True
    assert rest.active_break_title == rest.prompt.title
    assert _exercise("easy-walk").active_break_title == "Easy desk-side walk"


def test_announces_only_start_minute_and_zero(
    application, clock, monkeypatch
) -> None:
    said: list[str] = []
    monkeypatch.setattr(
        break_options, "announce", lambda _widget, message: said.append(message)
    )
    dialog = _rest()
    dialog.start_button.click()
    for _ in range(400):
        clock[0] += 1
        dialog._update_countdown()
    assert len(said) == 3
    assert said[1:] == ["One minute left.", "Suggested time complete"]


def test_global_safety_never_twice(application) -> None:
    dialog = _exercise("shoulder-roll", show_full_safety=True)
    global_safety = dialog.catalog.global_safety
    assert global_safety in dialog.safety.text()
    assert dialog.global_safety.isHidden()
    dialog._show_global_safety_inline(False)
    assert global_safety not in dialog.safety.text()
    assert not dialog.global_safety.isHidden()


def test_suggested_time_printed_once(application) -> None:
    dialog = _rest()
    texts = [
        label.text()
        for label in dialog.findChildren(type(dialog.countdown))
    ]
    assert not any("Suggested time" in text for text in texts)


def test_walk_away_thumbnail_is_small(application) -> None:
    dialog = _exercise("easy-walk")
    dialog.resize(700, 700)
    dialog.show()
    QTest.qWait(50)
    assert dialog._thumbnail is not None
    assert dialog._thumbnail.width() <= 0.3 * dialog.width() + 1
    dialog.reject()


def test_evidence_contents_link_scrolls(application) -> None:
    dialog = EvidenceDialog(load_exercise_catalog())
    dialog.show()
    QTest.qWait(50)
    assert "#media" in dialog.browser.toHtml()
    dialog.browser.setSource(QUrl("#media"))
    assert dialog.browser.verticalScrollBar().value() > 0
    dialog.close()
