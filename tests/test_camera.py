from __future__ import annotations

import time

import numpy as np

import vulture.camera as camera_module
from vulture.camera import (
    CameraThread,
    _NativeCameraWorker,
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
    camera_thread = CameraThread(descriptor, target_fps=10)
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


def test_missing_person_mask_blurs_entire_preview() -> None:
    rows, columns = np.indices((64, 64))
    checkerboard = ((rows + columns) % 2 * 255).astype(np.uint8)
    frame = np.repeat(checkerboard[..., None], 3, axis=2)

    preview = _blur_background(frame, None)

    assert not np.array_equal(preview, frame)
    assert preview.std() < frame.std()


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
