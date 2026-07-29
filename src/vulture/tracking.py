from __future__ import annotations

import math
from datetime import datetime, timedelta

from pydantic import Field

from vulture.calibration import geometry_compatible, score_frame
from vulture.i18n import tr
from vulture.models import (
    AlertPolicy,
    CalibrationProfile,
    FeatureFrame,
    PostureCategory,
    StrictModel,
    TrackerState,
    utc_now,
)


CATEGORY_MESSAGES = {
    PostureCategory.FORWARD_HEAD: "Your head position has drifted from your calibrated baseline.",
    PostureCategory.SLOUCH: "Your torso position has drifted from your calibrated baseline.",
    PostureCategory.SHOULDERS_SUNK: "Your shoulders have stayed away from your calibrated baseline.",
    PostureCategory.LATERAL_LEAN: "You have been leaning away from your calibrated baseline.",
    PostureCategory.GENERAL_DEVIATION: "You have stayed in one position away from your baseline.",
}


class PostureAssessment(StrictModel):
    assessed_at: datetime = Field(default_factory=utc_now)
    state: TrackerState
    category: PostureCategory | None = None
    scores: dict[PostureCategory, float] = Field(default_factory=dict)
    qualities: dict[PostureCategory, float] = Field(default_factory=dict)
    bad_duration_seconds: float = 0.0
    message: str
    newly_alerted: bool = False


class PostureEvaluatorState(StrictModel):
    smoothed_scores: dict[PostureCategory, float] = Field(
        default_factory=dict
    )
    category_active: dict[PostureCategory, bool] = Field(
        default_factory=dict
    )
    last_frame_at: datetime | None = None
    bad_since: datetime | None = None
    clear_since: datetime | None = None
    bad_interruption_uncertain: bool = False
    latest_tracking_event_at: datetime | None = None
    current_category: PostureCategory | None = None
    last_notification_at: datetime | None = None
    state: TrackerState = TrackerState.GOOD


