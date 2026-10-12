---
name: Vulture
description: A calm-coach posture and break companion for the Qt desktop
colors:
  primary-action: "#1f5f8f"
  primary-action-hover: "#1a5280"
  primary-action-pressed: "#144468"
  on-primary-action: "#ffffff"
  primary-action-dark: "#8cc4f0"
  primary-action-dark-hover: "#a3d1f5"
  primary-action-dark-pressed: "#6aaee4"
  on-primary-action-dark: "#0b1620"
  media-well: "#15191f"
  media-text: "#c3ccd8"
  state-stopped: "#4a5568"
  state-calibrating: "#2b6cb0"
  state-good: "#276749"
  state-warning: "#d69e2e"
  state-alert-ochre: "#8a5a00"
  state-uncalibrated: "#6b46c1"
  state-on-fill: "#f7fafc"
  state-on-warning: "#1a202c"
  exercise-badge: "#ecc94b"
  info-panel-bg: "#edf2f7"
  info-panel-text: "#1a202c"
  info-panel-border: "#cbd5e0"
  safety-panel-bg: "#fbf7ec"
  safety-panel-text: "#5b4a1f"
  safety-panel-border: "#e6d8b0"
  good-panel-bg: "#f0fff4"
  good-panel-text: "#22543d"
  good-panel-border: "#9ae6b4"
  unwanted-panel-bg: "#fffaf0"
  unwanted-panel-text: "#7b341e"
  unwanted-panel-border: "#fbd38d"
  error-panel-bg: "#fff5f5"
  error-panel-text: "#742a2a"
  error-panel-border: "#feb2b2"
  stage-current-bg: "#bee3f8"
  stage-current-text: "#1a365d"
  stage-recorded-bg: "#c6f6d5"
  stage-recorded-text: "#22543d"
  stage-retry-bg: "#feebc8"
  stage-retry-text: "#7b341e"
  stage-skipped-bg: "#e2e8f0"
  stage-skipped-text: "#2d3748"
  link: "#2b6cb0"
  link-visited: "#6b46c1"
  link-dark: "#90cdf4"
  link-visited-dark: "#d6bcfa"
  posture-baseline-blue: "#287eaf"
  posture-forward-head-olive: "#566b00"
  posture-slouch-clay: "#cc7240"
  posture-shoulders-sunk-brown: "#884f00"
  posture-lateral-lean-teal: "#25957c"
  posture-general-deviation-plum: "#7a5c9e"
  posture-other-tracked-amber: "#a56810"
typography:
  display:
    fontFamily: "Platform UI font (QApplication.font())"
    fontSize: "calc(1em + 8pt)"
    fontWeight: 600
    fontFeature: "\"tnum\" 1"
  title:
    fontFamily: "Platform UI font (QApplication.font())"
    fontSize: "calc(1em + 3pt)"
    fontWeight: 600
  headline:
    fontFamily: "Platform UI font (QApplication.font())"
    fontSize: "calc(1em + 1pt)"
    fontWeight: 600
  body:
    fontFamily: "Platform UI font (QApplication.font())"
    fontSize: "1em"
    fontWeight: 400
    lineHeight: 1.38
  body-strong:
    fontFamily: "Platform UI font (QApplication.font())"
    fontSize: "1em"
    fontWeight: 600
  label:
    fontFamily: "Platform UI font (QApplication.font())"
    fontSize: "1em"
    fontWeight: 400
rounded:
  sm: "4px"
  md: "8px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary-action}"
    textColor: "{colors.on-primary-action}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "28px"
  button-primary-hover:
    backgroundColor: "{colors.primary-action-hover}"
  button-primary-pressed:
    backgroundColor: "{colors.primary-action-pressed}"
  button-primary-dark:
    backgroundColor: "{colors.primary-action-dark}"
    textColor: "{colors.on-primary-action-dark}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "28px"
  button-flat:
    backgroundColor: "transparent"
    rounded: "{rounded.sm}"
    padding: "0 8px"
    height: "28px"
  panel-safety:
    backgroundColor: "{colors.safety-panel-bg}"
    textColor: "{colors.safety-panel-text}"
    rounded: "{rounded.md}"
    padding: "12px"
  panel-info:
    backgroundColor: "{colors.info-panel-bg}"
    textColor: "{colors.info-panel-text}"
    rounded: "{rounded.md}"
    padding: "12px"
  panel-good:
    backgroundColor: "{colors.good-panel-bg}"
    textColor: "{colors.good-panel-text}"
    rounded: "{rounded.md}"
    padding: "12px"
  media-well:
    backgroundColor: "{colors.media-well}"
    textColor: "{colors.media-text}"
    rounded: "{rounded.md}"
  stepper-pill-current:
    backgroundColor: "{colors.stage-current-bg}"
    textColor: "{colors.stage-current-text}"
    rounded: "{rounded.sm}"
    padding: "1px 8px"
