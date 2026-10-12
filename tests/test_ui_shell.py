from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from tests.test_ui import (
    _install_test_setup,
    _make_window,
    _teardown_window,
    make_profile,
)
from vulture.ui.calibration import (
    CalibrationStepSelectionDialog,
    SetupDialog,
)


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_break_mode_collapses_workspace_without_resizing(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window.resize(900, 700)
    window.show()
    application.processEvents()
    size = window.size()

    window._offer_exercise()
    application.processEvents()

    assert window._exercise_dialog is not None
    assert window.camera_workspace.isHidden()
    assert window.side_panel_close_button.text() == "Later"
    assert window.size() == size

    window._exercise_dialog.reject()
    application.processEvents()

    assert not window.camera_workspace.isHidden()
    assert window.size() == size

    window._show_notice("Saved data unavailable", "Disk is read-only.")
    application.processEvents()
    assert window.side_panel_close_button.text() == "Close"
    assert not window.camera_workspace.isHidden()

    _teardown_window(window, application)


def test_background_break_does_not_take_focus(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    activations: list[bool] = []
    window.activateWindow = lambda: activations.append(True)

    window._offer_exercise()
    application.processEvents()
    assert window._exercise_dialog is not None
    assert activations == []

    window._exercise_dialog.reject()
    application.processEvents()
    window._open_pending_exercise()
    application.processEvents()
    assert activations == [True]

    _teardown_window(window, application)


def test_first_run_hides_camera_actions_until_a_setup_exists(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    camera_actions = (
        window.add_setup_command,
        window.pause_command,
        window.calibrate_command,
        window.recalibrate_step_command,
    )

    assert not any(action.isVisible() for action in camera_actions)
    assert window.settings_command.isVisible()

    _install_test_setup(window, calibration=None)

    assert all(action.isVisible() for action in camera_actions)
    assert not window.recalibrate_step_command.isEnabled()
    assert window.recalibrate_step_command.toolTip()

    _teardown_window(window, application)


def test_setup_and_calibration_open_in_the_side_panel(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)

    window._add_setup()
    application.processEvents()
    assert isinstance(window._side_panel, SetupDialog)
    assert not window._side_panel.isWindow()
    window._setup_dialog.reject()
    application.processEvents()
    assert window._side_panel is None

    _install_test_setup(window, calibration=make_profile())
    window._camera_is_healthy = lambda: True
    window._activate_setup = lambda: None
    window._recalibrate_step()
    application.processEvents()

    selection = window._calibration_window
    assert isinstance(selection, CalibrationStepSelectionDialog)
    assert window._side_panel is selection
    assert not selection.isWindow()
    assert not window.preview_stack.isHidden()

    selection.reject()
    application.processEvents()
    assert window._side_panel is None
    assert not window._calibration_flow_active

    _teardown_window(window, application)


def test_full_safety_text_is_shown_on_the_first_movement_only(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    assert not window.data.full_safety_shown

    window._offer_exercise()
    application.processEvents()

    assert window._exercise_dialog.show_full_safety
    assert window.data.full_safety_shown

    _teardown_window(window, application)
