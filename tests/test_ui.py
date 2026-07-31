from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import vulture.ui as ui_module
from vulture.autostart import AutostartError, AutostartSnapshot
from vulture.exercises import load_exercise_catalog
from vulture.history import (
    BASELINE_POSTURE,
    DailyPostureSummary,
    HistoryStorageError,
    PostureHistoryStore,
    StoredPostureEpisode,
)
from vulture.models import (
    AppData,
    BreakPreferences,
    CalibrationProfile,
    CameraDescriptor,
    FeatureFrame,
    GeometryFingerprint,
    PostureCategory,
    SetupProfile,
    TrackerState,
)
from vulture.calibration import CalibrationError, CalibrationFitter
from vulture.storage import AppDataStore

from PySide6.QtCore import QDate, QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QPushButton,
    QSystemTrayIcon,
)

from vulture.ui import (
    CALIBRATION_STEPS,
    POSTURE_STEPS,
    CalibrationDialog,
    CalibrationStep,
    CalibrationStepSelectionDialog,
    EvidenceDialog,
    ExerciseDialog,
    ExerciseOutcome,
    MainWindow,
    MainWindowRuntimeState,
    NoticeDialog,
    PostureAreaChart,
    RollingWeekChart,
    SUMMARY_POSTURE_PALETTES,
    SettingsDialog,
    SetupDialog,
    WorkdaySummaryDialog,
    build_posture_area_data,
    build_rolling_week_data,
    create_state_icon,
)
from vulture.ui.common import ContentHeightTextBrowser, SemanticLabel
from tests.test_calibration import make_frame


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def make_profile() -> CalibrationProfile:
    return CalibrationProfile(
        good_center={"head_offset_x": 0.0},
        good_scale={"head_offset_x": 0.01},
        good_sample_count=30,
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


def make_history_episode(
    episode_id: int,
    started_at: datetime,
    ended_at: datetime,
    posture: str,
) -> StoredPostureEpisode:
    return StoredPostureEpisode(
        id=episode_id,
        local_date=started_at.date(),
        started_at=started_at,
        ended_at=ended_at,
        utc_offset_minutes=0,
        setup_id="desk",
        posture=posture,
        peak_state=TrackerState.GOOD,
        duration_seconds=(ended_at - started_at).total_seconds(),
        sample_count=2,
    )


def test_posture_area_data_buckets_episode_overlap() -> None:
    workday = date(2026, 7, 20)
    start = datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)
    episodes = [
        make_history_episode(
            1,
            start,
            start + timedelta(minutes=10),
            BASELINE_POSTURE,
        ),
        make_history_episode(
            2,
            start + timedelta(minutes=10),
            start + timedelta(minutes=20),
            PostureCategory.FORWARD_HEAD.value,
        ),
        make_history_episode(
            3,
            start + timedelta(minutes=20),
            start + timedelta(minutes=30),
            PostureCategory.SLOUCH.value,
        ),
    ]
    summary = DailyPostureSummary(
        local_date=workday,
        totals={
            BASELINE_POSTURE: 600,
            PostureCategory.FORWARD_HEAD.value: 600,
            PostureCategory.SLOUCH.value: 600,
        },
        tracked_seconds=1_800,
        reminder_count=0,
        episodes=episodes,
    )

    data = build_posture_area_data(summary)

    assert data is not None
    assert data.start_hour == 9
    assert data.end_hour == 10
    assert data.bucket_hours == (9.125, 9.375, 9.625, 9.875)
    assert data.minutes_by_posture[BASELINE_POSTURE] == (10, 0, 0, 0)
    assert data.minutes_by_posture[
        PostureCategory.FORWARD_HEAD.value
    ] == (5, 5, 0, 0)
    assert data.minutes_by_posture[
        PostureCategory.SLOUCH.value
    ] == (0, 10, 0, 0)


def test_rolling_week_data_aggregates_seven_days() -> None:
    end_date = date(2026, 7, 20)
    summaries = tuple(
        DailyPostureSummary(
            local_date=end_date - timedelta(days=6 - index),
            totals=(
                {
                    BASELINE_POSTURE: 600,
                    PostureCategory.SLOUCH.value: 300,
                }
                if index > 0
                else {}
            ),
            tracked_seconds=900 if index > 0 else 0,
            reminder_count=index % 2,
            episodes=[],
        )
        for index in range(7)
    )

    data = build_rolling_week_data(end_date, summaries)

    assert data.start_date == date(2026, 7, 14)
    assert data.end_date == end_date
    assert data.tracked_seconds == 5_400
    assert data.totals[BASELINE_POSTURE] == 3_600
    assert data.totals[PostureCategory.SLOUCH.value] == 1_800
    assert data.reminder_count == 3
    assert data.days_with_data == 6


def test_workday_summary_renders_stacked_posture_chart(
    application: QApplication,
) -> None:
    workday = date(2026, 7, 20)
    start = datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)
    episode = make_history_episode(
        1,
        start,
        start + timedelta(minutes=15),
        BASELINE_POSTURE,
    )
    summary = DailyPostureSummary(
        local_date=workday,
        totals={BASELINE_POSTURE: 900},
        tracked_seconds=900,
        reminder_count=0,
        episodes=[episode],
    )
    dialog = WorkdaySummaryDialog(
        lambda _selected_date: summary,
        lambda _selected_date: None,
        lambda: None,
        {"desk": "Desk"},
        True,
    )

    assert isinstance(dialog.posture_chart, PostureAreaChart)
    assert isinstance(dialog.weekly_chart, RollingWeekChart)
    assert dialog.period_tabs.count() == 3
    assert not dialog.posture_chart.chart().legend().isVisible()
    assert len(dialog.posture_chart.chart().series()) == 1
    assert [
        series.name()
        for series in dialog.posture_chart.chart().series()
    ] == [
        "Within baseline",
    ]
    assert (
        dialog.posture_chart.chart()
        .series()[0]
        .brush()
        .color()
        .name()
        == "#34a853"
    )
    assert dialog.posture_chart.chart().series()[0].opacity() == 0.82
    assert dialog.timeline.rowCount() == 1
    assert dialog.period_tabs.isTabEnabled(dialog.timeline_tab_index)
    assert len(dialog.weekly_chart.chart().series()) == 1
    assert dialog.weekly_chart.chart().legend().isVisible()
    assert (
        dialog.weekly_chart.chart().legend().alignment()
        == Qt.AlignmentFlag.AlignTop
    )
    assert dialog.weekly_table.rowCount() == 7
    assert dialog.weekly_days_metric.value_label.text() == "7 of 7"

    empty_summary = DailyPostureSummary(
        local_date=workday,
        totals={},
        tracked_seconds=0,
        reminder_count=0,
        episodes=[],
    )
    dialog.posture_chart.set_summary(empty_summary)
    application.processEvents()
    assert dialog.posture_chart.chart().series() == []
    assert (
        dialog.posture_chart.chart().title()
        == "No tracked posture data for this day."
    )

    dialog.posture_chart.set_summary(summary)
    application.processEvents()
    assert len(dialog.posture_chart.chart().series()) == 1

    dialog.close()
    application.processEvents()


def test_workday_summary_uses_bright_theme_palettes() -> None:
    assert set(SUMMARY_POSTURE_PALETTES["light"].values()) == {
        "#34A853",
        "#4285F4",
        "#EA4335",
        "#FBBC04",
        "#A142F4",
        "#12B5CB",
    }
    assert min(
        QColor(color).hsvSaturation()
        for color in SUMMARY_POSTURE_PALETTES["dark"].values()
    ) >= 80


