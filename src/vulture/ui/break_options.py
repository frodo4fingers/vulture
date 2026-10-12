from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QAccessible,
    QAccessibleAnnouncementEvent,
    QAction,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QToolButton,
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
    CONTROL_MIN_HEIGHT,
    CONTROL_SPACING,
    HAIRLINE,
    RADIUS_SM,
    REST_PANEL_MIN_SIZE,
    SECTION_SPACING,
    SPACE_LG,
    SPACE_SM,
    CaptionLabel,
    TextRole,
    apply_text_role,
)


# Qt has no "primary button" without a default button, and a default button
# lets a stray Enter complete a break. Mark the main action by colour instead,
# using the platform palette so both colour schemes stay legible.
_PRIMARY_BUTTON_STYLE = (
    "QPushButton {"
    " background-color: palette(highlight);"
    " color: palette(highlighted-text);"
    " font-weight: 600;"
    f" border: {HAIRLINE}px solid palette(highlight);"
    f" border-radius: {RADIUS_SM}px;"
    f" padding: 0 {SPACE_LG}px;"
    f" min-height: {CONTROL_MIN_HEIGHT}px;"
    " }"
    "QPushButton:focus {"
    f" border: {2 * HAIRLINE}px solid palette(text);"
    " }"
    "QPushButton:disabled {"
    " background-color: palette(mid);"
    " border-color: palette(mid);"
    " }"
)


def set_primary(button: QPushButton, primary: bool) -> None:
    """Visually emphasise ``button`` without making it a default button."""
    button.setAutoDefault(False)
    button.setDefault(False)
    button.setStyleSheet(_PRIMARY_BUTTON_STYLE if primary else "")


def assign_mnemonics(*buttons: QAbstractButton) -> None:
    """Give each button an ``&`` mnemonic no sibling uses.

    Picks the first letter not taken yet, so translated labels get unique
    keys without every language needing its own hand-placed ``&``.
    """
    used: set[str] = set()
    for button in buttons:
        text = button.text().replace("&", "")
        for index, char in enumerate(text):
            if char.isalnum() and char.lower() not in used:
                used.add(char.lower())
                button.setText(f"{text[:index]}&{text[index:]}")
                break


def announce(widget: QWidget, message: str) -> None:
    """Tell assistive technology about a state the user may not see."""
    widget.setAccessibleDescription(message)
    if QAccessible.isActive():
        event = QAccessibleAnnouncementEvent(widget, message)
        event.setPoliteness(QAccessible.AnnouncementPoliteness.Assertive)
        QAccessible.updateAccessibility(event)


def format_countdown(seconds: float) -> str:
    total_seconds = max(0, int(seconds + 0.999))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    return f"{minutes}:{remaining_seconds:02d}"


class AlternativeBreakPicker(QToolButton):
    """A small "Swap..." menu for choosing a different kind of break."""

    choice_selected = Signal(str)

    def __init__(
        self,
        choices: tuple[ManualBreakChoice, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setText(tr("Swap…"))
        self.setToolTip(tr("Would another kind of break fit better?"))
        self.setAccessibleName(tr("Choose a different break..."))
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu = QMenu(self)
        for choice in choices:
            action = self.menu.addAction(manual_break_choice_label(choice))
            action.setData(choice.value)
        self.menu.triggered.connect(self._choice_triggered)
        self.setMenu(self.menu)
        if not choices:
            self.hide()

    def _choice_triggered(self, action: QAction) -> None:
        value = action.data()
        if isinstance(value, str):
            self.choice_selected.emit(value)


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
        self.setMinimumSize(REST_PANEL_MIN_SIZE)

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
        self.countdown.setAccessibleName(tr("Time remaining"))
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

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(CONTROL_SPACING)
        self.start_button = QPushButton(tr("Start timer"))
        set_primary(self.start_button, True)
        self.start_button.clicked.connect(self._start_timer)
        actions.addWidget(self.start_button)
        self.done_button = QPushButton(tr("Done"))
        set_primary(self.done_button, False)
        self.done_button.clicked.connect(self._complete)
        actions.addWidget(self.done_button)
        actions.addStretch(1)
        self.alternative_picker = AlternativeBreakPicker(
            alternative_choices
        )
        self.alternative_picker.choice_selected.connect(
            self._switch_break
        )
        actions.addWidget(self.alternative_picker)
        skip_button = QPushButton(tr("Skip"))
        skip_button.setAutoDefault(False)
        skip_button.clicked.connect(self.reject)
        actions.addWidget(skip_button)
        layout.addLayout(actions)
        assign_mnemonics(
            self.start_button,
            self.done_button,
            self.alternative_picker,
            skip_button,
        )
        QWidget.setTabOrder(self.start_button, self.done_button)
        QWidget.setTabOrder(self.done_button, self.alternative_picker)
        QWidget.setTabOrder(self.alternative_picker, skip_button)

        self._deadline: float | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._update_countdown)

    @staticmethod
    def _format_countdown(seconds: float) -> str:
        return format_countdown(seconds)

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
        set_primary(self.start_button, False)
        set_primary(self.done_button, True)
        announce(self.countdown, tr("Suggested time complete"))

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
