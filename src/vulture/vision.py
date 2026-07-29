from __future__ import annotations

import math
import time
from collections.abc import Mapping
from pathlib import Path

import numpy as np
from pydantic import Field

from vulture.i18n import tr
from vulture.models import (
    FeatureFrame,
    GeometryFingerprint,
    PostureCategory,
    StrictModel,
)
from vulture.resources import resource_path


LEFT_EYE = 2
RIGHT_EYE = 5
LEFT_EAR = 7
RIGHT_EAR = 8
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24
NOSE = 0

FACE_NOSE_TIP = 1
FACE_LEFT_EYE_OUTER = 33
FACE_RIGHT_EYE_OUTER = 263
FACE_LEFT_CHEEK = 234
FACE_RIGHT_CHEEK = 454
FACE_FOREHEAD = 10
FACE_CHIN = 152
FEATURE_QUALITY_THRESHOLD = 0.70
MIN_PERSON_MASK_FRACTION = 0.01
MAX_PERSON_MASK_FRACTION = 0.98
MIN_MASK_LANDMARK_SUPPORT = 0.15
MAX_DETECTED_POSES = 2


class VisionDependencyError(RuntimeError):
    pass


class Landmark(StrictModel):
    x: float
    y: float
    z: float = 0.0
    visibility: float = Field(default=1.0, ge=0, le=1)
    presence: float = Field(default=1.0, ge=0, le=1)

    @property
    def quality(self) -> float:
        return min(self.visibility, self.presence)


class LandmarkObservation(StrictModel):
    pose: dict[int, Landmark]
    face: dict[int, Landmark] = Field(default_factory=dict)


def _point(landmark: Landmark, width: int, height: int) -> tuple[float, float]:
    return landmark.x * width, landmark.y * height


def _midpoint(
    left: tuple[float, float], right: tuple[float, float]
) -> tuple[float, float]:
    return (left[0] + right[0]) / 2, (left[1] + right[1]) / 2


def _distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _minimum_quality(
    landmarks: Mapping[int, Landmark], indices: tuple[int, ...]
) -> float:
    if any(
        index not in landmarks or not _landmark_in_frame(landmarks[index])
        for index in indices
    ):
        return 0.0
    return min(landmarks[index].quality for index in indices)


def _landmark_in_frame(landmark: Landmark) -> bool:
    return (
        math.isfinite(landmark.x)
        and math.isfinite(landmark.y)
        and 0.0 <= landmark.x <= 1.0
        and 0.0 <= landmark.y <= 1.0
    )


def _mask_value_at(
    mask: np.ndarray,
    landmark: Landmark,
) -> float:
    height, width = mask.shape
    center_x = round(landmark.x * (width - 1))
    center_y = round(landmark.y * (height - 1))
    radius = max(2, round(min(width, height) * 0.008))
    left = max(0, center_x - radius)
    right = min(width, center_x + radius + 1)
    top = max(0, center_y - radius)
    bottom = min(height, center_y + radius + 1)
    patch = mask[top:bottom, left:right]
    return float(patch.mean()) if patch.size else 0.0


def _mask_supports_pose(
    mask: np.ndarray | None,
    pose: Mapping[int, Landmark],
) -> bool:
    if (
        mask is None
        or mask.ndim != 2
        or mask.size == 0
        or any(
            index not in pose or not _landmark_in_frame(pose[index])
            for index in (NOSE, LEFT_SHOULDER, RIGHT_SHOULDER)
        )
    ):
        return False
    foreground_fraction = float((mask >= 0.5).mean())
    if not (
        MIN_PERSON_MASK_FRACTION
        <= foreground_fraction
        <= MAX_PERSON_MASK_FRACTION
    ):
        return False
    support = [
        _mask_value_at(mask, pose[index])
        for index in (NOSE, LEFT_SHOULDER, RIGHT_SHOULDER)
    ]
    return (
        sum(value >= MIN_MASK_LANDMARK_SUPPORT for value in support) >= 2
        and max(support) >= 0.45
    )


