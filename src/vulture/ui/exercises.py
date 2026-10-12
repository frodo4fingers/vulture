from __future__ import annotations

import re
import time

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QFocusEvent,
    QKeyEvent,
    QMouseEvent,
    QPalette,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vulture.breaks import ManualBreakChoice
from vulture.exercises import (
    Exercise,
    ExerciseCatalog,
    exercise_media_path,
)
from vulture.i18n import tr

from .common import (
    ContentHeightTextBrowser,
    SemanticLabel,
    set_accessible_link_palette,
)
from .break_options import (
    AlternativeBreakPicker,
    announce,
    assign_mnemonics,
    format_countdown,
    set_primary,
)
from .theme import (
    CONTROL_SPACING,
    EVIDENCE_MIN_SIZE,
    EVIDENCE_SIZE,
    FOCUS_RING_WIDTH,
    MEDIA_ASPECT_RATIO,
    MEDIA_MIN_HEIGHT,
    PANEL_MIN_WIDTH,
    RADIUS_MD,
    SECTION_SPACING,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
    CaptionLabel,
    Separator,
    TextRole,
    apply_text_role,
    role_font,
)


EXERCISE_POSTPONE_MINUTES = 10
COMPLETION_ACK_MS = 1500
# The walk-away countdown must be readable from across the room.
COUNTDOWN_SCALE = 2.5
MEDIA_HINT_WIDTH = 480

_DURATION_AT_END = re.compile(
    r"(\d+)(?:\s*[-–]\s*(\d+))?\s*(min|sek|sec|seg)\w*\s*$",
    re.IGNORECASE,
)
_SETS = re.compile(
    r"(\d+)\s+(?:\w+\s+)?"
    r"(?:sets?|rounds?|cycles?|Sätze|Durchgänge|Zyklen|series|rondas|ciclos)\b",
    re.IGNORECASE,
)


def dose_duration_seconds(dose: str) -> int | None:
    """Seconds for doses that end in a duration such as "5 minutes".

    Ranges use their upper bound. The catalog only has prose doses, so this
    covers the English, German and Spanish wordings it ships; anything else
    returns None and the panel simply shows no timer.
    """
    match = _DURATION_AT_END.search(dose)
    if match is None:
        return None
    amount = int(match.group(2) or match.group(1))
    return amount * (60 if match.group(3).lower() == "min" else 1)


def dose_set_count(dose: str) -> int | None:
    """Number of sets/rounds/cycles named in a rep-based dose, if any."""
    match = _SETS.search(dose)
    return int(match.group(1)) if match else None


