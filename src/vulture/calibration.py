from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

import numpy as np

from vulture.i18n import tr
from vulture.models import (
    CalibrationProfile,
    CategoryCalibration,
    FeatureFrame,
    GeometryFingerprint,
    PostureCategory,
)


CATEGORY_FEATURES: dict[PostureCategory, tuple[str, ...]] = {
    PostureCategory.FORWARD_HEAD: (
        "head_offset_x",
        "head_offset_y",
        "nose_offset_x",
        "nose_offset_y",
        "face_scale",
        "face_pitch_proxy",
        "mesh_face_scale",
        "mesh_face_pitch",
        "mesh_face_offset_x",
        "mesh_face_offset_y",
        "shoulder_face_gap",
    ),
    PostureCategory.SLOUCH: (
        "torso_length",
        "torso_vertical",
        "torso_lean",
        "head_offset_x",
        "head_offset_y",
        "shoulder_face_gap",
    ),
    PostureCategory.SHOULDERS_SUNK: (
        "nose_offset_y",
        "mesh_face_offset_y",
        "face_scale",
        "mesh_face_scale",
        "shoulder_face_gap",
        "left_shoulder_gap",
        "right_shoulder_gap",
        "shoulder_slope",
    ),
    PostureCategory.LATERAL_LEAN: (
        "torso_lean",
        "head_offset_x",
        "nose_offset_x",
        "mesh_face_offset_x",
        "shoulder_slope",
    ),
}

GENERAL_FEATURES = (
    "head_offset_x",
    "head_offset_y",
    "nose_offset_x",
    "nose_offset_y",
    "face_scale",
    "face_pitch_proxy",
    "shoulder_slope",
    "shoulder_face_gap",
    "left_shoulder_gap",
    "right_shoulder_gap",
    "torso_length",
    "torso_vertical",
    "torso_lean",
)


class CalibrationError(ValueError):
    pass


def _median(values: Sequence[float]) -> float:
    return float(np.median(np.asarray(values, dtype=float)))


def _percentile(values: Sequence[float], percentile: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), percentile))


def _robust_scale(values: Sequence[float], center: float) -> float:
    deviations = np.abs(np.asarray(values, dtype=float) - center)
    median_absolute_deviation = float(np.median(deviations))
    empirical_floor = max(abs(center) * 0.015, 0.008)
    return max(median_absolute_deviation * 1.4826, empirical_floor)


def _available_feature_names(
    frames: Sequence[FeatureFrame],
    requested: Iterable[str],
    required_fraction: float = 0.85,
) -> list[str]:
    minimum_count = max(1, math.ceil(len(frames) * required_fraction))
    return [
        name
        for name in requested
        if sum(name in frame.values for frame in frames) >= minimum_count
    ]


def _feature_value(
    frame: FeatureFrame,
    name: str,
    center: Mapping[str, float],
) -> float:
    return frame.values.get(name, center[name])


def _median_geometry(frames: Sequence[FeatureFrame]) -> GeometryFingerprint:
    torso_lengths = [
        frame.geometry.torso_length
        for frame in frames
        if frame.geometry.torso_length is not None
    ]
    return GeometryFingerprint(
        frame_width=round(_median([item.geometry.frame_width for item in frames])),
        frame_height=round(_median([item.geometry.frame_height for item in frames])),
        shoulder_width=_median(
            [item.geometry.shoulder_width for item in frames]
        ),
        torso_length=_median(torso_lengths) if torso_lengths else None,
        subject_center_x=_median(
            [item.geometry.subject_center_x for item in frames]
        ),
        subject_center_y=_median(
            [item.geometry.subject_center_y for item in frames]
        ),
        shoulder_roll_degrees=_median(
            [item.geometry.shoulder_roll_degrees for item in frames]
        ),
        yaw_proxy=_median([item.geometry.yaw_proxy for item in frames]),
    )


