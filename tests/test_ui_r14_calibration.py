from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from vulture.ui.calibration import CalibrationDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_recording_stays_hidden_during_countdown(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    dialog._start_sample()
    assert dialog._phase == "preparing"
    assert dialog.progress.isHidden()
    dialog.close()


def test_recording_shows_when_capture_starts(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    dialog._start_sample()
    dialog._deadline = 0.0
    dialog._tick()
    assert dialog._phase == "capturing"
    assert not dialog.progress.isHidden()
    dialog.close()


def test_capture_start_replaces_the_countdown_line(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog()
    dialog._start_sample()
    dialog._deadline = 0.0
    dialog._tick()
    assert dialog._phase == "capturing"
    assert "starts in" not in dialog.quality_label.text()
    dialog.close()
