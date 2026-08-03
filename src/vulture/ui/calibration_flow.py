from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog

from vulture.i18n import tr
from vulture.models import (
    CalibrationProfile,
    SetupProfile,
    TrackerState,
    utc_now,
)
from vulture.tracking import PostureEvaluator

from .calibration import (
    CALIBRATION_STEPS,
    CalibrationDialog,
    CalibrationStep,
    CalibrationStepSelectionDialog,
)


class CalibrationFlowMixin:
    def _cancel_active_calibration(self) -> None:
        if self._calibration_window is not None:
            self._calibration_window.reject()
        elif self._calibration_flow_active:
            self._end_calibration_flow()

    def _end_calibration_flow(self) -> None:
        self._calibration_dialog = None
        self._calibration_window = None
        self._calibration_flow_active = False
        self._refresh_setup_combo()
        QTimer.singleShot(
            0,
            lambda: self._show_deferred_panel(allow_exercise=True),
        )

    def _persist_calibration_profile(
        self,
        setup: SetupProfile,
        profile: CalibrationProfile,
    ) -> bool:
        previous_calibration = setup.calibration
        previous_updated_at = setup.updated_at
        previous_evaluator = self.evaluator
        setup.calibration = profile
        setup.updated_at = utc_now()
        self.evaluator = PostureEvaluator(
            profile,
            self.data.alert_policy,
        )
        if self._save_data():
            self._refresh_setup_combo()
            return True
        setup.calibration = previous_calibration
        setup.updated_at = previous_updated_at
        self.evaluator = previous_evaluator
        return False

    def _calibrate(self) -> None:
        if self._language_reload_preparing:
            return
        if not self._tracking_enabled:
            self._show_camera_released_state()
            return
        if self._calibration_flow_active:
            self._begin_calibration_flow()
            return
        if self.data.active_setup() is None:
            self._set_state(
                TrackerState.UNCALIBRATED,
                tr("Add a camera setup first."),
            )
            return
        if not self._camera_is_healthy():
            self._activate_setup()
        if not self._camera_is_healthy():
            self._set_state(
                TrackerState.CAMERA_UNAVAILABLE,
                tr(
                    "The saved camera for this setup is not available for "
                    "calibration."
                ),
            )
            return
        if not self._begin_calibration_flow():
            return
        self._set_state(
            TrackerState.CALIBRATING,
            tr(
                "Follow the calibration guide. Tracking alerts are paused."
            ),
        )
        self._suspend_history()
        self._reset_break_tracking()
        dialog = CalibrationDialog(self)
        self._calibration_dialog = dialog
        self._show_calibration_window(
            dialog,
            key="calibration-capture",
        )
        dialog.finished.connect(
            lambda result, active_dialog=dialog: (
                self._finish_full_calibration(active_dialog, result)
            )
        )

    def _finish_full_calibration(
        self,
        dialog: CalibrationDialog,
        result: int,
    ) -> None:
        if dialog is not self._calibration_dialog:
            return
        profile = dialog.profile
        completion_notice = dialog.completion_notice
        try:
            calibration_saved = False
            persistence_failed = False
            if not self._camera_is_healthy():
                if self._state != TrackerState.CAMERA_UNAVAILABLE:
                    self._set_state(
                        TrackerState.CAMERA_UNAVAILABLE,
                        tr("The camera stopped during calibration."),
                    )
                return
            if (
                result == QDialog.DialogCode.Accepted
                and profile is not None
            ):
                setup = self.data.active_setup()
                if setup is not None:
                    if self._persist_calibration_profile(
                        setup,
                        profile,
                    ):
                        calibration_saved = True
                    else:
                        persistence_failed = True
            if self._state == TrackerState.CAMERA_UNAVAILABLE:
                return
            setup = self.data.active_setup()
            if persistence_failed:
                if setup is None or setup.calibration is None:
                    self._set_state(
                        TrackerState.UNCALIBRATED,
                        tr(
                            "Calibration could not be saved. This setup still "
                            "needs calibration."
                        ),
                    )
                else:
                    self._set_state_after_calibration(
                        tr(
                            "Calibration could not be saved. The existing "
                            "calibration was kept."
                        )
                    )
            elif setup is None or setup.calibration is None:
                self._set_state(
                    TrackerState.UNCALIBRATED,
                    tr("This setup still needs calibration."),
                )
            elif calibration_saved:
                message = tr("Calibration saved.")
                if completion_notice:
                    message += " " + completion_notice
                self._set_state_after_calibration(
                    message
                )
            else:
                self._set_state_after_calibration(
                    tr(
                        "Calibration cancelled. Existing calibration was kept."
                    )
                )
        finally:
            self._end_calibration_flow()

    def _recalibrate_step(self) -> None:
        if self._language_reload_preparing:
            return
        if not self._tracking_enabled:
            self._show_camera_released_state()
            return
        if self._calibration_flow_active:
            self._begin_calibration_flow()
            return
        setup = self.data.active_setup()
        if setup is None or setup.calibration is None:
            self._set_state(
                TrackerState.UNCALIBRATED,
                tr("Complete a full calibration for this setup first."),
            )
            return
        if not self._camera_is_healthy():
            self._activate_setup()
        if not self._camera_is_healthy():
            self._set_state(
                TrackerState.CAMERA_UNAVAILABLE,
                tr("The saved camera for this setup is not available."),
            )
            return

        if not self._begin_calibration_flow():
            return
        selection = CalibrationStepSelectionDialog(
            setup.calibration,
            self,
        )
        self._show_calibration_window(
            selection,
            key="calibration-selection",
        )
        selection.finished.connect(
            lambda result, active_selection=selection, active_setup=setup: (
                self._finish_recalibration_selection(
                    active_selection,
                    active_setup,
                    result,
                )
            )
        )

    def _finish_recalibration_selection(
        self,
        selection: CalibrationStepSelectionDialog,
        setup: SetupProfile,
        result: int,
    ) -> None:
        if selection is not self._calibration_window:
            return
        if result != QDialog.DialogCode.Accepted:
            self._end_calibration_flow()
            return

        selected_step = selection.selected_step()
        if (
            self._state == TrackerState.CAMERA_UNAVAILABLE
            or not self._camera_is_healthy()
        ):
            self._set_state(
                TrackerState.CAMERA_UNAVAILABLE,
                tr(
                    "The saved camera stopped before calibration could begin."
                ),
            )
            self._end_calibration_flow()
            return

        if selected_step.category is None:
            self._run_recalibration_dialog(
                setup,
                steps=[
                    selected_step.model_copy(
                        update={"required": True}
                    )
                ],
                base_profile=None,
                tracking_message=tr("Recalibrating good baseline."),
                success_message=tr(
                    "Good baseline saved. Recalibrate unwanted postures "
                    "as needed."
                ),
                save_failure_message=tr(
                    "Baseline update could not be saved. The existing "
                    "calibration was kept."
                ),
                cancel_message=tr(
                    "Baseline update cancelled. The existing calibration "
                    "was kept."
                ),
            )
            return

        posture_step = selected_step
        selected_instructions = tr(
            posture_step.instructions
        ).removeprefix(
            tr("Optional: ")
        )
        selected_step = posture_step.model_copy(
            update={
                "required": True,
                "instructions": selected_instructions[:1].upper()
                + selected_instructions[1:],
            },
        )
        baseline_step = CalibrationStep(
            key="good",
            title="Confirm saved good baseline",
            instructions=(
                "Return to the comfortable good posture used for this "
                "setup. This confirms that the camera and seat still "
                "match before the new unwanted example is learned."
            ),
            image_filename=CALIBRATION_STEPS[0].image_filename,
            required=True,
            capture_seconds=10,
        )

        self._run_recalibration_dialog(
            setup,
            steps=[baseline_step, selected_step],
            base_profile=setup.calibration,
            tracking_message=tr(
                "Recalibrating posture example: {posture}.",
                posture=tr(selected_step.title),
            ),
            success_message=tr(
                "{posture} saved.",
                posture=tr(selected_step.title),
            ),
            save_failure_message=tr(
                "Posture update could not be saved. The existing "
                "calibration was kept."
            ),
            cancel_message=tr(
                "Posture update cancelled. Existing calibration was kept."
            ),
        )

    def _run_recalibration_dialog(
        self,
        setup: SetupProfile,
        *,
        steps: list[CalibrationStep],
        base_profile: CalibrationProfile | None,
        tracking_message: str,
        success_message: str,
        save_failure_message: str,
        cancel_message: str,
    ) -> None:
        self._suspend_history()
        self._reset_break_tracking()
        self._set_state(TrackerState.CALIBRATING, tracking_message)
        dialog = CalibrationDialog(
            self,
            steps=steps,
            base_profile=base_profile,
        )
        self._calibration_dialog = dialog
        self._show_calibration_window(
            dialog,
            key="calibration-capture",
        )
        dialog.finished.connect(
            lambda result, active_dialog=dialog, active_setup=setup: (
                self._finish_recalibration_dialog(
                    active_dialog,
                    active_setup,
                    result,
                    success_message=success_message,
                    save_failure_message=save_failure_message,
                    cancel_message=cancel_message,
                )
            )
        )

    def _finish_recalibration_dialog(
        self,
        dialog: CalibrationDialog,
        setup: SetupProfile,
        result: int,
        *,
        success_message: str,
        save_failure_message: str,
        cancel_message: str,
    ) -> None:
        if dialog is not self._calibration_dialog:
            return
        profile = dialog.profile
        completion_notice = dialog.completion_notice
        try:
            if (
                self._state == TrackerState.CAMERA_UNAVAILABLE
                or not self._camera_is_healthy()
            ):
                if self._state != TrackerState.CAMERA_UNAVAILABLE:
                    self._set_state(
                        TrackerState.CAMERA_UNAVAILABLE,
                        tr("The camera stopped during calibration."),
                    )
                return
            if (
                result == QDialog.DialogCode.Accepted
                and profile is not None
            ):
                if self._persist_calibration_profile(setup, profile):
                    message = success_message
                    if completion_notice:
                        message += " " + completion_notice
                    self._set_state_after_calibration(message)
                else:
                    self._set_state_after_calibration(
                        save_failure_message
                    )
                return
            self._set_state_after_calibration(cancel_message)
        finally:
            self._end_calibration_flow()

    def _set_state_after_calibration(self, message: str) -> None:
        if self._state == TrackerState.CAMERA_UNAVAILABLE:
            return
        if not self._tracking_enabled:
            self._set_state(
                TrackerState.STOPPED,
                tr(
                    "{message} Tracking remains paused.",
                    message=message,
                ),
            )
        elif not self._camera_is_healthy():
            self._set_state(
                TrackerState.CAMERA_UNAVAILABLE,
                tr(
                    "{message} The camera is no longer available.",
                    message=message,
                ),
            )
        else:
            self._set_state(
                TrackerState.LOW_CONFIDENCE,
                tr(
                    "{message} Finding your landmarks...",
                    message=message,
                ),
            )
