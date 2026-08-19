"""Design tokens for Vulture's desktop interface.

Every font size, spacing value, radius, and surface colour used by the UI is
defined here so the workspace, its side panel, and every dialog share one
visual system instead of drifting into per-widget adjustments.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
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
LIST_INDENT = 13

# Shape.
RADIUS_SM = 4
RADIUS_MD = 8
HAIRLINE = 1

# Fixed component metrics.
STATUS_DOT_SIZE = 40
SETUP_SELECTOR_WIDTH = 260
MEDIA_ASPECT_RATIO = 16 / 9
MEDIA_MIN_HEIGHT = 180

# Media wells stay dark in both colour schemes so camera and exercise footage
# is never framed by a bright letterbox.
MEDIA_SURFACE = "#15191f"
MEDIA_TEXT = "#c3ccd8"


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
    TextRole.CAPTION: -1,
}

_ROLE_WEIGHTS = {
    TextRole.DISPLAY: QFont.Weight.DemiBold,
    TextRole.TITLE: QFont.Weight.DemiBold,
    TextRole.HEADING: QFont.Weight.DemiBold,
    TextRole.BODY: QFont.Weight.Normal,
    TextRole.BODY_STRONG: QFont.Weight.DemiBold,
    TextRole.CAPTION: QFont.Weight.Normal,
}

_MIN_POINT_SIZE = 7.0
_MIN_PIXEL_SIZE = 9


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
        fixed_family = QFontDatabase.systemFont(
            QFontDatabase.SystemFont.FixedFont
        ).family()
        font.setFamilies([fixed_family, *base_font.families()])
        font.setStyleHint(QFont.StyleHint.Monospace)
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
        0.38,
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
