from __future__ import annotations

import logging
import sys
import time
from pathlib import Path, PurePosixPath

import cv2
import numpy as np

from vulture.i18n import tr
from vulture.models import CameraDescriptor, utc_now
from vulture.vision import FeatureExtractor, MediaPipeDetector

from PySide6.QtCore import (
    QCameraPermission,
    QCoreApplication,
    QObject,
    QThread,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage, QTransform
from PySide6.QtMultimedia import (
    QCamera,
    QMediaCaptureSession,
    QMediaDevices,
    QVideoFrame,
    QVideoSink,
)

DEFAULT_ANALYSIS_FPS = 5.0
DEFAULT_PREVIEW_FPS = 2.0
DEFAULT_PREVIEW_MAX_WIDTH = 320
_LOGGER = logging.getLogger(__name__)


def _configure_opencv_runtime() -> None:
    cv2.setNumThreads(1)


def _advance_deadline(
    deadline: float,
    now: float,
    interval: float,
) -> float:
    if deadline <= 0.0:
        return now + interval
    periods = max(1, int((now - deadline) // interval) + 1)
    return deadline + periods * interval


def _deadline_is_due(
    deadline: float,
    now: float,
    interval: float,
) -> bool:
    return deadline <= 0.0 or now + interval * 0.1 >= deadline


def _fourcc_name(value: float) -> str:
    encoded = int(value)
    return "".join(
        chr((encoded >> shift) & 0xFF)
        for shift in (0, 8, 16, 24)
    ).strip("\x00")


def _blur_background(
    rgb_frame: np.ndarray,
    person_mask: np.ndarray | None,
) -> np.ndarray:
    if (
        person_mask is None
        or person_mask.ndim != 2
        or person_mask.shape != rgb_frame.shape[:2]
    ):
        return np.ascontiguousarray(rgb_frame)
    height, width = rgb_frame.shape[:2]
    reduced_width = max(80, width // 4)
    reduced_height = max(60, height // 4)
    reduced = cv2.resize(
        rgb_frame,
        (reduced_width, reduced_height),
        interpolation=cv2.INTER_AREA,
    )
    reduced = cv2.GaussianBlur(
        reduced,
        (0, 0),
        sigmaX=max(2.0, min(reduced_width, reduced_height) / 30.0),
    )
    blurred = cv2.resize(
        reduced,
        (width, height),
        interpolation=cv2.INTER_LINEAR,
    )
    mask = np.nan_to_num(
        person_mask.astype(np.float32, copy=False),
        nan=0.0,
        posinf=1.0,
        neginf=0.0,
    ).clip(0.0, 1.0)
    edge_size = max(3, round(min(width, height) * 0.012))
    if edge_size % 2 == 0:
        edge_size += 1
    mask = cv2.dilate(
        mask,
        np.ones((edge_size, edge_size), dtype=np.uint8),
        iterations=1,
    )
    mask = cv2.GaussianBlur(
        mask,
        (0, 0),
        sigmaX=max(1.0, min(width, height) / 180.0),
    )
    transition = cv2.addWeighted(
        rgb_frame,
        0.70,
        blurred,
        0.30,
        0.0,
    )
    preview = blurred.copy()
    edge_mask = np.where(mask >= 0.12, 255, 0).astype(np.uint8)
    core_mask = np.where(mask >= 0.55, 255, 0).astype(np.uint8)
    cv2.copyTo(transition, edge_mask, preview)
    cv2.copyTo(rgb_frame, core_mask, preview)
    return np.ascontiguousarray(preview)


def _rgb_frame_to_image(rgb_frame: np.ndarray) -> QImage:
    height, width, _channels = rgb_frame.shape
    return QImage(
        rgb_frame.data,
        width,
        height,
        rgb_frame.strides[0],
        QImage.Format.Format_RGB888,
    ).copy()


def _indexed_camera_descriptors() -> list[CameraDescriptor]:
    return [
        CameraDescriptor(
            stable_id=f"camera-index-{index}",
            display_name=tr("Camera {number}", number=index + 1),
            locator=index,
        )
        for index in range(5)
    ]


def _qt_camera_descriptors(
    video_inputs=None,
) -> list[CameraDescriptor]:
    devices = (
        QMediaDevices.videoInputs()
        if video_inputs is None
        else video_inputs
    )
    descriptors: list[CameraDescriptor] = []
    for index, device in enumerate(devices):
        description = device.description().strip() or tr(
            "Camera {number}",
            number=index + 1,
        )
        descriptors.append(
            CameraDescriptor(
                stable_id=_qt_camera_stable_id(device, index),
                display_name=description,
                locator=index,
            )
        )
    return descriptors


def _qt_camera_stable_id(device, index: int) -> str:
    identifier = bytes(device.id()).hex() or f"index-{index}"
    return f"qt-camera-{identifier}"


def _linux_camera_descriptors(
    video_inputs=None,
    stable_paths: list[Path] | None = None,
) -> list[CameraDescriptor]:
    devices = (
        QMediaDevices.videoInputs()
        if video_inputs is None
        else video_inputs
    )
    if stable_paths is None:
        stable_paths = []
        for stable_directory in (
            Path("/dev/v4l/by-id"),
            Path("/dev/v4l/by-path"),
        ):
            if stable_directory.exists():
                stable_paths.extend(
                    sorted(
                        item
                        for item in stable_directory.iterdir()
                        if item.exists()
                    )
                )

    descriptors: list[CameraDescriptor] = []
    for index, device in enumerate(devices):
        try:
            raw_id = bytes(device.id()).decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not raw_id.startswith("/dev/"):
            continue
        native_path = PurePosixPath(raw_id)
        if stable_paths:
            resolved_native_path = Path(raw_id).resolve()
            stable_path = next(
                (
                    path
                    for path in stable_paths
                    if path.resolve() == resolved_native_path
                ),
                native_path,
            )
        else:
            stable_path = native_path
        description = device.description().strip() or tr(
            "Camera {number}",
            number=index + 1,
        )
        descriptors.append(
            CameraDescriptor(
                stable_id=str(stable_path),
                display_name=f"{description} ({stable_path})",
                locator=str(stable_path),
            )
        )
    return descriptors


def discover_cameras() -> list[CameraDescriptor]:
    if sys.platform.startswith("linux"):
        return _linux_camera_descriptors()

    if sys.platform in ("darwin", "win32"):
        return _qt_camera_descriptors()
    return _indexed_camera_descriptors()


def resolve_camera_descriptor(
    configured: CameraDescriptor,
) -> CameraDescriptor | None:
    for available in discover_cameras():
        if available.stable_id == configured.stable_id:
            return available.model_copy(
                update={
                    "width": configured.width,
                    "height": configured.height,
                    "mirror_preview": configured.mirror_preview,
                }
            )
    if (
        isinstance(configured.locator, str)
        and configured.locator.startswith("/dev/")
        and Path(configured.locator).exists()
    ):
        return configured.model_copy(deep=True)
    if (
        not _uses_native_camera_identity()
        and isinstance(configured.locator, int)
        and configured.stable_id.startswith("camera-index-")
    ):
        return configured.model_copy(deep=True)
    return None


def _qt_camera_device(
    descriptor: CameraDescriptor,
    video_inputs=None,
):
    devices = (
        QMediaDevices.videoInputs()
        if video_inputs is None
        else video_inputs
    )
    for index, device in enumerate(devices):
        if _qt_camera_stable_id(device, index) == descriptor.stable_id:
            return device
    if (
        isinstance(descriptor.locator, str)
        and descriptor.locator.startswith("/dev/")
    ):
        configured_path = Path(descriptor.locator).resolve()
        for device in devices:
            try:
                device_path = Path(bytes(device.id()).decode("utf-8")).resolve()
            except UnicodeDecodeError:
                continue
            if device_path == configured_path:
                return device
    if (
        not _uses_native_camera_identity()
        and descriptor.stable_id.startswith("camera-index-")
        and isinstance(descriptor.locator, int)
        and 0 <= descriptor.locator < len(devices)
    ):
        return devices[descriptor.locator]
    return None


def _uses_native_camera_identity() -> bool:
    return sys.platform.startswith("linux") or sys.platform in (
        "darwin",
        "win32",
    )


class _CameraAnalysisWorker:
    def __init__(self, owner: "CameraThread") -> None:
        self.owner = owner
        self.detector: MediaPipeDetector | None = None
        self.extractor = FeatureExtractor()
        self._opened = False
        self._next_preview_at = 0.0

    def _start_detector(self) -> bool:
        self.detector = MediaPipeDetector()
        return not self.owner.isInterruptionRequested()

    def _process_rgb_frame(self, rgb_frame: np.ndarray) -> None:
        if (
            rgb_frame.ndim != 3
            or rgb_frame.shape[2] != 3
            or rgb_frame.dtype != np.uint8
        ):
            raise ValueError(tr("The camera returned an invalid frame."))
        height, width, _channels = rgb_frame.shape
        if not self._opened:
            self._opened = True
            self.owner.camera_opened.emit(width, height)

        if self.detector is None:
            raise RuntimeError(
                tr("The landmark detector is not available.")
            )
        observation = self.detector.process(rgb_frame)
        self.owner._mark_inference_complete()
        self._emit_preview_if_due(rgb_frame)
        if observation is None:
            self.owner.tracking_lost.emit(utc_now())
            return
        features = self.extractor.extract(
            observation,
            width,
            height,
        )
        if features is None:
            self.owner.tracking_lost.emit(utc_now())
        else:
            self.owner.feature_ready.emit(features)

    def _emit_preview_if_due(self, rgb_frame: np.ndarray) -> None:
        if not self.owner.preview_enabled:
            return
        now = time.monotonic()
        if now < self._next_preview_at:
            return
        self._next_preview_at = _advance_deadline(
            self._next_preview_at,
            now,
            1.0 / max(self.owner.preview_fps, 1.0),
        )
        if self.detector is None:
            return
        preview_source = rgb_frame
        person_mask = getattr(self.detector, "person_mask", None)
        height, width = rgb_frame.shape[:2]
        if width > DEFAULT_PREVIEW_MAX_WIDTH:
            preview_width = DEFAULT_PREVIEW_MAX_WIDTH
            preview_height = max(1, round(height * preview_width / width))
            preview_source = cv2.resize(
                rgb_frame,
                (preview_width, preview_height),
                interpolation=cv2.INTER_AREA,
            )
            if person_mask is not None:
                person_mask = cv2.resize(
                    person_mask,
                    (preview_width, preview_height),
                    interpolation=cv2.INTER_LINEAR,
                )
        preview_frame = _blur_background(
            preview_source,
            person_mask,
        )
        preview = _rgb_frame_to_image(preview_frame)
        if self.owner.descriptor.mirror_preview:
            preview = preview.mirrored(True, False)
        self.owner.preview_ready.emit(preview)

    def _close_detector(self) -> None:
        if self.detector is not None:
            self.detector.close()
            self.detector = None


class _OpenCVCameraWorker(_CameraAnalysisWorker):
    def __init__(self, owner: "CameraThread") -> None:
        super().__init__(owner)
        self.capture: cv2.VideoCapture | None = None
        self._next_frame_at = 0.0

    def start(self) -> bool:
        if self.owner.isInterruptionRequested():
            return False
        try:
            _configure_opencv_runtime()
            if not self._start_detector():
                return False
            self.capture = cv2.VideoCapture(
                self.owner.descriptor.locator,
                cv2.CAP_V4L2,
            )
            if not self.capture.isOpened():
                self.owner._report_error(
                    tr(
                        "Could not use {camera}: {detail} {help}",
                        camera=self.owner.descriptor.display_name,
                        detail=tr("The camera could not be opened."),
                        help=self.owner._camera_access_help(),
                    )
                )
                return False
            self.capture.set(
                cv2.CAP_PROP_FRAME_WIDTH,
                self.owner.descriptor.width,
            )
            self.capture.set(
                cv2.CAP_PROP_FRAME_HEIGHT,
                self.owner.descriptor.height,
            )
            self.capture.set(
                cv2.CAP_PROP_FPS,
                max(self.owner.target_fps * 2.0, 10.0),
            )
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            selected_fourcc = _fourcc_name(
                self.capture.get(cv2.CAP_PROP_FOURCC)
            )
            _LOGGER.info(
                "Opened %s at %.0fx%.0f %.1f FPS using %s",
                self.owner.descriptor.locator,
                self.capture.get(cv2.CAP_PROP_FRAME_WIDTH),
                self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT),
                self.capture.get(cv2.CAP_PROP_FPS),
                selected_fourcc or "driver default",
            )
            return True
        except (cv2.error, OSError, RuntimeError, TypeError, ValueError) as error:
            self.owner._report_error(
                tr(
                    "Could not start {camera}: {error}. {help}",
                    camera=self.owner.descriptor.display_name,
                    error=error,
                    help=self.owner._camera_access_help(),
                )
            )
            return False

    def run(self) -> None:
        try:
            if not self.start():
                return
            while not self.owner.isInterruptionRequested():
                if self.capture is None:
                    raise RuntimeError(
                        tr("The camera could not be opened.")
                    )
                try:
                    ok, bgr_frame = self.capture.read()
                except (
                    cv2.error,
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ) as error:
                    self.owner._report_error(
                        tr(
                            "Could not use {camera}: {detail} {help}",
                            camera=self.owner.descriptor.display_name,
                            detail=str(error),
                            help=self.owner._camera_access_help(),
                        )
                    )
                    return
                if not ok or bgr_frame is None:
                    self.owner._report_error(
                        tr(
                            "{camera} is no longer available. {help}",
                            camera=self.owner.descriptor.display_name,
                            help=self.owner._camera_access_help(),
                        )
                    )
                    return
                self.owner._mark_frame_received()
                now = time.monotonic()
                frame_interval = 1.0 / max(self.owner.target_fps, 1.0)
                if not _deadline_is_due(
                    self._next_frame_at,
                    now,
                    frame_interval,
                ):
                    continue
                self._next_frame_at = _advance_deadline(
                    self._next_frame_at,
                    now,
                    frame_interval,
                )
                try:
                    self._process_bgr_frame(bgr_frame)
                except (
                    cv2.error,
                    BufferError,
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ) as error:
                    self.owner._report_error(
                        tr("Camera analysis failed: {error}", error=error)
                    )
                    return
        finally:
            self.close()

    def _process_bgr_frame(self, bgr_frame: np.ndarray) -> None:
        rgb_frame = cv2.cvtColor(
            bgr_frame,
            cv2.COLOR_BGR2RGB,
        )
        self._process_rgb_frame(rgb_frame)

    def close(self) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        self._close_detector()


class _NativeCameraWorker(QObject):
    def __init__(self, owner: "CameraThread") -> None:
        super().__init__()
        self.owner = owner
        self._analysis = _CameraAnalysisWorker(owner)
        self.camera: QCamera | None = None
        self.session: QMediaCaptureSession | None = None
        self.sink: QVideoSink | None = None
        self._next_frame_at = 0.0

    @property
    def detector(self):
        return self._analysis.detector

    @detector.setter
    def detector(self, detector) -> None:
        self._analysis.detector = detector

    def start(self) -> bool:
        if self.owner.isInterruptionRequested():
            return False
        if self.owner.camera_permission_denied:
            self.owner._report_error(
                tr(
                    "Camera access is denied. {help}",
                    help=self.owner._camera_access_help(),
                )
            )
            return False
        device = _qt_camera_device(self.owner.descriptor)
        if device is None:
            self.owner._report_error(
                tr(
                    "{camera} is no longer available. {help}",
                    camera=self.owner.descriptor.display_name,
                    help=self.owner._camera_access_help(),
                )
            )
            return False
        try:
            _configure_opencv_runtime()
            if not self._analysis._start_detector():
                return False
            self.camera = QCamera(device)
            camera_format = self._closest_camera_format(device)
            if camera_format is not None:
                self.camera.setCameraFormat(camera_format)
            self.session = QMediaCaptureSession()
            self.sink = QVideoSink()
            self.session.setCamera(self.camera)
            self.session.setVideoSink(self.sink)
            self.sink.videoFrameChanged.connect(self._on_frame)
            self.camera.errorOccurred.connect(self._on_error)
            self.camera.start()
            return self.owner.failure_message is None
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            self.owner._report_error(
                tr(
                    "Could not start {camera}: {error}. {help}",
                    camera=self.owner.descriptor.display_name,
                    error=error,
                    help=self.owner._camera_access_help(),
                )
            )
            return False

    def _closest_camera_format(self, device):
        formats = list(device.videoFormats())
        if not formats:
            return None

        target_width = self.owner.descriptor.width
        target_height = self.owner.descriptor.height

        def distance(camera_format) -> tuple[int, float]:
            resolution = camera_format.resolution()
            size_distance = abs(resolution.width() - target_width) + abs(
                resolution.height() - target_height
            )
            frame_rate_distance = abs(
                min(camera_format.maxFrameRate(), 30.0)
                - self.owner.target_fps
            )
            return size_distance, frame_rate_distance

        return min(formats, key=distance)

    @Slot(QVideoFrame)
    def _on_frame(self, frame: QVideoFrame) -> None:
        if self.owner.isInterruptionRequested():
            self.owner.quit()
            return
        if not frame.isValid():
            self.owner.tracking_lost.emit(utc_now())
            return
        self.owner._mark_frame_received()
        now = time.monotonic()
        frame_interval = 1.0 / max(self.owner.target_fps, 1.0)
        if not _deadline_is_due(
            self._next_frame_at,
            now,
            frame_interval,
        ):
            return
        self._next_frame_at = _advance_deadline(
            self._next_frame_at,
            now,
            frame_interval,
        )

        try:
            image = frame.toImage()
            if image.isNull():
                self.owner.tracking_lost.emit(utc_now())
                return
            rotation = frame.rotation().value
            if rotation:
                image = image.transformed(
                    QTransform().rotate(rotation),
                    Qt.TransformationMode.FastTransformation,
                )
            rgb_image = image.convertToFormat(QImage.Format.Format_RGB888)
            width = rgb_image.width()
            height = rgb_image.height()
            bytes_per_line = rgb_image.bytesPerLine()
            flat = np.frombuffer(
                rgb_image.constBits(),
                dtype=np.uint8,
                count=rgb_image.sizeInBytes(),
            )
            rgb_frame = (
                flat.reshape(height, bytes_per_line)[:, : width * 3]
                .reshape(height, width, 3)
                .copy()
            )
            self._analysis._process_rgb_frame(rgb_frame)
        except (
            cv2.error,
            BufferError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            self.owner._report_error(
                tr("Camera analysis failed: {error}", error=error)
            )
            self.owner.quit()

    @Slot(QCamera.Error, str)
    def _on_error(self, _error: QCamera.Error, message: str) -> None:
        detail = message.strip() or tr(
            "The native camera service reported an error."
        )
        self.owner._report_error(
            tr(
                "Could not use {camera}: {detail} {help}",
                camera=self.owner.descriptor.display_name,
                detail=detail,
                help=self.owner._camera_access_help(),
            )
        )
        self.owner.quit()

    def close(self) -> None:
        if self.camera is not None:
            self.camera.stop()
        self._analysis._close_detector()
        self.sink = None
        self.session = None
        self.camera = None


class CameraThread(QThread):
    preview_ready = Signal(QImage)
    feature_ready = Signal(object)
    tracking_lost = Signal(object)
    camera_opened = Signal(int, int)
    camera_error = Signal(str)

    def __init__(
        self,
        descriptor: CameraDescriptor,
        target_fps: float = DEFAULT_ANALYSIS_FPS,
        preview_fps: float = DEFAULT_PREVIEW_FPS,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.descriptor = descriptor
        self.target_fps = target_fps
        self.preview_fps = preview_fps
        self.preview_enabled = True
        self.failure_message: str | None = None
        self.last_frame_at: float | None = None
        self.last_inference_at: float | None = None
        self._startup_timer: QTimer | None = None
        self._startup_pending = False
        application = QCoreApplication.instance()
        self.camera_permission_denied = (
            sys.platform == "darwin"
            and application is not None
            and application.checkPermission(QCameraPermission())
            == Qt.PermissionStatus.Denied
        )
        self.camera_opened.connect(self._on_camera_opened)
        self.finished.connect(self._stop_startup_timer)

    def set_preview_enabled(self, enabled: bool) -> None:
        self.preview_enabled = enabled

    def _mark_frame_received(self) -> None:
        self.last_frame_at = time.monotonic()

    def _mark_inference_complete(self) -> None:
        self.last_inference_at = time.monotonic()

    def seconds_since_last_output(
        self,
        now: float | None = None,
    ) -> float | None:
        last_output_at = self.last_inference_at or self.last_frame_at
        if last_output_at is None:
            return None
        current_time = time.monotonic() if now is None else now
        return max(0.0, current_time - last_output_at)

    def _report_error(self, message: str) -> None:
        if self.failure_message is not None:
            return
        self.failure_message = message
        self.camera_error.emit(message)

    @staticmethod
    def _camera_access_help() -> str:
        if sys.platform == "darwin":
            return tr(
                "Allow camera access for Vulture, or for the terminal used to "
                "launch it, in System Settings > Privacy & Security > Camera."
            )
        if sys.platform == "win32":
            return tr(
                "In Settings > Privacy & security > Camera, enable Camera "
                "access and Let desktop apps access your camera."
            )
        return tr(
            "Check that the camera is connected and that your user can read "
            "the selected /dev/video device."
        )

    def start(
        self,
        priority: QThread.Priority = QThread.Priority.InheritPriority,
    ) -> None:
        self.failure_message = None
        self.last_frame_at = None
        self.last_inference_at = None
        self._startup_pending = True
        if self._startup_timer is None:
            self._startup_timer = QTimer(self)
            self._startup_timer.setSingleShot(True)
            self._startup_timer.setInterval(10_000)
            self._startup_timer.timeout.connect(self._on_startup_timeout)
        self._startup_timer.start()
        super().start(priority)

    @Slot(int, int)
    def _on_camera_opened(self, _width: int, _height: int) -> None:
        self._stop_startup_timer()

    @Slot()
    def _on_startup_timeout(self) -> None:
        if not self._startup_pending:
            return
        self._startup_pending = False
        self.requestInterruption()
        self.quit()
        self._report_error(
            tr(
                "{camera} did not deliver a camera frame within 10 seconds. "
                "{help}",
                camera=self.descriptor.display_name,
                help=self._camera_access_help(),
            )
        )

    @Slot()
    def _stop_startup_timer(self) -> None:
        self._startup_pending = False
        if self._startup_timer is not None:
            self._startup_timer.stop()

    def run(self) -> None:
        if sys.platform.startswith("linux"):
            _OpenCVCameraWorker(self).run()
            return
        worker = _NativeCameraWorker(self)
        try:
            if not worker.start():
                return
            if self.isInterruptionRequested():
                return
            self.exec()
        finally:
            worker.close()

    def stop(self, timeout_milliseconds: int = 3000) -> bool:
        self._stop_startup_timer()
        self.requestInterruption()
        self.quit()
        if not self.wait(timeout_milliseconds):
            self._report_error(
                tr("Camera shutdown is taking longer than expected.")
            )
            return False
        return True
