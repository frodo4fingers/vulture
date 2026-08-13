from __future__ import annotations

import argparse
import os
import sys
import time

from vulture.vision_worker_protocol import (
    MessageType,
    encode_json_payload,
    encode_message,
    new_message,
    read_message,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--behavior",
        choices=(
            "normal",
            "crash-after-hello",
            "delay-pong",
            "error-on-exit",
            "hang-on-hello",
            "hang-on-shutdown",
        ),
        default="normal",
    )
    arguments = parser.parse_args()
    while True:
        message = read_message(sys.stdin.buffer)
        if message is None:
            return 0
        message_type = MessageType(message.message_type)
        if message_type is MessageType.HELLO:
            if arguments.behavior == "hang-on-hello":
                time.sleep(60)
            _write(
                MessageType.CAPABILITIES,
                message.sequence,
                encode_json_payload(
                    {
                        "features": ["ping", "shutdown"],
                        "name": "fake-vision-worker",
                        "protocol_version": 1,
                    }
                ),
            )
            if arguments.behavior == "crash-after-hello":
                os._exit(17)
        elif message_type is MessageType.PING:
            if arguments.behavior == "delay-pong":
                time.sleep(0.25)
            _write(MessageType.PONG, message.sequence)
        elif message_type is MessageType.SHUTDOWN:
            if arguments.behavior == "hang-on-shutdown":
                time.sleep(60)
            _write(MessageType.STOPPED, message.sequence)
            return 7 if arguments.behavior == "error-on-exit" else 0
        else:
            _write(
                MessageType.ERROR,
                message.sequence,
                b"unsupported command",
            )


def _write(
    message_type: MessageType,
    sequence: int,
    payload: bytes = b"",
) -> None:
    sys.stdout.buffer.write(
        encode_message(new_message(message_type, sequence, payload))
    )
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    raise SystemExit(main())
