# Architecture

## Data flow

1. `camera.CameraThread` owns Qt-native camera capture and local MediaPipe
   inference.
2. `vision.FeatureExtractor` converts landmarks to normalized visual proxies
   and category-specific confidence values. Frames and raw landmarks are not
   persisted.
3. `calibration.CalibrationFitter` computes robust good-posture centers/scales
   and optional user-demonstrated category directions for one physical setup.
4. `tracking.PostureEvaluator` smooths scores, applies quality and setup gates,
   then runs sustained warning, alert, cooldown, clear hysteresis, and a bounded
   posture-transition buffer. Brief neutral, low-confidence, or missing-frame
   transitions freeze rather than erase accumulated bad-posture time; the gap
   is not counted and expiry starts a new streak.
5. `ui.main_window.MainWindow` composes the UI workflows that update the system
   tray, store reminder events, and invoke `exercises.ReminderEscalator` and
   `ExerciseSelector`.
6. `history.WorkdayRecorder` groups valid assessments into local posture
   episodes and checkpoints them to `PostureHistoryStore`; gaps, pause,
   calibration, camera loss, and setup changes close the active episode.
7. `storage.AppDataStore` atomically writes validated Pydantic models as local
   JSON.
8. `autostart.AutostartManager` reads and changes the current user's native
   login-startup registration without duplicating that state in `AppData`.

`MainWindow` owns a `side_panel_frame` as the second pane of its horizontal
workspace splitter. The frame supplies one shared title and close action above
the scrollable `side_panel_host`. Setup, settings, calibration selection and
capture, workday summary, evidence and safety, movement guidance, and
operational notices are `QDialog` content objects reparented as widgets into
that host. Only one panel is active at a time. Opening another rejects and
cleans up the previous panel, while Save/Cancel outcomes continue through
asynchronous `finished` signals rather than nested modal `exec()` loops. The
host sizes the main window from the active panel's hints and minimums, falling
back to scrolling only when screen geometry requires it, while preserving a
visible camera workspace. Validation, calibration errors, and destructive
history confirmation remain inline; operational failures use an embedded
`NoticeDialog`. Background movement offers and notices are deferred while a
user-owned panel is active, then surfaced in notice-first order after it
closes, so they cannot discard in-progress settings or setup input.

The main command row is a native `QToolBar`: the setup selector and primary
actions stay visible while long localized secondary actions move into Qt's
overflow menu. A `QStackedWidget` replaces the unused camera canvas with a
focused first-run setup state until a setup exists. Semantic information,
safety, good-stage, and unwanted-stage labels derive light/dark colors from the
active palette rather than assuming a light theme.

Exercise escalation stores one pending movement in `MainWindow`. When a
movement is due, `MainWindow` raises itself and embeds the bundled video in an
`ExerciseDialog` inside the shared side panel instead of routing through a
desktop notification first. A dynamic tray-menu action re-focuses or re-opens
the movement while it is pending, and a yellow dot is overlaid on the tray and
taskbar icon (`create_state_icon` draws the badge) whenever a movement is
pending.

The exercise panel exposes three outcomes through an `ExerciseOutcome`:
**Done** completes and clears the pending movement, **Remind me later**
postpones it for `EXERCISE_POSTPONE_MINUTES` (a single-shot `QTimer`
re-presents it), and **Skip** disregards it and clears the pending state.
Rejecting or replacing the panel is treated as **Remind me later**. The panel
is non-modal and never blocks desktop session shutdown. Safety remains visible;
source links and the medical disclaimer are progressively disclosed to keep
the primary movement instructions compact.

`MainWindow._toggle_tracking()` treats pausing as a camera handoff. It stops
`CameraThread`, clears the preview, disables calibration actions, and marks the
camera available to meeting applications. Resuming reactivates the selected
setup and starts a fresh camera thread. A paused runtime state survives language
reload without briefly reopening the camera.

## UI module boundaries

