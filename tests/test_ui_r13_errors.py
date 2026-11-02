from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

import vulture.camera as camera_module
from vulture.camera import CameraDescriptor, CameraThread, _OpenCVCameraWorker
from vulture.models import TrackerState
from vulture.ui import NoticeDialog

from tests.test_ui import (  # noqa: F401
    _FakeAutostartManager,
    _close_test_window,
    _install_test_setup,
    _make_window,
    _open_settings_window,
    _teardown_window,
    application,
)
from vulture.exercises import load_exercise_catalog
from vulture.history import PostureHistoryStore
from vulture.models import AppData
from vulture.storage import AppDataStore
from vulture.ui import MainWindow


def test_camera_not_opened_reports_calm_message_with_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = CameraThread(
        CameraDescriptor(
            stable_id="/dev/video-test",
            display_name="Test camera",
            locator="/dev/video-test",
        )
    )
    emitted = []
    thread.camera_error.connect(lambda *args: emitted.append(args))

    class ClosedCapture:
        def isOpened(self) -> bool:
            return False

        def release(self) -> None:
            pass

    class Detector:
        def close(self) -> None:
            pass

    monkeypatch.setattr(camera_module, "MediaPipeDetector", Detector)
    monkeypatch.setattr(
        camera_module.cv2, "VideoCapture", lambda *_args: ClosedCapture()
    )

    assert not _OpenCVCameraWorker(thread).start()

    assert len(emitted) == 1
    message, details, access_help = emitted[0]
    assert message == "Could not use Test camera."
    assert details == "The camera could not be opened."
    assert access_help


def test_startup_read_failure_notice_is_calm_with_details(
    application: QApplication,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manager = _FakeAutostartManager()
    window = MainWindow(
        AppDataStore(tmp_path / "settings.json"),
        AppData(),
        load_exercise_catalog(),
        PostureHistoryStore(tmp_path / "history.sqlite3"),
        autostart_manager=manager,
    )
    dialog = _open_settings_window(window, application)
    dialog.start_at_login.setChecked(True)
    manager.fail_read = True
    notices = []
    monkeypatch.setattr(
        window,
        "_show_notice",
        lambda *args, **kwargs: notices.append((args, kwargs)),
    )

    dialog._validate_and_accept()
    application.processEvents()

    assert notices == [
        (
            (
                "Startup setting unavailable",
                "Vulture could not read the system startup setting.",
            ),
            {"details": "permission denied"},
        )
    ]
    _close_test_window(window, application)


def test_camera_error_during_calibration_shows_notice_with_details(
    application: QApplication,  # noqa: F811
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    _install_test_setup(window, calibration=None)
    window._camera_is_healthy = lambda: True
    window._activate_setup = lambda: None
    window._calibrate()
    application.processEvents()
    assert window._calibration_window is not None
    current_camera = object()
    window.camera_thread = current_camera
    window.sender = lambda: current_camera

    window._on_camera_error("calm", "raw cv2 text")
    application.processEvents()

    assert window._state is TrackerState.CAMERA_UNAVAILABLE
    assert window._calibration_window is None
    notice = window._notice_dialog
    assert isinstance(notice, NoticeDialog)
    assert notice.details_label.text() == "raw cv2 text"
    window.camera_thread = None
    _teardown_window(window, application)
