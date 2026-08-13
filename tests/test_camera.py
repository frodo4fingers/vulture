from __future__ import annotations

import time

import numpy as np
import pytest

import vulture.camera as camera_module
from vulture.camera import (
    CameraThread,
    DEFAULT_ANALYSIS_FPS,
    _NativeCameraWorker,
    _OpenCVCameraWorker,
    _advance_deadline,
    _deadline_is_due,
    _blur_background,
    _linux_camera_descriptors,
    discover_cameras,
    _qt_camera_device,
    _qt_camera_descriptors,
    resolve_camera_descriptor,
)
from vulture.models import CameraDescriptor

from PySide6.QtGui import QColor, QImage
from PySide6.QtMultimedia import QVideoFrame, QtVideo


class FakeVideoDevice:
    def __init__(self, identifier: bytes, description: str) -> None:
        self._identifier = identifier
        self._description = description

    def id(self) -> bytes:
        return self._identifier

    def description(self) -> str:
        return self._description


class EmptyDetector:
    def __init__(self, expected_shape: tuple[int, int, int]) -> None:
        self.expected_shape = expected_shape

    def process(self, frame):
        assert frame.shape == self.expected_shape
        return None


class SlowDetector(EmptyDetector):
    def __init__(self, expected_shape: tuple[int, int, int]) -> None:
        super().__init__(expected_shape)
        self.calls = 0

    def process(self, frame):
        self.calls += 1
        time.sleep(0.15)
        return super().process(frame)


class RecordingDetector:
    def __init__(self) -> None:
        self.frame = None
        self.closed = False

    def process(self, frame):
        self.frame = frame.copy()
        return None

    def close(self) -> None:
        self.closed = True


def test_qt_camera_discovery_uses_native_names_and_ids() -> None:
    descriptors = _qt_camera_descriptors(
        [
            FakeVideoDevice(b"built-in", "FaceTime HD Camera"),
            FakeVideoDevice(b"usb-camera", "USB Webcam"),
        ]
    )

    assert [item.display_name for item in descriptors] == [
        "FaceTime HD Camera",
        "USB Webcam",
    ]
    assert descriptors[0].stable_id == "qt-camera-6275696c742d696e"
    assert descriptors[1].locator == 1


def test_native_discovery_does_not_invent_missing_cameras(
    monkeypatch,
) -> None:
    monkeypatch.setattr(camera_module.sys, "platform", "win32")
    monkeypatch.setattr(
        camera_module,
        "_qt_camera_descriptors",
        lambda: [],
    )

    assert discover_cameras() == []


def test_linux_discovery_keeps_native_device_paths() -> None:
    descriptors = _linux_camera_descriptors(
        [
            FakeVideoDevice(b"/dev/video0", "Built-in camera"),
            FakeVideoDevice(b"not-a-device-path", "Ignored camera"),
        ],
        stable_paths=[],
    )

    assert len(descriptors) == 1
    assert descriptors[0].stable_id == "/dev/video0"
    assert descriptors[0].locator == "/dev/video0"
    assert descriptors[0].display_name == "Built-in camera (/dev/video0)"


def test_native_capture_selects_the_saved_qt_device_id() -> None:
    first = FakeVideoDevice(b"built-in", "Built-in camera")
    second = FakeVideoDevice(b"usb-camera", "USB Webcam")
    configured = CameraDescriptor(
        stable_id="qt-camera-7573622d63616d657261",
        display_name="USB Webcam",
        locator=0,
    )

    selected = _qt_camera_device(
        configured,
        [first, second],
    )

    assert selected is second


def test_linux_capture_matches_the_saved_device_path() -> None:
    device = FakeVideoDevice(b"/dev/video4", "USB Webcam")
    configured = CameraDescriptor(
        stable_id="/dev/video4",
        display_name="USB Webcam",
        locator="/dev/video4",
    )

    selected = _qt_camera_device(configured, [device])

    assert selected is device