def _pose_candidate_score(
    pose: Mapping[int, Landmark],
    mask: np.ndarray | None,
) -> float | None:
    if mask is None:
        return None
    required = (NOSE, LEFT_SHOULDER, RIGHT_SHOULDER)
    quality = _minimum_quality(pose, required)
    if quality < 0.5:
        return None
    left_shoulder = pose[LEFT_SHOULDER]
    right_shoulder = pose[RIGHT_SHOULDER]
    shoulder_width = math.hypot(
        left_shoulder.x - right_shoulder.x,
        left_shoulder.y - right_shoulder.y,
    )
    if shoulder_width < 0.035:
        return None
    center_x = (left_shoulder.x + right_shoulder.x) / 2
    center_y = (left_shoulder.y + right_shoulder.y) / 2
    center_distance = math.hypot(center_x - 0.5, center_y - 0.45)
    center_score = max(0.0, 1.0 - center_distance / 0.75)
    if not _mask_supports_pose(mask, pose):
        return None
    foreground_fraction = float((mask >= 0.5).mean())
    mask_score = min(foreground_fraction / 0.35, 1.0)
    return (
        quality * 4.0
        + min(shoulder_width / 0.45, 1.0) * 3.0
        + center_score
        + mask_score
    )


def _select_foreground_pose(
    poses: list[dict[int, Landmark]],
    masks: list[np.ndarray | None],
) -> tuple[int, dict[int, Landmark], np.ndarray | None] | None:
    scored: list[
        tuple[float, int, dict[int, Landmark], np.ndarray | None]
    ] = []
    for index, pose in enumerate(poses):
        mask = masks[index] if index < len(masks) else None
        score = _pose_candidate_score(pose, mask)
        if score is not None:
            scored.append((score, index, pose, mask))
    if not scored:
        return None
    _score, index, pose, mask = max(scored, key=lambda item: item[0])
    return index, pose, mask


def _face_matches_pose(
    face: Mapping[int, Landmark],
    pose: Mapping[int, Landmark],
) -> bool:
    required_pose = (NOSE, LEFT_SHOULDER, RIGHT_SHOULDER)
    if (
        FACE_NOSE_TIP not in face
        or _minimum_quality(pose, required_pose) == 0.0
        or not _landmark_in_frame(face[FACE_NOSE_TIP])
    ):
        return False
    left_shoulder = pose[LEFT_SHOULDER]
    right_shoulder = pose[RIGHT_SHOULDER]
    shoulder_width = math.hypot(
        left_shoulder.x - right_shoulder.x,
        left_shoulder.y - right_shoulder.y,
    )
    pose_nose = pose[NOSE]
    face_nose = face[FACE_NOSE_TIP]
    nose_distance = math.hypot(
        pose_nose.x - face_nose.x,
        pose_nose.y - face_nose.y,
    )
    return nose_distance <= max(0.04, shoulder_width * 0.65)


