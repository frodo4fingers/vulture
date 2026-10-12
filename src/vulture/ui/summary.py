from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta, timezone

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSet,
    QChart,
    QChartView,
    QStackedBarSeries,
    QValueAxis,
)
from PySide6.QtCore import (
    QDate,
    QEvent,
    QLocale,
    Qt,
    Slot,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFontMetrics,
    QPainter,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QProgressBar,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from vulture.breaks import BreakChannel
from vulture.history import (
    BASELINE_POSTURE,
    DailyPostureSummary,
    StoredPostureEpisode,
)
from vulture.i18n import current_language, tr
from vulture.models import InterfaceLanguage, PostureCategory, TrackerState

from .common import SUMMARY_POSTURES, format_duration
from .theme import (
    SUMMARY_POSTURE_PALETTES,
    HAIRLINE,
    RADIUS_MD,
    RADIUS_SM,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
    CaptionLabel,
    TextRole,
    apply_text_role,
)


SUMMARY_OTHER_POSTURES = "other_tracked_postures"
SUMMARY_CHART_BUCKET_SECONDS = 15 * 60
# Charts stay readable but secondary: the break tiles own the first view.
SUMMARY_DAY_CHART_MIN_HEIGHT = 260
SUMMARY_WEEK_CHART_MIN_HEIGHT = 220
_UI_LOCALE_NAMES = {
    InterfaceLanguage.ENGLISH: "en_US",
    InterfaceLanguage.GERMAN: "de_DE",
    InterfaceLanguage.SPANISH: "es_ES",
}
REMINDER_STAGE_TITLES = {
    TrackerState.GOOD: "No nudge",
    TrackerState.WARNING: "Gentle nudge",
    TrackerState.ALERT: "Notification",
}


@dataclass(frozen=True, slots=True)
class PostureAreaData:
    start_hour: float
    end_hour: float
    bucket_hours: tuple[float, ...]
    minutes_by_posture: dict[str, tuple[float, ...]]


@dataclass(frozen=True, slots=True)
class RollingWeekData:
    start_date: date
    end_date: date
    dates: tuple[date, ...]
    daily_totals: tuple[dict[str, float], ...]
    daily_reminders: tuple[int, ...]
    totals: dict[str, float]
    tracked_seconds: float
    reminder_count: int
    days_with_data: int
    daily_breaks: tuple[int, ...] = ()
    break_count: int = 0
    minutes_moved: int = 0


@dataclass(frozen=True, slots=True)
class DailyBreakStats:
    count: int
    minutes_moved: int
    eye_breaks: int


def daily_break_stats(summary: DailyPostureSummary) -> DailyBreakStats:
    moved_seconds = sum(
        event.duration_seconds
        for event in summary.breaks
        if event.kind == "movement"
    )
    return DailyBreakStats(
        count=len(summary.breaks),
        minutes_moved=int(moved_seconds / 60 + 0.5),
        eye_breaks=sum(
            event.channel == BreakChannel.EYE for event in summary.breaks
        ),
    )


def ui_locale() -> QLocale:
    """Locale of the chosen UI language, not of the operating system."""
    return QLocale(_UI_LOCALE_NAMES[current_language()])


def _clock_label(hours: float) -> str:
    minutes = round(hours * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def summary_posture_color(
    posture: str,
    palette: QPalette,
) -> QColor:
    palette_name = (
        "dark"
        if palette.color(QPalette.ColorRole.Window).lightness() < 128
        else "light"
    )
    fallback = PostureCategory.GENERAL_DEVIATION.value
    return QColor(
        SUMMARY_POSTURE_PALETTES[palette_name].get(
            posture,
            SUMMARY_POSTURE_PALETTES[palette_name][fallback],
        )
    )


def _normalized_posture_totals(
    summary: DailyPostureSummary,
) -> dict[str, float]:
    totals = {
        posture: 0.0
        for posture, _title in SUMMARY_POSTURES
    }
    fallback = PostureCategory.GENERAL_DEVIATION.value
    for posture, duration in summary.totals.items():
        target = posture if posture in totals else fallback
        totals[target] += duration
    return totals


def break_summary_text(stats: DailyBreakStats) -> str:
    return tr(
        "Breaks: {count}; minutes moved: {minutes}; eye breaks: {eye}.",
        count=stats.count,
        minutes=stats.minutes_moved,
        eye=stats.eye_breaks,
    )


def break_headline(count: int, minutes: int, period: str) -> str:
    """One sentence for the break tiles; period is today, day or week."""
    if period == "today":
        if count == 1:
            return tr(
                "{breaks} break, {minutes} min moved today.",
                breaks=count,
                minutes=minutes,
            )
        return tr(
            "{breaks} breaks, {minutes} min moved today.",
            breaks=count,
            minutes=minutes,
        )
    if period == "week":
        if count == 1:
            return tr(
                "{breaks} break, {minutes} min moved this week.",
                breaks=count,
                minutes=minutes,
            )
        return tr(
            "{breaks} breaks, {minutes} min moved this week.",
            breaks=count,
            minutes=minutes,
        )
    if count == 1:
        return tr(
            "{breaks} break, {minutes} min moved that day.",
            breaks=count,
            minutes=minutes,
        )
    return tr(
        "{breaks} breaks, {minutes} min moved that day.",
        breaks=count,
        minutes=minutes,
    )


def build_rolling_week_data(
    end_date: date,
    summaries: tuple[DailyPostureSummary, ...],
) -> RollingWeekData:
    if len(summaries) != 7:
        raise ValueError("A rolling week requires exactly seven summaries.")

    dates = tuple(
        end_date - timedelta(days=offset)
        for offset in range(6, -1, -1)
    )
    daily_totals = tuple(
        _normalized_posture_totals(summary)
        for summary in summaries
    )
    totals = {
        posture: sum(day[posture] for day in daily_totals)
        for posture, _title in SUMMARY_POSTURES
    }
    daily_breaks = tuple(len(summary.breaks) for summary in summaries)
    return RollingWeekData(
        start_date=dates[0],
        end_date=end_date,
        dates=dates,
        daily_totals=daily_totals,
        daily_reminders=tuple(
            summary.reminder_count
            for summary in summaries
        ),
        totals=totals,
        tracked_seconds=sum(totals.values()),
        reminder_count=sum(
            summary.reminder_count
            for summary in summaries
        ),
        days_with_data=sum(
            bool(
                summary.tracked_seconds
                or summary.episodes
                or summary.reminder_count
                or summary.breaks
            )
            for summary in summaries
        ),
        daily_breaks=daily_breaks,
        break_count=sum(daily_breaks),
        minutes_moved=sum(
            daily_break_stats(summary).minutes_moved
            for summary in summaries
        ),
    )


def build_posture_area_data(
    summary: DailyPostureSummary,
) -> PostureAreaData | None:
    episode_bounds: list[tuple[StoredPostureEpisode, float, float]] = []
    for episode in summary.episodes:
        local_timezone = timezone(
            timedelta(minutes=episode.utc_offset_minutes)
        )
        local_start = episode.started_at.astimezone(local_timezone)
        seconds_from_midnight = (
            (local_start.date() - summary.local_date).days * 86_400
            + local_start.hour * 3_600
            + local_start.minute * 60
            + local_start.second
            + local_start.microsecond / 1_000_000
        )
        started_at = max(0.0, min(86_400.0, seconds_from_midnight))
        ended_at = min(
            86_400.0,
            started_at + episode.duration_seconds,
        )
        if ended_at > started_at:
            episode_bounds.append((episode, started_at, ended_at))

    if not episode_bounds:
        return None

    first_second = min(
        started_at
        for _episode, started_at, _end in episode_bounds
    )
    last_second = max(ended_at for _episode, _start, ended_at in episode_bounds)
    # Columns start and stop at the first and last bucket that hold data, so
    # the chart never shows a tail past the last recorded sample.
    chart_start = (
        math.floor(first_second / SUMMARY_CHART_BUCKET_SECONDS)
        * SUMMARY_CHART_BUCKET_SECONDS
    )
    chart_end = (
        math.ceil(last_second / SUMMARY_CHART_BUCKET_SECONDS)
        * SUMMARY_CHART_BUCKET_SECONDS
    )
    if chart_end <= chart_start:
        chart_end = chart_start + SUMMARY_CHART_BUCKET_SECONDS

    bucket_count = max(
        1,
        math.ceil(
            (chart_end - chart_start) / SUMMARY_CHART_BUCKET_SECONDS
        ),
    )
    minutes_by_posture = {
        posture: [0.0] * bucket_count
        for posture, _title in SUMMARY_POSTURES
    }
    known_postures = set(minutes_by_posture)
    fallback_posture = PostureCategory.GENERAL_DEVIATION.value

    for episode, started_at, ended_at in episode_bounds:
        posture = (
            episode.posture
            if episode.posture in known_postures
            else fallback_posture
        )
        first_bucket = max(
            0,
            int(
                (started_at - chart_start)
                // SUMMARY_CHART_BUCKET_SECONDS
            ),
        )
        last_bucket = min(
            bucket_count - 1,
            math.ceil(
                (ended_at - chart_start)
                / SUMMARY_CHART_BUCKET_SECONDS
            )
            - 1,
        )
        for bucket_index in range(first_bucket, last_bucket + 1):
            bucket_start = (
                chart_start
                + bucket_index * SUMMARY_CHART_BUCKET_SECONDS
            )
            bucket_end = bucket_start + SUMMARY_CHART_BUCKET_SECONDS
            overlap_seconds = max(
                0.0,
                min(ended_at, bucket_end)
                - max(started_at, bucket_start),
            )
            minutes_by_posture[posture][bucket_index] += (
                overlap_seconds / 60
            )

    return PostureAreaData(
        start_hour=chart_start / 3_600,
        end_hour=chart_end / 3_600,
        bucket_hours=tuple(
            (
                chart_start
                + (bucket_index + 0.5) * SUMMARY_CHART_BUCKET_SECONDS
            )
            / 3_600
            for bucket_index in range(bucket_count)
        ),
        minutes_by_posture={
            posture: tuple(minutes)
            for posture, minutes in minutes_by_posture.items()
        },
    )

class SummaryMetric(QFrame):
    def __init__(
        self,
        caption: str,
        parent: QWidget | None = None,
        *,
        secondary: bool = False,
        display: bool = False,
    ) -> None:
        super().__init__(parent)
        self._caption = caption
        self._applying_style = False
        self.setObjectName("summaryMetric")
        self.setMinimumWidth(120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_XS, SPACE_MD, SPACE_XS)
        layout.setSpacing(0)
        self.value_label = QLabel()
        apply_text_role(
            self.value_label,
            TextRole.DISPLAY
            if display
            else TextRole.BODY_STRONG
            if secondary
            else TextRole.HEADING,
        )
        layout.addWidget(self.value_label)
        self.caption_label = CaptionLabel(caption)
        layout.addWidget(self.caption_label)
        self._apply_palette()

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)
        self.setAccessibleName(f"{self._caption}: {value}")

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.PaletteChange
            and not self._applying_style
        ):
            self._apply_palette()

    def _apply_palette(self) -> None:
        palette = QApplication.palette()
        window = palette.color(QPalette.ColorRole.Window)
        dark = window.lightness() < 128
        surface = palette.color(QPalette.ColorRole.Base)
        border = palette.color(QPalette.ColorRole.Mid)
        if dark:
            surface = surface.lighter(108)
            border = border.lighter(115)
        else:
            surface = surface.darker(102)
            border = border.lighter(108)
        style = (
            "QFrame#summaryMetric {"
            f"background-color: {surface.name()};"
            f"border: {HAIRLINE}px solid {border.name()};"
            f"border-radius: {RADIUS_MD}px;"
            "}"
        )
        self._applying_style = True
        try:
            self.setStyleSheet(style)
        finally:
            self._applying_style = False


