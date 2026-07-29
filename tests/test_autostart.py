from __future__ import annotations

import os
import plistlib
import stat
import subprocess
from pathlib import Path

import pytest

from vulture.autostart import (
    APP_ID,
    START_MINIMIZED_FLAG,
    WINDOWS_RUN_COMMAND_LIMIT,
    WINDOWS_RUN_KEY,
    WINDOWS_VALUE_NAME,
    AutostartError,
    AutostartManager,
    current_launch_command,
)


class _FakeRegistryKey:
    def __init__(self, path: str) -> None:
        self.path = path

    def __enter__(self) -> _FakeRegistryKey:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _FakeRegistry:
    HKEY_CURRENT_USER = object()
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self) -> None:
        self.keys: set[str] = set()
        self.values: dict[tuple[str, str], tuple[str, int]] = {}

    def OpenKey(
        self,
        _root: object,
        path: str,
        _reserved: int,
        _access: int,
    ) -> _FakeRegistryKey:
        if path not in self.keys:
            raise FileNotFoundError(path)
        return _FakeRegistryKey(path)

    def CreateKeyEx(
        self,
        _root: object,
        path: str,
        _reserved: int,
        _access: int,
    ) -> _FakeRegistryKey:
        self.keys.add(path)
        return _FakeRegistryKey(path)

    def QueryValueEx(
        self,
        key: _FakeRegistryKey,
        name: str,
    ) -> tuple[str, int]:
        try:
            return self.values[(key.path, name)]
        except KeyError as error:
            raise FileNotFoundError(name) from error

    def SetValueEx(
        self,
        key: _FakeRegistryKey,
        name: str,
        _reserved: int,
        value_type: int,
        value: str,
    ) -> None:
        self.values[(key.path, name)] = (value, value_type)

    def DeleteValue(self, key: _FakeRegistryKey, name: str) -> None:
        try:
            del self.values[(key.path, name)]
        except KeyError as error:
            raise FileNotFoundError(name) from error


def test_default_autostart_command_starts_minimized(tmp_path: Path) -> None:
    manager = AutostartManager(platform_name="linux", home=tmp_path)

    assert manager.command[-1] == START_MINIMIZED_FLAG
    assert current_launch_command(platform_name="linux")[-1:] != (
        START_MINIMIZED_FLAG,
    )


def test_current_launch_command_covers_source_console_and_frozen(
    tmp_path: Path,
) -> None:
    python = tmp_path / "python3"
    console_script = tmp_path / "vulture"
    windows_executable = (
        tmp_path / "Program Files" / "Vulture" / "Vulture.exe"
    )
    macos_bundle = tmp_path / "Vulture.app"
    macos_executable = macos_bundle / "Contents" / "MacOS" / "Vulture"

    assert current_launch_command(
        platform_name="linux",
        executable=str(python),
        argv=[str(tmp_path / "src" / "vulture" / "__main__.py")],
        frozen=False,
    ) == (str(python), "-m", "vulture")
    assert current_launch_command(
        platform_name="win32",
        executable=str(windows_executable),
        frozen=True,
    ) == (str(windows_executable),)
    assert current_launch_command(
        platform_name="darwin",
        executable=str(macos_executable),
        frozen=True,
    ) == ("/usr/bin/open", str(macos_bundle))
    assert current_launch_command(
        platform_name="linux",
        executable=str(python),
        argv=[str(console_script)],
        frozen=False,
    ) == (str(console_script.resolve()),)


def test_windows_source_autostart_uses_pythonw(
    tmp_path: Path,
) -> None:
    python = tmp_path / "python.exe"
    pythonw = tmp_path / "pythonw.exe"
    python.touch()
    pythonw.touch()

    assert current_launch_command(
        platform_name="win32",
        executable=str(python),
        argv=[str(tmp_path / "vulture.exe")],
        frozen=False,
    ) == (str(pythonw), "-m", "vulture")


def test_linux_autostart_uses_xdg_registration(tmp_path: Path) -> None:
    config_home = tmp_path / "configuration"
    command = (
        "/opt/Vulture App/Vulture",
        "--desk",
        '100%-$HOME-C:\\Desk "A"',
    )
    manager = AutostartManager(
        platform_name="linux",
        command=command,
        home=tmp_path,
        environment={"XDG_CONFIG_HOME": str(config_home)},
    )

    assert not manager.is_enabled()
    manager.set_enabled(True)

    registration = (
        config_home / "autostart" / f"{APP_ID}.desktop"
    )
    content = registration.read_text(encoding="utf-8")
    assert (
        'Exec="/opt/Vulture App/Vulture" "--desk" '
        '"100%%-\\\\$HOME-C:\\\\\\\\Desk \\\\"A\\\\""'
        in content
    )
    if os.name != "nt":
        assert stat.S_IMODE(registration.stat().st_mode) == 0o600
    assert manager.is_enabled()

    registration.write_text(
        content.replace(
            'Exec="/opt/Vulture App/Vulture"',
            'Exec="/old/Vulture"',
        ),
        encoding="utf-8",
    )
    stale_content = registration.read_bytes()
    snapshot = manager.snapshot()
    assert snapshot.exists
    assert not snapshot.enabled
    manager.set_enabled(False)
    manager.restore(snapshot)
    assert registration.read_bytes() == stale_content

    registration.write_text(
        content + "OnlyShowIn=OtherDesktop;\n",
        encoding="utf-8",
    )
    assert not manager.is_enabled()

    registration.write_text(
        content.replace("Hidden=false", "Hidden=true"),
        encoding="utf-8",
    )
    assert not manager.is_enabled()

    registration.write_text(
        content.replace("Hidden=false", "Hidden=invalid"),
        encoding="utf-8",
    )
    assert not manager.is_enabled()

    manager.set_enabled(False)
    assert not registration.exists()
    assert not manager.is_enabled()