class FeatureExtractor:
    """Converts landmarks into scale-normalized, calibration-friendly proxies."""

    def extract(
        self,
        observation: LandmarkObservation,
        frame_width: int,
        frame_height: int,
    ) -> FeatureFrame | None:
        pose = observation.pose
        required = (LEFT_SHOULDER, RIGHT_SHOULDER, NOSE)
        if any(index not in pose for index in required):
            return None
        shoulder_quality = _minimum_quality(
            pose, (LEFT_SHOULDER, RIGHT_SHOULDER)
        )
        nose_shoulder_quality = _minimum_quality(
            pose, (NOSE, LEFT_SHOULDER, RIGHT_SHOULDER)
        )
        if (
            shoulder_quality < FEATURE_QUALITY_THRESHOLD
            or nose_shoulder_quality < FEATURE_QUALITY_THRESHOLD
        ):
            return None

        left_shoulder = _point(pose[LEFT_SHOULDER], frame_width, frame_height)
        right_shoulder = _point(pose[RIGHT_SHOULDER], frame_width, frame_height)
        shoulder_mid = _midpoint(left_shoulder, right_shoulder)
        shoulder_width = _distance(left_shoulder, right_shoulder)
        if shoulder_width < frame_width * 0.035:
            return None

        nose = _point(pose[NOSE], frame_width, frame_height)
        left_eye = _point(pose.get(LEFT_EYE, pose[NOSE]), frame_width, frame_height)
        right_eye = _point(pose.get(RIGHT_EYE, pose[NOSE]), frame_width, frame_height)
        eye_mid = _midpoint(left_eye, right_eye)
        left_ear = _point(pose.get(LEFT_EAR, pose[NOSE]), frame_width, frame_height)
        right_ear = _point(pose.get(RIGHT_EAR, pose[NOSE]), frame_width, frame_height)
        ear_mid = _midpoint(left_ear, right_ear)
        ear_width = _distance(left_ear, right_ear)

        values = {
            "nose_offset_x": (nose[0] - shoulder_mid[0]) / shoulder_width,
            "nose_offset_y": (nose[1] - shoulder_mid[1]) / shoulder_width,
            "shoulder_slope": (
                right_shoulder[1] - left_shoulder[1]
            ) / shoulder_width,
        }
        head_quality = _minimum_quality(
            pose, (NOSE, LEFT_EAR, RIGHT_EAR, LEFT_SHOULDER, RIGHT_SHOULDER)
        )
        eye_quality = _minimum_quality(
            pose, (LEFT_EYE, RIGHT_EYE, NOSE)
        )
        if head_quality >= FEATURE_QUALITY_THRESHOLD:
            values.update(
                {
                    "head_offset_x": (
                        ear_mid[0] - shoulder_mid[0]
                    ) / shoulder_width,
                    "head_offset_y": (
                        ear_mid[1] - shoulder_mid[1]
                    ) / shoulder_width,
                    "face_scale": ear_width / shoulder_width,
                    "shoulder_face_gap": (
                        shoulder_mid[1] - ear_mid[1]
                    ) / shoulder_width,
                    "left_shoulder_gap": (
                        left_shoulder[1] - left_ear[1]
                    ) / shoulder_width,
                    "right_shoulder_gap": (
                        right_shoulder[1] - right_ear[1]
                    ) / shoulder_width,
                }
            )
            if eye_quality >= FEATURE_QUALITY_THRESHOLD:
                values["face_pitch_proxy"] = (
                    nose[1] - eye_mid[1]
                ) / max(ear_width, 1.0)

        face_quality = 0.0
        face = observation.face
        face_indices = (
            FACE_NOSE_TIP,
            FACE_LEFT_EYE_OUTER,
            FACE_RIGHT_EYE_OUTER,
            FACE_LEFT_CHEEK,
            FACE_RIGHT_CHEEK,
            FACE_FOREHEAD,
            FACE_CHIN,
        )
        face_quality = _minimum_quality(face, face_indices)
        if face_quality >= FEATURE_QUALITY_THRESHOLD:
            face_left = _point(face[FACE_LEFT_CHEEK], frame_width, frame_height)
            face_right = _point(face[FACE_RIGHT_CHEEK], frame_width, frame_height)
            face_top = _point(face[FACE_FOREHEAD], frame_width, frame_height)
            face_bottom = _point(face[FACE_CHIN], frame_width, frame_height)
            face_nose = _point(face[FACE_NOSE_TIP], frame_width, frame_height)
            face_left_eye = _point(
                face[FACE_LEFT_EYE_OUTER], frame_width, frame_height
            )
            face_right_eye = _point(
                face[FACE_RIGHT_EYE_OUTER], frame_width, frame_height
            )
            face_eye_mid = _midpoint(face_left_eye, face_right_eye)
            face_width = max(_distance(face_left, face_right), 1.0)
            face_height = max(_distance(face_top, face_bottom), 1.0)
            values.update(
                {
                    "mesh_face_scale": face_width / shoulder_width,
                    "mesh_face_pitch": (
                        face_nose[1] - face_eye_mid[1]
                    ) / face_height,
                    "mesh_face_offset_x": (
                        face_nose[0] - shoulder_mid[0]
                    ) / shoulder_width,
                    "mesh_face_offset_y": (
                        face_nose[1] - shoulder_mid[1]
                    ) / shoulder_width,
                }
            )
        hip_quality = _minimum_quality(pose, (LEFT_HIP, RIGHT_HIP))
        torso_length: float | None = None
        subject_center = shoulder_mid
        torso_lean = 0.0
        if (
            LEFT_HIP in pose
            and RIGHT_HIP in pose
            and hip_quality >= FEATURE_QUALITY_THRESHOLD
        ):
            left_hip = _point(pose[LEFT_HIP], frame_width, frame_height)
            right_hip = _point(pose[RIGHT_HIP], frame_width, frame_height)
            hip_mid = _midpoint(left_hip, right_hip)
            candidate_torso_length = _distance(shoulder_mid, hip_mid)
            if candidate_torso_length > 1.0:
                torso_length = candidate_torso_length
                subject_center = _midpoint(shoulder_mid, hip_mid)
                torso_lean = (shoulder_mid[0] - hip_mid[0]) / torso_length
                values.update(
                    {
                        "torso_length": torso_length / shoulder_width,
                        "torso_vertical": (
                            hip_mid[1] - shoulder_mid[1]
                        ) / shoulder_width,
                        "torso_lean": torso_lean,
                    }
                )
            else:
                hip_quality = 0.0

        upper_body_quality = max(
            nose_shoulder_quality,
            min(shoulder_quality, head_quality),
            min(shoulder_quality, face_quality),
        )
        category_quality = {
            PostureCategory.FORWARD_HEAD: max(
                min(head_quality, shoulder_quality),
                min(shoulder_quality, face_quality),
            ),
            PostureCategory.SLOUCH: min(shoulder_quality, hip_quality),
            PostureCategory.SHOULDERS_SUNK: upper_body_quality,
            PostureCategory.LATERAL_LEAN: max(
                min(shoulder_quality, hip_quality),
                upper_body_quality,
            ),
            PostureCategory.GENERAL_DEVIATION: min(
                shoulder_quality, max(head_quality, hip_quality)
            ),
        }
        overall_quality = max(category_quality.values())
        yaw_proxy = (
            _distance(nose, left_shoulder)
            - _distance(nose, right_shoulder)
        ) / shoulder_width
        subject_center_x = subject_center[0] / frame_width
        subject_center_y = subject_center[1] / frame_height
        if not (
            0.0 <= subject_center_x <= 1.0
            and 0.0 <= subject_center_y <= 1.0
        ):
            return None

        geometry = GeometryFingerprint(
            frame_width=frame_width,
            frame_height=frame_height,
            shoulder_width=shoulder_width,
            torso_length=torso_length,
            subject_center_x=subject_center_x,
            subject_center_y=subject_center_y,
            shoulder_roll_degrees=math.degrees(
                math.atan2(
                    right_shoulder[1] - left_shoulder[1],
                    right_shoulder[0] - left_shoulder[0],
                )
            ),
            yaw_proxy=yaw_proxy,
        )
        return FeatureFrame(
            values=values,
            category_quality=category_quality,
            overall_quality=overall_quality,
            geometry=geometry,
        )


