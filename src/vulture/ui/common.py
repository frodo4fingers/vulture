from __future__ import annotations

from math import ceil

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import (
    QAccessible,
    QAccessibleAnnouncementEvent,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QPixmap,
    QTextOption,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QSizePolicy,
    QTextBrowser,
    QWidget,
)

from vulture.history import BASELINE_POSTURE
from vulture.i18n import tr
from vulture.models import PostureCategory, TrackerState

from .theme import (
    CARD_PADDING,
    EXERCISE_BADGE_COLOR,
    HAIRLINE,
    LINK_COLORS,
    LIST_INDENT,
    RADIUS_MD,
    SEMANTIC_PANEL_COLORS,
    SPACE_XS,
    STATE_COLOR_VALUES,
    STATE_DARK_FOREGROUND_STATES,
    STATE_FOREGROUND_DARK,
    STATE_FOREGROUND_LIGHT,
    TextRole,
    apply_text_role,
    scheme_name,
)


SUMMARY_POSTURES = (
    (BASELINE_POSTURE, "Within baseline"),
    (PostureCategory.FORWARD_HEAD.value, "Head forward"),
    (PostureCategory.SLOUCH.value, "Slouch / crouch"),
    (PostureCategory.SHOULDERS_SUNK.value, "Shoulders sunk"),
    (PostureCategory.LATERAL_LEAN.value, "Lateral lean"),
    (PostureCategory.GENERAL_DEVIATION.value, "Other drift"),
)
POSTURE_TITLES = dict(SUMMARY_POSTURES)

STATE_COLORS = {
    state: STATE_COLOR_VALUES[state.value] for state in TrackerState
}
STATE_FOREGROUND_COLORS = {
    state: (
        STATE_FOREGROUND_DARK
        if state.value in STATE_DARK_FOREGROUND_STATES
        else STATE_FOREGROUND_LIGHT
    )
    for state in TrackerState
}


def announce(widget: QWidget, message: str) -> None:
    """Have a screen reader speak ``message`` without moving focus."""
    event = QAccessibleAnnouncementEvent(widget, message)
    event.setPoliteness(QAccessible.AnnouncementPoliteness.Polite)
    QAccessible.updateAccessibility(event)


def shortcut_hint(
    text: str, shortcut: QKeySequence | QKeySequence.StandardKey | str
) -> str:
    """``text`` followed by its platform-native shortcut, for tooltips."""
    sequence = (
        shortcut
        if isinstance(shortcut, QKeySequence)
        else QKeySequence(shortcut)
    )
    if sequence.isEmpty():
        return text
    native = sequence.toString(QKeySequence.SequenceFormat.NativeText)
    return f"{text} ({native})"


def set_tooltip_with_shortcut(
    widget: QWidget,
    text: str,
    shortcut: QKeySequence | QKeySequence.StandardKey | str,
) -> None:
    """Tooltip ``text (Ctrl+S)`` with the shortcut in platform-native form."""
    widget.setToolTip(shortcut_hint(text, shortcut))


def semantic_panel_style(
    tone: str,
    *,
    strong: bool = False,
) -> str:
    background, foreground, border = SEMANTIC_PANEL_COLORS[scheme_name()][tone]
    weight = "; font-weight: 600" if strong else ""
    return (
        f"background-color: {background}; color: {foreground}; "
        f"border: {HAIRLINE}px solid {border}; border-radius: {RADIUS_MD}px; "
        f"padding: {CARD_PADDING}px"
        f"{weight}"
    )


class SemanticLabel(QLabel):
    def __init__(
        self,
        text: str = "",
        *,
        tone: str = "info",
        strong: bool = False,
        role: TextRole = TextRole.BODY,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._semantic_tone = tone
        self._semantic_strong = strong
        self._applying_semantic_style = False
        self.setWordWrap(True)
        apply_text_role(self, role)
        self._apply_semantic_style()

    def set_semantic_tone(
        self,
        tone: str,
        *,
        strong: bool | None = None,
    ) -> None:
        self._semantic_tone = tone
        if strong is not None:
            self._semantic_strong = strong
        self._apply_semantic_style()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.PaletteChange
            and not self._applying_semantic_style
        ):
            self._apply_semantic_style()

    def _apply_semantic_style(self) -> None:
        style = semantic_panel_style(
            self._semantic_tone,
            strong=self._semantic_strong,
        )
        if self.styleSheet() == style:
            return
        self._applying_semantic_style = True
        try:
            self.setStyleSheet(style)
        finally:
            self._applying_semantic_style = False


