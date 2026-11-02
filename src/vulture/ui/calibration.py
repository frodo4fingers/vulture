from __future__ import annotations

import math
import time
from collections import defaultdict

from pydantic import Field
from PySide6.QtCore import QRect, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QPalette, QPixmap
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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

from .break_options import announce, assign_mnemonics
from .common import POSTURE_TITLES, SemanticLabel
from .theme import (
    CALIBRATION_MIN_SIZE,
    CALIBRATION_SIZE,
    CALIBRATION_STAGE_COLORS,
    FOCUS_RING_WIDTH,
    HAIRLINE,
    RADIUS_MD,
    RADIUS_SM,
    SPACE_MD,
    SPACE_SM,
    SETUP_MIN_SIZE,
    SETUP_SIZE,
    SPACE_XS,
    STEP_SELECTION_MIN_SIZE,
    progress_bar_style,
    STEP_SELECTION_SIZE,
    CaptionLabel,
    Separator,
    TextRole,
    _PaletteAwareMixin,
    apply_text_role,
    border_color,
    media_surface_style,
    muted_color,
    scheme_name,
    set_primary,
)


class CalibrationStep(StrictModel):
    key: str
    title: str
    instructions: str
    image_filename: str | None = None
    image_caption: str | None = None
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
        # The reference photo shows a head turn; until it is regenerated the
        # caption says which movement is meant.
        image_caption="Chin moves forward, not sideways.",
        category=PostureCategory.FORWARD_HEAD,
    ),
    CalibrationStep(
        key=PostureCategory.SLOUCH.value,
        title="Rounded-torso example",
        instructions=(
            "Optional: comfortably demonstrate your usual rounded torso "
            "position. Do not exaggerate or move into pain."
        ),
        image_filename="calibration-03-slouch.jpg",
        category=PostureCategory.SLOUCH,
    ),
    CalibrationStep(
        key=PostureCategory.SHOULDERS_SUNK.value,
        title="Lowered-shoulder example",
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


# The reference photos show the whole seated figure; the webcam sees head and
# shoulders. Each photo is cropped at render time to a 4:3 window whose
# top-left corner (in source pixels) frames that photo's head and shoulders.
# Corners were tuned by eye per photo because the figure drifts between shots.
CROP_SIZE = (400, 300)
HEAD_AND_SHOULDERS_CORNERS = {
    "calibration-01-comfortable-baseline.jpg": (440, 50),
    "calibration-02-head-forward.jpg": (440, 30),
    "calibration-03-slouch.jpg": (460, 70),
    "calibration-04-sunk-shoulders.jpg": (460, 70),
    "calibration-05-side-lean.jpg": (470, 55),
}
DEFAULT_CROP_CORNER = (440, 50)


class CalibrationStageImage(QLabel):
    ASPECT_RATIO = CROP_SIZE[0] / CROP_SIZE[1]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_pixmap = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.setStyleSheet(media_surface_style())

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return round(width / self.ASPECT_RATIO)

    def sizeHint(self) -> QSize:
        return QSize(*CROP_SIZE) / 2

    def minimumSizeHint(self) -> QSize:
        return QSize(*CROP_SIZE) / 3

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
        x, y = HEAD_AND_SHOULDERS_CORNERS.get(
            step.image_filename, DEFAULT_CROP_CORNER
        )
        pixmap = pixmap.copy(QRect(x, y, *CROP_SIZE))
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
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class CalibrationReference(QWidget):
    """Reference photo with an optional caption underneath."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_XS)
        self.image = CalibrationStageImage()
        self.caption = CaptionLabel()
        layout.addWidget(self.image)
        layout.addWidget(self.caption)
        layout.addStretch(1)

    def set_step(self, step: CalibrationStep) -> None:
        self.image.set_step(step)
        caption = tr(step.image_caption) if step.image_caption else ""
        self.caption.setText(caption)
        self.caption.setVisible(bool(caption))
        self.setVisible(step.image_filename is not None)


# Stage state -> (marker, spoken word). The marker and the word carry the
# state, so colour is only reinforcement.
_STAGE_MARKERS = {
    "current": ("●", "current"),
    "recorded": ("✓", "recorded"),
    "retry": ("!", "needs another try"),
    "skipped": ("–", "skipped"),
    "pending": ("○", "not started"),
}


class CalibrationStepper(_PaletteAwareMixin, QFrame):
    """"Step 2 of 5" plus one marker per stage; focusable for keyboard users."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("calibrationStepper")
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(tr("Calibration progress"))
        self._state: tuple[list[str], list[str], int] | None = None
        self._counter = QLabel()
        apply_text_role(self._counter, TextRole.BODY_STRONG)
        self._pills: list[QLabel] = []
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(SPACE_XS, SPACE_XS, SPACE_XS, SPACE_XS)
        self._row.setSpacing(SPACE_SM)
        self._row.addWidget(self._counter)
        self._row.addStretch(1)

    def set_state(
        self, titles: list[str], statuses: list[str], index: int
    ) -> None:
        self._state = (titles, statuses, index)
        while len(self._pills) < len(titles):
            pill = QLabel()
            apply_text_role(pill, TextRole.CAPTION)
            self._pills.append(pill)
            self._row.insertWidget(self._row.count() - 1, pill)
        self._refresh_theme()

    def _apply_theme(self) -> None:
        self._render()

    def _render(self) -> None:
        if self._state is None:
            return
        titles, statuses, index = self._state
        total = len(titles)
        colors = CALIBRATION_STAGE_COLORS[scheme_name()]
        focus = self.palette().color(QPalette.ColorRole.Highlight).name()
        self.setStyleSheet(
            f"QFrame#calibrationStepper {{ border:"
            f" {FOCUS_RING_WIDTH}px solid transparent;"
            f" border-radius: {RADIUS_MD}px }}"
            f" QFrame#calibrationStepper:focus {{ border-color: {focus} }}"
        )
        current = min(index, total - 1)
        self._counter.setText(
            tr("Step {current} of {total}", current=current + 1, total=total)
        )
        summary = []
        for position, (pill, title, status) in enumerate(
            zip(self._pills, titles, statuses)
        ):
            state = (
                "current"
                if position == index and status != "retry"
                else status
            )
            marker, word = _STAGE_MARKERS[state]
            pill.setText(f"{marker} {position + 1}")
            description = tr(
                "Step {number}: {title}, {state}",
                number=position + 1,
                title=tr(title),
                state=tr(word),
            )
            pill.setAccessibleName(description)
            pill.setToolTip(description)
            summary.append(description)
            if state == "pending":
                look = (
                    f"background: transparent; color:"
                    f" {muted_color().name()}; border:"
                    f" {HAIRLINE}px solid {border_color().name()}"
                )
            else:
                background, foreground = colors[state]
                weight = "; font-weight: 600" if state == "current" else ""
                look = (
                    f"background-color: {background}; color: {foreground};"
                    f" border: {HAIRLINE}px solid {foreground}{weight}"
                )
            pill.setStyleSheet(
                f"QLabel {{ {look}; border-radius: {RADIUS_SM}px;"
                f" padding: {HAIRLINE}px {SPACE_SM}px }}"
            )
        self.setAccessibleDescription(
            tr(
                "Step {current} of {total}. ",
                current=current + 1,
                total=total,
            )
            + " ".join(summary)
        )


def _friendly_camera_name(camera: CameraDescriptor) -> str:
    """The camera's description without the trailing device path."""
    suffix = f" ({camera.locator})"
    name = camera.display_name
    return name[: -len(suffix)] if name.endswith(suffix) else name


class SetupDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Dialog)
        self.setWindowTitle(tr("Add camera setup"))
        self.setMinimumSize(SETUP_MIN_SIZE)
        self.resize(SETUP_SIZE)
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
        names = [_friendly_camera_name(camera) for camera in self._cameras]
        seen: dict[str, int] = {}
        for camera, name in zip(self._cameras, names):
            index = self.camera_combo.count()
            seen[name] = seen.get(name, 0) + 1
            shared = names.count(name) > 1
            self.camera_combo.addItem(
                f"{name} ({seen[name]})" if shared else name, camera
            )
            # Device paths are noise to read; keep them for identical names.
            if shared and isinstance(camera.locator, str):
                self.camera_combo.setItemData(
                    index, camera.locator, Qt.ItemDataRole.ToolTipRole
                )
        form.addRow(tr("Setup name"), self.name_edit)
        form.addRow(tr("Camera"), self.camera_combo)
        layout.addLayout(form)
        layout.addWidget(
            CaptionLabel(
                tr(
                    "Next, Vulture guides you through a short calibration "
                    "for this camera."
                )
            )
        )

        if not self._cameras:
            warning = QLabel(
                tr(
                    "No camera devices were found. Connect or enable a camera, "
                    "then reopen this dialog."
                )
            )
            warning.setWordWrap(True)
            apply_text_role(warning, TextRole.BODY_STRONG)
            layout.addWidget(warning)

        self.feedback_label = SemanticLabel(tone="safety")
        self.feedback_label.hide()
        layout.addWidget(self.feedback_label)

        # Hosted in the shell's side panel, whose header Close and Esc are
        # the one exit, so the form has no Cancel.
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self._validate_and_accept)
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setEnabled(bool(self._cameras))
        set_primary(save_button, True)
        layout.addWidget(buttons)
        # Content hugs the top; spare height stays below the buttons.
        layout.addStretch(1)
        QWidget.setTabOrder(self.name_edit, self.camera_combo)
        QWidget.setTabOrder(self.camera_combo, save_button)

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
        self.setWindowTitle(tr("Redo a calibration step"))
        self.setMinimumSize(STEP_SELECTION_MIN_SIZE)
        self.resize(STEP_SELECTION_SIZE)

        layout = QVBoxLayout(self)

        explanation = QLabel(
            tr("Choose one calibration step to record again.")
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        form = QFormLayout()
        self.step_combo = QComboBox()
        for step in CALIBRATION_STEPS:
            if step.category is None:
                status = tr("saved")
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

        # Photo on one half, copy on the other.
        self.reference = CalibrationReference()
        self.reference_image = self.reference.image
        self.description = SemanticLabel(tone="info")
        reference_row = QHBoxLayout()
        reference_row.setSpacing(SPACE_MD)
        reference_row.addWidget(self.reference, 1)
        reference_row.addWidget(
            self.description, 1, Qt.AlignmentFlag.AlignTop
        )
        layout.addLayout(reference_row)
        self.baseline_warning = SemanticLabel(
            tr(
                "Replacing the comfortable baseline removes every learned "
                "posture example for this setup, because they were learned "
                "relative to it. You will need to recalibrate those steps "
                "individually. Continue?"
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
        set_primary(self.confirm_button, True)
        buttons.accepted.connect(self._confirm_selection)
        buttons.rejected.connect(self.reject)
        layout.addStretch(1)
        layout.addWidget(buttons)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self._cancel_button = cancel_button
        QWidget.setTabOrder(self.step_combo, self.confirm_button)
        QWidget.setTabOrder(self.confirm_button, cancel_button)
        self._update_description()
        self._fit_height()

    def _update_description(self) -> None:
        self._baseline_confirmation_pending = False
        self.baseline_warning.hide()
        self._set_confirm_text(tr("Redo this step"))
        step = self._current_step()
        if step is None:
            self.reference.hide()
            self.description.clear()
            return
        self.reference.set_step(step)
        detail = tr(step.instructions)
        # The baseline's consequence is stated once, by baseline_warning.
        if step.category is not None:
            detail += "\n\n" + tr(
                "Only this posture example will be replaced; the other "
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
            self._set_confirm_text(tr("Recalibrate comfortable baseline"))
            self._fit_height()
            return
        self.accept()

    def _fit_height(self) -> None:
        """Grow (never shrink) to the content, e.g. once the warning shows."""
        needed = self.layout().totalHeightForWidth(self.width())
        self.resize(self.width(), max(self.height(), needed))

    def _set_confirm_text(self, text: str) -> None:
        self.confirm_button.setText(text)
        assign_mnemonics(self.confirm_button, self._cancel_button)

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


SOUND_CUE_FILES = {
    "countdown": "countdown.wav",
    "start": "record-start.wav",
    "end": "record-end.wav",
}
SOUND_CUE_VOLUME = 0.6


class CalibrationDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        steps: list[CalibrationStep] | None = None,
        base_profile: CalibrationProfile | None = None,
        sound_cues: bool = True,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self._sound_cues = sound_cues
        self._cue_effects: dict[str, QSoundEffect] = {}
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
        self._last_sample_at = 0.0
        self._samples: dict[str, list[FeatureFrame]] = defaultdict(list)
        self._latest_quality = 0.0
        self._stage_status = ["pending" for _step in self.steps]
        self._finished = False

        if base_profile is not None:
            window_title = tr("Recalibrate posture step")
        elif len(self.steps) == 1 and self.steps[0].category is None:
            window_title = tr("Recalibrate comfortable baseline")
        else:
            window_title = tr("Calibrate this setup")
        self.setWindowTitle(window_title)
        self.setMinimumSize(CALIBRATION_MIN_SIZE)
        self.resize(CALIBRATION_SIZE)
        outer_layout = QVBoxLayout(self)
        self.stepper = CalibrationStepper()
        outer_layout.addWidget(self.stepper)

        # Only the explanation scrolls; the actions below stay in view.
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area.setWidget(content)
        outer_layout.addWidget(self.scroll_area, 1)

        self.role_label = SemanticLabel(
            strong=True, role=TextRole.HEADING
        )
        self.reference = CalibrationReference()
        self.reference_image = self.reference.image
        self.instructions_label = QLabel()
        self.instructions_label.setWordWrap(True)
        # Photo on one half, instructions on the other.
        reference_row = QHBoxLayout()
        reference_row.setSpacing(SPACE_MD)
        reference_row.addWidget(self.reference, 1)
        reference_row.addWidget(
            self.instructions_label, 1, Qt.AlignmentFlag.AlignTop
        )
        self.phase_label = QLabel()
        apply_text_role(self.phase_label, TextRole.HEADING)
        self.quality_label = QLabel(tr("Looking for you in the camera..."))
        self.quality_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(SPACE_SM)
        self.progress.setStyleSheet(progress_bar_style())
        self.progress.setAccessibleName(tr("Recording progress"))
        self.progress.hide()
        layout.addWidget(self.role_label)
        layout.addLayout(reference_row)
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

        outer_layout.addWidget(Separator())
        controls = QHBoxLayout()
        self.start_button = QPushButton(tr("Start recording"))
        self.skip_button = QPushButton(tr("Skip this example"))
        self.cancel_button = QPushButton(tr("Cancel"))
        self.skip_button.setAutoDefault(False)
        self.cancel_button.setAutoDefault(False)
        set_primary(self.start_button, True)
        self.start_button.clicked.connect(self._start_sample)
        self.skip_button.clicked.connect(self._skip_step)
        self.cancel_button.clicked.connect(self.reject)
        controls.addWidget(self.start_button)
        controls.addWidget(self.skip_button)
        controls.addStretch()
        controls.addWidget(self.cancel_button)
        outer_layout.addLayout(controls)
        QWidget.setTabOrder(self.stepper, self.start_button)
        QWidget.setTabOrder(self.start_button, self.skip_button)
        QWidget.setTabOrder(self.skip_button, self.cancel_button)

        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._show_step()
        # Land on the first action, not on the stepper.
        self.start_button.setFocus()

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
            self._last_sample_at = time.monotonic()

    def _show_step(self) -> None:
        step = self.steps[self._step_index]
        if step.category is None:
            self.role_label.setText(tr("Your comfortable baseline"))
            self.role_label.set_semantic_tone("good", strong=True)
        else:
            self.role_label.setText(
                tr(
                    "Example: {posture} ({requirement})",
                    posture=tr(POSTURE_TITLES[step.category.value]),
                    requirement=(
                        tr("required") if step.required else tr("optional")
                    ),
                )
            )
            self.role_label.set_semantic_tone("info", strong=True)
        self.reference.set_step(step)
        self.instructions_label.setText(tr(step.instructions))
        self.phase_label.setText(tr("Ready when you are"))
        self.progress.setValue(0)
        self._show_recording(False)
        self.start_button.setText(tr("Start recording"))
        self._assign_mnemonics()
        self.start_button.setEnabled(True)
        self.skip_button.setEnabled(not step.required)
        self.feedback_label.clear()
        self.feedback_label.hide()
        self._phase = "idle"
        self._current_samples = []
        self._refresh_stepper()
        self._announce(
            tr(
                "Step {current} of {total}: {title}",
                current=self._step_index + 1,
                total=len(self.steps),
                title=tr(step.title),
            )
        )

    def _assign_mnemonics(self) -> None:
        assign_mnemonics(
            self.start_button, self.skip_button, self.cancel_button
        )

    def _refresh_stepper(self) -> None:
        self.stepper.set_state(
            [step.title for step in self.steps],
            self._stage_status,
            self._step_index,
        )

    def _show_recording(self, visible: bool) -> None:
        self.progress.setVisible(visible)

    def _announce(self, message: str) -> None:
        """Tell assistive technology about a state the user cannot see."""
        announce(self.phase_label, message)

    def _play_cue(self, cue: str) -> None:
        """A soft tone for moments the user cannot watch; silent on failure."""
        if not self._sound_cues:
            return
        try:
            effect = self._cue_effects.get(cue)
            if effect is None:
                effect = QSoundEffect(self)
                effect.setSource(
                    QUrl.fromLocalFile(
                        str(resource_path("sounds", SOUND_CUE_FILES[cue]))
                    )
                )
                effect.setVolume(SOUND_CUE_VOLUME)
                self._cue_effects[cue] = effect
            effect.play()
        except Exception:  # audio is a nicety, never a reason to fail
            self._sound_cues = False

    def _start_sample(self) -> None:
        if self._phase != "idle":
            return
        self._current_samples = []
        self._phase = "preparing"
        self._deadline = time.monotonic() + 3.0
        self.start_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.feedback_label.hide()
        self.phase_label.setText(tr("Get ready…"))
        self._play_cue("countdown")
        self._announce(tr("Get ready. Recording starts in 3 seconds."))

    def _skip_step(self) -> None:
        step = self.steps[self._step_index]
        if step.required:
            return
        self._stage_status[self._step_index] = "skipped"
        self._advance()

    def _tick(self) -> None:
        quality_percent = round(self._latest_quality * 100)
        if self._phase == "idle":
            text = tr(
                "Current tracking quality: {quality}% (70% required)",
                quality=quality_percent,
            )
            if quality_percent < 70:
                text += "\n" + tr(
                    "Move so your face and shoulders are in view, with "
                    "light in front of you."
                )
            self.quality_label.setText(text)
            return

        remaining = self._deadline - time.monotonic()
        if self._phase == "preparing":
            self.quality_label.setText(
                tr(
                    "Recording starts in {seconds}...",
                    seconds=max(1, math.ceil(remaining)),
                )
            )
            if remaining > 0:
                return
            step = self.steps[self._step_index]
            self._phase = "capturing"
            self._last_sample_at = time.monotonic()
            self._deadline = time.monotonic() + step.capture_seconds
            remaining = step.capture_seconds
            self._show_recording(True)
            self.phase_label.setText(tr("Recording… stay in this position"))
            self._play_cue("start")
            self._announce(tr("Recording. Stay in this position."))
            # Fall through so the countdown line is replaced right away.

        if self._phase == "capturing":
            step = self.steps[self._step_index]
            elapsed = step.capture_seconds - max(remaining, 0)
            self.progress.setValue(
                min(100, round(elapsed / step.capture_seconds * 100))
            )
            text = tr(
                "{seconds}s left.",
                seconds=max(1, math.ceil(remaining)),
            )
            if time.monotonic() - self._last_sample_at >= 1.5:
                text += "\n" + tr(
                    "Make sure your face and shoulders are in view, with "
                    "light in front of you."
                )
            self.quality_label.setText(text)
            if remaining <= 0:
                self._finish_sample()

    def _finish_sample(self) -> None:
        step = self.steps[self._step_index]
        minimum_samples = 30 if step.category is None else 15
        self._play_cue("end")
        if len(self._current_samples) < minimum_samples:
            self._phase = "idle"
            self._stage_status[self._step_index] = "retry"
            self.progress.setValue(0)
            self._show_recording(False)
            self.start_button.setText(tr("Record again"))
            self._assign_mnemonics()
            self.start_button.setEnabled(True)
            self.skip_button.setEnabled(not step.required)
            self.phase_label.setText(tr("Let's try that again"))
            # The idle tick keeps rewriting quality_label, so the reason
            # lives in the feedback panel where it stays readable.
            message = (
                tr(
                    "The camera could not see you clearly enough. Adjust "
                    "the camera or your position, then record this step "
                    "again."
                )
                if step.required
                else tr(
                    "The camera could not see you clearly enough. Adjust "
                    "the camera or your position, then record again or "
                    "skip this optional example."
                )
            )
            self.feedback_label.setText(message)
            self.feedback_label.show()
            self._announce(tr("Recording finished.") + " " + message)
            self._refresh_stepper()
            return
        self._announce(tr("Recording finished."))
        self._samples[step.key] = list(self._current_samples)
        self._stage_status[self._step_index] = "recorded"
        self._advance()

    def _advance(self) -> None:
        self._step_index += 1
        if self._step_index < len(self.steps):
            self._show_step()
            return
        self._refresh_stepper()
        self._fit_profile()

    def _fit_profile(self) -> None:
        self._phase = "idle"
        self._show_recording(False)
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
                            "Record the selected posture example before "
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
                tr("Calibration incomplete: {error}", error=error)
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
                    "General posture nudges remain available.",
                    postures=", ".join(disabled + unavailable),
                )
        if not self._finished:
            self.accept()
