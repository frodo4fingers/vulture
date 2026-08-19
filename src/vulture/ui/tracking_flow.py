from __future__ import annotations

import time
from datetime import date, datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QSystemTrayIcon

from vulture.breaks import (
    MANUAL_BREAK_CHOICES,
    BreakChannel,
    ManualBreakChoice,
    break_channel_name,
    break_channel_title,
    eye_break_activities,
    eye_break_message,
    hydration_break_activities,
    hydration_break_message,
    movement_break_activities,
    movement_break_message,
    manual_break_prompt,
    reset_break_activities,
    reset_break_message,
)
from vulture.history import DailyPostureSummary, HistoryStorageError
from vulture.i18n import tr
from vulture.models import (
    FeatureFrame,
    ReminderEvent,
    TrackerState,
)
from vulture.tracking import PostureAssessment, PostureEvaluator

from .exercises import (
    EXERCISE_POSTPONE_MINUTES,
    ExerciseDialog,
    ExerciseOutcome,
)
from .break_options import RestBreakDialog, RestBreakOutcome


class TrackingFlowMixin:
    _CAMERA_UNCERTAIN_AFTER_SECONDS = 3.0
    _CAMERA_UNAVAILABLE_AFTER_SECONDS = 10.0

    def _toggle_tracking(self) -> None:
        if self._language_reload_preparing:
            return
        if self._tracking_enabled:
            if not self._stop_camera():
                self._show_camera_release_error()
                return
            self._tracking_enabled = False
            if self.evaluator is not None:
                self.evaluator.reset()
            self._suspend_history()
            self._set_tracking_controls()
            self._show_camera_released_state()
            return

        self._tracking_enabled = True
        self._set_tracking_controls()
        self._activate_setup()

    def _set_tracking_controls(self) -> None:
        text = (
            tr("Release camera")
            if self._tracking_enabled
            else tr("Resume tracking")
        )
        self.pause_command.setText(text)
        self.pause_action.setText(text)
        self._refresh_setup_combo()

    def _show_camera_released_state(self) -> None:
        self._latest_image = None
        self.preview.clear()
        self.preview.setText(
            tr("Camera released — available to meeting apps")
        )
        self.preview.setAccessibleName(
            tr("Camera released — available to meeting apps")
        )
        self._set_state(
            TrackerState.STOPPED,
            tr(
                "Camera released. Other apps can use it. Resume tracking when "
                "your meeting ends."
            ),
        )

    def _on_preview(self, image: QImage) -> None:
        sender = self.sender()
        if sender is not None and sender is not self.camera_thread:
            return
        if (
            self._language_reload_preparing
            or not self._tracking_enabled
            or not self._camera_preview_visible()
        ):
            return
        self._latest_image = image
        self._draw_preview()

    def _draw_preview(self) -> None:
        if self._latest_image is None:
            return
        self.preview.setAccessibleName(tr("Camera preview"))
        pixmap = QPixmap.fromImage(self._latest_image)
        self.preview.setPixmap(
            pixmap.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:
        self._draw_preview()
        super().resizeEvent(event)

    def showEvent(self, event) -> None:
        self._sync_camera_preview_state()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._sync_camera_preview_state(force_hidden=True)
        super().hideEvent(event)

    def _camera_preview_visible(self) -> bool:
        return self.isVisible() and not self.isMinimized()

    def _sync_camera_preview_state(
        self,
        *,
        force_hidden: bool = False,
    ) -> None:
        if self.camera_thread is not None:
            self.camera_thread.set_preview_enabled(
                not force_hidden and self._camera_preview_visible()
            )

    def _reset_camera_liveness(self) -> None:
        self._camera_liveness_stage = 0

    def _check_camera_liveness(self) -> None:
        camera_thread = self.camera_thread
        if (
            self._language_reload_preparing
            or not self._tracking_enabled
            or camera_thread is None
        ):
            self._reset_camera_liveness()
            return
        if camera_thread.failure_message is not None:
            return
        if not camera_thread.isRunning():
            age = self._CAMERA_UNAVAILABLE_AFTER_SECONDS
        else:
            age = camera_thread.seconds_since_last_output()
            if age is None:
                return
        if age < self._CAMERA_UNCERTAIN_AFTER_SECONDS:
            self._reset_camera_liveness()
            return
        self._suspend_history()
        self._mark_tracking_interrupted()
        if self.evaluator is not None:
            self.evaluator.mark_tracking_uncertain(
                datetime.now().astimezone()
            )
        if (
            age >= self._CAMERA_UNAVAILABLE_AFTER_SECONDS
            and self._camera_liveness_stage < 2
        ):
            self._camera_liveness_stage = 2
            self._set_state(
                TrackerState.CAMERA_UNAVAILABLE,
                tr(
                    "Camera processing has stopped. Reconnect the camera or "
                    "release and resume tracking."
                ),
            )
        elif self._camera_liveness_stage < 1:
            self._camera_liveness_stage = 1
            self._set_state(
                TrackerState.LOW_CONFIDENCE,
                tr(
                    "Camera frames are delayed. Waiting for tracking to "
                    "resume."
                ),
            )

    def _on_feature(self, frame: FeatureFrame) -> None:
        sender = self.sender()
        if sender is not None and sender is not self.camera_thread:
            return
        if self._language_reload_preparing:
            return
        self._camera_liveness_stage = 0
        if self._calibration_dialog is not None:
            self._calibration_dialog.ingest(frame)
            return
        if self._calibration_flow_active:
            return
        if not self._tracking_enabled:
            self._suspend_history()
            return
        setup = self.data.active_setup()
        if setup is None or setup.calibration is None:
            self._suspend_history()
            self._set_state(
                TrackerState.UNCALIBRATED,
                tr("Calibrate this setup before tracking."),
            )
            return
        if self.evaluator is None:
            self.evaluator = PostureEvaluator(
                setup.calibration, self.data.alert_policy
            )
        assessment = self.evaluator.assess(frame)
        if assessment is None:
            return
        self._record_history_assessment(assessment, setup.id)
        if assessment.state in (
            TrackerState.GOOD,
            TrackerState.WARNING,
            TrackerState.ALERT,
        ):
            self._record_valid_tracking()
        else:
            self._mark_tracking_interrupted()
        self._apply_assessment(assessment)

    def _on_tracking_lost(self, captured_at: datetime) -> None:
        sender = self.sender()
        if sender is not None and sender is not self.camera_thread:
            return
        if (
            self._language_reload_preparing
            or self._calibration_flow_active
            or not self._tracking_enabled
        ):
            return
        self._camera_liveness_stage = 0
        if (
            self.evaluator is not None
            and not self.evaluator.mark_tracking_uncertain(captured_at)
        ):
            return
        self._suspend_history()
        self._mark_tracking_interrupted()
        self._set_state(
            TrackerState.LOW_CONFIDENCE,
            tr(
                "Tracking paused until your face and shoulders are visible."
            ),
        )

    def _on_camera_error(self, message: str) -> None:
        if self._language_reload_preparing:
            return
        if self.sender() is not self.camera_thread:
            return
        self._camera_liveness_stage = 2
        self._suspend_history()
        self._mark_tracking_interrupted()
        self._set_state(TrackerState.CAMERA_UNAVAILABLE, message)
        if self._calibration_window is not None:
            self._calibration_window.reject()
        elif self.isVisible():
            self._show_notice(tr("Camera unavailable"), message, critical=True)

    def _apply_assessment(self, assessment: PostureAssessment) -> None:
        message = assessment.message
        if assessment.bad_duration_seconds > 0:
            message = tr(
                "{message} Sustained for {seconds} seconds.",
                message=message,
                seconds=round(assessment.bad_duration_seconds),
            )
        self._set_state(assessment.state, message)
        if not assessment.newly_alerted or assessment.category is None:
            return
        due_channels = self._due_break_channels()
        if due_channels:
            if (
                not self._exercise_dialog_open
                and self._rest_break_dialog is None
            ):
                self._show_due_break_reminder(due_channels)
            return

        self._show_tray_message(
            tr("Vulture posture reminder"),
            tr(
                "{message} Change position when comfortable.",
                message=assessment.message,
            ),
            QSystemTrayIcon.MessageIcon.Warning,
            8000,
        )
        setup = self.data.active_setup()
        if setup is None:
            return
        event = ReminderEvent(
            occurred_at=assessment.assessed_at,
            setup_id=setup.id,
            category=assessment.category,
        )
        self._record_history_reminder(event)
        should_offer_exercise = self.escalator.register(self.data, event)
        self._save_data()
        if should_offer_exercise:
            QTimer.singleShot(0, self._offer_exercise)

    def _check_break_reminders(self) -> None:
        if (
            self._language_reload_preparing
            or self._exercise_dialog_open
            or self._rest_break_dialog is not None
        ):
            return
        preferences = self.data.break_preferences
        if not preferences.enabled:
            return
        due_channels = self._due_break_channels()
        if due_channels:
            self._show_due_break_reminder(due_channels)

    def _tick_break_clock(self) -> None:
        now = time.monotonic()
        elapsed = max(0.0, now - self._last_break_tick_at)
        self._last_break_tick_at = now
        preferences = self.data.break_preferences
        if preferences.enabled:
            if preferences.movement_reminders_enabled:
                self._tracked_seconds_since_break += elapsed
            if preferences.eye_reminders_enabled:
                self._tracked_seconds_since_eye_break += elapsed
            if preferences.hydration_reminders_enabled:
                self._tracked_seconds_since_hydration_break += elapsed
            if preferences.reset_reminders_enabled:
                self._tracked_seconds_since_reset_break += elapsed
        self._update_break_countdown()
        self._check_break_reminders()

    def _due_break_channels(self) -> tuple[BreakChannel, ...]:
        preferences = self.data.break_preferences
        if not preferences.enabled:
            return ()
        return tuple(
            channel
            for channel, enabled, elapsed, interval_minutes in (
                (
                    BreakChannel.MOVEMENT,
                    preferences.movement_reminders_enabled,
                    self._tracked_seconds_since_break,
                    preferences.movement_interval_minutes,
                ),
                (
                    BreakChannel.EYE,
                    preferences.eye_reminders_enabled,
                    self._tracked_seconds_since_eye_break,
                    preferences.eye_interval_minutes,
                ),
                (
                    BreakChannel.HYDRATION,
                    preferences.hydration_reminders_enabled,
                    self._tracked_seconds_since_hydration_break,
                    preferences.hydration_interval_minutes,
                ),
                (
                    BreakChannel.RESET,
                    preferences.reset_reminders_enabled,
                    self._tracked_seconds_since_reset_break,
                    preferences.reset_interval_minutes,
                ),
            )
            if enabled and elapsed >= interval_minutes * 60
        )

    def _next_break(self) -> tuple[BreakChannel, float] | None:
        preferences = self.data.break_preferences
        if not preferences.enabled:
            return None
        candidates = [
            (
                channel,
                max(0.0, interval_minutes * 60 - elapsed),
            )
            for channel, enabled, elapsed, interval_minutes in (
                (
                    BreakChannel.MOVEMENT,
                    preferences.movement_reminders_enabled,
                    self._tracked_seconds_since_break,
                    preferences.movement_interval_minutes,
                ),
                (
                    BreakChannel.EYE,
                    preferences.eye_reminders_enabled,
                    self._tracked_seconds_since_eye_break,
                    preferences.eye_interval_minutes,
                ),
                (
                    BreakChannel.HYDRATION,
                    preferences.hydration_reminders_enabled,
                    self._tracked_seconds_since_hydration_break,
                    preferences.hydration_interval_minutes,
                ),
                (
                    BreakChannel.RESET,
                    preferences.reset_reminders_enabled,
                    self._tracked_seconds_since_reset_break,
                    preferences.reset_interval_minutes,
                ),
            )
            if enabled
        ]
        return min(candidates, key=lambda item: item[1]) if candidates else None

    def _update_break_countdown(self) -> None:
        next_break = self._next_break()
        if next_break is None:
            self.next_break_label.setText(tr("Break reminders are off"))
            self.break_countdown.setText("--:--")
            self.break_countdown_caption.setText(
                tr("Enable them in Settings")
            )
            return
        channel, remaining_seconds = next_break
        self.next_break_label.setText(break_channel_name(channel))
        total_seconds = max(0, int(remaining_seconds + 0.999))
        hours, remainder = divmod(total_seconds, 3_600)
        minutes, seconds = divmod(remainder, 60)
        countdown = (
            f"{hours}:{minutes:02d}:{seconds:02d}"
            if hours
            else f"{minutes}:{seconds:02d}"
        )
        self.break_countdown.setText(countdown)
        self.break_countdown_caption.setText(
            tr("due now")
            if total_seconds == 0
            else tr("until next break")
        )

    def _check_sedentary_break(self) -> None:
        self._check_break_reminders()

    def _show_due_break_reminder(
        self,
        due_channels: tuple[BreakChannel, ...],
    ) -> None:
        preferences = self.data.break_preferences
        messages: list[tuple[BreakChannel, str, int]] = []
        exercise_channels: list[BreakChannel] = []
        for channel in due_channels:
            activity = self._choose_break_activity(channel)
            if activity.value == "guided_exercise":
                exercise_channels.append(channel)
                continue
            if channel is BreakChannel.MOVEMENT:
                message = movement_break_message(
                    activity,
                    preferences.movement_duration_minutes,
                )
                duration_seconds = (
                    preferences.movement_duration_minutes * 60
                )
            elif channel is BreakChannel.EYE:
                message = eye_break_message(
                    activity,
                    preferences.eye_duration_seconds,
                )
                duration_seconds = preferences.eye_duration_seconds
            elif channel is BreakChannel.HYDRATION:
                message = hydration_break_message(
                    preferences.hydration_duration_seconds
                )
                duration_seconds = (
                    preferences.hydration_duration_seconds
                )
            else:
                message = reset_break_message(
                    activity,
                    preferences.reset_duration_minutes,
                )
                duration_seconds = (
                    preferences.reset_duration_minutes * 60
                )
            messages.append((channel, message, duration_seconds))
            self._reset_break_channels((channel,))

        self._save_data()
        if messages:
            title = (
                break_channel_title(messages[0][0])
                if len(due_channels) == 1
                else tr("Time for a short break")
            )
            message = "\n".join(
                (
                    text
                    if len(messages) == 1
                    else f"{break_channel_title(channel)}: {text}"
                )
                for channel, text, _duration_seconds in messages
            )
            timeout_milliseconds = (
                max(
                    duration_seconds
                    for _channel, _text, duration_seconds in messages
                )
                * 1000
            )
            self._show_tray_message(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                timeout_milliseconds,
            )
        if exercise_channels:
            self._offer_exercise(
                reset_channels=tuple(exercise_channels)
            )
        self._update_break_countdown()

    def _choose_break_activity(self, channel: BreakChannel):
        preferences = self.data.break_preferences
        if channel is BreakChannel.MOVEMENT:
            activities = movement_break_activities(preferences)
        elif channel is BreakChannel.EYE:
            activities = eye_break_activities(preferences)
        elif channel is BreakChannel.HYDRATION:
            activities = hydration_break_activities(preferences)
        else:
            activities = reset_break_activities(preferences)
        selected, remaining = self.break_activity_selector.choose(
            activities,
            self.data.break_activity_bags.get(channel.value, []),
            self.data.last_break_activity_ids.get(channel.value),
        )
        self.data.break_activity_bags[channel.value] = remaining
        self.data.last_break_activity_ids[channel.value] = selected.value
        return selected

    def _offer_exercise(
        self,
        *,
        reset_channels: tuple[BreakChannel, ...] = (
            BreakChannel.MOVEMENT,
        ),
    ) -> None:
        if self._language_reload_preparing or self._exercise_dialog_open:
            return
        if self._pending_exercise is not None:
            self._pending_exercise_reset_channels = (
                self._merge_exercise_reset_channels(
                    self._pending_exercise_reset_channels,
                    reset_channels,
                )
            )
            self._reset_requested_break_tracking(reset_channels)
            self._present_exercise()
            return
        exercise, remaining = self.selector.choose_from_bag(
            self.data.exercise_preferences,
            self.data.exercise_shuffle_bag,
            self.data.last_exercise_id,
        )
        if exercise is None:
            self._clear_pending_exercise()
            self._show_tray_message(
                tr("Movement break"),
                tr(
                    "No exercise matches the current accessibility filters."
                ),
                QSystemTrayIcon.MessageIcon.Information,
                6000,
            )
            self._reset_requested_break_tracking(reset_channels)
            return
        self.data.exercise_shuffle_bag = remaining
        self.data.last_exercise_id = exercise.id
        self._cancel_exercise_postpone()
        self._pending_exercise = exercise
        self._pending_exercise_reset_channels = reset_channels
        self.open_exercise_action.setText(
            tr(
                "Open movement: {exercise}",
                exercise=exercise.title,
            )
        )
        self.open_exercise_action.setVisible(True)
        self.escalator.mark_exercise_offered(self.data, exercise.id)
        self._save_data()
        self._apply_icon()
        self._present_exercise()
        self._reset_requested_break_tracking(reset_channels)

    def _present_exercise(self) -> None:
        if self._language_reload_preparing or self._calibration_flow_active:
            return
        if self._exercise_dialog is not None:
            self._focus_exercise_dialog(self._exercise_dialog)
            return
        exercise = self._pending_exercise
        if exercise is None:
            return
        if self._side_panel is not None:
            return
        self._cancel_exercise_postpone()
        self._exercise_dialog_open = True
        self.move_now_button.setEnabled(False)
        dialog = ExerciseDialog(
            exercise,
            self.catalog,
            alternative_choices=self._alternative_break_choices(
                current_exercise_id=exercise.id,
            ),
        )
        dialog.finished.connect(self._exercise_dialog_finished)
        self._exercise_dialog = dialog
        self._capture_window_state_before_exercise()
        self._show_side_panel(dialog)

    def _capture_window_state_before_exercise(self) -> None:
        if not self.isVisible():
            self._window_state_before_exercise = "hidden"
        elif self.isMinimized():
            self._window_state_before_exercise = "minimized"
        else:
            self._window_state_before_exercise = None

    def _restore_window_state_after_exercise(self) -> None:
        state = self._window_state_before_exercise
        self._window_state_before_exercise = None
        if state is None:
            return
        if self._side_panel is not None:
            return
        if self._language_reload_preparing or self._quitting:
            return
        if state == "hidden":
            self._secondary_window_presenter.hide_for_owner()
            self.hide()
        elif state == "minimized":
            self.showMinimized()

    def _focus_exercise_dialog(self, dialog: "ExerciseDialog") -> None:
        self._focus_side_panel(dialog)

    def _schedule_exercise_postpone(self) -> None:
        if self._pending_exercise is None:
            return
        self.open_exercise_action.setVisible(True)
        self._exercise_postpone_timer.start(
            EXERCISE_POSTPONE_MINUTES * 60_000
        )

    def _cancel_exercise_postpone(self) -> None:
        self._exercise_postpone_timer.stop()

    def _present_postponed_exercise(self) -> None:
        if self._language_reload_preparing:
            return
        if (
            self._pending_exercise is None
            or self._exercise_dialog is not None
        ):
            return
        self._present_exercise()

    def _open_pending_exercise(self) -> None:
        self._present_exercise()

    def _exercise_dialog_finished(self, _result: int) -> None:
        dialog = self._exercise_dialog
        self._exercise_dialog = None
        self._exercise_dialog_open = False
        self.move_now_button.setEnabled(True)
        outcome = (
            dialog.outcome
            if dialog is not None
            else ExerciseOutcome.COMPLETED
        )
        if dialog is not None:
            self._hide_side_panel(
                dialog,
                allow_deferred_exercise=False,
            )
        if self._language_reload_preparing or self._quitting:
            return
        if outcome == ExerciseOutcome.SWAPPED:
            window_state = self._window_state_before_exercise
            reset_channels = self._pending_exercise_reset_channels
            self._clear_pending_exercise()
            self._offer_exercise(reset_channels=reset_channels)
            self._window_state_before_exercise = window_state
            return
        if outcome == ExerciseOutcome.ALTERNATIVE:
            window_state = self._window_state_before_exercise
            selected_choice = (
                dialog.selected_choice if dialog is not None else None
            )
            self._clear_pending_exercise()
            if selected_choice is not None:
                self._present_manual_break(selected_choice)
                self._window_state_before_exercise = window_state
            return
        if dialog is not None:
            QTimer.singleShot(
                0, self._restore_window_state_after_exercise
            )
        if outcome == ExerciseOutcome.POSTPONED:
            self._schedule_exercise_postpone()
        else:
            reset_channels = self._pending_exercise_reset_channels
            self._clear_pending_exercise()
            self._reset_requested_break_tracking(reset_channels)

    def _alternative_break_choices(
        self,
        *,
        current_exercise_id: str | None = None,
        current_choice: ManualBreakChoice | None = None,
    ) -> tuple[ManualBreakChoice, ...]:
        choices = [
            choice
            for choice in MANUAL_BREAK_CHOICES
            if choice is not current_choice
        ]
        has_guided_choice = bool(
            self.selector.eligible_exercises(
                self.data.exercise_preferences
            )
        )
        if current_exercise_id is not None:
            has_guided_choice = self.selector.has_alternative(
                self.data.exercise_preferences,
                current_exercise_id,
            )
        if (
            not has_guided_choice
            and ManualBreakChoice.GUIDED_MOVEMENT in choices
        ):
            choices.remove(ManualBreakChoice.GUIDED_MOVEMENT)
        return tuple(choices)

    def _present_manual_break(
        self,
        choice: ManualBreakChoice,
    ) -> None:
        if self._language_reload_preparing:
            return
        prompt = manual_break_prompt(
            choice,
            self.data.break_preferences,
        )
        self._reset_break_channels((prompt.channel,))
        dialog = RestBreakDialog(
            prompt,
            self._alternative_break_choices(current_choice=choice),
        )
        dialog.finished.connect(self._rest_break_dialog_finished)
        self._rest_break_dialog = dialog
        self.move_now_button.setEnabled(False)
        self._show_side_panel(dialog)

    def _rest_break_dialog_finished(self, _result: int) -> None:
        dialog = self._rest_break_dialog
        self._rest_break_dialog = None
        self.move_now_button.setEnabled(True)
        if dialog is not None:
            self._hide_side_panel(
                dialog,
                allow_deferred_exercise=False,
            )
        if self._language_reload_preparing or self._quitting:
            return
        if (
            dialog is not None
            and dialog.outcome == RestBreakOutcome.SWITCHED
            and dialog.selected_choice is not None
        ):
            window_state = self._window_state_before_exercise
            if (
                dialog.selected_choice
                is ManualBreakChoice.GUIDED_MOVEMENT
            ):
                self._offer_exercise()
            else:
                self._present_manual_break(dialog.selected_choice)
            self._window_state_before_exercise = window_state
            return
        QTimer.singleShot(0, self._restore_window_state_after_exercise)

    def _clear_pending_exercise(self) -> None:
        self._cancel_exercise_postpone()
        self._pending_exercise = None
        self._pending_exercise_reset_channels = ()
        self.open_exercise_action.setVisible(False)
        self._apply_icon()

    @staticmethod
    def _merge_exercise_reset_channels(
        current: tuple[BreakChannel, ...],
        additional: tuple[BreakChannel, ...],
    ) -> tuple[BreakChannel, ...]:
        return tuple(dict.fromkeys((*current, *additional)))

    def _reset_requested_break_tracking(
        self,
        channels: tuple[BreakChannel, ...],
    ) -> None:
        self._reset_break_channels(channels)

    def _record_valid_tracking(self) -> None:
        now = time.monotonic()
        self._tracking_gap_started_at = None
        self._last_valid_tracking_at = now

    def _mark_tracking_interrupted(self) -> None:
        if self._tracking_gap_started_at is None:
            self._tracking_gap_started_at = time.monotonic()
        self._last_valid_tracking_at = None

    def _reset_break_counters(self) -> None:
        self._tracked_seconds_since_break = 0.0
        self._tracked_seconds_since_eye_break = 0.0
        self._tracked_seconds_since_hydration_break = 0.0
        self._tracked_seconds_since_reset_break = 0.0
        self._update_break_countdown()

    def _reset_movement_break_tracking(self) -> None:
        self._tracked_seconds_since_break = 0.0

    def _reset_eye_break_tracking(self) -> None:
        self._tracked_seconds_since_eye_break = 0.0

    def _reset_break_channels(
        self,
        channels: tuple[BreakChannel, ...],
    ) -> None:
        for channel in channels:
            if channel is BreakChannel.MOVEMENT:
                self._reset_movement_break_tracking()
            elif channel is BreakChannel.EYE:
                self._reset_eye_break_tracking()
            elif channel is BreakChannel.HYDRATION:
                self._tracked_seconds_since_hydration_break = 0.0
            else:
                self._tracked_seconds_since_reset_break = 0.0
        self._update_break_countdown()

    def _record_history_assessment(
        self,
        assessment: PostureAssessment,
        setup_id: str,
    ) -> None:
        if self.history_recorder is None:
            return
        try:
            self.history_recorder.record(assessment, setup_id)
        except HistoryStorageError as error:
            self._disable_history_for_session(error)

    def _record_history_reminder(self, event: ReminderEvent) -> None:
        if self.history_recorder is None:
            return
        try:
            self.history_recorder.record_reminder(event)
        except HistoryStorageError as error:
            self._disable_history_for_session(error)

    def _checkpoint_history(self) -> None:
        if self._language_reload_preparing:
            return
        if self.history_recorder is None:
            return
        try:
            self.history_recorder.checkpoint()
            today = datetime.now().astimezone().date()
            if (
                today != self._last_history_prune_date
                and self.history_store is not None
            ):
                self.history_store.prune(
                    self.data.history_preferences.retention_days
                )
                self._last_history_prune_date = today
        except HistoryStorageError as error:
            self._disable_history_for_session(error)

    def _suspend_history(self) -> None:
        if self.history_recorder is None:
            return
        try:
            self.history_recorder.suspend()
        except HistoryStorageError as error:
            self._disable_history_for_session(error)

    def _disable_history_for_session(
        self,
        error: HistoryStorageError,
    ) -> None:
        self._history_disabled_for_session = True
        if self.history_recorder is None:
            return
        self.history_recorder = None
        self._history_error = str(error)
        self.summary_button.setEnabled(False)
        self.summary_action.setEnabled(False)
        self._show_tray_message(
            tr("Workday history disabled"),
            str(error),
            QSystemTrayIcon.MessageIcon.Warning,
            10_000,
        )

    def _show_initial_history_error(self) -> None:
        if self._language_reload_preparing:
            return
        if self._history_error is None:
            return
        self._show_notice(
            tr("Workday history unavailable"),
            tr(
                "{error}\n\nPosture tracking continues without saving "
                "summaries.",
                error=self._history_error,
            ),
            critical=True,
        )

    def _history_summary_for_date(
        self,
        selected_date: date,
    ) -> DailyPostureSummary:
        if self.history_store is None:
            raise HistoryStorageError(
                self._history_error or tr("Workday history is unavailable.")
            )
        try:
            if (
                self.history_recorder is not None
                and selected_date == datetime.now().astimezone().date()
            ):
                self.history_recorder.checkpoint()
            return self.history_store.daily_summary(selected_date)
        except HistoryStorageError as error:
            self._disable_history_for_session(error)
            raise
