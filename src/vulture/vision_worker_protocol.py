from __future__ import annotations

import json
import struct
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import BinaryIO, Mapping


MAGIC = b"VLT1"
PROTOCOL_VERSION = 1
MAX_PAYLOAD_BYTES = 1_048_576
_HEADER = struct.Struct("<4sHHIQQ")


class MessageType(IntEnum):
    HELLO = 1
    PING = 2
    SHUTDOWN = 3
    CAPABILITIES = 101
    PONG = 102
    STOPPED = 103
    ERROR = 199


class WorkerProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerMessage:
    message_type: int
    sequence: int
    timestamp_ns: int
    payload: bytes = b""


def encode_json_payload(values: Mapping[str, object]) -> bytes:
    payload = json.dumps(
        values,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    _validate_payload(payload)
    return payload


def decode_json_payload(payload: bytes) -> dict[str, object]:
    _validate_payload(payload)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkerProtocolError(
            "The worker returned invalid JSON."
        ) from error
    if not isinstance(value, dict):
        raise WorkerProtocolError(
            "The worker JSON payload must be an object."
        )
    return value


def encode_message(message: WorkerMessage) -> bytes:
    _validate_uint("message type", message.message_type, 16)
    _validate_uint("sequence", message.sequence, 64)
    _validate_uint("timestamp", message.timestamp_ns, 64)
    _validate_payload(message.payload)
    return (
        _HEADER.pack(
            MAGIC,
            PROTOCOL_VERSION,
            message.message_type,
            len(message.payload),
            message.sequence,
            message.timestamp_ns,
        )
        + message.payload
    )


def new_message(
    message_type: MessageType,
    sequence: int,
    payload: bytes = b"",
) -> WorkerMessage:
    return WorkerMessage(
        message_type=message_type,
        sequence=sequence,
        timestamp_ns=time.monotonic_ns(),
        payload=payload,
    )


def read_message(stream: BinaryIO) -> WorkerMessage | None:
    header = _read_exact(stream, _HEADER.size, allow_clean_eof=True)
    if header is None:
        return None
    (
        magic,
        version,
        message_type,
        payload_length,
        sequence,
        timestamp_ns,
    ) = _HEADER.unpack(header)
    if magic != MAGIC:
        raise WorkerProtocolError("The worker message magic is invalid.")
    if version != PROTOCOL_VERSION:
        raise WorkerProtocolError(
            f"Unsupported worker protocol version {version}."
        )
    if payload_length > MAX_PAYLOAD_BYTES:
        raise WorkerProtocolError(
            "The worker payload exceeds the configured limit."
        )
    payload = _read_exact(stream, payload_length)
    if payload is None:
        raise WorkerProtocolError("The worker payload is truncated.")
    return WorkerMessage(
        message_type=message_type,
        sequence=sequence,
        timestamp_ns=timestamp_ns,
        payload=payload,
    )


def _read_exact(
    stream: BinaryIO,
    length: int,
    *,
    allow_clean_eof: bool = False,
) -> bytes | None:
    chunks = bytearray()
    while len(chunks) < length:
        chunk = stream.read(length - len(chunks))
        if not chunk:
            if allow_clean_eof and not chunks:
                return None
            raise WorkerProtocolError("The worker message is truncated.")
        chunks.extend(chunk)
    return bytes(chunks)


def _validate_payload(payload: bytes) -> None:
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise WorkerProtocolError(
            "The worker payload exceeds the configured limit."
        )


def _validate_uint(name: str, value: int, bits: int) -> None:
    if not isinstance(value, int) or not 0 <= value < 2**bits:
        raise WorkerProtocolError(
            f"The worker {name} does not fit in an unsigned {bits}-bit value."
        )
