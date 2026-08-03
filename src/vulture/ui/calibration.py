from __future__ import annotations

import math
import time
from collections import defaultdict

from pydantic import Field
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from vulture.calibration import CalibrationError, CalibrationFitter
from vulture.camera import discover_cameras
from vulture.i18n import tr
from vulture.models import (
    CalibrationProfile,
    CameraDescriptor,
    FeatureFrame,
    PostureCategory,
    SetupProfile,
    StrictModel,
)
from vulture.resources import resource_path

from .common import POSTURE_TITLES, SemanticLabel


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


class SetupDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Dialog)
        self.setWindowTitle(tr("Add camera setup"))
        self.setMinimumSize(420, 220)
        self.resize(500, 260)
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
        super().__init__(parent, Qt.WindowType.Window)
        self.profile = profile
        self._baseline_confirmation_pending = False
        self.setWindowTitle(tr("Recalibrate step"))
        self.setMinimumSize(480, 420)
        self.resize(620, 600)

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
        super().__init__(parent, Qt.WindowType.Window)
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
        self.setMinimumSize(500, 480)
        self.resize(680, 700)
        outer_layout = QVBoxLayout(self)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area.setWidget(scroll_content)
        outer_layout.addWidget(self.scroll_area, 1)

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
        scroll_layout.addWidget(stage_group)

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
        scroll_layout.addWidget(content, 1)

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
            role_name = tr(step.title).upper()
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
            else tr(step.title).upper()
        )
