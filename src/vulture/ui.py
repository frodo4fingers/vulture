from __future__ import annotations

import math
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from pydantic import Field, ValidationError
from PySide6.QtCharts import (
    QAreaSeries,
    QCategoryAxis,
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import (
    QDate,
    QEvent,
    QLocale,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCloseEvent,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vulture.autostart import (
    AutostartError,
    AutostartManager,
    AutostartSnapshot,
)
from vulture.calibration import CalibrationError, CalibrationFitter
from vulture.camera import (
    CameraThread,
    discover_cameras,
    resolve_camera_descriptor,
)
from vulture.exercises import (
    Exercise,
    ExerciseCatalog,
    ExerciseSelector,
    ReminderEscalator,
    exercise_media_path,
)
from vulture.history import (
    BASELINE_POSTURE,
    DailyPostureSummary,
    HistoryStorageError,
    PostureHistoryStore,
    StoredPostureEpisode,
    WorkdayRecorder,
)
from vulture.i18n import LANGUAGE_NAMES, tr
from vulture.models import (
    AlertPolicy,
    AppData,
    CalibrationProfile,
    CameraDescriptor,
    ExercisePreferences,
    FeatureFrame,
    HistoryPreferences,
    InterfaceLanguage,
    PostureCategory,
    ReminderEvent,
    SetupProfile,
    StrictModel,
    TrackerState,
    utc_now,
)
from vulture.resources import resource_path
from vulture.storage import AppDataStore, StorageError
from vulture.tracking import (
    PostureAssessment,
    PostureEvaluator,
    PostureEvaluatorState,
)


STATE_COLORS = {
    TrackerState.STOPPED: "#718096",
    TrackerState.CALIBRATING: "#3182ce",
    TrackerState.GOOD: "#2f855a",
    TrackerState.WARNING: "#d69e2e",
    TrackerState.ALERT: "#c53030",
    TrackerState.LOW_CONFIDENCE: "#718096",
    TrackerState.CAMERA_UNAVAILABLE: "#718096",
    TrackerState.UNCALIBRATED: "#805ad5",
}
STATE_FOREGROUND_COLORS = {
    state: "#f7fafc" for state in TrackerState
}
STATE_FOREGROUND_COLORS[TrackerState.WARNING] = "#1a202c"

# Marker drawn on the tray and taskbar icon while a movement is waiting to do.
EXERCISE_BADGE_COLOR = "#ecc94b"

SEMANTIC_PANEL_COLORS = {
    "light": {
        "info": ("#edf2f7", "#1a202c", "#cbd5e0"),
        "safety": ("#fff5f5", "#742a2a", "#feb2b2"),
        "good": ("#f0fff4", "#22543d", "#9ae6b4"),
        "unwanted": ("#fffaf0", "#7b341e", "#fbd38d"),
    },
    "dark": {
        "info": ("#202832", "#edf2f7", "#465463"),
        "safety": ("#351f24", "#ffd9de", "#8f4d59"),
        "good": ("#183326", "#d9f7e5", "#397b55"),
        "unwanted": ("#392d17", "#ffe6b8", "#8d6a2c"),
    },
}


def semantic_panel_style(
    tone: str,
    *,
    strong: bool = False,
) -> str:
    window_color = QApplication.palette().color(
        QPalette.ColorRole.Window
    )
    palette_name = (
        "dark"
        if window_color.lightness() < 128
        else "light"
    )
    background, foreground, border = SEMANTIC_PANEL_COLORS[palette_name][tone]
    weight = "; font-weight: 700" if strong else ""
    return (
        f"background-color: {background}; color: {foreground}; "
        f"border: 1px solid {border}; border-radius: 5px; padding: 9px"
        f"{weight}"
    )


class SemanticLabel(QLabel):
    def __init__(
        self,
        text: str = "",
        *,
        tone: str = "info",
        strong: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._semantic_tone = tone
        self._semantic_strong = strong
        self._applying_semantic_style = False
        self.setWordWrap(True)
        self._apply_semantic_style()

    def set_semantic_tone(
        self,
        tone: str,
        *,
        strong: bool | None = None,
    ) -> None:
        self._semantic_tone = tone
        if strong is not None:
            self._semantic_strong = strong
        self._apply_semantic_style()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.PaletteChange
            and not self._applying_semantic_style
        ):
            self._apply_semantic_style()

    def _apply_semantic_style(self) -> None:
        style = semantic_panel_style(
            self._semantic_tone,
            strong=self._semantic_strong,
        )
        if self.styleSheet() == style:
            return
        self._applying_semantic_style = True
        try:
            self.setStyleSheet(style)
        finally:
            self._applying_semantic_style = False
SUMMARY_POSTURES = (
    (BASELINE_POSTURE, "Within baseline"),
    (PostureCategory.FORWARD_HEAD.value, "Head forward"),
    (PostureCategory.SLOUCH.value, "Slouch / crouch"),
    (PostureCategory.SHOULDERS_SUNK.value, "Shoulders sunk"),
    (PostureCategory.LATERAL_LEAN.value, "Lateral lean"),
    (PostureCategory.GENERAL_DEVIATION.value, "Other baseline deviation"),
)
POSTURE_TITLES = dict(SUMMARY_POSTURES)
SUMMARY_POSTURE_COLORS = {
    BASELINE_POSTURE: "#2f855a",
    PostureCategory.FORWARD_HEAD.value: "#dd6b20",
    PostureCategory.SLOUCH.value: "#c53030",
    PostureCategory.SHOULDERS_SUNK.value: "#805ad5",
    PostureCategory.LATERAL_LEAN.value: "#3182ce",
    PostureCategory.GENERAL_DEVIATION.value: "#718096",
}
SUMMARY_CHART_BUCKET_SECONDS = 15 * 60
REMINDER_STAGE_TITLES = {
    TrackerState.GOOD: "No reminder",
    TrackerState.WARNING: "Warning",
    TrackerState.ALERT: "Notification",
}


@dataclass(frozen=True, slots=True)
class PostureAreaData:
    start_hour: float
    end_hour: float
    bucket_hours: tuple[float, ...]
    minutes_by_posture: dict[str, tuple[float, ...]]


def build_posture_area_data(
    summary: DailyPostureSummary,
) -> PostureAreaData | None:
    episode_bounds: list[tuple[StoredPostureEpisode, float, float]] = []
    for episode in summary.episodes:
        local_timezone = timezone(
            timedelta(minutes=episode.utc_offset_minutes)
        )
        local_start = episode.started_at.astimezone(local_timezone)
        seconds_from_midnight = (
            (local_start.date() - summary.local_date).days * 86_400
            + local_start.hour * 3_600
            + local_start.minute * 60
            + local_start.second
            + local_start.microsecond / 1_000_000
        )
        started_at = max(0.0, min(86_400.0, seconds_from_midnight))
        ended_at = min(
            86_400.0,
            started_at + episode.duration_seconds,
        )
        if ended_at > started_at:
            episode_bounds.append((episode, started_at, ended_at))

    if not episode_bounds:
        return None

    first_second = min(
        started_at
        for _episode, started_at, _end in episode_bounds
    )
    last_second = max(ended_at for _episode, _start, ended_at in episode_bounds)
    chart_start = math.floor(first_second / 3_600) * 3_600
    chart_end = math.ceil(last_second / 3_600) * 3_600
    if chart_end <= chart_start:
        chart_end = min(86_400, chart_start + 3_600)

    bucket_count = max(
        1,
        math.ceil(
            (chart_end - chart_start) / SUMMARY_CHART_BUCKET_SECONDS
        ),
    )
    minutes_by_posture = {
        posture: [0.0] * bucket_count
        for posture, _title in SUMMARY_POSTURES
    }
    known_postures = set(minutes_by_posture)
    fallback_posture = PostureCategory.GENERAL_DEVIATION.value

    for episode, started_at, ended_at in episode_bounds:
        posture = (
            episode.posture
            if episode.posture in known_postures
            else fallback_posture
        )
        first_bucket = max(
            0,
            int(
                (started_at - chart_start)
                // SUMMARY_CHART_BUCKET_SECONDS
            ),
        )
        last_bucket = min(
            bucket_count - 1,
            math.ceil(
                (ended_at - chart_start)
                / SUMMARY_CHART_BUCKET_SECONDS
            )
            - 1,
        )
        for bucket_index in range(first_bucket, last_bucket + 1):
            bucket_start = (
                chart_start
                + bucket_index * SUMMARY_CHART_BUCKET_SECONDS
            )
            bucket_end = bucket_start + SUMMARY_CHART_BUCKET_SECONDS
            overlap_seconds = max(
                0.0,
                min(ended_at, bucket_end)
                - max(started_at, bucket_start),
            )
            minutes_by_posture[posture][bucket_index] += (
                overlap_seconds / 60
            )

    return PostureAreaData(
        start_hour=chart_start / 3_600,
        end_hour=chart_end / 3_600,
        bucket_hours=tuple(
            (
                chart_start
                + (bucket_index + 0.5) * SUMMARY_CHART_BUCKET_SECONDS
            )
            / 3_600
            for bucket_index in range(bucket_count)
        ),
        minutes_by_posture={
            posture: tuple(minutes)
            for posture, minutes in minutes_by_posture.items()
        },
    )


class MainWindowRuntimeState(StrictModel):
    tracking_enabled: bool = True
    tracked_seconds_since_break: float = Field(default=0.0, ge=0)
    evaluator_state: PostureEvaluatorState | None = None
    history_disabled_for_session: bool = False


def set_accessible_link_palette(browser: QTextBrowser) -> None:
    palette = browser.palette()
    base = palette.color(QPalette.ColorRole.Base)
    if base.lightness() < 128:
        link = QColor("#90cdf4")
        visited_link = QColor("#d6bcfa")
    else:
        link = QColor("#2b6cb0")
        visited_link = QColor("#6b46c1")
    palette.setColor(QPalette.ColorRole.Link, link)
    palette.setColor(QPalette.ColorRole.LinkVisited, visited_link)
    browser.setPalette(palette)
    browser.document().setDefaultStyleSheet(
        f"a {{ color: {link.name()}; text-decoration: underline; }}"
    )


def format_duration(seconds: float) -> str:
    rounded = max(0, round(seconds))
    hours, remainder = divmod(rounded, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    if hours:
        return tr(
            "{hours}h {minutes:02d}m",
            hours=hours,
            minutes=minutes,
        )
    if minutes:
        return tr(
            "{minutes}m {seconds:02d}s",
            minutes=minutes,
            seconds=remaining_seconds,
        )
    return tr("{seconds}s", seconds=remaining_seconds)


def create_state_icon(
    state: TrackerState, size: int = 64, *, badge: bool = False
) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(STATE_COLORS[state]))
    painter.drawEllipse(3, 3, size - 6, size - 6)
    painter.setPen(QColor("white"))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(round(size * 0.50))
    painter.setFont(font)
    painter.drawText(
        pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "V"
    )
    if badge:
        diameter = round(size * 0.42)
        left = size - diameter
        top = 0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(
            left - 2, top, diameter + 4, diameter + 4
        )
        painter.setBrush(QColor(EXERCISE_BADGE_COLOR))
        painter.drawEllipse(left, top + 2, diameter, diameter)
    painter.end()
    return QIcon(pixmap)


class CalibrationStep(StrictModel):
    key: str
    title: str
    instructions: str
    image_filename: str | None = None
    category: PostureCategory | None = None
    required: bool = False
    capture_seconds: int = Field(default=15, ge=5)


CALIBRATION_STEPS = [
    CalibrationStep(
        key="good",
        title="Comfortable baseline",
        instructions=(
            "Sit in a comfortable position you want Vulture to use as your "
            "baseline. Breathe normally and make small natural movements."
        ),
        image_filename="calibration-01-comfortable-baseline.jpg",
        required=True,
    ),
    CalibrationStep(
        key=PostureCategory.FORWARD_HEAD.value,
        title="Head-forward example",
        instructions=(
            "Optional: comfortably demonstrate the head-forward position you "
            "want detected while keeping your torso fairly still. Do not force "
            "your neck, and stop if anything hurts."
        ),
        image_filename="calibration-02-head-forward.jpg",
        category=PostureCategory.FORWARD_HEAD,
    ),
    CalibrationStep(
        key=PostureCategory.SLOUCH.value,
        title="Slouch example",
        instructions=(
            "Optional: comfortably demonstrate your usual collapsed or "
            "crouched torso position. Do not exaggerate or move into pain."
        ),
        image_filename="calibration-03-slouch.jpg",
        category=PostureCategory.SLOUCH,
    ),
    CalibrationStep(
        key=PostureCategory.SHOULDERS_SUNK.value,
        title="Sunk-shoulder example",
        instructions=(
            "Optional: let your shoulders settle into the low or rounded "
            "position you want detected. Keep the movement gentle."
        ),
        image_filename="calibration-04-sunk-shoulders.jpg",
        category=PostureCategory.SHOULDERS_SUNK,
    ),
    CalibrationStep(
        key=PostureCategory.LATERAL_LEAN.value,
        title="Side-lean example",
        instructions=(
            "Optional: gently lean to either side as you sometimes do at the "
            "desk. One side is enough; Vulture scores the size of this change."
        ),
        image_filename="calibration-05-side-lean.jpg",
        category=PostureCategory.LATERAL_LEAN,
    ),
]
POSTURE_STEPS = {
    step.category: step
    for step in CALIBRATION_STEPS
    if step.category is not None
}


class CalibrationStageImage(QLabel):
    ASPECT_RATIO = 16 / 9

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_pixmap = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.setStyleSheet(
            "background: #1a202c; border: 1px solid #cbd5e0; "
            "border-radius: 6px"
        )

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return max(160, round(width / self.ASPECT_RATIO))

    def sizeHint(self) -> QSize:
        return QSize(480, 270)

    def minimumSizeHint(self) -> QSize:
        return QSize(284, 160)

    def set_step(self, step: CalibrationStep) -> None:
        if step.image_filename is None:
            self._source_pixmap = QPixmap()
            self.clear()
            self.hide()
            return
        path = resource_path("calibration", step.image_filename)
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            raise RuntimeError(
                f"Calibration image could not be decoded: {path}"
            )
        self._source_pixmap = pixmap
        self.setAccessibleName(tr(step.title))
        self.setAccessibleDescription(tr(step.instructions))
        self.show()
        self._refresh_pixmap()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_pixmap()

    def _refresh_pixmap(self) -> None:
        if self._source_pixmap.isNull():
            return
        self.setPixmap(
            self._source_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class NoticeDialog(QDialog):
    def __init__(
        self,
        title: str,
        message: str,
        *,
        critical: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        message_label = SemanticLabel(
            message,
            tone="safety" if critical else "info",
        )
        layout.addWidget(message_label)
        layout.addStretch()


class SetupDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Add camera setup"))
        self.setMinimumWidth(420)
        self._cameras = discover_cameras()

        layout = QVBoxLayout(self)
        explanation = QLabel(
            tr(
                "Create a separate setup for every camera position, even when "
                "two setups use the same physical camera."
            )
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        form = QFormLayout()
        self.name_edit = QLineEdit(tr("Desk setup"))
        self.camera_combo = QComboBox()
        for camera in self._cameras:
            self.camera_combo.addItem(camera.display_name, camera)
        form.addRow(tr("Setup name"), self.name_edit)
        form.addRow(tr("Camera"), self.camera_combo)
        layout.addLayout(form)

        if not self._cameras:
            warning = QLabel(
                tr(
                    "No camera devices were found. Connect or enable a camera, "
                    "then reopen this dialog."
                )
            )
            warning.setWordWrap(True)
            warning.setStyleSheet("font-weight: 600")
            layout.addWidget(warning)

        self.feedback_label = SemanticLabel(tone="safety")
        self.feedback_label.hide()
        layout.addWidget(self.feedback_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setEnabled(bool(self._cameras))
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        if not self.name_edit.text().strip():
            self._show_feedback(tr("Enter a setup name."))
            return
        if self.camera_combo.currentData() is None:
            self._show_feedback(tr("Select a camera."))
            return
        self.feedback_label.hide()
        self.accept()

    def _show_feedback(self, message: str) -> None:
        self.feedback_label.setText(message)
        self.feedback_label.show()

    def setup_profile(self) -> SetupProfile:
        camera = self.camera_combo.currentData()
        if not isinstance(camera, CameraDescriptor):
            raise RuntimeError("No camera was selected.")
        return SetupProfile(
            name=self.name_edit.text().strip(),
            camera=camera.model_copy(deep=True),
        )


class CalibrationStepSelectionDialog(QDialog):
    def __init__(
        self,
        profile: CalibrationProfile,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.profile = profile
        self._baseline_confirmation_pending = False
        self.setWindowTitle(tr("Recalibrate step"))
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        explanation = QLabel(
            tr(
                "Choose one calibration stage to record again. An unwanted-"
                "posture stage first checks the saved good baseline. Replacing "
                "the good baseline clears every unwanted-posture example "
                "because those examples were learned relative to it."
            )
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        form = QFormLayout()
        self.step_combo = QComboBox()
        for step in CALIBRATION_STEPS:
            if step.category is None:
                status = tr("saved baseline")
            else:
                calibration = profile.categories.get(step.category)
                if calibration is None:
                    status = tr("not learned")
                elif calibration.enabled:
                    status = tr("learned")
                else:
                    status = tr("needs a clearer example")
            self.step_combo.addItem(
                tr("{posture} — {status}", posture=tr(step.title), status=status),
                step.key,
            )
        form.addRow(tr("Calibration step"), self.step_combo)
        layout.addLayout(form)

        self.reference_image = CalibrationStageImage()
        layout.addWidget(self.reference_image)

        self.description = SemanticLabel(tone="info")
        layout.addWidget(self.description)
        self.baseline_warning = SemanticLabel(
            tr(
                "Replacing the good baseline removes every learned "
                "unwanted-posture example for this setup. You will need "
                "to recalibrate those steps individually. Continue?"
            ),
            tone="safety",
        )
        self.baseline_warning.hide()
        layout.addWidget(self.baseline_warning)
        self.step_combo.currentIndexChanged.connect(
            self._update_description
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.confirm_button = buttons.button(
            QDialogButtonBox.StandardButton.Ok
        )
        self.confirm_button.setText(
            tr("Recalibrate step")
        )
        buttons.accepted.connect(self._confirm_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        layout.addStretch(1)
        self._update_description()

    def _update_description(self) -> None:
        self._baseline_confirmation_pending = False
        self.baseline_warning.hide()
        self.confirm_button.setText(tr("Recalibrate step"))
        step = self._current_step()
        if step is None:
            self.reference_image.hide()
            self.description.clear()
            return
        self.reference_image.set_step(step)
        detail = tr(step.instructions)
        if step.category is None:
            detail += "\n\n" + tr(
                "Replacing the good baseline removes all learned unwanted-"
                "posture examples."
            )
        else:
            detail += "\n\n" + tr(
                "Only this unwanted posture will be replaced; the other "
                "examples stay unchanged."
            )
        self.description.setText(detail)

    def _confirm_selection(self) -> None:
        step = self._current_step()
        if step is None:
            return
        if (
            step.category is None
            and not self._baseline_confirmation_pending
        ):
            self._baseline_confirmation_pending = True
            self.baseline_warning.show()
            self.confirm_button.setText(tr("Recalibrate good baseline"))
            return
        self.accept()

    def selected_step(self) -> CalibrationStep:
        step = self._current_step()
        if step is None:
            raise RuntimeError("No calibration step was selected.")
        return step

    def _current_step(self) -> CalibrationStep | None:
        key = self.step_combo.currentData()
        return next(
            (step for step in CALIBRATION_STEPS if step.key == key),
            None,
        )


class CalibrationDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        steps: list[CalibrationStep] | None = None,
        base_profile: CalibrationProfile | None = None,
    ) -> None:
        super().__init__(parent)
        self.steps = [
            step.model_copy(deep=True)
            for step in (steps or CALIBRATION_STEPS)
        ]
        baseline_steps = [
            step for step in self.steps if step.category is None
        ]
        if len(baseline_steps) != 1 or not baseline_steps[0].required:
            raise ValueError(
                "Calibration requires exactly one required good-baseline "
                "stage."
            )
        unwanted_steps = [
            step for step in self.steps if step.category is not None
        ]
        if base_profile is not None and (
            len(unwanted_steps) != 1 or not unwanted_steps[0].required
        ):
            raise ValueError(
                "Incremental calibration requires one selected, required "
                "unwanted-posture stage."
            )
        self.base_profile = base_profile
        self.profile: CalibrationProfile | None = None
        self.completion_notice: str | None = None
        self._step_index = 0
        self._phase = "idle"
        self._deadline = 0.0
        self._current_samples: list[FeatureFrame] = []
        self._samples: dict[str, list[FeatureFrame]] = defaultdict(list)
        self._latest_quality = 0.0
        self._stage_status = ["pending" for _step in self.steps]
        self._finished = False

        if base_profile is not None:
            window_title = tr("Recalibrate posture step")
        elif len(self.steps) == 1 and self.steps[0].category is None:
            window_title = tr("Recalibrate good baseline")
        else:
            window_title = tr("Calibrate this setup")
        self.setWindowTitle(window_title)
        self.setMinimumSize(360, 620)
        outer_layout = QVBoxLayout(self)

        stage_group = QGroupBox(tr("Calibration stages"))
        stage_layout = QVBoxLayout(stage_group)
        stage_help = QLabel(
            tr("The highlighted row is the only pose being recorded.")
        )
        stage_help.setWordWrap(True)
        stage_layout.addWidget(stage_help)
        self.stage_list = QListWidget()
        self.stage_list.setMaximumHeight(190)
        self.stage_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.stage_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        stage_layout.addWidget(self.stage_list)
        outer_layout.addWidget(stage_group)

        content = QWidget()
        layout = QVBoxLayout(content)
        self.step_counter = QLabel()
        self.role_label = SemanticLabel(strong=True)
        self.role_label.setWordWrap(True)
        self.title_label = QLabel()
        title_font = self.title_label.font()
        title_font.setPointSize(title_font.pointSize() + 4)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.reference_image = CalibrationStageImage()
        self.instructions_label = QLabel()
        self.instructions_label.setWordWrap(True)
        self.instructions_label.setMinimumHeight(70)
        self.phase_label = QLabel()
        phase_font = self.phase_label.font()
        phase_font.setBold(True)
        phase_font.setPointSize(phase_font.pointSize() + 2)
        self.phase_label.setFont(phase_font)
        self.quality_label = QLabel(tr("Waiting for clear landmarks..."))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.step_counter)
        layout.addWidget(self.role_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.reference_image)
        layout.addWidget(self.instructions_label)
        layout.addWidget(self.phase_label)
        layout.addWidget(self.quality_label)
        layout.addWidget(self.progress)
        self.feedback_label = SemanticLabel(tone="safety")
        self.feedback_label.hide()
        layout.addWidget(self.feedback_label)

        safety = SemanticLabel(
            tr(
                "Calibration is a personal visual baseline, not a medical "
                "test. Never force an uncomfortable posture."
            ),
            tone="info",
        )
        layout.addWidget(safety)
        layout.addStretch()

        controls = QHBoxLayout()
        self.start_button = QPushButton(tr("Start sample"))
        self.skip_button = QPushButton(tr("Skip this example"))
        self.cancel_button = QPushButton(tr("Cancel"))
        self.start_button.clicked.connect(self._start_sample)
        self.skip_button.clicked.connect(self._skip_step)
        self.cancel_button.clicked.connect(self.reject)
        controls.addWidget(self.start_button)
        controls.addWidget(self.skip_button)
        controls.addStretch()
        controls.addWidget(self.cancel_button)
        layout.addLayout(controls)
        outer_layout.addWidget(content, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._show_step()

    def done(self, result: int) -> None:
        self._finished = True
        self.timer.stop()
        super().done(result)

    def ingest(self, frame: FeatureFrame) -> None:
        if self._step_index >= len(self.steps):
            return
        step = self.steps[self._step_index]
        quality = (
            frame.overall_quality
            if step.category is None
            else frame.category_quality.get(step.category, 0.0)
        )
        self._latest_quality = quality
        if self._phase == "capturing" and quality >= 0.70:
            self._current_samples.append(frame)

    def _show_step(self) -> None:
        step = self.steps[self._step_index]
        self.step_counter.setText(
            tr(
                "Step {current} of {total}",
                current=self._step_index + 1,
                total=len(self.steps),
            )
        )
        if step.category is None:
            self.role_label.setText(
                tr(
                    "GOOD BASELINE — sit in the comfortable posture you want "
                    "Vulture to treat as your normal reference."
                )
            )
            self.role_label.set_semantic_tone("good", strong=True)
            role_name = tr("GOOD BASELINE")
        else:
            self.role_label.setText(
                tr(
                    "UNWANTED POSTURE EXAMPLE — demonstrate only: {posture}. "
                    "Do not combine it with a different unwanted pose.",
                    posture=tr(step.title),
                )
            )
            self.role_label.set_semantic_tone("unwanted", strong=True)
            role_name = tr("UNWANTED POSTURE")
        self.title_label.setText(tr(step.title))
        self.reference_image.set_step(step)
        self.instructions_label.setText(tr(step.instructions))
        self.phase_label.setText(
            tr("READY — {role}", role=role_name)
        )
        self.progress.setValue(0)
        self.start_button.setText(tr("Start sample"))
        self.start_button.setEnabled(True)
        self.skip_button.setEnabled(not step.required)
        self.feedback_label.clear()
        self.feedback_label.hide()
        self._phase = "idle"
        self._current_samples = []
        self._refresh_stage_list()

    def _refresh_stage_list(self) -> None:
        self.stage_list.clear()
        for index, step in enumerate(self.steps):
            status = self._stage_status[index]
            if (
                index == self._step_index
                and self._step_index < len(self.steps)
                and status == "retry"
            ):
                marker = "!"
                status_text = tr("RETRY")
            elif (
                index == self._step_index
                and self._step_index < len(self.steps)
            ):
                marker = "▶"
                status_text = tr("CURRENT")
            elif status == "recorded":
                marker = "✓"
                status_text = tr("RECORDED")
            elif status == "skipped":
                marker = "–"
                status_text = tr("SKIPPED")
            elif status == "retry":
                marker = "!"
                status_text = tr("RETRY")
            else:
                marker = "○"
                status_text = tr("PENDING")
            role = tr("GOOD") if step.category is None else tr("UNWANTED")
            requirement = tr("required") if step.required else tr("optional")
            item = QListWidgetItem(
                tr(
                    "{marker} {index}. {posture}\n"
                    "   {role} • {requirement} • {status}",
                    marker=marker,
                    index=index + 1,
                    posture=tr(step.title),
                    role=role,
                    requirement=requirement,
                    status=status_text,
                )
            )
            if status == "retry":
                item.setBackground(QColor("#fed7d7"))
                item.setForeground(QColor("#742a2a"))
            elif (
                index == self._step_index
                and self._step_index < len(self.steps)
            ):
                item.setBackground(QColor("#3182ce"))
                item.setForeground(QColor("white"))
            elif status == "recorded":
                item.setBackground(QColor("#c6f6d5"))
                item.setForeground(QColor("#22543d"))
            elif status == "skipped":
                item.setBackground(QColor("#e2e8f0"))
                item.setForeground(QColor("#4a5568"))
            self.stage_list.addItem(item)

    def _start_sample(self) -> None:
        if self._phase != "idle":
            return
        self._current_samples = []
        self._phase = "preparing"
        self._deadline = time.monotonic() + 3.0
        self.start_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.phase_label.setText(
            tr("GET READY — {role}", role=self._current_role_name())
        )

    def _skip_step(self) -> None:
        step = self.steps[self._step_index]
        if step.required:
            return
        self._stage_status[self._step_index] = "skipped"
        self._advance()

    def _tick(self) -> None:
        quality_percent = round(self._latest_quality * 100)
        if self._phase == "idle":
            self.quality_label.setText(
                tr(
                    "Current tracking quality: {quality}% (70% required)",
                    quality=quality_percent,
                )
            )
            return

        remaining = self._deadline - time.monotonic()
        if self._phase == "preparing":
            self.quality_label.setText(
                tr(
                    "Recording starts in {seconds}...",
                    seconds=max(1, math.ceil(remaining)),
                )
            )
            if remaining <= 0:
                step = self.steps[self._step_index]
                self._phase = "capturing"
                self._deadline = time.monotonic() + step.capture_seconds
                self.phase_label.setText(
                    tr(
                        "RECORDING NOW — {role}",
                        role=self._current_role_name(),
                    )
                )
            return

        if self._phase == "capturing":
            step = self.steps[self._step_index]
            elapsed = step.capture_seconds - max(remaining, 0)
            self.progress.setValue(
                min(100, round(elapsed / step.capture_seconds * 100))
            )
            self.quality_label.setText(
                tr(
                    "Recording clear samples: {count}",
                    count=len(self._current_samples),
                )
            )
            if remaining <= 0:
                self._finish_sample()

    def _finish_sample(self) -> None:
        step = self.steps[self._step_index]
        minimum_samples = 30 if step.category is None else 15
        if len(self._current_samples) < minimum_samples:
            self._phase = "idle"
            self._stage_status[self._step_index] = "retry"
            self.progress.setValue(0)
            self.start_button.setText(tr("Retry sample"))
            self.start_button.setEnabled(True)
            self.skip_button.setEnabled(not step.required)
            self.phase_label.setText(
                tr("RETRY — {role}", role=self._current_role_name())
            )
            self.quality_label.setText(
                (
                    tr(
                        "Not enough clear frames were visible. Reposition the "
                        "camera and retry this required stage."
                    )
                    if step.required
                    else tr(
                        "Not enough clear frames were visible. Reposition the "
                        "camera or skip this optional example."
                    )
                )
            )
            self._refresh_stage_list()
            return
        self._samples[step.key] = list(self._current_samples)
        self._stage_status[self._step_index] = "recorded"
        self._advance()

    def _advance(self) -> None:
        self._step_index += 1
        if self._step_index < len(self.steps):
            self._show_step()
            return
        self._refresh_stage_list()
        self._fit_profile()

    def _fit_profile(self) -> None:
        self._phase = "idle"
        self.timer.stop()
        good_step = next(
            step for step in self.steps if step.category is None
        )
        bad_samples = {
            step.category: self._samples[step.key]
            for step in self.steps
            if step.category is not None and self._samples.get(step.key)
        }
        try:
            fitter = CalibrationFitter()
            if self.base_profile is None:
                self.profile = fitter.fit(
                    self._samples[good_step.key],
                    bad_samples,
                )
            else:
                category = next(iter(bad_samples), None)
                if category is None:
                    raise CalibrationError(
                        tr(
                            "Record the selected unwanted posture before "
                            "saving."
                        )
                    )
                self.profile = fitter.fit_category_for_profile(
                    self.base_profile,
                    self._samples[good_step.key],
                    bad_samples[category],
                    category,
                )
        except CalibrationError as error:
            if self._finished:
                return
            self._step_index = 0
            self._samples.clear()
            self._stage_status = ["pending" for _step in self.steps]
            self._show_step()
            self.feedback_label.setText(
                tr("Calibration incomplete") + ": " + str(error)
            )
            self.feedback_label.show()
            self.timer.start()
            return

        if self.base_profile is None:
            disabled = [
                tr(
                    POSTURE_TITLES.get(
                        category.value,
                        category.value.replace("_", " ").title(),
                    )
                )
                for category, item in self.profile.categories.items()
                if not item.enabled
            ]
            unavailable = [
                tr(
                    POSTURE_TITLES.get(
                        category.value,
                        category.value.replace("_", " ").title(),
                    )
                )
                for category in bad_samples
                if category not in self.profile.categories
            ]
            if disabled or unavailable:
                self.completion_notice = tr(
                    "The camera could not reliably separate these examples, "
                    "so they remain disabled for this setup: {postures}. "
                    "General deviation reminders remain available.",
                    postures=", ".join(disabled + unavailable),
                )
        if not self._finished:
            self.accept()

    def _current_role_name(self) -> str:
        step = self.steps[self._step_index]
        return (
            tr("GOOD BASELINE")
            if step.category is None
            else tr(
                "UNWANTED: {posture}",
                posture=tr(step.title).upper(),
            )
        )


class SettingsDialog(QDialog):
    def __init__(
        self,
        policy: AlertPolicy,
        preferences: ExercisePreferences,
        history_preferences: HistoryPreferences,
        language: InterfaceLanguage,
        parent: QWidget | None = None,
        *,
        start_at_login_enabled: bool = False,
        startup_setting_available: bool = True,
        startup_setting_error: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Vulture settings"))
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        interface_group = QGroupBox(tr("Interface"))
        interface_group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        interface_form = QFormLayout(interface_group)
        self.language_combo = QComboBox()
        for choice, label in LANGUAGE_NAMES.items():
            self.language_combo.addItem(label, choice.value)
        selected_index = self.language_combo.findData(language.value)
        if selected_index >= 0:
            self.language_combo.setCurrentIndex(selected_index)
        interface_form.addRow(tr("Language"), self.language_combo)
        self.start_at_login = QCheckBox(
            tr("Start Vulture when I sign in")
        )
        self.start_at_login.setChecked(start_at_login_enabled)
        self.start_at_login.setEnabled(startup_setting_available)
        if not startup_setting_available:
            self.start_at_login.setToolTip(
                tr(
                    "The system startup setting is unavailable on this "
                    "computer."
                )
            )
        interface_form.addRow(self.start_at_login)
        if startup_setting_error:
            startup_error = SemanticLabel(
                startup_setting_error,
                tone="safety",
            )
            interface_form.addRow(startup_error)
        layout.addWidget(interface_group)

        alert_group = QGroupBox(tr("Reminder policy"))
        alert_group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        alert_form = QFormLayout(alert_group)
        self.warning_seconds = QDoubleSpinBox()
        self.warning_seconds.setRange(2, 300)
        self.warning_seconds.setValue(policy.warning_after_seconds)
        self.warning_seconds.setSuffix(tr(" seconds"))
        self.alert_seconds = QDoubleSpinBox()
        self.alert_seconds.setRange(5, 900)
        self.alert_seconds.setValue(policy.alert_after_seconds)
        self.alert_seconds.setSuffix(tr(" seconds"))
        self.transition_buffer_seconds = QDoubleSpinBox()
        self.transition_buffer_seconds.setRange(0, 30)
        self.transition_buffer_seconds.setValue(
            policy.posture_transition_buffer_seconds
        )
        self.transition_buffer_seconds.setSuffix(tr(" seconds"))
        self.repeat_count = QSpinBox()
        self.repeat_count.setRange(2, 20)
        self.repeat_count.setValue(policy.repeated_reminders_for_break)
        self.repeat_window = QSpinBox()
        self.repeat_window.setRange(5, 120)
        self.repeat_window.setValue(policy.repeated_reminder_window_minutes)
        self.repeat_window.setSuffix(tr(" minutes"))
        self.sedentary_minutes = QSpinBox()
        self.sedentary_minutes.setRange(20, 180)
        self.sedentary_minutes.setValue(policy.sedentary_break_minutes)
        self.sedentary_minutes.setSuffix(tr(" minutes"))
        alert_form.addRow(tr("Show warning after"), self.warning_seconds)
        alert_form.addRow(tr("Notify after"), self.alert_seconds)
        alert_form.addRow(
            tr("Posture-change buffer"),
            self.transition_buffer_seconds,
        )
        alert_form.addRow(
            tr("Offer exercise after reminders"),
            self.repeat_count,
        )
        alert_form.addRow(tr("Count reminders within"), self.repeat_window)
        alert_form.addRow(
            tr("Independent movement break"),
            self.sedentary_minutes,
        )
        layout.addWidget(alert_group)

        exercise_group = QGroupBox(tr("Exercise accessibility"))
        exercise_group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        exercise_layout = QVBoxLayout(exercise_group)
        self.seated_only = QCheckBox(tr("Only show seated movements"))
        self.seated_only.setChecked(preferences.seated_only)
        self.allow_balance = QCheckBox(
            tr("Allow movements that require standing balance")
        )
        self.allow_balance.setChecked(preferences.allow_balance_exercises)
        self.allow_strength = QCheckBox(
            tr("Allow light strength movements such as sit-to-stand")
        )
        self.allow_strength.setChecked(preferences.allow_strength_exercises)
        exercise_layout.addWidget(self.seated_only)
        exercise_layout.addWidget(self.allow_balance)
        exercise_layout.addWidget(self.allow_strength)
        layout.addWidget(exercise_group)

        history_group = QGroupBox(tr("Workday history"))
        history_group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        history_layout = QFormLayout(history_group)
        self.save_history = QCheckBox(
            tr("Save local posture categories and durations")
        )
        self.save_history.setChecked(history_preferences.enabled)
        self.history_retention_days = QSpinBox()
        self.history_retention_days.setRange(1, 365)
        self.history_retention_days.setValue(
            history_preferences.retention_days
        )
        self.history_retention_days.setSuffix(tr(" days"))
        self.history_retention_days.setEnabled(
            history_preferences.enabled
        )
        self.save_history.toggled.connect(
            self.history_retention_days.setEnabled
        )
        history_layout.addRow(self.save_history)
        history_layout.addRow(
            tr("Keep summaries for"),
            self.history_retention_days,
        )
        layout.addWidget(history_group)

        layout.addStretch(1)

        note = SemanticLabel(
            tr(
                "The repeated-reminder rule is a configurable product choice, "
                "not a clinical recommendation. Workday history contains "
                "labels and durations only—never camera frames or landmark "
                "coordinates."
            ),
            tone="info",
        )
        layout.addWidget(note)

        self.feedback_label = SemanticLabel(tone="safety")
        self.feedback_label.setAccessibleName(tr("Invalid reminder policy"))
        self.feedback_label.hide()
        layout.addWidget(self.feedback_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._policy = policy
        self._preferences = preferences
        self._history_preferences = history_preferences
        self._language = language
        self._startup_setting_available = startup_setting_available

    def _validate_and_accept(self) -> None:
        try:
            self._policy = AlertPolicy(
                minimum_tracking_quality=self._policy.minimum_tracking_quality,
                warning_after_seconds=self.warning_seconds.value(),
                alert_after_seconds=self.alert_seconds.value(),
                clear_after_seconds=self._policy.clear_after_seconds,
                posture_transition_buffer_seconds=(
                    self.transition_buffer_seconds.value()
                ),
                notification_cooldown_seconds=(
                    self._policy.notification_cooldown_seconds
                ),
                repeated_reminders_for_break=self.repeat_count.value(),
                repeated_reminder_window_minutes=self.repeat_window.value(),
                exercise_offer_cooldown_minutes=(
                    self._policy.exercise_offer_cooldown_minutes
                ),
                sedentary_break_minutes=self.sedentary_minutes.value(),
            )
        except ValidationError:
            self.feedback_label.setText(
                tr(
                    "The notification delay must be longer than the warning "
                    "delay."
                )
            )
            self.feedback_label.show()
            return
        self._preferences = ExercisePreferences(
            seated_only=self.seated_only.isChecked(),
            allow_balance_exercises=self.allow_balance.isChecked(),
            allow_strength_exercises=self.allow_strength.isChecked(),
            excluded_exercise_ids=self._preferences.excluded_exercise_ids,
        )
        self._history_preferences = HistoryPreferences(
            enabled=self.save_history.isChecked(),
            retention_days=self.history_retention_days.value(),
        )
        self._language = InterfaceLanguage(
            self.language_combo.currentData()
        )
        self.feedback_label.hide()
        self.accept()

    def values(
        self,
    ) -> tuple[
        AlertPolicy,
        ExercisePreferences,
        HistoryPreferences,
        InterfaceLanguage,
        bool | None,
    ]:
        return (
            self._policy,
            self._preferences,
            self._history_preferences,
            self._language,
            (
                self.start_at_login.isChecked()
                if self._startup_setting_available
                else None
            ),
        )


EXERCISE_POSTPONE_MINUTES = 10


class ExerciseOutcome:
    COMPLETED = "completed"
    POSTPONED = "postponed"
    DISMISSED = "dismissed"


class ExerciseDialog(QDialog):
    def __init__(
        self,
        exercise: Exercise,
        catalog: ExerciseCatalog,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.exercise = exercise
        self.catalog = catalog
        self.player: QMediaPlayer | None = None
        self.setWindowTitle(
            tr("Movement break: {exercise}", exercise=exercise.title)
        )
        self.setMinimumSize(500, 600)

        layout = QVBoxLayout(self)
        dose = QLabel(
            tr("<b>Dose:</b> {dose}", dose=exercise.dose)
        )
        dose.setWordWrap(True)
        layout.addWidget(dose)

        media = exercise_media_path(exercise)
        if media is not None:
            video = QVideoWidget()
            video.setMinimumHeight(280)
            layout.addWidget(video)
            self.player = QMediaPlayer(self)
            self.player.setVideoOutput(video)
            self.player.setSource(QUrl.fromLocalFile(str(media)))
            self.player.mediaStatusChanged.connect(self._loop_video)
            self.player.play()

        steps = QTextBrowser()
        steps.setOpenExternalLinks(True)
        steps.setMaximumHeight(170)
        step_html = "".join(
            f"<li>{step}</li>" for step in exercise.steps
        )
        steps.setHtml(f"<ol>{step_html}</ol>")
        layout.addWidget(steps)

        safety = SemanticLabel(
            tr(
                "<b>Safety:</b> {safety}<br><br>{global_safety}",
                safety=exercise.safety,
                global_safety=catalog.global_safety,
            ),
            tone="safety",
        )
        layout.addWidget(safety)

        self.details_toggle = QToolButton()
        self.details_toggle.setText(tr("Sources and medical context"))
        self.details_toggle.setCheckable(True)
        self.details_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.details_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.details_toggle.toggled.connect(
            self._set_details_expanded
        )
        layout.addWidget(self.details_toggle)

        self.details_panel = QWidget()
        details_layout = QVBoxLayout(self.details_panel)
        details_layout.setContentsMargins(0, 0, 0, 0)
        source_map = catalog.source_map()
        self.sources = QTextBrowser()
        self.sources.setOpenExternalLinks(True)
        set_accessible_link_palette(self.sources)
        self.sources.setMaximumHeight(90)
        source_lines = []
        for source_id in exercise.source_ids:
            source = source_map[source_id]
            source_lines.append(
                f'<a href="{source.url}">{source.organization}: '
                f"{source.title}</a>"
            )
        self.sources.setHtml(
            tr(
                "<b>Guidance sources:</b><br>{sources}",
                sources="<br>".join(source_lines),
            )
        )
        details_layout.addWidget(self.sources)

        self.disclaimer = QLabel(catalog.medical_disclaimer)
        self.disclaimer.setWordWrap(True)
        details_layout.addWidget(self.disclaimer)
        self.details_panel.hide()
        layout.addWidget(self.details_panel)

        self.outcome = ExerciseOutcome.POSTPONED
        button_row = QHBoxLayout()
        done_button = QPushButton(tr("Done"))
        done_button.setDefault(True)
        done_button.clicked.connect(self._complete)
        button_row.addWidget(done_button)
        button_row.addStretch(1)
        skip_button = QPushButton(tr("Skip"))
        skip_button.setAutoDefault(False)
        skip_button.clicked.connect(self._skip)
        button_row.addWidget(skip_button)
        postpone_button = QPushButton(tr("Remind me later"))
        postpone_button.setAutoDefault(False)
        postpone_button.clicked.connect(self._postpone)
        button_row.addWidget(postpone_button)
        layout.addLayout(button_row)

    def _set_details_expanded(self, expanded: bool) -> None:
        self.details_panel.setVisible(expanded)
        self.details_toggle.setArrowType(
            Qt.ArrowType.DownArrow
            if expanded
            else Qt.ArrowType.RightArrow
        )
        self.updateGeometry()

    def _complete(self) -> None:
        self.outcome = ExerciseOutcome.COMPLETED
        self.accept()

    def _postpone(self) -> None:
        self.outcome = ExerciseOutcome.POSTPONED
        self.reject()

    def _skip(self) -> None:
        self.outcome = ExerciseOutcome.DISMISSED
        self.reject()

    def _loop_video(self, status: QMediaPlayer.MediaStatus) -> None:
        if (
            self.player is not None
            and status == QMediaPlayer.MediaStatus.EndOfMedia
        ):
            self.player.setPosition(0)
            self.player.play()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.player is not None:
            self.player.stop()
        super().closeEvent(event)

    def done(self, result: int) -> None:
        if self.player is not None:
            self.player.stop()
        super().done(result)


class EvidenceDialog(QDialog):
    def __init__(
        self,
        catalog: ExerciseCatalog,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Evidence and safety"))
        self.setMinimumSize(480, 520)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        set_accessible_link_palette(browser)
        source_html = "".join(
            (
                f'<li><a href="{source.url}">{source.organization}: '
                f"{source.title}</a></li>"
            )
            for source in catalog.sources
        )
        browser.setHtml(
            f"<h2>{tr('Scope')}</h2>"
            "<p>"
            + tr(
                "Vulture compares webcam landmarks with your own calibration. "
                "It does not measure spinal anatomy, diagnose a condition, or "
                "determine whether a posture is medically safe."
            )
            + "</p>"
            f"<h2>{tr('Exercise policy')}</h2>"
            f"<p>{catalog.medical_disclaimer}</p>"
            f"<p>{catalog.global_safety}</p>"
            "<p>"
            + tr(
                "Movement doses are copied or conservatively selected from "
                "the listed authoritative guidance. The trigger timing is an "
                "explicit product setting rather than a clinical prescription."
            )
            + "</p>"
            f"<ul>{source_html}</ul>"
            f"<h2>{tr('Media')}</h2>"
            f"<p>{catalog.media_provenance}</p>"
        )
        layout.addWidget(browser)


class PostureAreaChart(QChartView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(QChart(), parent)
        self._area_series: list[QAreaSeries] = []
        self._boundary_series: list[QLineSeries] = []
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(230)
        self.setAccessibleName(
            tr("Posture over time (15-minute intervals)")
        )
        self.setAccessibleDescription(tr("Tracked posture time"))
        self.chart().setBackgroundVisible(False)
        self.chart().setDropShadowEnabled(False)
        self.chart().legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        self._apply_palette()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_palette()

    def _apply_palette(self) -> None:
        chart = self.chart()
        foreground = self.palette().color(QPalette.ColorRole.WindowText)
        grid = self.palette().color(QPalette.ColorRole.Mid)
        chart.setTitleBrush(QBrush(foreground))
        chart.legend().setLabelColor(foreground)
        for axis in chart.axes():
            axis.setLabelsColor(foreground)
            axis.setTitleBrush(QBrush(foreground))
            axis.setLinePenColor(foreground)
            axis.setGridLineColor(grid)

    def clear(self) -> None:
        chart = self.chart()
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)
            axis.deleteLater()
        self._area_series.clear()
        self._boundary_series.clear()
        chart.setTitle("")
        chart.legend().setVisible(False)

    def set_summary(self, summary: DailyPostureSummary) -> None:
        self.clear()
        chart = self.chart()
        area_data = build_posture_area_data(summary)
        if area_data is None:
            chart.setTitle(tr("No tracked posture data for this day."))
            return

        x_values = (
            area_data.start_hour,
            *area_data.bucket_hours,
            area_data.end_hour,
        )
        lower_values = [0.0] * len(x_values)
        area_series: list[QAreaSeries] = []
        for posture, title in SUMMARY_POSTURES:
            posture_minutes = area_data.minutes_by_posture[posture]
            values = (
                posture_minutes[0],
                *posture_minutes,
                posture_minutes[-1],
            )
            upper_values = [
                lower + value
                for lower, value in zip(
                    lower_values,
                    values,
                    strict=True,
                )
            ]
            lower_series = QLineSeries()
            upper_series = QLineSeries()
            for hour, lower, upper in zip(
                x_values,
                lower_values,
                upper_values,
                strict=True,
            ):
                lower_series.append(hour, lower)
                upper_series.append(hour, upper)

            color = QColor(SUMMARY_POSTURE_COLORS[posture])
            area = QAreaSeries(upper_series, lower_series)
            area.setName(tr(title))
            area.setBrush(color)
            area.setPen(QPen(color.darker(115), 1))
            area.setOpacity(0.86)
            chart.addSeries(area)
            area_series.append(area)
            self._area_series.append(area)
            self._boundary_series.extend((lower_series, upper_series))
            lower_values = upper_values

        x_axis = QCategoryAxis()
        x_axis.setTitleText(tr("Time of day"))
        x_axis.setRange(area_data.start_hour, area_data.end_hour)
        x_axis.setStartValue(area_data.start_hour)
        x_axis.setLabelsPosition(
            QCategoryAxis.AxisLabelsPosition.AxisLabelsPositionOnValue
        )
        hour_span = round(area_data.end_hour - area_data.start_hour)
        label_step = max(1, math.ceil(hour_span / 6))
        label_hours = list(
            range(
                round(area_data.start_hour),
                round(area_data.end_hour) + 1,
                label_step,
            )
        )
        if label_hours[-1] != round(area_data.end_hour):
            label_hours.append(round(area_data.end_hour))
        for hour in label_hours:
            x_axis.append(f"{hour:02d}:00", hour)
        y_axis = QValueAxis()
        y_axis.setTitleText(tr("Tracked minutes"))
        y_axis.setRange(0, SUMMARY_CHART_BUCKET_SECONDS / 60)
        y_axis.setTickCount(4)
        y_axis.setLabelFormat("%.0f")

        chart.addAxis(x_axis, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(y_axis, Qt.AlignmentFlag.AlignLeft)
        for area in area_series:
            area.attachAxis(x_axis)
            area.attachAxis(y_axis)
        chart.legend().setVisible(True)
        self._apply_palette()


class WorkdaySummaryDialog(QDialog):
    def __init__(
        self,
        summary_provider: Callable[[date], DailyPostureSummary],
        delete_day: Callable[[date], None],
        delete_all: Callable[[], None],
        setup_names: dict[str, str],
        recording_enabled: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._summary_provider = summary_provider
        self._delete_day_callback = delete_day
        self._delete_all_callback = delete_all
        self._setup_names = setup_names
        self._pending_delete: tuple[str, date | None] | None = None
        self.setWindowTitle(tr("Workday posture summary"))
        self.setMinimumSize(560, 650)

        layout = QVBoxLayout(self)
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel(tr("Workday")))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.setMinimumDate(QDate.currentDate().addDays(-365))
        self.date_edit.dateChanged.connect(lambda _value: self.refresh())
        top_row.addWidget(self.date_edit)
        refresh_button = QPushButton(tr("Refresh"))
        refresh_button.clicked.connect(self.refresh)
        top_row.addWidget(refresh_button)
        top_row.addStretch()
        layout.addLayout(top_row)

        self.recording_label = SemanticLabel(
            tr("Daily history recording is enabled.")
            if recording_enabled
            else tr(
                "Daily history recording is disabled; saved days remain "
                "viewable."
            ),
            tone="info",
        )
        layout.addWidget(self.recording_label)

        self.overview_label = QLabel()
        overview_font = self.overview_label.font()
        overview_font.setBold(True)
        self.overview_label.setFont(overview_font)
        layout.addWidget(self.overview_label)

        self.empty_state_container = QWidget()
        empty_state_layout = QVBoxLayout(self.empty_state_container)
        empty_state_layout.setContentsMargins(0, 0, 0, 0)
        empty_state_layout.addStretch(1)
        self._empty_state_text = tr(
            "<b>No posture history for this day</b><br>"
            "Leave tracking running to build a timeline. Only posture "
            "labels and durations are stored."
        )
        self.empty_state = SemanticLabel(
            self._empty_state_text,
            tone="info",
        )
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.setMinimumWidth(380)
        self.empty_state.setMaximumWidth(460)
        empty_state_layout.addWidget(
            self.empty_state,
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        empty_state_layout.addStretch(1)
        layout.addWidget(self.empty_state_container, 1)

        self.totals_group = QGroupBox(tr("Tracked posture time"))
        totals_layout = QGridLayout(self.totals_group)
        self.total_bars: dict[str, QProgressBar] = {}
        self.total_labels: dict[str, QLabel] = {}
        for row, (posture, title) in enumerate(SUMMARY_POSTURES):
            totals_layout.addWidget(QLabel(tr(title)), row, 0)
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setTextVisible(False)
            totals_layout.addWidget(bar, row, 1)
            value_label = QLabel(tr("{seconds}s", seconds=0))
            value_label.setMinimumWidth(120)
            value_label.setAlignment(
                Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignVCenter
            )
            totals_layout.addWidget(value_label, row, 2)
            self.total_bars[posture] = bar
            self.total_labels[posture] = value_label
        totals_layout.setColumnStretch(1, 1)
        layout.addWidget(self.totals_group)

        self.chart_group = QGroupBox(
            tr("Posture over time (15-minute intervals)")
        )
        chart_layout = QVBoxLayout(self.chart_group)
        self.posture_chart = PostureAreaChart()
        chart_layout.addWidget(self.posture_chart)
        layout.addWidget(self.chart_group)

        self.timeline_group = QGroupBox(tr("Timeline"))
        timeline_layout = QVBoxLayout(self.timeline_group)
        self.timeline = QTableWidget(0, 5)
        self.timeline.setHorizontalHeaderLabels(
            [
                tr("Started"),
                tr("Duration"),
                tr("Posture"),
                tr("Highest reminder stage"),
                tr("Setup"),
            ]
        )
        self.timeline.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.timeline.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.timeline.setAlternatingRowColors(True)
        header = self.timeline.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        timeline_layout.addWidget(self.timeline)
        layout.addWidget(self.timeline_group, 1)

        controls = QHBoxLayout()
        self.delete_day_button = QPushButton(tr("Delete this day"))
        self.delete_day_button.clicked.connect(self._delete_selected_day)
        self.delete_all_button = QPushButton(tr("Delete all history"))
        self.delete_all_button.clicked.connect(self._delete_all_history)
        controls.addWidget(self.delete_day_button)
        controls.addWidget(self.delete_all_button)
        controls.addStretch()
        layout.addLayout(controls)

        self.delete_confirmation = SemanticLabel(tone="safety")
        self.delete_confirmation.hide()
        layout.addWidget(self.delete_confirmation)
        confirmation_controls = QHBoxLayout()
        confirmation_controls.addStretch()
        self.cancel_delete_button = QPushButton(tr("Cancel"))
        self.cancel_delete_button.clicked.connect(
            self._cancel_history_delete
        )
        self.cancel_delete_button.hide()
        self.confirm_delete_button = QPushButton(tr("Delete this day"))
        self.confirm_delete_button.clicked.connect(
            self._confirm_history_delete
        )
        self.confirm_delete_button.hide()
        confirmation_controls.addWidget(self.cancel_delete_button)
        confirmation_controls.addWidget(self.confirm_delete_button)
        layout.addLayout(confirmation_controls)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(15_000)
        self.refresh_timer.timeout.connect(self._refresh_today)
        self.refresh_timer.start()
        self._selected_day_has_data = False
        self.refresh()

    def selected_date(self) -> date:
        selected = self.date_edit.date()
        return date(selected.year(), selected.month(), selected.day())

    def refresh(self) -> None:
        try:
            summary = self._summary_provider(self.selected_date())
        except HistoryStorageError as error:
            self._selected_day_has_data = False
            self.overview_label.hide()
            self.empty_state.set_semantic_tone("safety")
            self.empty_state.setText(
                tr(
                    "Could not read the workday summary: {error}",
                    error=error,
                )
            )
            self.empty_state_container.show()
            self.totals_group.hide()
            self.chart_group.hide()
            self.timeline_group.hide()
            self.delete_day_button.setEnabled(False)
            self.posture_chart.clear()
            self.timeline.setRowCount(0)
            return

        tracked = summary.tracked_seconds
        self.posture_chart.set_summary(summary)
        self.empty_state.set_semantic_tone("info")
        self.empty_state.setText(self._empty_state_text)
        self._selected_day_has_data = tracked > 0 or bool(summary.episodes)
        self.empty_state_container.setVisible(
            not self._selected_day_has_data
        )
        self.totals_group.setVisible(self._selected_day_has_data)
        self.chart_group.setVisible(self._selected_day_has_data)
        self.timeline_group.setVisible(self._selected_day_has_data)
        self.overview_label.setVisible(self._selected_day_has_data)
        if self._pending_delete is None:
            self.delete_day_button.setEnabled(self._selected_day_has_data)
        self.overview_label.setText(
            tr(
                "Tracked: {duration}    Notifications: {count}",
                duration=format_duration(tracked),
                count=summary.reminder_count,
            )
        )
        for posture, _title in SUMMARY_POSTURES:
            duration = summary.totals.get(posture, 0.0)
            percentage = duration / tracked * 100 if tracked > 0 else 0.0
            self.total_bars[posture].setValue(round(percentage * 10))
            self.total_labels[posture].setText(
                tr(
                    "{duration}  ({percentage}%)",
                    duration=format_duration(duration),
                    percentage=QLocale().toString(percentage, "f", 1),
                )
            )

        self.timeline.setRowCount(len(summary.episodes))
        for row, episode in enumerate(summary.episodes):
            local_timezone = timezone(
                timedelta(minutes=episode.utc_offset_minutes)
            )
            local_start = episode.started_at.astimezone(local_timezone)
            values = (
                local_start.strftime("%H:%M:%S"),
                format_duration(episode.duration_seconds),
                tr(
                    POSTURE_TITLES.get(
                        episode.posture,
                        episode.posture.replace("_", " ").title(),
                    )
                ),
                tr(
                    REMINDER_STAGE_TITLES.get(
                        episode.peak_state,
                        episode.peak_state.value.replace("_", " ").title(),
                    )
                ),
                self._setup_names.get(
                    episode.setup_id,
                    tr("Deleted setup"),
                ),
            )
            for column, value in enumerate(values):
                self.timeline.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )

    def _refresh_today(self) -> None:
        if self.selected_date() == datetime.now().astimezone().date():
            self.refresh()

    def _delete_selected_day(self) -> None:
        selected_date = self.selected_date()
        self._pending_delete = ("day", selected_date)
        self.delete_confirmation.setAccessibleName(
            tr("Delete workday summary")
        )
        self.delete_confirmation.setText(
            tr(
                "Delete all saved posture episodes and reminders for {date}?",
                date=selected_date.isoformat(),
            )
        )
        self._show_delete_confirmation()

    def _delete_all_history(self) -> None:
        self._pending_delete = ("all", None)
        self.delete_confirmation.setAccessibleName(
            tr("Delete all workday history")
        )
        self.delete_confirmation.setText(
            tr(
                "Delete every saved posture episode and reminder? This cannot "
                "be undone."
            )
        )
        self._show_delete_confirmation()

    def _show_delete_confirmation(self) -> None:
        self.delete_confirmation.show()
        self.cancel_delete_button.setText(tr("Cancel"))
        self.cancel_delete_button.show()
        self.confirm_delete_button.setText(
            tr("Delete all history")
            if self._pending_delete == ("all", None)
            else tr("Delete this day")
        )
        self.confirm_delete_button.show()
        self.delete_day_button.setEnabled(False)
        self.delete_all_button.setEnabled(False)

    def _cancel_history_delete(self) -> None:
        self._pending_delete = None
        self.delete_confirmation.hide()
        self.cancel_delete_button.hide()
        self.confirm_delete_button.hide()
        self.delete_day_button.setEnabled(self._selected_day_has_data)
        self.delete_all_button.setEnabled(True)

    def _confirm_history_delete(self) -> None:
        pending = self._pending_delete
        if pending is None:
            return
        try:
            action, selected_date = pending
            if action == "day" and selected_date is not None:
                self._delete_day_callback(selected_date)
            elif action == "all":
                self._delete_all_callback()
            self.refresh()
            self._cancel_history_delete()
        except HistoryStorageError as error:
            self._pending_delete = None
            self.delete_confirmation.setText(
                f"{tr('Could not delete history')}: {error}"
            )
            self.confirm_delete_button.hide()
            self.cancel_delete_button.setText(tr("Close"))


class MainWindow(QMainWindow):
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

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        self.setCentralWidget(central)

        self.command_bar = QToolBar()
        self.command_bar.setMovable(False)
        self.command_bar.setFloatable(False)
        self.command_bar.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        self.command_bar.setAccessibleName(tr("Camera setup controls"))

        setup_control = QWidget()
        setup_control.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        setup_row = QHBoxLayout(setup_control)
        setup_row.setContentsMargins(0, 0, 6, 0)
        setup_row.addWidget(QLabel(tr("Setup")))
        self.setup_combo = QComboBox()
        self.setup_combo.setMinimumWidth(180)
        self.setup_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setup_combo.currentIndexChanged.connect(self._setup_changed)
        setup_row.addWidget(self.setup_combo, 1)
        self.command_bar.addWidget(setup_control)
        self.command_bar.addSeparator()

        self.add_setup_command = QAction(tr("Add setup"), self)
        self.add_setup_command.triggered.connect(self._add_setup)
        self.command_bar.addAction(self.add_setup_command)
        self.pause_command = QAction(
            tr("Release camera")
            if self._tracking_enabled
            else tr("Resume tracking"),
            self,
        )
        self.pause_command.triggered.connect(self._toggle_tracking)
        self.command_bar.addAction(self.pause_command)
        self.command_bar.addSeparator()
        self.calibrate_command = QAction(tr("Calibrate"), self)
        self.calibrate_command.triggered.connect(self._calibrate)
        self.command_bar.addAction(self.calibrate_command)
        self.recalibrate_step_command = QAction(
            tr("Recalibrate step"),
            self,
        )
        self.recalibrate_step_command.setToolTip(
            tr(
                "Record the good baseline or one unwanted-posture stage again."
            )
        )
        self.recalibrate_step_command.triggered.connect(
            self._recalibrate_step
        )
        self.command_bar.addAction(self.recalibrate_step_command)
        self.settings_command = QAction(tr("Settings"), self)
        self.settings_command.triggered.connect(self._show_settings)
        self.command_bar.addAction(self.settings_command)

        self.add_setup_button = self.command_bar.widgetForAction(
            self.add_setup_command
        )
        self.pause_button = self.command_bar.widgetForAction(
            self.pause_command
        )
        self.calibrate_button = self.command_bar.widgetForAction(
            self.calibrate_command
        )
        self.recalibrate_step_button = self.command_bar.widgetForAction(
            self.recalibrate_step_command
        )
        self.settings_button = self.command_bar.widgetForAction(
            self.settings_command
        )
        layout.addWidget(self.command_bar)

        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setChildrenCollapsible(False)
        camera_workspace = QWidget()
        camera_layout = QVBoxLayout(camera_workspace)

        self.status_group = QGroupBox(tr("Tracking status"))
        status_layout = QHBoxLayout(self.status_group)
        self.status_dot = QLabel("V")
        self.status_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_dot.setFixedSize(46, 46)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_dot)
        status_layout.addWidget(self.status_label, 1)
        camera_layout.addWidget(self.status_group)

        self.preview_stack = QStackedWidget()
        self.preview_stack.setMinimumSize(640, 360)

        self.first_run_panel = QFrame()
        self.first_run_panel.setStyleSheet(
            "QFrame { background: #1a202c; border-radius: 6px; }"
        )
        first_run_outer = QVBoxLayout(self.first_run_panel)
        first_run_outer.addStretch(1)
        first_run_content = QWidget()
        first_run_content.setMinimumWidth(380)
        first_run_content.setMaximumWidth(500)
        first_run_layout = QVBoxLayout(first_run_content)
        first_run_layout.setSpacing(12)
        first_run_heading = QLabel(tr("Start with one camera setup"))
        first_run_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        first_run_heading.setStyleSheet(
            "color: #f7fafc; font-size: 20px; font-weight: 700"
        )
        first_run_layout.addWidget(first_run_heading)
        first_run_copy = QLabel(
            tr(
                "Choose the camera and name this physical position. Frames "
                "stay on this device and are discarded after analysis."
            )
        )
        first_run_copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        first_run_copy.setWordWrap(True)
        first_run_copy.setMinimumHeight(40)
        first_run_copy.setStyleSheet("color: #cbd5e0")
        first_run_layout.addWidget(first_run_copy)
        self.first_run_add_button = QPushButton(tr("Add camera setup"))
        self.first_run_add_button.setDefault(True)
        self.first_run_add_button.clicked.connect(self._add_setup)
        first_run_actions = QHBoxLayout()
        first_run_actions.addStretch(1)
        first_run_actions.addWidget(self.first_run_add_button)
        first_run_actions.addStretch(1)
        first_run_layout.addLayout(first_run_actions)
        first_run_outer.addWidget(
            first_run_content,
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        first_run_outer.addStretch(1)
        self.preview_stack.addWidget(self.first_run_panel)

        self.preview = QLabel(tr("Camera preview"))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet(
            "background: #1a202c; color: #cbd5e0; border-radius: 6px"
        )
        self.preview_stack.addWidget(self.preview)
        camera_layout.addWidget(self.preview_stack, 1)

        privacy = SemanticLabel(
            tr(
                "<b>Private by design:</b> camera frames are analyzed locally "
                "and discarded immediately. Stored workday history contains "
                "only posture labels, reminder stages, setups, timestamps, "
                "and durations."
            ),
            tone="info",
        )
        camera_layout.addWidget(privacy)

        footer = QHBoxLayout()
        self.summary_button = QPushButton(tr("Workday summary"))
        self.summary_button.clicked.connect(self._show_workday_summary)
        self.summary_button.setEnabled(self.history_store is not None)
        footer.addWidget(self.summary_button)
        self.evidence_button = QPushButton(tr("Evidence and safety"))
        self.evidence_button.clicked.connect(self._show_evidence)
        footer.addWidget(self.evidence_button)
        footer.addStretch()
        footer.addWidget(
            QLabel(tr("Personalized reminder — not a medical device"))
        )
        camera_layout.addLayout(footer)

        self.side_panel_frame = QWidget()
        side_panel_layout = QVBoxLayout(self.side_panel_frame)
        side_panel_layout.setContentsMargins(0, 0, 0, 0)
        side_panel_layout.setSpacing(0)

        side_panel_header = QWidget()
        side_panel_header_layout = QHBoxLayout(side_panel_header)
        side_panel_header_layout.setContentsMargins(10, 6, 6, 6)
        self.side_panel_title = QLabel()
        side_panel_title_font = self.side_panel_title.font()
        side_panel_title_font.setBold(True)
        side_panel_title_font.setPointSize(
            side_panel_title_font.pointSize() + 2
        )
        self.side_panel_title.setFont(side_panel_title_font)
        self.side_panel_title.setWordWrap(True)
        side_panel_header_layout.addWidget(self.side_panel_title, 1)
        self.side_panel_close_button = QToolButton()
        self.side_panel_close_button.setText(tr("Close"))
        self.side_panel_close_button.setAutoRaise(True)
        self.side_panel_close_button.clicked.connect(
            self._dismiss_side_panel
        )
        side_panel_header_layout.addWidget(self.side_panel_close_button)
        side_panel_layout.addWidget(side_panel_header)

        separator = QFrame()
        separator.setFixedHeight(1)
        separator.setStyleSheet(
            "background-color: palette(mid); border: none"
        )
        side_panel_layout.addWidget(separator)

        self.side_panel_host = QScrollArea()
        self.side_panel_host.setWidgetResizable(True)
        self.side_panel_host.setFrameShape(QFrame.Shape.NoFrame)
        self.side_panel_host.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        side_panel_layout.addWidget(self.side_panel_host, 1)
        self.side_panel_frame.setMinimumWidth(380)
        self.side_panel_frame.setMaximumWidth(760)
        self.side_panel_frame.hide()

        self.workspace_splitter.addWidget(camera_workspace)
        self.workspace_splitter.addWidget(self.side_panel_frame)
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 0)
        layout.addWidget(self.workspace_splitter, 1)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(create_state_icon(self._state), self)
        self.tray_menu = QMenu(self)
        self.tray.setContextMenu(self.tray_menu)
        show_action = QAction(tr("Show Vulture"), self)
        show_action.triggered.connect(self._show_window)
        self.pause_action = QAction(
            tr("Release camera")
            if self._tracking_enabled
            else tr("Resume tracking"),
            self,
        )
        self.pause_action.triggered.connect(self._toggle_tracking)
        self.calibrate_action = QAction(
            tr("Calibrate current setup"),
            self,
        )
        self.calibrate_action.triggered.connect(self._calibrate)
        self.recalibrate_step_action = QAction(
            tr("Recalibrate step"),
            self,
        )
        self.recalibrate_step_action.triggered.connect(
            self._recalibrate_step
        )
        self.summary_action = QAction(tr("Workday summary"), self)
        self.summary_action.setEnabled(self.history_store is not None)
        self.summary_action.triggered.connect(self._show_workday_summary)
        self.open_exercise_action = QAction(tr("Open movement"), self)
        self.open_exercise_action.setVisible(False)
        self.open_exercise_action.triggered.connect(
            self._open_pending_exercise
        )
        quit_action = QAction(tr("Quit"), self)
        quit_action.triggered.connect(self.quit_application)
        self.tray_menu.addAction(show_action)
        self.tray_menu.addAction(self.pause_action)
        self.tray_menu.addAction(self.calibrate_action)
        self.tray_menu.addAction(self.recalibrate_step_action)
        self.tray_menu.addAction(self.summary_action)
        self.tray_menu.addAction(self.open_exercise_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(quit_action)
        self.tray.activated.connect(self._tray_activated)
        self.tray.messageClicked.connect(self._tray_message_clicked)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _refresh_setup_combo(self) -> None:
        self.setup_combo.blockSignals(True)
        self.setup_combo.clear()
        for setup in self.data.setups:
            label = setup.name
            if setup.calibration is None:
                label += tr(" (not calibrated)")
            self.setup_combo.addItem(label, setup.id)
        if self.data.active_setup_id is not None:
            index = self.setup_combo.findData(self.data.active_setup_id)
            if index >= 0:
                self.setup_combo.setCurrentIndex(index)
        self.setup_combo.blockSignals(False)
        has_setup = bool(self.data.setups)
        controls_enabled = not self._calibration_flow_active
        camera_controls_enabled = (
            has_setup and controls_enabled and self._tracking_enabled
        )
        self.preview_stack.setCurrentWidget(
            self.preview if has_setup else self.first_run_panel
        )
        self.status_group.setVisible(has_setup)
        self.setup_combo.setEnabled(has_setup and controls_enabled)
        self.add_setup_command.setEnabled(controls_enabled)
        self.first_run_add_button.setEnabled(controls_enabled)
        self.calibrate_command.setEnabled(camera_controls_enabled)
        self.calibrate_action.setEnabled(camera_controls_enabled)
        self.pause_command.setEnabled(has_setup and controls_enabled)
        self.settings_command.setEnabled(controls_enabled)
        can_recalibrate_step = (
            camera_controls_enabled
            and self.data.active_setup() is not None
            and self.data.active_setup().calibration is not None
        )
        self.recalibrate_step_command.setEnabled(can_recalibrate_step)
        self.recalibrate_step_action.setEnabled(can_recalibrate_step)
        self.pause_action.setEnabled(has_setup and controls_enabled)
        self.summary_button.setEnabled(
            controls_enabled and self.history_store is not None
        )
        self.summary_action.setEnabled(
            controls_enabled and self.history_store is not None
        )
        self.evidence_button.setEnabled(controls_enabled)

    def _add_setup(self) -> None:
        if self._language_reload_preparing:
            return
        if self._setup_dialog is not None:
            self._focus_side_panel(self._setup_dialog)
            return
        dialog = SetupDialog()
        dialog.finished.connect(
            lambda result, active_dialog=dialog: (
                self._finish_add_setup(active_dialog, result)
            )
        )
        self._setup_dialog = dialog
        self._show_side_panel(dialog)

    def _finish_add_setup(
        self,
        dialog: SetupDialog,
        result: int,
    ) -> None:
        if dialog is not self._setup_dialog:
            return
        self._setup_dialog = None
        if result != QDialog.DialogCode.Accepted:
            self._hide_side_panel(dialog)
            return
        setup = dialog.setup_profile()
        self._hide_side_panel(dialog)
        if not self._stop_camera():
            self._show_camera_release_error()
            return
        self.data.setups.append(setup)
        self.data.active_setup_id = setup.id
        self._save_data()
        self._refresh_setup_combo()
        self._activate_setup()
        if self._tracking_enabled:
            self._calibrate()

    def _setup_changed(self, index: int) -> None:
        if self._language_reload_preparing:
            return
        setup_id = self.setup_combo.itemData(index)
        if not setup_id or setup_id == self.data.active_setup_id:
            return
        previous_setup_id = self.data.active_setup_id
        if not self._stop_camera():
            self.setup_combo.blockSignals(True)
            previous_index = self.setup_combo.findData(previous_setup_id)
            if previous_index >= 0:
                self.setup_combo.setCurrentIndex(previous_index)
            self.setup_combo.blockSignals(False)
            self._show_camera_release_error()
            return
        self.data.active_setup_id = setup_id
        self._save_data()
        self._refresh_setup_combo()
        self._activate_setup()

    def _activate_setup(self) -> None:
        if self._language_reload_preparing:
            return
        if not self._stop_camera():
            self._show_camera_release_error()
            return
        setup = self.data.active_setup()
        if setup is None:
            self.evaluator = None
            self._set_state(
                TrackerState.UNCALIBRATED,
                tr("Select or add a setup."),
            )
            return
        self.evaluator = (
            PostureEvaluator(setup.calibration, self.data.alert_policy)
            if setup.calibration is not None
            else None
        )
        if not self._tracking_enabled:
            self._show_camera_released_state()
            return
        camera = resolve_camera_descriptor(setup.camera)
        if camera is None:
            self._set_state(
                TrackerState.CAMERA_UNAVAILABLE,
                tr("The camera saved for this setup is not available."),
            )
            return
        self._latest_image = None
        self.preview.clear()
        self.preview.setText(tr("Starting camera..."))
        self.preview.setAccessibleName(tr("Camera preview"))
        self.camera_thread = CameraThread(camera, parent=self)
        self.camera_thread.preview_ready.connect(self._on_preview)
        self.camera_thread.feature_ready.connect(self._on_feature)
        self.camera_thread.tracking_lost.connect(self._on_tracking_lost)
        self.camera_thread.camera_error.connect(self._on_camera_error)
        self.camera_thread.start()
        self._reset_break_tracking()
        if setup.calibration is None:
            self._set_state(
                TrackerState.UNCALIBRATED,
                tr(
                    "Camera is ready. Calibrate this physical setup before "
                    "tracking."
                ),
            )
        elif self._tracking_enabled:
            self._set_state(
                TrackerState.LOW_CONFIDENCE,
                tr("Finding your face and shoulders..."),
            )

    def _stop_camera(self, timeout_milliseconds: int = 3000) -> bool:
        self._suspend_history()
        if self.camera_thread is None:
            return True
        camera_thread = self.camera_thread
        if camera_thread.stop(timeout_milliseconds):
            camera_thread.deleteLater()
            self.camera_thread = None
            return True
        return False

    def _camera_is_healthy(self) -> bool:
        return (
            self.camera_thread is not None
            and self.camera_thread.isRunning()
            and self.camera_thread.failure_message is None
        )

    def _show_camera_release_error(self) -> None:
        self._set_state(
            TrackerState.CAMERA_UNAVAILABLE,
            tr(
                "The previous camera has not released yet; setup switching "
                "is paused."
            ),
        )
        self._show_notice(
            tr("Camera still busy"),
            tr(
                "The current camera driver has not released safely. Wait a "
                "moment or disconnect the camera before switching setups."
            ),
            critical=True,
        )

    def _begin_calibration_flow(self) -> bool:
        if self._calibration_flow_active:
            self._focus_calibration_panel()
            self._show_tray_message(
                tr("Calibration already open"),
                tr(
                    "Finish or cancel the current calibration before starting "
                    "another."
                ),
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )
            return False
        self._calibration_flow_active = True
        self._refresh_setup_combo()
        return True

    def _show_side_panel(self, panel: QDialog) -> None:
        previous = self._side_panel
        if previous is not None and previous is not panel:
            if previous.isVisible():
                previous.reject()
            if self._side_panel is previous:
                self._hide_side_panel(previous)

        if (
            self._size_before_side_panel is None
            and not self.isMaximized()
            and not self.isFullScreen()
        ):
            self._size_before_side_panel = self.size()

        orphaned = self.side_panel_host.takeWidget()
        if orphaned is not None and orphaned is not panel:
            orphaned.hide()
            orphaned.deleteLater()
        panel.setWindowFlags(Qt.WindowType.Widget)
        self.side_panel_host.setWidget(panel)
        self._side_panel = panel
        title = panel.windowTitle()
        self.side_panel_title.setText(title)
        self.side_panel_close_button.setAccessibleName(
            tr("Close {title}", title=title)
        )
        self.preview_stack.setMinimumSize(340, 191)
        self.side_panel_frame.show()
        self.side_panel_host.show()
        panel.show()
        central_layout = self.centralWidget().layout()
        if central_layout is not None:
            central_layout.activate()

        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            requested_panel_size = panel.sizeHint().expandedTo(
                panel.minimumSizeHint()
            ).expandedTo(panel.minimumSize())
            requested_panel_width = min(
                max(
                    panel.minimumWidth(),
                    requested_panel_size.width(),
                    380,
                ),
                760,
            )
            panel_vertical_overhead = max(
                0,
                self.height()
                - self.side_panel_host.viewport().height(),
            )
            requested_window_height = (
                requested_panel_size.height() + panel_vertical_overhead
            )
            if self.isMaximized() or self.isFullScreen():
                target_width = self.width()
                target_height = self.height()
            else:
                target_width = min(
                    max(self.width(), 620 + requested_panel_width),
                    available.width(),
                )
                target_height = min(
                    max(self.height(), 720, requested_window_height),
                    available.height(),
                )
                self.resize(target_width, target_height)
            panel_width = min(
                requested_panel_width,
                max(380, target_width - 340),
            )
            self.side_panel_frame.setMaximumWidth(
                max(620, requested_panel_width)
            )
            self.workspace_splitter.setSizes(
                [max(340, target_width - panel_width), panel_width]
            )
        self._show_window()
        panel.setFocus(Qt.FocusReason.OtherFocusReason)

    def _show_calibration_panel(self, panel: QDialog) -> None:
        self._calibration_panel = panel
        self._show_side_panel(panel)

    def _focus_side_panel(self, panel: QDialog | None = None) -> None:
        target = panel or self._side_panel
        self._show_window()
        self.side_panel_frame.show()
        self.side_panel_host.show()
        if target is not None:
            target.show()
            target.setFocus(Qt.FocusReason.OtherFocusReason)
        QApplication.alert(self)

    def _focus_calibration_panel(self) -> None:
        self._focus_side_panel(self._calibration_panel)

    def _hide_side_panel(self, panel: QDialog | None = None) -> None:
        if panel is not None and panel is not self._side_panel:
            return
        hosted = self.side_panel_host.takeWidget()
        allow_deferred_exercise = not isinstance(
            self._side_panel,
            ExerciseDialog,
        )
        if hosted is not None:
            hosted.hide()
            hosted.deleteLater()
        self.preview_stack.setMinimumSize(640, 360)
        self.side_panel_host.hide()
        self.side_panel_frame.hide()
        self.side_panel_title.clear()
        self._side_panel = None
        QTimer.singleShot(
            0,
            lambda: self._finish_side_panel_close(
                allow_exercise=allow_deferred_exercise
            ),
        )

    def _finish_side_panel_close(self, *, allow_exercise: bool) -> None:
        self._show_deferred_panel(allow_exercise=allow_exercise)
        if self._side_panel is not None:
            return
        if self._language_reload_preparing or self._quitting:
            self._size_before_side_panel = None
            return
        self._restore_pre_panel_size()

    def _restore_pre_panel_size(self) -> None:
        previous_size = self._size_before_side_panel
        if (
            previous_size is None
            or self._side_panel is not None
            or self.isMaximized()
            or self.isFullScreen()
        ):
            return
        self._size_before_side_panel = None
        self.resize(previous_size)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.WindowStateChange
            and getattr(self, "_size_before_side_panel", None) is not None
            and self._side_panel is None
        ):
            QTimer.singleShot(0, self._restore_pre_panel_size)

    def _show_deferred_panel(self, *, allow_exercise: bool) -> None:
        if (
            self._language_reload_preparing
            or self._quitting
            or self._side_panel is not None
        ):
            return
        if self._pending_notice is not None:
            title, message, critical = self._pending_notice
            self._pending_notice = None
            self._show_notice(title, message, critical=critical)
            return
        if (
            allow_exercise
            and self._tracking_enabled
            and self._pending_exercise is not None
            and self._exercise_dialog is None
        ):
            self._present_exercise()

    def _dismiss_side_panel(self) -> None:
        panel = self._side_panel
        if panel is None:
            return
        panel.reject()
        if self._side_panel is panel:
            self._hide_side_panel(panel)

    def _hide_calibration_panel(self) -> None:
        self._hide_side_panel(self._calibration_panel)
        self._calibration_panel = None

    def _cancel_active_calibration(self) -> None:
        if self._calibration_panel is not None:
            self._calibration_panel.reject()
        elif self._calibration_flow_active:
            self._end_calibration_flow()

    def _end_calibration_flow(self) -> None:
        self._calibration_dialog = None
        self._hide_calibration_panel()
        self._calibration_flow_active = False
        self._refresh_setup_combo()

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
        dialog = CalibrationDialog()
        self._calibration_dialog = dialog
        dialog.finished.connect(
            lambda result, active_dialog=dialog: (
                self._finish_full_calibration(active_dialog, result)
            )
        )
        self._show_calibration_panel(dialog)

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
        selection = CalibrationStepSelectionDialog(setup.calibration)
        selection.finished.connect(
            lambda result, active_selection=selection, active_setup=setup: (
                self._finish_recalibration_selection(
                    active_selection,
                    active_setup,
                    result,
                )
            )
        )
        self._show_calibration_panel(selection)

    def _finish_recalibration_selection(
        self,
        selection: CalibrationStepSelectionDialog,
        setup: SetupProfile,
        result: int,
    ) -> None:
        if selection is not self._calibration_panel:
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
            steps=steps,
            base_profile=base_profile,
        )
        self._calibration_dialog = dialog
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
        self._show_calibration_panel(dialog)

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
            self._reset_break_tracking()
            self._set_tracking_controls()
            self._show_camera_released_state()
            return

        self._tracking_enabled = True
        self._set_tracking_controls()
        self._reset_break_tracking()
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
        if self._language_reload_preparing or not self._tracking_enabled:
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

    def _on_feature(self, frame: FeatureFrame) -> None:
        sender = self.sender()
        if sender is not None and sender is not self.camera_thread:
            return
        if self._language_reload_preparing:
            return
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
            self._last_valid_tracking_at = None
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
        if (
            self.evaluator is not None
            and not self.evaluator.mark_tracking_uncertain(captured_at)
        ):
            return
        self._suspend_history()
        self._last_valid_tracking_at = None
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
        self._suspend_history()
        self._last_valid_tracking_at = None
        self._set_state(TrackerState.CAMERA_UNAVAILABLE, message)
        if self._calibration_panel is not None:
            self._calibration_panel.reject()
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

    def _check_sedentary_break(self) -> None:
        if (
            self._language_reload_preparing
            or not self._tracking_enabled
            or self.data.active_setup() is None
            or self._exercise_dialog_open
        ):
            return
        if (
            self._tracked_seconds_since_break
            < self.data.alert_policy.sedentary_break_minutes * 60
        ):
            return
        self.data.last_exercise_offer_at = datetime.now(timezone.utc)
        self._save_data()
        self._offer_exercise()

    def _offer_exercise(self) -> None:
        if self._language_reload_preparing or self._exercise_dialog_open:
            return
        exercise = self.selector.choose(
            self.data.exercise_preferences,
            self.data.recent_exercise_ids,
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
            self._reset_break_tracking()
            return
        self._cancel_exercise_postpone()
        self._pending_exercise = exercise
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
        self._reset_break_tracking()

    def _present_exercise(self) -> None:
        if self._language_reload_preparing:
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
        dialog = ExerciseDialog(exercise, self.catalog)
        dialog.finished.connect(self._exercise_dialog_finished)
        self._exercise_dialog = dialog
        self._show_side_panel(dialog)

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
        if not self._tracking_enabled:
            if self._pending_exercise is not None:
                self._schedule_exercise_postpone()
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
        outcome = (
            dialog.outcome
            if dialog is not None
            else ExerciseOutcome.COMPLETED
        )
        if dialog is not None:
            self._hide_side_panel(dialog)
        if self._language_reload_preparing or self._quitting:
            return
        if outcome == ExerciseOutcome.POSTPONED:
            self._schedule_exercise_postpone()
        else:
            self._clear_pending_exercise()
            self._reset_break_tracking()

    def _clear_pending_exercise(self) -> None:
        self._cancel_exercise_postpone()
        self._pending_exercise = None
        self.open_exercise_action.setVisible(False)
        self._apply_icon()

    def _record_valid_tracking(self) -> None:
        now = time.monotonic()
        if self._last_valid_tracking_at is not None:
            elapsed = now - self._last_valid_tracking_at
            if elapsed <= 2.0:
                self._tracked_seconds_since_break += elapsed
        self._last_valid_tracking_at = now

    def _reset_break_tracking(self) -> None:
        self._tracked_seconds_since_break = 0.0
        self._last_valid_tracking_at = None

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
            if self.history_recorder is not None:
                self.history_recorder.checkpoint()
            return self.history_store.daily_summary(selected_date)
        except HistoryStorageError as error:
            self._disable_history_for_session(error)
            raise

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
        )
        (
            new_policy,
            new_exercise_preferences,
            new_history_preferences,
            new_language,
            requested_startup_enabled,
        ) = dialog.values()
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
        ) = (
            new_policy,
            new_exercise_preferences,
            new_history_preferences,
            new_language,
        )
        if not self._save_data():
            (
                self.data.alert_policy,
                self.data.exercise_preferences,
                self.data.history_preferences,
                self.data.interface_language,
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
        self._clear_pending_exercise()
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
