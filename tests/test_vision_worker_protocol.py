from __future__ import annotations

import io
import struct

import pytest

from vulture.vision_worker_protocol import (
    MAGIC,
    MAX_PAYLOAD_BYTES,
    MessageType,
    WorkerMessage,
    WorkerProtocolError,
    decode_json_payload,
    encode_json_payload,
    encode_message,
    read_message,
)


def test_worker_message_round_trip() -> None:
    original = WorkerMessage(
        message_type=MessageType.PING,
        sequence=42,
        timestamp_ns=123_456,
        payload=b"payload",
    )

    restored = read_message(io.BytesIO(encode_message(original)))

    assert restored == original


def test_clean_worker_stream_end_returns_none() -> None:
    assert read_message(io.BytesIO()) is None


def test_truncated_worker_message_is_rejected() -> None:
    encoded = encode_message(
        WorkerMessage(
            message_type=MessageType.PING,
            sequence=1,
            timestamp_ns=1,
            payload=b"payload",
        )
    )

    with pytest.raises(WorkerProtocolError, match="truncated"):
        read_message(io.BytesIO(encoded[:-1]))


def test_oversized_worker_payload_is_rejected_before_reading() -> None:
    header = struct.pack(
        "<4sHHIQQ",
        MAGIC,
        1,
        MessageType.PING,
        MAX_PAYLOAD_BYTES + 1,
        1,
        1,
    )

    with pytest.raises(WorkerProtocolError, match="exceeds"):
        read_message(io.BytesIO(header))


def test_worker_json_payload_requires_an_object() -> None:
    with pytest.raises(WorkerProtocolError, match="must be an object"):
        decode_json_payload(b"[]")

    assert decode_json_payload(
        encode_json_payload({"protocol_version": 1})
    ) == {"protocol_version": 1}
