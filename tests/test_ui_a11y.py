from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QAccessible, QKeySequence
from PySide6.QtWidgets import QApplication, QLabel

from tests.test_ui import _make_window, _teardown_window
from vulture.breaks import BreakChannel
from vulture.models import (
    AlertPolicy,
    ExercisePreferences,
    HistoryPreferences,
    InterfaceLanguage,
    TrackerState,
)
from vulture.ui.settings import SettingsDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _shortcuts(window) -> dict[str, list[str]]:
    actions = {
        "settings": window.settings_command,
        "pause": window.pause_command,
        "summary": window.summary_action,
        "evidence": window.evidence_action,
    }
    return {
        name: [key.toString() for key in action.shortcuts()]
        for name, action in actions.items()
    }


def test_window_shortcuts_are_registered(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    keys = _shortcuts(window)

    assert "Ctrl+Shift+P" in keys["pause"]
    assert "Ctrl+Shift+S" in keys["summary"]
    assert keys["evidence"] and keys["settings"]
    window._set_command_state(window.pause_command, True, "")
    assert "Ctrl+Shift+P" in window.pause_command.toolTip()
    assert "Ctrl+Shift+S" in window.summary_button.toolTip()
    # Mnemonics live on the actions; the button text shows none of the markers.
    assert "&" not in window.settings_button.text()

    _teardown_window(window, application)


def test_escape_closes_the_side_panel_only_while_one_is_open(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    assert not window._dismiss_shortcut.isEnabled()

    window._show_notice("Saved data unavailable", "Disk is read-only.")
    application.processEvents()
    assert window._dismiss_shortcut.isEnabled()
    assert "Esc" in window.side_panel_close_button.toolTip()

    window._dismiss_shortcut.activated.emit()
    application.processEvents()
    assert window._side_panel is None
    assert not window._dismiss_shortcut.isEnabled()

    _teardown_window(window, application)


def test_escape_postpones_a_break_like_the_later_button(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window._offer_exercise()
    application.processEvents()
    assert window.side_panel_close_button.text() == "Later"

    window._dismiss_shortcut.activated.emit()
    application.processEvents()

    assert window._exercise_dialog is None
    assert window._pending_exercise is not None
    assert window._exercise_postpone_timer.isActive()

    _teardown_window(window, application)


def test_toolbar_buttons_are_keyboard_focusable(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    for button in (
        window.add_setup_button,
        window.pause_button,
        window.calibrate_button,
        window.settings_button,
    ):
        assert button.focusPolicy().name == "StrongFocus"

    _teardown_window(window, application)


def test_state_change_and_break_arrival_are_announced(
    application: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _make_window(tmp_path)
    messages: list[str] = []
    monkeypatch.setattr(
        QAccessible,
        "updateAccessibility",
        lambda event: messages.append(event.message()),
    )

    window._set_state(TrackerState.GOOD, "All clear.")
    window._set_state(TrackerState.GOOD, "Still clear.")
    window._set_state(TrackerState.LOW_CONFIDENCE, "Looking.")
    window._set_state(TrackerState.WARNING, "Drifting.")

    assert len(messages) == 2
    assert messages[0].endswith("All clear.")
    assert messages[1].endswith("Drifting.")

    messages.clear()
    window._offer_exercise()
    application.processEvents()
    assert any(window.side_panel_title.text() in text for text in messages)

    _teardown_window(window, application)


def test_countdown_due_is_announced_once(
    application: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _make_window(tmp_path)
    messages: list[str] = []
    monkeypatch.setattr(
        QAccessible,
        "updateAccessibility",
        lambda event: messages.append(event.message()),
    )
    window._next_break = lambda: (BreakChannel.EYE, 0.0)

    window._update_break_countdown()
    window._update_break_countdown()

    assert len(messages) == 1
    assert "0:00" in window.break_countdown.accessibleName()

    _teardown_window(window, application)


def test_tray_tooltip_names_the_state_in_words(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window._set_state(TrackerState.ALERT, "Shift your weight.")

    tooltip = window.tray.toolTip()
    assert window._state_title(TrackerState.ALERT) in tooltip
    assert "Shift your weight." in tooltip

    _teardown_window(window, application)


def test_settings_form_labels_are_bound_to_their_controls(
    application: QApplication,
) -> None:
    dialog = SettingsDialog(
        AlertPolicy(),
        ExercisePreferences(),
        HistoryPreferences(),
        InterfaceLanguage.ENGLISH,
    )
    buddies = {
        label.buddy() for label in dialog.findChildren(QLabel) if label.buddy()
    }
    for spin in (
        dialog.warning_seconds,
        dialog.movement_interval_minutes,
        dialog.eye_duration_seconds,
        dialog.history_retention_days,
        dialog.language_combo,
    ):
        assert spin in buddies
    assert dialog.warning_seconds.accessibleDescription()

    # Alt mnemonics within the Posture tab never repeat.
    mnemonics = [
        QKeySequence.mnemonic(label.text()).toString()
        for label in dialog.scroll_area.findChildren(QLabel)
        if label.buddy() is not None
    ]
    assert len(mnemonics) == len(set(mnemonics))

    dialog.deleteLater()
