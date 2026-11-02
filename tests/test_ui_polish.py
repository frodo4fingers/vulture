from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialog,
    QPushButton,
    QWidget,
)

from tests.test_ui import _make_window, _teardown_window, make_profile
from vulture.breaks import ManualBreakChoice, manual_break_prompt
from vulture.models import BreakPreferences
from vulture.exercises import load_exercise_catalog
from vulture.ui.break_options import RestBreakDialog, assign_mnemonics
from vulture.ui.calibration import (
    CalibrationDialog,
    CalibrationStepSelectionDialog,
    SetupDialog,
)
from vulture.ui.exercises import ExerciseDialog, MediaFrame


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _mnemonics(dialog: QDialog) -> list[str]:
    keys = []
    for button in dialog.findChildren(QAbstractButton):
        text = button.text()
        if "&" in text and not button.isHidden():
            keys.append(text[text.index("&") + 1].lower())
    return keys


def test_assign_mnemonics_never_repeats_a_letter(
    application: QApplication,
) -> None:
    buttons = [QPushButton(text) for text in ("Start", "Skip", "Swap…")]
    assign_mnemonics(*buttons)
    assert [b.text() for b in buttons] == ["&Start", "S&kip", "S&wap…"]


@pytest.mark.parametrize("size", [(1280, 760), (1024, 650)])
def test_every_break_fits_without_scrolling(
    application: QApplication, tmp_path: Path, size: tuple[int, int]
) -> None:
    window = _make_window(tmp_path)
    window.resize(*size)
    window.show()
    catalog = load_exercise_catalog()
    for exercise in catalog.exercises:
        window.data.full_safety_shown = False
        window._pending_exercise = exercise
        window._present_exercise()
        QTest.qWait(50)
        bar = window.side_panel_host.verticalScrollBar()
        assert bar.maximum() == 0, exercise.id
        window._dismiss_side_panel()
    _teardown_window(window, application)


def test_full_safety_folds_away_when_it_forces_a_scroll(
    application: QApplication,
) -> None:
    catalog = load_exercise_catalog()
    host = QWidget()
    host.resize(700, 300)
    host.show()
    dialog = ExerciseDialog(
        catalog.exercises[0], catalog, host, show_full_safety=True
    )
    dialog.setWindowFlags(Qt.WindowType.Widget)
    dialog.setParent(host)
    dialog.resize(700, 300)
    dialog.show()
    QTest.qWait(50)
    assert dialog.safety.text() == dialog._short_safety_text
    dialog.close()
    host.close()


def test_video_focus_ring_is_drawn(application: QApplication) -> None:
    catalog = load_exercise_catalog()
    dialog = ExerciseDialog(catalog.exercises[1], catalog)
    dialog.resize(700, 760)
    dialog.show()
    dialog.activateWindow()
    QTest.qWait(100)
    frame = dialog.findChild(MediaFrame)
    assert dialog.video is not None and frame is not None
    dialog.video.setFocus()
    QTest.qWait(100)
    top = frame.mapTo(dialog, frame.rect().center()).x()
    y = frame.mapTo(dialog, frame.rect().topLeft()).y() + 1
    pixel = dialog.grab().toImage().pixelColor(top, y)
    highlight = dialog.palette().color(QPalette.ColorRole.Highlight)
    assert pixel.name() == highlight.name()
    dialog.close()


def test_break_panels_have_unique_mnemonics_and_tab_order(
    application: QApplication,
) -> None:
    catalog = load_exercise_catalog()
    exercise = next(e for e in catalog.exercises if e.id == "easy-walk")
    exercise_dialog = ExerciseDialog(
        exercise,
        catalog,
        alternative_choices=(ManualBreakChoice.STAND,),
    )
    exercise_dialog.show()
    keys = _mnemonics(exercise_dialog)
    # Before Start only Start and "Not now" show; the menu actions carry
    # their own mnemonics (covered in test_ui_r2_break.py).
    assert len(keys) == len(set(keys)) >= 2

    rest = RestBreakDialog(
        manual_break_prompt(ManualBreakChoice.STAND, BreakPreferences()),
        (ManualBreakChoice.GUIDED_MOVEMENT,),
    )
    rest.show()
    keys = _mnemonics(rest)
    assert len(keys) == len(set(keys)) >= 2
    assert rest.start_button.nextInFocusChain() is not None
    exercise_dialog.close()
    rest.close()


def test_calibration_panels_have_unique_mnemonics(
    application: QApplication,
) -> None:
    calibration = CalibrationDialog()
    calibration.show()
    keys = _mnemonics(calibration)
    assert len(keys) == len(set(keys)) == 3
    assert calibration.start_button.text() == "&Start recording"
    calibration.close()

    selection = CalibrationStepSelectionDialog(make_profile())
    assert selection.windowTitle() == "Redo a calibration step"
    selection.close()


def test_setup_dialog_keeps_content_at_the_top(
    application: QApplication,
) -> None:
    dialog = SetupDialog()
    dialog.resize(500, 700)
    dialog.show()
    QTest.qWait(50)
    assert dialog.name_edit.y() < 200
    dialog.close()
