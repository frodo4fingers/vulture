from __future__ import annotations

import ast
import os
from pathlib import Path
from string import Formatter

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QToolButton

from vulture.autostart import AutostartSnapshot
import vulture.exercises as exercises_module
import vulture.i18n as i18n_module
from vulture.exercises import load_exercise_catalog
from vulture.history import PostureHistoryStore
from vulture.i18n import set_language, tr, translation_messages
from vulture.models import (
    AlertPolicy,
    AppData,
    CameraDescriptor,
    ExercisePreferences,
    FeatureFrame,
    GeometryFingerprint,
    HistoryPreferences,
    InterfaceLanguage,
    SetupProfile,
)
from vulture.storage import AppDataStore
from vulture.ui import MainWindow, MainWindowRuntimeState, SettingsDialog


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _translation_keys() -> set[str]:
    keys: set[str] = set()
    source_root = PROJECT_ROOT / "src" / "vulture"
    for path in source_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                keys.add(node.args[0].value)

    for path in (
        source_root / "ui.py",
        source_root / "tracking.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                names = {
                    target.id
                    for target in node.targets
                    if isinstance(target, ast.Name)
                }
                if names & {
                    "CATEGORY_MESSAGES",
                    "SUMMARY_POSTURES",
                    "REMINDER_STAGE_TITLES",
                }:
                    for child in ast.walk(node.value):
                        if (
                            isinstance(child, ast.Constant)
                            and isinstance(child.value, str)
                        ):
                            keys.add(child.value)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "CalibrationStep"
            ):
                for keyword in node.keywords:
                    if (
                        keyword.arg in {"title", "instructions"}
                        and isinstance(keyword.value, ast.Constant)
                        and isinstance(keyword.value.value, str)
                    ):
                        keys.add(keyword.value.value)
    return keys


def _placeholders(message: str) -> set[tuple[str, str]]:
    return {
        (field_name, format_spec)
        for _literal, field_name, format_spec, _conversion in Formatter().parse(
            message
        )
        if field_name is not None
    }


def test_all_interface_messages_have_complete_translations() -> None:
    keys = _translation_keys()

    for language in (
        InterfaceLanguage.GERMAN,
        InterfaceLanguage.SPANISH,
    ):
        messages = translation_messages(language)
        assert set(messages) == keys
        assert all(
            _placeholders(source) == _placeholders(translated)
            for source, translated in messages.items()
        )


def test_language_defaults_and_round_trips(
    tmp_path: Path,
) -> None:
    legacy = AppData.model_validate({"schema_version": 1})
    assert legacy.interface_language is InterfaceLanguage.ENGLISH
    assert legacy.alert_policy.posture_transition_buffer_seconds == 8

    store = AppDataStore(tmp_path / "settings.json")
    legacy.interface_language = InterfaceLanguage.SPANISH
    store.save(legacy)

    assert (
        store.load().interface_language
        is InterfaceLanguage.SPANISH
    )


def test_localized_catalogs_preserve_structural_identifiers() -> None:
    catalogs = {
        language: load_exercise_catalog(language=language)
        for language in InterfaceLanguage
    }
    english = catalogs[InterfaceLanguage.ENGLISH]
    exercise_ids = [exercise.id for exercise in english.exercises]
    source_ids = [source.id for source in english.sources]

    for language, catalog in catalogs.items():
        assert [exercise.id for exercise in catalog.exercises] == exercise_ids
        assert [source.id for source in catalog.sources] == source_ids
        assert [
            exercise.media_path for exercise in catalog.exercises
        ] == [
            exercise.media_path for exercise in english.exercises
        ]
        if language is not InterfaceLanguage.ENGLISH:
            assert catalog.exercises[0].title != english.exercises[0].title


def test_settings_dialog_returns_selected_language(
    application: QApplication,
) -> None:
    set_language(InterfaceLanguage.GERMAN)
    dialog = SettingsDialog(
        AlertPolicy(clear_after_seconds=31),
        ExercisePreferences(),
        HistoryPreferences(),
        InterfaceLanguage.GERMAN,
        start_at_login_enabled=True,
    )
    spanish_index = dialog.language_combo.findData(
        InterfaceLanguage.SPANISH.value
    )
    dialog.language_combo.setCurrentIndex(spanish_index)
    dialog.transition_buffer_seconds.setValue(12)
    dialog._validate_and_accept()

    assert dialog.values()[0].posture_transition_buffer_seconds == 12
    assert dialog.values()[3] is InterfaceLanguage.SPANISH
    assert dialog.values()[4] is True
    assert dialog.windowTitle() == "Vulture-Einstellungen"

    dialog.close()
    application.processEvents()

    unavailable_dialog = SettingsDialog(
        AlertPolicy(),
        ExercisePreferences(),
        HistoryPreferences(),
        InterfaceLanguage.GERMAN,
        startup_setting_available=False,
    )
    assert not unavailable_dialog.start_at_login.isEnabled()
    assert unavailable_dialog.values()[4] is None
    unavailable_dialog.close()
    application.processEvents()
    set_language(InterfaceLanguage.ENGLISH)