class CalibrationFitter:
    def __init__(
        self,
        minimum_quality: float = 0.70,
        minimum_good_samples: int = 30,
        minimum_bad_samples: int = 15,
    ) -> None:
        self.minimum_quality = minimum_quality
        self.minimum_good_samples = minimum_good_samples
        self.minimum_bad_samples = minimum_bad_samples

    def fit(
        self,
        good_frames: Sequence[FeatureFrame],
        bad_frames: Mapping[PostureCategory, Sequence[FeatureFrame]] | None = None,
    ) -> CalibrationProfile:
        usable_good = [
            frame
            for frame in good_frames
            if frame.overall_quality >= self.minimum_quality
        ]
        if len(usable_good) < self.minimum_good_samples:
            raise CalibrationError(
                tr(
                    "Need at least {minimum} clear good-posture samples; "
                    "received {received}.",
                    minimum=self.minimum_good_samples,
                    received=len(usable_good),
                )
            )
        provisional_geometry = _median_geometry(usable_good)
        usable_good = [
            frame
            for frame in usable_good
            if geometry_compatible(
                frame.geometry, provisional_geometry
            )[0]
        ]
        if len(usable_good) < self.minimum_good_samples:
            raise CalibrationError(
                tr(
                    "The camera or seating position moved too much during the "
                    "baseline sample. Keep the setup still and retry."
                )
            )
        calibrated_geometry = _median_geometry(usable_good)

        all_requested = tuple(
            dict.fromkeys(
                GENERAL_FEATURES
                + tuple(
                    feature
                    for features in CATEGORY_FEATURES.values()
                    for feature in features
                )
            )
        )
        feature_names = _available_feature_names(usable_good, all_requested)
        if len(feature_names) < 6:
            raise CalibrationError(
                tr("Too few stable head-and-shoulder features were visible.")
            )

        center: dict[str, float] = {}
        scale: dict[str, float] = {}
        for name in feature_names:
            values = [
                frame.values[name]
                for frame in usable_good
                if name in frame.values
            ]
            center[name] = _median(values)
            scale[name] = _robust_scale(values, center[name])

        general_names = [name for name in GENERAL_FEATURES if name in center]
        general_good_scores = [
            general_deviation_score(frame, center, scale, general_names)
            for frame in usable_good
        ]
        general_on = max(4.0, _percentile(general_good_scores, 99) + 1.0)
        general_off = max(2.5, general_on * 0.70)

        categories: dict[PostureCategory, CategoryCalibration] = {}
        for category, frames in (bad_frames or {}).items():
            if category not in CATEGORY_FEATURES:
                continue
            usable_bad = [
                frame
                for frame in frames
                if frame.category_quality.get(category, 0.0)
                >= self.minimum_quality
                and geometry_compatible(
                    frame.geometry, calibrated_geometry
                )[0]
            ]
            if len(usable_bad) < self.minimum_bad_samples:
                continue
            category_calibration = self._fit_category(
                category,
                usable_good,
                usable_bad,
                center,
                scale,
            )
            if category_calibration is not None:
                categories[category] = category_calibration

        return CalibrationProfile(
            good_center=center,
            good_scale=scale,
            good_sample_count=len(usable_good),
            geometry=calibrated_geometry,
            categories=categories,
            general_on_threshold=general_on,
            general_off_threshold=general_off,
        )

    def fit_category_for_profile(
        self,
        profile: CalibrationProfile,
        good_frames: Sequence[FeatureFrame],
        bad_frames: Sequence[FeatureFrame],
        category: PostureCategory,
    ) -> CalibrationProfile:
        if category not in CATEGORY_FEATURES:
            raise CalibrationError(
                tr("This posture category cannot be calibrated.")
            )

        usable_good = [
            frame
            for frame in good_frames
            if frame.overall_quality >= self.minimum_quality
            and geometry_compatible(frame.geometry, profile.geometry)[0]
        ]
        if len(usable_good) < self.minimum_good_samples:
            raise CalibrationError(
                tr(
                    "Need at least {minimum} clear baseline samples in the "
                    "original camera position; received {received}.",
                    minimum=self.minimum_good_samples,
                    received=len(usable_good),
                )
            )

        general_names = [
            name for name in GENERAL_FEATURES if name in profile.good_center
        ]
        baseline_scores = [
            general_deviation_score(
                frame,
                profile.good_center,
                profile.good_scale,
                general_names,
            )
            for frame in usable_good
        ]
        if _median(baseline_scores) > profile.general_off_threshold:
            raise CalibrationError(
                tr(
                    "The demonstrated baseline does not match this setup's "
                    "saved baseline. Return to the original position or run "
                    "a full calibration."
                )
            )

        usable_bad = [
            frame
            for frame in bad_frames
            if frame.category_quality.get(category, 0.0)
            >= self.minimum_quality
            and geometry_compatible(frame.geometry, profile.geometry)[0]
        ]
        if len(usable_bad) < self.minimum_bad_samples:
            raise CalibrationError(
                tr(
                    "Need at least {minimum} clear posture samples in the "
                    "calibrated camera position; received {received}.",
                    minimum=self.minimum_bad_samples,
                    received=len(usable_bad),
                )
            )

        category_calibration = self._fit_category(
            category,
            usable_good,
            usable_bad,
            profile.good_center,
            profile.good_scale,
        )
        if category_calibration is None or not category_calibration.enabled:
            raise CalibrationError(
                tr(
                    "The camera could not reliably distinguish this posture "
                    "from the saved baseline. Reposition the camera or retry "
                    "a clearer, comfortable example."
                )
            )

        updated_profile = profile.model_copy(deep=True)
        updated_profile.categories[category] = category_calibration
        return updated_profile

    def _fit_category(
        self,
        category: PostureCategory,
        good_frames: Sequence[FeatureFrame],
        bad_frames: Sequence[FeatureFrame],
        center: Mapping[str, float],
        scale: Mapping[str, float],
    ) -> CategoryCalibration | None:
        good_feature_names = set(
            _available_feature_names(
                good_frames,
                CATEGORY_FEATURES[category],
                0.80,
            )
        )
        candidate_names = [
            name
            for name in _available_feature_names(
                bad_frames, CATEGORY_FEATURES[category], 0.80
            )
            if name in center and name in good_feature_names
        ]
        if len(candidate_names) < 2:
            return None

        bad_vectors = np.asarray(
            [
                [
                    self._category_standardized_value(
                        category,
                        _feature_value(frame, name, center),
                        center[name],
                        scale[name],
                    )
                    for name in candidate_names
                ]
                for frame in bad_frames
            ],
            dtype=float,
        )
        raw_direction = np.median(bad_vectors, axis=0)
        direction_norm = float(np.linalg.norm(raw_direction))
        if direction_norm < 0.75:
            return None
        direction = raw_direction / direction_norm

        def project(frame: FeatureFrame) -> float:
            vector = np.asarray(
                [
                    self._category_standardized_value(
                        category,
                        _feature_value(frame, name, center),
                        center[name],
                        scale[name],
                    )
                    for name in candidate_names
                ],
                dtype=float,
            )
            return float(np.dot(vector, direction))

        good_scores = [project(frame) for frame in good_frames]
        bad_scores = [project(frame) for frame in bad_frames]
        good_median = _median(good_scores)
        good_high = _percentile(good_scores, 97)
        bad_median = _median(bad_scores)
        bad_low = _percentile(bad_scores, 20)
        score_scale = _robust_scale(good_scores, good_median)
        separation = (bad_median - good_median) / score_scale
        enabled = bad_median > good_high + 0.75 and separation >= 2.0

        midpoint = (good_high + bad_low) / 2
        on_threshold = max(good_high + 0.50, midpoint)
        if on_threshold >= bad_median:
            on_threshold = good_high + max(
                0.50, (bad_median - good_high) * 0.50
            )
        off_threshold = max(
            good_high + 0.15,
            on_threshold - max(0.35, (on_threshold - good_median) * 0.30),
        )
        off_threshold = min(off_threshold, on_threshold - 0.10)

        return CategoryCalibration(
            category=category,
            feature_names=candidate_names,
            direction={
                name: float(direction[index])
                for index, name in enumerate(candidate_names)
            },
            on_threshold=on_threshold,
            off_threshold=off_threshold,
            bad_reference_score=bad_median,
            separation=separation,
            sample_count=len(bad_frames),
            enabled=enabled,
        )

    @staticmethod
    def _category_standardized_value(
        category: PostureCategory,
        value: float,
        center: float,
        scale: float,
    ) -> float:
        standardized = (value - center) / scale
        if category == PostureCategory.LATERAL_LEAN:
            return abs(standardized)
        return standardized


