from __future__ import annotations

from datetime import date, datetime

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QSystemTrayIcon,
)

from vulture.autostart import AutostartError, AutostartSnapshot
from vulture.breaks import BreakChannel
from vulture.history import HistoryStorageError
from vulture.i18n import tr
from vulture.models import BreakPreferences, TrackerState
from vulture.storage import StorageError
from vulture.tracking import PostureEvaluator

from .common import (
    STATE_COLORS,
    STATE_FOREGROUND_COLORS,
    create_state_icon,
)
from .exercises import EvidenceDialog
from .notices import NoticeDialog
from .settings import SettingsDialog
from .summary_dialog import WorkdaySummaryDialog


class ApplicationFlowMixin:
    @staticmethod
    def _changed_break_channels(
        previous: BreakPreferences,
        current: BreakPreferences,
    ) -> tuple[BreakChannel, ...]:
        all_channels = tuple(BreakChannel)
        if (
            previous.enabled != current.enabled
            or previous.away_reset_minutes != current.away_reset_minutes
        ):
            return all_channels

        changed: list[BreakChannel] = []
        channel_fields = {
            BreakChannel.MOVEMENT: (
                "movement_reminders_enabled",
                "movement_interval_minutes",
                "suggest_position_change",
                "suggest_standing",
                "suggest_walking",
                "legacy_walk_includes_drinks",
                "suggest_guided_exercise",
            ),
            BreakChannel.EYE: (
                "eye_reminders_enabled",
                "eye_interval_minutes",
                "suggest_nature_view",
                "suggest_blinking",
                "suggest_closed_eye_rest",
            ),
            BreakChannel.HYDRATION: (
                "hydration_reminders_enabled",
                "hydration_interval_minutes",
            ),
            BreakChannel.RESET: (
                "reset_reminders_enabled",
                "reset_interval_minutes",
                "suggest_tea_or_coffee",
                "suggest_reset_walking",
                "suggest_breathing_reset",
                "suggest_offscreen_reset",
                "suggest_reset_guided_exercise",
            ),
        }
        for channel, fields in channel_fields.items():
            if any(
                getattr(previous, field) != getattr(current, field)
                for field in fields
            ):
                changed.append(channel)
        return tuple(changed)

    def _show_workday_summary(self) -> None:
        if self._language_reload_preparing:
            return
        if self.history_store is None:
            self._show_notice(
                tr("Workday history unavailable"),
                self._history_error
                or tr("The local history database is unavailable."),
                critical=True,
            )
            return
        if self._summary_dialog is not None:
            self._focus_side_panel(self._summary_dialog)
            return

        setup_names = {setup.id: setup.name for setup in self.data.setups}
        dialog = WorkdaySummaryDialog(
            self._history_summary_for_date,
            self._delete_history_day,
            self._delete_all_history,
            setup_names,
            self.data.history_preferences.enabled,
        )
        dialog.finished.connect(self._summary_dialog_finished)
        self._summary_dialog = dialog
        self._show_side_panel(dialog)

    def _summary_dialog_finished(self, _result: int) -> None:
        dialog = self._summary_dialog
        self._summary_dialog = None
        if dialog is not None:
            self._hide_side_panel(dialog)

    def _delete_history_day(self, selected_date: date) -> None:
        if self._language_reload_preparing:
            return
        if self.history_store is None:
            raise HistoryStorageError(
                tr("Workday history is unavailable.")
            )
        try:
            if selected_date == datetime.now().astimezone().date():
                self._suspend_history()
            self.history_store.delete_day(selected_date)
            self.data.reminder_history = [
                event
                for event in self.data.reminder_history
                if event.occurred_at.astimezone().date() != selected_date
            ]
            self._save_data()
        except HistoryStorageError as error:
            self._disable_history_for_session(error)
            raise

    def _delete_all_history(self) -> None:
        if self._language_reload_preparing:
            return
        if self.history_store is None:
            raise HistoryStorageError(
                tr("Workday history is unavailable.")
            )
        try:
            self._suspend_history()
            self.history_store.delete_all()
            self.data.reminder_history = []
            self._save_data()
        except HistoryStorageError as error:
            self._disable_history_for_session(error)
            raise

    def _close_history(self) -> bool:
        if self.history_store is None:
            return True
        self.history_timer.stop()
        if self._summary_dialog is not None:
            self._summary_dialog.close()
        try:
            if self.history_recorder is not None:
                self.history_recorder.close()
            else:
                self.history_store.close()
        except HistoryStorageError as error:
            self._show_notice(
                tr("Could not close workday history"),
                str(error),
                critical=True,
            )
            return False
        self.history_recorder = None
        self.history_store = None
        return True

    def _show_settings(self) -> None:
        if self._language_reload_preparing:
            return
        if self._settings_dialog is not None:
            self._focus_side_panel(self._settings_dialog)
            return
        startup_enabled = False
        startup_setting_available = self.autostart_manager.is_supported
        startup_setting_error: str | None = None
        if startup_setting_available:
            try:
                startup_snapshot = self.autostart_manager.snapshot()
                startup_enabled = startup_snapshot.enabled
            except AutostartError as error:
                startup_setting_available = False
                startup_setting_error = tr(
                    "Vulture could not read the system startup setting: "
                    "{error}",
                    error=error,
                )
        dialog = SettingsDialog(
            self.data.alert_policy,
            self.data.exercise_preferences,
            self.data.history_preferences,
            self.data.interface_language,
            break_preferences=self.data.break_preferences,
            start_at_login_enabled=startup_enabled,
            startup_setting_available=startup_setting_available,
            startup_setting_error=startup_setting_error,
        )
        dialog.finished.connect(
            lambda result, active_dialog=dialog: (
                self._finish_settings_dialog(active_dialog, result)
            )
        )
        self._settings_dialog = dialog
        self._show_side_panel(dialog)

    def _finish_settings_dialog(
        self,
        dialog: SettingsDialog,
        result: int,
    ) -> None:
        if dialog is not self._settings_dialog:
            return
        self._settings_dialog = None
        if result != QDialog.DialogCode.Accepted:
            self._hide_side_panel(dialog)
            return
        previous_values = (
            self.data.alert_policy,
            self.data.exercise_preferences,
            self.data.history_preferences,
            self.data.interface_language,
            self.data.break_preferences,
        )
        (
            new_policy,
            new_exercise_preferences,
            new_history_preferences,
            new_language,
            requested_startup_enabled,
            new_break_preferences,
        ) = dialog.values()
        changed_break_channels = self._changed_break_channels(
            previous_values[4],
            new_break_preferences,
        )
        exercise_preferences_changed = (
            new_exercise_preferences != previous_values[1]
        )
        self._hide_side_panel(dialog)
        startup_snapshot: AutostartSnapshot | None = None
        startup_enabled = False
        if requested_startup_enabled is not None:
            try:
                startup_snapshot = self.autostart_manager.snapshot()
                startup_enabled = startup_snapshot.enabled
            except AutostartError as error:
                self._show_notice(
                    tr("Startup setting unavailable"),
                    tr(
                        "Vulture could not read the system startup setting: "
                        "{error}",
                        error=error,
                    ),
                )
                return
        startup_changed = (
            requested_startup_enabled is not None
            and (
                requested_startup_enabled != startup_enabled
                or (
                    not requested_startup_enabled
                    and startup_snapshot is not None
                    and startup_snapshot.exists
                )
            )
        )
        if startup_changed and requested_startup_enabled is not None:
            try:
                self.autostart_manager.set_enabled(
                    requested_startup_enabled
                )
            except AutostartError as error:
                self._show_notice(
                    tr("Could not update startup setting"),
                    tr(
                        "Vulture could not update whether it starts when you "
                        "sign in: {error}",
                        error=error,
                    ),
                )
                return
        (
            self.data.alert_policy,
            self.data.exercise_preferences,
            self.data.history_preferences,
            self.data.interface_language,
            self.data.break_preferences,
        ) = (
            new_policy,
            new_exercise_preferences,
            new_history_preferences,
            new_language,
            new_break_preferences,
        )
        if not self._save_data():
            (
                self.data.alert_policy,
                self.data.exercise_preferences,
                self.data.history_preferences,
                self.data.interface_language,
                self.data.break_preferences,
            ) = previous_values
            if startup_changed and startup_snapshot is not None:
                try:
                    self.autostart_manager.restore(startup_snapshot)
                except AutostartError as error:
                    self._show_notice(
                        tr("Could not restore startup setting"),
                        tr(
                            "The other settings were not saved, and Vulture "
                            "could not restore the previous system startup "
                            "setting: {error}",
                            error=error,
                        ),
                        critical=True,
                    )
            return
        if exercise_preferences_changed:
            self._clear_pending_exercise()
        if changed_break_channels:
            self._reset_break_channels(changed_break_channels)
        if self._summary_dialog is not None:
            self._summary_dialog.close()
        if self.history_recorder is not None:
            try:
                self.history_recorder.set_enabled(
                    self.data.history_preferences.enabled
                )
                if self.history_store is not None:
                    self.history_store.prune(
                        self.data.history_preferences.retention_days
                    )
            except HistoryStorageError as error:
                self._disable_history_for_session(error)
        setup = self.data.active_setup()
        if setup is not None and setup.calibration is not None:
            if (
                self.evaluator is not None
                and self.evaluator.profile == setup.calibration
            ):
                self.evaluator.policy = self.data.alert_policy
            else:
                self.evaluator = PostureEvaluator(
                    setup.calibration,
                    self.data.alert_policy,
                )
        if self.data.interface_language != previous_values[3]:
            self.language_change_requested.emit(
                self.data.interface_language.value
            )

    def _show_evidence(self) -> None:
        if self._language_reload_preparing:
            return
        if self._evidence_dialog is not None:
            self._focus_side_panel(self._evidence_dialog)
            return
        dialog = EvidenceDialog(self.catalog)
        dialog.finished.connect(self._evidence_dialog_finished)
        self._evidence_dialog = dialog
        self._show_side_panel(dialog)

    def _evidence_dialog_finished(self, _result: int) -> None:
        dialog = self._evidence_dialog
        self._evidence_dialog = None
        if dialog is not None:
            self._hide_side_panel(dialog)

    def _show_notice(
        self,
        title: str,
        message: str,
        *,
        critical: bool = False,
    ) -> None:
        if self._language_reload_preparing:
            return
        if self._notice_dialog is not None:
            self._notice_dialog.reject()
        if self._side_panel is not None:
            self._pending_notice = (title, message, critical)
            return
        dialog = NoticeDialog(
            title,
            message,
            critical=critical,
        )
        dialog.finished.connect(self._notice_dialog_finished)
        self._notice_dialog = dialog
        self._show_side_panel(dialog)

    def _notice_dialog_finished(self, _result: int) -> None:
        dialog = self._notice_dialog
        self._notice_dialog = None
        if dialog is not None:
            self._hide_side_panel(dialog)

    def _set_state(self, state: TrackerState, message: str) -> None:
        self._state = state
        color = STATE_COLORS[state]
        foreground = STATE_FOREGROUND_COLORS[state]
        self.status_dot.setStyleSheet(
            f"background: {color}; color: {foreground}; border-radius: 23px; "
            "font-weight: bold; font-size: 22px"
        )
        self.status_label.setText(message)
        self._apply_icon()
        self.tray.setToolTip(
            tr("Vulture — {message}", message=message)
        )

    def _apply_icon(self) -> None:
        icon = create_state_icon(
            self._state, badge=self._pending_exercise is not None
        )
        self.setWindowIcon(icon)
        self.tray.setIcon(icon)

    def _show_tray_message(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon,
        timeout_milliseconds: int,
    ) -> None:
        if self._language_reload_preparing:
            return
        self.tray.showMessage(
            title,
            message,
            icon,
            timeout_milliseconds,
        )

    def _save_data(self) -> bool:
        if self._language_reload_preparing:
            return False
        try:
            self.store.save(self.data)
            return True
        except StorageError as error:
            self._show_notice(
                tr("Could not save settings"),
                str(error),
                critical=True,
            )
            return False

    def _tray_activated(
        self, reason: QSystemTrayIcon.ActivationReason
    ) -> None:
        if self._language_reload_preparing:
            return
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            if (
                self._exercise_dialog is not None
                or self._pending_exercise is not None
            ):
                self._open_pending_exercise()
                return
            self._show_window()

    def _tray_message_clicked(self) -> None:
        if self._language_reload_preparing:
            return
        self._show_window()

    def _show_window(self) -> None:
        if self._language_reload_preparing:
            return
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        if (
            not self._quitting
            and QSystemTrayIcon.isSystemTrayAvailable()
        ):
            self._cancel_active_calibration()
            event.ignore()
            self.hide()
            if not self._close_notice_shown:
                self._show_tray_message(
                    tr("Vulture is still running"),
                    tr("Tracking continues locally in the system tray."),
                    QSystemTrayIcon.MessageIcon.Information,
                    5000,
                )
                self._close_notice_shown = True
            return
        self._cancel_active_calibration()
        if not self._stop_camera(10_000):
            event.ignore()
            self._quitting = False
            self._show_notice(
                tr("Camera still busy"),
                tr(
                    "The camera driver did not release safely. Disconnect the "
                    "camera or wait a moment, then quit again."
                ),
                critical=True,
            )
            return
        self._dismiss_side_panel()
        self._clear_pending_exercise()
        if not self._close_history():
            event.ignore()
            self._quitting = False
            return
        self._quitting = True
        QApplication.instance().quit()
        event.accept()

    def quit_application(self) -> None:
        self._quitting = True
        self._cancel_active_calibration()
        if not self._stop_camera(10_000):
            self._quitting = False
            self._show_notice(
                tr("Camera still busy"),
                tr(
                    "The camera driver did not release safely. Disconnect the "
                    "camera or wait a moment, then quit again."
                ),
                critical=True,
            )
            return
        self._dismiss_side_panel()
        self._clear_pending_exercise()
        if not self._close_history():
            self._quitting = False
            return
        self.tray.hide()
        QApplication.instance().quit()