`vulture.ui` is a compatibility facade over a package of focused modules.
`common` owns shared visual primitives; `calibration`, `settings`, `exercises`,
`notices`, `summary`, and `summary_dialog` own bounded dialog and reporting
surfaces. `shell`, `calibration_flow`, `tracking_flow`, and `application_flow`
provide behavior-preserving `MainWindow` mixins, while `main_window` contains
the runtime snapshot and concrete composition root. Dialog modules do not
depend on `MainWindow`; the facade alone adapts the former camera injection
points to their new owning modules.

## Platform integration

The Settings checkbox for starting at sign-in uses one per-user native
registration on each target: an XDG autostart desktop entry on Linux, a
`LaunchAgent` property list on macOS, and the current-user `Run` registry key
on Windows. File registrations are written atomically with mode `0600`;
Windows commands use the standard command-line quoting rules and respect the
Run-key length limit. Frozen builds register their executable, a macOS
`.app` is opened through Launch Services, an installed console script
registers that script on Linux or macOS, and an unfrozen Windows install uses
the matching `pythonw.exe -m vulture` command to avoid opening a console at
sign-in. The registered command appends `--minimized` so a sign-in launch
starts tracking in the system tray without showing the main window; the window
is still shown when no system tray is available.

The operating-system registration is deliberately the only persisted startup
state. Settings reads it whenever the dialog opens. Enabling or disabling it
is transactional with the JSON settings save: if the JSON write fails, Vulture
restores the exact previous desktop entry, plist, or registry value, and any
read, write, or rollback error is shown to the user. A registration whose
command no longer points to the current Vulture installation appears cleared;
saving it cleared removes the stale entry, while checking it replaces the
entry with the current command. Creating a registration does not launch
another process; it applies at the next sign-in.

Vulture manages only its documented per-user registration. It does not bypass
higher-level desktop startup controls, macOS launchd overrides, Windows
Startup Apps approval, or organization policy; those system controls can still
suppress a registered application.

Linux camera profiles use stable Video4Linux links from `/dev/v4l/by-id` or
`/dev/v4l/by-path` where available, filtered against Qt's usable native video
inputs. macOS and Windows camera profiles use Qt's native `QMediaDevices`
identifiers and descriptions. Resolving and opening a saved profile both match
the native device, so reconnecting or reordering cameras does not silently
select a different device. Legacy index-based profiles are not resolved on
these native targets because an index cannot prove that the calibrated camera
is still selected.

On every platform, `CameraThread` creates `QCamera`,
`QMediaCaptureSession`, and `QVideoSink` inside its own event-loop thread,
applies frame rotation metadata, converts throttled native frames to RGB, then
feeds the same local MediaPipe and `FeatureExtractor` pipeline. A first-frame
deadline surfaces native backends that neither activate nor emit an error. The
thread's event loop is explicitly stopped during setup switching or shutdown.
Platform-specific errors point to macOS or Windows camera privacy settings, or
Linux device permissions.

The bundled pose model also emits ephemeral segmentation masks for up to two
detected poses. Candidates with required landmarks outside the frame or without
mask support are rejected, and the larger foreground subject is preferred.
Face detection runs against that isolated subject so a background face is not
combined with the selected pose. The same mask blurs only the non-person area
of the local preview; frames and masks are discarded after each inference.

`packaging/vulture.spec` is one native-target PyInstaller definition. It emits
an onedir GUI bundle on Linux and Windows and wraps the same collected files in
a macOS `.app`. The macOS `Info.plist` includes
`NSCameraUsageDescription`; all builds include the local models, exercise
metadata and videos, MediaPipe native library, Qt platform/tray/multimedia
plugins, and the platform's video playback backend. Packaging does not add a
runtime network path. `--check-runtime` decodes a frame from every bundled
exercise before loading both landmark models, so missing media codecs or
plugins fail explicitly. The Windows executable uses the console subsystem so
PowerShell can synchronously run that check, but hides a console window during
normal graphical launches.

## Localization

`AppData.interface_language` persists `en`, `de`, or `es`, defaulting to
English for existing settings files. `i18n.tr` resolves application messages
from bundled JSON dictionaries, while Qt's own `qtbase` translator localizes
standard buttons, calendars, and native widget text. Exercise guidance uses a
complete catalog per language with identical source IDs, exercise IDs, safety
metadata, and media paths.