def category_score(
    frame: FeatureFrame,
    profile: CalibrationProfile,
    category: PostureCategory,
) -> tuple[float, float]:
    category_profile = profile.categories.get(category)
    if category_profile is None or not category_profile.enabled:
        return 0.0, 0.0

    weighted_score = 0.0
    available_weight_squared = 0.0
    total_weight_squared = sum(
        weight * weight for weight in category_profile.direction.values()
    )
    for name in category_profile.feature_names:
        if name not in frame.values:
            continue
        weight = category_profile.direction[name]
        standardized = (
            frame.values[name] - profile.good_center[name]
        ) / profile.good_scale[name]
        if category == PostureCategory.LATERAL_LEAN:
            standardized = abs(standardized)
        weighted_score += standardized * weight
        available_weight_squared += weight * weight

    if available_weight_squared <= 0 or total_weight_squared <= 0:
        return 0.0, 0.0
    coverage = math.sqrt(available_weight_squared / total_weight_squared)
    normalized_score = weighted_score / math.sqrt(available_weight_squared)
    quality = frame.category_quality.get(category, 0.0) * coverage
    return normalized_score, quality


def general_deviation_score(
    frame: FeatureFrame,
    center: Mapping[str, float],
    scale: Mapping[str, float],
    names: Sequence[str] | None = None,
) -> float:
    available_names = [
        name
        for name in (names or GENERAL_FEATURES)
        if name in frame.values and name in center and name in scale
    ]
    if not available_names:
        return 0.0
    standardized = np.asarray(
        [
            abs((frame.values[name] - center[name]) / scale[name])
            for name in available_names
        ],
        dtype=float,
    )
    root_mean_square = float(np.sqrt(np.mean(np.square(standardized))))
    return float(0.65 * np.max(standardized) + 0.35 * root_mean_square)