def test_legacy_index_is_not_reused_on_native_platform(
    monkeypatch,
) -> None:
    monkeypatch.setattr(camera_module.sys, "platform", "win32")
    first = FakeVideoDevice(b"built-in", "Built-in camera")
    second = FakeVideoDevice(b"usb-camera", "USB Webcam")
    configured = CameraDescriptor(
        stable_id="camera-index-1",
        display_name="Camera 2",
        locator=1,
    )

    selected = _qt_camera_device(
        configured,
        [first, second],
    )

    assert selected is None


def test_legacy_index_remains_available_on_fallback_platform(
    monkeypatch,
) -> None:
    monkeypatch.setattr(camera_module.sys, "platform", "freebsd")
    first = FakeVideoDevice(b"built-in", "Built-in camera")
    second = FakeVideoDevice(b"usb-camera", "USB Webcam")
    configured = CameraDescriptor(
        stable_id="camera-index-1",
        display_name="Camera 2",
        locator=1,
    )

    selected = _qt_camera_device(
        configured,
        [first, second],
    )

    assert selected is second


def test_missing_native_camera_id_does_not_reuse_stale_index(
    monkeypatch,
) -> None:
    monkeypatch.setattr(camera_module.sys, "platform", "win32")
    configured = CameraDescriptor(
        stable_id="qt-camera-missing",
        display_name="Removed camera",
        locator=1,
    )
    replacement = configured.model_copy(
        update={
            "stable_id": "qt-camera-replacement",
            "display_name": "Different camera",
        }
    )
    monkeypatch.setattr(
        camera_module,
        "discover_cameras",
        lambda: [replacement],
    )

    assert resolve_camera_descriptor(configured) is None


def test_native_camera_id_resolves_after_device_order_changes(
    monkeypatch,
) -> None:
    configured = CameraDescriptor(
        stable_id="qt-camera-757362",
        display_name="USB Webcam",
        locator=0,
        width=1280,
        height=720,
        mirror_preview=False,
    )
    available = configured.model_copy(
        update={
            "locator": 2,
            "width": 640,
            "height": 480,
            "mirror_preview": True,
        }
    )
    monkeypatch.setattr(
        camera_module,
        "discover_cameras",
        lambda: [available],
    )

    resolved = resolve_camera_descriptor(configured)

    assert resolved is not None
    assert resolved.locator == 2
    assert resolved.width == 1280
    assert resolved.height == 720
    assert not resolved.mirror_preview


def test_windows_camera_errors_include_permission_help(
    monkeypatch,
) -> None:
    monkeypatch.setattr(camera_module.sys, "platform", "win32")

    assert (
        "Let desktop apps access your camera"
        in CameraThread._camera_access_help()
    )


def test_linux_camera_thread_uses_opencv_capture(monkeypatch) -> None:
    descriptor = CameraDescriptor(
        stable_id="/dev/video-test",
        display_name="Test camera",
        locator="/dev/video-test",
    )
    camera_thread = CameraThread(descriptor)
    workers = []

    class FakeOpenCVWorker:
        def __init__(self, owner) -> None:
            self.owner = owner

        def run(self) -> None:
            workers.append(self)

    monkeypatch.setattr(camera_module.sys, "platform", "linux")
    monkeypatch.setattr(
        camera_module,
        "_OpenCVCameraWorker",
        FakeOpenCVWorker,
    )

    camera_thread.run()

    assert len(workers) == 1
    assert workers[0].owner is camera_thread


def test_camera_defaults_to_five_analysis_frames_per_second() -> None:
    descriptor = CameraDescriptor(
        stable_id="/dev/video-test",
        display_name="Test camera",
        locator="/dev/video-test",
    )

    camera_thread = CameraThread(descriptor)

    assert camera_thread.target_fps == DEFAULT_ANALYSIS_FPS == 5.0


def test_fixed_deadline_skips_missed_periods_without_drifting() -> None:
    assert _advance_deadline(10.0, 10.45, 0.2) == pytest.approx(10.6)
    assert _advance_deadline(0.0, 10.45, 0.2) == pytest.approx(10.65)


def test_deadline_tolerates_camera_delivery_jitter() -> None:
    assert _deadline_is_due(10.2, 10.185, 0.2)
    assert not _deadline_is_due(10.2, 10.15, 0.2)


