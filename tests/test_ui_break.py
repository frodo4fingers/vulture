from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from vulture.breaks import ManualBreakChoice
from vulture.exercises import load_exercise_catalog
from vulture.ui.break_options import AlternativeBreakPicker
from vulture.ui.exercises import (
    ExerciseDialog,
    ExerciseOutcome,
    dose_duration_seconds,
    dose_set_count,
)


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _dialog(exercise_id: str, **kwargs) -> ExerciseDialog:
    catalog = load_exercise_catalog()
    exercise = next(e for e in catalog.exercises if e.id == exercise_id)
    return ExerciseDialog(exercise, catalog, **kwargs)


@pytest.mark.parametrize(
    ("dose", "seconds"),
    [
        ("5 minutes", 300),
        ("One slow round; about 2-3 minutes", 180),
        ("5 Minuten", 300),
        ("unos 2-3 minutos", 180),
        ("Hold 5-10 seconds; repeat 5 times", None),
        ("5 slow repetitions", None),
    ],
)
def test_dose_duration_seconds(dose: str, seconds: int | None) -> None:
    assert dose_duration_seconds(dose) == seconds


@pytest.mark.parametrize(
    ("dose", "sets"),
    [
        ("2 sets of 5 per foot", 2),
        ("3 slow rounds per hand", 3),
        ("3 cycles per wrist", 3),
        ("5 slow repetitions", None),
    ],
)
def test_dose_set_count(dose: str, sets: int | None) -> None:
    assert dose_set_count(dose) == sets


def test_exercise_dialog_has_no_default_button(
    application: QApplication,
) -> None:
    dialog = _dialog("shoulder-roll")
    dialog.show()
    for button in dialog.findChildren(QPushButton):
        assert not button.isDefault()
        assert not button.autoDefault()
    QTest.keyClick(dialog, Qt.Key.Key_Return)
    assert dialog.result() == 0
    assert dialog.outcome == ExerciseOutcome.POSTPONED
    dialog.reject()


def test_wants_break_mode_flag() -> None:
    assert ExerciseDialog.wants_break_mode is True


def test_walk_away_flow_uses_start_then_done(
    application: QApplication,
) -> None:
    dialog = _dialog("easy-walk")
    dialog.show()
    assert dialog.walk_away
    assert not dialog.start_button.isHidden()
    # The suggested time is the hero before Start.
    assert not dialog.countdown_block.isHidden()
    assert dialog.countdown_caption.text() == "suggested"

    dialog.start_button.click()
    assert dialog.start_button.isHidden()
    assert dialog.preview.isHidden()
    assert not dialog.countdown_block.isHidden()
    assert dialog.countdown.text() == "5:00"
    # While the timer runs only "Stop early" remains.
    assert not dialog.stop_button.isHidden()
    assert dialog.not_now_button.isHidden()
    assert dialog.done_button.isHidden()
    dialog.reject()


def test_rep_dose_has_checklist_and_no_timer(
    application: QApplication,
) -> None:
    dialog = _dialog("ankle-point-flex")
    dialog.show()
    assert len(dialog.set_checkboxes) == 2
    assert not dialog.start_button.isHidden()
    assert dialog.done_button.isHidden()
    dialog.start_button.click()
    assert not dialog.done_button.isHidden()
    dialog.reject()


def test_global_safety_only_in_details_unless_requested(
    application: QApplication,
) -> None:
    catalog = load_exercise_catalog()
    quiet = _dialog("shoulder-roll")
    full = _dialog("shoulder-roll", show_full_safety=True)
    assert catalog.global_safety in quiet.global_safety.text()
    assert not quiet.global_safety.isVisible()
    from vulture.ui.common import SemanticLabel

    def inline_text(dialog: ExerciseDialog) -> str:
        return " ".join(
            label.text() for label in dialog.findChildren(SemanticLabel)
        )

    assert catalog.global_safety not in inline_text(quiet)
    assert catalog.global_safety in inline_text(full)


def test_done_shows_acknowledgement_then_closes(
    application: QApplication,
) -> None:
    dialog = _dialog("shoulder-roll")
    dialog.show()
    dialog.start_button.click()
    dialog.done_button.click()
    assert dialog.outcome == ExerciseOutcome.COMPLETED
    assert dialog.completion_note.isVisible()
    assert dialog.isVisible()
    dialog._ack_timer.timeout.emit()
    assert not dialog.isVisible()


def test_swap_menu_emits_choice(application: QApplication) -> None:
    picker = AlternativeBreakPicker((ManualBreakChoice.STAND,))
    seen: list[str] = []
    picker.choice_selected.connect(seen.append)
    picker.actions()[0].trigger()
    assert seen == [ManualBreakChoice.STAND.value]
