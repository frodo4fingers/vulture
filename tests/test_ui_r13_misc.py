from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from vulture.exercises import load_exercise_catalog
from vulture.ui.calibration import CalibrationDialog
from vulture.ui.common import format_duration
from vulture.ui.exercises import EvidenceDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_format_duration_drops_zero_seconds() -> None:
    assert format_duration(2520) == "42m"
    assert format_duration(2525) == "42m 05s"


def test_evidence_dialog_has_close_button(application: QApplication) -> None:
    dialog = EvidenceDialog(load_exercise_catalog())
    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    assert buttons.standardButtons() & QDialogButtonBox.StandardButton.Close
    dialog.close()


def test_calibration_recording_hidden_when_idle(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog()
    assert dialog._phase == "idle"
    assert dialog.progress.isHidden()
    assert dialog.progress_label.isHidden()
    dialog.timer.stop()
    dialog.close()


def test_calibration_idle_quality_hint(application: QApplication) -> None:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    dialog._latest_quality = 0.5
    dialog._tick()
    assert "Move so your face" in dialog.quality_label.text()
    dialog._latest_quality = 0.9
    dialog._tick()
    assert "Move so your face" not in dialog.quality_label.text()
    dialog.close()
