from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QCloseEvent
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

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
            video.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            layout.addWidget(video)
            self.player = QMediaPlayer(self)
            self.player.setVideoOutput(video)
            self.player.setSource(QUrl.fromLocalFile(str(media)))
            self.player.mediaStatusChanged.connect(self._loop_video)
            self.player.play()

        steps = ContentHeightTextBrowser()
        steps.setOpenExternalLinks(True)
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

        layout.addStretch(1)

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
