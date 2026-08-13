from __future__ import annotations

import queue
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import BinaryIO

from vulture.vision_worker_protocol import (
    MessageType,
    WorkerMessage,
    WorkerProtocolError,
    decode_json_payload,
    encode_json_payload,
    encode_message,
    new_message,
    read_message,
)


class VisionWorkerError(RuntimeError):
    pass


class VisionWorkerStartupError(VisionWorkerError):
    pass


class VisionWorkerCrashed(VisionWorkerError):
    pass


class VisionWorkerTimeout(VisionWorkerError):
    pass


class VisionWorkerState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    CRASHED = "crashed"
    STOPPING = "stopping"


_END_OF_STREAM = object()


class VisionWorkerSupervisor:
    def __init__(
        self,
        command: Sequence[str | Path],
        *,
        startup_timeout_seconds: float = 3.0,
        request_timeout_seconds: float = 1.0,
        shutdown_timeout_seconds: float = 1.0,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if not command:
            raise ValueError("The vision worker command cannot be empty.")
        self.command = tuple(str(item) for item in command)
        self.startup_timeout_seconds = startup_timeout_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.shutdown_timeout_seconds = shutdown_timeout_seconds
        self.environment = dict(environment) if environment is not None else None
        self.state = VisionWorkerState.STOPPED
        self.capabilities: dict[str, object] = {}
        self._process: subprocess.Popen[bytes] | None = None
        self._messages: queue.Queue[WorkerMessage | object] = queue.Queue()
        self._reader_error: WorkerProtocolError | OSError | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr = bytearray()
        self._stderr_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._next_sequence = 1

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process is not None else None

    @property
    def stderr_text(self) -> str:
        with self._stderr_lock:
            return bytes(self._stderr).decode("utf-8", errors="replace")

    def start(self) -> dict[str, object]:
        if self.state is not VisionWorkerState.STOPPED:
            raise VisionWorkerError("The vision worker is already active.")
        self._messages = queue.Queue()
        self._reader_error = None
        self._next_sequence = 1
        with self._stderr_lock:
            self._stderr.clear()
        self.state = VisionWorkerState.STARTING
        try:
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.environment,
                bufsize=0,
            )
            self._start_reader_threads()
            sequence = self._send(
                MessageType.HELLO,
                encode_json_payload(
                    {
                        "client": "vulture",
                        "protocol_version": 1,
                    }
                ),
            )
            response = self._wait_for(
                MessageType.CAPABILITIES,
                sequence,
                self.startup_timeout_seconds,
            )
            self.capabilities = decode_json_payload(response.payload)
            self.state = VisionWorkerState.RUNNING
            return dict(self.capabilities)
        except (
            OSError,
            VisionWorkerError,
            WorkerProtocolError,
        ) as error:
            self._terminate_process()
            self._finish_process()
            self.state = VisionWorkerState.STOPPED
            raise VisionWorkerStartupError(
                f"Could not start the vision worker: {error}"
            ) from error

    def ping(self, timeout_seconds: float | None = None) -> float:
        self._require_running()
        started_at = time.monotonic()
        try:
            with self._request_lock:
                sequence = self._send(MessageType.PING)
                self._wait_for(
                    MessageType.PONG,
                    sequence,
                    timeout_seconds or self.request_timeout_seconds,
                )
        except VisionWorkerTimeout as error:
            self.state = VisionWorkerState.CRASHED
            self._terminate_process()
            self._finish_process()
            raise VisionWorkerCrashed(
                "The vision worker missed its heartbeat deadline."
            ) from error
        return time.monotonic() - started_at

    def stop(self) -> bool:
        process = self._process
        if process is None:
            self.state = VisionWorkerState.STOPPED
            return True
        if process.poll() is not None:
            self._finish_process()
            self.state = VisionWorkerState.STOPPED
            return True
        self.state = VisionWorkerState.STOPPING
        graceful = False
        try:
            with self._request_lock:
                sequence = self._send(MessageType.SHUTDOWN)
                self._wait_for(
                    MessageType.STOPPED,
                    sequence,
                    self.shutdown_timeout_seconds,
                )
            return_code = process.wait(
                timeout=self.shutdown_timeout_seconds
            )
            graceful = return_code == 0
        except (
            OSError,
            subprocess.TimeoutExpired,
            VisionWorkerError,
            WorkerProtocolError,
        ):
            self._terminate_process()
        finally:
            self._finish_process()
            self.state = VisionWorkerState.STOPPED
        return graceful

    def __enter__(self) -> "VisionWorkerSupervisor":
        self.start()
        return self

    def __exit__(self, _exception_type, _exception, _traceback) -> None:
        self.stop()

    def _start_reader_threads(self) -> None:
        process = self._process
        if (
            process is None
            or process.stdout is None
            or process.stderr is None
        ):
            raise VisionWorkerStartupError(
                "The vision worker pipes are unavailable."
            )
        self._reader_thread = threading.Thread(
            target=self._read_messages,
            args=(process.stdout,),
            name="vision-worker-reader",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr,
            args=(process.stderr,),
            name="vision-worker-stderr",
            daemon=True,
        )
        self._reader_thread.start()
        self._stderr_thread.start()

    def _read_messages(self, stream: BinaryIO) -> None:
        try:
            while True:
                message = read_message(stream)
                if message is None:
                    break
                self._messages.put(message)
        except (OSError, WorkerProtocolError) as error:
            self._reader_error = error
        finally:
            self._messages.put(_END_OF_STREAM)

    def _read_stderr(self, stream: BinaryIO) -> None:
        while True:
            try:
                chunk = stream.read(4096)
            except OSError:
                return
            if not chunk:
                return
            with self._stderr_lock:
                self._stderr.extend(chunk)
                if len(self._stderr) > 32_768:
                    del self._stderr[:-32_768]

    def _send(
        self,
        message_type: MessageType,
        payload: bytes = b"",
    ) -> int:
        process = self._process
        if process is None or process.stdin is None:
            raise VisionWorkerCrashed("The vision worker is not running.")
        if process.poll() is not None:
            self.state = VisionWorkerState.CRASHED
            raise VisionWorkerCrashed(
                f"The vision worker exited with code {process.returncode}."
            )
        sequence = self._next_sequence
        self._next_sequence += 1
        try:
            process.stdin.write(
                encode_message(
                    new_message(message_type, sequence, payload)
                )
            )
            process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            self.state = VisionWorkerState.CRASHED
            raise VisionWorkerCrashed(
                "The vision worker command pipe closed."
            ) from error
        return sequence

    def _wait_for(
        self,
        expected_type: MessageType,
        sequence: int,
        timeout_seconds: float,
    ) -> WorkerMessage:
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise VisionWorkerTimeout(
                    f"Timed out waiting for {expected_type.name}."
                )
            try:
                message = self._messages.get(timeout=remaining)
            except queue.Empty as error:
                raise VisionWorkerTimeout(
                    f"Timed out waiting for {expected_type.name}."
                ) from error
            if message is _END_OF_STREAM:
                self.state = VisionWorkerState.CRASHED
                detail = (
                    f": {self._reader_error}"
                    if self._reader_error is not None
                    else ""
                )
                return_code = (
                    self._process.poll()
                    if self._process is not None
                    else None
                )
                raise VisionWorkerCrashed(
                    f"The vision worker exited with code {return_code}{detail}."
                )
            if not isinstance(message, WorkerMessage):
                raise VisionWorkerError(
                    "The vision worker returned an invalid message."
                )
            if message.sequence != sequence:
                raise VisionWorkerError(
                    "The vision worker response sequence is invalid."
                )
            if message.message_type == MessageType.ERROR:
                raise VisionWorkerError(
                    message.payload.decode("utf-8", errors="replace")
                    or "The vision worker reported an error."
                )
            if message.message_type != expected_type:
                raise VisionWorkerError(
                    "The vision worker returned an unexpected message type."
                )
            return message

    def _require_running(self) -> None:
        if self.state is not VisionWorkerState.RUNNING:
            raise VisionWorkerError("The vision worker is not running.")

    def _terminate_process(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=self.shutdown_timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=self.shutdown_timeout_seconds)

    def _finish_process(self) -> None:
        process = self._process
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
        for thread in (self._reader_thread, self._stderr_thread):
            if thread is not None:
                thread.join(timeout=0.5)
        self._process = None
        self._reader_thread = None
        self._stderr_thread = None
