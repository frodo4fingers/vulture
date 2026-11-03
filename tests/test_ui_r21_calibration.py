from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from tests.test_ui import make_profile
from vulture.exercises import load_exercise_catalog
from vulture.models import CameraDescriptor
from vulture.ui import calibration as calibration_module
from vulture.ui.calibration import (
    CalibrationDialog,
    CalibrationStepSelectionDialog,
    SetupDialog,
)
from vulture.ui.exercises import EvidenceDialog

LONG_NAME = "Integrated Webcam With A Remarkably Long Product Name 4K Pro"


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _setup_dialog(monkeypatch: pytest.MonkeyPatch) -> SetupDialog:
    cameras = [
        CameraDescriptor(
            stable_id=path, display_name=name, locator=path
        )
        for name, path in (
            (LONG_NAME, "/dev/video0"),
            ("Cam", "/dev/video2"),
        )
    ]
    monkeypatch.setattr(
        calibration_module, "discover_cameras", lambda: cameras
    )
    return SetupDialog()


def _heading(quality: float) -> CalibrationDialog:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    dialog._latest_quality = quality
    dialog._tick()
    return dialog


def test_save_button_has_no_theme_mnemonic(
    application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    dialog = _setup_dialog(monkeypatch)
    save = dialog.findChild(calibration_module.QDialogButtonBox).button(
        calibration_module.QDialogButtonBox.StandardButton.Save
    )
    assert save.text() == "Save"
    dialog.close()


def test_idle_heading_follows_camera_quality(
    application: QApplication,
) -> None:
    dialog = _heading(0.5)
    assert dialog.phase_label.text() == "Get into view"
    dialog._latest_quality = 0.9
    dialog._tick()
    assert dialog.phase_label.text() == "Ready when you are"
    dialog.close()


def test_retry_heading_stays_until_recording_starts(
    application: QApplication,
) -> None:
    dialog = _heading(0.9)
    dialog._retry_step("x")
    dialog._tick()
    assert dialog.phase_label.text() == "Let's try that again"
    dialog._start_sample()
    assert dialog.phase_label.text() != "Let's try that again"
    dialog.close()


def test_idle_heading_has_hysteresis(application: QApplication) -> None:
    dialog = _heading(0.9)
    assert dialog._view_clear
    dialog._latest_quality = 0.65
    dialog._tick()
    assert dialog._view_clear
    assert dialog.phase_label.text() == "Ready when you are"
    dialog._latest_quality = 0.55
    dialog._tick()
    assert not dialog._view_clear
    assert dialog.phase_label.text() == "Get into view"
    dialog._latest_quality = 0.65
    dialog._tick()
    assert not dialog._view_clear
    assert dialog.phase_label.text() == "Get into view"
    dialog.close()


def test_unclear_idle_line_is_only_the_tip(
    application: QApplication,
) -> None:
    dialog = _heading(0.5)
    assert dialog.quality_label.text() == (
        "Move so your face and shoulders are in view, with light in "
        "front of you."
    )
    dialog.close()


def _camera(name: str) -> CameraDescriptor:
    return CameraDescriptor(
        stable_id="a", display_name=name, locator="/dev/video0"
    )


def test_friendly_name_drops_truncated_duplicate() -> None:
    friendly = calibration_module._friendly_camera_name
    assert (
        friendly(_camera("Integrated Camera: Integrated C (/dev/video0)"))
        == "Integrated Camera"
    )
    assert friendly(_camera("Cam: Cam (/dev/video0)")) == "Cam"


def test_friendly_name_keeps_distinct_parts() -> None:
    friendly = calibration_module._friendly_camera_name
    assert (
        friendly(_camera("Logitech: HD Pro Webcam (/dev/video0)"))
        == "Logitech: HD Pro Webcam"
    )
    assert friendly(_camera("Cam (/dev/video0)")) == "Cam"
    assert friendly(_camera("Cam")) == "Cam"


def test_standard_buttons_use_translated_text(
    application: QApplication,
) -> None:
    selection = CalibrationStepSelectionDialog(make_profile())
    evidence = EvidenceDialog(load_exercise_catalog())
    # The step dialog hands out its own unique Alt keys.
    assert selection._cancel_button.text().replace("&", "") == "Cancel"
    close = evidence.findChild(QDialogButtonBox).buttons()[0]
    assert close.text() == "Close"
    selection.close()
    evidence.close()
