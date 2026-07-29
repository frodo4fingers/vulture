from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta, timezone

from PySide6.QtCharts import (
    QAreaSeries,
    QBarCategoryAxis,
    QBarSet,
    QCategoryAxis,
    QChart,
    QChartView,
    QLineSeries,
    QStackedBarSeries,
    QValueAxis,
)
from PySide6.QtCore import (
    QDate,
    QEvent,
    QLocale,
    Qt,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget

from vulture.history import (
    BASELINE_POSTURE,
    DailyPostureSummary,
    StoredPostureEpisode,
)
from vulture.i18n import tr
from vulture.models import PostureCategory, TrackerState

from .common import SUMMARY_POSTURES


SUMMARY_OTHER_POSTURES = "other_tracked_postures"
SUMMARY_POSTURE_PALETTES = {
    "light": {
        BASELINE_POSTURE: "#34A853",
        PostureCategory.FORWARD_HEAD.value: "#4285F4",
        PostureCategory.SLOUCH.value: "#EA4335",
        PostureCategory.SHOULDERS_SUNK.value: "#FBBC04",
        PostureCategory.LATERAL_LEAN.value: "#A142F4",
        PostureCategory.GENERAL_DEVIATION.value: "#12B5CB",
        SUMMARY_OTHER_POSTURES: "#4285F4",
    },
    "dark": {
        BASELINE_POSTURE: "#81C995",
        PostureCategory.FORWARD_HEAD.value: "#8AB4F8",
        PostureCategory.SLOUCH.value: "#F28B82",
        PostureCategory.SHOULDERS_SUNK.value: "#FDD663",
        PostureCategory.LATERAL_LEAN.value: "#C58AF9",
        PostureCategory.GENERAL_DEVIATION.value: "#78D9EC",
        SUMMARY_OTHER_POSTURES: "#8AB4F8",
    },
}
SUMMARY_CHART_BUCKET_SECONDS = 15 * 60
REMINDER_STAGE_TITLES = {
    TrackerState.GOOD: "No reminder",
    TrackerState.WARNING: "Warning",
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
            )
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
    chart_start = math.floor(first_second / 3_600) * 3_600
    chart_end = math.ceil(last_second / 3_600) * 3_600
    if chart_end <= chart_start:
        chart_end = min(86_400, chart_start + 3_600)

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
    ) -> None:
        super().__init__(parent)
        self._caption = caption
        self._applying_style = False
        self.setObjectName("summaryMetric")
        self.setMinimumWidth(120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(1)
        self.value_label = QLabel()
        value_font = self.value_label.font()
        value_font.setBold(True)
        value_font.setPointSize(max(13, value_font.pointSize() + 3))
        self.value_label.setFont(value_font)
        layout.addWidget(self.value_label)
        self.caption_label = QLabel(caption)
        layout.addWidget(self.caption_label)
        self._apply_palette()

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)
        self.setAccessibleName(self._caption)
        self.setAccessibleDescription(value)

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
            f"border: 1px solid {border.name()};"
            "border-radius: 6px;"
            "}"
        )
        caption_palette = QPalette(palette)
        caption_palette.setColor(
            QPalette.ColorRole.WindowText,
            palette.color(QPalette.ColorRole.PlaceholderText),
        )
        self._applying_style = True
        try:
            self.setStyleSheet(style)
            self.caption_label.setPalette(caption_palette)
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
        self.setFixedHeight(9)
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
            "border-radius: 4px;"
            "}"
            "QProgressBar::chunk {"
            f"background-color: {color.name()};"
            "border-radius: 4px;"
            "}"
        )
        self._applying_style = True
        try:
            self.setStyleSheet(style)
        finally:
            self._applying_style = False