class PostureEvaluator:
    def __init__(
        self,
        profile: CalibrationProfile,
        policy: AlertPolicy | None = None,
        smoothing_seconds: float = 0.6,
    ) -> None:
        self.profile = profile
        self.policy = policy or AlertPolicy()
        self.smoothing_seconds = smoothing_seconds
        self._smoothed_scores: dict[PostureCategory, float] = {}
        self._category_active: dict[PostureCategory, bool] = {}
        self._last_frame_at: datetime | None = None
        self._bad_since: datetime | None = None
        self._clear_since: datetime | None = None
        self._bad_interruption_uncertain = False
        self._latest_tracking_event_at: datetime | None = None
        self._current_category: PostureCategory | None = None
        self._last_notification_at: datetime | None = None
        self._state = TrackerState.GOOD

    def snapshot(self) -> PostureEvaluatorState:
        return PostureEvaluatorState(
            smoothed_scores=dict(self._smoothed_scores),
            category_active=dict(self._category_active),
            last_frame_at=self._last_frame_at,
            bad_since=self._bad_since,
            clear_since=self._clear_since,
            bad_interruption_uncertain=self._bad_interruption_uncertain,
            latest_tracking_event_at=self._latest_tracking_event_at,
            current_category=self._current_category,
            last_notification_at=self._last_notification_at,
            state=self._state,
        )

    def restore(self, state: PostureEvaluatorState) -> None:
        self._smoothed_scores = dict(state.smoothed_scores)
        self._category_active = dict(state.category_active)
        self._last_frame_at = state.last_frame_at
        self._bad_since = state.bad_since
        self._clear_since = state.clear_since
        self._bad_interruption_uncertain = (
            state.bad_interruption_uncertain
        )
        self._latest_tracking_event_at = state.latest_tracking_event_at
        self._current_category = state.current_category
        self._last_notification_at = state.last_notification_at
        self._state = state.state

    def reset(self) -> None:
        self._smoothed_scores.clear()
        self._category_active.clear()
        self._last_frame_at = None
        self._bad_since = None
        self._clear_since = None
        self._bad_interruption_uncertain = False
        self._latest_tracking_event_at = None
        self._current_category = None
        self._state = TrackerState.GOOD

    def mark_tracking_lost(
        self,
        captured_at: datetime | None = None,
    ) -> None:
        if captured_at is not None:
            self._record_tracking_event(captured_at)
        self._smoothed_scores.clear()
        self._last_frame_at = None
        self._reset_bad_period()
        self._state = TrackerState.LOW_CONFIDENCE

    def mark_tracking_uncertain(
        self,
        captured_at: datetime,
    ) -> bool:
        if (
            self._latest_tracking_event_at is not None
            and captured_at < self._latest_tracking_event_at
        ):
            return False
        self._record_tracking_event(captured_at)
        if self._bad_since is not None and self._last_frame_at is not None:
            frame_gap = (captured_at - self._last_frame_at).total_seconds()
            if frame_gap > self.policy.posture_transition_buffer_seconds:
                self._reset_bad_period()
            else:
                self._begin_bad_interruption(
                    self._last_frame_at,
                    uncertain=True,
                )
        else:
            self._begin_bad_interruption(captured_at, uncertain=True)
        if (
            self._clear_since is not None
            and (
                captured_at - self._clear_since
            ).total_seconds()
            >= self._bad_interruption_buffer_seconds()
        ):
            self._reset_bad_period()
        self._smoothed_scores.clear()
        self._category_active.clear()
        self._last_frame_at = None
        self._state = TrackerState.LOW_CONFIDENCE
        return True

    def assess(self, frame: FeatureFrame) -> PostureAssessment | None:
        if (
            self._latest_tracking_event_at is not None
            and frame.captured_at < self._latest_tracking_event_at
        ):
            return None
        self._record_tracking_event(frame.captured_at)
        if (
            self._last_frame_at is not None
            and (frame.captured_at - self._last_frame_at).total_seconds() > 2.0
        ):
            frame_gap = (
                frame.captured_at - self._last_frame_at
            ).total_seconds()
            if (
                self._bad_since is not None
                and frame_gap
                <= self.policy.posture_transition_buffer_seconds
            ):
                self._begin_bad_interruption(
                    self._last_frame_at,
                    uncertain=True,
                )
                self._smoothed_scores.clear()
                self._category_active.clear()
                self._last_frame_at = None
            else:
                self.mark_tracking_lost(frame.captured_at)
        compatible, geometry_message = geometry_compatible(
            frame.geometry, self.profile.geometry
        )
        if not compatible:
            self.mark_tracking_lost(frame.captured_at)
            return PostureAssessment(
                assessed_at=frame.captured_at,
                state=TrackerState.LOW_CONFIDENCE,
                message=geometry_message
                or tr("Camera setup no longer matches calibration."),
            )
        raw_scores, qualities = score_frame(frame, self.profile)
        valid_categories = {
            category
            for category, quality in qualities.items()
            if quality >= self.policy.minimum_tracking_quality
        }
        if not valid_categories:
            return self._assess_low_confidence(
                frame,
                qualities,
                tr(
                    "Tracking paused until your face and shoulders are clear."
                ),
            )
        self._smooth(raw_scores, frame.captured_at)

        active_categories: list[PostureCategory] = []
        for category in raw_scores:
            if category not in valid_categories:
                self._category_active[category] = False
                continue
            on_threshold, off_threshold = self._thresholds(category)
            threshold = (
                off_threshold
                if self._category_active.get(category, False)
                else on_threshold
            )
            is_active = self._smoothed_scores.get(category, 0.0) >= threshold
            self._category_active[category] = is_active
            if is_active:
                active_categories.append(category)

        if not active_categories:
            return self._assess_clear(frame, qualities)

        category = max(
            active_categories,
            key=lambda item: self._smoothed_scores[item]
            / max(self._thresholds(item)[0], 0.001),
        )
        self._resume_bad_period(frame.captured_at)
        self._current_category = category
        bad_duration = self._bad_duration(frame.captured_at)

        newly_alerted = False
        if bad_duration >= self.policy.alert_after_seconds:
            self._state = TrackerState.ALERT
            cooldown = timedelta(
                seconds=self.policy.notification_cooldown_seconds
            )
            if (
                self._last_notification_at is None
                or frame.captured_at - self._last_notification_at >= cooldown
            ):
                newly_alerted = True
                self._last_notification_at = frame.captured_at
        elif bad_duration >= self.policy.warning_after_seconds:
            self._state = TrackerState.WARNING
        else:
            self._state = TrackerState.GOOD

        return PostureAssessment(
            assessed_at=frame.captured_at,
            state=self._state,
            category=category,
            scores=dict(self._smoothed_scores),
            qualities=qualities,
            bad_duration_seconds=bad_duration,
            message=tr(CATEGORY_MESSAGES[category]),
            newly_alerted=newly_alerted,
        )

    def _assess_clear(
        self,
        frame: FeatureFrame,
        qualities: dict[PostureCategory, float],
    ) -> PostureAssessment:
        if self._bad_since is not None:
            self._begin_bad_interruption(
                frame.captured_at,
                uncertain=False,
            )
            clear_duration = (
                frame.captured_at - self._clear_since
            ).total_seconds()
            interruption_buffer = (
                self._bad_interruption_buffer_seconds()
            )
            if clear_duration >= interruption_buffer:
                self._reset_bad_period()
                self._state = TrackerState.GOOD
                return PostureAssessment(
                    assessed_at=frame.captured_at,
                    state=TrackerState.GOOD,
                    scores=dict(self._smoothed_scores),
                    qualities=qualities,
                    message=tr("Within your calibrated range."),
                )
            if clear_duration < self.policy.clear_after_seconds:
                return PostureAssessment(
                    assessed_at=frame.captured_at,
                    state=self._state,
                    category=self._current_category,
                    scores=dict(self._smoothed_scores),
                    qualities=qualities,
                    bad_duration_seconds=self._bad_duration(
                        frame.captured_at
                    ),
                    message=tr(
                        "Return toward your comfortable calibrated baseline."
                    ),
                )
            if clear_duration < interruption_buffer:
                self._state = TrackerState.GOOD
                return PostureAssessment(
                    assessed_at=frame.captured_at,
                    state=TrackerState.GOOD,
                    scores=dict(self._smoothed_scores),
                    qualities=qualities,
                    message=tr("Within your calibrated range."),
                )
        self._reset_bad_period()
        self._state = TrackerState.GOOD
        return PostureAssessment(
            assessed_at=frame.captured_at,
            state=TrackerState.GOOD,
            scores=dict(self._smoothed_scores),
            qualities=qualities,
            message=tr("Within your calibrated range."),
        )

    def _assess_low_confidence(
        self,
        frame: FeatureFrame,
        qualities: dict[PostureCategory, float],
        message: str,
    ) -> PostureAssessment:
        self.mark_tracking_uncertain(frame.captured_at)
        return PostureAssessment(
            assessed_at=frame.captured_at,
            state=TrackerState.LOW_CONFIDENCE,
            qualities=qualities,
            message=message,
        )

    def _bad_interruption_buffer_seconds(self) -> float:
        if self._bad_interruption_uncertain:
            return self.policy.posture_transition_buffer_seconds
        return max(
            self.policy.clear_after_seconds,
            self.policy.posture_transition_buffer_seconds,
        )

    def _record_tracking_event(
        self,
        captured_at: datetime,
    ) -> None:
        if (
            self._latest_tracking_event_at is None
            or captured_at > self._latest_tracking_event_at
        ):
            self._latest_tracking_event_at = captured_at

    def _begin_bad_interruption(
        self,
        captured_at: datetime,
        *,
        uncertain: bool,
    ) -> None:
        if self._bad_since is not None and self._clear_since is None:
            self._clear_since = captured_at
        if self._bad_since is not None and uncertain:
            self._bad_interruption_uncertain = True

    def _resume_bad_period(self, captured_at: datetime) -> None:
        if self._bad_since is None:
            self._bad_since = captured_at
        elif self._clear_since is not None:
            interruption = captured_at - self._clear_since
            if (
                interruption.total_seconds()
                <= self._bad_interruption_buffer_seconds()
            ):
                self._bad_since += interruption
            else:
                self._bad_since = captured_at
        self._clear_since = None
        self._bad_interruption_uncertain = False

    def _bad_duration(self, captured_at: datetime) -> float:
        if self._bad_since is None:
            return 0.0
        duration_end = self._clear_since or captured_at
        return max(0.0, (duration_end - self._bad_since).total_seconds())

    def _smooth(
        self,
        raw_scores: dict[PostureCategory, float],
        captured_at: datetime,
    ) -> None:
        if self._last_frame_at is None:
            self._smoothed_scores = dict(raw_scores)
            self._last_frame_at = captured_at
            return
        elapsed = max(
            0.001, (captured_at - self._last_frame_at).total_seconds()
        )
        if elapsed > 2.0:
            self._smoothed_scores = dict(raw_scores)
        else:
            alpha = 1.0 - math.exp(-elapsed / self.smoothing_seconds)
            for category, score in raw_scores.items():
                previous = self._smoothed_scores.get(category, score)
                self._smoothed_scores[category] = (
                    previous + alpha * (score - previous)
                )
        self._last_frame_at = captured_at

    def _thresholds(
        self, category: PostureCategory
    ) -> tuple[float, float]:
        if category == PostureCategory.GENERAL_DEVIATION:
            return (
                self.profile.general_on_threshold,
                self.profile.general_off_threshold,
            )
        category_profile = self.profile.categories[category]
        return category_profile.on_threshold, category_profile.off_threshold

    def _reset_bad_period(self) -> None:
        self._bad_since = None
        self._clear_since = None
        self._bad_interruption_uncertain = False
        self._current_category = None
        self._category_active.clear()
