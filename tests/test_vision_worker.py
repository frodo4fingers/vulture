from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from vulture.vision_worker import (
    VisionWorkerCrashed,
    VisionWorkerStartupError,
    VisionWorkerState,
    VisionWorkerSupervisor,
)


FAKE_WORKER = Path(__file__).parent / "helpers" / "fake_vision_worker.py"


def _command(behavior: str = "normal") -> list[str]:
    return [
        sys.executable,
        str(FAKE_WORKER),
        "--behavior",
        behavior,
    ]


def test_worker_supervisor_handshake_ping_and_shutdown() -> None:
    supervisor = VisionWorkerSupervisor(_command())

    capabilities = supervisor.start()

    assert capabilities["protocol_version"] == 1
    assert capabilities["features"] == ["ping", "shutdown"]
    assert supervisor.state is VisionWorkerState.RUNNING
    assert supervisor.pid is not None
    assert supervisor.ping() >= 0
    assert supervisor.stop()
    assert supervisor.state is VisionWorkerState.STOPPED
    assert supervisor.pid is None


def test_worker_supervisor_can_restart_after_clean_shutdown() -> None:
    supervisor = VisionWorkerSupervisor(_command())

    supervisor.start()
    assert supervisor.stop()
    supervisor.start()

    assert supervisor.ping() >= 0
    assert supervisor.stop()


def test_worker_supervisor_reports_child_crash() -> None:
    supervisor = VisionWorkerSupervisor(
        _command("crash-after-hello"),
        request_timeout_seconds=0.5,
    )
    supervisor.start()
    time.sleep(0.05)

    with pytest.raises(VisionWorkerCrashed):
        supervisor.ping()

    assert supervisor.stop()


def test_worker_supervisor_terminates_after_heartbeat_timeout() -> None:
    supervisor = VisionWorkerSupervisor(
        _command("delay-pong"),
        request_timeout_seconds=0.05,
        shutdown_timeout_seconds=0.1,
    )
    supervisor.start()

    with pytest.raises(VisionWorkerCrashed, match="heartbeat"):
        supervisor.ping()

    assert supervisor.state is VisionWorkerState.CRASHED
    assert supervisor.pid is None
    assert supervisor.stop()


def test_worker_supervisor_cleans_up_failed_startup() -> None:
    supervisor = VisionWorkerSupervisor(
        _command("hang-on-hello"),
        startup_timeout_seconds=0.1,
        shutdown_timeout_seconds=0.1,
    )

    with pytest.raises(VisionWorkerStartupError, match="CAPABILITIES"):
        supervisor.start()

    assert supervisor.state is VisionWorkerState.STOPPED
    assert supervisor.pid is None


def test_worker_supervisor_forces_hung_shutdown() -> None:
    supervisor = VisionWorkerSupervisor(
        _command("hang-on-shutdown"),
        shutdown_timeout_seconds=0.1,
    )
    supervisor.start()

    started_at = time.monotonic()
    graceful = supervisor.stop()

    assert not graceful
    assert time.monotonic() - started_at < 1.0
    assert supervisor.state is VisionWorkerState.STOPPED
    assert supervisor.pid is None


def test_worker_supervisor_rejects_nonzero_shutdown_exit() -> None:
    supervisor = VisionWorkerSupervisor(
        _command("error-on-exit"),
        shutdown_timeout_seconds=0.5,
    )
    supervisor.start()

    assert not supervisor.stop()
    assert supervisor.state is VisionWorkerState.STOPPED
    assert supervisor.pid is None
