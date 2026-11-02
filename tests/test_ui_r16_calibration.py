from __future__ import annotations

import time

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from vulture.calibration import CalibrationError, CalibrationFitter
from vulture.ui.calibration import CalibrationDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _capturing_dialog() -> CalibrationDialog:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    dialog._start_sample()
    dialog._deadline = 0.0
    dialog._tick()
    assert dialog._phase == "capturing"
    return dialog


def test_capture_has_no_recording_caption(application: QApplication) -> None:
    dialog = _capturing_dialog()
    assert not [
        label
        for label in dialog.findChildren(QLabel)
        if label.text() == "Recording"
    ]
    assert not dialog.progress.isHidden()
    dialog.close()


def test_capture_shows_seconds_left_not_sample_count(
    application: QApplication,
) -> None:
    dialog = _capturing_dialog()
    text = dialog.quality_label.text()
    assert "s left." in text
    assert "samples" not in text
    dialog.close()


def test_move_tip_shows_only_after_samples_stall(
    application: QApplication,
) -> None:
    dialog = _capturing_dialog()
    dialog._last_sample_at = time.monotonic() - 2
    dialog._tick()
    assert "Make sure your face" in dialog.quality_label.text()
    dialog._last_sample_at = time.monotonic()
    dialog._tick()
    assert "Make sure your face" not in dialog.quality_label.text()
    dialog.close()


def test_incomplete_calibration_feedback(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise CalibrationError("not enough frames")

    monkeypatch.setattr(CalibrationFitter, "fit", fail)
    dialog = CalibrationDialog()
    dialog.timer.stop()
    dialog._fit_profile()
    assert (
        dialog.feedback_label.text()
        == "Calibration incomplete: not enough frames"
    )
    dialog.timer.stop()
    dialog.close()
