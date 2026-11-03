from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QMessageBox

import vulture.__main__ as application_main
from tests.test_ui import (  # noqa: F401
    _install_test_setup,
    _make_window,
    _teardown_window,
    application,
    make_profile,
)
from vulture.ui.common import shortcut_hint


def _native(sequence: QKeySequence) -> str:
    return sequence.toString(QKeySequence.SequenceFormat.NativeText)


def test_evidence_tooltip_lists_every_shortcut(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    _install_test_setup(window, calibration=make_profile())
    window.resize(1280, 760)
    window.show()
    application.processEvents()

    action = window.evidence_action
    tooltip = window.evidence_button.toolTip()
    assert tooltip == shortcut_hint(action.text(), action.shortcuts())
    for sequence in action.shortcuts():
        assert _native(sequence) in tooltip

    _teardown_window(window, application)


def test_startup_failure_ok_button_reads_ok(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shown: list[QMessageBox] = []
    monkeypatch.setattr(
        QMessageBox, "exec", lambda self: shown.append(self) or 0
    )

    application_main._show_failure(
        None,
        "Vulture could not start",
        "Vulture could not load its saved data or resources.",
        "disk full",
    )

    assert len(shown) == 1
    ok_button = shown[0].button(QMessageBox.StandardButton.Ok)
    assert ok_button.text() == "OK"
