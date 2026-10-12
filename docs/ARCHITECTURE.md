# Architecture

## Data flow

1. `camera.CameraThread` owns platform camera capture and local MediaPipe
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
   tray, request timer-aligned break notifications, store reminder events, and
   invoke `exercises.ReminderEscalator` and `ExerciseSelector`.
6. `history.WorkdayRecorder` groups valid assessments into local posture
   episodes and checkpoints them to `PostureHistoryStore`; gaps, pause,
   calibration, camera loss, and setup changes close the active episode.
   Completed movement and rest breaks are passed to `record_break` through the
   same recorder, which skips them when recording is disabled.
7. `storage.AppDataStore` atomically writes validated Pydantic models as local
   JSON.
8. `autostart.AutostartManager` reads and changes the current user's native
   login-startup registration without duplicating that state in `AppData`.

An experimental `vulture-vision-worker` process boundary is under development
but is not yet connected to `CameraThread`. The C++20 skeleton and Python
supervisor currently prove bounded, versioned IPC over inherited binary pipes:
handshake, heartbeat ping, protocol errors, graceful shutdown, crash detection,
and forced termination. Camera capture and MediaPipe remain in process until
the worker reaches feature and recognition parity.

`MainWindow` owns a `side_panel_frame` as the second pane of its horizontal
workspace splitter. The frame supplies one shared title and close action above
the scrollable `side_panel_host`. Add setup, calibration selection and capture,
rest breaks, movement guidance, and operational notices are `QDialog` content
objects reparented as widgets into that host. These are the short
interruptions and flows that belong beside the live preview. Settings, the
workday summary, and evidence and safety instead open through
`SecondaryWindowPresenter` (`application_flow.py`) as separate windows placed
beside the main window. Only one side panel is active at a time. Opening another
rejects and cleans up the previous panel, while Save/Cancel outcomes continue
through asynchronous `finished` signals rather than nested modal `exec()` loops.
The host sizes the main window from the active panel's hints and minimums,
falling back to scrolling only when screen geometry requires it, while preserving a
visible camera workspace. Validation, calibration errors, and destructive
history confirmation remain inline; operational failures use an embedded
`NoticeDialog`. Background movement offers and notices are deferred while a
user-owned panel is active, then surfaced in notice-first order after it
closes, so they cannot discard in-progress settings or setup input.

The main command row is a native `QToolBar`: the setup selector and primary
actions stay visible while long localized secondary actions move into Qt's
overflow menu. A `QStackedWidget` replaces the unused camera canvas with a
first-run card (`_FIRST_RUN_OBJECT_NAME`, themed by `card_style`) until a setup
exists; it takes initial focus on **Add camera setup**. `ShellMixin` hides the
footer disclaimer while a side panel is open. Semantic information,
safety, good-stage, and unwanted-stage labels derive light/dark colors from the
active palette rather than assuming a light theme.

Posture, ordinary break, and operational messages use native
`QSystemTrayIcon` notifications. For an ordinary break, the timeout hint
matches the configured activity duration; channels that become due together
use the longest included duration. The operating system or desktop environment
controls the final lifetime and placement and may ignore Qt's timeout hint.

Exercise escalation stores one pending movement in `MainWindow`. When a
movement is due, `MainWindow` raises itself and embeds the bundled video in an
`ExerciseDialog` inside the shared side panel instead of routing through a
desktop notification first. A dynamic tray-menu action re-focuses or re-opens
the movement while it is pending, and a yellow dot is overlaid on the tray and
taskbar icon (`create_state_icon` draws the badge) whenever a movement is
pending.

The exercise panel exposes three outcomes through an `ExerciseOutcome`:
**Done** completes and clears the pending movement, **Later** postpones it for
`EXERCISE_POSTPONE_MINUTES` (a single-shot `QTimer` re-presents it), and
**Skip** disregards it and clears the pending state. **Later** is the first
item of the **Not now** menu in `BreakPanel`, and the header button performs the
same postponement. Rejecting or replacing the panel is treated as **Later**.
Rest breaks have no postponement: their header button reads **Close** and
dismissing one skips it. `BreakPanel` shows **Start** and the **Not now** menu
before a timer starts. While a timer runs, `ShellMixin` hides the header button
and ignores Esc, leaving **Stop early** as the way out.
**Done** records the outcome immediately, shows a short acknowledgement for
`COMPLETION_ACK_MS`, then closes. The panel has no default button, so Enter
cannot complete a break. It is non-modal and never blocks desktop session
shutdown. The inline safety line is specific to the movement. The first movement
shown also appends the full global safety text (`AppData.full_safety_shown`).
Source links and the medical disclaimer are progressively disclosed under
**Sources and medical context** to keep the primary movement instructions
compact.

## Break mode

`BreakPanel` sets `wants_break_mode`, so both `ExerciseDialog` (guided
movements) and `RestBreakDialog` (rest breaks) inherit it. When
`ShellMixin._show_side_panel` hosts such a panel, it hides the camera workspace
and gives the break the whole content area in a centred column capped at
`_BREAK_COLUMN_MAX_WIDTH`.
Ordinary panels keep the workspace beside them. Break mode never resizes the
window and skips the height-fit pass. Background arrivals call
`_show_window(activate=False)`, which sets `WA_ShowWithoutActivating`, raises
the window, and calls `QApplication.alert`, so a movement cannot take keyboard focus
from the user's typing. Closing the panel restores the camera workspace.

