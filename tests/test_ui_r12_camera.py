from __future__ import annotations

from pathlib import Path

import pytest

from vulture.camera import CameraDescriptor, CameraThread
from vulture.models import TrackerState

from PySide6.QtWidgets import QApplication

from tests.test_ui import _make_window, _teardown_window, application  # noqa: F401


def test_report_error_emits_message_and_details() -> None:
    thread = CameraThread(
        CameraDescriptor(
            stable_id="/dev/video-test",
            display_name="Test camera",
            locator="/dev/video-test",
        )
    )
    emitted = []
    thread.camera_error.connect(lambda *args: emitted.append(args))

    thread._report_error("calm", "raw cv2 text")

    assert emitted == [("calm", "raw cv2 text", "")]
    assert thread.failure_message == "calm"


def test_camera_error_notice_carries_raw_text_as_details(
    application: QApplication,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _make_window(tmp_path)
    notices = []
    monkeypatch.setattr(
        window,
        "_show_notice",
        lambda *args, **kwargs: notices.append((args, kwargs)),
    )
    monkeypatch.setattr(window, "isVisible", lambda: True)
    current_camera = object()
    window.camera_thread = current_camera
    window.sender = lambda: current_camera

    window._on_camera_error("calm", "raw cv2 text")

    assert window._state is TrackerState.CAMERA_UNAVAILABLE
    assert "raw cv2 text" not in window.status_label.text()
    assert notices == [
        (
            ("Camera unavailable", "calm"),
            {"critical": True, "details": "raw cv2 text"},
        )
    ]

    window.camera_thread = None
    _teardown_window(window, application)
