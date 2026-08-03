# Vulture

Vulture is a private, local-first desktop posture reminder. It watches one
selected webcam, compares visible landmarks with a setup-specific personal
baseline, and changes its system-tray state or shows a notification after a
sustained deviation. Repeated reminders can open a sourced movement break with
a bundled offline video.

Vulture is **not a medical device**. It does not diagnose a condition, measure
spinal anatomy, determine injury risk, or decide that a posture is medically
"correct." Its output means only that the visible pose has remained different
from the baseline demonstrated for that camera setup.

## What the MVP supports

- Multiple named physical setups, including a laptop camera and a separate
  desk camera. Every camera position has its own calibration.
- A mandatory comfortable-baseline sample and optional examples for
  head-forward posture, slouch/crouch, sunk shoulders, and lateral lean. The
  right-side calibration panel keeps every stage and its status visible while
  leaving the live camera preview unobstructed.
- An **Add posture** flow for learning a skipped supported posture or replacing
  one example later without discarding the other category calibrations.
- Confidence gates: Vulture stays quiet when required landmarks are hidden or
  the camera geometry no longer resembles the calibrated setup.
- Temporal smoothing, sustained-warning and alert delays, hysteresis, and
  notification cooldowns.
- A tray icon with green, amber, red, purple, blue, or gray status.
- A local workday summary with a bright, theme-aware posture palette, daily
  distribution and
  timeline views, plus a rolling seven-day report ending on the selected date.
- Setup, settings, calibration, workday summary, evidence and safety, movement
  guidance, and operational notices all draw out in a titled right-side panel
  with one consistent close action while the live camera preview remains
  visible. Panels size to their content and scroll only when the screen cannot
  accommodate them.
- **Release camera** stops tracking and relinquishes the webcam for meeting
  applications. **Resume tracking** reacquires the selected camera afterward.
- English, German, and Spanish interfaces, selected under **Settings** and
  saved locally. Changing language rebuilds the desktop window immediately
  without restarting the process.
- An optional **Start Vulture when I sign in** setting backed by the native
  per-user startup mechanism on Linux, macOS, and Windows.
- Local foreground-person segmentation chooses the strongest visible subject,
  rejects partial out-of-frame detections, and blurs the non-person camera
  preview background. The temporary mask is discarded with each frame.
- An evidence-linked catalog of 13 conservative movements with accessibility
  filters. Eight retain original pregenerated MP4 instructions and five
  additional Vulture Lite movements use the same sourced text-first panel.
- Configurable break management that runs independently of posture alerts:
  position changes, standing, walking, guided movements, distance or greenery
  views, blinking, closed-eye rest, water, tea or coffee, slow breathing, and
  full off-screen resets.
- Local persistence of settings, calibration statistics, and recent reminder
  timestamps. Camera frames are discarded immediately after inference.

Vulture uses one camera at a time. "Multiple setups" means quickly switching
between independently calibrated profiles; it does not fuse simultaneous
camera feeds.

## Download and install

Prebuilt archives are attached to the
[latest GitHub Release](../../releases/latest). They include Python,
MediaPipe, the landmark models, translations, calibration images, and exercise
videos; no separate runtime installation or account is required.

| System | Download |
| --- | --- |
| Linux x86-64 | `Vulture-Linux-x86_64.tar.gz` |
| Windows x86-64 | `Vulture-Windows-x86_64.zip` |
| macOS on Apple silicon | `Vulture-macOS-arm64.zip` |
| macOS on Intel | `Vulture-macOS-x86_64.zip` |

Release builds are currently unsigned. Verify the checksum before overriding
an operating-system warning. Each release includes `SHA256SUMS.txt`.

```bash
# Linux
sha256sum Vulture-Linux-x86_64.tar.gz

# macOS
shasum -a 256 Vulture-macOS-arm64.zip
```

```powershell
# Windows PowerShell
Get-FileHash .\Vulture-Windows-x86_64.zip -Algorithm SHA256
```

Compare the printed value with the matching line in `SHA256SUMS.txt`.

### Linux

Extract the complete folder and start the executable:

```bash
tar -xzf Vulture-Linux-x86_64.tar.gz
./Vulture/Vulture
```

Vulture needs a graphical desktop, a webcam, and permission to read the
selected `/dev/video*` device. It prefers stable `/dev/v4l/by-id` or
`/dev/v4l/by-path` identities when they are available. Some desktops hide
legacy tray icons by default or require a tray extension.