def test_workday_summary_restyles_metrics_after_palette_change(
    application: QApplication,
) -> None:
    original_palette = application.palette()
    light_palette = QPalette(original_palette)
    dark_palette = QPalette(original_palette)
    for role, value in {
        QPalette.ColorRole.Window: "#f0f0f0",
        QPalette.ColorRole.Base: "#ffffff",
        QPalette.ColorRole.AlternateBase: "#e8e8e8",
        QPalette.ColorRole.Mid: "#b0b0b0",
        QPalette.ColorRole.PlaceholderText: "#707070",
    }.items():
        light_palette.setColor(role, QColor(value))
    for role, value in {
        QPalette.ColorRole.Window: "#171a1f",
        QPalette.ColorRole.Base: "#20262d",
        QPalette.ColorRole.AlternateBase: "#272e36",
        QPalette.ColorRole.Mid: "#4a535e",
        QPalette.ColorRole.PlaceholderText: "#aab1b9",
    }.items():
        dark_palette.setColor(role, QColor(value))

    workday = date(2026, 7, 20)
    summary = DailyPostureSummary(
        local_date=workday,
        totals={},
        tracked_seconds=0,
        reminder_count=0,
        episodes=[],
    )
    dialog: WorkdaySummaryDialog | None = None
    try:
        application.setPalette(light_palette)
        dialog = WorkdaySummaryDialog(
            lambda _selected_date: summary,
            lambda _selected_date: None,
            lambda: None,
            {},
            True,
        )
        dialog.show()
        application.processEvents()
        light_metric_style = dialog.daily_tracked_metric.styleSheet()

        application.setPalette(dark_palette)
        application.processEvents()

        assert (
            dialog.daily_tracked_metric.styleSheet()
            != light_metric_style
        )
        assert (
            dark_palette.color(QPalette.ColorRole.Base)
            .lighter(108)
            .name()
            in dialog.daily_tracked_metric.styleSheet()
        )
        assert (
            "#81c995"
            in dialog.total_bars[BASELINE_POSTURE].styleSheet()
        )
        assert (
            dialog.daily_tracked_metric.caption_label.palette().color(
                QPalette.ColorRole.WindowText
            )
            == dark_palette.color(QPalette.ColorRole.PlaceholderText)
        )
    finally:
        if dialog is not None:
            dialog.close()
        application.setPalette(original_palette)
        application.processEvents()


def test_workday_history_deletion_confirms_inline(
    application: QApplication,
) -> None:
    workday = date(2026, 7, 20)
    deleted_days: list[date] = []
    summary = DailyPostureSummary(
        local_date=workday,
        totals={},
        tracked_seconds=0,
        reminder_count=0,
        episodes=[],
    )
    dialog = WorkdaySummaryDialog(
        lambda _selected_date: summary,
        deleted_days.append,
        lambda: None,
        {},
        True,
    )
    dialog.date_edit.setDate(QDate(2026, 7, 20))

    dialog._delete_selected_day()

    assert deleted_days == []
    assert not dialog.delete_confirmation.isHidden()
    assert not dialog.confirm_delete_button.isHidden()
    assert not dialog.delete_day_button.isEnabled()

    dialog._confirm_history_delete()

    assert deleted_days == [workday]
    assert dialog.delete_confirmation.isHidden()
    assert not dialog.delete_day_button.isEnabled()

    dialog.close()
    application.processEvents()


def test_workday_summary_uses_one_empty_state(
    application: QApplication,
) -> None:
    workday = date(2026, 7, 20)
    summary = DailyPostureSummary(
        local_date=workday,
        totals={},
        tracked_seconds=0,
        reminder_count=0,
        episodes=[],
    )
    dialog = WorkdaySummaryDialog(
        lambda _selected_date: summary,
        lambda _selected_date: None,
        lambda: None,
        {},
        True,
    )

    assert not dialog.empty_state.isHidden()
    assert dialog.totals_group.isHidden()
    assert dialog.chart_group.isHidden()
    assert dialog.timeline_group.isHidden()
    assert not dialog.period_tabs.isTabEnabled(dialog.timeline_tab_index)
    assert dialog.period_tabs.isTabEnabled(dialog.week_tab_index)
    assert (
        dialog.weekly_chart.chart().title()
        == "No tracked posture data in this 7-day window."
    )
    assert not dialog.delete_day_button.isEnabled()

    dialog.close()
    application.processEvents()


def test_workday_summary_surfaces_storage_errors(
    application: QApplication,
) -> None:
    workday = date(2026, 7, 20)
    summary = DailyPostureSummary(
        local_date=workday,
        totals={},
        tracked_seconds=0,
        reminder_count=0,
        episodes=[],
    )
    should_fail = False

    def provide_summary(_selected_date: date) -> DailyPostureSummary:
        if should_fail:
            raise HistoryStorageError("database unavailable")
        return summary

    dialog = WorkdaySummaryDialog(
        provide_summary,
        lambda _selected_date: None,
        lambda: None,
        {},
        True,
    )
    should_fail = True

    dialog.refresh()

    assert not dialog.empty_state_container.isHidden()
    assert "database unavailable" in dialog.empty_state.text()
    assert dialog.totals_group.isHidden()
    assert not dialog.period_tabs.isTabEnabled(dialog.week_tab_index)
    assert not dialog.delete_day_button.isEnabled()

    dialog.close()
    application.processEvents()


class _FakeAutostartManager:
    is_supported = True

    def __init__(
        self,
        *,
        enabled: bool = False,
        fail_read: bool = False,
        fail_write: bool = False,
        registered: bool | None = None,
        snapshots: list[AutostartSnapshot] | None = None,
    ) -> None:
        self.enabled = enabled
        self.fail_read = fail_read
        self.fail_write = fail_write
        self.registered = enabled if registered is None else registered
        self.snapshots = list(snapshots or [])
        self.calls: list[bool] = []
        self.restore_calls: list[AutostartSnapshot] = []

    def is_enabled(self) -> bool:
        return self.snapshot().enabled

    def snapshot(self) -> AutostartSnapshot:
        if self.fail_read:
            raise AutostartError("permission denied")
        if self.snapshots:
            snapshot = self.snapshots.pop(0)
            self.enabled = snapshot.enabled
            self.registered = snapshot.exists
            return snapshot
        return AutostartSnapshot(
            "linux",
            self.registered,
            self.enabled,
        )

    def set_enabled(self, enabled: bool) -> None:
        self.calls.append(enabled)
        if self.fail_write:
            raise AutostartError("permission denied")
        self.enabled = enabled
        self.registered = enabled

    def restore(self, snapshot: AutostartSnapshot) -> None:
        self.restore_calls.append(snapshot)
        self.enabled = snapshot.enabled
        self.registered = snapshot.exists


def _close_test_window(
    window: MainWindow,
    application: QApplication,
) -> None:
    window.break_timer.stop()
    window._dismiss_side_panel()
    window._close_history()
    window.tray.hide()
    window.deleteLater()
    application.processEvents()


def _open_settings_panel(
    window: MainWindow,
    application: QApplication,
) -> SettingsDialog:
    window._show_settings()
    application.processEvents()
    dialog = window._settings_dialog
    assert isinstance(dialog, SettingsDialog)
    assert dialog is window._side_panel
    assert window.side_panel_host.widget() is dialog
    assert not dialog.isWindow()
    return dialog


