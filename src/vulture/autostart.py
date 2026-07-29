from __future__ import annotations

import configparser
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.parsers.expat import ExpatError

try:
    import winreg as _winreg
except ImportError:  # pragma: no cover - unavailable outside Windows
    _winreg = None


APP_ID = "org.vulture.posture"
WINDOWS_VALUE_NAME = "Vulture"
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WINDOWS_RUN_COMMAND_LIMIT = 260
# Passed to the app by the autostart registration so a login launch starts
# tracking in the background (system tray only) without showing the window.
START_MINIMIZED_FLAG = "--minimized"


class AutostartError(RuntimeError):
    """Raised when the system startup registration cannot be read or changed."""


@dataclass(frozen=True)
class AutostartSnapshot:
    platform_name: str
    exists: bool
    enabled: bool
    payload: object | None = None
    value_type: int | None = None
    mode: int | None = None


def current_launch_command(
    *,
    platform_name: str | None = None,
    executable: str | None = None,
    argv: Sequence[str] | None = None,
    frozen: bool | None = None,
) -> tuple[str, ...]:
    platform_name = platform_name or sys.platform
    executable_path = Path(executable or sys.executable)
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen

    if frozen:
        if platform_name == "darwin":
            app_bundle = next(
                (
                    parent
                    for parent in executable_path.parents
                    if parent.suffix.lower() == ".app"
                ),
                None,
            )
            if app_bundle is not None:
                return ("/usr/bin/open", str(app_bundle))
        return (str(executable_path),)

    if platform_name == "win32":
        gui_executable = executable_path.with_name("pythonw.exe")
        return (
            str(gui_executable if gui_executable.is_file() else executable_path),
            "-m",
            "vulture",
        )

    arguments = tuple(sys.argv if argv is None else argv)
    launcher = Path(arguments[0]) if arguments else Path()
    if launcher.name.lower() in {"vulture", "vulture.exe"}:
        resolved = shutil.which(str(launcher))
        return (str(Path(resolved).resolve()) if resolved else str(launcher.resolve()),)

    return (str(executable_path), "-m", "vulture")


