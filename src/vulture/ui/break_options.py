from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vulture.breaks import (
    ManualBreakChoice,
    ManualBreakPrompt,
    manual_break_choice_label,
)
from vulture.i18n import tr

from .common import SemanticLabel, format_duration
from .theme import (
    CONTROL_SPACING,
    SECTION_SPACING,
    SPACE_SM,
    SPACE_XS,
    CaptionLabel,
    Separator,
    TextRole,
    apply_text_role,
)


class AlternativeBreakPicker(QWidget):
    choice_selected = Signal(str)

    def __init__(
        self,
        choices: tuple[ManualBreakChoice, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_XS)
        prompt = CaptionLabel(tr("Would another kind of break fit better?"))
        self.combo = QComboBox()
        self.combo.setAccessibleName(tr("Choose a different break..."))
        self.combo.addItem(tr("Choose a different break..."), None)
        for choice in choices:
            self.combo.addItem(
                manual_break_choice_label(choice),
                choice.value,
            )
        self.combo.activated.connect(self._choice_activated)
        layout.addWidget(prompt)
        layout.addWidget(self.combo)

    def _choice_activated(self, index: int) -> None:
        value = self.combo.itemData(index)
        if not isinstance(value, str):
            return
        self.choice_selected.emit(value)
        self.combo.setCurrentIndex(0)


class RestBreakOutcome:
    COMPLETED = "completed"
    DISMISSED = "dismissed"
    SWITCHED = "switched"


class RestBreakDialog(QDialog):
    def __init__(
        self,
        prompt: ManualBreakPrompt,
        alternative_choices: tuple[ManualBreakChoice, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.prompt = prompt
        self.outcome = RestBreakOutcome.DISMISSED
        self.selected_choice: ManualBreakChoice | None = None
        self.setWindowTitle(prompt.title)
        self.setMinimumSize(440, 360)

        layout = QVBoxLayout(self)
        layout.setSpacing(SECTION_SPACING)
        duration = QLabel(
            tr(
                "<b>Suggested time:</b> {duration}",
                duration=format_duration(prompt.duration_seconds),
            )
        )
        duration.setWordWrap(True)
        layout.addWidget(duration)
        message = SemanticLabel(prompt.message, tone="info")
        layout.addWidget(message)

        countdown_block = QVBoxLayout()
        countdown_block.setContentsMargins(0, SPACE_SM, 0, 0)
        countdown_block.setSpacing(0)
        self.countdown = QLabel(
            self._format_countdown(prompt.duration_seconds)
        )
        apply_text_role(self.countdown, TextRole.DISPLAY)
        self.countdown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        countdown_block.addWidget(self.countdown)
        self.countdown_caption = CaptionLabel(tr("suggested"))
        self.countdown_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        countdown_block.addWidget(self.countdown_caption)
        layout.addLayout(countdown_block)
        self.progress = QProgressBar()
        self.progress.setRange(0, prompt.duration_seconds)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(SPACE_SM)
        self.progress.setAccessibleName(tr("Break progress"))
        layout.addWidget(self.progress)
        layout.addStretch(1)

        layout.addWidget(Separator())
        self.alternative_picker = AlternativeBreakPicker(
            alternative_choices
        )
        self.alternative_picker.choice_selected.connect(
            self._switch_break
        )
        layout.addWidget(self.alternative_picker)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(CONTROL_SPACING)
        self.start_button = QPushButton(tr("Start timer"))
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self._start_timer)
        actions.addWidget(self.start_button)
        self.done_button = QPushButton(tr("Done"))
        self.done_button.setAutoDefault(False)
        self.done_button.clicked.connect(self._complete)
        actions.addWidget(self.done_button)
        actions.addStretch(1)
        skip_button = QPushButton(tr("Skip"))
        skip_button.setAutoDefault(False)
        skip_button.clicked.connect(self.reject)
        actions.addWidget(skip_button)
        layout.addLayout(actions)

        self._deadline: float | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._update_countdown)

    @staticmethod
    def _format_countdown(seconds: float) -> str:
        total_seconds = max(0, int(seconds + 0.999))
        minutes, remaining_seconds = divmod(total_seconds, 60)
        return f"{minutes}:{remaining_seconds:02d}"

    def _start_timer(self) -> None:
        self._deadline = time.monotonic() + self.prompt.duration_seconds
        self.start_button.setEnabled(False)
        self.start_button.setText(tr("Timer running"))
        self.countdown_caption.setText(tr("remaining"))
        self._timer.start()
        self._update_countdown()

    def _update_countdown(self) -> None:
        if self._deadline is None:
            return
        remaining = max(0.0, self._deadline - time.monotonic())
        elapsed = self.prompt.duration_seconds - remaining
        self.countdown.setText(self._format_countdown(remaining))
        self.progress.setValue(round(elapsed))
        if remaining > 0:
            return
        self._timer.stop()
        self.countdown_caption.setText(tr("Suggested time complete"))
        self.start_button.setText(tr("Timer complete"))
        self.done_button.setDefault(True)

    def _complete(self) -> None:
        self.outcome = RestBreakOutcome.COMPLETED
        self.accept()

    def _switch_break(self, choice_value: str) -> None:
        self.selected_choice = ManualBreakChoice(choice_value)
        self.outcome = RestBreakOutcome.SWITCHED
        self.reject()

    def done(self, result: int) -> None:
        self._timer.stop()
        super().done(result)