### Windows

Extract the ZIP instead of running from inside it, then open
`Vulture\Vulture.exe`. Windows 10 or 11 may show Microsoft Defender
SmartScreen because the build is not code-signed. After verifying the
checksum, choose **More info → Run anyway**.

If the camera cannot open, enable **Camera access** and **Let desktop apps
access your camera** under **Settings → Privacy & security → Camera**.

### macOS

Download the archive matching the Mac's processor, extract `Vulture.app`, and
move it to **Applications**. On first launch, Control-click the app and choose
**Open**. If macOS still blocks it, use **System Settings → Privacy & Security
→ Open Anyway** after verifying the checksum.

Approve the camera prompt. If access was previously denied, enable **Vulture**
under **System Settings → Privacy & Security → Camera**, then restart it.
Apple-silicon Macs should use the `arm64` build; Intel Macs should use the
`x86_64` build.

### Runtime check

The packaged application can verify its models, translations, media decoders,
and MediaPipe runtime without opening a camera:

```text
Linux:   Vulture/Vulture --check-runtime
macOS:   Vulture.app/Contents/MacOS/Vulture --check-runtime
Windows: Vulture\Vulture.exe --check-runtime
```

Exit code `0` and `Vulture runtime check passed.` indicate a healthy bundle.

## Install from source