class PostureProgressBar(QProgressBar):
    def __init__(
        self,
        posture: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._posture = posture
        self._applying_style = False
        self.setRange(0, 1000)
        self.setTextVisible(False)
        # A slim track, not a stray constant: one spacing step tall.
        self.setFixedHeight(SPACE_SM)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._apply_palette()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.PaletteChange
            and not self._applying_style
        ):
            self._apply_palette()

    def _apply_palette(self) -> None:
        palette = QApplication.palette()
        window = palette.color(QPalette.ColorRole.Window)
        dark = window.lightness() < 128
        track = palette.color(QPalette.ColorRole.AlternateBase)
        if abs(track.lightness() - window.lightness()) < 12:
            track = window.lighter(135) if dark else window.darker(108)
        color = summary_posture_color(self._posture, palette)
        style = (
            "QProgressBar {"
            "border: none;"
            f"background-color: {track.name()};"
            f"border-radius: {RADIUS_SM}px;"
            "}"
            "QProgressBar::chunk {"
            f"background-color: {color.name()};"
            f"border-radius: {RADIUS_SM}px;"
            "}"
        )
        self._applying_style = True
        try:
            self.setStyleSheet(style)
        finally:
            self._applying_style = False


class _StackedColumnChart(QChartView):
    """Stacked columns drawn from the palette: shared styling and clearing."""

    def __init__(self, min_height: int, parent: QWidget | None = None) -> None:
        super().__init__(QChart(), parent)
        self._bar_sets: list[tuple[str, QBarSet]] = []
        self._tooltip_for = None
        self._label_axis: QBarCategoryAxis | None = None
        self._label_sample = ""
        self._label_count = 0
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(min_height)
        self.chart().setBackgroundVisible(False)
        self.chart().setDropShadowEnabled(False)
        self.chart().legend().setAlignment(Qt.AlignmentFlag.AlignBottom)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_palette()

    def _apply_palette(self) -> None:
        chart = self.chart()
        palette = self.palette()
        foreground = palette.color(QPalette.ColorRole.WindowText)
        gap = palette.color(QPalette.ColorRole.Window)
        grid = palette.color(QPalette.ColorRole.Mid)
        grid.setAlpha(70)
        axis_line = QColor(foreground)
        axis_line.setAlpha(135)
        chart.setTitleBrush(QBrush(foreground))
        chart.legend().setLabelColor(foreground)
        for posture, bar_set in self._bar_sets:
            bar_set.setColor(summary_posture_color(posture, palette))
            # A surface-coloured outline leaves a gap between stacked segments.
            bar_set.setPen(QPen(gap, 1.5))
            bar_set.setLabelColor(foreground)
        for axis in chart.axes():
            axis.setLabelsColor(foreground)
            axis.setTitleBrush(QBrush(foreground))
            axis.setLinePenColor(axis_line)
            axis.setGridLineColor(grid)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_labels()

    def _fit_labels(self) -> None:
        """Horizontal category labels when they fit a column, else upright."""
        axis = self._label_axis
        if axis is None or not self._label_count:
            return
        # ponytail: plot width approximated as the view minus axis margins.
        column = (self.width() - 80) / self._label_count
        needed = QFontMetrics(axis.labelsFont()).horizontalAdvance(
            self._label_sample
        )
        # Qt elides a label that fills its whole column, so keep some air.
        axis.setLabelsAngle(0 if column >= needed * 1.4 + SPACE_SM else -90)

    def _set_label_axis(
        self, axis: QBarCategoryAxis, sample: str, count: int
    ) -> None:
        self._label_axis = axis
        self._label_sample = sample
        self._label_count = count
        self._fit_labels()

    @Slot(bool)
    def _on_marker_hover(self, status: bool) -> None:
        # Legend entries elide when crowded; the marker keeps the full text.
        marker = self.sender()
        if status and marker is not None:
            QToolTip.showText(QCursor.pos(), marker.label(), self)
        else:
            QToolTip.hideText()

    def _watch_legend(self) -> None:
        for marker in self.chart().legend().markers():
            marker.hovered.connect(self._on_marker_hover)

    def clear(self) -> None:
        chart = self.chart()
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)
            axis.deleteLater()
        self._label_axis = None
        self._bar_sets.clear()
        chart.setTitle("")
        chart.legend().setVisible(False)

    def _add_bar_set(
        self,
        series: QStackedBarSeries,
        posture: str,
        title: str,
        values: tuple[float, ...],
    ) -> None:
        bar_set = QBarSet(title)
        bar_set.append(values)
        series.append(bar_set)
        self._bar_sets.append((posture, bar_set))

    def _watch_hover(self, series: QStackedBarSeries, tooltip_for) -> None:
        # A bound method, not a lambda: a closure over self keeps the chart
        # alive past Qt's own teardown.
        self._tooltip_for = tooltip_for
        series.hovered.connect(self._on_hover)

    def _on_hover(self, status: bool, index: int, bar_set: QBarSet) -> None:
        if status and self._tooltip_for is not None:
            QToolTip.showText(
                QCursor.pos(),
                self._tooltip_for(index, bar_set.label(), bar_set.at(index)),
                self,
            )
        else:
            QToolTip.hideText()


