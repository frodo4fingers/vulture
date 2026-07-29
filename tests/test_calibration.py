from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from vulture.calibration import (
    CalibrationError,
    CalibrationFitter,
    category_score,
)
from vulture.models import (
    FeatureFrame,
    GeometryFingerprint,
    PostureCategory,
)
from vulture.vision import (
    FACE_CHIN,
    FACE_FOREHEAD,
    FACE_LEFT_CHEEK,
    FACE_LEFT_EYE_OUTER,
    FACE_NOSE_TIP,
    FACE_RIGHT_CHEEK,
    FACE_RIGHT_EYE_OUTER,
    LEFT_EAR,
    LEFT_EYE,
    LEFT_SHOULDER,
    NOSE,
    RIGHT_EAR,
    RIGHT_EYE,
    RIGHT_SHOULDER,
    FeatureExtractor,
    Landmark,
    LandmarkObservation,
)


BASE_VALUES = {
    "head_offset_x": 0.0,
    "head_offset_y": -0.70,
    "nose_offset_x": 0.0,
    "nose_offset_y": -0.78,
    "face_scale": 0.38,
    "face_pitch_proxy": 0.28,
    "shoulder_slope": 0.0,
    "shoulder_face_gap": 0.70,
    "left_shoulder_gap": 0.70,
    "right_shoulder_gap": 0.70,
    "torso_length": 1.45,
    "torso_vertical": 1.43,
    "torso_lean": 0.0,
}


def make_frame(
    index: int,
    changes: dict[str, float] | None = None,
    captured_at: datetime | None = None,
) -> FeatureFrame:
    jitter = math.sin(index * 1.7) * 0.003
    values = {name: value + jitter for name, value in BASE_VALUES.items()}
    values.update(changes or {})
    quality = {category: 0.98 for category in PostureCategory}
    return FeatureFrame(
        captured_at=captured_at or datetime.now(timezone.utc),
        values=values,
        category_quality=quality,
        overall_quality=0.98,
        geometry=GeometryFingerprint(
            frame_width=640,
            frame_height=480,
            shoulder_width=180,
            torso_length=260,
            subject_center_x=0.5,
            subject_center_y=0.52,
            shoulder_roll_degrees=0,
            yaw_proxy=0,
        ),
    )


def make_upper_body_frame(
    index: int,
    *,
    shoulder_y: float = 0.38,
    shoulder_tilt: float = 0.0,
    face_shift_x: float = 0.0,
) -> FeatureFrame:
    jitter = math.sin(index * 1.7) * 0.001
    face_x = 0.50 + face_shift_x + jitter
    pose = {
        NOSE: Landmark(x=face_x, y=0.20, visibility=0.99),
        LEFT_EYE: Landmark(x=face_x - 0.03, y=0.18, visibility=0.99),
        RIGHT_EYE: Landmark(x=face_x + 0.03, y=0.18, visibility=0.99),
        LEFT_EAR: Landmark(x=face_x - 0.07, y=0.22, visibility=0.20),
        RIGHT_EAR: Landmark(x=face_x + 0.07, y=0.22, visibility=0.20),
        LEFT_SHOULDER: Landmark(
            x=0.38,
            y=shoulder_y - shoulder_tilt,
            visibility=0.99,
        ),
        RIGHT_SHOULDER: Landmark(
            x=0.62,
            y=shoulder_y + shoulder_tilt,
            visibility=0.99,
        ),
    }
    face = {
        FACE_NOSE_TIP: Landmark(x=face_x, y=0.20),
        FACE_LEFT_EYE_OUTER: Landmark(x=face_x - 0.03, y=0.18),
        FACE_RIGHT_EYE_OUTER: Landmark(x=face_x + 0.03, y=0.18),
        FACE_LEFT_CHEEK: Landmark(x=face_x - 0.05, y=0.22),
        FACE_RIGHT_CHEEK: Landmark(x=face_x + 0.05, y=0.22),
        FACE_FOREHEAD: Landmark(x=face_x, y=0.14),
        FACE_CHIN: Landmark(x=face_x, y=0.27),
    }
    frame = FeatureExtractor().extract(
        LandmarkObservation(pose=pose, face=face),
        640,
        480,
    )
    assert frame is not None
    return frame


