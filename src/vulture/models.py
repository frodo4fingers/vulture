from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class PostureCategory(StrEnum):
    FORWARD_HEAD = "forward_head"
    SLOUCH = "slouch"
    SHOULDERS_SUNK = "shoulders_sunk"
    LATERAL_LEAN = "lateral_lean"
    GENERAL_DEVIATION = "general_deviation"


class TrackerState(StrEnum):
    STOPPED = "stopped"
    CALIBRATING = "calibrating"
    GOOD = "good"
    WARNING = "warning"
    ALERT = "alert"
    LOW_CONFIDENCE = "low_confidence"
    CAMERA_UNAVAILABLE = "camera_unavailable"
    UNCALIBRATED = "uncalibrated"


class InterfaceLanguage(StrEnum):
    ENGLISH = "en"
    GERMAN = "de"
    SPANISH = "es"


class CameraDescriptor(StrictModel):
    stable_id: str
    display_name: str
    locator: str | int
    width: int = Field(default=640, ge=320, le=3840)
    height: int = Field(default=480, ge=240, le=2160)
    mirror_preview: bool = True


class GeometryFingerprint(StrictModel):
    frame_width: int = Field(gt=0)
    frame_height: int = Field(gt=0)
    shoulder_width: float = Field(gt=0)
    torso_length: float | None = Field(default=None, gt=0)
    subject_center_x: float = Field(ge=0, le=1)
    subject_center_y: float = Field(ge=0, le=1)
    shoulder_roll_degrees: float
    yaw_proxy: float


class FeatureFrame(StrictModel):
    captured_at: datetime = Field(default_factory=utc_now)
    values: dict[str, float]
    category_quality: dict[PostureCategory, float]
    overall_quality: float = Field(ge=0, le=1)
    geometry: GeometryFingerprint


class CategoryCalibration(StrictModel):
    category: PostureCategory
    feature_names: list[str]
    direction: dict[str, float]
    on_threshold: float
    off_threshold: float
    bad_reference_score: float
    separation: float
    sample_count: int = Field(ge=1)
    enabled: bool = True

    @field_validator("feature_names")
    @classmethod
    def feature_names_must_be_unique(cls, value: list[str]) -> list[str]:
        if not value or len(value) != len(set(value)):
            raise ValueError("feature_names must be non-empty and unique")
        return value


class CalibrationProfile(StrictModel):
    version: int = 1
    created_at: datetime = Field(default_factory=utc_now)
    good_center: dict[str, float]
    good_scale: dict[str, float]
    good_sample_count: int = Field(ge=1)
    geometry: GeometryFingerprint
    categories: dict[PostureCategory, CategoryCalibration] = Field(default_factory=dict)
    general_on_threshold: float = Field(default=4.5, gt=0)
    general_off_threshold: float = Field(default=3.0, gt=0)