Source installation requires Python 3.11 or newer, a webcam exposed by Qt
Multimedia, and a desktop environment with system-tray support.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
vulture
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
vulture
```

Dependency installation may use the network. After installation, camera
analysis, calibration, reminder logic, models, and media run locally without a
service account or network connection. Model source URLs and hashes are in
`src/vulture/resources/models/NOTICE.md`; no model is fetched at runtime.

Camera profiles use native device identifiers on macOS and Windows and stable
device paths where possible on Linux. If an older profile points to a reordered
or replaced camera, add a new setup and calibrate it once.

### Build a native desktop bundle

PyInstaller builds on the current operating system and does not cross-compile:

```bash
python -m pip install -e '.[bundle]'
python -m PyInstaller --noconfirm --clean packaging/vulture.spec
```

The output is `dist/Vulture/Vulture` on Linux,
`dist\Vulture\Vulture.exe` on Windows, or `dist/Vulture.app` on macOS.
Locally built bundles are not automatically signed or notarized.

### Interface language

Open **Settings**, choose **English**, **Deutsch**, or **Español**, and save.
The main window, calibration, summaries, tray actions and notifications,
camera guidance, and exercise instructions switch immediately. The selection
is stored in the same local settings file as the other preferences.

### Start at sign-in

Open **Settings**, check **Start Vulture when I sign in**, and save. Vulture
registers the exact installed or bundled application for the current user;
administrator access is not required. Clearing the checkbox removes that
registration. The change takes effect at the next desktop sign-in and does not
launch a second copy while Settings is open.

A sign-in launch starts in the background: Vulture begins tracking and shows
only its system-tray icon, without opening the main window. Use **Show
Vulture** from the tray menu to open it. If the desktop has no system tray, the
window is shown instead so the app stays reachable.

| Platform | Per-user registration |
| --- | --- |
| Linux | `${XDG_CONFIG_HOME:-~/.config}/autostart/org.vulture.posture.desktop` |
| macOS | `~/Library/LaunchAgents/org.vulture.posture.plist` |
| Windows | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, value `Vulture` |

The operating-system registration is the source of truth for the checkbox.
Vulture reports permission or registry errors instead of pretending the change
was saved. If the application bundle, executable, or source virtual
environment is moved, the checkbox appears cleared because the old command no
longer matches. Check it and save to replace that stale registration with the
new location; saving it cleared removes the stale registration.

Desktop startup managers and organization policies remain authoritative. If
startup is disabled separately in a platform's system settings, Task Manager,
or device policy, re-enable it there as well; Vulture does not bypass those
controls.

### Break management

Open **Settings → Break management** to configure four independent reminder
channels:

- **Movement and position changes** default to every 30 minutes with a
  two-minute suggestion. Vulture shuffles changing the seated position,
  standing, an easy walk, and the guided movement catalog.
- **Eye comfort** defaults to a 20-second distance-view prompt every 20 minutes.
  The non-repeating shuffle also includes a distant green view when available,
  five slow complete blinks, and a gentle closed-eye rest. Vulture does not
  prescribe palming, eye rotations, "eye yoga," or blue-light products.
- **Water** defaults to a neutral 30-second cue every 60 minutes. It does not
  set an intake target and remains the intentionally recurring single-item
  channel.
- **Longer reset** defaults to five minutes every 90 minutes and shuffles tea
  or coffee, an easy walk, a slower breathing pause, a full off-screen reset,
  and a guided movement.

Within every multi-item channel, Vulture chooses randomly without replacement:
every enabled option appears before the bag refills, and a new cycle avoids
repeating the previous item. The activity and exercise bags are stored locally,
so restarting the app or changing language does not reset the sequence.

Saved 0.2.0 profiles keep their previous distance-eye and combined
walk/water/tea/coffee activity mix. The new water, longer-reset, and greenery
options remain off for those profiles until they are enabled in Settings.

Only time with valid posture tracking advances all four timers. A sufficiently
long period away from the camera counts as a break, and reminders can always be
dismissed; Vulture never blocks the desktop.

The defaults are guidance rather than clinical thresholds. UK HSE recommends
short, frequent breaks or changes of activity and explicitly notes that exact
timing depends on the work. Acute randomized evidence and systematic reviews
suggest that brief light walking generally has stronger post-meal glucose and
insulin effects than standing alone, but they do not establish long-term
disease prevention. Micro-break research more consistently supports reduced
fatigue than improved task performance. The optometric 20-20-20 rule is widely
recommended, while a small controlled study found that its exact 20-second
schedule was not an effective standalone treatment for digital eye strain.

Sources:

- [HSE: Work routine and breaks](https://www.hse.gov.uk/msd/dse/work-routine.htm)
- [Buffey et al. 2022: standing and light-walking break meta-analysis](https://doi.org/10.1007/s40279-022-01649-4)
- [Albulescu et al. 2022: micro-break systematic review and meta-analysis](https://doi.org/10.1371/journal.pone.0272460)
- [American Optometric Association: computer vision syndrome](https://www.aoa.org/healthy-eyes/eye-and-vision-conditions/computer-vision-syndrome)
- [Wilkins et al.: “20-20-20 Rule: Are These Numbers Justified?”](https://pubmed.ncbi.nlm.nih.gov/36473088/)
- [Homer et al. 2021: simple resistance activity interruptions](https://pubmed.ncbi.nlm.nih.gov/33905343/)
- [Yin et al. 2024: interruption-frequency meta-analysis](https://pubmed.ncbi.nlm.nih.gov/39630056/)
- [Yaghoubitajani et al. 2026: workplace micro-exercise meta-analysis](https://pubmed.ncbi.nlm.nih.gov/42297926/)
- [Balban et al. 2023: structured respiration trial](https://pubmed.ncbi.nlm.nih.gov/36630953/)
- [Lee et al. 2015: green-view micro-break trial](https://doi.org/10.1016/j.jenvp.2015.04.003)

Vulture is not a medical device and these reminders do not diagnose, treat, or
prevent a condition. Persistent pain, blurred vision, eye redness, light
sensitivity, or other concerning symptoms warrant advice from an appropriate
health professional.

## First calibration

1. Choose **Add setup**, give the physical arrangement a name, and select its
   camera.
2. Keep the face, both shoulders, and preferably both hips visible. A front
   view is best for side lean and shoulder asymmetry. A mild oblique view
   usually gives a more useful personalized head-forward/slouch signal.
3. Record the comfortable baseline while breathing and moving naturally.
4. Optionally demonstrate each unwanted posture gently. Skip any example that
   is uncomfortable or that the camera cannot see. Follow the highlighted
   stage and the **GOOD BASELINE** or **UNWANTED POSTURE** banner so examples
   are not recorded in the wrong step.
5. Repeat this process when camera position, crop, resolution, desk, or seat
   changes materially.

Use **Recalibrate step** in the main window or tray menu to record any one
visible stage again. The stage chooser and capture guide open inside the main
window to the right of the live camera preview, so position and framing remain
visible throughout. For an unwanted posture, Vulture first asks for a short
sample of the saved good baseline to confirm that the camera and seat still
match, then replaces only the selected posture; the other examples remain
unchanged. Replacing the comfortable baseline is also available as a
single-stage flow, but it clears all unwanted posture examples because they
were learned relative to the previous baseline and raw calibration frames are
never stored. This flow supports the four built-in unwanted-posture categories;
it does not create arbitrary named categories.

A head-and-shoulders laptop framing cannot credibly score torso slouch, so that
category will pause when hips are not visible. Sunk shoulders and lateral lean
can fall back to calibrated face-and-shoulder geometry when pose ears or hips
are outside the crop, although visible hips strengthen the side-lean signal. A
directly front-facing monocular camera has limited depth information; a
personalized head-forward example may still work through relative head/face
scale, but it is not a clinical neck-angle measurement.

After upgrading an existing installation, re-record **Sunk shoulders** and
**Lateral lean** with **Recalibrate step** so their profiles include the
upper-body fallbacks. Vulture cannot retrofit old examples because calibration
frames and landmarks are intentionally never stored.

Copy-ready image-generation prompts for all five visible calibration stages
are in `src/vulture/resources/calibration/photo-prompts.json`. They use the
same locked-off telephoto, warm near-monochrome mannequin style as the exercise
video prompts, adapted to a single 1280x720 still. Prepend the shared
`continuity_lock` to one stage prompt. Generate the comfortable baseline first
and, when supported, attach that unchanged image to the four unwanted-posture
requests. Each prompt isolates one stage and intentionally contains no text so
the application can supply the localized title and instructions. The accepted
five images are bundled beside the prompt file and appear in the recalibration
chooser and active capture guide as visual examples.

## Reminder behavior

Defaults are intentionally conservative:

- warning after 8 seconds of sustained personalized deviation;
- notification after 60 seconds;
- retain accumulated bad-posture time across an up-to-8-second posture-change
  buffer without counting the transition itself;
- notification cooldown of 2 minutes;
- movement-break offer after 5 notifications within 20 minutes;
- independent eye, movement, water, and longer-reset timers with configurable
  intervals and durations.

Ordinary break activities use one system notification, bundling channels that
become due together. A guided movement raises the main window and opens its
instructions in the right-side panel beside the live camera preview.

The exercise panel offers three choices. **Done** marks the movement complete
and clears it. **Remind me later** closes the panel and re-opens it after a
short delay. **Skip** disregards the movement. Closing or replacing the
exercise panel behaves like **Remind me later**. While a movement is pending
you can also re-open it with **Open movement** from the tray-icon menu.
If another right-side panel is in use when a movement becomes due, Vulture
keeps that work intact and opens the pending movement after the panel closes.
Safety guidance stays visible; source links and the longer medical context are
available through **Sources and medical context**.

While a movement is waiting, Vulture marks its tray icon and taskbar icon with a
yellow dot. The marker clears once the movement is completed or skipped.

The exact alert and escalation values are **product settings**, not medical
recommendations. They can be changed in **Settings**. Short intentional
movements and low-confidence frames do not trigger a reminder. A brief neutral,
uncertain, or missing-frame transition can preserve the previous bad-posture
timer, but the transition time itself is excluded and a longer recovery resets
the timer.

Use **Release camera** before joining a meeting that needs the same webcam.
Vulture stops its camera thread rather than merely suspending posture scoring,
clears the preview, and disables calibration until **Resume tracking** is
selected.

## Exercise guidance

The eight bundled clips are language-neutral generated demonstrations created
for Vulture. They contain no narration, text, logos, or footage of a real
person. Most use the shared mannequin style; a minimal geometric fallback
remains where a reviewed mannequin replacement is not yet available. The
movement instructions and doses—not the artwork—are linked to the authoritative
sources in [docs/EVIDENCE.md](docs/EVIDENCE.md).

The five imported Vulture Lite movements are fully localized, sourced
text-first guides without placeholder video. The same safety, accessibility,
postpone, skip, and source-link behavior applies.

Copy-ready generation prompts and review requirements are in
`src/vulture/resources/exercises/video-prompts.json`. Prepend its shared
`continuity_lock` to one exercise prompt. The lock defines the stable
mannequin, camera, lighting, grade, framing, motion, audio, and output format;
a chair or support required for safe technique is its only prop exception.
Reject any generated clip that changes the technique, violates the lock, or
shows anatomically incorrect movement.

## Privacy

Vulture has no telemetry or upload path. It does not save frames, photos,
camera videos, raw landmarks, or posture scores. If workday history is enabled,
it saves local category labels, reminder stages, setup identifiers, timestamps,
and aggregate durations for the configured retention period. Open **Workday
summary** to inspect or delete one day or all history. See
[docs/PRIVACY.md](docs/PRIVACY.md) for details.

## Updates and uninstall

Vulture does not yet include an automatic updater. Download a newer release,
quit Vulture, and replace the extracted application folder or `.app`. Settings,
calibrations, and optional posture history remain in the separate user-data
directory:

| Platform | Default data directory |
| --- | --- |
| Linux | `~/.config/Vulture` |
| macOS | `~/Library/Application Support/Vulture` |
| Windows | `%LOCALAPPDATA%\Vulture` |

Open **Settings** and disable **Start Vulture when I sign in** before removing
the application. Delete the application folder or `.app` to uninstall it.
Delete the data directory as well only if you also want to remove every saved
setup, preference, calibration, and local history record.

## Troubleshooting

- **Another application needs the webcam:** choose **Release camera** in
  Vulture, join the meeting, then choose **Resume tracking** afterward.
- **The camera does not open:** close other camera applications, confirm the
  operating-system privacy permission, and verify that the selected setup
  still points to the intended camera.
- **No tray icon is visible:** open Vulture from its executable and enable the
  desktop's tray/status-icon support. Vulture shows its window automatically
  when no system tray is available.
- **A downloaded bundle will not start:** run its `--check-runtime` command
  from a terminal and include the complete output in a bug report.
- **A moved installation no longer starts at sign-in:** open **Settings**,
  clear and save the startup option, then enable and save it again from the new
  location.

## Development

```bash
python -m pip install -e '.[dev,bundle]'
python -m pytest
```

Architecture and extension points are described in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### Automated builds and releases

`.github/workflows/build-and-release.yml` runs the full test suite, builds
native bundles for Linux x86-64, Windows x86-64, macOS Apple silicon, and macOS
Intel, and runs each bundle's runtime check. Pull requests and pushes to
`main` retain downloadable workflow artifacts for 14 days.

To publish a release:

1. Update the matching version in `pyproject.toml` and
   `src/vulture/__init__.py`.
2. Commit and push the tested change to `main`.
3. Create and push an annotated `v<version>` tag, for example:

   ```bash
   git tag -a v0.1.0 -m "Vulture 0.1.0"
   git push origin main v0.1.0
   ```

The workflow rejects a tag that does not match `pyproject.toml`, then publishes
the four archives and `SHA256SUMS.txt` as a GitHub Release. Windows code signing
and Apple Developer signing/notarization remain separate release-hardening
steps because they require private certificates.

## Contributing

Vulture is young and a few concrete contributions would help it noticeably.
Please open an issue to coordinate before starting larger work, then send a
pull request. Development setup lives just above; generated exercise clips must
stay language-neutral and must never depict a real person.

### Help wanted

- **A proper application icon.** Vulture currently draws its own placeholder —
  a flat coloured disc with a white "V" (see `create_state_icon` in
  `src/vulture/ui/common.py`). It deserves a distinctive, recognisable mark
  that stays legible at tray sizes (16–32 px) as well as large application
  sizes, survives recolouring across the six tray states (green, amber, red,
  purple, blue, gray) or ships as per-state variants, and exports to the
  platform bundle formats (`.png`, Windows `.ico`, macOS `.icns`). A clean
  monochrome silhouette that Qt can tint per state is ideal.
- **A review pass over the instructional videos.** The eight bundled clips are
  generated, language-neutral demonstrations. Watch each one against its
  generation prompt and against the technique and dose recorded in
  [docs/EVIDENCE.md](docs/EVIDENCE.md), then flag any clip that drifts from the
  specified technique, breaks the shared continuity lock, or shows
  anatomically incorrect movement. The copy-ready prompts, the shared
  `continuity_lock`, and the review requirement are all in
  `src/vulture/resources/exercises/video-prompts.json`.
- **One missing instructional video.** Seven clips are full mannequin
  demonstrations (~2.6 MB each); `ankle-point-flex.mp4` is still a minimal
  geometric placeholder (~28 KB). It needs a proper replacement generated from
  the `ankle-point-flex` prompt in `video-prompts.json` (prepend the shared
  `continuity_lock`), reviewed against the same requirement, and saved over
  `src/vulture/resources/exercises/videos/ankle-point-flex.mp4`. Keep it a
  10-second, 16:9 seamless loop with no narration, on-screen text, logo, or
  watermark.

## License

Vulture is released under the [MIT License](LICENSE). Bundled dependencies and
model assets remain under their respective upstream licenses; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the
[model notice](src/vulture/resources/models/NOTICE.md).
