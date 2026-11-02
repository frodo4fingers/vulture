from __future__ import annotations

from pathlib import Path

import pytest

from vulture.camera import CameraDescriptor, CameraThread
from vulture.models import TrackerState

from PySide6.QtWidgets import QApplication

from tests.test_ui import _make_window, _teardown_window, application  # noqa: F401


def test_report_error_emits_message_details_and_help() -> None:
    thread = CameraThread(
        CameraDescriptor(
            stable_id="/dev/video-test",
            display_name="Test camera",
            locator="/dev/video-test",
        )
    )
    emitted = []
    thread.camera_error.connect(lambda *args: emitted.append(args))

    thread._report_error("calm", "raw", "Check permissions.")

    assert emitted == [("calm", "raw", "Check permissions.")]


def test_camera_help_stays_out_of_status_line_but_joins_notice(
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

    window._on_camera_error(
        "Could not start Cam.", "raw", "Check permissions."
    )

    assert window._state is TrackerState.CAMERA_UNAVAILABLE
    assert "Check permissions." not in window.status_label.text()
    assert notices == [
        (
            ("Camera unavailable", "Could not start Cam. Check permissions."),
            {"critical": True, "details": "raw"},
        )
    ]

    window.camera_thread = None
    _teardown_window(window, application)


def test_hidden_window_keeps_camera_help_in_status_line(
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
    monkeypatch.setattr(window, "isVisible", lambda: False)
    current_camera = object()
    window.camera_thread = current_camera
    window.sender = lambda: current_camera

    window._on_camera_error(
        "Could not start Cam.", "raw", "Check permissions."
    )

    assert notices == []
    assert "Check permissions." in window.status_label.text()

    window.camera_thread = None
    _teardown_window(window, application)