class ExerciseMedia(QVideoWidget):
    """Demonstration footage that takes the height the panel has left.

    The video never grows taller than its 16:9 frame, and never forces the
    panel to scroll: a shorter slot letterboxes the footage instead.
    """

    toggle_requested = Signal()
    focus_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"border-radius: {RADIUS_MD}px")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.focus_changed.emit(True)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        self.focus_changed.emit(False)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space:
            self.toggle_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.toggle_requested.emit()
        event.accept()

    def sizeHint(self) -> QSize:
        # The preferred height is the minimum: a scroll area sizes its widget
        # from hints, and spare height reaches the video through its stretch.
        return QSize(MEDIA_HINT_WIDTH, MEDIA_MIN_HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return QSize(
            round(MEDIA_MIN_HEIGHT * MEDIA_ASPECT_RATIO),
            MEDIA_MIN_HEIGHT,
        )


class MediaFrame(QFrame):
    """Hosts the video and draws the keyboard focus ring around it.

    A native video surface paints over its own border, so the ring lives on
    this frame. The frame also stops the video growing taller than 16:9.
    """

    def __init__(self, media: ExerciseMedia, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("exerciseMediaFrame")
        self.setSizePolicy(media.sizePolicy())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*(FOCUS_RING_WIDTH,) * 4)
        layout.addWidget(media)
        media.focus_changed.connect(self._set_focused)
        self._set_focused(False)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        inner = self.width() - 2 * FOCUS_RING_WIDTH
        self.setMaximumHeight(
            round(inner / MEDIA_ASPECT_RATIO) + 2 * FOCUS_RING_WIDTH
        )

    def _set_focused(self, focused: bool) -> None:
        color = (
            self.palette().color(QPalette.ColorRole.Highlight).name()
            if focused
            else "transparent"
        )
        self.setStyleSheet(
            f"QFrame#exerciseMediaFrame {{ border: {FOCUS_RING_WIDTH}px"
            f" solid {color}; border-radius: {RADIUS_MD}px }}"
        )


class ExerciseOutcome:
    COMPLETED = "completed"
    POSTPONED = "postponed"
    DISMISSED = "dismissed"
    SWAPPED = "swapped"
    ALTERNATIVE = "alternative"


class ExerciseDialog(QDialog):
    # The shell collapses the camera workspace while a dialog with this flag
    # sits in the side panel.
    wants_break_mode = True

    def __init__(
        self,
        exercise: Exercise,
        catalog: ExerciseCatalog,
        parent: QWidget | None = None,
        *,
        alternative_choices: tuple[ManualBreakChoice, ...] = (),
        show_full_safety: bool = False,
    ) -> None:
        super().__init__(parent)
        self.exercise = exercise
        self.catalog = catalog
        self.show_full_safety = show_full_safety
        self.player: QMediaPlayer | None = None
        self.outcome = ExerciseOutcome.POSTPONED
        self.selected_choice: ManualBreakChoice | None = None
        self._duration = dose_duration_seconds(exercise.dose)
        self._set_count = None if self._duration else dose_set_count(
            exercise.dose
        )
        # A timed standing movement takes you away from the desk.
        self.walk_away = (
            self._duration is not None and "standing" in exercise.tags
        )
        self._deadline: float | None = None
        self.setWindowTitle(
            tr("Movement break: {exercise}", exercise=exercise.title)
        )
        self.setMinimumWidth(PANEL_MIN_WIDTH)

        layout = QVBoxLayout(self)
        # Break mode is height-constrained, so the gaps use the tighter step.
        layout.setSpacing(CONTROL_SPACING)

        # Everything that is shown before you start; hidden while you walk.
        self.preview = QWidget()
        preview_layout = QVBoxLayout(self.preview)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(CONTROL_SPACING)
        if self.walk_away:
            heading = QLabel(tr("Watch once, then go"))
            apply_text_role(heading, TextRole.HEADING)
            preview_layout.addWidget(heading)

        media = exercise_media_path(exercise)
        self.video: ExerciseMedia | None = None
        self.playback_button = QToolButton()
        self.playback_button.setAutoRaise(True)
        self.playback_button.clicked.connect(self._toggle_playback)
        if media is not None:
            self.video = ExerciseMedia()
            self.video.setAccessibleName(
                tr(
                    "Demonstration: {exercise}",
                    exercise=exercise.title,
                )
            )
            self.video.toggle_requested.connect(self._toggle_playback)
            preview_layout.addWidget(MediaFrame(self.video), 1)
            # No audio output is attached: the clips are silent by design.
            self.player = QMediaPlayer(self)
            self.player.setVideoOutput(self.video)
            self.player.setSource(QUrl.fromLocalFile(str(media)))
            self.player.setLoops(QMediaPlayer.Loops.Infinite)
            self.player.playbackStateChanged.connect(
                self._sync_playback_button
            )
            self.player.play()
        self._sync_playback_button()

        media_row = QHBoxLayout()
        media_row.setContentsMargins(0, 0, 0, 0)
        media_row.setSpacing(CONTROL_SPACING)
        if self.player is not None:
            media_row.addWidget(self.playback_button)
        dose = QLabel(exercise.dose)
        dose.setWordWrap(True)
        apply_text_role(dose, TextRole.BODY_STRONG)
        media_row.addWidget(dose, 1)
        self.alternative_picker = AlternativeBreakPicker(
            alternative_choices
        )
        self.alternative_picker.choice_selected.connect(
            self._choose_alternative
        )
        media_row.addWidget(self.alternative_picker)
        preview_layout.addLayout(media_row)

        steps = ContentHeightTextBrowser()
        steps.setOpenExternalLinks(True)
        set_accessible_link_palette(steps)
        step_html = "".join(
            f"<li>{step}</li>" for step in exercise.steps
        )
        steps.setHtml(f"<ol>{step_html}</ol>")
        preview_layout.addWidget(steps)
        # The preview (and its video) soaks up the spare height; the stretch
        # below only matters once the preview is hidden mid-walk.
        layout.addWidget(self.preview, 1)

        self.set_checkboxes: list[QCheckBox] = []
        if self._set_count:
            checklist = QHBoxLayout()
            checklist.setContentsMargins(0, 0, 0, 0)
            checklist.setSpacing(SECTION_SPACING)
            for number in range(1, self._set_count + 1):
                box = QCheckBox(tr("Round {number}", number=number))
                self.set_checkboxes.append(box)
                checklist.addWidget(box)
            checklist.addStretch(1)
            layout.addLayout(checklist)

        self.countdown_block = QWidget()
        self.countdown = QLabel()
        self.countdown_caption = CaptionLabel("")
        self.progress = QProgressBar()
        self.running_note = SemanticLabel(
            tr("Off you go. Come back when the timer ends."),
            tone="info",
        )
        if self._duration:
            self._build_countdown_block(self._duration)
            layout.addWidget(self.running_note)
            layout.addWidget(self.countdown_block)
            self.running_note.hide()
            if self.walk_away:
                self.countdown_block.hide()

        safety_text = tr(
            "<b>Safety:</b> {safety}", safety=exercise.safety
        )
        self._short_safety_text = safety_text
        if show_full_safety:
            safety_text += f"<br><br>{catalog.global_safety}"
        self.safety = SemanticLabel(
            safety_text,
            tone="safety",
            role=TextRole.CAPTION,
        )
        layout.addWidget(self.safety)

        self.details_toggle = QToolButton()
        self.details_toggle.setText(tr("Sources and medical context"))
        self.details_toggle.setCheckable(True)
        self.details_toggle.setAutoRaise(True)
        self.details_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.details_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.details_toggle.toggled.connect(
            self._set_details_expanded
        )
        layout.addWidget(
            self.details_toggle,
            0,
            Qt.AlignmentFlag.AlignLeft,
        )

        self.details_panel = QWidget()
        details_layout = QVBoxLayout(self.details_panel)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(CONTROL_SPACING)
        self.global_safety = QLabel(catalog.global_safety)
        self.global_safety.setWordWrap(True)
        apply_text_role(self.global_safety, TextRole.CAPTION)
        details_layout.addWidget(self.global_safety)
        source_map = catalog.source_map()
        self.sources = ContentHeightTextBrowser()
        self.sources.setOpenExternalLinks(True)
        set_accessible_link_palette(self.sources)
        apply_text_role(self.sources, TextRole.CAPTION)
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
        apply_text_role(self.disclaimer, TextRole.CAPTION)
        details_layout.addWidget(self.disclaimer)
        self.details_panel.hide()
        layout.addWidget(self.details_panel)

        layout.addStretch(0)

        self.completion_note = SemanticLabel(
            tr("Nice work — break done."),
            tone="good",
            role=TextRole.HEADING,
        )
        self.completion_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.completion_note.hide()
        layout.addWidget(self.completion_note)

        layout.addWidget(Separator())
        # Primary Start/Done, then Later and Skip: at most four exits.
        self.actions = QWidget()
        button_row = QHBoxLayout(self.actions)
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(SPACE_SM)
        self.start_button = QPushButton(tr("Start"))
        self.start_button.clicked.connect(self._start_timer)
        button_row.addWidget(self.start_button)
        self.done_button = QPushButton(tr("Done"))
        self.done_button.clicked.connect(self._finish)
        button_row.addWidget(self.done_button)
        button_row.addStretch(1)
        self.postpone_button = QPushButton(tr("Remind me later"))
        self.postpone_button.setAutoDefault(False)
        self.postpone_button.clicked.connect(self._postpone)
        button_row.addWidget(self.postpone_button)
        self.skip_button = QPushButton(tr("Skip"))
        self.skip_button.setAutoDefault(False)
        self.skip_button.clicked.connect(self._skip)
        button_row.addWidget(self.skip_button)
        layout.addWidget(self.actions)
        self.start_button.setVisible(self._duration is not None)
        set_primary(self.start_button, True)
        set_primary(self.done_button, self._duration is None)
        assign_mnemonics(
            self.start_button,
            self.done_button,
            self.alternative_picker,
            self.postpone_button,
            self.skip_button,
        )
        order = [
            self.video,
            self.playback_button if self.player is not None else None,
            self.alternative_picker,
            *self.set_checkboxes,
            self.start_button,
            self.done_button,
            self.postpone_button,
            self.skip_button,
            self.details_toggle,
        ]
        order = [widget for widget in order if widget is not None]
        for first, second in zip(order, order[1:]):
            QWidget.setTabOrder(first, second)

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._update_countdown)
        self._ack_timer = QTimer(self)
        self._ack_timer.setSingleShot(True)
        self._ack_timer.setInterval(COMPLETION_ACK_MS)
        self._ack_timer.timeout.connect(self.accept)

    def _build_countdown_block(self, seconds: int) -> None:
        block = QVBoxLayout(self.countdown_block)
        block.setContentsMargins(0, SPACE_SM, 0, 0)
        block.setSpacing(0)
        self.countdown.setText(format_countdown(seconds))
        font = role_font(TextRole.DISPLAY)
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * COUNTDOWN_SCALE)
        self.countdown.setFont(font)
        self.countdown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown.setAccessibleName(tr("Time remaining"))
        block.addWidget(self.countdown)
        self.countdown_caption.setText(tr("suggested"))
        self.countdown_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        block.addWidget(self.countdown_caption)
        self.progress.setRange(0, seconds)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(SPACE_SM)
        self.progress.setAccessibleName(tr("Break progress"))
        block.addWidget(self.progress)

    def _start_timer(self) -> None:
        if self._duration is None or self._deadline is not None:
            return
        self._deadline = time.monotonic() + self._duration
        self.start_button.hide()
        self.countdown_caption.setText(tr("remaining"))
        self.countdown_block.show()
        if self.walk_away:
            # Hand over to the glanceable countdown; the clip is no longer
            # needed and would only spend CPU unseen.
            if self.player is not None:
                self.player.pause()
            self.preview.hide()
            self.running_note.show()
        self._timer.start()
        self._update_countdown()

    def _update_countdown(self) -> None:
        if self._deadline is None or self._duration is None:
            return
        remaining = max(0.0, self._deadline - time.monotonic())
        self.countdown.setText(format_countdown(remaining))
        self.progress.setValue(round(self._duration - remaining))
        if remaining > 0:
            return
        self._timer.stop()
        self.countdown_caption.setText(tr("Suggested time complete"))
        set_primary(self.done_button, True)
        announce(self.countdown, tr("Suggested time complete"))
        if self.walk_away:
            QApplication.beep()

    def _sync_playback_button(self, *_args: object) -> None:
        playing = (
            self.player is not None
            and self.player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        )
        self.playback_button.setText(
            tr("Pause video") if playing else tr("Play video")
        )

    def _toggle_playback(self) -> None:
        if self.player is None:
            return
        if (
            self.player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        ):
            self.player.pause()
        else:
            self.player.play()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self.show_full_safety:
            QTimer.singleShot(0, self, self._fit_full_safety)

    def _fit_full_safety(self) -> None:
        """Fold the first-break safety text away when it forces a scroll.

        The text stays one click away under "Sources and medical context".
        """
        viewport = self.parentWidget()
        if (
            viewport is not None
            and self.layout().totalMinimumHeightForWidth(self.width())
            > viewport.height()
        ):
            self.safety.setText(self._short_safety_text)

    def _set_details_expanded(self, expanded: bool) -> None:
        self.details_panel.setVisible(expanded)
        self.details_toggle.setArrowType(
            Qt.ArrowType.DownArrow
            if expanded
            else Qt.ArrowType.RightArrow
        )
        self.updateGeometry()

    def _finish(self) -> None:
        """Acknowledge the finished break calmly, then close.

        The outcome is recorded immediately so closing the panel during the
        acknowledgement still logs the break as done. A static message keeps
        this free of animation, so there is nothing to reduce.
        """
        if self._ack_timer.isActive():
            return
        self.outcome = ExerciseOutcome.COMPLETED
        self._timer.stop()
        self.actions.setEnabled(False)
        self.completion_note.show()
        self._ack_timer.start()

    def _complete(self) -> None:
        self.outcome = ExerciseOutcome.COMPLETED
        self.accept()

    def _postpone(self) -> None:
        self.outcome = ExerciseOutcome.POSTPONED
        self.reject()

    def _skip(self) -> None:
        self.outcome = ExerciseOutcome.DISMISSED
        self.reject()

    def _choose_alternative(self, choice_value: str) -> None:
        self.selected_choice = ManualBreakChoice(choice_value)
        self.outcome = (
            ExerciseOutcome.SWAPPED
            if self.selected_choice is ManualBreakChoice.GUIDED_MOVEMENT
            else ExerciseOutcome.ALTERNATIVE
        )
        self.reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.player is not None:
            self.player.stop()
        super().closeEvent(event)

    def done(self, result: int) -> None:
        self._timer.stop()
        self._ack_timer.stop()
        if self.player is not None:
            self.player.stop()
        super().done(result)