---

# Design System: Vulture

<!-- Source of truth: src/vulture/ui/theme.py (tokens, helpers) and src/vulture/ui/common.py (shared primitives). Light-scheme values are listed unsuffixed; every scheme-keyed table in theme.py also carries a dark set, chosen at runtime by scheme_name(). The dark sets of SEMANTIC_PANEL_COLORS, CALIBRATION_STAGE_COLORS and SUMMARY_POSTURE_PALETTES live in theme.py and are normative there. -->

## Overview

**Creative North Star: "The Calm Coach"**

Vulture is a native Qt Widgets desktop tool used mostly in Operate mode: it sits next to a work session, watches posture through a local camera, and invites short breaks. The interface wears the platform's own skin (Fusion or the desktop style, honouring the user's UI font and colour scheme) and adds only a thin layer of its own: one filled primary action per surface, quiet flat text actions, hairline-bordered calm wells, dark media wells, and tinted semantic panels. Read-mode text (exercise steps, the Evidence window, safety notes) uses the same UI font, with a relaxed 138% line height and list markers flush with the copy.

The tone is a coach, not an alarm. Posture states never use alarm red: attention is a deep ochre, deviations are earth, plum and teal tones, and red is kept for real failures. The UI invites instead of warning. It celebrates breaks: the Workday summary leads with breaks taken, minutes moved and eye breaks, and puts tracked posture time after them. Wording is plain and in sentence case: "nudge", "Posture drifting", "posture example", "Pause camera". States are never written in ALL CAPS.

Presentation follows the length of the task. Short flows (calibration, setup choices) open in a side panel next to the live camera preview. Movement and rest breaks take over the window as a centred break column (at most 760px wide), with the camera workspace hidden. Settings, Workday summary and Evidence open as separate windows.

**Key Characteristics:**
- Native platform look; tokens add emphasis, not decoration.
- One filled primary action per surface; everything else uses the platform style or a flat text button.
- Calm palette: no red for posture, ochre for attention, red only for real errors.
- Accessibility floor: text at least 12px, controls at least 28px tall, every text pair at WCAG AA (4.5:1), visible 2px focus rings.
- Panels arriving in the background never take keyboard focus.

## Colors

A cool, low-chroma working palette. A single deep blue carries the action, warm tints carry notes, and earth tones replace red wherever posture is described.

### Primary
- **Steady Harbour Blue** (primary-action; dark scheme: primary-action-dark): the fill of the one primary button on a surface ("Start", "Add camera setup"). Hover and pressed go one and two steps deeper (lighter in the dark scheme). The text pair clears 6.8:1 in light and 9.8:1 in dark. Fusion's default highlight fill with white text (3.7:1) is not used for this.

### Secondary
- **Tracker state set** (state-*): the status dot, status pill and tray icon. Stopped, low confidence and camera unavailable share Slate (state-stopped). Calibrating is blue, good is forest green, warning is light gold with dark text (state-on-warning), and alert is **Deep Ochre** (state-alert-ochre), which reads as "attention" and never as danger. Uncalibrated is violet. All other fills take state-on-fill text.
- **Exercise Badge Gold** (exercise-badge): the dot drawn on the tray and taskbar icon while a movement is waiting.

### Tertiary
- **Workday posture palette** (posture-*): used only in the summary charts and bars. Baseline is a quiet blue. Forward head is olive, slouch clay, shoulders sunk brown, lateral lean teal, other drift plum, and "other tracked postures" amber. Adjacent stack slots alternate light and dark so they stay distinct under colour-vision deficiency. Bars sit 2px apart, and a legend and table views identify the series too. The palette was checked with the dataviz validator in both schemes.

### Neutral
- **Window, text and borders**: these come from the platform palette, not from hex values. The **calm well** surface is the window colour blended 55% toward white (light) or 22% toward black (dark). Borders are Mid blended 25% toward Window. Muted copy uses the themed PlaceholderText colour when it is opaque, and otherwise a 28% blend of text into window.
- **Media Well Ink** (media-well, media-text): camera and exercise footage wells stay dark in both schemes, so footage never sits in a bright letterbox.
- **Semantic panels** (info / safety / good / unwanted / error, each with background, text and border): info is cool grey. Safety is a quiet warm parchment, a note and not an alarm. Good is pale green. Unwanted frames a calibration example, not a fault. Error is pale rose and is used only for real failures.
- **Calibration stage tints** (stage-*): current is sky, recorded is mint, retry is apricot, skipped is grey. Pending steps are transparent with a muted hairline.
- **Links** (link, link-visited, plus dark variants): underlined links in rich-text browsers.

