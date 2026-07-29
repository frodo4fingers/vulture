from __future__ import annotations

from datetime import datetime

from pydantic import Field
from PySide6.QtCore import QSize, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QDialog, QMainWindow

from vulture.autostart import AutostartManager
from vulture.camera import CameraThread
from vulture.exercises import (
    Exercise,
    ExerciseCatalog,
    ExerciseSelector,
    ReminderEscalator,
)
from vulture.history import (
    HistoryStorageError,
    PostureHistoryStore,
    WorkdayRecorder,
)
from vulture.i18n import tr
from vulture.models import AppData, StrictModel, TrackerState
from vulture.storage import AppDataStore
from vulture.tracking import PostureEvaluator, PostureEvaluatorState

from .application_flow import ApplicationFlowMixin
from .calibration import CalibrationDialog, SetupDialog
from .calibration_flow import CalibrationFlowMixin
from .exercises import EvidenceDialog, ExerciseDialog
from .notices import NoticeDialog
from .settings import SettingsDialog
from .shell import ShellMixin
from .summary_dialog import WorkdaySummaryDialog
from .tracking_flow import TrackingFlowMixin


class MainWindowRuntimeState(StrictModel):
    tracking_enabled: bool = True
    tracked_seconds_since_break: float = Field(default=0.0, ge=0)
    evaluator_state: PostureEvaluatorState | None = None
    history_disabled_for_session: bool = False


class MainWindow(
    ShellMixin,
    CalibrationFlowMixin,
    TrackingFlowMixin,
    ApplicationFlowMixin,
    QMainWindow,
):
    language_change_requested = Signal(str)

    def __init__(
        self,
        store: AppDataStore,
        data: AppData,
        catalog: ExerciseCatalog,
        history_store: PostureHistoryStore | None = None,
        runtime_state: MainWindowRuntimeState | None = None,
        autostart_manager: AutostartManager | None = None,
    ) -> None:
        super().__init__()
        self.store = store
        self.data = data
        self.catalog = catalog
        self.autostart_manager = autostart_manager or AutostartManager()
        self.selector = ExerciseSelector(catalog)
        self.escalator = ReminderEscalator()
        self.camera_thread: CameraThread | None = None
        self.evaluator: PostureEvaluator | None = None
        self._side_panel: QDialog | None = None
        self._size_before_side_panel: QSize | None = None
        self._calibration_dialog: CalibrationDialog | None = None
        self._calibration_panel: QDialog | None = None
        self._calibration_flow_active = False
        self._setup_dialog: SetupDialog | None = None
        self._settings_dialog: SettingsDialog | None = None
        self._exercise_dialog: ExerciseDialog | None = None
        self._evidence_dialog: EvidenceDialog | None = None
        self._summary_dialog: WorkdaySummaryDialog | None = None
        self._notice_dialog: NoticeDialog | None = None
        self._pending_notice: tuple[str, str, bool] | None = None
        self._pending_exercise: Exercise | None = None
        self._latest_image: QImage | None = None
        self._tracking_enabled = (
            runtime_state.tracking_enabled
            if runtime_state is not None
            else True
        )
        self._language_reload_preparing = False
        self._quitting = False
        self._close_notice_shown = False
        self._exercise_dialog_open = False
        self._tracked_seconds_since_break = 0.0
        self._last_valid_tracking_at: float | None = None
        self._state = TrackerState.STOPPED
        self._history_error: str | None = None
        self._history_disabled_for_session = bool(
            runtime_state
            and runtime_state.history_disabled_for_session
        )
        self.history_store: PostureHistoryStore | None = None
        self.history_recorder: WorkdayRecorder | None = None
        if not self._history_disabled_for_session:
            try:
                self.history_store = history_store or PostureHistoryStore(
                    self.store.path.with_name("posture-history.sqlite3")
                )
                self.history_store.prune(
                    self.data.history_preferences.retention_days
                )
                self.history_recorder = WorkdayRecorder(
                    self.history_store,
                    enabled=self.data.history_preferences.enabled,
                )
            except HistoryStorageError as error:
                self._history_disabled_for_session = True
                self._history_error = str(error)
                if self.history_store is not None:
                    try:
                        self.history_store.close()
                    except HistoryStorageError as close_error:
                        self._history_error = tr(
                            "{message} Closing it also failed: {error}",
                            message=self._history_error,
                            error=close_error,
                        )
                self.history_store = None
        self._last_history_prune_date = datetime.now().astimezone().date()

        self.setWindowTitle("Vulture")
        self.setMinimumSize(760, 650)
        self._build_ui()
        self._build_tray()
        self._refresh_setup_combo()

        self.break_timer = QTimer(self)
        self.break_timer.setInterval(60_000)
        self.break_timer.timeout.connect(self._check_sedentary_break)
        self.break_timer.start()
        self._exercise_postpone_timer = QTimer(self)
        self._exercise_postpone_timer.setSingleShot(True)
        self._exercise_postpone_timer.timeout.connect(
            self._present_postponed_exercise
        )
        self.history_timer = QTimer(self)
        self.history_timer.setInterval(10_000)
        self.history_timer.timeout.connect(self._checkpoint_history)
        self.history_timer.start()

        if self._history_error is not None:
            QTimer.singleShot(0, self._show_initial_history_error)

        if self.data.active_setup() is not None:
            self._activate_setup()
        else:
            self._set_state(
                TrackerState.UNCALIBRATED,
                tr("Add a camera setup to begin."),
            )
        if runtime_state is not None:
            self._restore_runtime_state(runtime_state)

    def _runtime_state(self) -> MainWindowRuntimeState:
        return MainWindowRuntimeState(
            tracking_enabled=self._tracking_enabled,
            tracked_seconds_since_break=self._tracked_seconds_since_break,
            evaluator_state=(
                self.evaluator.snapshot()
                if self.evaluator is not None
                else None
            ),
            history_disabled_for_session=(
                self._history_disabled_for_session
            ),
        )

    def _restore_runtime_state(
        self,
        state: MainWindowRuntimeState,
    ) -> None:
        self._tracking_enabled = state.tracking_enabled
        self._tracked_seconds_since_break = (
            state.tracked_seconds_since_break
        )
        self._last_valid_tracking_at = None
        if self.evaluator is not None and state.evaluator_state is not None:
            self.evaluator.restore(state.evaluator_state)
        self._set_tracking_controls()
        if not self._tracking_enabled:
            self._suspend_history()
            self._show_camera_released_state()

    def _resume_after_failed_language_reload(
        self,
        state: MainWindowRuntimeState,
    ) -> None:
        self._language_reload_preparing = False
        self.break_timer.start()
        if self.history_store is not None:
            self.history_timer.start()
        self._activate_setup()
        self._restore_runtime_state(state)

    def prepare_for_language_reload(
        self,
    ) -> MainWindowRuntimeState | None:
        self._language_reload_preparing = True
        runtime_state = self._runtime_state()
        self.break_timer.stop()
        self._cancel_active_calibration()
        self._dismiss_side_panel()
        if not self._stop_camera(10_000):
            self._language_reload_preparing = False
            self.break_timer.start()
            self._show_camera_release_error()
            return None
        if not self._close_history():
            self._resume_after_failed_language_reload(runtime_state)
            return None
        self._clear_pending_exercise()
        self.tray.hide()
        self.hide()
        return runtime_state
