"""Design tokens for Vulture's desktop interface.

Every font size, spacing value, radius, and surface colour used by the UI is
defined here so the workspace, its side panel, and every dialog share one
visual system instead of drifting into per-widget adjustments.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProxyStyle,
    QPushButton,
    QStyle,
    QStyleOption,
    QVBoxLayout,
    QWidget,
)


# Spacing scale. Every margin and gap in the UI is one of these steps.
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24

# Structural spacing roles built from the scale.
WINDOW_MARGIN = SPACE_MD
SECTION_SPACING = SPACE_MD
CARD_PADDING = SPACE_MD
CONTROL_SPACING = SPACE_SM
NESTED_INDENT = SPACE_XL
# Ordered-list markers sit flush with the surrounding copy at this indent.
LIST_INDENT = SPACE_MD

# Shape.
RADIUS_SM = 4
RADIUS_MD = 8
HAIRLINE = 1
FOCUS_RING_WIDTH = 2 * HAIRLINE

# Fixed component metrics.
# Every clickable control is at least this tall, so targets stay comfortable
# regardless of the platform style's defaults.
CONTROL_MIN_HEIGHT = 28
SETUP_SELECTOR_WIDTH = 260
MEDIA_ASPECT_RATIO = 16 / 9
MEDIA_MIN_HEIGHT = 150

# Minimum and opening sizes of panels and dialogs.
PANEL_MIN_WIDTH = 500
REST_PANEL_MIN_SIZE = QSize(440, 360)
EVIDENCE_MIN_SIZE = QSize(440, 420)
EVIDENCE_SIZE = QSize(640, 600)
SETUP_MIN_SIZE = QSize(420, 220)
SETUP_SIZE = QSize(500, 260)
STEP_SELECTION_MIN_SIZE = QSize(480, 420)
STEP_SELECTION_SIZE = QSize(620, 420)
CALIBRATION_MIN_SIZE = QSize(420, 400)
CALIBRATION_SIZE = QSize(560, 700)

# Media wells stay dark in both colour schemes so camera and exercise footage
# is never framed by a bright letterbox.
MEDIA_SURFACE = "#15191f"
MEDIA_TEXT = "#c3ccd8"

# Colour tokens. Vulture is a calm coach: posture states never use alarm red,
# and every foreground/background pair here meets WCAG AA (4.5:1) for small
# text. Hex values live in this module only.
#
# Tracker states (status pill, tray icon), keyed by ``TrackerState`` value so
# this module stays free of model imports.
STATE_COLOR_VALUES = {
    "stopped": "#4a5568",
    "calibrating": "#2b6cb0",
    "good": "#276749",
    "warning": "#d69e2e",
    # Deep ochre: reads as "attention", never as danger, and stays apart from
    # the light gold "warning" fill by lightness (5.65:1 with the light text).
    "alert": "#8a5a00",
    "low_confidence": "#4a5568",
    "camera_unavailable": "#4a5568",
    "uncalibrated": "#6b46c1",
}
STATE_FOREGROUND_LIGHT = "#f7fafc"
STATE_FOREGROUND_DARK = "#1a202c"
# States whose fill is light enough to need dark text.
STATE_DARK_FOREGROUND_STATES = frozenset({"warning"})

# Marker drawn on the tray and taskbar icon while a movement is waiting.
EXERCISE_BADGE_COLOR = "#ecc94b"

# Semantic panels: (background, foreground, border) per scheme and tone.
# "safety" is a quiet, warm note rather than an alarm; "unwanted" frames a
# calibration example, not a fault; "error" is reserved for real failures.
SEMANTIC_PANEL_COLORS = {
    "light": {
        "info": ("#edf2f7", "#1a202c", "#cbd5e0"),
        "safety": ("#fbf7ec", "#5b4a1f", "#e6d8b0"),
        "good": ("#f0fff4", "#22543d", "#9ae6b4"),
        "unwanted": ("#fffaf0", "#7b341e", "#fbd38d"),
        "error": ("#fff5f5", "#742a2a", "#feb2b2"),
    },
    "dark": {
        "info": ("#202832", "#edf2f7", "#465463"),
        "safety": ("#2b2a22", "#f3ead2", "#6b5f3a"),
        "good": ("#183326", "#d9f7e5", "#397b55"),
        "unwanted": ("#392d17", "#ffe6b8", "#8d6a2c"),
        "error": ("#351f24", "#ffd9de", "#8f4d59"),
    },
}

# Calibration stage rows: (background, foreground) per scheme and status.
CALIBRATION_STAGE_COLORS = {
    "light": {
        "current": ("#bee3f8", "#1a365d"),
        "recorded": ("#c6f6d5", "#22543d"),
        "retry": ("#feebc8", "#7b341e"),
        "skipped": ("#e2e8f0", "#2d3748"),
    },
    "dark": {
        "current": ("#2c5282", "#ebf8ff"),
        "recorded": ("#22543d", "#f0fff4"),
        "retry": ("#5f370e", "#fefcbf"),
        "skipped": ("#2d3748", "#e2e8f0"),
    },
}

# Rich-text hyperlinks: (link, visited) per scheme.
LINK_COLORS = {
    "light": ("#2b6cb0", "#6b46c1"),
    "dark": ("#90cdf4", "#d6bcfa"),
}

# Workday summary posture palette per scheme, keyed by posture category value
# (plus "baseline" and "other_tracked_postures"). Owned by the summary surface.
# Calm coach: baseline is a quiet blue and no deviation is red. Forward head
# is olive, slouch clay, shoulders sunk brown, lateral lean teal and the
# general deviation plum, so neighbours and the olive/brown pair stay apart.
# Adjacent stack slots alternate light/dark so they stay apart under
# colour-vision deficiency; the legend, 2px gaps and the table views carry
# identity too. Validated with the dataviz palette validator (adjacent pairs,
# light on #efefef/#ffffff, dark on #171a1f). "Other tracked postures" only
# appears next to baseline in the 7-day chart.
SUMMARY_POSTURE_PALETTES = {
    "light": {
        "baseline": "#287eaf",
        "forward_head": "#566b00",
        "slouch": "#cc7240",
        "shoulders_sunk": "#884f00",
        "lateral_lean": "#25957c",
        "general_deviation": "#7a5c9e",
        "other_tracked_postures": "#a56810",
    },
    "dark": {
        "baseline": "#3c8fc1",
        "forward_head": "#5f7400",
        "slouch": "#d67654",
        "shoulders_sunk": "#955b16",
        "lateral_lean": "#2fa58a",
        "general_deviation": "#9a7cc0",
        "other_tracked_postures": "#ac7d1b",
    },
}

# Primary action fill: (fill, text, hover, pressed) per scheme. Both pairs
# clear 4.5:1 (light 6.8:1, dark 9.8:1); Fusion's default #308cc6 with white
# text does not (3.7:1).
PRIMARY_BUTTON_COLORS = {
    "light": ("#1f5f8f", "#ffffff", "#1a5280", "#144468"),
    "dark": ("#8cc4f0", "#0b1620", "#a3d1f5", "#6aaee4"),
}


class TextRole(Enum):
    """Named steps of the type scale.

    Sizes are expressed relative to the platform's base UI font so the app
    still honours the user's desktop font settings.
    """

    DISPLAY = "display"
    TITLE = "title"
    HEADING = "heading"
    BODY = "body"
    BODY_STRONG = "body_strong"
    CAPTION = "caption"


_ROLE_STEPS = {
    TextRole.DISPLAY: 8,
    TextRole.TITLE: 3,
    TextRole.HEADING: 1,
    TextRole.BODY: 0,
    TextRole.BODY_STRONG: 0,
    # Captions are quieter through colour, not size: one step smaller drops
    # below 12px on common 9pt desktop fonts.
    TextRole.CAPTION: 0,
}

_ROLE_WEIGHTS = {
    TextRole.DISPLAY: QFont.Weight.DemiBold,
    TextRole.TITLE: QFont.Weight.DemiBold,
    TextRole.HEADING: QFont.Weight.DemiBold,
    TextRole.BODY: QFont.Weight.Normal,
    TextRole.BODY_STRONG: QFont.Weight.DemiBold,
    TextRole.CAPTION: QFont.Weight.Normal,
}

_MIN_POINT_SIZE = 9.0
_MIN_PIXEL_SIZE = 12


def _enable_tabular_figures(font: QFont) -> None:
    """Keep counting digits from shifting the layout every second."""
    try:
        font.setFeature(QFont.Tag("tnum"), 1)
    except (AttributeError, TypeError, ValueError):  # pragma: no cover
        pass


def role_font(role: TextRole, base: QFont | None = None) -> QFont:
    base_font = base if base is not None else QApplication.font()
    font = QFont(base_font)
    step = _ROLE_STEPS[role]
    point_size = base_font.pointSizeF()
    if point_size > 0:
        font.setPointSizeF(max(_MIN_POINT_SIZE, point_size + step))
    else:
        pixel_size = base_font.pixelSize()
        scaled = round(pixel_size * (1 + step / 10)) if pixel_size > 0 else 0
        font.setPixelSize(max(_MIN_PIXEL_SIZE, scaled))
    font.setWeight(_ROLE_WEIGHTS[role])
    if role is TextRole.DISPLAY:
        # The UI font with tabular figures: digits keep one width without the
        # typewriter look of the system monospace font.
        _enable_tabular_figures(font)
    return font


def apply_text_role(widget: QWidget, role: TextRole) -> None:
    widget.setFont(role_font(role))


def align_first_baseline(*labels: QLabel) -> None:
    """Pad shorter labels so a row of mixed type sizes shares one baseline.

    Qt aligns widget boxes, not text baselines, so a large number next to a
    small heading otherwise sits a few pixels off the line the eye reads.
    """
    ascents = [QFontMetrics(label.font()).ascent() for label in labels]
    tallest = max(ascents)
    for label, ascent in zip(labels, ascents):
        margins = label.contentsMargins()
        label.setContentsMargins(
            margins.left(),
            tallest - ascent,
            margins.right(),
            margins.bottom(),
        )


def _mix(foreground: QColor, background: QColor, weight: float) -> QColor:
    return QColor(
        round(
            foreground.red() * (1 - weight) + background.red() * weight
        ),
        round(
            foreground.green() * (1 - weight) + background.green() * weight
        ),
        round(
            foreground.blue() * (1 - weight) + background.blue() * weight
        ),
    )


def is_dark_theme(palette: QPalette | None = None) -> bool:
    active = palette or QApplication.palette()
    return active.color(QPalette.ColorRole.Window).lightness() < 128


def scheme_name(palette: QPalette | None = None) -> str:
    """``"dark"`` or ``"light"``: the key of every colour table here."""
    return "dark" if is_dark_theme(palette) else "light"


def muted_color(palette: QPalette | None = None) -> QColor:
    """The colour for secondary copy.

    An explicitly themed ``PlaceholderText`` wins, because that is the role a
    platform theme uses for de-emphasised text. Qt's default is a
    semi-transparent tint of the text colour, which is too faint for small
    copy, so that case falls back to a measured blend.
    """
    active = palette or QApplication.palette()
    placeholder = active.color(QPalette.ColorRole.PlaceholderText)
    if placeholder.alpha() == 255:
        return placeholder
    return _mix(
        active.color(QPalette.ColorRole.WindowText),
        active.color(QPalette.ColorRole.Window),
        0.28,
    )


def border_color(palette: QPalette | None = None) -> QColor:
    active = palette or QApplication.palette()
    return _mix(
        active.color(QPalette.ColorRole.Mid),
        active.color(QPalette.ColorRole.Window),
        0.25,
    )


def surface_color(palette: QPalette | None = None) -> QColor:
    """A calm well that sits one step away from the window background."""
    active = palette or QApplication.palette()
    window = active.color(QPalette.ColorRole.Window)
    if is_dark_theme(active):
        return _mix(window, QColor("#000000"), 0.22)
    return _mix(window, QColor("#ffffff"), 0.55)


def card_style(object_name: str) -> str:
    return (
        f"QFrame#{object_name} {{"
        f" background-color: {surface_color().name()};"
        f" border: {HAIRLINE}px solid {border_color().name()};"
        f" border-radius: {RADIUS_MD}px;"
        " }"
    )


def separator_style() -> str:
    return (
        f"background-color: {border_color().name()}; border: none"
    )


def media_surface_style(*, radius: int = RADIUS_MD) -> str:
    return (
        f"background-color: {MEDIA_SURFACE}; color: {MEDIA_TEXT};"
        f" border-radius: {radius}px"
    )


def _button_rule(state: str, **declarations: str) -> str:
    """One rule for push and tool buttons in ``state`` (``":hover"``...)."""
    selector = f"QPushButton{state}, QToolButton{state}"
    body = "; ".join(
        f"{name.replace('_', '-')}: {value}"
        for name, value in declarations.items()
    )
    return f"{selector} {{ {body} }}"


def primary_button_style() -> str:
    """The one filled action of a surface, at >= 4.5:1 in both schemes.

    Apply with ``button.setStyleSheet(primary_button_style())``. The border is
    always ``FOCUS_RING_WIDTH`` wide (transparent at rest) so showing the focus
    ring never moves the label.
    """
    palette = QApplication.palette()
    fill, text, hover, pressed = PRIMARY_BUTTON_COLORS[scheme_name(palette)]
    window = palette.color(QPalette.ColorRole.Window)
    disabled_fill = _mix(
        palette.color(QPalette.ColorRole.WindowText), window, 0.88
    )
    base = {
        "background_color": fill,
        "color": text,
        "border": f"{FOCUS_RING_WIDTH}px solid transparent",
        "border_radius": f"{RADIUS_SM}px",
        "min_height": f"{CONTROL_MIN_HEIGHT - 2 * FOCUS_RING_WIDTH}px",
        "padding": f"0 {SPACE_MD}px",
    }
    ring = palette.color(QPalette.ColorRole.WindowText).name()
    return " ".join(
        [
            _button_rule("", **base),
            _button_rule(":hover", background_color=hover),
            _button_rule(":pressed", background_color=pressed),
            _button_rule(
                ":focus",
                border=f"{FOCUS_RING_WIDTH}px solid {ring}",
            ),
            _button_rule(
                ":disabled",
                background_color=disabled_fill.name(),
                color=muted_color(palette).name(),
            ),
        ]
    )


def set_primary(button: QPushButton, primary: bool) -> None:
    """Visually emphasise ``button`` without making it a default button.

    Qt has no "primary button" without a default button, and a default
    button lets a stray Enter complete a break, so colour marks it instead.
    """
    button.setAutoDefault(False)
    button.setDefault(False)
    button.setStyleSheet(primary_button_style() if primary else "")


def progress_bar_style() -> str:
    """A thin bar whose empty track stays visible in light and dark."""
    palette = QApplication.palette()
    highlight = palette.color(QPalette.ColorRole.Highlight).name()
    return (
        "QProgressBar {"
        "border: none;"
        f"background-color: {border_color(palette).name()};"
        f"border-radius: {RADIUS_SM}px;"
        "}"
        "QProgressBar::chunk {"
        f"background-color: {highlight};"
        f"border-radius: {RADIUS_SM}px;"
        "}"
    )


def flat_action_style() -> str:
    """A secondary text action drawn as an outlined button.

    For the toolbar Settings button and the panel header Later and Close:
    a hairline in the muted text colour (>= 3:1 on the window) at rest, a
    surface on hover, and a ring on keyboard focus. The resting margin takes
    the ring's extra width so focus never moves the label.
    """
    palette = QApplication.palette()
    window = palette.color(QPalette.ColorRole.Window)
    text = palette.color(QPalette.ColorRole.WindowText)
    hover_fill = surface_color(palette).name()
    base = {
        "background_color": "transparent",
        "border": f"{HAIRLINE}px solid {muted_color(palette).name()}",
        "border_radius": f"{RADIUS_SM}px",
        "margin": f"{FOCUS_RING_WIDTH - HAIRLINE}px",
        "min_height": f"{CONTROL_MIN_HEIGHT - 2 * FOCUS_RING_WIDTH}px",
        "padding": f"0 {SPACE_SM}px",
    }
    return " ".join(
        [
            _button_rule("", **base),
            _button_rule(":hover", background_color=hover_fill),
            _button_rule(
                ":pressed",
                background_color=_mix(window, text, 0.12).name(),
            ),
            _button_rule(
                ":focus",
                border=f"{FOCUS_RING_WIDTH}px solid {text.name()}",
                margin="0",
            ),
            _button_rule(
                ":disabled",
                color=muted_color(palette).name(),
            ),
        ]
    )


class _PaletteAwareMixin:
    """Re-applies palette-derived styling when the colour scheme changes.

    Applying a stylesheet or palette itself raises ``PaletteChange``, so the
    refresh is guarded against re-entering itself.
    """

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() != QEvent.Type.PaletteChange:
            return
        if getattr(self, "_theme_update_active", False):
            return
        self._refresh_theme()

    def _refresh_theme(self) -> None:
        self._theme_update_active = True
        try:
            self._apply_theme()
        finally:
            self._theme_update_active = False

    def _apply_theme(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class CaptionLabel(_PaletteAwareMixin, QLabel):
    """Secondary copy: one step below body text and deliberately quieter."""

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        apply_text_role(self, TextRole.CAPTION)
        self._refresh_theme()

    def _apply_theme(self) -> None:
        palette = self.palette()
        color = muted_color(QApplication.palette())
        palette.setColor(QPalette.ColorRole.WindowText, color)
        palette.setColor(QPalette.ColorRole.Text, color)
        self.setPalette(palette)


class Separator(_PaletteAwareMixin, QFrame):
    """A hairline rule used to group a surface's regions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(HAIRLINE)
        self._refresh_theme()

    def _apply_theme(self) -> None:
        self.setStyleSheet(separator_style())