### Named Rules
**The No Alarm Red Rule.** No posture state, deviation or reminder uses red. Attention is Deep Ochre, deviations use earth, plum and teal, and the red-family error panel is only for real failures (a camera that cannot open, a write that failed).

**The Single Source Rule.** Hex values live in theme.py only. Surfaces read scheme-keyed tables through scheme_name() and re-apply on PaletteChange, so both colour schemes stay correct when the system theme changes at runtime.

**The AA Pair Rule.** Every foreground/background pair in the tables meets 4.5:1 for small text. A new pair is not added without measuring it in both schemes.

## Typography

**Display Font:** the platform UI font, with tabular figures
**Body Font:** the platform UI font (QApplication.font())

**Character:** one family with no imported faces. Sizes step up from the user's desktop font, so Vulture follows their size and accessibility settings. Hierarchy comes from weight (DemiBold 600 against Normal 400) and small point steps, not from a second typeface.

### Hierarchy
- **Display** (600, base +8pt, tabular figures): timers and big counts, such as "20:00 until next break". The break-panel countdown is Display at 2.5x so it can be read from across the room.
- **Title** (600, base +3pt): window and panel titles, such as "Movement break: Easy desk-side walk".
- **Heading** (600, base +1pt): section headings and the completion note.
- **Body** (400, base; 138% line height in rich text): instructions, exercise steps, Evidence text.
- **Body strong** (600, base): lead-ins inside panels ("Safety:", "Private by design:") and summary metric values.
- **Caption** (400, base size, muted colour): card titles, the "suggested" label under a countdown, footnotes. Captions are quieter through colour, not size.

### Named Rules
**The 12px Floor Rule.** No text drops below 9pt or 12px. Captions get quieter through colour because one step smaller falls under 12px on common 9pt desktop fonts.

**The Steady Digits Rule.** Every counting number uses the Display role with tabular figures, so a ticking timer never moves the layout. Do not use the system monospace font for numbers.

**The Sentence Case Rule.** Labels, buttons and states are written in sentence case with plain words. No ALL-CAPS state names and no letter-spaced labels.

## Layout

Margins and gaps come from one 4/8/12/16/24 scale: window margin, section spacing and card padding are 12px, control spacing is 8px, nested indent is 24px, and list indent is 12px. The main window stacks the Next break card, the camera workspace (a dark media well), the privacy note, and a footer row (Workday summary, Evidence and safety, and the "not a medical device" caption). Settings is a top-right flat action.

- **Side panel** (minimum 380px, with the workspace kept at least 340px): short flows next to the live preview. Esc closes it, or acts as "Later" for a movement. A form panel such as Add setup has one exit: the header Close (or Esc).
- **Break mode**: movement and rest breaks hide the camera workspace and centre one column of at most 760px. The header has only the title (its flat action is hidden); exits are "Not now", Stop early while timing, and Esc. Then come the countdown, the steps and media, the safety note, and the footer: one primary action on the left and a "Not now" menu on the right, above a hairline.
- **Separate windows**: Settings (tabs, scrollable pages), Workday summary (Day overview / Timeline / 7-day report tabs; break metric tiles come before posture), and Evidence (rich text, opening at 640x600).
- Media keeps a 16:9 ratio with a 150px minimum height. Exercise video letterboxes rather than making the panel scroll.
- Labels of mixed sizes in a row share one baseline (align_first_baseline).

## Elevation & Depth

The system is flat and uses no shadows. Depth comes from tone: the calm well sits one step away from the window background and is outlined with a 1px hairline. Media wells are a fixed dark ink. Semantic panels are tinted. Hairline separators divide header, body and footer regions.

### Named Rules
**The Flat Tonal Rule.** Surfaces are separated by a one-step tonal shift and a hairline, never by a drop shadow or bevel that the system adds itself.

## Shapes

There are two radii. Gentle 8px corners (rounded.md) go on containers: cards, semantic panels, media wells, the summary metric tiles, and the stepper focus frame. Tighter 4px corners (rounded.sm) go on controls: buttons, stepper pills and progress chunks. Borders are 1px hairlines. Focus rings are 2px. Primary and flat buttons always carry a transparent 2px border, so the label does not move when the focus ring appears. Progress tracks are one spacing step (8px) tall.

## Components

