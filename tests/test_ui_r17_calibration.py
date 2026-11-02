from __future__ import annotations

import time

import pytest
from PySide6.QtWidgets import QApplication

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


def test_capture_heading_matches_every_step(
    application: QApplication,
) -> None:
    dialog = _capturing_dialog()
    assert dialog.phase_label.text() == "Recording… stay in this position"
    dialog.close()


def test_start_and_retry_button_words(application: QApplication) -> None:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    assert dialog.start_button.text().replace("&", "") == "Start recording"
    dialog._finish_sample()
    assert dialog.start_button.text().replace("&", "") == "Record again"
    dialog.close()


def test_retry_message_for_required_step(application: QApplication) -> None:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    assert dialog.steps[dialog._step_index].required
    dialog._finish_sample()
    assert dialog.feedback_label.text() == (
        "The camera could not see you clearly enough. Adjust the camera "
        "or your position, then record this step again."
    )
    dialog.close()


def test_capture_bar_shows_no_percent_text(application: QApplication) -> None:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    assert not dialog.progress.isTextVisible()
    dialog.close()


def test_tip_follows_stalled_samples(application: QApplication) -> None:
    dialog = _capturing_dialog()
    dialog._current_samples.append(object())
    dialog._last_sample_at = time.monotonic()
    dialog._tick()
    assert "Make sure your face" not in dialog.quality_label.text()
    dialog._last_sample_at = time.monotonic() - 2
    dialog._tick()
    assert "Make sure your face" in dialog.quality_label.text()
    dialog.close()