def test_upper_body_categories_calibrate_without_pose_ears_or_hips() -> None:
    good = [make_upper_body_frame(index) for index in range(80)]
    sunk_shoulders = [
        make_upper_body_frame(index, shoulder_y=0.45)
        for index in range(40)
    ]
    side_lean = [
        make_upper_body_frame(
            index,
            shoulder_tilt=0.04,
            face_shift_x=0.06,
        )
        for index in range(40)
    ]
    opposite_side_lean = make_upper_body_frame(
        100,
        shoulder_tilt=-0.04,
        face_shift_x=-0.06,
    )

    profile = CalibrationFitter().fit(
        good,
        {
            PostureCategory.SHOULDERS_SUNK: sunk_shoulders,
            PostureCategory.LATERAL_LEAN: side_lean,
        },
    )

    shoulders = profile.categories[PostureCategory.SHOULDERS_SUNK]
    lean = profile.categories[PostureCategory.LATERAL_LEAN]
    assert shoulders.enabled
    assert lean.enabled
    assert "mesh_face_offset_y" in shoulders.feature_names
    assert "mesh_face_offset_x" in lean.feature_names
    shoulder_score, shoulder_quality = category_score(
        sunk_shoulders[-1],
        profile,
        PostureCategory.SHOULDERS_SUNK,
    )
    lean_score, lean_quality = category_score(
        side_lean[-1],
        profile,
        PostureCategory.LATERAL_LEAN,
    )
    opposite_lean_score, opposite_lean_quality = category_score(
        opposite_side_lean,
        profile,
        PostureCategory.LATERAL_LEAN,
    )
    assert shoulder_score > shoulders.on_threshold
    assert shoulder_quality > 0.9
    assert lean_score > lean.on_threshold
    assert lean_quality > 0.9
    assert opposite_lean_score > lean.on_threshold
    assert opposite_lean_quality > 0.9

    incremental = CalibrationFitter().fit(good)
    incremental = CalibrationFitter().fit_category_for_profile(
        incremental,
        good,
        sunk_shoulders,
        PostureCategory.SHOULDERS_SUNK,
    )
    incremental = CalibrationFitter().fit_category_for_profile(
        incremental,
        good,
        side_lean,
        PostureCategory.LATERAL_LEAN,
    )
    assert incremental.categories[PostureCategory.SHOULDERS_SUNK].enabled
    assert incremental.categories[PostureCategory.LATERAL_LEAN].enabled


def test_personalized_forward_head_category_separates() -> None:
    good = [make_frame(index) for index in range(80)]
    bad = [
        make_frame(
            index,
            {
                "head_offset_x": 0.11,
                "nose_offset_x": 0.12,
                "face_scale": 0.47,
            },
        )
        for index in range(40)
    ]
    profile = CalibrationFitter().fit(
        good, {PostureCategory.FORWARD_HEAD: bad}
    )

    learned = profile.categories[PostureCategory.FORWARD_HEAD]
    assert learned.enabled
    score, quality = category_score(
        bad[-1], profile, PostureCategory.FORWARD_HEAD
    )
    assert score > learned.on_threshold
    assert quality > 0.9


def test_lateral_calibration_detects_opposite_side() -> None:
    good = [make_frame(index) for index in range(80)]
    right_lean = [
        make_frame(
            index,
            {
                "torso_lean": 0.16,
                "head_offset_x": 0.14,
                "nose_offset_x": 0.14,
                "shoulder_slope": 0.08,
            },
        )
        for index in range(40)
    ]
    left_lean = make_frame(
        100,
        {
            "torso_lean": -0.16,
            "head_offset_x": -0.14,
            "nose_offset_x": -0.14,
            "shoulder_slope": -0.08,
        },
    )
    profile = CalibrationFitter().fit(
        good, {PostureCategory.LATERAL_LEAN: right_lean}
    )

    score, _ = category_score(
        left_lean, profile, PostureCategory.LATERAL_LEAN
    )
    assert score > profile.categories[
        PostureCategory.LATERAL_LEAN
    ].on_threshold