def test_opencv_frame_is_converted_for_local_inference() -> None:
    descriptor = CameraDescriptor(
        stable_id="/dev/video-test",
        display_name="Test camera",
        locator="/dev/video-test",
        mirror_preview=False,
    )
    camera_thread = CameraThread(descriptor)
    worker = _OpenCVCameraWorker(camera_thread)
    detector = RecordingDetector()
    worker.detector = detector
    previews = []
    opened = []
    tracking_lost = []
    camera_thread.preview_ready.connect(previews.append)
    camera_thread.camera_opened.connect(
        lambda width, height: opened.append((width, height))
    )
    camera_thread.tracking_lost.connect(tracking_lost.append)
    bgr_frame = np.zeros((2, 4, 3), dtype=np.uint8)
    bgr_frame[0, 0] = [10, 20, 30]

    worker._process_bgr_frame(bgr_frame)

    assert detector.frame is not None
    assert detector.frame[0, 0].tolist() == [30, 20, 10]
    assert len(previews) == 1
    assert (previews[0].width(), previews[0].height()) == (4, 2)
    assert opened == [(4, 2)]
    assert len(tracking_lost) == 1


def test_hidden_preview_skips_image_processing() -> None:
    descriptor = CameraDescriptor(
        stable_id="/dev/video-test",
        display_name="Test camera",
        locator="/dev/video-test",
        mirror_preview=False,
    )
    camera_thread = CameraThread(descriptor)
    camera_thread.set_preview_enabled(False)
    worker = _OpenCVCameraWorker(camera_thread)
    detector = RecordingDetector()
    worker.detector = detector
    previews = []
    tracking_lost = []
    camera_thread.preview_ready.connect(previews.append)
    camera_thread.tracking_lost.connect(tracking_lost.append)

    worker._process_bgr_frame(np.zeros((2, 4, 3), dtype=np.uint8))

    assert detector.frame is not None
    assert previews == []
    assert len(tracking_lost) == 1


def test_preview_is_reduced_before_ui_delivery() -> None:
    descriptor = CameraDescriptor(
        stable_id="/dev/video-test",
        display_name="Test camera",
        locator="/dev/video-test",
        mirror_preview=False,
    )
    camera_thread = CameraThread(descriptor)
    worker = _OpenCVCameraWorker(camera_thread)
    worker.detector = RecordingDetector()
    previews = []
    camera_thread.preview_ready.connect(previews.append)

    worker._process_bgr_frame(np.zeros((480, 640, 3), dtype=np.uint8))

    assert len(previews) == 1
    assert (previews[0].width(), previews[0].height()) == (320, 240)


def test_opencv_read_failure_is_reported_and_releases_capture(
    monkeypatch,
) -> None:
    descriptor = CameraDescriptor(
        stable_id="/dev/video-test",
        display_name="Test camera",
        locator="/dev/video-test",
    )
    camera_thread = CameraThread(descriptor)
    errors = []
    camera_thread.camera_error.connect(errors.append)
    detector = RecordingDetector()
    capture_arguments = []

    class FakeCapture:
        def __init__(self) -> None:
            self.released = False
            self.settings = []

        def isOpened(self) -> bool:
            return True

        def set(self, property_id, value) -> bool:
            self.settings.append((property_id, value))
            return True

        def get(self, property_id) -> float:
            return next(
                (
                    value
                    for configured_property, value in reversed(self.settings)
                    if configured_property == property_id
                ),
                0.0,
            )

        def read(self):
            return False, None

        def release(self) -> None:
            self.released = True

    capture = FakeCapture()

    def create_capture(source, backend):
        capture_arguments.append((source, backend))
        return capture

    monkeypatch.setattr(
        camera_module,
        "MediaPipeDetector",
        lambda: detector,
    )
    monkeypatch.setattr(
        camera_module.cv2,
        "VideoCapture",
        create_capture,
    )

    _OpenCVCameraWorker(camera_thread).run()

    assert capture_arguments == [
        ("/dev/video-test", camera_module.cv2.CAP_V4L2)
    ]
    assert errors
    assert "no longer available" in errors[0]
    assert all(
        property_id != camera_module.cv2.CAP_PROP_FOURCC
        for property_id, _value in capture.settings
    )
    assert capture.released
    assert detector.closed