def score_frame(
    frame: FeatureFrame,
    profile: CalibrationProfile,
) -> tuple[
    dict[PostureCategory, float],
    dict[PostureCategory, float],
]:
    scores: dict[PostureCategory, float] = {}
    qualities: dict[PostureCategory, float] = {}
    for category in profile.categories:
        score, quality = category_score(frame, profile, category)
        scores[category] = score
        qualities[category] = quality

    general_names = [
        name for name in GENERAL_FEATURES if name in profile.good_center
    ]
    scores[PostureCategory.GENERAL_DEVIATION] = general_deviation_score(
        frame,
        profile.good_center,
        profile.good_scale,
        general_names,
    )
    qualities[PostureCategory.GENERAL_DEVIATION] = frame.category_quality.get(
        PostureCategory.GENERAL_DEVIATION,
        frame.overall_quality,
    )
    return scores, qualities


def geometry_compatible(
    current: GeometryFingerprint,
    calibrated: GeometryFingerprint,
) -> tuple[bool, str | None]:
    if (
        current.frame_width != calibrated.frame_width
        or current.frame_height != calibrated.frame_height
    ):
        return False, tr(
            "Camera resolution changed; recalibrate this setup."
        )

    current_scale = current.shoulder_width / current.frame_width
    calibrated_scale = calibrated.shoulder_width / calibrated.frame_width
    scale_change = abs(current_scale / calibrated_scale - 1.0)
    if scale_change > 0.30:
        return False, tr("Move back to the calibrated camera distance.")

    center_shift = math.hypot(
        current.subject_center_x - calibrated.subject_center_x,
        current.subject_center_y - calibrated.subject_center_y,
    )
    if center_shift > 0.22:
        return False, tr("Move back into the calibrated camera position.")

    if abs(current.yaw_proxy - calibrated.yaw_proxy) > 0.40:
        return False, tr("Face the camera as you did during calibration.")
    return True, None
