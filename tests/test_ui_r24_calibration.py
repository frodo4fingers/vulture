from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from tests.test_calibration import make_frame
from vulture.camera import CAMERA_SILENT_AFTER_SECONDS
from vulture.ui import calibration
from vulture.ui.calibration import CalibrationDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _frame(quality: float):
    return make_frame(0).model_copy(
        update={"overall_quality": quality, "category_quality": {}}
    )


def _recorded(dialog: CalibrationDialog) -> list[str]:
    calls: list[str] = []
    dialog._announce = calls.append  # type: ignore[method-assign]
    return calls


def test_silent_camera_gets_a_hint_once(
    application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    calls = _recorded(dialog)
    now = dialog._last_output_at
    clock = {"t": now + CAMERA_SILENT_AFTER_SECONDS - 0.5}
    monkeypatch.setattr(calibration.time, "monotonic", lambda: clock["t"])
    dialog._tick()
    assert dialog.phase_label.text() == "Starting the camera…"
    assert calls == []
    clock["t"] = now + CAMERA_SILENT_AFTER_SECONDS
    for _ in range(3):
        dialog._tick()
    assert dialog.phase_label.text() == "No camera image yet"
    assert "camera is connected" in dialog.quality_label.text()
    assert len(calls) == 1
    assert calls[0].startswith("No camera image yet. Check that")
    dialog.ingest(_frame(0.9))
    dialog._tick()
    assert dialog.phase_label.text() == "Ready when you are"
    assert dialog.quality_label.text() == "The camera sees you clearly."
    dialog.close()


def test_camera_that_stalls_later_gets_the_hint(
    application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    calls = _recorded(dialog)
    clock = {"t": 100.0}
    monkeypatch.setattr(calibration.time, "monotonic", lambda: clock["t"])
    dialog.ingest(_frame(0.9))
    dialog._tick()
    assert dialog.phase_label.text() == "Ready when you are"
    clock["t"] += CAMERA_SILENT_AFTER_SECONDS
    dialog._tick()
    assert dialog.phase_label.text() == "No camera image yet"
    assert calls == ["No camera image yet. " + dialog.quality_label.text()]
    dialog.ingest(_frame(0.9))
    dialog._tick()
    assert dialog.phase_label.text() == "Ready when you are"
    dialog.close()


def _waiting_dialog(application: QApplication) -> CalibrationDialog:
    dialog = CalibrationDialog()
    dialog.timer.stop()
    dialog.show()
    application.processEvents()
    dialog.activateWindow()
    assert not dialog.start_button.isEnabled()
    return dialog


def test_first_output_keeps_focus_on_the_instructions_and_announces(
    application: QApplication,
) -> None:
    dialog = _waiting_dialog(application)
    dialog.scroll_area.setFocus()
    calls = _recorded(dialog)
    dialog.ingest(_frame(0.9))
    assert dialog.focusWidget() is dialog.scroll_area
    assert calls == ["You can start recording now."]
    dialog.close()


def test_first_output_moves_focus_from_cancel_silently(
    application: QApplication,
) -> None:
    dialog = _waiting_dialog(application)
    dialog.cancel_button.setFocus()
    calls = _recorded(dialog)
    dialog.ingest(_frame(0.9))
    assert dialog.focusWidget() is dialog.start_button
    assert calls == []
    dialog.close()
