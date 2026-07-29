from __future__ import annotations

import numpy as np

from vulture.models import PostureCategory
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
    LEFT_HIP,
    LEFT_SHOULDER,
    NOSE,
    RIGHT_EAR,
    RIGHT_EYE,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    FeatureExtractor,
    Landmark,
    LandmarkObservation,
    _select_foreground_pose,
)


def test_upper_body_postures_do_not_require_pose_ears_or_hips() -> None:
    pose = {
        NOSE: Landmark(x=0.50, y=0.20, visibility=0.99),
        LEFT_EYE: Landmark(x=0.47, y=0.18, visibility=0.99),
        RIGHT_EYE: Landmark(x=0.53, y=0.18, visibility=0.99),
        LEFT_EAR: Landmark(x=0.43, y=0.22, visibility=0.20),
        RIGHT_EAR: Landmark(x=0.57, y=0.22, visibility=0.20),
        LEFT_SHOULDER: Landmark(x=0.38, y=0.38, visibility=0.99),
        RIGHT_SHOULDER: Landmark(x=0.62, y=0.38, visibility=0.99),
    }
    face = {
        FACE_NOSE_TIP: Landmark(x=0.50, y=0.20),
        FACE_LEFT_EYE_OUTER: Landmark(x=0.47, y=0.18),
        FACE_RIGHT_EYE_OUTER: Landmark(x=0.53, y=0.18),
        FACE_LEFT_CHEEK: Landmark(x=0.45, y=0.22),
        FACE_RIGHT_CHEEK: Landmark(x=0.55, y=0.22),
        FACE_FOREHEAD: Landmark(x=0.50, y=0.14),
        FACE_CHIN: Landmark(x=0.50, y=0.27),
    }

    frame = FeatureExtractor().extract(
        LandmarkObservation(pose=pose, face=face),
        640,
        480,
    )

    assert frame is not None
    assert "torso_lean" not in frame.values
    assert "head_offset_x" not in frame.values
    assert "mesh_face_offset_x" in frame.values
    assert frame.category_quality[PostureCategory.SHOULDERS_SUNK] == 0.99
    assert frame.category_quality[PostureCategory.LATERAL_LEAN] == 0.99


def test_low_confidence_hips_do_not_create_torso_features() -> None:
    pose = {
        NOSE: Landmark(x=0.50, y=0.20, visibility=0.99),
        LEFT_EYE: Landmark(x=0.47, y=0.18, visibility=0.99),
        RIGHT_EYE: Landmark(x=0.53, y=0.18, visibility=0.99),
        LEFT_EAR: Landmark(x=0.43, y=0.22, visibility=0.99),
        RIGHT_EAR: Landmark(x=0.57, y=0.22, visibility=0.99),
        LEFT_SHOULDER: Landmark(x=0.38, y=0.38, visibility=0.99),
        RIGHT_SHOULDER: Landmark(x=0.62, y=0.38, visibility=0.99),
        LEFT_HIP: Landmark(x=0.10, y=0.95, visibility=0.20),
        RIGHT_HIP: Landmark(x=0.90, y=0.95, visibility=0.20),
    }
    frame = FeatureExtractor().extract(
        LandmarkObservation(pose=pose), 640, 480
    )

    assert frame is not None
    assert "torso_length" not in frame.values
    assert frame.geometry.torso_length is None
    assert frame.category_quality[PostureCategory.SLOUCH] < 0.7


def test_out_of_frame_subject_is_rejected_without_validation_error() -> None:
    pose = {
        NOSE: Landmark(x=1.08, y=0.20, visibility=0.99),
        LEFT_SHOULDER: Landmark(x=1.02, y=0.38, visibility=0.99),
        RIGHT_SHOULDER: Landmark(x=1.20, y=0.38, visibility=0.99),
        LEFT_HIP: Landmark(x=1.04, y=0.80, visibility=0.99),
        RIGHT_HIP: Landmark(x=1.18, y=0.80, visibility=0.99),
    }

    frame = FeatureExtractor().extract(
        LandmarkObservation(pose=pose),
        640,
        480,
    )

    assert frame is None


def test_out_of_frame_hips_are_ignored() -> None:
    pose = {
        NOSE: Landmark(x=0.50, y=0.20, visibility=0.99),
        LEFT_SHOULDER: Landmark(x=0.38, y=0.38, visibility=0.99),
        RIGHT_SHOULDER: Landmark(x=0.62, y=0.38, visibility=0.99),
        LEFT_HIP: Landmark(x=0.42, y=1.08, visibility=0.99),
        RIGHT_HIP: Landmark(x=0.58, y=1.08, visibility=0.99),
    }

    frame = FeatureExtractor().extract(
        LandmarkObservation(pose=pose),
        640,
        480,
    )

    assert frame is not None
    assert frame.geometry.torso_length is None
    assert frame.geometry.subject_center_x == 0.5
    assert frame.geometry.subject_center_y == 0.38


def test_degenerate_hips_are_ignored() -> None:
    pose = {
        NOSE: Landmark(x=0.50, y=0.20, visibility=0.99),
        LEFT_SHOULDER: Landmark(x=0.38, y=0.38, visibility=0.99),
        RIGHT_SHOULDER: Landmark(x=0.62, y=0.38, visibility=0.99),
        LEFT_HIP: Landmark(x=0.38, y=0.38, visibility=0.99),
        RIGHT_HIP: Landmark(x=0.62, y=0.38, visibility=0.99),
    }

    frame = FeatureExtractor().extract(
        LandmarkObservation(pose=pose),
        640,
        480,
    )

    assert frame is not None
    assert frame.geometry.torso_length is None
    assert "torso_length" not in frame.values
    assert frame.category_quality[PostureCategory.SLOUCH] == 0.0
    assert frame.category_quality[PostureCategory.LATERAL_LEAN] == 0.99


def test_foreground_selector_prefers_larger_supported_person() -> None:
    background_pose = {
        NOSE: Landmark(x=0.50, y=0.24, visibility=0.99),
        LEFT_SHOULDER: Landmark(x=0.45, y=0.38, visibility=0.99),
        RIGHT_SHOULDER: Landmark(x=0.55, y=0.38, visibility=0.99),
    }
    foreground_pose = {
        NOSE: Landmark(x=0.56, y=0.20, visibility=0.99),
        LEFT_SHOULDER: Landmark(x=0.38, y=0.40, visibility=0.99),
        RIGHT_SHOULDER: Landmark(x=0.74, y=0.40, visibility=0.99),
    }
    background_mask = np.zeros((100, 100), dtype=np.float32)
    background_mask[18:75, 43:58] = 1.0
    foreground_mask = np.zeros((100, 100), dtype=np.float32)
    foreground_mask[12:92, 30:82] = 1.0

    selected = _select_foreground_pose(
        [background_pose, foreground_pose],
        [background_mask, foreground_mask],
    )

    assert selected is not None
    assert selected[0] == 1
    assert selected[1] is foreground_pose


def test_foreground_selector_rejects_pose_without_mask() -> None:
    pose = {
        NOSE: Landmark(x=0.50, y=0.20, visibility=0.99),
        LEFT_SHOULDER: Landmark(x=0.38, y=0.40, visibility=0.99),
        RIGHT_SHOULDER: Landmark(x=0.62, y=0.40, visibility=0.99),
    }

    assert _select_foreground_pose([pose], [None]) is None
