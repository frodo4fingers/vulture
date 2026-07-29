import sys
from types import ModuleType

from vulture.camera import discover_cameras, resolve_camera_descriptor

from . import calibration as _calibration_module
from . import shell as _shell_module
from .calibration import (
    CALIBRATION_STEPS,
    POSTURE_STEPS,
    CalibrationDialog,
    CalibrationStageImage,
    CalibrationStep,
    CalibrationStepSelectionDialog,
    SetupDialog,
)
from .common import (
    EXERCISE_BADGE_COLOR,
    POSTURE_TITLES,
    SEMANTIC_PANEL_COLORS,
    STATE_COLORS,
    STATE_FOREGROUND_COLORS,
    SUMMARY_POSTURES,
    SemanticLabel,
    create_state_icon,
    format_duration,
    semantic_panel_style,
    set_accessible_link_palette,
)
from .exercises import (
    EXERCISE_POSTPONE_MINUTES,
    EvidenceDialog,
    ExerciseDialog,
    ExerciseOutcome,
)
from .main_window import MainWindow, MainWindowRuntimeState
from .notices import NoticeDialog
from .settings import SettingsDialog
from .summary import (
    REMINDER_STAGE_TITLES,
    SUMMARY_CHART_BUCKET_SECONDS,
    SUMMARY_POSTURE_PALETTES,
    PostureAreaChart,
    PostureAreaData,
    PostureProgressBar,
    RollingWeekChart,
    RollingWeekData,
    SummaryMetric,
    build_posture_area_data,
    build_rolling_week_data,
    summary_posture_color,
)
from .summary_dialog import WorkdaySummaryDialog

__all__ = [
    "CALIBRATION_STEPS",
    "EXERCISE_BADGE_COLOR",
    "EXERCISE_POSTPONE_MINUTES",
    "POSTURE_STEPS",
    "POSTURE_TITLES",
    "REMINDER_STAGE_TITLES",
    "SEMANTIC_PANEL_COLORS",
    "STATE_COLORS",
    "STATE_FOREGROUND_COLORS",
    "SUMMARY_CHART_BUCKET_SECONDS",
    "SUMMARY_POSTURES",
    "SUMMARY_POSTURE_PALETTES",
    "CalibrationDialog",
    "CalibrationStageImage",
    "CalibrationStep",
    "CalibrationStepSelectionDialog",
    "EvidenceDialog",
    "ExerciseDialog",
    "ExerciseOutcome",
    "MainWindow",
    "MainWindowRuntimeState",
    "NoticeDialog",
    "PostureAreaChart",
    "PostureAreaData",
    "PostureProgressBar",
    "RollingWeekChart",
    "RollingWeekData",
    "SemanticLabel",
    "SettingsDialog",
    "SetupDialog",
    "SummaryMetric",
    "WorkdaySummaryDialog",
    "build_posture_area_data",
    "build_rolling_week_data",
    "create_state_icon",
    "discover_cameras",
    "format_duration",
    "resolve_camera_descriptor",
    "semantic_panel_style",
    "set_accessible_link_palette",
    "summary_posture_color",
]


class _UIFacadeModule(ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        if name == "discover_cameras":
            _calibration_module.discover_cameras = value
        elif name == "resolve_camera_descriptor":
            _shell_module.resolve_camera_descriptor = value


# Preserve the injection points exposed by the former single-file module.
sys.modules[__name__].__class__ = _UIFacadeModule
