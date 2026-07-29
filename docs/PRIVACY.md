# Privacy model

## Local processing

OpenCV reads frames from the selected camera and MediaPipe performs landmark
inference in the camera thread. Each frame is converted into a preview image
and normalized feature values, then released. Vulture has no network client,
telemetry SDK, account system, cloud endpoint, or upload code.

The preview is displayed only in application memory. Vulture does not record
the preview, camera frames, raw pose landmarks, raw face landmarks, audio, or
exercise activity.

## Persisted data

The application stores one JSON file containing:

- named setup and camera descriptors;
- robust calibration centers, scales, category directions, thresholds, and a
  coarse geometry fingerprint;
- reminder policy and accessibility preferences;
- recent reminder category/timestamp/setup identifiers for escalation;
- recently shown exercise identifiers to reduce repetition.

When **Save local posture categories and durations** is enabled, a separate
SQLite database stores:

- posture label (`baseline`, `forward_head`, `slouch`, `shoulders_sunk`,
  `lateral_lean`, or `general_deviation`);
- highest reminder stage reached during each contiguous episode;
- setup identifier, local workday, UTC start/end timestamps and UTC offset;
- aggregate duration and sample count;
- notification timestamps and categories.

It does not store raw scores, feature vectors, landmarks, camera frames, or
exercise video of the user. Retention defaults to 30 days and is configurable
from **Settings**. The **Workday summary** window can delete one day or all
history. Disabling recording leaves existing history available until it is
deleted or expires.

The settings file and history database are written with owner-only permissions
on Unix-like systems. SQLite secure deletion is enabled and deleting all
history also compacts the database, but filesystem snapshots and backups may
retain older blocks.

The default location is selected by `platformdirs`:

- Linux: usually `~/.config/Vulture/settings.json`
- macOS: usually `~/Library/Application Support/Vulture/settings.json`
- Windows: usually `%LOCALAPPDATA%\Vulture\settings.json`

Set `VULTURE_DATA_DIR` to choose another local directory.
The history database is stored beside the settings file as
`posture-history.sqlite3`.

## Threat boundary

Vulture protects against accidental application-level retention and upload; it
cannot protect a compromised operating system, camera driver, desktop
environment, or user account. Calibration statistics and reminder history can
still be sensitive behavioral data and should be protected by normal disk and
account security.
