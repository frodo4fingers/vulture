from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from tests.test_calibration import make_frame
from vulture.ui.calibration import CalibrationDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _frame(quality: float):
    return make_frame(0).model_copy(
        update={"overall_quality": quality, "category_quality": {}}
    )


def test_no_frame_yet_keeps_initial_texts(application: QApplication) -> None:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    heading = dialog.phase_label.text()
    line = dialog.quality_label.text()
    for _ in range(3):
        dialog._tick()
    assert dialog.phase_label.text() == heading == "Starting the camera…"
    assert dialog.quality_label.text() == line == ""
    dialog.close()


def test_first_frames_drive_the_heading(application: QApplication) -> None:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    dialog.ingest(_frame(0.9))
    dialog._tick()
    assert dialog.phase_label.text() == "Ready when you are"
    dialog.ingest(_frame(0.5))
    dialog._tick()
    assert dialog.phase_label.text() == "Get into view"
    dialog.close()
