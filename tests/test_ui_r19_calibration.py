from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from tests.test_calibration import make_frame
from vulture.calibration import CalibrationError, CalibrationFitter
from vulture.models import PostureCategory
from vulture.ui import POSTURE_STEPS
from vulture.ui.calibration import CalibrationDialog, CalibrationStep

MOVED = (
    "The camera or your seat moved while recording the baseline. Keep "
    "the setup still and record it again."
)
STEP_KEYS = (
    "Calibration step",
    "Recalibrate posture step",
    "Re&do a calibration step",
    "Redo a calibration step",
    "Redo this step",
    "Step {number}: {title}, {state}",
)


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _moved_frames() -> list:
    # Half the frames sit left, half right: the median lands between
    # them and neither group is compatible with it.
    frames = []
    for index in range(50):
        frame = make_frame(index)
        center_x = 0.2 if index % 2 else 0.8
        geometry = frame.geometry.model_copy(
            update={"subject_center_x": center_x}
        )
        frames.append(frame.model_copy(update={"geometry": geometry}))
    return frames


def _idle_text(quality: float) -> str:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    dialog._latest_quality = quality
    dialog._tick()
    text = dialog.quality_label.text()
    dialog.close()
    return text


def test_idle_text_when_clear(application: QApplication) -> None:
    text = _idle_text(0.9)
    assert text == "The camera sees you clearly."
    assert "%" not in text


def test_idle_text_when_unclear(application: QApplication) -> None:
    text = _idle_text(0.5)
    assert text.startswith("The camera can't see you clearly yet.\n")
    assert "Move so your face and shoulders are in view" in text
    assert "%" not in text


def test_german_steps_say_schritt() -> None:
    path = (
        Path(__file__).parents[1]
        / "src/vulture/resources/i18n/de.json"
    )
    de = json.loads(path.read_text(encoding="utf-8"))
    for key in STEP_KEYS:
        assert "Stufe" not in de[key]
        assert "schritt" in de[key].lower()


def test_check_baseline_passes_steady_frames() -> None:
    frames = [make_frame(index) for index in range(40)]
    assert len(CalibrationFitter().check_baseline(frames)) == 40


def test_check_baseline_rejects_moved_geometry() -> None:
    with pytest.raises(CalibrationError) as caught:
        CalibrationFitter().check_baseline(_moved_frames())
    assert str(caught.value) == MOVED


def test_fit_rejects_moved_geometry() -> None:
    with pytest.raises(CalibrationError) as caught:
        CalibrationFitter().fit(_moved_frames())
    assert str(caught.value) == MOVED


def test_baseline_check_failure_retries_step_one(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def moved(self, good_frames, profile=None):
        raise CalibrationError(MOVED)

    monkeypatch.setattr(CalibrationFitter, "check_baseline", moved)
    dialog = CalibrationDialog()
    dialog.timer.stop()
    assert dialog.steps[0].category is None
    dialog._current_samples = [make_frame(index) for index in range(30)]
    dialog._finish_sample()
    assert dialog.start_button.text().replace("&", "") == "Record again"
    assert dialog.feedback_label.text() == MOVED
    assert dialog._step_index == 0
    assert dialog._stage_status[0] == "retry"
    dialog.close()


PROFILE_MOVED = (
    "The camera seems to have moved since this setup was calibrated. "
    "Put it back where it was, or run a full calibration."
)


def _profile():
    return CalibrationFitter().fit(
        [make_frame(index) for index in range(40)]
    )


def _shifted_frames() -> list:
    # Steady among themselves, but away from the saved camera position.
    frames = []
    for index in range(40):
        frame = make_frame(index)
        geometry = frame.geometry.model_copy(
            update={"subject_center_x": 0.9}
        )
        frames.append(frame.model_copy(update={"geometry": geometry}))
    return frames


def test_check_baseline_with_profile_passes_same_position() -> None:
    frames = [make_frame(index) for index in range(40)]
    result = CalibrationFitter().check_baseline(frames, _profile())
    assert len(result) == 40


def test_check_baseline_with_profile_rejects_moved_camera() -> None:
    frames = _shifted_frames()
    # Steady frames pass without a profile, so only the profile objects.
    assert len(CalibrationFitter().check_baseline(frames)) == 40
    with pytest.raises(CalibrationError) as caught:
        CalibrationFitter().check_baseline(frames, _profile())
    assert str(caught.value) == PROFILE_MOVED


def test_check_baseline_with_profile_rejects_few_clear_frames() -> None:
    frames = [make_frame(index) for index in range(10)]
    with pytest.raises(CalibrationError) as caught:
        CalibrationFitter().check_baseline(frames, _profile())
    assert str(caught.value).startswith("Need at least 30 clear")


def test_check_baseline_rejects_too_few_features() -> None:
    frames = []
    for index in range(40):
        frame = make_frame(index)
        values = dict(list(frame.values.items())[:3])
        frames.append(frame.model_copy(update={"values": values}))
    with pytest.raises(CalibrationError) as caught:
        CalibrationFitter().check_baseline(frames)
    assert str(caught.value) == (
        "Too few stable head-and-shoulder features were visible."
    )


def _incremental_dialog(profile) -> CalibrationDialog:
    baseline = CalibrationStep(
        key="good",
        title="Confirm saved good baseline",
        instructions="Sit in the saved baseline.",
        required=True,
        capture_seconds=10,
    )
    unwanted = POSTURE_STEPS[PostureCategory.SLOUCH].model_copy(
        update={"required": True}
    )
    return CalibrationDialog(
        steps=[baseline, unwanted], base_profile=profile
    )


def test_incremental_dialog_retries_step_one_when_camera_moved(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = []

    def moved(self, good_frames, profile=None):
        seen.append(profile)
        raise CalibrationError(PROFILE_MOVED)

    profile = _profile()
    monkeypatch.setattr(CalibrationFitter, "check_baseline", moved)
    dialog = _incremental_dialog(profile)
    dialog.timer.stop()
    dialog._current_samples = [make_frame(index) for index in range(30)]
    dialog._finish_sample()
    assert seen == [profile]
    assert dialog._step_index == 0
    assert dialog._stage_status[0] == "retry"
    assert dialog.feedback_label.text() == PROFILE_MOVED
    dialog.close()
