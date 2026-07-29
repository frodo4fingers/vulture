from __future__ import annotations

from datetime import datetime, timedelta, timezone

from vulture.calibration import CalibrationFitter
from vulture.models import (
    AlertPolicy,
    CalibrationProfile,
    FeatureFrame,
    PostureCategory,
    TrackerState,
)
from vulture.tracking import PostureEvaluator

from tests.test_calibration import make_frame, make_upper_body_frame


def make_posture_switch_profile() -> tuple[
    CalibrationProfile,
    list[FeatureFrame],
    list[FeatureFrame],
    list[FeatureFrame],
]:
    good = [make_frame(index) for index in range(80)]
    forward_head = [
        make_frame(
            index,
            {
                "head_offset_x": 0.12,
                "nose_offset_x": 0.13,
                "face_scale": 0.48,
            },
        )
        for index in range(40)
    ]
    slouch = [
        make_frame(
            index,
            {
                "torso_length": 1.05,
                "torso_vertical": 0.95,
                "torso_lean": 0.18,
                "head_offset_y": -0.48,
                "shoulder_face_gap": 0.50,
            },
        )
        for index in range(40)
    ]
    profile = CalibrationFitter().fit(
        good,
        {
            PostureCategory.FORWARD_HEAD: forward_head,
            PostureCategory.SLOUCH: slouch,
        },
    )
    profile.general_on_threshold = 1_000_000
    profile.general_off_threshold = 1_000_000
    return profile, good, forward_head, slouch


def test_evaluator_uses_upper_body_shoulder_and_lean_calibrations() -> None:
    good = [make_upper_body_frame(index) for index in range(80)]
    examples = {
        PostureCategory.SHOULDERS_SUNK: [
            make_upper_body_frame(index, shoulder_y=0.45)
            for index in range(40)
        ],
        PostureCategory.LATERAL_LEAN: [
            make_upper_body_frame(
                index,
                shoulder_tilt=0.04,
                face_shift_x=0.06,
            )
            for index in range(40)
        ],
    }

    for category, bad_frames in examples.items():
        profile = CalibrationFitter().fit(good, {category: bad_frames})
        profile.general_on_threshold = 1_000_000
        profile.general_off_threshold = 1_000_000
        evaluator = PostureEvaluator(profile, smoothing_seconds=0.1)

        assessment = evaluator.assess(bad_frames[-1])

        assert assessment is not None
        assert assessment.category is category
        assert assessment.qualities[category] > 0.9


def test_alert_requires_sustained_deviation_and_clears_with_hysteresis() -> None:
    good = [make_frame(index) for index in range(80)]
    bad = [
        make_frame(
            index,
            {
                "head_offset_x": 0.12,
                "nose_offset_x": 0.13,
                "face_scale": 0.48,
            },
        )
        for index in range(40)
    ]
    profile = CalibrationFitter().fit(
        good, {PostureCategory.FORWARD_HEAD: bad}
    )
    policy = AlertPolicy(
        warning_after_seconds=1,
        alert_after_seconds=5,
        clear_after_seconds=2,
        notification_cooldown_seconds=10,
    )
    evaluator = PostureEvaluator(profile, policy, smoothing_seconds=0.1)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    first = evaluator.assess(
        bad[0].model_copy(update={"captured_at": start})
    )
    warning = evaluator.assess(
        bad[1].model_copy(
            update={"captured_at": start + timedelta(seconds=1.5)}
        )
    )
    evaluator.assess(
        bad[2].model_copy(
            update={"captured_at": start + timedelta(seconds=3.2)}
        )
    )
    alert = evaluator.assess(
        bad[3].model_copy(
            update={"captured_at": start + timedelta(seconds=5.2)}
        )
    )

    assert first.state == TrackerState.GOOD
    assert warning.state == TrackerState.WARNING
    assert alert.state == TrackerState.ALERT
    assert alert.newly_alerted

    clearing = evaluator.assess(
        good[0].model_copy(
            update={"captured_at": start + timedelta(seconds=6)}
        )
    )
    clear = evaluator.assess(
        good[1].model_copy(
            update={"captured_at": start + timedelta(seconds=8.2)}
        )
    )
    assert clearing.state == TrackerState.ALERT
    assert clear.state == TrackerState.GOOD


