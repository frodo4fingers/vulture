from __future__ import annotations

from collections import defaultdict
import re

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QAbstractButton, QApplication, QLabel
import pytest

from tests.test_ui import (  # noqa: F401
    _install_test_setup,
    _make_window,
    _teardown_window,
    application,
    make_profile,
)
from vulture.breaks import ManualBreakChoice
from vulture.i18n import set_language, tr
from vulture.models import InterfaceLanguage

_MNEMONIC = re.compile(r"(?<!&)&(\w)")


@pytest.fixture(autouse=True)
def english() -> None:
    set_language(InterfaceLanguage.ENGLISH)
    yield
    set_language(InterfaceLanguage.ENGLISH)


def _alt_keys(window) -> dict[str, list[str]]:
    """Every Alt letter a user can press now, with the texts that claim it."""
    keys: dict[str, list[str]] = defaultdict(list)
    for widget in window.findChildren(QAbstractButton):
        if widget.isVisibleTo(window) and (m := _MNEMONIC.search(widget.text())):
            keys[m.group(1).lower()].append(widget.text())
    for label in window.findChildren(QLabel):
        if (
            label.isVisibleTo(window)
            and label.buddy() is not None
            and (m := _MNEMONIC.search(label.text()))
        ):
            keys[m.group(1).lower()].append(label.text())
    for action in window.findChildren(QAction):
        mnemonic = QKeySequence.mnemonic(action.text())
        if (
            not mnemonic.isEmpty()
            and mnemonic in action.shortcuts()
            and action.isVisible()
            and action.isEnabled()
        ):
            keys[mnemonic.toString()[-1].lower()].append(
                f"toolbar {action.text()}"
            )
    return keys


@pytest.mark.parametrize("language", list(InterfaceLanguage))
@pytest.mark.parametrize("state", ["first run", "rest eyes", "move"])
def test_main_window_alt_keys_are_unique(
    application: QApplication,
    tmp_path,
    language: InterfaceLanguage,
    state: str,
) -> None:
    set_language(language)
    window = _make_window(tmp_path)
    if state != "first run":
        _install_test_setup(window, calibration=make_profile())
        window.move_now_button.setText(
            tr("&Rest eyes now") if state == "rest eyes" else tr("&Move now")
        )
    window.resize(1280, 760)
    window.show()
    application.processEvents()
    if state != "first run":
        window.move_now_button.setText(
            tr("&Rest eyes now") if state == "rest eyes" else tr("&Move now")
        )

    clashes = {k: v for k, v in _alt_keys(window).items() if len(v) > 1}
    _teardown_window(window, application)

    assert not clashes, f"{language.value}/{state}: {clashes}"


def _open_break(window, kind: str):
    if kind == "rest break":
        window._present_manual_break(ManualBreakChoice.EYE_REST)
        return window._rest_break_dialog
    window._pending_exercise = next(
        e for e in window.catalog.exercises if e.id == "shoulder-roll"
    )
    window._present_exercise()
    return window._exercise_dialog


@pytest.mark.parametrize("language", list(InterfaceLanguage))
@pytest.mark.parametrize("calibrated", [True, False])
@pytest.mark.parametrize("running", [False, True])
@pytest.mark.parametrize("kind", ["rest break", "exercise"])
def test_break_panel_alt_keys_do_not_clash_with_main_window(
    application: QApplication,
    tmp_path,
    language: InterfaceLanguage,
    calibrated: bool,
    running: bool,
    kind: str,
) -> None:
    set_language(language)
    window = _make_window(tmp_path)
    if calibrated:
        _install_test_setup(window, calibration=make_profile())
    window.resize(1280, 760)
    window.show()
    application.processEvents()
    panel = _open_break(window, kind)
    assert panel is not None
    if running:
        panel.start_button.click()
    application.processEvents()

    clashes = {k: v for k, v in _alt_keys(window).items() if len(v) > 1}
    _teardown_window(window, application)

    assert not clashes, f"{language.value}/{kind}/{running}: {clashes}"