def test_main_window_saves_and_requests_language_reload(
    application: QApplication,
    tmp_path: Path,
) -> None:
    set_language(InterfaceLanguage.ENGLISH)
    store = AppDataStore(tmp_path / "settings.json")
    data = AppData()
    history_store = PostureHistoryStore(tmp_path / "history.sqlite3")

    class FakeAutostartManager:
        is_supported = True

        @staticmethod
        def snapshot() -> AutostartSnapshot:
            return AutostartSnapshot("linux", False, False)

        @staticmethod
        def set_enabled(_enabled: bool) -> None:
            return None

        @staticmethod
        def restore(_snapshot: AutostartSnapshot) -> None:
            return None

    window = MainWindow(
        store,
        data,
        load_exercise_catalog(language=InterfaceLanguage.ENGLISH),
        history_store,
        autostart_manager=FakeAutostartManager(),
    )

    requested_languages: list[str] = []
    window.language_change_requested.connect(
        requested_languages.append
    )

    window._show_settings()
    application.processEvents()
    dialog = window._settings_dialog
    assert isinstance(dialog, SettingsDialog)
    spanish_index = dialog.language_combo.findData(
        InterfaceLanguage.SPANISH.value
    )
    dialog.language_combo.setCurrentIndex(spanish_index)
    dialog.start_at_login.setChecked(False)
    dialog._validate_and_accept()
    application.processEvents()

    assert requested_languages == [InterfaceLanguage.SPANISH.value]
    assert (
        store.load().interface_language
        is InterfaceLanguage.SPANISH
    )

    window.break_timer.stop()
    window._close_history()
    window.tray.hide()
    window.deleteLater()
    application.processEvents()
    set_language(InterfaceLanguage.ENGLISH)


def test_spanish_translation_is_active() -> None:
    try:
        set_language(InterfaceLanguage.SPANISH)
        assert tr("Settings") == "Configuración"
    finally:
        set_language(InterfaceLanguage.ENGLISH)


def test_missing_language_resources_raise_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_resource(*_parts: str) -> Path:
        raise FileNotFoundError("missing resource")

    monkeypatch.setattr(i18n_module, "resource_path", missing_resource)
    with pytest.raises(RuntimeError, match="interface translations"):
        translation_messages(InterfaceLanguage.GERMAN)

    monkeypatch.setattr(
        exercises_module,
        "exercise_catalog_path",
        lambda _language: missing_resource(),
    )
    with pytest.raises(RuntimeError, match="exercise catalog"):
        load_exercise_catalog(language=InterfaceLanguage.GERMAN)


def test_window_reload_preserves_paused_session_state(
    application: QApplication,
    tmp_path: Path,
) -> None:
    set_language(InterfaceLanguage.ENGLISH)
    store = AppDataStore(tmp_path / "settings.json")
    data = AppData()
    old_window = MainWindow(
        store,
        data,
        load_exercise_catalog(language=InterfaceLanguage.ENGLISH),
        PostureHistoryStore(tmp_path / "old-history.sqlite3"),
    )
    old_window._tracking_enabled = False
    old_window._tracked_seconds_since_break = 321.5

    runtime_state = old_window.prepare_for_language_reload()
    assert runtime_state is not None

    set_language(InterfaceLanguage.SPANISH)
    replacement = MainWindow(
        store,
        data,
        load_exercise_catalog(language=InterfaceLanguage.SPANISH),
        PostureHistoryStore(tmp_path / "new-history.sqlite3"),
        runtime_state,
    )

    assert not replacement._tracking_enabled
    assert replacement._tracked_seconds_since_break == 321.5
    assert replacement.pause_button.text() == "Reanudar seguimiento"

    replacement.break_timer.stop()
    replacement._close_history()
    replacement.tray.hide()
    replacement.deleteLater()
    old_window.deleteLater()
    application.processEvents()
    set_language(InterfaceLanguage.ENGLISH)


def test_long_localized_toolbar_uses_native_overflow(
    application: QApplication,
    tmp_path: Path,
) -> None:
    set_language(InterfaceLanguage.GERMAN)
    window = MainWindow(
        AppDataStore(tmp_path / "settings.json"),
        AppData(),
        load_exercise_catalog(language=InterfaceLanguage.GERMAN),
        PostureHistoryStore(tmp_path / "history.sqlite3"),
    )
    window.break_timer.stop()
    window.history_timer.stop()
    window._exercise_postpone_timer.stop()
    window.resize(760, 650)
    window.show()
    application.processEvents()

    overflow_buttons = [
        button
        for button in window.command_bar.findChildren(QToolButton)
        if button.defaultAction() is None and button.isVisible()
    ]
    assert overflow_buttons
    assert window.add_setup_button.isVisible()
    assert window.pause_button.isVisible()

    window._close_history()
    window.tray.hide()
    window.deleteLater()
    application.processEvents()
    set_language(InterfaceLanguage.ENGLISH)


