# Changelog

Notable user-visible changes are recorded here.

## Unreleased

### Added

- Movement breaks use a break mode: the camera workspace steps aside and the
  movement fills the window in a centred column. A movement that arrives in
  the background does not resize the window or take keyboard focus.
- Movements show a round checklist for set-based doses, and a "Watch once,
  then go" heading and large countdown for standing walk-away movements.
- A calibration option to play sound cues, under **Settings → General**.
- Screen-reader announcements during calibration recording.

### Changed

- Settings is split into Posture, Breaks, Privacy & data, and General tabs.
  Break shuffle lists sit behind **Customize…**.
- Add setup, calibration, rest breaks, movement guidance, and notices open in
  the right-side panel beside the live preview. Settings and Evidence and
  safety open in separate windows instead.
- The reference photo in calibration is cropped to head and shoulders beside
  the instructions, and the actions stay pinned at the bottom.
- **Release camera** is now **Pause camera**. **Recalibrate step** is now
  **Redo a calibration step**. Camera actions are hidden until a setup exists.
- The status panel shows a coloured dot beside the state name.
- The colour palette is calm. Posture states no longer use alarm red, captions
  are no smaller than body text, and clickable controls are at least 28 px tall.
- Movement demonstration videos are silent and loop. The first movement break
  shows the full global safety text once, and each movement shows its own
  safety line.
- **Done** shows a short acknowledgement. No button is the default, so Enter
  cannot complete a break.

## 0.6.0 - 2026-08-19

### Added

- Break reminders now run independently of camera tracking. Vulture can start
  without a camera setup, keeps all four schedules running during calibration
  or while the camera is released, and gives scheduled breaks priority when a
  posture alert is due at the same time.
- Added **Move now** for taking an early break, plus in-panel alternatives for
  switching between guided movement, eye rest, standing, walking, water,
  coffee, breathing, and off-screen reset activities.
- Non-exercise breaks now offer an optional live countdown and progress
  indicator while leaving the user in control of when to finish.

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
