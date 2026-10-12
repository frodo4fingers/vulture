from __future__ import annotations

from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vulture.i18n import LANGUAGE_NAMES, tr
from vulture.models import (
    AlertPolicy,
    BreakPreferences,
    ExercisePreferences,
    HistoryPreferences,
    InterfaceLanguage,
)

from .common import SemanticLabel
from .theme import (
    CONTROL_SPACING,
    NESTED_INDENT,
    SECTION_SPACING,
    SPACE_XS,
    WINDOW_MARGIN,
    CaptionLabel,
    Separator,
    TextRole,
    apply_text_role,
)


def _spin(
    low: int,
    high: int,
    value: float,
    suffix: str,
) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(low, high)
    spin.setValue(round(value))
    spin.setSuffix(suffix)
    return spin


def _check(text: str, checked: bool) -> QCheckBox:
    box = QCheckBox(text)
    box.setChecked(checked)
    return box


def _heading(box: QCheckBox) -> QCheckBox:
    apply_text_role(box, TextRole.BODY_STRONG)
    return box


def _hinted(control: QWidget, hint: str) -> QWidget:
    """A control with a one-line helper caption underneath."""
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SPACE_XS)
    layout.addWidget(control, 0, Qt.AlignmentFlag.AlignLeft)
    layout.addWidget(CaptionLabel(hint))
    control.setAccessibleDescription(hint)
    return holder


def _form() -> QFormLayout:
    form = QFormLayout()
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setVerticalSpacing(CONTROL_SPACING)
    return form


def _row(
    form: QFormLayout,
    text: str,
    field: QWidget,
    control: QWidget | None = None,
) -> None:
    """Add a form row whose label is bound to ``control`` (default ``field``).

    The buddy gives the control its accessible name and, when the label text
    has an ``&``, an Alt mnemonic. Repeated labels carry no ``&``.
    """
    label = QLabel(text)
    label.setBuddy(control or field)
    form.addRow(label, field)


def _disclosure(text: str, body: QWidget) -> QToolButton:
    """A "Customize..." toggle that reveals ``body``."""
    button = QToolButton()
    button.setText(text)
    button.setCheckable(True)
    button.setAutoRaise(True)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    button.setArrowType(Qt.ArrowType.RightArrow)
    body.setVisible(False)

    def toggle(expanded: bool) -> None:
        button.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        body.setVisible(expanded)

    button.toggled.connect(toggle)
    return button


