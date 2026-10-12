from __future__ import annotations

import re

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
from .break_options import BreakPanel
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
    SPACE_XS,
    TextRole,
    apply_text_role,
    role_font,
)


EXERCISE_POSTPONE_MINUTES = 10
MEDIA_HINT_WIDTH = 480
# A walk-away break leads with its timer; the clip is a small reminder loop.
THUMBNAIL_SHARE = 0.3

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


def general_safety(catalog: ExerciseCatalog, exercise: Exercise) -> str:
    """The catalog's general safety text, fitted to ``exercise``.

    The catalog writes it as: chair and floor, how to move, what to avoid,
    when to stop. The chair sentence only suits seated exercises, and the
    stop sentence repeats the per-exercise caution shown next to it.
    """
    sentences = re.split(r"(?<=[.!?])\s+", catalog.global_safety.strip())
    if len(sentences) < 3:
        return catalog.global_safety
    sentences = sentences[:-1]
    if "seated" not in exercise.tags:
        sentences = sentences[1:]
    return " ".join(sentences)


class ExerciseOutcome:
    COMPLETED = "completed"
    POSTPONED = "postponed"
    DISMISSED = "dismissed"
    SWAPPED = "swapped"
    ALTERNATIVE = "alternative"


class ExerciseDialog(BreakPanel):
    def __init__(
        self,
        exercise: Exercise,
        catalog: ExerciseCatalog,
        parent: QWidget | None = None,
        *,
        alternative_choices: tuple[ManualBreakChoice, ...] = (),
        show_full_safety: bool = False,
        breaks_today: int | None = None,
    ) -> None:
        duration = dose_duration_seconds(exercise.dose)
        super().__init__(
            exercise.title, duration, parent, breaks_today=breaks_today
        )
        self.exercise = exercise
        self.catalog = catalog
        self.show_full_safety = show_full_safety
        self.player: QMediaPlayer | None = None
        self.outcome = ExerciseOutcome.POSTPONED
        self.selected_choice: ManualBreakChoice | None = None
        self._set_count = None if duration else dose_set_count(exercise.dose)
        # A timed standing movement takes you away from the desk.
        self.walk_away = duration is not None and "standing" in exercise.tags
        self.setWindowTitle(
            tr("Movement break: {exercise}", exercise=exercise.title)
        )
        self.setMinimumWidth(PANEL_MIN_WIDTH)

        layout = QVBoxLayout(self)
        # Break mode is height-constrained, so the gaps use the tighter step.
        layout.setSpacing(CONTROL_SPACING)

        self.running_note = SemanticLabel(
            tr("Off you go. Come back when the timer ends."),
            tone="info",
        )
        self.running_note.hide()
        layout.addWidget(self.running_note)
        if self.walk_away:
            # Timer hero: the countdown leads, the clip is a reminder.
            layout.addWidget(self.countdown_block)

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
        self._thumbnail: MediaFrame | None = None
        frame: MediaFrame | None = None
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
            frame = MediaFrame(self.video)
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
            media_row.addWidget(
                self.playback_button, 0, Qt.AlignmentFlag.AlignLeft
            )
        dose = QLabel(exercise.dose)
        dose.setWordWrap(True)
        apply_text_role(dose, TextRole.BODY_STRONG)
        # "5 minutes" is already the countdown; print the time once.
        dose.setVisible(_DURATION_AT_END.match(exercise.dose) is None)
        media_row.addWidget(dose, 1)

        steps = ContentHeightTextBrowser()
        steps.setOpenExternalLinks(True)
        set_accessible_link_palette(steps)
        step_html = "".join(
            f"<li>{step}</li>" for step in exercise.steps
        )
        steps.setHtml(f"<ol>{step_html}</ol>")
        if self.walk_away:
            beside = QHBoxLayout()
            beside.setContentsMargins(0, 0, 0, 0)
            beside.setSpacing(SECTION_SPACING)
            if frame is not None and self.video is not None:
                self.video.setMinimumSize(1, 1)
                self._thumbnail = frame
                beside.addWidget(frame, 0, Qt.AlignmentFlag.AlignTop)
            beside.addWidget(steps, 1, Qt.AlignmentFlag.AlignTop)
            preview_layout.addLayout(beside)
            preview_layout.addLayout(media_row)
            layout.addWidget(self.preview)
        else:
            if frame is not None:
                preview_layout.addWidget(frame, 1)
            preview_layout.addLayout(media_row)
            preview_layout.addWidget(steps)
            # The preview (and its video) soaks up the spare height.
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

        if duration and not self.walk_away:
            layout.addWidget(self.countdown_block)

        self._general_safety = general_safety(catalog, exercise)
        self._short_safety_text = tr(
            "<b>Safety:</b> {safety}", safety=exercise.safety
        )
        self.safety = SemanticLabel(
            self._short_safety_text,
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
        self.global_safety = QLabel(self._general_safety)
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
        self._show_global_safety_inline(show_full_safety)

        layout.addStretch(1 if self.walk_away else 0)
        self._add_footer(layout, alternative_choices, offer_later=True)

        order = [
            self.video,
            self.playback_button if self.player is not None else None,
            *self.set_checkboxes,
            self.start_button,
            self.done_button,
            self.stop_button,
            self.not_now_button,
            self.details_toggle,
        ]
        order = [widget for widget in order if widget is not None]
        for first, second in zip(order, order[1:]):
            QWidget.setTabOrder(first, second)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._thumbnail is not None:
            self._thumbnail.setFixedWidth(
                round(self.width() * THUMBNAIL_SHARE)
            )

    def _started(self) -> None:
        if not self.walk_away:
            return
        # Hand over to the glanceable countdown; the clip is no longer
        # needed and would only spend CPU unseen.
        if self.player is not None:
            self.player.pause()
        self.preview.hide()
        self.running_note.show()

    def _time_up(self) -> None:
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

    def _show_global_safety_inline(self, inline: bool) -> None:
        """Show the general policy once: inline, or under the disclosure."""
        text = self._short_safety_text
        if inline:
            text += f"<br><br>{self._general_safety}"
        self.safety.setText(text)
        self.global_safety.setVisible(not inline)

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
            self._show_global_safety_inline(False)

    def _set_details_expanded(self, expanded: bool) -> None:
        self.details_panel.setVisible(expanded)
        self.details_toggle.setArrowType(
            Qt.ArrowType.DownArrow
            if expanded
            else Qt.ArrowType.RightArrow
        )
        self.updateGeometry()

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
        self.browser = browser = QTextBrowser()
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
        sections = [
            (
                "scope",
                tr("Scope"),
                "<p>"
                + tr(
                    "Vulture compares webcam landmarks with your own "
                    "calibration. It does not measure spinal anatomy, "
                    "diagnose a condition, or determine whether a posture "
                    "is medically safe."
                )
                + "</p>",
            ),
            (
                "exercise-policy",
                tr("Exercise policy"),
                f"<p>{catalog.medical_disclaimer}</p>"
                f"<p>{catalog.global_safety}</p>"
                "<p>"
                + tr(
                    "Movement doses are copied or conservatively selected "
                    "from the listed authoritative guidance. The trigger "
                    "timing is an explicit product setting rather than a "
                    "clinical prescription."
                )
                + "</p>",
            ),
            (
                "break-timing",
                tr("Break timing"),
                "<p>"
                + tr(
                    "Short, frequent interruptions are better supported "
                    "than one exact schedule. Controlled studies show "
                    "stronger acute metabolic effects for light walking "
                    "than for standing alone, but they do not prove that "
                    "reminder software prevents long-term disease. Vulture "
                    "therefore keeps timing and activities configurable."
                )
                + "</p>",
            ),
            (
                "eye-comfort",
                tr("Eye comfort guidance"),
                "<p>"
                + tr(
                    "Looking into the distance and blinking are low-risk "
                    "comfort prompts. The 20-20-20 rule is widely "
                    "recommended, but its exact numbers have limited trial "
                    "support. Vulture does not claim that eye breaks treat "
                    "dry eye or improve vision, and does not promote "
                    "palming, eye yoga, or blue-light products."
                )
                + "</p>",
            ),
            (
                "restorative-pauses",
                tr("Restorative pause guidance"),
                "<p>"
                + tr(
                    "Water reminders are neutral convenience cues rather "
                    "than intake targets, and tea or coffee prompts are "
                    "reasons to step away rather than recommendations to "
                    "consume caffeine. The breathing and greenery options "
                    "are based on promising individual trials, not "
                    "established treatments."
                )
                + "</p>",
            ),
            ("sources", tr("Guidance sources"), f"<ul>{source_html}</ul>"),
            ("media", tr("Media"), f"<p>{catalog.media_provenance}</p>"),
        ]
        # A short contents list; "#anchor" links scroll inside the browser.
        contents = " · ".join(
            f'<a href="#{anchor}">{title.replace(" ", "&nbsp;")}</a>'
            for anchor, title, _body in sections
        )
        browser.setHtml(
            f"<p><b>{tr('On this page')}</b><br>{contents}</p>"
            + "".join(
                f'<h2><a name="{anchor}"></a>{title}</h2>{body}'
                for anchor, title, body in sections
            )
        )
        layout.addWidget(browser)