class EvidenceDialog(QDialog):
    def __init__(
        self,
        catalog: ExerciseCatalog,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(tr("Evidence and safety"))
        self.setMinimumSize(EVIDENCE_MIN_SIZE)
        self.resize(EVIDENCE_SIZE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        set_accessible_link_palette(browser)
        # Headings follow the HEADING type role instead of the browser's
        # default <h2> size.
        heading_font = role_font(TextRole.HEADING)
        heading_size = (
            f"{heading_font.pointSizeF()}pt"
            if heading_font.pointSizeF() > 0
            else f"{heading_font.pixelSize()}px"
        )
        document = browser.document()
        document.setDefaultStyleSheet(
            document.defaultStyleSheet()
            + f" h2 {{ font-size: {heading_size}; font-weight: 600;"
            f" margin-top: {SPACE_MD}px; margin-bottom: {SPACE_XS}px; }}"
        )
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
            f"<h2>{tr('Break timing')}</h2>"
            "<p>"
            + tr(
                "Short, frequent interruptions are better supported than one "
                "exact schedule. Controlled studies show stronger acute "
                "metabolic effects for light walking than for standing alone, "
                "but they do not prove that reminder software prevents "
                "long-term disease. Vulture therefore keeps timing and "
                "activities configurable."
            )
            + "</p>"
            f"<h2>{tr('Eye comfort guidance')}</h2>"
            "<p>"
            + tr(
                "Looking into the distance and blinking are low-risk comfort "
                "prompts. The 20-20-20 rule is widely recommended, but its "
                "exact numbers have limited trial support. Vulture does not "
                "claim that eye breaks treat dry eye or improve vision, and "
                "does not promote palming, eye yoga, or blue-light products."
            )
            + "</p>"
            f"<h2>{tr('Restorative pause guidance')}</h2>"
            "<p>"
            + tr(
                "Water reminders are neutral convenience cues rather than "
                "intake targets, and tea or coffee prompts are reasons to "
                "step away rather than recommendations to consume caffeine. "
                "The breathing and greenery options are based on promising "
                "individual trials, not established treatments."
            )
            + "</p>"
            f"<h2>{tr('Guidance sources')}</h2>"
            f"<ul>{source_html}</ul>"
            f"<h2>{tr('Media')}</h2>"
            f"<p>{catalog.media_provenance}</p>"
        )
        layout.addWidget(browser)