def test_calibration_timestamps_do_not_affect_features() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    good = [
        make_frame(index, captured_at=start + timedelta(seconds=index / 10))
        for index in range(80)
    ]
    profile = CalibrationFitter().fit(good)
    assert profile.good_sample_count == 80


def test_incremental_category_fit_preserves_existing_profile() -> None:
    good = [make_frame(index) for index in range(80)]
    sunk_shoulders = [
        make_frame(
            index,
            {
                "shoulder_face_gap": 0.48,
                "left_shoulder_gap": 0.48,
                "right_shoulder_gap": 0.48,
            },
        )
        for index in range(40)
    ]
    forward_head = [
        make_frame(
            index,
            {
                "head_offset_x": 0.11,
                "nose_offset_x": 0.12,
                "face_scale": 0.47,
            },
        )
        for index in range(40)
    ]
    fitter = CalibrationFitter()
    original = fitter.fit(
        good,
        {PostureCategory.SHOULDERS_SUNK: sunk_shoulders},
    )
    original_snapshot = original.model_copy(deep=True)

    updated = fitter.fit_category_for_profile(
        original,
        good,
        forward_head,
        PostureCategory.FORWARD_HEAD,
    )

    assert PostureCategory.FORWARD_HEAD not in original.categories
    assert updated.categories[PostureCategory.FORWARD_HEAD].enabled
    assert (
        updated.categories[PostureCategory.SHOULDERS_SUNK]
        == original_snapshot.categories[PostureCategory.SHOULDERS_SUNK]
    )
    assert updated.good_center == original_snapshot.good_center
    assert updated.good_scale == original_snapshot.good_scale
    assert updated.geometry == original_snapshot.geometry


def test_incremental_category_fit_rejects_changed_baseline() -> None:
    good = [make_frame(index) for index in range(80)]
    changed_baseline = [
        make_frame(
            index,
            {
                "head_offset_x": 0.30,
                "nose_offset_x": 0.30,
                "torso_lean": 0.25,
            },
        )
        for index in range(80)
    ]
    forward_head = [
        make_frame(
            index,
            {
                "head_offset_x": 0.11,
                "nose_offset_x": 0.12,
                "face_scale": 0.47,
            },
        )
        for index in range(40)
    ]
    profile = CalibrationFitter().fit(good)

    with pytest.raises(CalibrationError, match="does not match"):
        CalibrationFitter().fit_category_for_profile(
            profile,
            changed_baseline,
            forward_head,
            PostureCategory.FORWARD_HEAD,
        )


def test_incremental_category_fit_replaces_only_selected_category() -> None:
    good = [make_frame(index) for index in range(80)]
    first_forward_head = [
        make_frame(
            index,
            {
                "head_offset_x": 0.11,
                "nose_offset_x": 0.12,
                "face_scale": 0.47,
            },
        )
        for index in range(40)
    ]
    second_forward_head = [
        make_frame(
            index,
            {
                "head_offset_y": -0.50,
                "nose_offset_y": -0.56,
                "face_pitch_proxy": 0.48,
            },
        )
        for index in range(40)
    ]
    sunk_shoulders = [
        make_frame(
            index,
            {
                "shoulder_face_gap": 0.48,
                "left_shoulder_gap": 0.48,
                "right_shoulder_gap": 0.48,
            },
        )
        for index in range(40)
    ]
    fitter = CalibrationFitter()
    original = fitter.fit(
        good,
        {
            PostureCategory.FORWARD_HEAD: first_forward_head,
            PostureCategory.SHOULDERS_SUNK: sunk_shoulders,
        },
    )
    snapshot = original.model_copy(deep=True)

    updated = fitter.fit_category_for_profile(
        original,
        good,
        second_forward_head,
        PostureCategory.FORWARD_HEAD,
    )

    assert (
        updated.categories[PostureCategory.FORWARD_HEAD]
        != snapshot.categories[PostureCategory.FORWARD_HEAD]
    )
    assert (
        updated.categories[PostureCategory.SHOULDERS_SUNK]
        == snapshot.categories[PostureCategory.SHOULDERS_SUNK]
    )
    assert original == snapshot
