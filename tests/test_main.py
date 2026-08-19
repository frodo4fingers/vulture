from __future__ import annotations

import sys

import vulture.__main__ as application
from vulture.__main__ import CameraPermissionLauncher, _should_start_minimized
from vulture.autostart import START_MINIMIZED_FLAG

from PySide6.QtCore import QObject


def test_camera_permission_callback_is_qobject_bound() -> None:
    called = []
    launcher = CameraPermissionLauncher(lambda: called.append(True))

    assert isinstance(launcher, QObject)
    assert launcher.permission_decided.__self__ is launcher

    launcher.permission_decided()

    assert called == [True]


def test_should_start_minimized_detects_autostart_flag() -> None:
    assert _should_start_minimized([START_MINIMIZED_FLAG])
    assert _should_start_minimized(["--other", START_MINIMIZED_FLAG])
    assert not _should_start_minimized([])
    assert not _should_start_minimized(["--check-runtime"])
    assert not _should_start_minimized(["--check-runtime-assets-only"])


def test_main_routes_asset_only_runtime_check(monkeypatch) -> None:
    checks = []
    monkeypatch.setattr(
        application,
        "check_runtime",
        lambda *, check_vision_inference=True: checks.append(
            check_vision_inference
        )
        or 0,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["vulture", "--check-runtime-assets-only"],
    )

    assert application.main() == 0
    assert checks == [False]