### Buttons
- **Shape:** tight corners (4px), at least 28px tall. ControlMetricsStyle enforces the height for push buttons, tool buttons, combos, line edits and spin boxes while keeping the platform look.
- **Primary:** Steady Harbour Blue fill with white text (in dark: pale blue with near-black text), 12px horizontal padding. There is one per surface. On break panels it moves through "Start", then "Stop early", then "Done".
- **Hover / Focus:** hover and pressed step the fill deeper. Keyboard focus draws a 2px ring in the window text colour. Disabled is a 12% text tint with muted label text.
- **Flat action:** transparent at rest with 8px padding. Hover shows the calm-well fill and a hairline, and focus shows the 2px text-colour ring. Used for toolbar Settings and panel-header Later and Close.
- **Everything else:** platform-default push buttons with mnemonics. assign_mnemonics picks a unique letter per sibling so translated labels keep their access keys.

### Cards / Containers
- **Corner Style:** gentle (8px).
- **Background:** the calm well (surface_color), with a 1px border_color hairline.
- **Shadow Strategy:** none (see Elevation & Depth).
- **Internal Padding:** 12px, with 8px between rows. The header row holds a muted caption title and an optional trailing action, such as "Move now".

### Semantic panels (SemanticLabel)
A tinted, word-wrapped label in one of five tones (info, safety, good, unwanted, error), with an 8px radius, 12px padding and a 1px tone border. It can be set to strong weight. Break panels show safety once: one exercise-specific line led by "Safety:", followed by the general movement policy. The completion note ("good" tone, Heading role) shows for 1.5s after Done.

### Inputs / Fields
These are platform-native (combos, spin boxes, line edits, check boxes) at the 28px minimum height. Feedback appears in a safety-tone SemanticLabel next to the control, not in a modal.

### Navigation
Settings and the Workday summary use native QTabWidget tabs. Keyboard access is on par with mouse access: Ctrl+, opens Settings (or the platform Preferences key), Ctrl+Shift+S opens the Workday summary, Ctrl+Shift+P pauses the camera, F1 opens Evidence and safety, and Esc dismisses the side panel. Tooltips show the native shortcut through shortcut_hint, for example "Workday summary (Ctrl+Shift+S)".

### Calibration stepper
A focusable row of 4px pills, one per stage. Each is tinted by stage status and labelled with its number and a state marker. A "Step n of m" counter goes with it. Each pill carries a full accessible name ("Step 2: Head forward, recorded"), and the row carries a combined description.

### Break countdown
Display role at 2.5x, centred, with a "suggested" caption and an 8px progress bar that stays hidden until Start, because an empty bar reads as a stalled task. Its accessible name is fixed ("Time remaining"). It speaks once at one minute left and once at completion, never every second.

### Workday summary tiles and bars
Metric tiles are 8px-radius wells with a bold value over a label. Break tiles come first. Posture bars are 8px-tall rounded progress tracks filled from the posture palette, beside a duration and a percentage.

## Do's and Don'ts

### Do:
- **Do** take every size, gap, radius and colour from theme.py. Add a token there before using a new value.
- **Do** give each surface exactly one primary_button_style() action. On break panels, set primary emphasis without making the button a default button (setDefault(False), setAutoDefault(False)), so a stray Enter cannot complete a break.
- **Do** use Deep Ochre for attention and the earth, plum and teal posture set for deviations.
- **Do** keep text at 12px or larger, controls at 28px or taller, and every new text pair at 4.5:1 or better in both schemes.
- **Do** announce state changes politely through common.announce, without moving focus, and only at meaningful moments (start, one minute left, done).
- **Do** raise background arrivals with WA_ShowWithoutActivating and QApplication.alert, so keyboard focus stays where the user is typing.
- **Do** lead the Workday summary with breaks, and use plain sentence-case words: nudge, Posture drifting, posture example, Pause camera.
- **Do** show short flows in the side panel, movement and rest breaks in break mode, and Settings, summary and Evidence as separate windows.

### Don't:
- **Don't** use red, or a red-reading rust, for any posture state or deviation. The error tone is for real failures.
- **Don't** put ALL-CAPS states, alarm wording or "bad posture" phrasing in the UI.
- **Don't** add default buttons to break panels or steal focus from the user's work.
- **Don't** repeat the safety policy more than once per break panel.
- **Don't** shrink captions below body size. Make them quieter through colour.
- **Don't** add shadows, gradients or bevels the platform does not draw.
- **Don't** fill a primary button with the platform Highlight colour and white text (3.7:1 on Fusion).
- **Don't** announce ticking timers every second or give them a changing accessible name.
