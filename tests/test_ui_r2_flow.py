from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

import vulture.ui.break_options as break_options
from tests.test_ui import _make_window, _teardown_window
from vulture.breaks import BreakChannel, ManualBreakChoice
from vulture.history import BreakEvent


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [100.0]
    monkeypatch.setattr(break_options.time, "monotonic", lambda: now[0])
    return now


def _today_breaks(window) -> list[BreakEvent]:
    return window.history_store.daily_summary(
        datetime.now().astimezone().date()
    ).breaks


def _open_walk(window, application):
    window._pending_exercise = next(
        e for e in window.catalog.exercises if e.id == "easy-walk"
    )
    window._present_exercise()
    application.processEvents()
    return window._exercise_dialog


def test_completed_movement_is_recorded(application, tmp_path: Path) -> None:
    window = _make_window(tmp_path)
    dialog = _open_walk(window, application)
    dialog._complete()
    application.processEvents()

    (event,) = _today_breaks(window)
    assert event.kind == "movement"
    assert event.channel is BreakChannel.MOVEMENT
    assert event.exercise_id == "easy-walk"
    assert event.duration_seconds == dialog.completed_seconds > 0
    assert event.completed_at.tzinfo is not None
    _teardown_window(window, application)


def test_completed_rest_break_is_recorded(
    application, tmp_path: Path
) -> None:
    window = _make_window(tmp_path)
    window._present_manual_break(ManualBreakChoice.COFFEE)
    dialog = window._rest_break_dialog
    dialog._complete()
    application.processEvents()

    (event,) = _today_breaks(window)
    assert event.kind == "rest"
    assert event.channel is dialog.prompt.channel
    assert event.exercise_id is None
    _teardown_window(window, application)


@pytest.mark.parametrize("leave", ["_skip", "_postpone"])
def test_skipped_or_postponed_movement_is_not_recorded(
    application, tmp_path: Path, leave: str
) -> None:
    window = _make_window(tmp_path)
    dialog = _open_walk(window, application)
    getattr(dialog, leave)()
    application.processEvents()
    assert _today_breaks(window) == []
    _teardown_window(window, application)


def test_dismissed_or_swapped_rest_break_is_not_recorded(
    application, tmp_path: Path
) -> None:
    window = _make_window(tmp_path)
    window._present_manual_break(ManualBreakChoice.COFFEE)
    window._rest_break_dialog._choose_alternative(
        ManualBreakChoice.STAND.value
    )
    application.processEvents()
    window._rest_break_dialog._skip()
    application.processEvents()
    assert _today_breaks(window) == []
    _teardown_window(window, application)


def test_panels_get_breaks_today_including_this_one(
    application, tmp_path: Path
) -> None:
    window = _make_window(tmp_path)
    now = datetime.now().astimezone()
    window.history_store.record_break(
        BreakEvent(
            kind="rest",
            channel=BreakChannel.EYE,
            completed_at=now,
            local_date=now.date(),
            duration_seconds=20,
        )
    )
    window._present_manual_break(ManualBreakChoice.COFFEE)
    assert "2 breaks today" in window._rest_break_dialog.completion_note.text()
    window._rest_break_dialog._skip()
    application.processEvents()

    window.history_recorder.enabled = False
    dialog = _open_walk(window, application)
    assert dialog.completion_note.text() == "Nice work — break done."
    _teardown_window(window, application)


def test_rest_break_uses_break_mode_with_an_honest_close(
    application, tmp_path: Path
) -> None:
    window = _make_window(tmp_path)
    window._present_manual_break(ManualBreakChoice.STAND)
    application.processEvents()
    assert window.camera_workspace.isHidden()
    assert window.side_panel_close_button.text() == "Close"
    assert "Esc" in window.side_panel_close_button.toolTip()
    _teardown_window(window, application)


def test_card_shows_the_running_break_then_reverts(
    application, tmp_path: Path, clock: list[float]
) -> None:
    window = _make_window(tmp_path)
    window._present_manual_break(ManualBreakChoice.COFFEE)
    dialog = window._rest_break_dialog
    assert window.move_now_button.isHidden()
    dialog.start_button.click()
    clock[0] += 60
    window._update_break_countdown()

    assert window.next_break_label.text() == (
        f"On a break: {dialog.active_break_title}"
    )
    assert window.break_countdown.text() == "4:00"
    assert window.side_panel_close_button.isHidden()

    dialog._complete()
    application.processEvents()
    assert not window.next_break_label.text().startswith("On a break")
    assert not window.move_now_button.isHidden()
    assert not window.side_panel_close_button.isHidden()
    _teardown_window(window, application)


def test_escape_and_header_do_nothing_while_the_timer_runs(
    application, tmp_path: Path, clock: list[float]
) -> None:
    window = _make_window(tmp_path)
    dialog = _open_walk(window, application)
    assert window.side_panel_close_button.text() == "Later"
    dialog.start_button.click()

    window._dismiss_shortcut.activated.emit()
    window.side_panel_close_button.click()
    application.processEvents()

    assert window._exercise_dialog is dialog
    assert not window._exercise_postpone_timer.isActive()
    _teardown_window(window, application)


def test_countdown_name_does_not_tick(application, tmp_path: Path) -> None:
    window = _make_window(tmp_path)
    window._update_break_countdown()
    window._tracked_seconds_since_eye_break += 5
    window._update_break_countdown()
    assert window.break_countdown.accessibleName() == "Time until next break"
    _teardown_window(window, application)


def test_footer_disclaimer_hides_beside_a_side_panel(
    application, tmp_path: Path
) -> None:
    window = _make_window(tmp_path)
    assert not window.footer_disclaimer.wordWrap()
    window._add_setup()
    application.processEvents()
    assert window.footer_disclaimer.isHidden()
    window._dismiss_side_panel()
    application.processEvents()
    assert not window.footer_disclaimer.isHidden()
    _teardown_window(window, application)


def test_summary_gets_has_any_history(application, tmp_path: Path) -> None:
    window = _make_window(tmp_path)
    window._show_workday_summary()
    application.processEvents()
    assert (
        window._summary_dialog._has_any_history
        == window.history_store.has_any_history
    )
    _teardown_window(window, application)


def test_first_run_focus_lands_on_add_camera_setup(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window.show()
    application.processEvents()

    assert window.focusWidget() is window.first_run_add_button
    _teardown_window(window, application)
