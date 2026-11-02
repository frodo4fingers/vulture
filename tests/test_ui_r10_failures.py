from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

import vulture.__main__ as application_main
from tests.test_ui import _make_window, _teardown_window
from vulture.history import HistoryStorageError


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_history_disabled_tray_message_hides_raw_error(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    messages: list[tuple[str, str, QSystemTrayIcon.MessageIcon, int]] = []
    window._show_tray_message = (
        lambda title, message, icon, timeout: messages.append(
            (title, message, icon, timeout)
        )
    )

    window._disable_history_for_session(HistoryStorageError("disk full"))

    assert len(messages) == 1
    title, message, icon, timeout = messages[0]
    assert title == "Workday history paused"
    assert message == (
        "History is paused for this session. Posture feedback still works."
    )
    assert "disk full" not in message
    assert icon == QSystemTrayIcon.MessageIcon.Information
    assert timeout == 10_000
    assert window._history_error == "disk full"
    _teardown_window(window, application)


def test_show_failure_shows_calm_text_with_details(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shown: list[QMessageBox] = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self) or 0)

    application_main._show_failure(
        None,
        "Vulture could not start",
        "Vulture could not load its saved data or resources.",
        "disk full",
    )

    assert len(shown) == 1
    box = shown[0]
    assert box.windowTitle() == "Vulture could not start"
    assert box.text() == "Vulture could not load its saved data or resources."
    assert box.detailedText() == "disk full"
    assert box.icon() == QMessageBox.Icon.Critical
