from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from tests.test_ui import _make_window, _teardown_window
from vulture.history import DailyPostureSummary, HistoryStorageError
from vulture.ui.common import SemanticLabel
from vulture.ui.notices import NoticeDialog
from vulture.ui.summary_dialog import WorkdaySummaryDialog
from vulture.ui.theme import CaptionLabel


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_notice_details_are_a_selectable_caption(
    application: QApplication,
) -> None:
    dialog = NoticeDialog("Title", "Calm sentence.", details="disk full")

    captions = dialog.findChildren(CaptionLabel)
    assert [label.text() for label in captions] == ["disk full"]
    assert captions[0].wordWrap()
    assert (
        captions[0].textInteractionFlags()
        & Qt.TextInteractionFlag.TextSelectableByMouse
    )
    assert [
        label.text() for label in dialog.findChildren(SemanticLabel)
    ] == ["Calm sentence."]
    dialog.close()


def test_notice_without_details_has_no_caption(
    application: QApplication,
) -> None:
    dialog = NoticeDialog("Title", "Calm sentence.")

    assert dialog.findChildren(CaptionLabel) == []
    dialog.close()


def test_history_unavailable_notice_is_calm_with_details(
    application: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _make_window(tmp_path)
    shown: list[tuple[tuple[str, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        window,
        "_show_notice",
        lambda *args, **kwargs: shown.append((args, kwargs)),
    )
    window._history_error = "disk full"

    window._show_initial_history_error()

    assert len(shown) == 1
    args, kwargs = shown[0]
    assert args == (
        "Workday history unavailable",
        "Posture tracking continues without saving summaries.",
    )
    assert kwargs["details"] == "disk full"
    _teardown_window(window, application)


def test_pending_notice_keeps_details(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window._calibration_flow_active = True

    window._show_notice("Title", "Calm.", critical=True, details="raw")

    assert window._pending_notice == ("Title", "Calm.", True, "raw")
    window._calibration_flow_active = False
    _teardown_window(window, application)


def test_summary_delete_failure_is_calm_with_details(
    application: QApplication,
) -> None:
    today = datetime.now().astimezone().date()

    def fail_delete(_day: object) -> None:
        raise HistoryStorageError("disk full")

    dialog = WorkdaySummaryDialog(
        lambda _day: DailyPostureSummary(
            local_date=today,
            totals={},
            tracked_seconds=0,
            reminder_count=0,
            episodes=[],
            breaks=[],
        ),
        fail_delete,
        lambda: None,
        {},
        True,
    )

    dialog._delete_selected_day()
    assert dialog.delete_confirmation.toolTip() == ""
    dialog._confirm_history_delete()

    assert dialog.delete_confirmation.text() == (
        "History could not be deleted right now. Try again later."
    )
    assert dialog.delete_confirmation.toolTip() == ""
    assert dialog.delete_confirmation_details.text() == "disk full"

    dialog._delete_selected_day()
    assert dialog.delete_confirmation.toolTip() == ""
    assert dialog.delete_confirmation_details.text() == ""
    assert dialog.delete_confirmation_details.isHidden()
    dialog.close()