class AutostartManager:
    def __init__(
        self,
        *,
        platform_name: str | None = None,
        command: Sequence[str] | None = None,
        home: Path | None = None,
        environment: Mapping[str, str] | None = None,
        registry_module: Any | None = None,
    ) -> None:
        self.platform_name = platform_name or sys.platform
        default_command = (
            *current_launch_command(platform_name=self.platform_name),
            START_MINIMIZED_FLAG,
        )
        self.command = tuple(
            str(part)
            for part in (command or default_command)
        )
        if (
            not self.command
            or not self.command[0].strip()
            or any("\0" in part for part in self.command)
        ):
            raise AutostartError("The startup command is invalid.")
        self.home = Path.home() if home is None else Path(home)
        self.environment = dict(
            os.environ if environment is None else environment
        )
        self._registry = (
            _winreg if registry_module is None else registry_module
        )

    @property
    def is_supported(self) -> bool:
        return self.platform_name in {"linux", "darwin", "win32"}

    def is_enabled(self) -> bool:
        return self.snapshot().enabled

    def snapshot(self) -> AutostartSnapshot:
        if not self.is_supported:
            raise AutostartError(
                f"Startup registration is not supported on {self.platform_name}."
            )
        try:
            if self.platform_name == "linux":
                return self._linux_snapshot()
            if self.platform_name == "darwin":
                return self._macos_snapshot()
            return self._windows_snapshot()
        except AutostartError:
            raise
        except OSError as error:
            raise AutostartError(str(error)) from error

    def restore(self, snapshot: AutostartSnapshot) -> None:
        if snapshot.platform_name != self.platform_name:
            raise AutostartError(
                "The startup snapshot belongs to a different platform."
            )
        try:
            if self.platform_name == "linux":
                self._restore_file(self._linux_path(), snapshot)
            elif self.platform_name == "darwin":
                self._restore_file(self._macos_path(), snapshot)
            elif self.platform_name == "win32":
                self._windows_restore(snapshot)
            else:
                raise AutostartError(
                    "Startup registration is not supported on "
                    f"{self.platform_name}."
                )
        except AutostartError:
            raise
        except OSError as error:
            raise AutostartError(str(error)) from error

    def set_enabled(self, enabled: bool) -> None:
        if not self.is_supported:
            raise AutostartError(
                f"Startup registration is not supported on {self.platform_name}."
            )
        try:
            if self.platform_name == "linux":
                self._linux_set_enabled(enabled)
            elif self.platform_name == "darwin":
                self._macos_set_enabled(enabled)
            else:
                self._windows_set_enabled(enabled)
        except AutostartError:
            raise
        except OSError as error:
            raise AutostartError(str(error)) from error

    def _linux_path(self) -> Path:
        configured = self.environment.get("XDG_CONFIG_HOME")
        config_home = Path(configured).expanduser() if configured else None
        if config_home is None or not config_home.is_absolute():
            config_home = self.home / ".config"
        return config_home / "autostart" / f"{APP_ID}.desktop"

    def _linux_exec(self) -> str:
        if "=" in self.command[0]:
            raise AutostartError(
                "Linux startup executable paths cannot contain an equals sign."
            )
        return " ".join(_desktop_exec_argument(part) for part in self.command)

    def _linux_snapshot(self) -> AutostartSnapshot:
        path = self._linux_path()
        try:
            payload = path.read_bytes()
            mode = stat.S_IMODE(path.stat().st_mode)
        except FileNotFoundError:
            return AutostartSnapshot(self.platform_name, False, False)

        enabled = False
        try:
            content = payload.decode("utf-8")
        except UnicodeError:
            pass
        else:
            parser = configparser.ConfigParser(interpolation=None)
            parser.optionxform = str
            try:
                parser.read_string(content)
                entry = parser["Desktop Entry"]
                hidden = entry.getboolean("Hidden", fallback=False)
                desktop_enabled = entry.getboolean(
                    "X-GNOME-Autostart-enabled",
                    fallback=True,
                )
                enabled = (
                    entry.get("Type") == "Application"
                    and entry.get("Exec") == self._linux_exec()
                    and not any(
                        key in entry
                        for key in (
                            "OnlyShowIn",
                            "NotShowIn",
                            "TryExec",
                        )
                    )
                    and not hidden
                    and desktop_enabled
                )
            except (
                AutostartError,
                configparser.Error,
                KeyError,
                ValueError,
            ):
                pass
        return AutostartSnapshot(
            self.platform_name,
            True,
            enabled,
            payload=payload,
            mode=mode,
        )

    def _linux_set_enabled(self, enabled: bool) -> None:
        path = self._linux_path()
        if not enabled:
            path.unlink(missing_ok=True)
            return

        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Version=1.0\n"
            "Name=Vulture\n"
            f"Exec={self._linux_exec()}\n"
            "Terminal=false\n"
            "Hidden=false\n"
            "X-GNOME-Autostart-enabled=true\n"
        )
        _atomic_write(path, content.encode("utf-8"))

    def _macos_path(self) -> Path:
        return self.home / "Library" / "LaunchAgents" / f"{APP_ID}.plist"

    def _macos_snapshot(self) -> AutostartSnapshot:
        path = self._macos_path()
        try:
            payload = path.read_bytes()
            mode = stat.S_IMODE(path.stat().st_mode)
        except FileNotFoundError:
            return AutostartSnapshot(self.platform_name, False, False)

        enabled = False
        try:
            registration = plistlib.loads(payload)
        except (ExpatError, plistlib.InvalidFileException, ValueError):
            pass
        else:
            enabled = (
                isinstance(registration, dict)
                and registration.get("Label") == APP_ID
                and registration.get("ProgramArguments")
                == list(self.command)
                and registration.get("RunAtLoad") is True
                and registration.get("LimitLoadToSessionType") == "Aqua"
                and registration.get("ProcessType") == "Interactive"
                and registration.get("Disabled") is not True
            )
        return AutostartSnapshot(
            self.platform_name,
            True,
            enabled,
            payload=payload,
            mode=mode,
        )

    def _macos_set_enabled(self, enabled: bool) -> None:
        path = self._macos_path()
        if not enabled:
            path.unlink(missing_ok=True)
            return

        registration = {
            "Label": APP_ID,
            "LimitLoadToSessionType": "Aqua",
            "ProcessType": "Interactive",
            "ProgramArguments": list(self.command),
            "RunAtLoad": True,
        }
        _atomic_write(
            path,
            plistlib.dumps(
                registration,
                fmt=plistlib.FMT_XML,
                sort_keys=True,
            ),
        )

    def _windows_command(self) -> str:
        command = subprocess.list2cmdline(list(self.command))
        if len(command) > WINDOWS_RUN_COMMAND_LIMIT:
            raise AutostartError(
                "The Windows startup command is longer than the supported "
                f"{WINDOWS_RUN_COMMAND_LIMIT} characters."
            )
        return command

    def _windows_registry(self) -> Any:
        if self._registry is None:
            raise AutostartError(
                "The Windows registry API is unavailable."
            )
        return self._registry

    def _windows_snapshot(self) -> AutostartSnapshot:
        registry = self._windows_registry()
        try:
            with registry.OpenKey(
                registry.HKEY_CURRENT_USER,
                WINDOWS_RUN_KEY,
                0,
                registry.KEY_READ,
            ) as key:
                value, value_type = registry.QueryValueEx(
                    key,
                    WINDOWS_VALUE_NAME,
                )
        except FileNotFoundError:
            return AutostartSnapshot(self.platform_name, False, False)

        try:
            expected_command = self._windows_command()
        except AutostartError:
            enabled = False
        else:
            enabled = (
                value_type == registry.REG_SZ
                and value == expected_command
            )
        return AutostartSnapshot(
            self.platform_name,
            True,
            enabled,
            payload=value,
            value_type=value_type,
        )

    def _windows_set_enabled(self, enabled: bool) -> None:
        registry = self._windows_registry()
        if enabled:
            with registry.CreateKeyEx(
                registry.HKEY_CURRENT_USER,
                WINDOWS_RUN_KEY,
                0,
                registry.KEY_SET_VALUE,
            ) as key:
                registry.SetValueEx(
                    key,
                    WINDOWS_VALUE_NAME,
                    0,
                    registry.REG_SZ,
                    self._windows_command(),
                )
            return

        try:
            with registry.OpenKey(
                registry.HKEY_CURRENT_USER,
                WINDOWS_RUN_KEY,
                0,
                registry.KEY_SET_VALUE,
            ) as key:
                registry.DeleteValue(key, WINDOWS_VALUE_NAME)
        except FileNotFoundError:
            return

    def _windows_restore(self, snapshot: AutostartSnapshot) -> None:
        registry = self._windows_registry()
        if not snapshot.exists:
            self._windows_set_enabled(False)
            return
        if snapshot.value_type is None:
            raise AutostartError(
                "The Windows startup snapshot is incomplete."
            )
        with registry.CreateKeyEx(
            registry.HKEY_CURRENT_USER,
            WINDOWS_RUN_KEY,
            0,
            registry.KEY_SET_VALUE,
        ) as key:
            registry.SetValueEx(
                key,
                WINDOWS_VALUE_NAME,
                0,
                snapshot.value_type,
                snapshot.payload,
            )

    @staticmethod
    def _restore_file(
        path: Path,
        snapshot: AutostartSnapshot,
    ) -> None:
        if not snapshot.exists:
            path.unlink(missing_ok=True)
            return
        if not isinstance(snapshot.payload, bytes):
            raise AutostartError(
                "The startup file snapshot is incomplete."
            )
        _atomic_write(
            path,
            snapshot.payload,
            mode=(
                snapshot.mode
                if snapshot.mode is not None
                else 0o600
            ),
        )


def _desktop_exec_argument(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise AutostartError(
            "Linux startup commands cannot contain line breaks."
        )
    escaped = (
        value.replace("\\", r"\\\\")
        .replace('"', r'\\"')
        .replace("`", r"\\`")
        .replace("$", r"\\$")
        .replace("%", "%%")
    )
    return f'"{escaped}"'


def _atomic_write(
    path: Path,
    payload: bytes,
    *,
    mode: int = 0o600,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            os.chmod(temporary_path, mode)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