def test_geometry_change_pauses_scoring() -> None:
    good = [make_frame(index) for index in range(80)]
    profile = CalibrationFitter().fit(good)
    evaluator = PostureEvaluator(profile)
    moved = good[0].model_copy(deep=True)
    moved.geometry.subject_center_x = 0.9

    assessment = evaluator.assess(moved)
    assert assessment.state == TrackerState.LOW_CONFIDENCE
    assert "camera position" in assessment.message.lower()


def test_tracking_gap_starts_a_new_bad_streak() -> None:
    good = [make_frame(index) for index in range(80)]
    bad = [
        make_frame(
            index,
            {
                "head_offset_x": 0.12,
                "nose_offset_x": 0.13,
                "face_scale": 0.48,
            },
        )
        for index in range(40)
    ]
    profile = CalibrationFitter().fit(
        good, {PostureCategory.FORWARD_HEAD: bad}
    )
    evaluator = PostureEvaluator(
        profile,
        AlertPolicy(
            warning_after_seconds=1,
            alert_after_seconds=5,
            notification_cooldown_seconds=10,
        ),
        smoothing_seconds=0.1,
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    evaluator.assess(bad[0].model_copy(update={"captured_at": start}))
    evaluator.assess(
        bad[1].model_copy(
            update={"captured_at": start + timedelta(seconds=1.5)}
        )
    )

    after_gap = evaluator.assess(
        bad[2].model_copy(
            update={"captured_at": start + timedelta(seconds=10)}
        )
    )
    assert after_gap.state == TrackerState.GOOD
    assert after_gap.bad_duration_seconds == 0


def test_bad_posture_switch_survives_tracking_loss_transition() -> None:
    profile, _good, forward_head, slouch = make_posture_switch_profile()
    evaluator = PostureEvaluator(
        profile,
        AlertPolicy(
            warning_after_seconds=2,
            alert_after_seconds=20,
            clear_after_seconds=1,
            posture_transition_buffer_seconds=8,
        ),
        smoothing_seconds=0.1,
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(4):
        evaluator.assess(
            forward_head[index].model_copy(
                update={"captured_at": start + timedelta(seconds=index)}
            )
        )

    evaluator.mark_tracking_uncertain(
        start + timedelta(seconds=3.5)
    )
    uncertain = evaluator.snapshot()
    restored = PostureEvaluator(profile, evaluator.policy, smoothing_seconds=0.1)
    restored.restore(uncertain)
    switched = restored.assess(
        slouch[0].model_copy(
            update={"captured_at": start + timedelta(seconds=4.5)}
        )
    )

    assert uncertain.state is TrackerState.LOW_CONFIDENCE
    assert switched.category is PostureCategory.SLOUCH
    assert switched.state is TrackerState.WARNING
    assert switched.bad_duration_seconds == 3


def test_bad_posture_switch_survives_low_quality_frame() -> None:
    profile, _good, forward_head, slouch = make_posture_switch_profile()
    evaluator = PostureEvaluator(
        profile,
        AlertPolicy(
            warning_after_seconds=2,
            alert_after_seconds=20,
            clear_after_seconds=1,
            posture_transition_buffer_seconds=8,
        ),
        smoothing_seconds=0.1,
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(4):
        evaluator.assess(
            forward_head[index].model_copy(
                update={"captured_at": start + timedelta(seconds=index)}
            )
        )
    low_quality = make_frame(100).model_copy(
        update={
            "captured_at": start + timedelta(seconds=3.5),
            "category_quality": {
                category: 0.0 for category in PostureCategory
            },
            "overall_quality": 0.0,
        }
    )

    uncertain = evaluator.assess(low_quality)
    switched = evaluator.assess(
        slouch[0].model_copy(
            update={"captured_at": start + timedelta(seconds=4.5)}
        )
    )

    assert uncertain.state is TrackerState.LOW_CONFIDENCE
    assert switched.category is PostureCategory.SLOUCH
    assert switched.bad_duration_seconds == 3


def test_tracking_loss_transition_buffer_expires() -> None:
    profile, _good, forward_head, slouch = make_posture_switch_profile()
    evaluator = PostureEvaluator(
        profile,
        AlertPolicy(
            warning_after_seconds=2,
            alert_after_seconds=20,
            clear_after_seconds=1,
            posture_transition_buffer_seconds=8,
        ),
        smoothing_seconds=0.1,
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(3):
        evaluator.assess(
            forward_head[index].model_copy(
                update={"captured_at": start + timedelta(seconds=index)}
            )
        )

    evaluator.mark_tracking_uncertain(
        start + timedelta(seconds=2.5)
    )
    evaluator.mark_tracking_uncertain(
        start + timedelta(seconds=11)
    )
    stale = evaluator.assess(
        slouch[0].model_copy(
            update={"captured_at": start + timedelta(seconds=10)}
        )
    )
    switched = evaluator.assess(
        slouch[1].model_copy(
            update={"captured_at": start + timedelta(seconds=12)}
        )
    )

    assert stale is None
    assert switched.category is PostureCategory.SLOUCH
    assert switched.bad_duration_seconds == 0


def test_tracking_loss_uses_configured_buffer_not_clear_hysteresis() -> None:
    profile, _good, forward_head, slouch = make_posture_switch_profile()
    evaluator = PostureEvaluator(
        profile,
        AlertPolicy(
            warning_after_seconds=2,
            alert_after_seconds=20,
            clear_after_seconds=31,
            posture_transition_buffer_seconds=12,
        ),
        smoothing_seconds=0.1,
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(4):
        evaluator.assess(
            forward_head[index].model_copy(
                update={"captured_at": start + timedelta(seconds=index)}
            )
        )
    evaluator.mark_tracking_uncertain(
        start + timedelta(seconds=3.5)
    )

    switched = evaluator.assess(
        slouch[0].model_copy(
            update={"captured_at": start + timedelta(seconds=20)}
        )
    )

    assert switched.category is PostureCategory.SLOUCH
    assert switched.bad_duration_seconds == 0


def test_camera_silence_is_not_counted_as_bad_posture() -> None:
    profile, _good, forward_head, slouch = make_posture_switch_profile()
    evaluator = PostureEvaluator(
        profile,
        AlertPolicy(
            warning_after_seconds=2,
            alert_after_seconds=20,
            clear_after_seconds=1,
            posture_transition_buffer_seconds=8,
        ),
        smoothing_seconds=0.1,
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    evaluator.assess(
        forward_head[0].model_copy(update={"captured_at": start})
    )
    evaluator.assess(
        forward_head[1].model_copy(
            update={"captured_at": start + timedelta(seconds=1)}
        )
    )

    evaluator.mark_tracking_uncertain(
        start + timedelta(seconds=20)
    )
    resumed = evaluator.assess(
        slouch[0].model_copy(
            update={"captured_at": start + timedelta(seconds=21)}
        )
    )

    assert resumed.category is PostureCategory.SLOUCH
    assert resumed.bad_duration_seconds == 0


def test_stale_frame_is_ignored_without_an_active_bad_streak() -> None:
    profile, _good, _forward_head, slouch = make_posture_switch_profile()
    evaluator = PostureEvaluator(
        profile,
        AlertPolicy(
            warning_after_seconds=2,
            alert_after_seconds=20,
            clear_after_seconds=1,
            posture_transition_buffer_seconds=8,
        ),
        smoothing_seconds=0.1,
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    evaluator.mark_tracking_uncertain(
        start + timedelta(seconds=10)
    )
    restored = PostureEvaluator(profile, evaluator.policy, smoothing_seconds=0.1)
    restored.restore(evaluator.snapshot())

    stale = restored.assess(
        slouch[0].model_copy(
            update={"captured_at": start + timedelta(seconds=9)}
        )
    )
    live = restored.assess(
        slouch[1].model_copy(
            update={"captured_at": start + timedelta(seconds=11)}
        )
    )

    assert stale is None
    assert live.category is PostureCategory.SLOUCH
    assert live.bad_duration_seconds == 0


def test_late_tracking_loss_event_is_ignored() -> None:
    profile, _good, forward_head, slouch = make_posture_switch_profile()
    evaluator = PostureEvaluator(
        profile,
        AlertPolicy(
            warning_after_seconds=2,
            alert_after_seconds=20,
            clear_after_seconds=1,
            posture_transition_buffer_seconds=8,
        ),
        smoothing_seconds=0.1,
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(4):
        evaluator.assess(
            forward_head[index].model_copy(
                update={"captured_at": start + timedelta(seconds=index)}
            )
        )
    switched = evaluator.assess(
        slouch[0].model_copy(
            update={"captured_at": start + timedelta(seconds=4.5)}
        )
    )

    accepted = evaluator.mark_tracking_uncertain(
        start + timedelta(seconds=3.5)
    )
    continued = evaluator.assess(
        slouch[1].model_copy(
            update={"captured_at": start + timedelta(seconds=5.5)}
        )
    )

    assert switched.bad_duration_seconds == 4.5
    assert not accepted
    assert continued.state is TrackerState.WARNING
    assert continued.bad_duration_seconds == 5.5


def test_stale_frame_after_tracking_loss_is_ignored() -> None:
    profile, _good, forward_head, slouch = make_posture_switch_profile()
    evaluator = PostureEvaluator(
        profile,
        AlertPolicy(
            warning_after_seconds=2,
            alert_after_seconds=20,
            clear_after_seconds=1,
            posture_transition_buffer_seconds=8,
        ),
        smoothing_seconds=0.1,
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(4):
        evaluator.assess(
            forward_head[index].model_copy(
                update={"captured_at": start + timedelta(seconds=index)}
            )
        )
    evaluator.mark_tracking_uncertain(
        start + timedelta(seconds=3.5)
    )

    stale = evaluator.assess(
        slouch[0].model_copy(
            update={"captured_at": start + timedelta(seconds=3.25)}
        )
    )
    resumed = evaluator.assess(
        slouch[1].model_copy(
            update={"captured_at": start + timedelta(seconds=4.5)}
        )
    )

    assert stale is None
    assert resumed.category is PostureCategory.SLOUCH
    assert resumed.bad_duration_seconds == 3


def test_bad_posture_switch_buffer_excludes_gap_and_expires() -> None:
    profile, good, forward_head, slouch = make_posture_switch_profile()
    policy = AlertPolicy(
        warning_after_seconds=2,
        alert_after_seconds=20,
        clear_after_seconds=1,
        posture_transition_buffer_seconds=8,
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    evaluator = PostureEvaluator(profile, policy, smoothing_seconds=0.1)
    for index in range(3):
        evaluator.assess(
            forward_head[index].model_copy(
                update={"captured_at": start + timedelta(seconds=index)}
            )
        )
    evaluator.assess(
        good[0].model_copy(
            update={"captured_at": start + timedelta(seconds=2.5)}
        )
    )
    clear = evaluator.assess(
        good[1].model_copy(
            update={"captured_at": start + timedelta(seconds=4)}
        )
    )
    resumed = evaluator.assess(
        slouch[0].model_copy(
            update={"captured_at": start + timedelta(seconds=5)}
        )
    )

    assert clear.state is TrackerState.GOOD
    assert resumed.category is PostureCategory.SLOUCH
    assert resumed.bad_duration_seconds == 2.5

    expired = PostureEvaluator(profile, policy, smoothing_seconds=0.1)
    for index in range(3):
        expired.assess(
            forward_head[index].model_copy(
                update={"captured_at": start + timedelta(seconds=index)}
            )
        )
    expired.assess(
        good[0].model_copy(
            update={"captured_at": start + timedelta(seconds=2.5)}
        )
    )
    after_buffer = expired.assess(
        slouch[0].model_copy(
            update={"captured_at": start + timedelta(seconds=11)}
        )
    )

    assert after_buffer.category is PostureCategory.SLOUCH
    assert after_buffer.bad_duration_seconds == 0


def test_evaluator_snapshot_preserves_notification_cooldown() -> None:
    good = [make_frame(index) for index in range(80)]
    bad = [
        make_frame(
            index,
            {
                "head_offset_x": 0.12,
                "nose_offset_x": 0.13,
                "face_scale": 0.48,
            },
        )
        for index in range(40)
    ]
    profile = CalibrationFitter().fit(
        good, {PostureCategory.FORWARD_HEAD: bad}
    )
    policy = AlertPolicy(
        warning_after_seconds=1,
        alert_after_seconds=5,
        notification_cooldown_seconds=10,
    )
    evaluator = PostureEvaluator(
        profile,
        policy,
        smoothing_seconds=0.1,
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    evaluator.assess(bad[0].model_copy(update={"captured_at": start}))
    evaluator.assess(
        bad[1].model_copy(
            update={"captured_at": start + timedelta(seconds=1.5)}
        )
    )
    evaluator.assess(
        bad[2].model_copy(
            update={"captured_at": start + timedelta(seconds=3.2)}
        )
    )
    first_alert = evaluator.assess(
        bad[3].model_copy(
            update={"captured_at": start + timedelta(seconds=5.2)}
        )
    )
    assert first_alert.newly_alerted

    restored = PostureEvaluator(
        profile,
        policy,
        smoothing_seconds=0.1,
    )
    restored.restore(evaluator.snapshot())
    within_cooldown = restored.assess(
        bad[4].model_copy(
            update={"captured_at": start + timedelta(seconds=6)}
        )
    )

    assert within_cooldown.state is TrackerState.ALERT
    assert not within_cooldown.newly_alerted
