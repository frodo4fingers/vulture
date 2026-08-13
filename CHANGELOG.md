# Changelog

Notable user-visible changes are recorded here.

## 0.5.0 - 2026-08-13

### Added

- Added the first supervised C++ vision-worker foundation with bounded,
  versioned IPC, heartbeat checks, crash detection, startup cleanup, and forced
  termination. It is not yet selected as the runtime camera backend.
- Native worker compilation is now checked on Linux, Windows, and Apple
  silicon in continuous integration.

### Changed

- Reduced the outer margins around the main workspace and embedded side panels
  while preserving spacing inside forms and control groups.

## 0.4.0 - 2026-08-13

### Changed

- Camera analysis now targets five frames per second with a monotonic cadence,
  limits OpenCV's worker fan-out, and produces smaller previews at a lower
  cadence only while the window is visible. MediaPipe CPU inference remains
  the reliable default; GPU inference is available through
  `VULTURE_MEDIAPIPE_DELEGATE=gpu`.
- The preview remains visible while person segmentation is temporarily
  unavailable instead of blurring the entire frame.
- Tracking now replaces stale posture results with an explicit delayed-camera
  state and reports the camera unavailable if processing remains stopped.

### Fixed

- Linux camera capture now reports device resets or disconnects instead of
  allowing Qt's FFmpeg V4L2 buffer path to terminate the application.

## 0.3.1 - 2026-08-11

### Fixed

- Settings files written by another Vulture version no longer block startup.
  Unknown entries, such as the experimental notification placement setting, are
  now ignored instead of failing with a validation error.

### Changed

- Break reminders now request a native notification timeout matching the
  configured activity duration. Combined reminders request the longest
  included duration; the operating system still controls actual lifetime and
  placement.
