from __future__ import annotations

import math
import time

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAccessible, QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
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
from .common import announce as speak
from .theme import (
    REST_PANEL_MIN_SIZE,
    SECTION_SPACING,
    SPACE_SM,
    SPACE_XS,
    CaptionLabel,
    Separator,
    TextRole,
    progress_bar_style,
    role_font,
    set_primary,
)


COMPLETION_ACK_MS = 3500
# Longer notes stay longer: about 250 ms a word, plus a second to notice.
ACK_MS_PER_WORD = 250
ACK_MS_TO_NOTICE = 1000
# A stopped-early break counts from 30 s, or a quarter of its suggested time
# when that is shorter, so a 20-second eye break still counts.
STOP_EARLY_FLOOR_SECONDS = 30
STOP_EARLY_FLOOR_SHARE = 0.25
# The countdown must be readable from across the room.
COUNTDOWN_SCALE = 2.5
# One spoken reminder before the end, never a per-second readout.
ANNOUNCE_REMAINING_SECONDS = 60


def assign_mnemonics(
    *buttons: QAbstractButton | QAction, taken: str = ""
) -> None:
    """Give each button or menu action an ``&`` mnemonic no sibling uses.

    Picks the first letter not taken yet, so translated labels get unique
    keys without every language needing its own hand-placed ``&``. Letters
    in ``taken`` belong to widgets outside this call and are skipped.
    """
    used = set(taken.lower())
    for button in buttons:
        text = button.text().replace("&", "")
        for index, char in enumerate(text):
            if char.isalnum() and char.lower() not in used:
                used.add(char.lower())
                button.setText(f"{text[:index]}&{text[index:]}")
                break


def announce(widget: QWidget, message: str) -> None:
    """Tell assistive technology about a state the user may not see.

    The description keeps the latest state readable on demand; the spoken
    announcement stays polite like every other one in the app.
    """
    widget.setAccessibleDescription(message)
    if QAccessible.isActive():
        speak(widget, message)


def format_countdown(seconds: float) -> str:
    total_seconds = max(0, int(seconds + 0.999))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    return f"{minutes}:{remaining_seconds:02d}"


def ack_interval_ms(text: str) -> int:
    """How long the acknowledgement stays: never less than the default."""
    reading = ACK_MS_TO_NOTICE + ACK_MS_PER_WORD * len(text.split())
    return max(COMPLETION_ACK_MS, reading)


def completion_message(breaks_today: int | None) -> str:
    if breaks_today is None:
        return tr("Nice work — break done.")
    if breaks_today == 1:
        return tr("Nice work — first break today.")
    return tr("Nice work — that's {count} breaks today.", count=breaks_today)


