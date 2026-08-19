# Changelog

Notable user-visible changes are recorded here.

## Unreleased

### Changed

- The interface now draws its type sizes, spacing, and corner radii from a
  single set of design tokens. Headings, values, captions, and countdowns use
  one type scale instead of the per-widget font adjustments that had
  accumulated across the workspace, calibration, settings, and summary
  surfaces.
- The workspace and the exercise, break, and notice side panels now line up:
  their first line of text starts on a shared baseline, and the panel's action
  buttons sit on the same footer baseline as the workspace buttons.
- The break card reads as one block, with the next break, its countdown, and
  the "until next break" caption aligned on a shared baseline instead of
  drifting apart at different sizes.
- The toolbar groups the setup selector on the left and the commands on the
  right, separated so that Settings no longer crowds the tracking actions.
- Exercise media keeps a 16:9 shape as the panel resizes rather than a fixed
  height, and exercise steps, sources, and safety notes share the workspace's
  reading rhythm.

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
