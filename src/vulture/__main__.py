from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from vulture import __version__
from vulture.autostart import START_MINIMIZED_FLAG
from vulture.exercises import exercise_media_path, load_exercise_catalog
from vulture.i18n import (
    configure_qt_translations,
    current_language,
    set_language,
    tr,
    translation_messages,
    validate_qt_translations,
)
from vulture.models import InterfaceLanguage
from vulture.resources import resource_path
from vulture.storage import AppDataStore, StorageError
from vulture.ui import CALIBRATION_STEPS, MainWindow
from vulture.vision import MediaPipeDetector

from PySide6.QtCore import (
    QCameraPermission,
    QCoreApplication,
    QEventLoop,
    QObject,
    QTimer,
    Qt,
    QUrl,
    Slot,
)
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon


def _write_runtime_status(message: str, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        print(message, file=stream)


class CameraPermissionLauncher(QObject):
    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__()
        self._callback = callback

    @Slot()
    def permission_decided(self) -> None:
        self._callback()


def _check_exercise_video(title: str, path: Path) -> None:
    player = QMediaPlayer()
    video_sink = QVideoSink()
    event_loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.setInterval(5_000)
    decoded_frame = False

    def frame_received(frame: QVideoFrame) -> None:
        nonlocal decoded_frame
        if frame.isValid():
            decoded_frame = True
            event_loop.quit()

    video_sink.videoFrameChanged.connect(frame_received)
    timeout.timeout.connect(event_loop.quit)
    player.errorOccurred.connect(event_loop.quit)
    player.setVideoOutput(video_sink)
    player.setSource(QUrl.fromLocalFile(str(path)))
    player.play()
    timeout.start()
    event_loop.exec()
    player.stop()
    if not decoded_frame:
        detail = player.errorString().strip() or player.mediaStatus().name
        raise RuntimeError(
            f'Bundled exercise video "{title}" could not be decoded: '
            f"{detail}"
        )


def check_runtime() -> int:
    detector: MediaPipeDetector | None = None
    _runtime_application = QCoreApplication.instance()
    if _runtime_application is None:
        _runtime_application = QCoreApplication([sys.argv[0]])
    try:
        import numpy as np

        catalogs = {
            language: load_exercise_catalog(language=language)
            for language in InterfaceLanguage
        }
        catalog = catalogs[InterfaceLanguage.ENGLISH]
        expected_exercise_ids = [
            exercise.id for exercise in catalog.exercises
        ]
        expected_source_ids = [source.id for source in catalog.sources]
        for language, localized_catalog in catalogs.items():
            translation_messages(language)
            validate_qt_translations(language)
            if [
                exercise.id for exercise in localized_catalog.exercises
            ] != expected_exercise_ids or [
                source.id for source in localized_catalog.sources
            ] != expected_source_ids:
                raise RuntimeError(
                    "Localized exercise catalog identifiers do not match "
                    f"English: {language.value}"
                )
        exercise_media = [
            (exercise.title, exercise_media_path(exercise))
            for exercise in catalog.exercises
            if exercise.media_path is not None
        ]
        missing_media = [
            title for title, path in exercise_media if path is None
        ]
        if missing_media:
            raise RuntimeError(
                "Bundled exercise media is missing: "
                + ", ".join(missing_media)
            )
        for title, path in exercise_media:
            if path is not None:
                _check_exercise_video(title, path)
        for step in CALIBRATION_STEPS:
            if step.image_filename is None:
                continue
            image_path = resource_path(
                "calibration",
                step.image_filename,
            )
            if QImage(str(image_path)).isNull():
                raise RuntimeError(
                    "Bundled calibration image could not be decoded: "
                    f"{step.title}"
                )
        detector = MediaPipeDetector()
        detector.process(np.zeros((480, 640, 3), dtype=np.uint8))
    except (OSError, RuntimeError, ValueError) as error:
        _write_runtime_status(
            f"Vulture runtime check failed: {error}",
            error=True,
        )
        return 1
    finally:
        if detector is not None:
            detector.close()
    _write_runtime_status("Vulture runtime check passed.")
    return 0


def _should_start_minimized(argv: Sequence[str]) -> bool:
    return START_MINIMIZED_FLAG in argv


def main() -> int:
    if "--check-runtime" in sys.argv[1:]:
        return check_runtime()

    start_minimized = _should_start_minimized(sys.argv[1:])

    app = QApplication(sys.argv)
    app.setApplicationName("Vulture")
    app.setApplicationVersion(__version__)
    app.setOrganizationDomain("vulture.local")
    app.setOrganizationName("Vulture")
    app.setQuitOnLastWindowClosed(False)

    store = AppDataStore()
    try:
        data = store.load()
        set_language(data.interface_language)
        configure_qt_translations(app)
        catalog = load_exercise_catalog(
            language=data.interface_language
        )
    except (StorageError, RuntimeError) as error:
        QMessageBox.critical(
            None,
            tr("Vulture could not start"),
            str(error),
        )
        return 1

    window: MainWindow | None = None
    permission_launcher: CameraPermissionLauncher | None = None

    def connect_window(candidate: MainWindow) -> None:
        candidate.language_change_requested.connect(change_language)
        app.aboutToQuit.connect(candidate._stop_camera)
        app.aboutToQuit.connect(candidate._close_history)

    def change_language(language_value: str) -> None:
        nonlocal window, data, catalog
        if window is None:
            return
        previous_language = current_language()
        selected_language = InterfaceLanguage(language_value)
        try:
            translation_messages(selected_language)
            validate_qt_translations(selected_language)
            localized_catalog = load_exercise_catalog(
                language=selected_language
            )
        except RuntimeError as error:
            window.data.interface_language = previous_language
            window._save_data()
            QMessageBox.critical(
                window,
                tr("Could not change language"),
                str(error),
            )
            return
        previous_window = window
        runtime_state = previous_window.prepare_for_language_reload()
        if runtime_state is None:
            previous_window.data.interface_language = previous_language
            previous_window._save_data()
            return
        set_language(selected_language)
        configure_qt_translations(app)
        catalog = localized_catalog
        replacement_data = data.model_copy(deep=True)
        replacement = MainWindow(
            store,
            replacement_data,
            catalog,
            runtime_state=runtime_state,
        )
        connect_window(replacement)
        data = replacement_data
        window = replacement
        replacement.show()
        previous_window.deleteLater()

    def show_main_window(*_args) -> None:
        nonlocal window
        if window is not None:
            return
        window = MainWindow(store, data, catalog)
        connect_window(window)
        # Autostart launches stay in the background, but fall back to showing
        # the window when there is no system tray to reach the app from.
        if not start_minimized or not QSystemTrayIcon.isSystemTrayAvailable():
            window.show()

    if sys.platform == "darwin":
        camera_permission = QCameraPermission()
        if (
            app.checkPermission(camera_permission)
            == Qt.PermissionStatus.Undetermined
        ):
            permission_launcher = CameraPermissionLauncher(show_main_window)
            permission_launcher.setParent(app)
            app.requestPermission(
                camera_permission,
                permission_launcher,
                permission_launcher.permission_decided,
            )
        else:
            show_main_window()
    else:
        show_main_window()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
