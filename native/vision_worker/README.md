# Vulture vision worker

This directory contains the first isolated native-worker slice. The executable
currently implements only protocol handshake, ping, error, and shutdown
messages. It does not open a camera or load MediaPipe, and the application does
not select it as a vision backend yet.

Build locally:

```sh
cmake -S native/vision_worker -B build/vision-worker
cmake --build build/vision-worker
```

The worker communicates through inherited binary standard-input and
standard-output pipes. Each little-endian message contains:

- four-byte `VLT1` magic;
- 16-bit protocol version;
- 16-bit message type;
- 32-bit payload length;
- 64-bit sequence number;
- 64-bit monotonic timestamp;
- a payload limited to 1 MiB.

`src/vulture/vision_worker_protocol.py` owns the matching Python framing, while
`src/vulture/vision_worker.py` owns child-process startup, request timeouts,
graceful shutdown, and forced termination.