class SetupProfile(StrictModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = Field(min_length=1, max_length=80)
    camera: CameraDescriptor
    calibration: CalibrationProfile | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AlertPolicy(StrictModel):
    minimum_tracking_quality: float = Field(default=0.70, ge=0, le=1)
    warning_after_seconds: float = Field(default=8.0, ge=1)
    alert_after_seconds: float = Field(default=60.0, ge=5)
    clear_after_seconds: float = Field(default=3.0, ge=0)
    posture_transition_buffer_seconds: float = Field(
        default=8.0,
        ge=0,
        le=30,
    )
    notification_cooldown_seconds: float = Field(default=120.0, ge=10)
    repeated_reminders_for_break: int = Field(default=5, ge=2, le=20)
    repeated_reminder_window_minutes: int = Field(default=20, ge=5, le=120)
    exercise_offer_cooldown_minutes: int = Field(default=20, ge=5, le=240)
    sedentary_break_minutes: int = Field(default=55, ge=20, le=180)

    @field_validator("alert_after_seconds")
    @classmethod
    def alert_must_follow_warning(cls, value: float, info) -> float:
        warning = info.data.get("warning_after_seconds")
        if warning is not None and value <= warning:
            raise ValueError("alert_after_seconds must exceed warning_after_seconds")
        return value


class BreakPreferences(StrictModel):
    enabled: bool = True
    movement_reminders_enabled: bool = True
    movement_interval_minutes: int = Field(default=30, ge=20, le=180)
    movement_duration_minutes: int = Field(default=2, ge=1, le=10)
    away_reset_minutes: int = Field(default=2, ge=1, le=30)
    suggest_position_change: bool = True
    suggest_standing: bool = True
    suggest_walking: bool = True
    legacy_walk_includes_drinks: bool = False
    suggest_guided_exercise: bool = True
    eye_reminders_enabled: bool = True
    eye_interval_minutes: int = Field(default=20, ge=10, le=60)
    eye_duration_seconds: int = Field(default=20, ge=10, le=120)
    suggest_nature_view: bool = True
    suggest_blinking: bool = True
    suggest_closed_eye_rest: bool = True
    hydration_reminders_enabled: bool = True
    hydration_interval_minutes: int = Field(default=60, ge=20, le=240)
    hydration_duration_seconds: int = Field(default=30, ge=15, le=180)
    reset_reminders_enabled: bool = True
    reset_interval_minutes: int = Field(default=90, ge=30, le=240)
    reset_duration_minutes: int = Field(default=5, ge=1, le=15)
    suggest_tea_or_coffee: bool = True
    suggest_reset_walking: bool = True
    suggest_breathing_reset: bool = True
    suggest_offscreen_reset: bool = True
    suggest_reset_guided_exercise: bool = True

    @model_validator(mode="before")
    @classmethod
    def preserve_existing_channel_defaults(cls, value):
        if not isinstance(value, dict) or not value:
            return value
        existing_fields = {
            "movement_reminders_enabled",
            "movement_interval_minutes",
            "eye_reminders_enabled",
            "eye_interval_minutes",
        }
        if not existing_fields.intersection(value):
            return value
        if (
            "hydration_reminders_enabled" in value
            or "reset_reminders_enabled" in value
        ):
            return value
        migrated = dict(value)
        migrated.setdefault("hydration_reminders_enabled", False)
        migrated.setdefault("reset_reminders_enabled", False)
        migrated.setdefault("suggest_nature_view", False)
        migrated.setdefault(
            "legacy_walk_includes_drinks",
            bool(migrated.get("suggest_walking", True)),
        )
        return migrated

    @model_validator(mode="after")
    def enabled_reminders_need_a_channel(self) -> BreakPreferences:
        if self.enabled and not (
            self.movement_reminders_enabled
            or self.eye_reminders_enabled
            or self.hydration_reminders_enabled
            or self.reset_reminders_enabled
        ):
            raise ValueError("at least one break reminder channel is required")
        if (
            self.enabled
            and self.movement_reminders_enabled
            and not any(
                (
                    self.suggest_position_change,
                    self.suggest_standing,
                    self.suggest_walking,
                    self.suggest_guided_exercise,
                )
            )
        ):
            raise ValueError("at least one movement suggestion is required")
        if (
            self.enabled
            and self.reset_reminders_enabled
            and not any(
                (
                    self.suggest_tea_or_coffee,
                    self.suggest_reset_walking,
                    self.suggest_breathing_reset,
                    self.suggest_offscreen_reset,
                    self.suggest_reset_guided_exercise,
                )
            )
        ):
            raise ValueError("at least one longer reset suggestion is required")
        return self


class ExercisePreferences(StrictModel):
    seated_only: bool = False
    allow_balance_exercises: bool = False
    allow_strength_exercises: bool = False
    excluded_exercise_ids: list[str] = Field(default_factory=list)


class HistoryPreferences(StrictModel):
    enabled: bool = True
    retention_days: int = Field(default=30, ge=1, le=365)


class ReminderEvent(StrictModel):
    occurred_at: datetime = Field(default_factory=utc_now)
    setup_id: str
    category: PostureCategory


class AppData(StrictModel):
    schema_version: int = 1
    interface_language: InterfaceLanguage = InterfaceLanguage.ENGLISH
    active_setup_id: str | None = None
    setups: list[SetupProfile] = Field(default_factory=list)
    alert_policy: AlertPolicy = Field(default_factory=AlertPolicy)
    break_preferences: BreakPreferences = Field(
        default_factory=BreakPreferences
    )
    exercise_preferences: ExercisePreferences = Field(default_factory=ExercisePreferences)
    history_preferences: HistoryPreferences = Field(default_factory=HistoryPreferences)
    reminder_history: list[ReminderEvent] = Field(default_factory=list)
    recent_exercise_ids: list[str] = Field(default_factory=list)
    exercise_shuffle_bag: list[str] = Field(default_factory=list)
    last_exercise_id: str | None = None
    break_activity_bags: dict[str, list[str]] = Field(default_factory=dict)
    last_break_activity_ids: dict[str, str] = Field(default_factory=dict)
    last_exercise_offer_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_break_preferences(cls, value):
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        if "last_exercise_id" not in migrated:
            recent_exercise_ids = migrated.get("recent_exercise_ids")
            if (
                isinstance(recent_exercise_ids, list)
                and recent_exercise_ids
                and isinstance(recent_exercise_ids[-1], str)
            ):
                migrated["last_exercise_id"] = recent_exercise_ids[-1]
        if "break_preferences" in migrated:
            return migrated
        policy = migrated.get("alert_policy")
        if not isinstance(policy, dict):
            return migrated
        legacy_interval = policy.get("sedentary_break_minutes")
        if legacy_interval is None:
            return migrated
        # Older versions represented every independent break as a guided
        # exercise, so preserve that cadence until the user opts into more.
        migrated["break_preferences"] = {
            "movement_interval_minutes": legacy_interval,
            "suggest_position_change": False,
            "suggest_standing": False,
            "suggest_walking": False,
            "suggest_guided_exercise": True,
            "eye_reminders_enabled": False,
        }
        return migrated

    def active_setup(self) -> SetupProfile | None:
        return next((item for item in self.setups if item.id == self.active_setup_id), None)