class Card(_PaletteAwareMixin, QFrame):
    """A titled surface: heading row, optional trailing action, body."""

    OBJECT_NAME = "vultureCard"

    def __init__(
        self,
        title: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(self.OBJECT_NAME)
        self.setFrameShape(QFrame.Shape.NoFrame)
        # Let wrapped copy inside the card grow the card instead of clipping.
        policy = self.sizePolicy()
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            CARD_PADDING,
            CARD_PADDING,
            CARD_PADDING,
            CARD_PADDING,
        )
        outer.setSpacing(CONTROL_SPACING)

        self.header_row = QHBoxLayout()
        self.header_row.setContentsMargins(0, 0, 0, 0)
        self.header_row.setSpacing(CONTROL_SPACING)
        self.title_label = CaptionLabel(title)
        self.title_label.setWordWrap(False)
        self.header_row.addWidget(self.title_label)
        self.header_row.addStretch(1)
        outer.addLayout(self.header_row)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(CONTROL_SPACING)
        outer.addLayout(self.body, 1)

        self._refresh_theme()

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def add_header_action(self, widget: QWidget) -> None:
        self.header_row.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def _apply_theme(self) -> None:
        self.setStyleSheet(card_style(self.OBJECT_NAME))


class ControlMetricsStyle(QProxyStyle):
    """Keeps the platform look but enforces ``CONTROL_MIN_HEIGHT`` targets."""

    _SIZED = frozenset(
        {
            QStyle.ContentsType.CT_PushButton,
            QStyle.ContentsType.CT_ToolButton,
            QStyle.ContentsType.CT_ComboBox,
            QStyle.ContentsType.CT_LineEdit,
            QStyle.ContentsType.CT_SpinBox,
        }
    )

    def sizeFromContents(
        self,
        contents_type: QStyle.ContentsType,
        option: QStyleOption | None,
        size: QSize,
        widget: QWidget | None = None,
    ) -> QSize:
        result = super().sizeFromContents(contents_type, option, size, widget)
        if contents_type in self._SIZED:
            result.setHeight(max(result.height(), CONTROL_MIN_HEIGHT))
        return result


def install_control_metrics(app: QApplication) -> None:
    """Wrap the active platform style once; safe to call repeatedly."""
    if isinstance(app.style(), ControlMetricsStyle):
        return
    app.setStyle(ControlMetricsStyle(app.style().name()))
