from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from tests.test_ui_r4 import _rest
from vulture.exercises import load_exercise_catalog
from vulture.i18n import set_language
from vulture.models import InterfaceLanguage


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def english() -> None:
    set_language(InterfaceLanguage.ENGLISH)
    yield
    set_language(InterfaceLanguage.ENGLISH)


@pytest.mark.parametrize(
    ("language", "stop"),
    [
        (InterfaceLanguage.ENGLISH, "Stop if"),
        (InterfaceLanguage.GERMAN, "Hören Sie auf"),
        (InterfaceLanguage.SPANISH, "Deténgase"),
    ],
)
def test_walk_safety_says_stop_not_skip(
    language: InterfaceLanguage, stop: str
) -> None:
    # While the timer runs Stop early is the only exit, so the advice
    # must name that action rather than Skip.
    catalog = load_exercise_catalog(language=language)
    walk = next(e for e in catalog.exercises if e.id == "easy-walk")
    assert walk.safety.startswith(stop)


def test_stop_early_tooltip_admits_short_breaks_do_not_count(
    application: QApplication,
) -> None:
    dialog = _rest()
    assert dialog.stop_button.toolTip() == (
        "Ends the break now. A very short break is not counted."
    )
    dialog.close()