def test_linux_autostart_ignores_relative_xdg_path(
    tmp_path: Path,
) -> None:
    manager = AutostartManager(
        platform_name="linux",
        command=("/opt/Vulture",),
        home=tmp_path,
        environment={"XDG_CONFIG_HOME": "relative"},
    )

    manager.set_enabled(True)

    assert (
        tmp_path
        / ".config"
        / "autostart"
        / f"{APP_ID}.desktop"
    ).is_file()


def test_macos_autostart_uses_launch_agent(tmp_path: Path) -> None:
    command = ("/usr/bin/open", "/Applications/Vulture.app")
    manager = AutostartManager(
        platform_name="darwin",
        command=command,
        home=tmp_path,
    )

    assert not manager.is_enabled()
    manager.set_enabled(True)

    registration = (
        tmp_path / "Library" / "LaunchAgents" / f"{APP_ID}.plist"
    )
    with registration.open("rb") as handle:
        payload = plistlib.load(handle)
    assert payload["Label"] == APP_ID
    assert payload["ProgramArguments"] == list(command)
    assert payload["RunAtLoad"] is True
    assert payload["LimitLoadToSessionType"] == "Aqua"
    if os.name != "nt":
        assert stat.S_IMODE(registration.stat().st_mode) == 0o600
    assert manager.is_enabled()

    disabled_payload = dict(payload, Disabled=True)
    with registration.open("wb") as handle:
        plistlib.dump(disabled_payload, handle)
    assert not manager.is_enabled()

    payload["ProgramArguments"] = ["/Applications/Old Vulture.app"]
    with registration.open("wb") as handle:
        plistlib.dump(payload, handle)
    stale_content = registration.read_bytes()
    snapshot = manager.snapshot()
    assert snapshot.exists
    assert not snapshot.enabled
    manager.set_enabled(False)
    manager.restore(snapshot)
    assert registration.read_bytes() == stale_content

    registration.write_bytes(b"<plist><dict>")
    malformed_snapshot = manager.snapshot()
    assert malformed_snapshot.exists
    assert not malformed_snapshot.enabled

    manager.set_enabled(False)
    assert not registration.exists()
    assert not manager.is_enabled()


def test_windows_autostart_uses_current_user_run_key() -> None:
    registry = _FakeRegistry()
    command = (r"C:\Program Files\Vulture\Vulture.exe", "--quiet")
    manager = AutostartManager(
        platform_name="win32",
        command=command,
        registry_module=registry,
    )

    assert not manager.is_enabled()
    manager.set_enabled(True)

    assert registry.values[(WINDOWS_RUN_KEY, WINDOWS_VALUE_NAME)] == (
        subprocess.list2cmdline(list(command)),
        registry.REG_SZ,
    )
    assert manager.is_enabled()

    registry.values[(WINDOWS_RUN_KEY, WINDOWS_VALUE_NAME)] = (
        "other-command.exe",
        registry.REG_SZ,
    )
    snapshot = manager.snapshot()
    assert snapshot.exists
    assert not snapshot.enabled
    manager.set_enabled(False)
    manager.restore(snapshot)
    assert registry.values[(WINDOWS_RUN_KEY, WINDOWS_VALUE_NAME)] == (
        "other-command.exe",
        registry.REG_SZ,
    )

    manager.set_enabled(False)
    assert not manager.is_enabled()


def test_windows_autostart_rejects_overlong_run_command() -> None:
    manager = AutostartManager(
        platform_name="win32",
        command=("x" * (WINDOWS_RUN_COMMAND_LIMIT + 1),),
        registry_module=_FakeRegistry(),
    )

    with pytest.raises(AutostartError, match="longer"):
        manager.set_enabled(True)


@pytest.mark.parametrize("command", [("",), ("bad\0command",)])
def test_invalid_startup_commands_are_rejected(
    command: tuple[str, ...],
) -> None:
    with pytest.raises(AutostartError, match="invalid"):
        AutostartManager(platform_name="linux", command=command)


@pytest.mark.parametrize(
    "command",
    [
        ("/opt/Vulture", "line\nbreak"),
        ("/opt/Vulture=invalid",),
    ],
)
def test_invalid_linux_desktop_commands_are_rejected(
    command: tuple[str, ...],
    tmp_path: Path,
) -> None:
    manager = AutostartManager(
        platform_name="linux",
        command=command,
        home=tmp_path,
        environment={},
    )

    with pytest.raises(AutostartError):
        manager.set_enabled(True)


def test_unsupported_platform_surfaces_an_error() -> None:
    manager = AutostartManager(
        platform_name="freebsd",
        command=("/opt/Vulture",),
    )

    assert not manager.is_supported
    with pytest.raises(AutostartError, match="not supported"):
        manager.is_enabled()
    with pytest.raises(AutostartError, match="not supported"):
        manager.set_enabled(True)
