from __future__ import annotations

from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
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
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(tr("Vulture settings"))
        self.setMinimumSize(440, 420)
        self.resize(620, 640)
        break_preferences = break_preferences or BreakPreferences()

        outer_layout = QVBoxLayout(self)
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

        alert_group = QGroupBox(tr("Posture reminders"))
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
        layout.addWidget(alert_group)

        break_group = QGroupBox(tr("Break management"))
        break_group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        break_layout = QVBoxLayout(break_group)
        break_intro = SemanticLabel(
            tr(
                "Good posture can still be too static. Vulture can remind "
                "you to vary position, rest your eyes, drink, or step fully "
                "away even when posture tracking is green."
            ),
            tone="info",
        )
        break_layout.addWidget(break_intro)

        self.break_reminders_enabled = QCheckBox(
            tr("Enable independent break reminders")
        )
        self.break_reminders_enabled.setChecked(
            break_preferences.enabled
        )
        break_layout.addWidget(self.break_reminders_enabled)
        shuffle_note = QLabel(
            tr(
                "Within each channel, enabled suggestions are shuffled "
                "without repeats until every option has appeared."
            )
        )
        shuffle_note.setWordWrap(True)
        break_layout.addWidget(shuffle_note)

        self.movement_reminders_enabled = QCheckBox(
            tr("Movement and position changes")
        )
        movement_heading_font = self.movement_reminders_enabled.font()
        movement_heading_font.setBold(True)
        self.movement_reminders_enabled.setFont(movement_heading_font)
        self.movement_reminders_enabled.setChecked(
            break_preferences.movement_reminders_enabled
        )
        break_layout.addWidget(self.movement_reminders_enabled)

        self.movement_controls = QWidget()
        movement_layout = QVBoxLayout(self.movement_controls)
        movement_layout.setContentsMargins(22, 0, 0, 0)
        movement_form = QFormLayout()
        movement_form.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapLongRows
        )
        self.movement_interval_minutes = QSpinBox()
        self.movement_interval_minutes.setRange(20, 180)
        self.movement_interval_minutes.setValue(
            break_preferences.movement_interval_minutes
        )
        self.movement_interval_minutes.setSuffix(tr(" minutes"))
        self.movement_interval_minutes.setToolTip(
            tr("Vulture counts only time with valid posture tracking.")
        )
        self.movement_duration_minutes = QSpinBox()
        self.movement_duration_minutes.setRange(1, 10)
        self.movement_duration_minutes.setValue(
            break_preferences.movement_duration_minutes
        )
        self.movement_duration_minutes.setSuffix(tr(" minutes"))
        self.away_reset_minutes = QSpinBox()
        self.away_reset_minutes.setRange(1, 30)
        self.away_reset_minutes.setValue(
            break_preferences.away_reset_minutes
        )
        self.away_reset_minutes.setSuffix(tr(" minutes"))
        self.away_reset_minutes.setToolTip(
            tr(
                "After this much time away from the camera, Vulture starts "
                "a fresh break interval."
            )
        )
        movement_form.addRow(tr("Every"), self.movement_interval_minutes)
        movement_form.addRow(
            tr("Suggested length"),
            self.movement_duration_minutes,
        )
        movement_form.addRow(
            tr("Away time that resets the timer"),
            self.away_reset_minutes,
        )
        movement_layout.addLayout(movement_form)

        movement_options_label = QLabel(tr("Shuffle suggestions between"))
        movement_options_font = movement_options_label.font()
        movement_options_font.setBold(True)
        movement_options_label.setFont(movement_options_font)
        movement_layout.addWidget(movement_options_label)
        self.suggest_position_change = QCheckBox(
            tr("Change sitting position")
        )
        self.suggest_position_change.setChecked(
            break_preferences.suggest_position_change
        )
        self.suggest_standing = QCheckBox(tr("Stand up"))
        self.suggest_standing.setChecked(
            break_preferences.suggest_standing
        )
        walking_label = (
            tr("Walk away, refill water, or make tea or coffee")
            if break_preferences.legacy_walk_includes_drinks
            else tr("Take an easy walk")
        )
        self.suggest_walking = QCheckBox(walking_label)
        self.suggest_walking.setChecked(
            break_preferences.suggest_walking
        )
        self.suggest_guided_exercise = QCheckBox(
            tr("Open one of the existing guided movements")
        )
        self.suggest_guided_exercise.setChecked(
            break_preferences.suggest_guided_exercise
        )
        movement_layout.addWidget(self.suggest_position_change)
        movement_layout.addWidget(self.suggest_standing)
        movement_layout.addWidget(self.suggest_walking)
        movement_layout.addWidget(self.suggest_guided_exercise)
        break_layout.addWidget(self.movement_controls)
        self.sedentary_minutes = self.movement_interval_minutes

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        break_layout.addWidget(divider)

        self.eye_reminders_enabled = QCheckBox(tr("Eye comfort"))
        eye_heading_font = self.eye_reminders_enabled.font()
        eye_heading_font.setBold(True)
        self.eye_reminders_enabled.setFont(eye_heading_font)
        self.eye_reminders_enabled.setChecked(
            break_preferences.eye_reminders_enabled
        )
        break_layout.addWidget(self.eye_reminders_enabled)

        self.eye_controls = QWidget()
        eye_layout = QVBoxLayout(self.eye_controls)
        eye_layout.setContentsMargins(22, 0, 0, 0)
        eye_form = QFormLayout()
        eye_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.eye_interval_minutes = QSpinBox()
        self.eye_interval_minutes.setRange(10, 60)
        self.eye_interval_minutes.setValue(
            break_preferences.eye_interval_minutes
        )
        self.eye_interval_minutes.setSuffix(tr(" minutes"))
        self.eye_duration_seconds = QSpinBox()
        self.eye_duration_seconds.setRange(10, 120)
        self.eye_duration_seconds.setValue(
            break_preferences.eye_duration_seconds
        )
        self.eye_duration_seconds.setSuffix(tr(" seconds"))
        eye_form.addRow(
            tr("Distance-view reminder every"),
            self.eye_interval_minutes,
        )
        eye_form.addRow(tr("Look away for"), self.eye_duration_seconds)
        eye_layout.addLayout(eye_form)
        eye_explanation = QLabel(
            tr(
                "Each eye reminder starts by looking away from the screen."
            )
        )
        eye_explanation.setWordWrap(True)
        eye_layout.addWidget(eye_explanation)
        self.suggest_nature_view = QCheckBox(
            tr("Look toward distant greenery when available")
        )
        self.suggest_nature_view.setChecked(
            break_preferences.suggest_nature_view
        )
        self.suggest_blinking = QCheckBox(
            tr("Add five slow, complete blinks")
        )
        self.suggest_blinking.setChecked(
            break_preferences.suggest_blinking
        )
        self.suggest_closed_eye_rest = QCheckBox(
            tr("Offer a gentle closed-eye rest")
        )
        self.suggest_closed_eye_rest.setChecked(
            break_preferences.suggest_closed_eye_rest
        )
        eye_layout.addWidget(self.suggest_nature_view)
        eye_layout.addWidget(self.suggest_blinking)
        eye_layout.addWidget(self.suggest_closed_eye_rest)
        break_layout.addWidget(self.eye_controls)

        hydration_divider = QFrame()
        hydration_divider.setFrameShape(QFrame.Shape.HLine)
        hydration_divider.setFrameShadow(QFrame.Shadow.Sunken)
        break_layout.addWidget(hydration_divider)

        self.hydration_reminders_enabled = QCheckBox(tr("Water reminder"))
        hydration_heading_font = self.hydration_reminders_enabled.font()
        hydration_heading_font.setBold(True)
        self.hydration_reminders_enabled.setFont(hydration_heading_font)
        self.hydration_reminders_enabled.setChecked(
            break_preferences.hydration_reminders_enabled
        )
        break_layout.addWidget(self.hydration_reminders_enabled)

        self.hydration_controls = QWidget()
        hydration_layout = QFormLayout(self.hydration_controls)
        hydration_layout.setContentsMargins(22, 0, 0, 0)
        hydration_layout.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapLongRows
        )
        self.hydration_interval_minutes = QSpinBox()
        self.hydration_interval_minutes.setRange(20, 240)
        self.hydration_interval_minutes.setValue(
            break_preferences.hydration_interval_minutes
        )
        self.hydration_interval_minutes.setSuffix(tr(" minutes"))
        self.hydration_duration_seconds = QSpinBox()
        self.hydration_duration_seconds.setRange(15, 180)
        self.hydration_duration_seconds.setValue(
            break_preferences.hydration_duration_seconds
        )
        self.hydration_duration_seconds.setSuffix(tr(" seconds"))
        hydration_layout.addRow(
            tr("Water reminder every"),
            self.hydration_interval_minutes,
        )
        hydration_layout.addRow(
            tr("Suggested length"),
            self.hydration_duration_seconds,
        )
        break_layout.addWidget(self.hydration_controls)

        reset_divider = QFrame()
        reset_divider.setFrameShape(QFrame.Shape.HLine)
        reset_divider.setFrameShadow(QFrame.Shadow.Sunken)
        break_layout.addWidget(reset_divider)

        self.reset_reminders_enabled = QCheckBox(tr("Longer reset"))
        reset_heading_font = self.reset_reminders_enabled.font()
        reset_heading_font.setBold(True)
        self.reset_reminders_enabled.setFont(reset_heading_font)
        self.reset_reminders_enabled.setChecked(
            break_preferences.reset_reminders_enabled
        )
        break_layout.addWidget(self.reset_reminders_enabled)

        self.reset_controls = QWidget()
        reset_layout = QVBoxLayout(self.reset_controls)
        reset_layout.setContentsMargins(22, 0, 0, 0)
        reset_form = QFormLayout()
        reset_form.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapLongRows
        )
        self.reset_interval_minutes = QSpinBox()
        self.reset_interval_minutes.setRange(30, 240)
        self.reset_interval_minutes.setValue(
            break_preferences.reset_interval_minutes
        )
        self.reset_interval_minutes.setSuffix(tr(" minutes"))
        self.reset_duration_minutes = QSpinBox()
        self.reset_duration_minutes.setRange(1, 15)
        self.reset_duration_minutes.setValue(
            break_preferences.reset_duration_minutes
        )
        self.reset_duration_minutes.setSuffix(tr(" minutes"))
        reset_form.addRow(tr("Every"), self.reset_interval_minutes)
        reset_form.addRow(
            tr("Suggested length"),
            self.reset_duration_minutes,
        )
        reset_layout.addLayout(reset_form)
        reset_options_label = QLabel(tr("Shuffle suggestions between"))
        reset_options_font = reset_options_label.font()
        reset_options_font.setBold(True)
        reset_options_label.setFont(reset_options_font)
        reset_layout.addWidget(reset_options_label)
        self.suggest_tea_or_coffee = QCheckBox(tr("Make tea or coffee"))
        self.suggest_tea_or_coffee.setChecked(
            break_preferences.suggest_tea_or_coffee
        )
        self.suggest_reset_walking = QCheckBox(tr("Take an easy walk"))
        self.suggest_reset_walking.setChecked(
            break_preferences.suggest_reset_walking
        )
        self.suggest_breathing_reset = QCheckBox(
            tr("Take a slower breathing reset")
        )
        self.suggest_breathing_reset.setChecked(
            break_preferences.suggest_breathing_reset
        )
        self.suggest_offscreen_reset = QCheckBox(
            tr("Take a full off-screen reset")
        )
        self.suggest_offscreen_reset.setChecked(
            break_preferences.suggest_offscreen_reset
        )
        self.suggest_reset_guided_exercise = QCheckBox(
            tr("Open a guided movement")
        )
        self.suggest_reset_guided_exercise.setChecked(
            break_preferences.suggest_reset_guided_exercise
        )
        reset_layout.addWidget(self.suggest_tea_or_coffee)
        reset_layout.addWidget(self.suggest_reset_walking)
        reset_layout.addWidget(self.suggest_breathing_reset)
        reset_layout.addWidget(self.suggest_offscreen_reset)
        reset_layout.addWidget(self.suggest_reset_guided_exercise)
        break_layout.addWidget(self.reset_controls)

        evidence_note = SemanticLabel(
            tr(
                "Short, frequent movement breaks have stronger support than "
                "any exact schedule, and light walking has stronger acute "
                "evidence than standing alone. The 20-20-20 eye rule is "
                "widely recommended, but its exact timing has limited trial "
                "evidence. Water and longer-reset intervals are convenience "
                "defaults, not intake or treatment prescriptions."
            ),
            tone="info",
        )
        break_layout.addWidget(evidence_note)
        layout.addWidget(break_group)

        self.break_reminders_enabled.toggled.connect(
            self._sync_break_controls
        )
        self.movement_reminders_enabled.toggled.connect(
            self._sync_break_controls
        )
        self.eye_reminders_enabled.toggled.connect(
            self._sync_break_controls
        )
        self.hydration_reminders_enabled.toggled.connect(
            self._sync_break_controls
        )
        self.reset_reminders_enabled.toggled.connect(
            self._sync_break_controls
        )
        self._sync_break_controls()

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
        self.feedback_label.setAccessibleName(tr("Invalid settings"))
        self.feedback_label.hide()
        layout.addWidget(self.feedback_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        outer_layout.addWidget(buttons)
        self._policy = policy
        self._break_preferences = break_preferences
        self._preferences = preferences
        self._history_preferences = history_preferences
        self._language = language
        self._startup_setting_available = startup_setting_available

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
            self.feedback_label.setText(
                tr(
                    "The notification delay must be longer than the warning "
                    "delay."
                )
            )
            self.feedback_label.show()
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
            self.feedback_label.setText(
                tr(
                    "Enable at least one break channel, and keep at least one "
                    "suggestion in each enabled movement or longer-reset "
                    "channel."
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