When settings save a new language, `MainWindow` requests a controlled window
reload. The application validates the selected message dictionary, exercise
catalog, and Qt translation before stopping the old camera/history workers.
It then installs the locale, constructs a replacement window over the same
persisted values in a deep-copied `AppData`, and destroys the old tray/window.
The retired window is quiesced before handoff so queued camera or UI events
cannot alter the replacement. This applies the new language immediately
without restarting the process or changing stored calibration/history
identifiers.

## Workday history

`posture-history.sqlite3` contains only posture-category episodes and reminder
events. An episode records its local date, UTC timestamps, UTC offset, setup,
posture label, highest reminder stage reached, duration, and sample count. It
does not contain frames, landmarks, feature vectors, or numeric posture scores.

Episodes are inserted at first detection, updated every ten seconds, and
finalized on transitions. Inter-frame gaps above two seconds add no duration.
Intervals crossing local midnight are split between both calendar days. The
summary panel checkpoints an active episode when today's data is requested,
then presents a daily overview, selected-day timeline, and rolling seven-day
report assembled from the same local daily summaries. One selected day or all
history can be deleted after an inline confirmation.

## Why calibration is setup-specific

Monocular image geometry changes with camera height, yaw, pitch, crop,
resolution, subject distance, and seat position. A universal threshold would
confuse those changes with posture. Every `SetupProfile` therefore binds one
camera descriptor and geometry fingerprint to one robust calibration.

The optional poor-posture examples define standardized directions away from the
good baseline. Lateral lean uses magnitude so a demonstration to one side can
detect either side. Categories that do not separate sufficiently remain
disabled rather than generating confident-looking guesses. A generic baseline
deviation score remains available.

Slouch, sunk shoulders, and lateral lean use whichever calibrated upper-body
landmarks are reliable. Pose-ear and hip geometry improve those categories when
present, but face-mesh, nose, and shoulder relationships keep them calibratable
in a normal head-and-shoulders laptop crop. Feature coverage reduces runtime
confidence when landmarks used by a particular profile disappear.

The shared right-side host keeps the live camera preview visible throughout
calibration. The chooser and capture guide never become top-level windows. The
calibration panel presents the complete ordered stage list throughout capture
and labels each step as a good baseline or unwanted-posture example. Every
built-in `CalibrationStep` also names a bundled calibration PNG.
`CalibrationStageImage` resolves that resource, preserves its aspect ratio, and
shows the matching mannequin pose in both the stage chooser and capture guide;
incremental baseline confirmation reuses the comfortable-baseline image.
After full calibration, `CalibrationFitter.fit_category_for_profile` can learn
or replace one built-in category. It first checks a fresh short baseline sample
against the stored geometry and general-deviation threshold, then fits the
selected example using the stored center and scale. The method returns a deep
copy with only that category replaced; the baseline and all other category
calibrations are preserved. The stage selector also permits a baseline-only
recalibration. That path deliberately creates a new profile with no category
calibrations: category directions and thresholds cannot be safely transferred
to a different center and scale because raw unwanted-posture samples are not
stored.

## Deliberate limitations

- One active camera; no multi-camera fusion.
- PyInstaller builds must be produced natively on each target OS and CPU
  architecture; signing/notarization is a separate release step.
- Incremental examples are limited to the four built-in posture categories;
  arbitrary user-named categories are not yet modeled through tracking,
  reminders, or summaries.
- No clinical angles or anatomical claims.
- Slouch requires visible hips; lateral lean is strongest with hips but has a
  calibrated face-and-shoulder fallback.
- Direct front views have weak anterior/posterior depth information.
- No silent adaptive baseline that could normalize sustained slouch.
- No frame, image, video, or raw-landmark storage.
- No background network dependency.

## Extension points

- Replace `MediaPipeDetector` while retaining `LandmarkObservation`.
- Add a setup-validation capture before accepting calibration.
- Add OS idle/presentation detection so break timers pause automatically.
- Package platform-specific installers and camera entitlements.
- Add explicit user-controlled aggregate statistics without changing the
  frame-retention policy.
