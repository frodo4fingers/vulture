from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    exercise_preferences: ExercisePreferences = Field(default_factory=ExercisePreferences)
    history_preferences: HistoryPreferences = Field(default_factory=HistoryPreferences)
    reminder_history: list[ReminderEvent] = Field(default_factory=list)
    recent_exercise_ids: list[str] = Field(default_factory=list)
    last_exercise_offer_at: datetime | None = None

    def active_setup(self) -> SetupProfile | None:
        return next((item for item in self.setups if item.id == self.active_setup_id), None)