class PostureAreaChart(_StackedColumnChart):
    """Stacked columns, one per 15-minute bucket (name kept for callers)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(SUMMARY_DAY_CHART_MIN_HEIGHT, parent)
        self.setAccessibleName(
            tr("Posture over time (15-minute intervals)")
        )
        self.setAccessibleDescription(tr("No tracked posture data for this day."))
        self._apply_palette()

    def clear(self) -> None:
        super().clear()
        self.setAccessibleDescription(tr("No tracked posture data for this day."))

    def set_summary(self, summary: DailyPostureSummary) -> None:
        self.clear()
        chart = self.chart()
        area_data = build_posture_area_data(summary)
        if area_data is None:
            chart.setTitle(tr("No tracked posture data for this day."))
            return

        bucket_count = len(area_data.bucket_hours)
        bucket_starts = [
            area_data.start_hour
            + index * SUMMARY_CHART_BUCKET_SECONDS / 3_600
            for index in range(bucket_count)
        ]
        # QBarCategoryAxis drops duplicate categories, so unlabelled columns
        # get a unique run of spaces instead of an empty string.
        categories = [
            f"{round(start * 60) // 60:02d}"
            if round(start * 60) % 60 == 0
            else " " * (index + 1)
            for index, start in enumerate(bucket_starts)
        ]

        def tooltip_for(index: int, name: str, minutes: float) -> str:
            return tr(
                "{start}–{end}  {posture}: {duration}",
                start=_clock_label(bucket_starts[index]),
                end=_clock_label(
                    bucket_starts[index]
                    + SUMMARY_CHART_BUCKET_SECONDS / 3_600
                ),
                posture=name,
                duration=format_duration(minutes * 60),
            )

        series = QStackedBarSeries()
        series.setBarWidth(0.9)
        totals: list[tuple[str, float]] = []
        for posture, title in SUMMARY_POSTURES:
            posture_minutes = area_data.minutes_by_posture[posture]
            if not any(posture_minutes):
                continue
            self._add_bar_set(series, posture, tr(title), posture_minutes)
            totals.append((tr(title), sum(posture_minutes) * 60))
        self._watch_hover(series, tooltip_for)
        chart.addSeries(series)

        x_axis = QBarCategoryAxis()
        x_axis.setTitleText(tr("Time of day"))
        x_axis.append(categories)
        # Whole-hour labels stay horizontal: rotated ones clipped to "⋮".
        x_axis.setLabelsAngle(0)
        y_axis = QValueAxis()
        y_axis.setTitleText(tr("Minutes"))
        y_axis.setRange(0, SUMMARY_CHART_BUCKET_SECONDS / 60)
        y_axis.setTickCount(4)
        y_axis.setLabelFormat("%.0f")

        chart.addAxis(x_axis, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(y_axis, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(x_axis)
        series.attachAxis(y_axis)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        self._watch_legend()
        description = tr(
            "Tracked from {start} to {end}. {details}",
            start=_clock_label(area_data.start_hour),
            end=_clock_label(area_data.end_hour),
            details="; ".join(
                f"{title} {format_duration(seconds)}"
                for title, seconds in totals
            ),
        )
        if summary.breaks:
            description += " " + break_summary_text(daily_break_stats(summary))
        self.setAccessibleDescription(description)
        self._apply_palette()


class RollingWeekChart(_StackedColumnChart):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(SUMMARY_WEEK_CHART_MIN_HEIGHT, parent)
        self.setAccessibleName(tr("Rolling 7-day posture report"))
        self.setAccessibleDescription(
            tr("No tracked posture data in this 7-day window.")
        )
        self._apply_palette()

    def clear(self) -> None:
        super().clear()
        self.setAccessibleDescription(
            tr("No tracked posture data in this 7-day window.")
        )

    def set_summary(self, summary: RollingWeekData) -> None:
        self.clear()
        chart = self.chart()
        if summary.tracked_seconds <= 0:
            chart.setTitle(
                tr("No tracked posture data in this 7-day window.")
            )
            self._apply_palette()
            return

        locale = ui_locale()
        day_labels = [
            locale.toString(QDate(v.year, v.month, v.day), "ddd d")
            for v in summary.dates
        ]
        series = QStackedBarSeries()
        series.setBarWidth(0.72)
        weekly_sets = (
            (
                BASELINE_POSTURE,
                tr("Within baseline"),
                tuple(
                    day[BASELINE_POSTURE] / 60
                    for day in summary.daily_totals
                ),
            ),
            (
                SUMMARY_OTHER_POSTURES,
                tr("Other tracked postures"),
                tuple(
                    sum(
                        duration
                        for posture, duration in day.items()
                        if posture != BASELINE_POSTURE
                    )
                    / 60
                    for day in summary.daily_totals
                ),
            ),
        )
        def tooltip_for(index: int, name: str, minutes: float) -> str:
            return tr(
                "{day}  {posture}: {duration}",
                day=day_labels[index],
                posture=name,
                duration=format_duration(minutes * 60),
            )

        for posture, title, values in weekly_sets:
            if not any(values):
                continue
            self._add_bar_set(series, posture, title, values)
        self._watch_hover(series, tooltip_for)
        chart.addSeries(series)

        date_axis = QBarCategoryAxis()
        date_axis.append(day_labels)
        minutes_axis = QValueAxis()
        minutes_axis.setTitleText(tr("Minutes"))
        maximum_minutes = max(
            sum(day.values()) / 60
            for day in summary.daily_totals
        )
        rounded_maximum = max(
            30,
            math.ceil(maximum_minutes / 30) * 30,
        )
        minutes_axis.setRange(0, rounded_maximum)
        minutes_axis.setTickCount(5)
        minutes_axis.setLabelFormat("%.0f")

        chart.addAxis(date_axis, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(minutes_axis, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(date_axis)
        series.attachAxis(minutes_axis)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop)
        self._watch_legend()
        self._set_label_axis(
            date_axis,
            max(day_labels, key=len),
            len(day_labels),
        )
        description = tr(
            "Last 7 days. {details}",
            details="; ".join(
                tr(
                    "{day}: {tracked} tracked, {baseline} within baseline",
                    day=label,
                    tracked=format_duration(sum(totals.values())),
                    baseline=format_duration(totals[BASELINE_POSTURE]),
                )
                for label, totals in zip(
                    day_labels, summary.daily_totals, strict=True
                )
                if sum(totals.values()) > 0
            ),
        )
        if summary.break_count:
            description += " " + tr(
                "Breaks per day: {details}.",
                details="; ".join(
                    f"{label} {count}"
                    for label, count in zip(
                        day_labels, summary.daily_breaks, strict=True
                    )
                ),
            )
        self.setAccessibleDescription(description)
        self._apply_palette()