class MediaPipeDetector:
    """Local MediaPipe detector. Frames are returned to the caller, not retained."""

    def __init__(
        self,
        minimum_detection_confidence: float = 0.6,
        pose_model_path: Path | None = None,
        face_model_path: Path | None = None,
    ) -> None:
        try:
            import mediapipe as mp
        except ImportError as error:
            raise VisionDependencyError(
                tr(
                    "MediaPipe is not installed. Install the project "
                    "dependencies first."
                )
            ) from error

        pose_asset = pose_model_path or resource_path(
            "models", "pose_landmarker_full.task"
        )
        face_asset = face_model_path or resource_path(
            "models", "face_landmarker.task"
        )
        vision = mp.tasks.vision
        running_mode = vision.RunningMode.VIDEO
        self._mp = mp
        self._pose = vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(
                    model_asset_path=str(pose_asset)
                ),
                running_mode=running_mode,
                num_poses=MAX_DETECTED_POSES,
                min_pose_detection_confidence=minimum_detection_confidence,
                min_pose_presence_confidence=minimum_detection_confidence,
                min_tracking_confidence=0.6,
                output_segmentation_masks=True,
            )
        )
        self._face = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(
                    model_asset_path=str(face_asset)
                ),
                running_mode=running_mode,
                num_faces=1,
                min_face_detection_confidence=minimum_detection_confidence,
                min_face_presence_confidence=minimum_detection_confidence,
                min_tracking_confidence=0.6,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
            )
        )
        self._last_timestamp_ms = 0
        self.person_mask: np.ndarray | None = None

    @staticmethod
    def _confidence(item, attribute: str) -> float:
        value = getattr(item, attribute, None)
        if value is None:
            return 1.0
        return max(0.0, min(1.0, float(value)))

    def process(self, rgb_frame) -> LandmarkObservation | None:
        self.person_mask = None
        timestamp_ms = max(
            self._last_timestamp_ms + 1,
            time.monotonic_ns() // 1_000_000,
        )
        self._last_timestamp_ms = timestamp_ms
        image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB,
            data=rgb_frame,
        )
        pose_result = self._pose.detect_for_video(image, timestamp_ms)
        if not pose_result.pose_landmarks:
            return None
        poses = [
            {
                index: Landmark(
                    x=item.x,
                    y=item.y,
                    z=item.z,
                    visibility=self._confidence(item, "visibility"),
                    presence=self._confidence(item, "presence"),
                )
                for index, item in enumerate(items)
            }
            for items in pose_result.pose_landmarks
        ]
        masks: list[np.ndarray | None] = []
        segmentation_masks = pose_result.segmentation_masks or []
        for index in range(len(poses)):
            if index >= len(segmentation_masks):
                masks.append(None)
                continue
            raw_mask = np.asarray(
                segmentation_masks[index].numpy_view(),
                dtype=np.float32,
            ).squeeze()
            if raw_mask.ndim != 2 or raw_mask.shape != rgb_frame.shape[:2]:
                masks.append(None)
                continue
            masks.append(
                np.nan_to_num(
                    raw_mask,
                    nan=0.0,
                    posinf=1.0,
                    neginf=0.0,
                ).clip(0.0, 1.0).copy()
            )
        selected = _select_foreground_pose(poses, masks)
        if selected is None:
            return None
        _selected_index, pose, person_mask = selected
        self.person_mask = person_mask

        face_frame = rgb_frame
        if person_mask is not None:
            alpha = np.clip(
                (person_mask - 0.05) / 0.55,
                0.0,
                1.0,
            )[..., None]
            face_frame = np.ascontiguousarray(
                np.rint(
                    rgb_frame.astype(np.float32) * alpha
                    + 127.0 * (1.0 - alpha)
                ).astype(np.uint8)
            )
        face_image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB,
            data=face_frame,
        )
        face_result = self._face.detect_for_video(
            face_image,
            timestamp_ms,
        )
        face: dict[int, Landmark] = {}
        if face_result.face_landmarks:
            candidate_face = {
                index: Landmark(
                    x=item.x,
                    y=item.y,
                    z=item.z,
                    visibility=self._confidence(item, "visibility"),
                    presence=self._confidence(item, "presence"),
                )
                for index, item in enumerate(
                    face_result.face_landmarks[0]
                )
            }
            if _face_matches_pose(candidate_face, pose):
                face = candidate_face
        return LandmarkObservation(pose=pose, face=face)

    def close(self) -> None:
        self._pose.close()
        self._face.close()
        self.person_mask = None