def test_failed_reload_preparation_resumes_window(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    set_language(InterfaceLanguage.ENGLISH)
    window = MainWindow(
        AppDataStore(tmp_path / "settings.json"),
        AppData(),
        load_exercise_catalog(language=InterfaceLanguage.ENGLISH),
        PostureHistoryStore(tmp_path / "history.sqlite3"),
    )
    actual_close_history = window._close_history
    restarted: list[bool] = []
    window._tracking_enabled = False
    window._tracked_seconds_since_break = 45.0
    monkeypatch.setattr(window, "_stop_camera", lambda *_args: True)
    monkeypatch.setattr(window, "_close_history", lambda: False)
    monkeypatch.setattr(
        window,
        "_activate_setup",
        lambda: restarted.append(True),
    )

    assert window.prepare_for_language_reload() is None
    assert restarted == [True]
    assert window.break_timer.isActive()
    assert not window._tracking_enabled
    assert window._tracked_seconds_since_break == 45.0

    window.break_timer.stop()
    actual_close_history()
    window.tray.hide()
    window.deleteLater()
    application.processEvents()


def test_reload_keeps_history_disabled_after_session_error(
    application: QApplication,
    tmp_path: Path,
) -> None:
    store = AppDataStore(tmp_path / "settings.json")
    history_path = tmp_path / "posture-history.sqlite3"
    window = MainWindow(
        store,
        AppData(),
        load_exercise_catalog(language=InterfaceLanguage.ENGLISH),
        runtime_state=MainWindowRuntimeState(
            history_disabled_for_session=True
        ),
    )

    assert window.history_store is None
    assert window.history_recorder is None
    assert not history_path.exists()
    assert not window.summary_button.isEnabled()

    window.break_timer.stop()
    window.tray.hide()
    window.deleteLater()
    application.processEvents()


def test_queued_camera_callbacks_are_ignored_during_reload(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = MainWindow(
        AppDataStore(tmp_path / "settings.json"),
        AppData(),
        load_exercise_catalog(language=InterfaceLanguage.ENGLISH),
        PostureHistoryStore(tmp_path / "history.sqlite3"),
    )
    queued_preview = QImage(16, 16, QImage.Format.Format_RGB888)
    queued_feature = FeatureFrame(
        values={},
        category_quality={},
        overall_quality=1.0,
        geometry=GeometryFingerprint(
            frame_width=640,
            frame_height=480,
            shoulder_width=180,
            torso_length=260,
            subject_center_x=0.5,
            subject_center_y=0.5,
            shoulder_roll_degrees=0,
            yaw_proxy=0,
        ),
    )
    initial_status = window.status_label.text()
    QTimer.singleShot(0, lambda: window._on_preview(queued_preview))
    QTimer.singleShot(0, lambda: window._on_feature(queued_feature))

    assert window.prepare_for_language_reload() is not None
    application.processEvents()

    assert window._latest_image is None
    assert window.status_label.text() == initial_status

    window.tray.hide()
    window.deleteLater()
    application.processEvents()


def test_queued_actions_cannot_mutate_replacement_state(
    application: QApplication,
    tmp_path: Path,
) -> None:
    store = AppDataStore(tmp_path / "settings.json")
    data = AppData()
    window = MainWindow(
        store,
        data,
        load_exercise_catalog(language=InterfaceLanguage.ENGLISH),
        PostureHistoryStore(tmp_path / "history.sqlite3"),
    )
    first_setup = SetupProfile(
        name="First",
        camera=CameraDescriptor(
            stable_id="first",
            display_name="First camera",
            locator=0,
        ),
    )
    second_setup = SetupProfile(
        name="Second",
        camera=CameraDescriptor(
            stable_id="second",
            display_name="Second camera",
            locator=1,
        ),
    )
    data.setups = [first_setup, second_setup]
    data.active_setup_id = first_setup.id
    store.save(data)
    window._refresh_setup_combo()
    second_index = window.setup_combo.findData(second_setup.id)
    QTimer.singleShot(0, lambda: window._setup_changed(second_index))
    QTimer.singleShot(0, window._toggle_tracking)

    assert window.prepare_for_language_reload() is not None
    replacement_data = data.model_copy(deep=True)
    application.processEvents()

    assert data.active_setup_id == first_setup.id
    assert replacement_data.active_setup_id == first_setup.id
    assert store.load().active_setup_id == first_setup.id
    assert window._tracking_enabled
    assert window.camera_thread is None

    window.tray.hide()
    window.deleteLater()
    application.processEvents()