class ContentHeightTextBrowser(QTextBrowser):
    """A read-only text browser that hugs its rendered content height.

    Regular ``QTextBrowser`` widgets reserve their maximum height regardless
    of how little text they hold, which leaves dead vertical space above the
    widgets that follow them. This variant tracks the document layout and its
    own width so it is always exactly as tall as the text it displays.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.viewport().setAutoFillBackground(False)
        self.setStyleSheet("QTextBrowser { background: transparent }")
        self.setWordWrapMode(
            QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
        )
        self.document().setDocumentMargin(0)
        self.document().setIndentWidth(LIST_INDENT)
        self.document().documentLayout().documentSizeChanged.connect(
            lambda *_: self._fit_to_contents()
        )

    def _fit_to_contents(self) -> None:
        document = self.document()
        document.setTextWidth(self.viewport().width())
        height = ceil(document.size().height())
        height += 2 * self.frameWidth() + self.contentsMargins().top()
        height += self.contentsMargins().bottom()
        self.setFixedHeight(height)

    def setHtml(self, text: str) -> None:  # noqa: A003 - Qt override
        super().setHtml(text)
        self._fit_to_contents()

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)
        self._fit_to_contents()


def rich_text_document_style(link: QColor | None = None) -> str:
    """Shared typography for the read-only rich-text surfaces.

    Qt indents ordered and unordered lists far past the surrounding copy by
    default, which breaks the left edge every other block sits on.
    """
    rules = [
        "p, li { line-height: 138%; }",
        "ol, ul { -qt-list-indent: 1; margin-left: 0px; "
        "margin-top: 0px; margin-bottom: 0px; }",
        "li { margin-bottom: " + str(SPACE_XS) + "px; }",
        "h2 { margin-top: 0px; }",
    ]
    if link is not None:
        rules.append(
            f"a {{ color: {link.name()}; text-decoration: underline; }}"
        )
    return " ".join(rules)


def set_accessible_link_palette(browser: QTextBrowser) -> None:
    palette = browser.palette()
    base = palette.color(QPalette.ColorRole.Base)
    link_hex, visited_hex = LINK_COLORS[
        "dark" if base.lightness() < 128 else "light"
    ]
    link = QColor(link_hex)
    visited_link = QColor(visited_hex)
    palette.setColor(QPalette.ColorRole.Link, link)
    palette.setColor(QPalette.ColorRole.LinkVisited, visited_link)
    browser.setPalette(palette)
    browser.document().setDefaultStyleSheet(
        rich_text_document_style(link)
    )


def format_duration(seconds: float) -> str:
    rounded = max(0, round(seconds))
    hours, remainder = divmod(rounded, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    if hours:
        return tr(
            "{hours}h {minutes:02d}m",
            hours=hours,
            minutes=minutes,
        )
    if minutes:
        return tr(
            "{minutes}m {seconds:02d}s",
            minutes=minutes,
            seconds=remaining_seconds,
        )
    return tr("{seconds}s", seconds=remaining_seconds)


def create_state_icon(
    state: TrackerState, size: int = 64, *, badge: bool = False
) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(STATE_COLORS[state]))
    painter.drawEllipse(3, 3, size - 6, size - 6)
    painter.setPen(QColor("white"))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(round(size * 0.50))
    painter.setFont(font)
    painter.drawText(
        pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "V"
    )
    if badge:
        diameter = round(size * 0.42)
        left = size - diameter
        top = 0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(
            left - 2, top, diameter + 4, diameter + 4
        )
        painter.setBrush(QColor(EXERCISE_BADGE_COLOR))
        painter.drawEllipse(left, top + 2, diameter, diameter)
    painter.end()
    return QIcon(pixmap)