class AlternativeBreakPicker(QMenu):
    """The "Swap…" submenu for choosing a different kind of break."""

    choice_selected = Signal(str)

    def __init__(
        self,
        choices: tuple[ManualBreakChoice, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(tr("Swap…"), parent)
        self.setToolTipsVisible(True)
        self.menuAction().setToolTip(
            tr("Would another kind of break fit better?")
        )
        for choice in choices:
            action = self.addAction(manual_break_choice_label(choice))
            action.setData(choice.value)
        self.menuAction().setVisible(bool(choices))
        assign_mnemonics(*self.actions())
        self.triggered.connect(self._choice_triggered)

    def _choice_triggered(self, action: QAction) -> None:
        value = action.data()
        if isinstance(value, str):
            self.choice_selected.emit(value)


class RestBreakOutcome:
    COMPLETED = "completed"
    DISMISSED = "dismissed"
    SWITCHED = "switched"


class BreakPanel(QDialog):
    """The frame both break types share.

    Before Start there is one primary action and a "Not now" menu. While the
    timer runs only "Stop early" remains; at zero "Done" takes over. Done
    shows a calm completion card for ``COMPLETION_ACK_MS``, then accepts.

    Contract for the shell: ``completed_seconds``, ``active_break_title`` and
    ``remaining_seconds()``. Subclasses provide ``_skip`` and
    ``_choose_alternative`` (and ``_postpone`` when they offer Later).
    """

    # The shell collapses the camera workspace while a panel with this flag
    # sits in the side panel.
    wants_break_mode = True

    def __init__(
        self,
        title: str,
        duration_seconds: int | None,
        parent: QWidget | None = None,
        *,
        breaks_today: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.active_break_title = title
        self.completed_seconds = 0.0
        self._duration = duration_seconds or None
        self._started_at: float | None = None
        self._minute_announced = False

        self.countdown_block = QWidget()
        self.countdown = QLabel()
        self.countdown_caption = CaptionLabel(tr("suggested"))
        self.progress = QProgressBar()
        if self._duration:
            self._build_countdown_block(self._duration)

        self.completion_note = SemanticLabel(
            completion_message(breaks_today),
            tone="good",
            role=TextRole.HEADING,
        )
        self.completion_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # A click on the acknowledgement closes the panel early.
        self.completion_note.installEventFilter(self)
        self.completion_note.hide()

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
        # A fixed name: the ticking text must not be read out every second.
        self.countdown.setAccessibleName(tr("Time remaining"))
        block.addWidget(self.countdown)
        self.countdown_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        block.addWidget(self.countdown_caption)
        self.progress.setRange(0, seconds)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(SPACE_SM)
        self.progress.setStyleSheet(progress_bar_style())
        self.progress.setAccessibleName(tr("Break progress"))
        # An empty bar before Start reads as a stalled task.
        self.progress.hide()
        block.addSpacing(SPACE_XS)
        block.addWidget(self.progress)

    def _add_footer(
        self,
        layout: QVBoxLayout,
        alternative_choices: tuple[ManualBreakChoice, ...],
        *,
        offer_later: bool,
    ) -> None:
        # The acknowledgement takes the countdown's place when there is one.
        index = layout.indexOf(self.countdown_block)
        if index >= 0:
            layout.insertWidget(index + 1, self.completion_note)
        else:
            layout.addWidget(self.completion_note)
        layout.addWidget(Separator())
        self.actions = QWidget()
        row = QHBoxLayout(self.actions)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACE_SM)
        self.start_button = QPushButton(tr("Start"))
        self.start_button.clicked.connect(self._start)
        self.done_button = QPushButton(tr("Done"))
        self.done_button.clicked.connect(self._finish)
        self.stop_button = QPushButton(tr("Stop early"))
        self.stop_button.setToolTip(tr("Ends the break now. A very short break is not counted."))
        self.stop_button.clicked.connect(self._finish)
        self.not_now_button = QPushButton(tr("Not now"))
        self.not_now_menu = QMenu(self.not_now_button)
        menu_actions = []
        if offer_later:
            later = self.not_now_menu.addAction(tr("Later"))
            later.triggered.connect(self._postpone)
            menu_actions.append(later)
        skip = self.not_now_menu.addAction(tr("Skip"))
        skip.triggered.connect(self._skip)
        menu_actions.append(skip)
        self.alternative_picker = AlternativeBreakPicker(
            alternative_choices, self.not_now_menu
        )
        self.alternative_picker.choice_selected.connect(
            self._choose_alternative
        )
        self.not_now_menu.addMenu(self.alternative_picker)
        menu_actions.append(self.alternative_picker.menuAction())
        self.not_now_button.setMenu(self.not_now_menu)
        for button in (self.start_button, self.done_button, self.stop_button):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(self.not_now_button)
        layout.addWidget(self.actions)

        set_primary(self.start_button, True)
        set_primary(self.done_button, True)
        set_primary(self.stop_button, False)
        set_primary(self.not_now_button, False)
        self.done_button.hide()
        self.stop_button.hide()
        assign_mnemonics(
            self.start_button,
            self.done_button,
            self.stop_button,
            self.not_now_button,
        )
        assign_mnemonics(*menu_actions)

    def avoid_mnemonics(self, taken: str) -> None:
        """Re-pick the button keys, skipping letters the host window uses."""
        assign_mnemonics(
            self.start_button,
            self.done_button,
            self.stop_button,
            self.not_now_button,
            taken=taken,
        )

    # The contract the shell reads for its "On a break" card.
    def remaining_seconds(self) -> int | None:
        """Whole seconds left on a running timer, or None before Start.

        Also None during the acknowledgement: the break is over, so Esc
        reaches the panel and closes it early.
        """
        if (
            self._duration is None
            or self._started_at is None
            or self._ack_timer.isActive()
        ):
            return None
        return math.ceil(self._remaining())

    def _remaining(self) -> float:
        assert self._duration is not None and self._started_at is not None
        return max(0.0, self._started_at + self._duration - time.monotonic())

    def _start(self) -> None:
        if self._started_at is not None:
            return
        self._started_at = time.monotonic()
        self.start_button.hide()
        self.not_now_button.hide()
        if self._duration:
            self._minute_announced = self._duration <= ANNOUNCE_REMAINING_SECONDS
            self.countdown_caption.setText(tr("remaining"))
            self.countdown_block.show()
            self.progress.show()
            self.stop_button.show()
            self.stop_button.setFocus()
            self._timer.start()
            announce(
                self.countdown,
                tr(
                    "Timer started, {duration} to go.",
                    duration=format_duration(self._duration),
                ),
            )
        else:
            self.done_button.show()
            self.done_button.setFocus()
        self._started()
        self._update_countdown()

    def _started(self) -> None:
        """Hook for subclasses once Start was pressed."""

    def _time_up(self) -> None:
        """Hook for subclasses when the countdown reaches zero."""

    def _update_countdown(self) -> None:
        if self._duration is None or self._started_at is None:
            return
        remaining = self._remaining()
        self.countdown.setText(format_countdown(remaining))
        self.progress.setValue(round(self._duration - remaining))
        if (
            not self._minute_announced
            and remaining <= ANNOUNCE_REMAINING_SECONDS
        ):
            self._minute_announced = True
            if remaining > 0:
                announce(self.countdown, tr("One minute left."))
        if remaining > 0 or not self._timer.isActive():
            return
        self._timer.stop()
        self.countdown_caption.setText(tr("Suggested time complete"))
        self.done_button.show()
        if self.stop_button.hasFocus():
            self.done_button.setFocus()
        self.stop_button.hide()
        announce(self.countdown, tr("Suggested time complete"))
        self._time_up()

    def _stop_early_floor(self) -> float:
        return min(
            STOP_EARLY_FLOOR_SECONDS,
            STOP_EARLY_FLOOR_SHARE * (self._duration or 0),
        )

    def _record_completion(self) -> None:
        self._timer.stop()
        self.outcome = RestBreakOutcome.COMPLETED  # same value for movements
        if self._started_at is None:
            self.completed_seconds = float(self._duration or 0)
            return
        elapsed = time.monotonic() - self._started_at
        if not self._duration:
            self.completed_seconds = elapsed
            return
        if elapsed < self._stop_early_floor():
            # Too short to count: nothing is recorded, the reminder resets
            # like a skip.
            self.outcome = RestBreakOutcome.DISMISSED  # same for movements
            return
        self.completed_seconds = min(elapsed, float(self._duration))

    def _finish(self) -> None:
        """Acknowledge the finished break calmly, then close.

        The outcome is recorded immediately so closing the panel during the
        acknowledgement still logs the break as done. The note replaces the
        countdown; Esc or a click on it closes early. A static message keeps
        this free of animation, so there is nothing to reduce.
        """
        if self._ack_timer.isActive():
            return
        self._record_completion()
        if self.outcome != RestBreakOutcome.COMPLETED:
            self.completion_note.setText(
                tr(
                    "No problem — breaks under {seconds} seconds aren't "
                    "counted. The next one comes soon.",
                    seconds=math.ceil(self._stop_early_floor()),
                )
            )
            self.completion_note.set_semantic_tone("info")
        self.actions.setEnabled(False)
        self.countdown_block.hide()
        self.completion_note.show()
        announce(self.completion_note, self.completion_note.text())
        self._ack_timer.start(ack_interval_ms(self.completion_note.text()))

    def _complete(self) -> None:
        self._record_completion()
        self.accept()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            watched is self.completion_note
            and event.type() == QEvent.Type.MouseButtonRelease
            and self._ack_timer.isActive()
        ):
            self.accept()
            return True
        return super().eventFilter(watched, event)

    def reject(self) -> None:
        # Esc during the acknowledgement closes early, keeping the outcome.
        if self._ack_timer.isActive():
            self.accept()
            return
        super().reject()

    def done(self, result: int) -> None:
        self._timer.stop()
        self._ack_timer.stop()
        super().done(result)


class RestBreakDialog(BreakPanel):
    def __init__(
        self,
        prompt: ManualBreakPrompt,
        alternative_choices: tuple[ManualBreakChoice, ...],
        parent: QWidget | None = None,
        *,
        breaks_today: int | None = None,
    ) -> None:
        super().__init__(
            prompt.title,
            prompt.duration_seconds,
            parent,
            breaks_today=breaks_today,
        )
        self.prompt = prompt
        self.outcome = RestBreakOutcome.DISMISSED
        self.selected_choice: ManualBreakChoice | None = None
        self.setWindowTitle(prompt.title)
        self.setMinimumSize(REST_PANEL_MIN_SIZE)

        layout = QVBoxLayout(self)
        layout.setSpacing(SECTION_SPACING)
        # The countdown states the suggested time, so it is printed once.
        layout.addWidget(SemanticLabel(prompt.message, tone="info"))
        layout.addWidget(self.countdown_block)
        layout.addStretch(1)
        self._add_footer(layout, alternative_choices, offer_later=False)

    def _skip(self) -> None:
        self.outcome = RestBreakOutcome.DISMISSED
        self.reject()

    def _choose_alternative(self, choice_value: str) -> None:
        self.selected_choice = ManualBreakChoice(choice_value)
        self.outcome = RestBreakOutcome.SWITCHED
        self.reject()
