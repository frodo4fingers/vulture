#!/usr/bin/env python3
"""Capture offscreen screenshots of Vulture's main window and its dialogs.

Usage:
    python tools/screenshot_panels.py OUTDIR [--theme light|dark|both] [--size WxH ...]

Every state saves the main window and each visible top-level QDialog to its
own PNG. All data lives in a temporary directory, so the user's real settings
and history are never read or written.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import tempfile
import traceback
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
for _path in (REPO_ROOT, REPO_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QPushButton  # noqa: E402

from vulture.autostart import AutostartManager  # noqa: E402
from vulture.breaks import BreakChannel, ManualBreakChoice  # noqa: E402
from vulture.exercises import load_exercise_catalog  # noqa: E402
from vulture.history import (  # noqa: E402
    BASELINE_POSTURE,
    ActivePostureEpisode,
    PostureHistoryStore,
)
from vulture.i18n import tr  # noqa: E402
from vulture.models import (  # noqa: E402
    AppData,
    CalibrationProfile,
    GeometryFingerprint,
    PostureCategory,
    TrackerState,
)
from vulture.storage import AppDataStore  # noqa: E402
from vulture.ui import (  # noqa: E402
    CalibrationDialog,
    CalibrationStepSelectionDialog,
    MainWindow,
)
from vulture.ui.exercises import ExerciseDialog  # noqa: E402
from vulture.ui.theme import install_control_metrics  # noqa: E402

DEFAULT_SIZES = ((1280, 760), (1024, 640))
THEMES = ("light", "dark")
SETTLE_MS = 600

DARK_ROLES = {
    QPalette.ColorRole.Window: "#171a1f",
    QPalette.ColorRole.WindowText: "#e6e9ee",
    QPalette.ColorRole.Base: "#20262d",
    QPalette.ColorRole.AlternateBase: "#272e36",
    QPalette.ColorRole.Text: "#e6e9ee",
    QPalette.ColorRole.Button: "#272e36",
    QPalette.ColorRole.ButtonText: "#e6e9ee",
    QPalette.ColorRole.Mid: "#4a535e",
    QPalette.ColorRole.PlaceholderText: "#aab1b9",
}
DARK_DISABLED_TEXT = "#6b737d"


def parse_size(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)x(\d+)", value)
    if match is None:
        raise argparse.ArgumentTypeError(f"size must look like 1280x760: {value}")
    return int(match.group(1)), int(match.group(2))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("outdir", type=Path, help="directory for the PNG files")
    parser.add_argument(
        "--theme",
        choices=("light", "dark", "both"),
        default="both",
        help="palette to use (default: both)",
    )
    parser.add_argument(
        "--size",
        type=parse_size,
        nargs="+",
        action="extend",
        metavar="WxH",
        help="window sizes (default: 1280x760 1024x640)",
    )
    args = parser.parse_args(argv)
    args.size = args.size or list(DEFAULT_SIZES)
    return args


def dark_palette(base: QPalette) -> QPalette:
    palette = QPalette(base)
    for role, value in DARK_ROLES.items():
        palette.setColor(role, QColor(value))
    # setColor fills every group; an OS dark palette dims disabled text.
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(
            QPalette.ColorGroup.Disabled, role, QColor(DARK_DISABLED_TEXT)
        )
    return palette


def seed_history(history: PostureHistoryStore, now: datetime) -> None:
    """Insert a day of episodes ending now so the summary charts have data."""
    offset_minutes = int((now.utcoffset() or timedelta(0)).total_seconds() // 60)
    postures = (
        PostureCategory.FORWARD_HEAD,
        PostureCategory.SLOUCH,
        PostureCategory.SHOULDERS_SUNK,
        PostureCategory.LATERAL_LEAN,
        PostureCategory.GENERAL_DEVIATION,
    )
    states = (TrackerState.GOOD, TrackerState.WARNING, TrackerState.ALERT)
    for index in range(10):
        started_at = now - timedelta(minutes=(10 - index) * 22)
        duration = timedelta(minutes=6 + index)
        posture = BASELINE_POSTURE if index % 3 == 0 else postures[index % len(postures)]
        history.create_episode(
            ActivePostureEpisode(
                database_id=0,
                local_date=now.date(),
                started_at=started_at,
                ended_at=started_at + duration,
                utc_offset_minutes=offset_minutes,
                setup_id="desk",
                posture=posture,
                peak_state=states[index % len(states)],
                duration_seconds=duration.total_seconds(),
                sample_count=2 + index,
            )
        )


def state_label(index: int | str) -> str:
    """Zero-pad numbered states; keep suffixed ones such as "04b" as written."""
    return str(index).zfill(2)


def seed_breaks(history: PostureHistoryStore, now: datetime) -> None:
    """Record three completed breaks for today. Caller checks record_break exists."""
    from vulture.history import BreakEvent  # noqa: PLC0415

    plan = (
        ("movement", BreakChannel.MOVEMENT, 3, 120.0),
        ("rest", BreakChannel.RESET, 2, 300.0),
        ("movement", BreakChannel.MOVEMENT, 1, 90.0),
    )
    for kind, channel, minutes_ago, seconds in plan:
        history.record_break(
            BreakEvent(
                kind=kind,
                channel=channel,
                exercise_id=None,
                completed_at=now - timedelta(minutes=minutes_ago),
                local_date=now.date(),
                duration_seconds=seconds,
            )
        )


def calibration_profile() -> CalibrationProfile:
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


def visible_dialogs(app: QApplication) -> list[QDialog]:
    return [
        widget
        for widget in app.topLevelWidgets()
        if isinstance(widget, QDialog) and widget.isVisible()
    ]


class Session:
    """One theme and size combination, run against a fresh temporary store."""

    def __init__(
        self,
        app: QApplication,
        outdir: Path,
        theme: str,
        size: tuple[int, int],
        data_dir: Path,
    ) -> None:
        self.app = app
        self.outdir = outdir
        self.theme = theme
        self.width, self.height = size
        self.data_dir = data_dir
        self.written: list[Path] = []
        self.failures: list[tuple[str, str]] = []
        # Main-window grabs of states that open a separate window: identical
        # to the previous grab by design, so the md5 check annotates them.
        self.expected_identical: set[Path] = set()
        self.window: MainWindow | None = None
        self.history: PostureHistoryStore | None = None
        self.catalog = None

    @property
    def label(self) -> str:
        return f"{self.theme}-{self.width}x{self.height}"

    def open_window(self) -> MainWindow:
        now = datetime.now().astimezone()
        history = PostureHistoryStore(self.data_dir / "history.sqlite3")
        seed_history(history, now)
        self.history = history
        self.catalog = load_exercise_catalog()
        try:
            autostart = AutostartManager(home=self.data_dir)
        except TypeError:
            autostart = None
        window = MainWindow(
            AppDataStore(self.data_dir / "settings.json"),
            AppData(),
            self.catalog,
            history,
            autostart_manager=autostart,
        )
        for name in ("break_timer", "history_timer", "_exercise_postpone_timer"):
            timer = getattr(window, name, None)
            if timer is not None:
                timer.stop()
        window.resize(self.width, self.height)
        window.show()
        self.window = window
        return window

    def capture(self, index: int | str, state: str, *, separate_window: bool = False) -> None:
        QTest.qWait(SETTLE_MS)
        self.app.processEvents()
        assert self.window is not None
        prefix = f"{self.label}-{state_label(index)}-{state}"
        main_path = self._save(self.window.grab(), prefix + ".png")
        if separate_window:
            self.expected_identical.add(main_path)
        for number, dialog in enumerate(visible_dialogs(self.app), start=1):
            self._save(dialog.grab(), f"{prefix}-window{number}.png")

    def _save(self, pixmap, filename: str) -> Path:
        path = self.outdir / filename
        if not pixmap.save(str(path)):
            raise RuntimeError(f"could not save {path}")
        self.written.append(path)
        print("ok", path.name, flush=True)
        return path

    def cleanup(self) -> None:
        window = self.window
        if window is not None:
            for name in ("_dismiss_side_panel", "_close_secondary_windows"):
                try:
                    getattr(window, name)()
                except Exception:
                    traceback.print_exc()
        for dialog in visible_dialogs(self.app):
            dialog.close()
        self.app.processEvents()
        QTest.qWait(100)

    def run_state(
        self,
        index: int | str,
        state: str,
        action: Callable[[], None] | None,
        *,
        separate_window: bool = False,
    ) -> None:
        try:
            if action is not None:
                action()
            self.capture(index, state, separate_window=separate_window)
        except Exception as exc:
            traceback.print_exc()
            self.failures.append(
                (f"{state_label(index)}-{state}", f"{type(exc).__name__}: {exc}")
            )
        finally:
            try:
                self.cleanup()
            except Exception:
                traceback.print_exc()

    def run_standalone(
        self, index: int | str, state: str, make: Callable[[], QDialog]
    ) -> None:
        dialog: QDialog | None = None

        def action() -> None:
            nonlocal dialog
            dialog = make()
            dialog.show()

        self.run_state(index, state, action, separate_window=True)
        if dialog is not None:
            dialog.close()

    def run(self) -> None:
        window = self.open_window()
        assert window is not None
        self.run_state(1, "first-run", None)
        self.run_state(2, "add-setup", window._add_setup)
        self.run_state(3, "settings", window._show_settings, separate_window=True)
        self.run_state(
            "03b",
            "settings-breaks",
            self._present_settings_breaks,
            separate_window=True,
        )
        self.run_state(4, "summary", window._show_workday_summary, separate_window=True)
        if hasattr(PostureHistoryStore, "record_break"):
            self.run_state(
                "04b",
                "summary-breaks",
                self._show_summary_with_breaks,
                separate_window=True,
            )
        else:
            print("note: PostureHistoryStore.record_break missing, skipping 04b-summary-breaks")
        self.run_state(5, "evidence", window._show_evidence, separate_window=True)
        self.run_state(
            6, "exercise-break", self._present_first_exercise, separate_window=True
        )
        self.run_state(
            "06b", "exercise-running", self._present_running_exercise, separate_window=True
        )
        self.run_state(
            7,
            "rest-break",
            lambda: window._present_manual_break(ManualBreakChoice.STAND),
            separate_window=True,
        )
        self.run_standalone(8, "calibration-capture", CalibrationDialog)
        self.run_standalone(
            "08b", "calibration-recording", self._present_calibration_recording
        )
        self.run_standalone(
            9,
            "calibration-select",
            lambda: CalibrationStepSelectionDialog(calibration_profile()),
        )
        try:
            if window.tray is not None:
                window.tray.hide()
        except Exception:
            pass
        window.close()
        self.app.processEvents()

    def _present_first_exercise(self) -> None:
        assert self.window is not None and self.catalog is not None
        self.window._pending_exercise = self.catalog.exercises[0]
        self.window._present_exercise()

    def _present_running_exercise(self) -> None:
        self._present_first_exercise()
        # The break dialog lives in the side panel, so it is not a top-level window.
        assert self.window is not None
        dialogs = [d for d in self.window.findChildren(ExerciseDialog) if d.isVisible()]
        assert dialogs, "exercise dialog is not visible"
        dialog = dialogs[0]
        button = getattr(dialog, "start_button", None) or next(
            b
            for b in dialog.findChildren(QPushButton)
            if b.isVisible() and b.text().replace("&", "") == "Start"
        )
        button.click()
        QTest.qWait(1200)

    def _show_summary_with_breaks(self) -> None:
        assert self.window is not None and self.history is not None
        seed_breaks(self.history, datetime.now().astimezone())
        self.window._show_workday_summary()

    def _present_settings_breaks(self) -> None:
        assert self.window is not None
        self.window._show_settings()
        dialog = self.window._settings_dialog
        assert dialog is not None, "settings dialog did not open"
        for index in range(dialog.tabs.count()):
            if dialog.tabs.tabText(index).replace("&", "") == tr("Breaks"):
                dialog.tabs.setCurrentIndex(index)
                return
        raise AssertionError("Breaks tab not found")

    def _present_calibration_recording(self) -> CalibrationDialog:
        dialog = CalibrationDialog()
        dialog.timer.stop()
        dialog._start_sample()
        # Countdown is over: the capture phase shows the recording bar.
        dialog._deadline = 0.0
        dialog._tick()
        return dialog


def report(
    written: list[Path],
    failures: list[tuple[str, str]],
    expected_identical: set[Path],
) -> None:
    by_hash: dict[str, list[Path]] = defaultdict(list)
    print("\nmd5 summary:")
    for path in sorted(written):
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        by_hash[digest].append(path)
        print(f"{digest}  {path.name}")
    for paths in by_hash.values():
        expected = [p for p in paths if p in expected_identical]
        unexpected = [p for p in paths if p not in expected_identical]
        if len(expected) > 1:
            names = ", ".join(p.name for p in expected)
            print(f"NOTE identical main-window grabs (state opens a separate window): {names}")
        if len(unexpected) > 1:
            names = ", ".join(p.name for p in unexpected)
            print(f"WARN identical files: {names}")
    print(f"\n{len(written)} files written, {len(failures)} states failed")
    for state, error in failures:
        print(f"FAILED {state}: {error}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    outdir: Path = args.outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    themes = THEMES if args.theme == "both" else (args.theme,)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    install_control_metrics(app)
    default_palette = QPalette(app.palette())
    written: list[Path] = []
    failures: list[tuple[str, str]] = []
    expected_identical: set[Path] = set()

    for theme in themes:
        palette = dark_palette(default_palette) if theme == "dark" else default_palette
        app.setPalette(palette)
        for width, height in args.size:
            with tempfile.TemporaryDirectory(prefix="vulture-shots-") as tmp:
                # Keep every store and autostart path inside the temp dir.
                os.environ["VULTURE_DATA_DIR"] = tmp
                session = Session(app, outdir, theme, (width, height), Path(tmp))
                try:
                    session.run()
                except Exception as exc:
                    traceback.print_exc()
                    session.failures.append(("session", f"{type(exc).__name__}: {exc}"))
                finally:
                    written.extend(session.written)
                    expected_identical.update(session.expected_identical)
                    failures.extend(
                        (f"{session.label} {state}", error)
                        for state, error in session.failures
                    )
                    if session.window is not None:
                        session.window.deleteLater()
                    app.processEvents()
    app.setPalette(default_palette)

    report(written, failures, expected_identical)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