class SettingsDialog(QDialog):
    def __init__(
        self,
        policy: AlertPolicy,
        preferences: ExercisePreferences,
        history_preferences: HistoryPreferences,
        language: InterfaceLanguage,
        parent: QWidget | None = None,
        *,
        break_preferences: BreakPreferences | None = None,
        start_at_login_enabled: bool = False,
        startup_setting_available: bool = True,
        startup_setting_error: str | None = None,
        calibration_sound_cues: bool = True,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(tr("Vulture settings"))
        self.setMinimumSize(440, 420)
        self.resize(620, 640)
        break_preferences = break_preferences or BreakPreferences()

        outer_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        outer_layout.addWidget(self.tabs, 1)

        # Posture
        layout = self._add_page(tr("Posture"))
        alert_form = _form()
        self.warning_seconds = _spin(
            2, 300, policy.warning_after_seconds, tr(" seconds")
        )
        self.alert_seconds = _spin(
            5, 900, policy.alert_after_seconds, tr(" seconds")
        )
        self.transition_buffer_seconds = _spin(
            0, 30, policy.posture_transition_buffer_seconds, tr(" seconds")
        )
        self.repeat_count = _spin(
            2, 20, policy.repeated_reminders_for_break, tr(" reminders")
        )
        self.repeat_window = _spin(
            5, 120, policy.repeated_reminder_window_minutes, tr(" minutes")
        )
        _row(
            alert_form,
            tr("&Nudge me after"),
            _hinted(
                self.warning_seconds,
                tr("A gentle nudge on screen once your posture has been "
                   "drifting this long."),
            ),
            self.warning_seconds,
        )
        _row(
            alert_form,
            tr("Send a no&tification after"),
            _hinted(
                self.alert_seconds,
                tr("A desktop notification if you are still drifting. Must "
                   "be longer than the nudge delay."),
            ),
            self.alert_seconds,
        )
        _row(
            alert_form,
            tr("&Ignore quick changes for"),
            _hinted(
                self.transition_buffer_seconds,
                tr("Shifting or stretching briefly will not count as "
                   "drifting."),
            ),
            self.transition_buffer_seconds,
        )
        _row(
            alert_form,
            tr("Su&ggest an exercise after"),
            _hinted(
                self.repeat_count,
                tr("Repeated reminders add up to an exercise suggestion."),
            ),
            self.repeat_count,
        )
        _row(
            alert_form,
            tr("&Counted over the last"),
            _hinted(
                self.repeat_window,
                tr("Older reminders stop counting."),
            ),
            self.repeat_window,
        )
        layout.addLayout(alert_form)

        layout.addWidget(Separator())
        exercise_label = QLabel(tr("Exercise accessibility"))
        apply_text_role(exercise_label, TextRole.BODY_STRONG)
        layout.addWidget(exercise_label)
        self.seated_only = _check(
            tr("Only show seated movements"), preferences.seated_only
        )
        self.allow_balance = _check(
            tr("Allow movements that require standing balance"),
            preferences.allow_balance_exercises,
        )
        self.allow_strength = _check(
            tr("Allow light strength movements such as sit-to-stand"),
            preferences.allow_strength_exercises,
        )
        layout.addWidget(self.seated_only)
        layout.addWidget(self.allow_balance)
        layout.addWidget(self.allow_strength)
        layout.addStretch(1)

        # Breaks
        layout = self._add_page(tr("Breaks"))
        self.break_reminders_enabled = _heading(
            _check(
                tr("Remind me to take breaks"),
                break_preferences.enabled,
            )
        )
        layout.addWidget(self.break_reminders_enabled)
        layout.addWidget(
            CaptionLabel(
                tr(
                    "Good posture can still be too static. Each reminder "
                    "rotates through your chosen suggestions without repeats."
                )
            )
        )

        self.movement_reminders_enabled = _heading(
            _check(
                tr("Movement and position changes"),
                break_preferences.movement_reminders_enabled,
            )
        )
        layout.addWidget(Separator())
        layout.addWidget(self.movement_reminders_enabled)
        self.movement_controls = QWidget()
        movement_layout = QVBoxLayout(self.movement_controls)
        movement_layout.setContentsMargins(NESTED_INDENT, 0, 0, 0)
        movement_form = _form()
        self.movement_interval_minutes = _spin(
            20, 180, break_preferences.movement_interval_minutes,
            tr(" minutes"),
        )
        self.movement_duration_minutes = _spin(
            1, 10, break_preferences.movement_duration_minutes,
            tr(" minutes"),
        )
        self.away_reset_minutes = _spin(
            1, 30, break_preferences.away_reset_minutes, tr(" minutes")
        )
        _row(movement_form, tr("Every"), self.movement_interval_minutes)
        _row(
            movement_form,
            tr("Suggested length"),
            self.movement_duration_minutes,
        )
        movement_layout.addLayout(movement_form)
        walking_label = (
            tr("Walk away, refill water, or make tea or coffee")
            if break_preferences.legacy_walk_includes_drinks
            else tr("Take an easy walk")
        )
        self.suggest_position_change = _check(
            tr("Change sitting position"),
            break_preferences.suggest_position_change,
        )
        self.suggest_standing = _check(
            tr("Stand up"), break_preferences.suggest_standing
        )
        self.suggest_walking = _check(
            walking_label, break_preferences.suggest_walking
        )
        self.suggest_guided_exercise = _check(
            tr("Open one of the existing guided movements"),
            break_preferences.suggest_guided_exercise,
        )
        movement_customize = self._add_customize(
            movement_layout,
            self.suggest_position_change,
            self.suggest_standing,
            self.suggest_walking,
            self.suggest_guided_exercise,
        )
        layout.addWidget(self.movement_controls)
        self.sedentary_minutes = self.movement_interval_minutes

        self.eye_reminders_enabled = _heading(
            _check(tr("Eye comfort"), break_preferences.eye_reminders_enabled)
        )
        layout.addWidget(Separator())
        layout.addWidget(self.eye_reminders_enabled)
        self.eye_controls = QWidget()
        eye_layout = QVBoxLayout(self.eye_controls)
        eye_layout.setContentsMargins(NESTED_INDENT, 0, 0, 0)
        eye_form = _form()
        self.eye_interval_minutes = _spin(
            10, 60, break_preferences.eye_interval_minutes, tr(" minutes")
        )
        self.eye_duration_seconds = _spin(
            10, 120, break_preferences.eye_duration_seconds, tr(" seconds")
        )
        _row(eye_form, tr("Every"), self.eye_interval_minutes)
        _row(eye_form, tr("Look &away for"), self.eye_duration_seconds)
        eye_layout.addLayout(eye_form)
        self.suggest_nature_view = _check(
            tr("Look toward distant greenery when available"),
            break_preferences.suggest_nature_view,
        )
        self.suggest_blinking = _check(
            tr("Add five slow, complete blinks"),
            break_preferences.suggest_blinking,
        )
        self.suggest_closed_eye_rest = _check(
            tr("Offer a gentle closed-eye rest"),
            break_preferences.suggest_closed_eye_rest,
        )
        eye_customize = self._add_customize(
            eye_layout,
            self.suggest_nature_view,
            self.suggest_blinking,
            self.suggest_closed_eye_rest,
        )
        layout.addWidget(self.eye_controls)

        self.hydration_reminders_enabled = _heading(
            _check(
                tr("Water reminder"),
                break_preferences.hydration_reminders_enabled,
            )
        )
        layout.addWidget(Separator())
        layout.addWidget(self.hydration_reminders_enabled)
        self.hydration_controls = QWidget()
        hydration_layout = QVBoxLayout(self.hydration_controls)
        hydration_layout.setContentsMargins(NESTED_INDENT, 0, 0, 0)
        hydration_form = _form()
        self.hydration_interval_minutes = _spin(
            20, 240, break_preferences.hydration_interval_minutes,
            tr(" minutes"),
        )
        self.hydration_duration_seconds = _spin(
            15, 180, break_preferences.hydration_duration_seconds,
            tr(" seconds"),
        )
        _row(hydration_form, tr("Every"), self.hydration_interval_minutes)
        _row(
            hydration_form,
            tr("Suggested length"),
            self.hydration_duration_seconds,
        )
        hydration_layout.addLayout(hydration_form)
        layout.addWidget(self.hydration_controls)

        self.reset_reminders_enabled = _heading(
            _check(
                tr("Longer reset"),
                break_preferences.reset_reminders_enabled,
            )
        )
        layout.addWidget(Separator())
        layout.addWidget(self.reset_reminders_enabled)
        self.reset_controls = QWidget()
        reset_layout = QVBoxLayout(self.reset_controls)
        reset_layout.setContentsMargins(NESTED_INDENT, 0, 0, 0)
        reset_form = _form()
        self.reset_interval_minutes = _spin(
            30, 240, break_preferences.reset_interval_minutes,
            tr(" minutes"),
        )
        self.reset_duration_minutes = _spin(
            1, 15, break_preferences.reset_duration_minutes, tr(" minutes")
        )
        _row(reset_form, tr("Every"), self.reset_interval_minutes)
        _row(
            reset_form,
            tr("Suggested length"),
            self.reset_duration_minutes,
        )
        reset_layout.addLayout(reset_form)
        self.suggest_tea_or_coffee = _check(
            tr("Make tea or coffee"), break_preferences.suggest_tea_or_coffee
        )
        self.suggest_reset_walking = _check(
            tr("Take an easy walk"), break_preferences.suggest_reset_walking
        )
        self.suggest_breathing_reset = _check(
            tr("Take a slower breathing reset"),
            break_preferences.suggest_breathing_reset,
        )
        self.suggest_offscreen_reset = _check(
            tr("Take a full off-screen reset"),
            break_preferences.suggest_offscreen_reset,
        )
        self.suggest_reset_guided_exercise = _check(
            tr("Open a guided movement"),
            break_preferences.suggest_reset_guided_exercise,
        )
        reset_customize = self._add_customize(
            reset_layout,
            self.suggest_tea_or_coffee,
            self.suggest_reset_walking,
            self.suggest_breathing_reset,
            self.suggest_offscreen_reset,
            self.suggest_reset_guided_exercise,
        )
        layout.addWidget(self.reset_controls)

        evidence_note = CaptionLabel(
            tr(
                "Short, frequent movement breaks have stronger support "
                "than any exact schedule, and light walking has stronger "
                "acute evidence than standing alone. The 20-20-20 eye "
                "rule is widely recommended, but its exact timing has "
                "limited trial evidence. Water and longer-reset "
                "intervals are convenience defaults, not intake or "
                "treatment prescriptions."
            )
        )
        evidence_toggle = _disclosure(
            tr("Why these intervals?"), evidence_note
        )
        layout.addWidget(evidence_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(evidence_note)
        layout.addStretch(1)

        for toggle in (
            self.break_reminders_enabled,
            self.movement_reminders_enabled,
            self.eye_reminders_enabled,
            self.hydration_reminders_enabled,
            self.reset_reminders_enabled,
        ):
            toggle.toggled.connect(self._sync_break_controls)
        self._sync_break_controls()

        # Privacy & data
        layout = self._add_page(tr("Privacy & data"))
        layout.addWidget(
            SemanticLabel(
                tr(
                    "<b>Private by design:</b> camera frames are analyzed "
                    "locally and discarded immediately. Stored workday "
                    "history contains only posture labels, reminder stages, "
                    "setups, timestamps, and durations."
                ),
                tone="info",
                role=TextRole.CAPTION,
            )
        )
        self.save_history = _check(
            tr("Save local posture categories and durations"),
            history_preferences.enabled,
        )
        self.history_retention_days = _spin(
            1, 365, history_preferences.retention_days, tr(" days")
        )
        self.history_retention_days.setEnabled(history_preferences.enabled)
        self.save_history.toggled.connect(
            self.history_retention_days.setEnabled
        )
        layout.addWidget(self.save_history)
        history_form = _form()
        _row(
            history_form,
            tr("&Keep summaries for"),
            self.history_retention_days,
        )
        layout.addLayout(history_form)
        layout.addWidget(
            CaptionLabel(
                tr(
                    "Workday history contains labels and durations only, "
                    "never camera frames or landmark coordinates."
                )
            )
        )
        layout.addStretch(1)

        # General
        layout = self._add_page(tr("General"))
        interface_form = _form()
        self.language_combo = QComboBox()
        for choice, label in LANGUAGE_NAMES.items():
            self.language_combo.addItem(label, choice.value)
        selected_index = self.language_combo.findData(language.value)
        if selected_index >= 0:
            self.language_combo.setCurrentIndex(selected_index)
        _row(interface_form, tr("&Language"), self.language_combo)
        layout.addLayout(interface_form)
        self.start_at_login = _check(
            tr("Start Vulture when I sign in"), start_at_login_enabled
        )
        self.start_at_login.setEnabled(startup_setting_available)
        if not startup_setting_available:
            self.start_at_login.setToolTip(
                tr(
                    "The system startup setting is unavailable on this "
                    "computer."
                )
            )
        layout.addWidget(self.start_at_login)
        if startup_setting_error:
            layout.addWidget(
                SemanticLabel(startup_setting_error, tone="safety")
            )
        self.calibration_sound_cues = _check(
            tr("Play sound cues during calibration"),
            calibration_sound_cues,
        )
        layout.addWidget(self.calibration_sound_cues)
        layout.addStretch(1)

        self.feedback_label = SemanticLabel(tone="safety")
        self.feedback_label.setAccessibleName(tr("Invalid settings"))
        self.feedback_label.hide()
        outer_layout.addWidget(self.feedback_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        outer_layout.addWidget(buttons)
        # Tab order follows the visual order, one chain across every tab:
        # widgets on hidden pages are skipped.
        order = [
            self.tabs,
            self.warning_seconds,
            self.alert_seconds,
            self.transition_buffer_seconds,
            self.repeat_count,
            self.repeat_window,
            self.seated_only,
            self.allow_balance,
            self.allow_strength,
            self.break_reminders_enabled,
            self.movement_reminders_enabled,
            self.movement_interval_minutes,
            self.movement_duration_minutes,
            movement_customize,
            self.suggest_position_change,
            self.suggest_standing,
            self.suggest_walking,
            self.suggest_guided_exercise,
            self.eye_reminders_enabled,
            self.eye_interval_minutes,
            self.eye_duration_seconds,
            eye_customize,
            self.suggest_nature_view,
            self.suggest_blinking,
            self.suggest_closed_eye_rest,
            self.hydration_reminders_enabled,
            self.hydration_interval_minutes,
            self.hydration_duration_seconds,
            self.reset_reminders_enabled,
            self.reset_interval_minutes,
            self.reset_duration_minutes,
            reset_customize,
            self.suggest_tea_or_coffee,
            self.suggest_reset_walking,
            self.suggest_breathing_reset,
            self.suggest_offscreen_reset,
            self.suggest_reset_guided_exercise,
            evidence_toggle,
            self.save_history,
            self.history_retention_days,
            self.language_combo,
            self.start_at_login,
            self.calibration_sound_cues,
            *buttons.buttons(),
        ]
        for current, following in zip(order, order[1:]):
            self.setTabOrder(current, following)
        self._policy = policy
        self._break_preferences = break_preferences
        self._preferences = preferences
        self._history_preferences = history_preferences
        self._language = language
        self._startup_setting_available = startup_setting_available

    def _add_page(self, title: str) -> QVBoxLayout:
        """Add a tab whose content scrolls only if the window is tiny."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(
            WINDOW_MARGIN, WINDOW_MARGIN, WINDOW_MARGIN, WINDOW_MARGIN
        )
        layout.setSpacing(SECTION_SPACING)
        scroll.setWidget(content)
        # "&" would otherwise become a mnemonic marker and vanish.
        self.tabs.addTab(scroll, title.replace("&", "&&"))
        if not hasattr(self, "scroll_area"):
            self.scroll_area = scroll
        return layout

    @staticmethod
    def _add_customize(
        layout: QVBoxLayout,
        *options: QCheckBox,
    ) -> QToolButton:
        """Hide a channel's shuffle checklist behind a disclosure."""
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(NESTED_INDENT, 0, 0, 0)
        body_layout.addWidget(QLabel(tr("Shuffle suggestions between")))
        for option in options:
            body_layout.addWidget(option)
        button = _disclosure(tr("Customize…"), body)
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(body)
        return button

    def _sync_break_controls(self) -> None:
        enabled = self.break_reminders_enabled.isChecked()
        self.movement_reminders_enabled.setEnabled(enabled)
        self.eye_reminders_enabled.setEnabled(enabled)
        self.hydration_reminders_enabled.setEnabled(enabled)
        self.reset_reminders_enabled.setEnabled(enabled)
        self.movement_controls.setEnabled(
            enabled and self.movement_reminders_enabled.isChecked()
        )
        self.eye_controls.setEnabled(
            enabled and self.eye_reminders_enabled.isChecked()
        )
        self.hydration_controls.setEnabled(
            enabled and self.hydration_reminders_enabled.isChecked()
        )
        self.reset_controls.setEnabled(
            enabled and self.reset_reminders_enabled.isChecked()
        )

    def _show_error(self, message: str, tab: int) -> None:
        self.tabs.setCurrentIndex(tab)
        self.feedback_label.setText(message)
        self.feedback_label.show()

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
                sedentary_break_minutes=(
                    self.movement_interval_minutes.value()
                ),
            )
        except ValidationError:
            self._show_error(
                tr(
                    "The notification delay must be longer than the nudge "
                    "delay."
                ),
                0,
            )
            return
        try:
            self._break_preferences = BreakPreferences(
                enabled=self.break_reminders_enabled.isChecked(),
                movement_reminders_enabled=(
                    self.movement_reminders_enabled.isChecked()
                ),
                movement_interval_minutes=(
                    self.movement_interval_minutes.value()
                ),
                movement_duration_minutes=(
                    self.movement_duration_minutes.value()
                ),
                away_reset_minutes=self.away_reset_minutes.value(),
                suggest_position_change=(
                    self.suggest_position_change.isChecked()
                ),
                suggest_standing=self.suggest_standing.isChecked(),
                suggest_walking=self.suggest_walking.isChecked(),
                legacy_walk_includes_drinks=(
                    self._break_preferences.legacy_walk_includes_drinks
                    and self.suggest_walking.isChecked()
                    and not self.hydration_reminders_enabled.isChecked()
                    and not self.reset_reminders_enabled.isChecked()
                ),
                suggest_guided_exercise=(
                    self.suggest_guided_exercise.isChecked()
                ),
                eye_reminders_enabled=(
                    self.eye_reminders_enabled.isChecked()
                ),
                eye_interval_minutes=self.eye_interval_minutes.value(),
                eye_duration_seconds=self.eye_duration_seconds.value(),
                suggest_nature_view=(
                    self.suggest_nature_view.isChecked()
                ),
                suggest_blinking=self.suggest_blinking.isChecked(),
                suggest_closed_eye_rest=(
                    self.suggest_closed_eye_rest.isChecked()
                ),
                hydration_reminders_enabled=(
                    self.hydration_reminders_enabled.isChecked()
                ),
                hydration_interval_minutes=(
                    self.hydration_interval_minutes.value()
                ),
                hydration_duration_seconds=(
                    self.hydration_duration_seconds.value()
                ),
                reset_reminders_enabled=(
                    self.reset_reminders_enabled.isChecked()
                ),
                reset_interval_minutes=(
                    self.reset_interval_minutes.value()
                ),
                reset_duration_minutes=(
                    self.reset_duration_minutes.value()
                ),
                suggest_tea_or_coffee=(
                    self.suggest_tea_or_coffee.isChecked()
                ),
                suggest_reset_walking=(
                    self.suggest_reset_walking.isChecked()
                ),
                suggest_breathing_reset=(
                    self.suggest_breathing_reset.isChecked()
                ),
                suggest_offscreen_reset=(
                    self.suggest_offscreen_reset.isChecked()
                ),
                suggest_reset_guided_exercise=(
                    self.suggest_reset_guided_exercise.isChecked()
                ),
            )
        except ValidationError:
            self._show_error(
                tr(
                    "Enable at least one break channel, and keep at least one "
                    "suggestion in each enabled movement or longer-reset "
                    "channel."
                ),
                1,
            )
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
        BreakPreferences,
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
            self._break_preferences,
        )
