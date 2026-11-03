from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

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


def test_shortcut_hint_single_shortcut_unchanged(
    application: QApplication,
) -> None:
    sequence = QKeySequence("Ctrl+S")
    assert shortcut_hint("Save", sequence) == f"Save ({_native(sequence)})"
    assert shortcut_hint("Save", "Ctrl+S") == f"Save ({_native(sequence)})"


def test_shortcut_hint_joins_list_with_middle_dot(
    application: QApplication,
) -> None:
    comma = QKeySequence("Ctrl+,")
    mnemonic = QKeySequence("Alt+S")
    assert shortcut_hint("Settings", [comma, mnemonic]) == (
        f"Settings ({_native(comma)} · {_native(mnemonic)})"
    )
    assert shortcut_hint("Settings", (comma, "Alt+S")) == (
        f"Settings ({_native(comma)} · {_native(mnemonic)})"
    )


def test_shortcut_hint_empty_list_gives_text(
    application: QApplication,
) -> None:
    assert shortcut_hint("Settings", []) == "Settings"
    assert shortcut_hint("Settings", ()) == "Settings"
    assert shortcut_hint("Settings", [QKeySequence()]) == "Settings"


def test_shortcut_hint_drops_duplicates_and_keeps_order(
    application: QApplication,
) -> None:
    save = QKeySequence("Ctrl+S")
    open_key = QKeySequence("Ctrl+O")
    assert shortcut_hint("File", [save, open_key, save]) == (
        f"File ({_native(save)} · {_native(open_key)})"
    )


def test_settings_tooltip_lists_every_shortcut(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    _install_test_setup(window, calibration=make_profile())
    window.resize(1280, 760)
    window.show()
    application.processEvents()

    action = window.settings_command
    tooltip = action.toolTip()
    preferences = QKeySequence.keyBindings(
        QKeySequence.StandardKey.Preferences
    ) or [QKeySequence("Ctrl+,")]
    mnemonic = QKeySequence.mnemonic(action.text())
    assert not mnemonic.isEmpty()
    for sequence in [*preferences, mnemonic]:
        assert _native(sequence) in tooltip
    expected = shortcut_hint(action.iconText(), action.shortcuts())
    assert tooltip == expected

    _teardown_window(window, application)