Inside the dialog, the demonstration `QMediaPlayer` has no audio output and
loops its clip. Timed doses start with **Start** and show a countdown. Set-based
doses show round checkboxes instead. A standing walk-away movement pauses its
clip when the countdown starts and shows a large countdown, with the clip as a
small thumbnail beside the steps (`THUMBNAIL_SHARE` of the panel width).

`MainWindow._toggle_tracking()` treats pausing as a camera handoff. It stops
`CameraThread`, clears the preview, disables calibration actions, and marks the
camera available to meeting applications. The toolbar and tray action read
**Pause camera** while tracking and **Resume tracking** while paused. Resuming
reactivates the selected setup and starts a fresh camera thread. A paused
runtime state survives language reload without briefly reopening the camera.

## UI module boundaries

`vulture.ui` is a compatibility facade over a package of focused modules.
`theme` owns the design tokens — the spacing scale, the type roles, the
palette-derived colours, and the `Card`, `Separator`, and `CaptionLabel`
primitives — so that every surface reads its sizes from one place instead of
nudging fonts and margins locally. The colour tokens are calm: posture states
never use alarm red, and foreground/background pairs meet WCAG AA for small
text. Captions are quieter through colour rather than size, so the `CAPTION`
role does not step below body text (`_ROLE_STEPS`). The `DISPLAY` role, used for
countdowns, is the UI font with tabular figures (`tnum`), so digits keep one
width without a monospace face. `primary_button_style()` is the filled action
used by `BreakPanel` for **Start** and **Done**, and `flat_action_style()` gives
the shell's toolbar actions and side-panel header buttons their button shape
only while they are in play. Every clickable control is at least
`CONTROL_MIN_HEIGHT` (28 px) through `ControlMetricsStyle`, a `QProxyStyle`
that keeps the platform look while enforcing that minimum for push buttons,
tool buttons, combo boxes, line edits, and spin boxes. `common`
owns shared visual primitives built on those tokens; `calibration`, `settings`,
`exercises`, `notices`, `summary`, and `summary_dialog` own bounded dialog and
reporting surfaces.
`shell`, `calibration_flow`, `tracking_flow`, and `application_flow`
provide behavior-preserving `MainWindow` mixins, while `main_window` contains
the runtime snapshot and concrete composition root. Dialog modules do not
depend on `MainWindow`; the facade alone adapts the former camera injection
points to their new owning modules.

The workspace is a two-column grid whose columns share two datums: the break
card and the side panel start their first line of text on the same baseline,
and the side panel's action row sits on the same footer baseline as the
workspace buttons. `shell.SIDE_PANEL_CONTENT_MARGINS` keeps the hosted panel
flush with that footer, and `theme.align_first_baseline` aligns mixed type
sizes that share a row. Both datums are covered by tests, because they are
invisible to unit assertions about individual widgets.

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

On Linux, `CameraThread` opens the resolved stable Video4Linux path through
OpenCV. This keeps Qt's FFmpeg V4L2 buffer lifecycle out of the long-running
capture path, so a device reset or disconnect becomes a reported read failure
instead of a native Qt process crash. The Linux path retains the camera
driver's selected capture format, keeps only one OpenCV image worker, and
requests enough camera frames to keep the analysis deadline supplied. Frames
that arrive ahead of the monotonic deadline are discarded rather than queued.
On macOS and Windows, `CameraThread` creates `QCamera`,
`QMediaCaptureSession`, and `QVideoSink` inside its own event-loop thread and
applies frame rotation metadata. Both paths use a monotonic five-frame-per-
second analysis deadline and feed the same local MediaPipe and
`FeatureExtractor` pipeline. CPU inference is the default on every platform
because it provides the reliable recognition baseline. Linux users can
explicitly test the MediaPipe GPU delegate with
`VULTURE_MEDIAPIPE_DELEGATE=gpu`; initialization failure falls back to CPU.
Preview generation has a separate two-frame-per-second deadline and is disabled
while the main window is hidden or minimized. Preview images are reduced to at
most 320 pixels wide before background processing and display scaling. If
person segmentation is temporarily unavailable, the local preview remains
unblurred rather than turning into an unusable fully blurred frame. A
first-frame deadline surfaces backends that neither activate nor emit an error.
An ongoing main-thread heartbeat replaces old posture results after three
seconds without camera or inference progress and reports the camera unavailable
after ten seconds. The thread is explicitly stopped during setup switching or
shutdown. Platform-specific errors point to macOS or Windows camera privacy
settings, or Linux device permissions.

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

`posture-history.sqlite3` contains only posture-category episodes, reminder
events, and completed breaks. A `break_events` row records the local date,
UTC completion time, kind (`movement` or `rest`), channel, exercise identifier
for movements, and duration. Skipped, postponed, and swapped breaks are not
recorded. The table is added by the existing `CREATE TABLE IF NOT EXISTS`
script, so `SCHEMA_VERSION` stays at 1. Deleting a day or all history and
retention pruning also delete `break_events` rows.

An episode records its local date, UTC timestamps, UTC offset, setup,
posture label, highest reminder stage reached, duration, and sample count. It
does not contain frames, landmarks, feature vectors, or numeric posture scores.

Episodes are inserted at first detection, updated every ten seconds, and
finalized on transitions. Inter-frame gaps above two seconds add no duration.
Intervals crossing local midnight are split between both calendar days. The
summary panel checkpoints an active episode when today's data is requested,
then presents a daily overview, selected-day timeline, and rolling seven-day
report assembled from the same local daily summaries. The daily overview leads
with breaks, minutes moved, and eye breaks; the seven-day report shows the
breaks for each day. One selected day or all
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
