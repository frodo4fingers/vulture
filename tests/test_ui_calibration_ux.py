from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from tests.test_ui import make_profile
from vulture.models import CameraDescriptor
from vulture.ui import calibration as calibration_module
from vulture.ui.calibration import (
    CALIBRATION_STEPS,
    CalibrationDialog,
    CalibrationStepSelectionDialog,
    SetupDialog,
)


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _close(dialog: CalibrationDialog, application: QApplication) -> None:
    dialog.timer.stop()
    dialog.close()
    application.processEvents()


def test_stepper_is_focusable_and_describes_every_stage(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog()
    stepper = dialog.stepper

    assert stepper.focusPolicy() is Qt.FocusPolicy.TabFocus
    assert stepper.accessibleName() == "Calibration progress"
    description = stepper.accessibleDescription()
    assert description.startswith("Step 1 of 5.")
    assert "Step 1: Comfortable baseline, current" in description
    assert "Step 2: Head-forward example, not started" in description
    assert len(stepper._pills) == len(CALIBRATION_STEPS)

    dialog._stage_status[0] = "recorded"
    dialog._step_index = 1
    dialog._show_step()
    assert "Step 1: Comfortable baseline, recorded" in (
        stepper.accessibleDescription()
    )
    _close(dialog, application)


def test_actions_sit_outside_the_scroll_area(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog()
    for height in (720, 640):
        dialog.resize(480, height)
        dialog.show()
        application.processEvents()
        for button in (
            dialog.start_button,
            dialog.skip_button,
            dialog.cancel_button,
        ):
            assert not dialog.scroll_area.isAncestorOf(button)
            assert dialog.rect().contains(button.geometry())
    _close(dialog, application)


def test_labels_are_calm_sentence_case(application: QApplication) -> None:
    dialog = CalibrationDialog()
    assert dialog.role_label.text() == "Your comfortable baseline"
    dialog._step_index = 2
    dialog._show_step()
    assert dialog.role_label.text() == "Example: Rounded torso (optional)"
    assert dialog.phase_label.text() == "Ready when you are"
    dialog._finish_sample()
    assert dialog.phase_label.text() == "Let's try that again"
    assert dialog.feedback_label.isVisibleTo(dialog)
    _close(dialog, application)


def test_recording_state_is_announced_and_cued(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog()
    cues: list[str] = []
    dialog._play_cue = cues.append  # type: ignore[method-assign]

    dialog._start_sample()
    assert dialog.phase_label.text() == "Get ready…"
    dialog._deadline = 0.0
    dialog._tick()
    assert dialog.phase_label.text() == "Recording… stay in this position"
    assert dialog.phase_label.accessibleDescription() == (
        "Recording. Stay in this position."
    )
    dialog._finish_sample()
    assert cues == ["countdown", "start", "end"]
    _close(dialog, application)


def test_sound_cues_can_be_muted(application: QApplication) -> None:
    dialog = CalibrationDialog(sound_cues=False)
    dialog._play_cue("countdown")
    assert dialog._cue_effects == {}
    for filename in calibration_module.SOUND_CUE_FILES.values():
        assert calibration_module.resource_path("sounds", filename).is_file()
    _close(dialog, application)


def test_head_forward_photo_is_captioned_and_cropped(
    application: QApplication,
) -> None:
    dialog = CalibrationStepSelectionDialog(make_profile())
    dialog.step_combo.setCurrentIndex(1)

    assert dialog.reference.caption.text() == "Chin moves forward, not sideways."
    pixmap = dialog.reference_image._source_pixmap
    assert (pixmap.width(), pixmap.height()) == calibration_module.CROP_SIZE
    dialog.step_combo.setCurrentIndex(2)
    assert dialog.reference.caption.isHidden()
    dialog.close()
    application.processEvents()


def test_setup_dialog_hides_device_paths_but_keeps_them_for_duplicates(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def camera(name: str, path: str) -> CameraDescriptor:
        return CameraDescriptor(
            stable_id=path,
            display_name=f"{name} ({path})",
            locator=path,
        )

    monkeypatch.setattr(
        calibration_module,
        "discover_cameras",
        lambda: [
            camera("USB Cam", "/dev/v4l/by-path/a"),
            camera("USB Cam", "/dev/v4l/by-path/b"),
            camera("Laptop Camera", "/dev/v4l/by-path/c"),
        ],
    )
    dialog = SetupDialog()
    combo = dialog.camera_combo

    assert [combo.itemText(i) for i in range(3)] == [
        "USB Cam (1)",
        "USB Cam (2)",
        "Laptop Camera",
    ]
    assert combo.itemData(1, Qt.ItemDataRole.ToolTipRole) == (
        "/dev/v4l/by-path/b"
    )
    assert combo.itemData(2, Qt.ItemDataRole.ToolTipRole) is None
    dialog.close()