class PostureAreaChart(QChartView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(QChart(), parent)
        self._area_series: list[tuple[str, QAreaSeries]] = []
        self._boundary_series: list[QLineSeries] = []
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(220)
        self.setAccessibleName(
            tr("Posture over time (15-minute intervals)")
        )
        self.setAccessibleDescription(tr("Tracked posture time"))
        self.chart().setBackgroundVisible(False)
        self.chart().setDropShadowEnabled(False)
        self.chart().legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        self._apply_palette()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_palette()

    def _apply_palette(self) -> None:
        chart = self.chart()
        foreground = self.palette().color(QPalette.ColorRole.WindowText)
        grid = self.palette().color(QPalette.ColorRole.Mid)
        grid.setAlpha(70)
        axis_line = QColor(foreground)
        axis_line.setAlpha(135)
        chart.setTitleBrush(QBrush(foreground))
        chart.legend().setLabelColor(foreground)
        for posture, area in self._area_series:
            color = summary_posture_color(posture, self.palette())
            border = (
                color.lighter(108)
                if self.palette().color(
                    QPalette.ColorRole.Window
                ).lightness() < 128
                else color.darker(108)
            )
            area.setBrush(QBrush(color))
            area.setPen(QPen(border, 0.8))
        for axis in chart.axes():
            axis.setLabelsColor(foreground)
            axis.setTitleBrush(QBrush(foreground))
            axis.setLinePenColor(axis_line)
            axis.setGridLineColor(grid)

    def clear(self) -> None:
        chart = self.chart()
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)
            axis.deleteLater()
        self._area_series.clear()
        self._boundary_series.clear()
        chart.setTitle("")
        chart.legend().setVisible(False)

    def set_summary(self, summary: DailyPostureSummary) -> None:
        self.clear()
        chart = self.chart()
        area_data = build_posture_area_data(summary)
        if area_data is None:
            chart.setTitle(tr("No tracked posture data for this day."))
            return

        x_values = (
            area_data.start_hour,
            *area_data.bucket_hours,
            area_data.end_hour,
        )
        lower_values = [0.0] * len(x_values)
        area_series: list[QAreaSeries] = []
        for posture, title in SUMMARY_POSTURES:
            posture_minutes = area_data.minutes_by_posture[posture]
            if not any(posture_minutes):
                continue
            values = (
                posture_minutes[0],
                *posture_minutes,
                posture_minutes[-1],
            )
            upper_values = [
                lower + value
                for lower, value in zip(
                    lower_values,
                    values,
                    strict=True,
                )
            ]
            lower_series = QLineSeries()
            upper_series = QLineSeries()
            for hour, lower, upper in zip(
                x_values,
                lower_values,
                upper_values,
                strict=True,
            ):
                lower_series.append(hour, lower)
                upper_series.append(hour, upper)

            area = QAreaSeries(upper_series, lower_series)
            area.setName(tr(title))
            area.setOpacity(0.82)
            chart.addSeries(area)
            area_series.append(area)
            self._area_series.append((posture, area))
            self._boundary_series.extend((lower_series, upper_series))
            lower_values = upper_values

        x_axis = QCategoryAxis()
        x_axis.setTitleText(tr("Time of day"))
        x_axis.setRange(area_data.start_hour, area_data.end_hour)
        x_axis.setStartValue(area_data.start_hour)
        x_axis.setLabelsPosition(
            QCategoryAxis.AxisLabelsPosition.AxisLabelsPositionOnValue
        )
        hour_span = round(area_data.end_hour - area_data.start_hour)
        label_step = max(1, math.ceil(hour_span / 6))
        label_hours = list(
            range(
                round(area_data.start_hour),
                round(area_data.end_hour) + 1,
                label_step,
            )
        )
        if label_hours[-1] != round(area_data.end_hour):
            label_hours.append(round(area_data.end_hour))
        for hour in label_hours:
            x_axis.append(f"{hour:02d}:00", hour)
        y_axis = QValueAxis()
        y_axis.setTitleText(tr("Tracked minutes"))
        y_axis.setRange(0, SUMMARY_CHART_BUCKET_SECONDS / 60)
        y_axis.setTickCount(4)
        y_axis.setLabelFormat("%.0f")

        chart.addAxis(x_axis, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(y_axis, Qt.AlignmentFlag.AlignLeft)
        for area in area_series:
            area.attachAxis(x_axis)
            area.attachAxis(y_axis)
        chart.legend().setVisible(False)
        self._apply_palette()


class RollingWeekChart(QChartView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(QChart(), parent)
        self._bar_sets: list[tuple[str, QBarSet]] = []
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(180)
        self.setAccessibleName(tr("Rolling 7-day posture report"))
        self.setAccessibleDescription(tr("Tracked posture time"))
        self.chart().setBackgroundVisible(False)
        self.chart().setDropShadowEnabled(False)
        self.chart().legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        self._apply_palette()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_palette()

    def _apply_palette(self) -> None:
        chart = self.chart()
        foreground = self.palette().color(QPalette.ColorRole.WindowText)
        grid = self.palette().color(QPalette.ColorRole.Mid)
        grid.setAlpha(70)
        axis_line = QColor(foreground)
        axis_line.setAlpha(135)
        chart.setTitleBrush(QBrush(foreground))
        chart.legend().setLabelColor(foreground)
        dark = (
            self.palette()
            .color(QPalette.ColorRole.Window)
            .lightness()
            < 128
        )
        for posture, bar_set in self._bar_sets:
            color = summary_posture_color(posture, self.palette())
            border = color.lighter(108) if dark else color.darker(108)
            bar_set.setColor(color)
            bar_set.setBorderColor(border)
            bar_set.setLabelColor(foreground)
        for axis in chart.axes():
            axis.setLabelsColor(foreground)
            axis.setTitleBrush(QBrush(foreground))
            axis.setLinePenColor(axis_line)
            axis.setGridLineColor(grid)

    def clear(self) -> None:
        chart = self.chart()
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)
            axis.deleteLater()
        self._bar_sets.clear()
        chart.setTitle("")
        chart.legend().setVisible(False)

    def set_summary(self, summary: RollingWeekData) -> None:
        self.clear()
        chart = self.chart()
        if summary.tracked_seconds <= 0:
            chart.setTitle(
                tr("No tracked posture data in this 7-day window.")
            )
            self._apply_palette()
            return

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
        for posture, title, values in weekly_sets:
            if not any(values):
                continue
            bar_set = QBarSet(title)
            bar_set.append(values)
            series.append(bar_set)
            self._bar_sets.append((posture, bar_set))
        chart.addSeries(series)

        date_axis = QBarCategoryAxis()
        date_axis.append(
            [
                QLocale().toString(
                    QDate(value.year, value.month, value.day),
                    "ddd d",
                )
                for value in summary.dates
            ]
        )
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
        self._apply_palette()