def test_camera_output_age_uses_latest_pipeline_activity() -> None:
    descriptor = CameraDescriptor(
        stable_id="/dev/video-test",
        display_name="Test camera",
        locator="/dev/video-test",
    )
    camera_thread = CameraThread(descriptor)
    camera_thread.last_frame_at = 10.0
    camera_thread.last_inference_at = 12.0

    assert camera_thread.seconds_since_last_output(now=14.5) == 2.5


def test_native_video_frame_is_converted_for_local_inference() -> None:
    descriptor = CameraDescriptor(
        stable_id="qt-camera-test",
        display_name="Test camera",
        locator=0,
    )
    camera_thread = CameraThread(descriptor)
    worker = _NativeCameraWorker(camera_thread)
    worker.detector = EmptyDetector((4, 2, 3))
    previews = []
    opened = []
    tracking_lost = []
    camera_thread.preview_ready.connect(previews.append)
    camera_thread.camera_opened.connect(
        lambda width, height: opened.append((width, height))
    )
    camera_thread.tracking_lost.connect(tracking_lost.append)
    image = QImage(4, 2, QImage.Format.Format_RGB888)
    image.fill(QColor("#336699"))
    video_frame = QVideoFrame(image)
    video_frame.setRotation(QtVideo.Rotation.Clockwise90)

    worker._on_frame(video_frame)

    assert len(previews) == 1
    assert (previews[0].width(), previews[0].height()) == (2, 4)
    assert opened == [(2, 4)]
    assert len(tracking_lost) == 1
    assert tracking_lost[0].tzinfo is not None


def test_native_capture_drops_queued_frames_after_slow_inference() -> None:
    descriptor = CameraDescriptor(
        stable_id="qt-camera-test",
        display_name="Test camera",
        locator=0,
    )
    camera_thread = CameraThread(descriptor, target_fps=5)
    worker = _NativeCameraWorker(camera_thread)
    detector = SlowDetector((2, 4, 3))
    worker.detector = detector
    image = QImage(4, 2, QImage.Format.Format_RGB888)
    image.fill(QColor("#336699"))
    video_frame = QVideoFrame(image)

    worker._on_frame(video_frame)
    worker._on_frame(video_frame)

    assert detector.calls == 1


def test_background_blur_preserves_person_mask() -> None:
    rows, columns = np.indices((64, 64))
    checkerboard = ((rows + columns) % 2 * 255).astype(np.uint8)
    frame = np.repeat(checkerboard[..., None], 3, axis=2)
    person_mask = np.zeros((64, 64), dtype=np.float32)
    person_mask[20:45, 20:45] = 1.0

    preview = _blur_background(frame, person_mask)

    assert preview.dtype == np.uint8
    assert preview.shape == frame.shape
    assert np.array_equal(preview[32, 32], frame[32, 32])
    assert not np.array_equal(preview[8, 8], frame[8, 8])


def test_missing_person_mask_keeps_preview_visible() -> None:
    rows, columns = np.indices((64, 64))
    checkerboard = ((rows + columns) % 2 * 255).astype(np.uint8)
    frame = np.repeat(checkerboard[..., None], 3, axis=2)

    preview = _blur_background(frame, None)

    assert np.array_equal(preview, frame)


def test_denied_camera_permission_fails_before_capture() -> None:
    descriptor = CameraDescriptor(
        stable_id="qt-camera-test",
        display_name="Test camera",
        locator=0,
    )
    camera_thread = CameraThread(descriptor)
    camera_thread.camera_permission_denied = True
    errors = []
    camera_thread.camera_error.connect(errors.append)

    started = _NativeCameraWorker(camera_thread).start()

    assert not started
    assert errors
    assert "Camera access is denied" in errors[0]


def test_native_camera_startup_timeout_is_reported() -> None:
    descriptor = CameraDescriptor(
        stable_id="qt-camera-test",
        display_name="Test camera",
        locator=0,
    )
    camera_thread = CameraThread(descriptor)
    errors = []
    camera_thread.camera_error.connect(errors.append)
    camera_thread._startup_pending = True

    camera_thread._on_startup_timeout()

    assert errors
    assert "within 10 seconds" in errors[0]
