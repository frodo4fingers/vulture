from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from vulture.history import DailyPostureSummary, HistoryStorageError
from vulture.i18n import set_language
from vulture.models import AppData, BreakPreferences, InterfaceLanguage
from vulture.ui.notices import NoticeDialog
from vulture.ui.settings import SettingsDialog
from vulture.ui.summary_dialog import WorkdaySummaryDialog

KEYBOARD = Qt.TextInteractionFlag.TextSelectableByKeyboard


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def english() -> None:
    set_language(InterfaceLanguage.ENGLISH)
    yield
    set_language(InterfaceLanguage.ENGLISH)


def _settings(**kwargs: object) -> SettingsDialog:
    data = AppData()
    return SettingsDialog(
        data.alert_policy,
        data.exercise_preferences,
        data.history_preferences,
        data.interface_language,
        break_preferences=BreakPreferences(),
        **kwargs,
    )


def test_posture_spin_boxes_share_one_width(application: QApplication) -> None:
    dialog = _settings()
    spins = [
        dialog.warning_seconds,
        dialog.alert_seconds,
        dialog.transition_buffer_seconds,
        dialog.repeat_count,
        dialog.repeat_window,
    ]
    assert len({spin.minimumWidth() for spin in spins}) == 1
    assert len({spin.maximumWidth() for spin in spins}) == 1
    assert spins[0].minimumWidth() == max(s.sizeHint().width() for s in spins)
    dialog.close()


def test_notice_details_are_keyboard_selectable(
    application: QApplication,
) -> None:
    dialog = NoticeDialog("Title", "Calm.", details="disk full")
    assert dialog.details_label.textInteractionFlags() & KEYBOARD
    assert dialog.details_label.focusPolicy() == Qt.FocusPolicy.StrongFocus
    dialog.close()


def test_startup_details_show_as_selectable_caption(
    application: QApplication,
) -> None:
    dialog = _settings(
        startup_setting_available=False,
        startup_setting_error="Vulture could not read the startup setting.",
        startup_setting_details="dbus down",
    )
    caption = dialog.startup_details_label
    assert caption.text() == "dbus down"
    assert caption.wordWrap()
    assert caption.textInteractionFlags() & KEYBOARD
    dialog.close()


def test_storage_error_details_are_shown_and_refresh_hides_them(
    application: QApplication,
) -> None:
    summary = DailyPostureSummary(
        local_date=date(2026, 7, 20),
        totals={},
        tracked_seconds=3600,
        reminder_count=0,
        episodes=[],
        breaks=[],
    )
    dialog = WorkdaySummaryDialog(
        lambda _day: summary, lambda _day: None, lambda: None, {}, True
    )
    dialog.show()
    caption = dialog.empty_state_details
    assert caption.isHidden()

    dialog._show_storage_error(HistoryStorageError("disk I/O error"))

    assert caption.text() == "disk I/O error"
    assert caption.isVisible()
    assert caption.textInteractionFlags() & KEYBOARD

    dialog.refresh()

    assert caption.text() == ""
    assert caption.isHidden()
    dialog.close()
