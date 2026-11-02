from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from tests.test_ui import _make_window, _teardown_window
from vulture.models import PostureCategory, TrackerState


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_posture_drift_tray_message_is_an_information_nudge(
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
    assessment = SimpleNamespace(
        state=TrackerState.ALERT,
        message="Move toward baseline.",
        bad_duration_seconds=0,
        newly_alerted=True,
        category=PostureCategory.SLOUCH,
        assessed_at=datetime.now(timezone.utc),
    )

    window._apply_assessment(assessment)

    assert messages == [
        (
            "Posture nudge",
            "Move toward baseline. Change position when comfortable.",
            QSystemTrayIcon.MessageIcon.Information,
            8000,
        )
    ]
    _teardown_window(window, application)
