from __future__ import annotations

from datetime import datetime, timezone

import pytest
from PySide6.QtWidgets import QApplication

from tests.test_calibration import make_frame
from tests.test_ui import _make_window, _teardown_window
from vulture.ui.calibration import CalibrationDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _frame(quality: float):
    return make_frame(0).model_copy(
        update={"overall_quality": quality, "category_quality": {}}
    )


def test_start_waits_for_first_frame_then_takes_focus(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    dialog.show()
    application.processEvents()
    dialog.activateWindow()
    assert not dialog.start_button.isEnabled()
    dialog.ingest(_frame(0.9))
    application.processEvents()
    assert dialog.start_button.isEnabled()
    assert dialog.focusWidget() is dialog.start_button
    dialog.close()


def test_later_step_keeps_start_enabled(application: QApplication) -> None:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    dialog.ingest(_frame(0.9))
    dialog._step_index = 1
    dialog._show_step()
    assert dialog.start_button.isEnabled()
    dialog.close()


def test_camera_without_a_person_says_get_into_view(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    dialog.note_tracking_lost()
    dialog._tick()
    assert dialog.start_button.isEnabled()
    assert dialog.phase_label.text() == "Get into view"
    dialog.ingest(_frame(0.9))
    dialog._tick()
    assert dialog.phase_label.text() == "Ready when you are"
    # Leaving the view again is noticed, not masked by the last frame.
    dialog.note_tracking_lost()
    dialog._tick()
    assert dialog.phase_label.text() == "Get into view"
    dialog.close()


def test_main_window_forwards_tracking_loss_to_calibration(
    application: QApplication, tmp_path
) -> None:
    window = _make_window(tmp_path)
    dialog = CalibrationDialog()
    dialog.timer.stop()
    window._calibration_dialog = dialog
    window._on_tracking_lost(datetime.now(timezone.utc))
    assert dialog.start_button.isEnabled()
    window._calibration_dialog = None
    dialog.close()
    _teardown_window(window, application)


@pytest.mark.parametrize("held", ["cancel", "skip"])
def test_next_step_hands_focus_back_to_start(
    application: QApplication, held: str
) -> None:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    dialog.show()
    application.processEvents()
    dialog.activateWindow()
    dialog.ingest(_frame(0.9))
    dialog._step_index = 1  # an optional step, so Skip is enabled
    dialog._show_step()
    button = dialog.cancel_button if held == "cancel" else dialog.skip_button
    button.setFocus()
    application.processEvents()
    dialog._show_step()
    application.processEvents()
    expected = dialog.start_button if held == "cancel" else dialog.skip_button
    assert dialog.focusWidget() is expected
    dialog.close()
