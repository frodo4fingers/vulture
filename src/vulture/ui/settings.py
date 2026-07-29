from __future__ import annotations

from pydantic import ValidationError
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from vulture.i18n import LANGUAGE_NAMES, tr
from vulture.models import (
    AlertPolicy,
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
        start_at_login_enabled: bool = False,
        startup_setting_available: bool = True,
        startup_setting_error: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Vulture settings"))
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
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

        alert_group = QGroupBox(tr("Reminder policy"))
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
        self.sedentary_minutes = QSpinBox()
        self.sedentary_minutes.setRange(20, 180)
        self.sedentary_minutes.setValue(policy.sedentary_break_minutes)
        self.sedentary_minutes.setSuffix(tr(" minutes"))
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
        alert_form.addRow(
            tr("Independent movement break"),
            self.sedentary_minutes,
        )
        layout.addWidget(alert_group)

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
        self.feedback_label.setAccessibleName(tr("Invalid reminder policy"))
        self.feedback_label.hide()
        layout.addWidget(self.feedback_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._policy = policy
        self._preferences = preferences
        self._history_preferences = history_preferences
        self._language = language
        self._startup_setting_available = startup_setting_available

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
                sedentary_break_minutes=self.sedentary_minutes.value(),
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
        )
