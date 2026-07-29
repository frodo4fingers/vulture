from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPalette,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QTextBrowser,
    QWidget,
)

from vulture.history import BASELINE_POSTURE
from vulture.i18n import tr
from vulture.models import PostureCategory, TrackerState


SUMMARY_POSTURES = (
    (BASELINE_POSTURE, "Within baseline"),
    (PostureCategory.FORWARD_HEAD.value, "Head forward"),
    (PostureCategory.SLOUCH.value, "Slouch / crouch"),
    (PostureCategory.SHOULDERS_SUNK.value, "Shoulders sunk"),
    (PostureCategory.LATERAL_LEAN.value, "Lateral lean"),
    (PostureCategory.GENERAL_DEVIATION.value, "Other baseline deviation"),
)
POSTURE_TITLES = dict(SUMMARY_POSTURES)

STATE_COLORS = {
    TrackerState.STOPPED: "#718096",
    TrackerState.CALIBRATING: "#3182ce",
    TrackerState.GOOD: "#2f855a",
    TrackerState.WARNING: "#d69e2e",
    TrackerState.ALERT: "#c53030",
    TrackerState.LOW_CONFIDENCE: "#718096",
    TrackerState.CAMERA_UNAVAILABLE: "#718096",
    TrackerState.UNCALIBRATED: "#805ad5",
}
STATE_FOREGROUND_COLORS = {
    state: "#f7fafc" for state in TrackerState
}
STATE_FOREGROUND_COLORS[TrackerState.WARNING] = "#1a202c"

# Marker drawn on the tray and taskbar icon while a movement is waiting to do.
EXERCISE_BADGE_COLOR = "#ecc94b"

SEMANTIC_PANEL_COLORS = {
    "light": {
        "info": ("#edf2f7", "#1a202c", "#cbd5e0"),
        "safety": ("#fff5f5", "#742a2a", "#feb2b2"),
        "good": ("#f0fff4", "#22543d", "#9ae6b4"),
        "unwanted": ("#fffaf0", "#7b341e", "#fbd38d"),
    },
    "dark": {
        "info": ("#202832", "#edf2f7", "#465463"),
        "safety": ("#351f24", "#ffd9de", "#8f4d59"),
        "good": ("#183326", "#d9f7e5", "#397b55"),
        "unwanted": ("#392d17", "#ffe6b8", "#8d6a2c"),
    },
}


def semantic_panel_style(
    tone: str,
    *,
    strong: bool = False,
) -> str:
    window_color = QApplication.palette().color(
        QPalette.ColorRole.Window
    )
    palette_name = (
        "dark"
        if window_color.lightness() < 128
        else "light"
    )
    background, foreground, border = SEMANTIC_PANEL_COLORS[palette_name][tone]
    weight = "; font-weight: 700" if strong else ""
    return (
        f"background-color: {background}; color: {foreground}; "
        f"border: 1px solid {border}; border-radius: 5px; padding: 9px"
        f"{weight}"
    )


class SemanticLabel(QLabel):
    def __init__(
        self,
        text: str = "",
        *,
        tone: str = "info",
        strong: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._semantic_tone = tone
        self._semantic_strong = strong
        self._applying_semantic_style = False
        self.setWordWrap(True)
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

def set_accessible_link_palette(browser: QTextBrowser) -> None:
    palette = browser.palette()
    base = palette.color(QPalette.ColorRole.Base)
    if base.lightness() < 128:
        link = QColor("#90cdf4")
        visited_link = QColor("#d6bcfa")
    else:
        link = QColor("#2b6cb0")
        visited_link = QColor("#6b46c1")
    palette.setColor(QPalette.ColorRole.Link, link)
    palette.setColor(QPalette.ColorRole.LinkVisited, visited_link)
    browser.setPalette(palette)
    browser.document().setDefaultStyleSheet(
        f"a {{ color: {link.name()}; text-decoration: underline; }}"
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