def test_settings_updates_system_startup_registration(
    application: QApplication,
    tmp_path: Path,
) -> None:
    manager = _FakeAutostartManager()
    store = AppDataStore(tmp_path / "settings.json")
    data = AppData()
    window = MainWindow(
        store,
        data,
        load_exercise_catalog(),
        PostureHistoryStore(tmp_path / "history.sqlite3"),
        autostart_manager=manager,
    )

    dialog = _open_settings_panel(window, application)
    assert dialog.start_at_login.isEnabled()
    dialog.start_at_login.setChecked(True)
    dialog.movement_interval_minutes.setValue(45)
    dialog.eye_reminders_enabled.setChecked(False)
    dialog._validate_and_accept()
    application.processEvents()

    assert manager.enabled
    assert manager.calls == [True]
    assert store.path.is_file()
    saved = store.load()
    assert saved.break_preferences.movement_interval_minutes == 45
    assert not saved.break_preferences.eye_reminders_enabled
    assert window._settings_dialog is None
    assert window.side_panel_host.isHidden()
    _close_test_window(window, application)


def test_settings_roll_back_startup_when_preferences_cannot_save(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manager = _FakeAutostartManager()
    data = AppData()
    window = MainWindow(
        AppDataStore(tmp_path / "settings.json"),
        data,
        load_exercise_catalog(),
        PostureHistoryStore(tmp_path / "history.sqlite3"),
        autostart_manager=manager,
    )

    monkeypatch.setattr(window, "_save_data", lambda: False)

    dialog = _open_settings_panel(window, application)
    dialog.start_at_login.setChecked(True)
    dialog._validate_and_accept()
    application.processEvents()

    assert not manager.enabled
    assert manager.calls == [True]
    assert len(manager.restore_calls) == 1
    _close_test_window(window, application)


def test_settings_surface_startup_registration_failures(
    application: QApplication,
    tmp_path: Path,
) -> None:
    manager = _FakeAutostartManager(fail_write=True)
    data = AppData()
    window = MainWindow(
        AppDataStore(tmp_path / "settings.json"),
        data,
        load_exercise_catalog(),
        PostureHistoryStore(tmp_path / "history.sqlite3"),
        autostart_manager=manager,
    )

    dialog = _open_settings_panel(window, application)
    dialog.start_at_login.setChecked(True)
    dialog._validate_and_accept()
    application.processEvents()

    assert not manager.enabled
    assert manager.calls == [True]
    notice = window._notice_dialog
    assert isinstance(notice, NoticeDialog)
    assert notice.windowTitle() == "Could not update startup setting"
    assert notice is window._side_panel
    assert not notice.isWindow()
    _close_test_window(window, application)


def test_settings_disable_startup_control_when_state_cannot_be_read(
    application: QApplication,
    tmp_path: Path,
) -> None:
    manager = _FakeAutostartManager(fail_read=True)
    window = MainWindow(
        AppDataStore(tmp_path / "settings.json"),
        AppData(),
        load_exercise_catalog(),
        PostureHistoryStore(tmp_path / "history.sqlite3"),
        autostart_manager=manager,
    )

    dialog = _open_settings_panel(window, application)
    assert not dialog.start_at_login.isEnabled()
    assert any(
        "permission denied" in label.text()
        for label in dialog.findChildren(QLabel)
    )
    dialog.reject()
    application.processEvents()
    _close_test_window(window, application)


def test_settings_remove_stale_startup_registration(
    application: QApplication,
    tmp_path: Path,
) -> None:
    manager = _FakeAutostartManager(registered=True)
    data = AppData()
    window = MainWindow(
        AppDataStore(tmp_path / "settings.json"),
        data,
        load_exercise_catalog(),
        PostureHistoryStore(tmp_path / "history.sqlite3"),
        autostart_manager=manager,
    )

    dialog = _open_settings_panel(window, application)
    dialog.start_at_login.setChecked(False)
    dialog._validate_and_accept()
    application.processEvents()

    assert not manager.registered
    assert manager.calls == [False]
    _close_test_window(window, application)


def test_settings_refresh_startup_state_before_saving(
    application: QApplication,
    tmp_path: Path,
) -> None:
    manager = _FakeAutostartManager(
        snapshots=[
            AutostartSnapshot("linux", False, False),
            AutostartSnapshot("linux", True, True, payload=b"current"),
        ]
    )
    data = AppData()
    window = MainWindow(
        AppDataStore(tmp_path / "settings.json"),
        data,
        load_exercise_catalog(),
        PostureHistoryStore(tmp_path / "history.sqlite3"),
        autostart_manager=manager,
    )

    dialog = _open_settings_panel(window, application)
    dialog.start_at_login.setChecked(False)
    dialog._validate_and_accept()
    application.processEvents()

    assert manager.calls == [False]
    assert not manager.registered
    _close_test_window(window, application)


def test_tracking_loss_uses_posture_transition_buffer() -> None:
    captured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    calls: list[object] = []
    states: list[TrackerState] = []

    class Evaluator:
        def mark_tracking_uncertain(self, value: datetime) -> bool:
            calls.append(value)
            return True

        def mark_tracking_lost(self) -> None:
            calls.append("lost")

    window = SimpleNamespace(
        sender=lambda: None,
        camera_thread=None,
        _language_reload_preparing=False,
        _calibration_flow_active=False,
        _tracking_enabled=True,
        evaluator=Evaluator(),
        _suspend_history=lambda: calls.append("history"),
        _last_valid_tracking_at=object(),
        _tracking_gap_started_at=None,
        _set_state=lambda state, _message: states.append(state),
    )
    window._mark_tracking_interrupted = (
        lambda: MainWindow._mark_tracking_interrupted(window)
    )

    MainWindow._on_tracking_lost(window, captured_at)

    assert calls == [captured_at, "history"]
    assert states == [TrackerState.LOW_CONFIDENCE]
    assert window._last_valid_tracking_at is None


def test_stale_tracking_loss_has_no_ui_side_effects() -> None:
    calls: list[str] = []
    window = SimpleNamespace(
        sender=lambda: None,
        camera_thread=None,
        _language_reload_preparing=False,
        _calibration_flow_active=False,
        _tracking_enabled=True,
        evaluator=SimpleNamespace(
            mark_tracking_uncertain=lambda _captured_at: False,
        ),
        _suspend_history=lambda: calls.append("history"),
        _last_valid_tracking_at=object(),
        _mark_tracking_interrupted=lambda: calls.append("interrupted"),
        _set_state=lambda _state, _message: calls.append("state"),
    )

    MainWindow._on_tracking_lost(
        window,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert calls == []
    assert window._last_valid_tracking_at is not None


def test_replaced_camera_signals_are_ignored() -> None:
    old_camera = object()
    current_camera = object()
    window = SimpleNamespace(
        sender=lambda: old_camera,
        camera_thread=current_camera,
    )

    MainWindow._on_feature(window, object())
    MainWindow._on_tracking_lost(
        window,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_full_calibration_lists_every_stage(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog()

    assert dialog.stage_list.count() == len(CALIBRATION_STEPS)
    assert "GOOD" in dialog.stage_list.item(0).text()
    assert "CURRENT" in dialog.stage_list.item(0).text()
    assert all(
        "UNWANTED" in dialog.stage_list.item(index).text()
        for index in range(1, dialog.stage_list.count())
    )
    assert dialog.reference_image.accessibleName() == "Comfortable baseline"
    assert dialog.reference_image.pixmap() is not None
    assert not dialog.reference_image.pixmap().isNull()

    dialog.timer.stop()
    dialog.close()
    application.processEvents()


def test_incremental_calibration_shows_baseline_and_selected_posture(
    application: QApplication,
) -> None:
    baseline = CalibrationStep(
        key="good",
        title="Confirm saved good baseline",
        instructions="Sit in the saved baseline.",
        required=True,
        capture_seconds=10,
    )
    unwanted = POSTURE_STEPS[PostureCategory.SLOUCH].model_copy(
        update={"required": True}
    )
    dialog = CalibrationDialog(
        steps=[baseline, unwanted],
        base_profile=make_profile(),
    )

    assert dialog.stage_list.count() == 2
    assert "GOOD" in dialog.stage_list.item(0).text()
    assert "UNWANTED" in dialog.stage_list.item(1).text()
    assert "required" in dialog.stage_list.item(1).text()

    dialog.timer.stop()
    dialog.close()
    application.processEvents()


def test_calibration_step_selection_includes_baseline_and_postures(
    application: QApplication,
) -> None:
    dialog = CalibrationStepSelectionDialog(make_profile())

    assert dialog.step_combo.count() == len(CALIBRATION_STEPS)
    assert dialog.selected_step().category is None
    assert "removes all learned" in dialog.description.text()
    baseline_cache_key = dialog.reference_image.pixmap().cacheKey()
    assert dialog.reference_image.accessibleName() == "Comfortable baseline"

    dialog.step_combo.setCurrentIndex(1)
    assert dialog.selected_step().category is PostureCategory.FORWARD_HEAD
    assert "other examples stay unchanged" in dialog.description.text()
    assert dialog.reference_image.accessibleName() == "Head-forward example"
    assert dialog.reference_image.pixmap().cacheKey() != baseline_cache_key

    dialog.close()
    application.processEvents()


def test_baseline_recalibration_requires_inline_confirmation(
    application: QApplication,
) -> None:
    dialog = CalibrationStepSelectionDialog(make_profile())
    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))
    dialog.show()

    QTest.mouseClick(dialog.confirm_button, Qt.MouseButton.LeftButton)
    application.processEvents()

    assert accepted == []
    assert dialog.baseline_warning.isVisible()
    assert dialog.confirm_button.text() == "Recalibrate good baseline"

    QTest.mouseClick(dialog.confirm_button, Qt.MouseButton.LeftButton)
    application.processEvents()

    assert accepted == [True]
    dialog.deleteLater()
    application.processEvents()


def test_good_baseline_can_be_recalibrated_as_one_stage(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog(steps=[CALIBRATION_STEPS[0]])
    dialog._samples["good"] = [make_frame(index) for index in range(40)]

    dialog._fit_profile()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.profile is not None
    assert dialog.profile.categories == {}
    assert dialog.windowTitle() == "Recalibrate good baseline"

    dialog.close()
    application.processEvents()


def test_recalibrate_baseline_routes_only_the_selected_stage(
    application: QApplication,
) -> None:
    setup = SimpleNamespace(calibration=make_profile())
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    selection = CalibrationStepSelectionDialog(setup.calibration)
    window = SimpleNamespace(
        _calibration_panel=selection,
        _camera_is_healthy=lambda: True,
        _state=TrackerState.GOOD,
        _run_recalibration_dialog=lambda *args, **kwargs: calls.append(
            (args, kwargs)
        ),
        _end_calibration_flow=lambda: None,
    )

    MainWindow._finish_recalibration_selection(
        window,
        selection,
        setup,
        QDialog.DialogCode.Accepted,
    )

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == (setup,)
    assert kwargs["base_profile"] is None
    assert len(kwargs["steps"]) == 1
    assert kwargs["steps"][0].category is None
    selection.close()
    application.processEvents()


def test_recalibrate_posture_routes_only_baseline_check_and_selected_step(
    application: QApplication,
) -> None:
    setup = SimpleNamespace(calibration=make_profile())
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    selection = CalibrationStepSelectionDialog(setup.calibration)
    selection.step_combo.setCurrentIndex(
        selection.step_combo.findData(
            PostureCategory.SHOULDERS_SUNK.value
        )
    )
    window = SimpleNamespace(
        _calibration_panel=selection,
        _camera_is_healthy=lambda: True,
        _state=TrackerState.GOOD,
        _run_recalibration_dialog=lambda *args, **kwargs: calls.append(
            (args, kwargs)
        ),
        _end_calibration_flow=lambda: None,
    )

    MainWindow._finish_recalibration_selection(
        window,
        selection,
        setup,
        QDialog.DialogCode.Accepted,
    )

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == (setup,)
    assert kwargs["base_profile"] is setup.calibration
    assert len(kwargs["steps"]) == 2
    assert kwargs["steps"][0].category is None
    assert kwargs["steps"][1].category is PostureCategory.SHOULDERS_SUNK
    assert kwargs["steps"][1].required
    selection.close()
    application.processEvents()


def test_calibration_retry_starts_with_empty_samples(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog()
    dialog._current_samples = [
        FeatureFrame(
            values={},
            category_quality={},
            overall_quality=1.0,
            geometry=make_profile().geometry,
        )
    ]

    dialog._start_sample()

    assert dialog._current_samples == []

    dialog.timer.stop()
    dialog.close()
    application.processEvents()


def test_calibration_retry_heading_names_the_pose_once(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog()
    dialog._step_index = 2
    dialog._show_step()

    dialog._finish_sample()

    assert dialog.phase_label.text() == "RETRY — SLOUCH EXAMPLE"
    assert "UNWANTED" not in dialog.phase_label.text()
    assert dialog.start_button.text() == "Retry sample"

    dialog.timer.stop()
    dialog.close()
    application.processEvents()


def test_calibration_timer_stops_when_dialog_is_rejected(
    application: QApplication,
) -> None:
    dialog = CalibrationDialog()
    assert dialog.timer.isActive()

    dialog.reject()

    assert not dialog.timer.isActive()

    dialog.close()
    application.processEvents()


def test_rejected_dialog_is_not_reaccepted_after_fitting(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog = CalibrationDialog(steps=[CALIBRATION_STEPS[0]])
    profile = make_profile()

    def reject_while_fitting(*_args, **_kwargs) -> CalibrationProfile:
        dialog.reject()
        return profile

    monkeypatch.setattr(CalibrationFitter, "fit", reject_while_fitting)
    dialog._samples["good"] = []

    dialog._fit_profile()

    assert dialog.result() == QDialog.DialogCode.Rejected

    dialog.close()
    application.processEvents()


def test_calibration_fit_error_is_shown_inline(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog = CalibrationDialog(steps=[CALIBRATION_STEPS[0]])
    dialog._samples["good"] = []

    def fail_fit(*_args: object, **_kwargs: object) -> CalibrationProfile:
        raise CalibrationError("Clear baseline frames are required.")

    monkeypatch.setattr(CalibrationFitter, "fit", fail_fit)

    dialog._fit_profile()

    assert not dialog.feedback_label.isHidden()
    assert "Clear baseline frames are required." in (
        dialog.feedback_label.text()
    )
    assert dialog.timer.isActive()

    dialog.reject()
    application.processEvents()


def _make_window(tmp_path):
    window = MainWindow(
        AppDataStore(tmp_path / "settings.json"),
        AppData(),
        load_exercise_catalog(),
        PostureHistoryStore(tmp_path / "history.sqlite3"),
    )
    window.break_timer.stop()
    window.history_timer.stop()
    window._exercise_postpone_timer.stop()
    return window


def _teardown_window(window, application):
    window._dismiss_side_panel()
    window._exercise_postpone_timer.stop()
    window._close_history()
    window.tray.hide()
    window.deleteLater()
    application.processEvents()


def _assert_embedded_panel(
    window: MainWindow,
    panel: QDialog,
) -> None:
    assert panel is window._side_panel
    assert window.side_panel_host.widget() is panel
    assert window.side_panel_host.isVisible()
    assert window.preview_stack.isVisible()
    assert not panel.isWindow()


def test_all_main_dialogs_use_right_side_panel(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    monkeypatch.setattr(
        ui_module,
        "discover_cameras",
        lambda: [
            CameraDescriptor(
                stable_id="test-camera",
                display_name="Test camera",
                locator=0,
            )
        ],
    )

    window._add_setup()
    application.processEvents()
    assert isinstance(window._setup_dialog, SetupDialog)
    _assert_embedded_panel(window, window._setup_dialog)
    window._setup_dialog.reject()
    application.processEvents()

    window._show_settings()
    application.processEvents()
    assert isinstance(window._settings_dialog, SettingsDialog)
    _assert_embedded_panel(window, window._settings_dialog)
    window._settings_dialog.reject()
    application.processEvents()

    window._show_evidence()
    application.processEvents()
    assert isinstance(window._evidence_dialog, EvidenceDialog)
    _assert_embedded_panel(window, window._evidence_dialog)
    window._evidence_dialog.reject()
    application.processEvents()

    window._show_workday_summary()
    application.processEvents()
    assert isinstance(window._summary_dialog, WorkdaySummaryDialog)
    _assert_embedded_panel(window, window._summary_dialog)
    window._summary_dialog.reject()
    application.processEvents()

    window._offer_exercise()
    application.processEvents()
    assert isinstance(window._exercise_dialog, ExerciseDialog)
    _assert_embedded_panel(window, window._exercise_dialog)

    _teardown_window(window, application)


def test_side_panel_has_shared_title_and_close_action(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)

    window._show_evidence()
    application.processEvents()

    assert window.side_panel_title.text() == "Evidence and safety"
    assert (
        window.side_panel_close_button.accessibleName()
        == "Close Evidence and safety"
    )

    window.side_panel_close_button.click()
    application.processEvents()

    assert window._side_panel is None
    assert window.side_panel_frame.isHidden()

    _teardown_window(window, application)


def _install_test_setup(
    window: MainWindow,
    *,
    calibration: CalibrationProfile | None,
) -> SetupProfile:
    setup = SetupProfile(
        name="Desk",
        camera=CameraDescriptor(
            stable_id="test-camera",
            display_name="Test camera",
            locator=0,
        ),
        calibration=calibration,
    )
    window.data.setups = [setup]
    window.data.active_setup_id = setup.id
    window._refresh_setup_combo()
    return setup


def test_settings_break_controls_validate_and_round_trip(
    application: QApplication,
) -> None:
    data = AppData()
    dialog = SettingsDialog(
        data.alert_policy,
        data.exercise_preferences,
        data.history_preferences,
        data.interface_language,
        break_preferences=BreakPreferences(),
    )

    assert dialog.movement_controls.isEnabled()
    assert dialog.eye_controls.isEnabled()
    dialog.movement_reminders_enabled.setChecked(False)
    assert not dialog.movement_controls.isEnabled()
    dialog.eye_interval_minutes.setValue(30)
    dialog.eye_duration_seconds.setValue(40)
    dialog._validate_and_accept()

    assert dialog.values()[0].sedentary_break_minutes == 30
    break_preferences = dialog.values()[5]
    assert not break_preferences.movement_reminders_enabled
    assert break_preferences.eye_interval_minutes == 30
    assert break_preferences.eye_duration_seconds == 40
    dialog.close()
    application.processEvents()

    data = AppData()
    invalid = SettingsDialog(
        data.alert_policy,
        data.exercise_preferences,
        data.history_preferences,
        data.interface_language,
        break_preferences=BreakPreferences(),
    )
    invalid.movement_reminders_enabled.setChecked(False)
    invalid.eye_reminders_enabled.setChecked(False)
    invalid._validate_and_accept()

    assert not invalid.feedback_label.isHidden()
    assert "Choose movement or eye reminders" in (
        invalid.feedback_label.text()
    )
    invalid.close()
    application.processEvents()


def test_combined_break_due_uses_one_movement_notification(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    _install_test_setup(window, calibration=None)
    window.data.break_preferences = BreakPreferences(
        movement_interval_minutes=20,
        movement_duration_minutes=3,
        suggest_position_change=True,
        suggest_standing=False,
        suggest_walking=False,
        suggest_guided_exercise=False,
        eye_interval_minutes=20,
    )
    messages: list[tuple[str, str]] = []
    window._show_tray_message = (
        lambda title, message, *_args: messages.append((title, message))
    )
    for _ in range(3):
        window._tracked_seconds_since_break = 20 * 60
        window._tracked_seconds_since_eye_break = 20 * 60
        window._check_break_reminders()

    assert len(messages) == 3
    assert messages[0][0] == "Time for a movement break"
    assert "Change how you are sitting for about 3 minutes" in messages[0][1]
    assert "6 m (20 ft) away" in messages[0][1]
    assert "five slow, complete blinks" in messages[1][1]
    assert "close your eyes gently" in messages[2][1]
    assert window._tracked_seconds_since_break == 0
    assert window._tracked_seconds_since_eye_break == 0
    _teardown_window(window, application)


def test_eye_only_break_uses_configured_distance_prompt(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    _install_test_setup(window, calibration=None)
    window.data.break_preferences = BreakPreferences(
        movement_reminders_enabled=False,
        eye_interval_minutes=10,
        eye_duration_seconds=30,
        suggest_blinking=False,
        suggest_closed_eye_rest=False,
    )
    messages: list[tuple[str, str]] = []
    window._show_tray_message = (
        lambda title, message, *_args: messages.append((title, message))
    )
    window._tracked_seconds_since_break = 300
    window._tracked_seconds_since_eye_break = 10 * 60

    window._check_break_reminders()

    assert messages == [
        (
            "Eye comfort break",
            (
                "Look at something about 6 m (20 ft) away for 30 seconds "
                "and let your focus relax."
            ),
        )
    ]
    assert window._tracked_seconds_since_break == 300
    assert window._tracked_seconds_since_eye_break == 0
    _teardown_window(window, application)


def test_guided_break_reuses_existing_exercise_flow(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    _install_test_setup(window, calibration=None)
    window.data.break_preferences = BreakPreferences(
        movement_interval_minutes=20,
        suggest_position_change=False,
        suggest_standing=False,
        suggest_walking=False,
        suggest_guided_exercise=True,
        eye_reminders_enabled=False,
    )
    offers: list[bool] = []
    window._offer_exercise = lambda: offers.append(True)
    window._tracked_seconds_since_break = 20 * 60

    window._check_break_reminders()

    assert offers == [True]
    _teardown_window(window, application)


def test_away_time_resets_break_counters(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window.data.break_preferences = BreakPreferences(
        away_reset_minutes=2
    )
    window._tracked_seconds_since_break = 700
    window._tracked_seconds_since_eye_break = 500
    window._tracking_gap_started_at = 100.0
    monkeypatch.setattr(
        "vulture.ui.tracking_flow.time.monotonic",
        lambda: 221.0,
    )

    window._record_valid_tracking()

    assert window._tracked_seconds_since_break == 0
    assert window._tracked_seconds_since_eye_break == 0
    assert window._tracking_gap_started_at is None
    _teardown_window(window, application)


def test_first_run_state_leads_to_camera_setup(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)

    assert window.preview_stack.currentWidget() is window.first_run_panel
    assert not window.first_run_add_button.isHidden()
    assert window.status_group.isHidden()

    _install_test_setup(window, calibration=None)

    assert window.preview_stack.currentWidget() is window.preview
    assert not window.status_group.isHidden()

    _teardown_window(window, application)


def test_main_window_size_returns_after_side_panel_closes(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    original_size = QSize(760, 650)
    window.resize(original_size)

    window._show_evidence()
    application.processEvents()

    assert window._size_before_side_panel == original_size
    assert isinstance(window._evidence_dialog, EvidenceDialog)

    window._evidence_dialog.reject()
    QTest.qWait(1)
    application.processEvents()

    assert window._side_panel is None
    assert window._size_before_side_panel is None
    assert window.size() == original_size

    _teardown_window(window, application)


def test_main_window_size_survives_side_panel_replacement(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    original_size = QSize(760, 650)
    window.resize(original_size)

    window._show_settings()
    application.processEvents()
    assert window._size_before_side_panel == original_size

    window._show_evidence()
    application.processEvents()

    assert window._settings_dialog is None
    assert isinstance(window._evidence_dialog, EvidenceDialog)
    assert window._size_before_side_panel == original_size

    window._evidence_dialog.reject()
    QTest.qWait(1)
    application.processEvents()

    assert window.size() == original_size
    assert window._size_before_side_panel is None

    _teardown_window(window, application)


@pytest.mark.parametrize(
    ("show_method", "dialog_attribute"),
    [
        ("_show_workday_summary", "_summary_dialog"),
        ("_offer_exercise", "_exercise_dialog"),
    ],
)
def test_tall_side_panels_open_without_vertical_scrollbar(
    application: QApplication,
    tmp_path: Path,
    show_method: str,
    dialog_attribute: str,
) -> None:
    window = _make_window(tmp_path)
    window.resize(760, 650)
    window.screen = lambda: SimpleNamespace(
        availableGeometry=lambda: QRect(0, 0, 1920, 1080)
    )

    getattr(window, show_method)()
    application.processEvents()

    assert getattr(window, dialog_attribute) is not None
    assert not window.side_panel_host.verticalScrollBar().isVisible()

    _teardown_window(window, application)


def test_settings_fit_without_horizontal_scroll_at_compact_width(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window.resize(760, 650)
    window.screen = lambda: SimpleNamespace(
        availableGeometry=lambda: QRect(0, 0, 800, 650)
    )

    window._show_settings()
    application.processEvents()

    assert not window.side_panel_host.horizontalScrollBar().isVisible()
    _teardown_window(window, application)


@pytest.mark.parametrize(
    "available_size",
    [(1366, 768), (800, 650)],
)
def test_workday_summary_stays_horizontally_reachable(
    application: QApplication,
    tmp_path: Path,
    available_size: tuple[int, int],
) -> None:
    window = _make_window(tmp_path)
    window.resize(760, 650)
    available_width, available_height = available_size
    window.screen = lambda: SimpleNamespace(
        availableGeometry=lambda: QRect(
            0,
            0,
            available_width,
            available_height,
        )
    )

    window._show_workday_summary()
    application.processEvents()

    panel = window._summary_dialog
    viewport = window.side_panel_host.viewport()
    assert panel is not None
    # The panel is always fully reachable horizontally: it fits the viewport
    # width and never falls back to a horizontal scrollbar.
    assert panel.width() <= viewport.width()
    assert not window.side_panel_host.horizontalScrollBar().isVisible()
    # It is never vertically clipped either: it either fits the viewport or
    # stays reachable through the vertical scrollbar. The exact height at which
    # the scrollbar appears depends on platform font and control metrics, so we
    # assert the reachability invariant rather than a fixed pixel threshold.
    fits_vertically = panel.height() <= viewport.height()
    assert (
        fits_vertically
        or window.side_panel_host.verticalScrollBar().isVisible()
    )

    _teardown_window(window, application)


def test_embedded_setup_save_transitions_to_calibration(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    camera = CameraDescriptor(
        stable_id="test-camera",
        display_name="Test camera",
        locator=0,
    )
    monkeypatch.setattr(
        ui_module,
        "discover_cameras",
        lambda: [camera],
    )
    window = _make_window(tmp_path)
    window._stop_camera = lambda *_args, **_kwargs: True
    window._activate_setup = lambda: None
    window._camera_is_healthy = lambda: True

    window._add_setup()
    application.processEvents()
    setup_panel = window._setup_dialog
    assert isinstance(setup_panel, SetupDialog)
    setup_panel.name_edit.setText("Standing desk")
    setup_panel._validate_and_accept()
    application.processEvents()

    assert len(window.data.setups) == 1
    assert window.data.setups[0].name == "Standing desk"
    assert window.data.active_setup_id == window.data.setups[0].id
    assert isinstance(window._calibration_panel, CalibrationDialog)
    _assert_embedded_panel(window, window._calibration_panel)

    window._calibration_panel.reject()
    application.processEvents()
    _teardown_window(window, application)


def test_full_calibration_is_embedded_right_of_live_preview(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    setup = _install_test_setup(window, calibration=None)
    window._camera_is_healthy = lambda: True
    window._activate_setup = lambda: None

    window._calibrate()
    application.processEvents()

    panel = window._calibration_panel
    assert isinstance(panel, CalibrationDialog)
    assert not panel.isWindow()
    assert window.workspace_splitter.widget(1) is window.side_panel_frame
    assert window.preview.isVisible()
    assert window.side_panel_host.isVisible()
    assert not window.setup_combo.isEnabled()

    profile = make_profile()
    panel.profile = profile
    panel.accept()
    application.processEvents()

    assert setup.calibration == profile
    assert not window._calibration_flow_active
    assert window.side_panel_host.isHidden()
    assert window.setup_combo.isEnabled()

    _teardown_window(window, application)


def test_recalibration_chooser_transitions_to_embedded_capture_panel(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    setup = _install_test_setup(window, calibration=make_profile())
    window._camera_is_healthy = lambda: True
    window._activate_setup = lambda: None

    window._recalibrate_step()
    application.processEvents()

    selection = window._calibration_panel
    assert isinstance(selection, CalibrationStepSelectionDialog)
    assert not selection.isWindow()
    selection.step_combo.setCurrentIndex(
        selection.step_combo.findData(
            PostureCategory.SHOULDERS_SUNK.value
        )
    )
    QTest.mouseClick(
        selection.confirm_button,
        Qt.MouseButton.LeftButton,
    )
    application.processEvents()

    capture = window._calibration_panel
    assert isinstance(capture, CalibrationDialog)
    assert not capture.isWindow()
    assert capture is window._calibration_dialog
    assert len(capture.steps) == 2
    assert capture.steps[0].category is None
    assert capture.steps[1].category is PostureCategory.SHOULDERS_SUNK
    assert window.preview.isVisible()

    capture.reject()
    application.processEvents()

    assert not window._calibration_flow_active
    assert window.side_panel_host.isHidden()
    assert setup.calibration is not None

    _teardown_window(window, application)


def test_recalibration_chooser_keeps_media_and_copy_together(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    _install_test_setup(window, calibration=make_profile())
    window._camera_is_healthy = lambda: True
    window._activate_setup = lambda: None

    window._recalibrate_step()
    application.processEvents()

    panel = window._calibration_panel
    assert isinstance(panel, CalibrationStepSelectionDialog)
    layout = panel.layout()
    spacing = layout.spacing()
    media_copy_gap = (
        panel.description.geometry().top()
        - panel.reference_image.geometry().bottom()
        - 1
    )

    assert media_copy_gap <= spacing

    panel.reject()
    application.processEvents()
    _teardown_window(window, application)


def test_calibration_reference_image_keeps_widescreen_ratio() -> None:
    image = ui_module.CalibrationStageImage()

    assert image.heightForWidth(480) == 270
    assert image.sizeHint() == QSize(480, 270)


def test_camera_error_closes_calibration_panel_without_popup(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    _install_test_setup(window, calibration=None)
    window._camera_is_healthy = lambda: True
    window._activate_setup = lambda: None
    window._calibrate()
    application.processEvents()
    assert window._calibration_panel is not None

    current_camera = object()
    window.camera_thread = current_camera
    window.sender = lambda: current_camera

    window._on_camera_error("Camera disconnected.")
    application.processEvents()

    assert window._notice_dialog is None
    assert window._state is TrackerState.CAMERA_UNAVAILABLE
    assert not window._calibration_flow_active
    assert window.side_panel_host.isHidden()

    window.camera_thread = None
    _teardown_window(window, application)


def test_language_reload_cancels_embedded_calibration(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    _install_test_setup(window, calibration=None)
    window._camera_is_healthy = lambda: True
    window._activate_setup = lambda: None
    window._calibrate()
    application.processEvents()
    assert window._calibration_flow_active

    runtime_state = window.prepare_for_language_reload()
    application.processEvents()

    assert runtime_state is not None
    assert not window._calibration_flow_active
    assert window.side_panel_host.isHidden()
    assert window._calibration_dialog is None

    window.deleteLater()
    application.processEvents()


def test_offer_exercise_opens_dialog_directly(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)

    window._offer_exercise()
    application.processEvents()

    dialog = window._exercise_dialog
    assert dialog is not None
    assert dialog.isVisible()
    _assert_embedded_panel(window, dialog)
    assert window._pending_exercise is not None
    assert window.open_exercise_action.isVisible()
    assert not window._exercise_postpone_timer.isActive()

    _teardown_window(window, application)


def test_background_exercise_waits_for_active_panel(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    original_size = QSize(760, 650)
    window.resize(original_size)
    settings = _open_settings_panel(window, application)

    window._offer_exercise()
    application.processEvents()

    assert window._settings_dialog is settings
    assert window._exercise_dialog is None
    assert window._pending_exercise is not None
    assert window.open_exercise_action.isVisible()

    settings.reject()
    application.processEvents()

    assert isinstance(window._exercise_dialog, ExerciseDialog)
    _assert_embedded_panel(window, window._exercise_dialog)
    assert window._size_before_side_panel == original_size

    window._exercise_dialog.reject()
    QTest.qWait(1)
    application.processEvents()

    assert window.size() == original_size
    assert window._size_before_side_panel is None

    _teardown_window(window, application)


def test_notice_waits_for_active_panel(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    settings = _open_settings_panel(window, application)

    window._show_notice("Saved data unavailable", "Disk is read-only.")
    application.processEvents()

    assert window._settings_dialog is settings
    assert window._notice_dialog is None
    assert window._pending_notice is not None

    settings.reject()
    application.processEvents()

    assert isinstance(window._notice_dialog, NoticeDialog)
    _assert_embedded_panel(window, window._notice_dialog)

    _close_test_window(window, application)


def test_exercise_done_button_is_leftmost(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window._offer_exercise()
    application.processEvents()
    dialog = window._exercise_dialog
    assert dialog is not None

    buttons = {
        button.text(): button for button in dialog.findChildren(QPushButton)
    }
    done_x = buttons["Done"].x()
    assert done_x < buttons["Skip"].x()
    assert done_x < buttons["Remind me later"].x()

    _teardown_window(window, application)


def test_exercise_sources_are_progressively_disclosed(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window._offer_exercise()
    application.processEvents()
    dialog = window._exercise_dialog
    assert dialog is not None

    assert dialog.details_panel.isHidden()
    dialog.details_toggle.click()
    application.processEvents()
    assert dialog.details_panel.isVisible()
    assert dialog.details_toggle.arrowType() is Qt.ArrowType.DownArrow

    _teardown_window(window, application)


def test_exercise_steps_hug_content_without_dead_space(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window._offer_exercise()
    application.processEvents()
    application.processEvents()
    dialog = window._exercise_dialog
    assert dialog is not None

    steps = dialog.findChild(ContentHeightTextBrowser)
    safety = dialog.findChild(SemanticLabel)
    assert steps is not None
    assert safety is not None

    document_height = int(steps.document().size().height())
    # The steps browser is sized to its rendered content instead of reserving
    # a fixed block, so its height tracks the document closely.
    assert steps.height() <= document_height + 12
    # The safety guidance follows immediately, without a wasted gap.
    gap = safety.mapTo(dialog, safety.rect().topLeft()).y() - (
        steps.mapTo(dialog, steps.rect().bottomLeft()).y()
    )
    assert 0 <= gap <= 16

    _teardown_window(window, application)


def test_exercise_close_returns_to_tray_when_started_hidden(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window.hide()
    application.processEvents()
    assert not window.isVisible()

    window._offer_exercise()
    application.processEvents()
    dialog = window._exercise_dialog
    assert dialog is not None
    # Presenting the exercise brings the window forward so it can be seen.
    assert window.isVisible()

    dialog.reject()
    for _ in range(4):
        application.processEvents()

    # Closing the exercise returns the window to its pre-existing tray state.
    assert not window.isVisible()

    _teardown_window(window, application)


def test_exercise_close_keeps_window_open_when_already_visible(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window.show()
    application.processEvents()
    assert window.isVisible()

    window._offer_exercise()
    application.processEvents()
    dialog = window._exercise_dialog
    assert dialog is not None

    dialog.reject()
    for _ in range(4):
        application.processEvents()

    # A window that was already open stays open after the exercise closes.
    assert window.isVisible()

    _teardown_window(window, application)


def test_warning_status_uses_dark_contrast_text(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)

    window._set_state(TrackerState.WARNING, "Warning")

    assert "color: #1a202c" in window.status_dot.styleSheet()

    _teardown_window(window, application)


def test_releasing_camera_stops_capture_until_resume(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    _install_test_setup(window, calibration=make_profile())
    stopped: list[bool] = []
    restarted: list[bool] = []
    monkeypatch.setattr(
        window,
        "_stop_camera",
        lambda *_args, **_kwargs: stopped.append(True) or True,
    )
    monkeypatch.setattr(
        window,
        "_activate_setup",
        lambda: restarted.append(True),
    )

    window._toggle_tracking()

    assert stopped == [True]
    assert not window._tracking_enabled
    assert window.pause_button.text() == "Resume tracking"
    assert "meeting apps" in window.preview.text()
    assert not window.calibrate_button.isEnabled()

    window._toggle_tracking()

    assert window._tracking_enabled
    assert restarted == [True]
    assert window.pause_button.text() == "Release camera"
    assert window.calibrate_button.isEnabled()

    _teardown_window(window, application)


def test_failed_camera_release_keeps_tracking_enabled(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    _install_test_setup(window, calibration=make_profile())
    monkeypatch.setattr(window, "_stop_camera", lambda *_args: False)

    window._toggle_tracking()
    application.processEvents()

    assert window._tracking_enabled
    assert window.pause_button.text() == "Release camera"
    assert window._state is TrackerState.CAMERA_UNAVAILABLE

    _teardown_window(window, application)


def test_paused_runtime_does_not_acquire_camera(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    setup = SetupProfile(
        name="Desk",
        camera=CameraDescriptor(
            stable_id="test-camera",
            display_name="Test camera",
            locator=0,
        ),
        calibration=make_profile(),
    )
    data = AppData(setups=[setup], active_setup_id=setup.id)
    resolutions: list[CameraDescriptor] = []
    monkeypatch.setattr(
        ui_module,
        "resolve_camera_descriptor",
        lambda camera: resolutions.append(camera) or camera,
    )

    window = MainWindow(
        AppDataStore(tmp_path / "settings.json"),
        data,
        load_exercise_catalog(),
        PostureHistoryStore(tmp_path / "history.sqlite3"),
        runtime_state=MainWindowRuntimeState(tracking_enabled=False),
    )
    window.break_timer.stop()
    window.history_timer.stop()
    window._exercise_postpone_timer.stop()

    assert resolutions == []
    assert window.camera_thread is None
    assert window.pause_button.text() == "Resume tracking"
    assert window._state is TrackerState.STOPPED

    _teardown_window(window, application)


def test_stale_preview_frames_do_not_replace_current_camera_state(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    stale_camera = object()
    current_camera = object()
    window.camera_thread = current_camera
    window.sender = lambda: stale_camera
    frame = QImage(16, 16, QImage.Format.Format_RGB888)

    window._on_preview(frame)

    assert window._latest_image is None

    window.sender = lambda: None
    window._tracking_enabled = False
    window._on_preview(frame)

    assert window._latest_image is None

    window.camera_thread = None
    _teardown_window(window, application)


def test_exercise_done_clears_pending(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window._offer_exercise()
    application.processEvents()
    dialog = window._exercise_dialog
    assert dialog is not None

    dialog._complete()
    application.processEvents()

    assert dialog.outcome == ExerciseOutcome.COMPLETED
    assert window._exercise_dialog is None
    assert window._pending_exercise is None
    assert not window.open_exercise_action.isVisible()
    assert not window._exercise_postpone_timer.isActive()

    _teardown_window(window, application)


def test_exercise_remind_me_later_reschedules(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window._offer_exercise()
    application.processEvents()
    dialog = window._exercise_dialog
    assert dialog is not None
    pending = window._pending_exercise

    dialog._postpone()
    application.processEvents()

    assert dialog.outcome == ExerciseOutcome.POSTPONED
    assert window._exercise_dialog is None
    assert window._pending_exercise is pending
    assert window.open_exercise_action.isVisible()
    assert window._exercise_postpone_timer.isActive()

    # Simulate the postpone timer firing.
    window._present_postponed_exercise()
    application.processEvents()

    reopened = window._exercise_dialog
    assert reopened is not None
    assert reopened.isVisible()
    assert window._pending_exercise is pending
    assert not window._exercise_postpone_timer.isActive()

    _teardown_window(window, application)


def test_postponed_exercise_rearms_while_tracking_is_paused(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window._offer_exercise()
    application.processEvents()
    window._exercise_dialog._postpone()
    application.processEvents()
    assert window._exercise_postpone_timer.isActive()

    window._exercise_postpone_timer.stop()
    window._tracking_enabled = False
    window._present_postponed_exercise()

    assert window._exercise_postpone_timer.isActive()
    assert window._exercise_dialog is None

    _teardown_window(window, application)


def test_window_frame_close_postpones_exercise(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window._offer_exercise()
    application.processEvents()
    dialog = window._exercise_dialog
    assert dialog is not None

    dialog.close()
    application.processEvents()

    assert window._exercise_dialog is None
    assert window._pending_exercise is not None
    assert window._exercise_postpone_timer.isActive()

    _teardown_window(window, application)


def test_exercise_skip_disregards(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window._offer_exercise()
    application.processEvents()
    dialog = window._exercise_dialog
    assert dialog is not None

    dialog._skip()
    application.processEvents()

    assert dialog.outcome == ExerciseOutcome.DISMISSED
    assert window._exercise_dialog is None
    assert window._pending_exercise is None
    assert not window.open_exercise_action.isVisible()
    assert not window._exercise_postpone_timer.isActive()

    _teardown_window(window, application)


def test_tray_activation_refocuses_open_exercise(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window._offer_exercise()
    application.processEvents()
    dialog = window._exercise_dialog
    assert dialog is not None

    window._tray_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
    application.processEvents()

    assert window._exercise_dialog is dialog
    assert window.isVisible()
    _assert_embedded_panel(window, dialog)

    _teardown_window(window, application)


def test_tray_activation_reopens_postponed_exercise(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    window._offer_exercise()
    application.processEvents()
    window._exercise_dialog._postpone()
    application.processEvents()
    assert window._exercise_dialog is None
    assert window._pending_exercise is not None

    window._tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
    application.processEvents()

    assert window._exercise_dialog is not None
    assert window._exercise_dialog.isVisible()
    _assert_embedded_panel(window, window._exercise_dialog)

    _teardown_window(window, application)


def test_offer_without_matching_exercise_shows_tray_message(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    monkeypatch.setattr(window.selector, "choose", lambda *_a, **_k: None)
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        window,
        "_show_tray_message",
        lambda title, message, *args, **kwargs: messages.append(
            (title, message)
        ),
    )

    window._offer_exercise()
    application.processEvents()

    assert window._exercise_dialog is None
    assert window._pending_exercise is None
    assert len(messages) == 1

    _teardown_window(window, application)


def _corner_alpha(icon) -> int:
    image = icon.pixmap(64, 64).toImage()
    return image.pixelColor(60, 4).alpha()


def test_state_icon_badge_marks_top_right_corner() -> None:
    assert _corner_alpha(create_state_icon(TrackerState.GOOD)) == 0
    assert _corner_alpha(create_state_icon(TrackerState.GOOD, badge=True)) > 0


def test_pending_exercise_badges_taskbar_and_tray_icons(
    application: QApplication,
    tmp_path: Path,
) -> None:
    window = _make_window(tmp_path)
    assert _corner_alpha(window.windowIcon()) == 0
    assert _corner_alpha(window.tray.icon()) == 0

    window._offer_exercise()
    application.processEvents()

    assert window._pending_exercise is not None
    assert _corner_alpha(window.windowIcon()) > 0
    assert _corner_alpha(window.tray.icon()) > 0

    # Postponing keeps the marker because the movement is still pending.
    window._exercise_dialog._postpone()
    application.processEvents()
    assert _corner_alpha(window.windowIcon()) > 0
    assert _corner_alpha(window.tray.icon()) > 0

    # Completing it clears the marker.
    window._present_postponed_exercise()
    application.processEvents()
    window._exercise_dialog._complete()
    application.processEvents()
    assert window._pending_exercise is None
    assert _corner_alpha(window.windowIcon()) == 0
    assert _corner_alpha(window.tray.icon()) == 0

    _teardown_window(window, application)
