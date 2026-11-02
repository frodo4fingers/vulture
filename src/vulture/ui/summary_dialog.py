from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from PySide6.QtCore import QDate, QEvent, QLocale, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vulture.history import (
    DailyPostureSummary,
    HistoryStorageError,
)
from vulture.i18n import tr

from .common import (
    POSTURE_TITLES,
    SUMMARY_POSTURES,
    SemanticLabel,
    format_duration,
)
from .theme import (
    SPACE_SM,
    SPACE_XS,
    TextRole,
    apply_text_role,
    role_font,
)
from .summary import (
    REMINDER_STAGE_TITLES,
    PostureAreaChart,
    PostureProgressBar,
    RollingWeekChart,
    RollingWeekData,
    SummaryMetric,
    break_headline,
    build_rolling_week_data,
    daily_break_stats,
    ui_locale,
)


SUMMARY_DIALOG_HEIGHT = 760


def _short_date_format() -> str:
    """Locale short date format with a four-digit year."""
    return re.sub(
        r"(?<!y)yy(?!y)",
        "yyyy",
        ui_locale().dateFormat(QLocale.FormatType.ShortFormat),
    )


def _scrolling(page: QWidget) -> QScrollArea:
    """Host ``page`` at its natural height; it scrolls in a short window."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(page)
    return scroll


def _place_tiles(
    layout: QGridLayout,
    row: int,
    tiles: list[tuple[SummaryMetric, bool]],
) -> None:
    """Show the flagged tiles packed left to right, hide the rest."""
    for tile, _show in tiles:
        layout.removeWidget(tile)
    shown = [tile for tile, show in tiles if show]
    for tile, show in tiles:
        tile.setVisible(show)
    for column, tile in enumerate(shown):
        layout.addWidget(tile, row, column)


class WorkdaySummaryDialog(QDialog):
    def __init__(
        self,
        summary_provider: Callable[[date], DailyPostureSummary],
        delete_day: Callable[[date], None],
        delete_all: Callable[[], None],
        setup_names: dict[str, str],
        recording_enabled: bool,
        parent: QWidget | None = None,
        *,
        has_any_history: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self._applying_summary_palette = False
        self._summary_provider = summary_provider
        self._has_any_history = has_any_history
        self._delete_day_callback = delete_day
        self._delete_all_callback = delete_all
        self._setup_names = setup_names
        self._pending_delete: tuple[str, date | None] | None = None
        self.setWindowTitle(tr("Workday summary"))
        self.setMinimumSize(480, 420)
        # Tall enough for the whole Day overview, colour key included; the
        # presenter clamps it to the screen and the tab scrolls below that.
        self.resize(780, SUMMARY_DIALOG_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACE_SM)
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel(tr("Date")))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setLocale(ui_locale())
        self.date_edit.setDisplayFormat(_short_date_format())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.setMinimumDate(QDate.currentDate().addDays(-365))
        self.date_edit.dateChanged.connect(lambda _value: self.refresh())
        self.date_edit.setAccessibleName(tr("Date"))
        top_row.addWidget(self.date_edit)
        refresh_button = QPushButton(tr("&Refresh"))
        refresh_button.clicked.connect(self.refresh)
        refresh_button.setAutoDefault(False)
        top_row.addWidget(refresh_button)
        top_row.addStretch()
        layout.addLayout(top_row)

        # Only the unusual state gets a notice; recording on is the default.
        self.recording_label = SemanticLabel(
            tr(
                "Daily history recording is disabled; saved days remain "
                "viewable."
            ),
            tone="info",
        )
        self.recording_label.setVisible(not recording_enabled)
        layout.addWidget(self.recording_label)

        self.period_tabs = QTabWidget()
        self.period_tabs.setDocumentMode(True)
        self.period_tabs.setAccessibleName(tr("Workday summary views"))
        layout.addWidget(self.period_tabs, 1)

        self.day_page = QWidget()
        day_layout = QVBoxLayout(self.day_page)
        day_layout.setContentsMargins(SPACE_SM, SPACE_SM, SPACE_SM, SPACE_SM)
        day_layout.setSpacing(SPACE_SM)

        self.daily_metrics_container = QWidget()
        daily_metrics_layout = QGridLayout(self.daily_metrics_container)
        daily_metrics_layout.setContentsMargins(0, 0, 0, 0)
        daily_metrics_layout.setHorizontalSpacing(SPACE_SM)
        daily_metrics_layout.setVerticalSpacing(SPACE_SM)
        # Breaks lead; nudges and tracked time are the quieter second row.
        self.daily_headline = QLabel()
        self.daily_headline.setWordWrap(True)
        apply_text_role(self.daily_headline, TextRole.HEADING)
        daily_metrics_layout.addWidget(self.daily_headline, 0, 0, 1, 3)
        self.daily_breaks_metric = SummaryMetric(
            tr("Breaks"), self.daily_metrics_container, display=True
        )
        self.daily_moved_metric = SummaryMetric(
            tr("Minutes moved"), self.daily_metrics_container, display=True
        )
        self.daily_eye_metric = SummaryMetric(
            tr("Eye breaks"), self.daily_metrics_container
        )
        self.no_breaks_label = QLabel()
        self.no_breaks_label.setWordWrap(True)
        self.daily_nudges_metric = SummaryMetric(
            tr("Nudges"), secondary=True
        )
        self.daily_tracked_metric = SummaryMetric(
            tr("Tracked posture time"), secondary=True
        )
        daily_metrics_layout.addWidget(self.no_breaks_label, 1, 0, 1, 3)
        daily_metrics_layout.addWidget(self.daily_nudges_metric, 2, 0)
        daily_metrics_layout.addWidget(self.daily_tracked_metric, 2, 1)
        for column in range(3):
            daily_metrics_layout.setColumnStretch(column, 1)
        day_layout.addWidget(self.daily_metrics_container)

        self.empty_state_container = QWidget()
        empty_state_layout = QVBoxLayout(self.empty_state_container)
        empty_state_layout.setContentsMargins(0, 0, 0, 0)
        empty_state_layout.addStretch(1)
        self._empty_state_text = tr(
            "<b>No posture history for this day</b><br>"
            "Leave tracking running to build a timeline. Only posture "
            "labels and durations are stored."
        )
        self.empty_state = SemanticLabel(
            self._empty_state_text,
            tone="info",
        )
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.setMinimumWidth(260)
        self.empty_state.setMaximumWidth(460)
        empty_state_layout.addWidget(
            self.empty_state,
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        empty_state_layout.addStretch(1)
        day_layout.addWidget(self.empty_state_container, 1)

        self.totals_group = QGroupBox(tr("Tracked posture time"))
        totals_layout = QGridLayout(self.totals_group)
        totals_layout.setVerticalSpacing(SPACE_XS)
        self.total_bars: dict[str, QProgressBar] = {}
        self.total_labels: dict[str, QLabel] = {}
        for row, (posture, title) in enumerate(SUMMARY_POSTURES):
            title_label = QLabel(tr(title))
            totals_layout.addWidget(title_label, row, 0)
            bar = PostureProgressBar(posture)
            bar.setAccessibleName(tr(title))
            totals_layout.addWidget(bar, row, 1)
            value_label = QLabel(tr("{seconds}s", seconds=0))
            value_label.setMinimumWidth(112)
            value_label.setAlignment(
                Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignVCenter
            )
            totals_layout.addWidget(value_label, row, 2)
            self.total_bars[posture] = bar
            self.total_labels[posture] = value_label
        totals_layout.setColumnStretch(1, 1)

        # The timeline chart leads and takes the spare height; the posture
        # split below it is secondary.
        self.chart_group = QGroupBox(
            tr("Posture over time (15-minute intervals)")
        )
        chart_layout = QVBoxLayout(self.chart_group)
        self.posture_chart = PostureAreaChart()
        chart_layout.addWidget(self.posture_chart)
        day_layout.addWidget(self.chart_group, 1)
        day_layout.addWidget(self.totals_group)
        self.day_tab_index = self.period_tabs.addTab(
            _scrolling(self.day_page),
            tr("Day overview"),
        )

        self.timeline_page = QWidget()
        timeline_page_layout = QVBoxLayout(self.timeline_page)
        timeline_page_layout.setContentsMargins(
            SPACE_SM, SPACE_SM, SPACE_SM, SPACE_SM
        )
        self.timeline_group = QGroupBox(tr("Timeline"))
        timeline_layout = QVBoxLayout(self.timeline_group)
        self.timeline = QTableWidget(0, 5)
        self.timeline.setHorizontalHeaderLabels(
            [
                tr("Started"),
                tr("Duration"),
                tr("Posture"),
                tr("Strongest nudge"),
                tr("Setup"),
            ]
        )
        self.timeline.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.timeline.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.timeline.setAlternatingRowColors(True)
        header = self.timeline.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        timeline_layout.addWidget(self.timeline)
        timeline_page_layout.addWidget(self.timeline_group, 1)
        self.timeline_tab_index = self.period_tabs.addTab(
            self.timeline_page,
            tr("Timeline"),
        )

        self.week_page = QWidget()
        week_layout = QVBoxLayout(self.week_page)
        week_layout.setContentsMargins(SPACE_SM, SPACE_SM, SPACE_SM, SPACE_SM)
        week_layout.setSpacing(SPACE_SM)
        self.weekly_range_label = QLabel()
        apply_text_role(self.weekly_range_label, TextRole.HEADING)
        week_layout.addWidget(self.weekly_range_label)

        # One compact row. "Within baseline" is no longer a headline number.
        self.weekly_metrics_container = QWidget()
        weekly_metrics_layout = QGridLayout(
            self.weekly_metrics_container
        )
        weekly_metrics_layout.setContentsMargins(0, 0, 0, 0)
        weekly_metrics_layout.setHorizontalSpacing(SPACE_SM)
        weekly_metrics_layout.setVerticalSpacing(SPACE_SM)
        self.weekly_headline = QLabel()
        self.weekly_headline.setWordWrap(True)
        apply_text_role(self.weekly_headline, TextRole.HEADING)
        weekly_metrics_layout.addWidget(self.weekly_headline, 0, 0, 1, 3)
        self.weekly_breaks_metric = SummaryMetric(
            tr("Breaks"), self.weekly_metrics_container, display=True
        )
        self.weekly_moved_metric = SummaryMetric(
            tr("Minutes moved"), self.weekly_metrics_container, display=True
        )
        self.weekly_no_breaks_label = QLabel(
            tr("No breaks recorded this week yet.")
        )
        self.weekly_no_breaks_label.setWordWrap(True)
        weekly_metrics_layout.addWidget(
            self.weekly_no_breaks_label, 1, 0, 1, 3
        )
        self.weekly_tracked_metric = SummaryMetric(
            tr("Tracked posture time"), secondary=True
        )
        self.weekly_nudges_metric = SummaryMetric(
            tr("Nudges"), secondary=True
        )
        self.weekly_days_metric = SummaryMetric(
            tr("Days with data"), secondary=True
        )
        for column, metric in enumerate(
            (
                self.weekly_tracked_metric,
                self.weekly_nudges_metric,
                self.weekly_days_metric,
            )
        ):
            weekly_metrics_layout.addWidget(metric, 2, column)
            weekly_metrics_layout.setColumnStretch(column, 1)
        week_layout.addWidget(self.weekly_metrics_container)

        self.weekly_chart_label = QLabel(tr("Posture across 7 days"))
        apply_text_role(self.weekly_chart_label, TextRole.HEADING)
        week_layout.addWidget(self.weekly_chart_label)
        self.weekly_chart = RollingWeekChart()
        week_layout.addWidget(self.weekly_chart, 1)

        self.weekly_table_label = QLabel(tr("Daily totals"))
        apply_text_role(self.weekly_table_label, TextRole.HEADING)
        week_layout.addWidget(self.weekly_table_label)
        self.weekly_table = QTableWidget(0, 4)
        self.weekly_table.setHorizontalHeaderLabels(
            [
                tr("Date"),
                tr("Breaks"),
                tr("Tracked posture time"),
                tr("Nudges"),
            ]
        )
        self.weekly_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.weekly_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.weekly_table.setAlternatingRowColors(True)
        weekly_vertical_header = self.weekly_table.verticalHeader()
        weekly_vertical_header.hide()
        weekly_vertical_header.setDefaultSectionSize(18)
        weekly_vertical_header.setMinimumSectionSize(18)
        weekly_header = self.weekly_table.horizontalHeader()
        weekly_header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        for column in range(1, 4):
            weekly_header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )
        # Seven rows always fit, so the tab's scroll area is the only scroller.
        self.weekly_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._fit_weekly_table()
        self.weekly_table.setAccessibleName(tr("Rolling 7-day posture report"))
        week_layout.addWidget(self.weekly_table)
        self.week_tab_index = self.period_tabs.addTab(
            _scrolling(self.week_page),
            tr("7-day report"),
        )

        controls = QHBoxLayout()
        self.delete_day_button = QPushButton(tr("&Delete selected day"))
        self.delete_day_button.clicked.connect(self._delete_selected_day)
        self.delete_all_button = QPushButton(tr("Delete all &history"))
        self.delete_all_button.clicked.connect(self._delete_all_history)
        # No default frame: deletion stays visually behind the data.
        for button in (self.delete_day_button, self.delete_all_button):
            button.setAutoDefault(False)
            button.setDefault(False)
        # The irreversible action sits apart, at the far edge.
        controls.addWidget(self.delete_day_button)
        controls.addStretch()
        controls.addWidget(self.delete_all_button)
        layout.addLayout(controls)

        self.delete_confirmation = SemanticLabel(tone="safety")
        self.delete_confirmation.hide()
        layout.addWidget(self.delete_confirmation)
        confirmation_controls = QHBoxLayout()
        confirmation_controls.addStretch()
        self.cancel_delete_button = QPushButton(tr("&Cancel"))
        self.cancel_delete_button.clicked.connect(
            self._cancel_history_delete
        )
        self.cancel_delete_button.hide()
        self.confirm_delete_button = QPushButton(tr("Delete &this day"))
        self.confirm_delete_button.clicked.connect(
            self._confirm_history_delete
        )
        self.confirm_delete_button.hide()
        for button in (self.cancel_delete_button, self.confirm_delete_button):
            button.setAutoDefault(False)
            button.setDefault(False)
        confirmation_controls.addWidget(self.cancel_delete_button)
        confirmation_controls.addWidget(self.confirm_delete_button)
        layout.addLayout(confirmation_controls)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(15_000)
        self.refresh_timer.timeout.connect(self._refresh_today)
        self.refresh_timer.start()
        self._selected_day_has_data = False
        self._any_history = False
        self.refresh()
        # Start on the tabs, not in the date field with a segment selected.
        self.period_tabs.setFocus()

    def _sync_delete_all_button(self) -> None:
        if self._has_any_history is not None:
            try:
                self._any_history = self._has_any_history()
            except HistoryStorageError:
                self._any_history = True  # unknown: leave deletion available
        if self._pending_delete is None:
            self.delete_all_button.setEnabled(self._any_history)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.PaletteChange
            and not self._applying_summary_palette
        ):
            self._apply_summary_palette()

    def _apply_summary_palette(self) -> None:
        self._applying_summary_palette = True
        try:
            for metric in self.findChildren(SummaryMetric):
                metric._apply_palette()
            for bar in self.findChildren(PostureProgressBar):
                bar._apply_palette()
            for chart in self.findChildren(PostureAreaChart):
                chart._apply_palette()
            for chart in self.findChildren(RollingWeekChart):
                chart._apply_palette()
        finally:
            self._applying_summary_palette = False

    def selected_date(self) -> date:
        selected = self.date_edit.date()
        return date(selected.year(), selected.month(), selected.day())

    def _fit_weekly_table(self) -> None:
        """Size the table to its rows; larger fonts grow rows past 18 px."""
        table = self.weekly_table
        rows = (
            sum(table.rowHeight(row) for row in range(table.rowCount()))
            if table.rowCount()
            else 7 * table.verticalHeader().defaultSectionSize()
        )
        table.setFixedHeight(
            table.horizontalHeader().sizeHint().height()
            + rows
            + 2 * table.frameWidth()
        )

    @staticmethod
    def _localized_date(value: date, pattern: str) -> str:
        return ui_locale().toString(
            QDate(value.year, value.month, value.day),
            pattern,
        )

    def refresh(self) -> None:
        selected_date = self.selected_date()
        week_dates = tuple(
            selected_date - timedelta(days=offset)
            for offset in range(6, -1, -1)
        )
        try:
            week_summaries = tuple(
                self._summary_provider(value)
                for value in week_dates
            )
        except HistoryStorageError as error:
            self._show_storage_error(error)
            return

        summary = week_summaries[-1]
        week_summary = build_rolling_week_data(
            selected_date,
            week_summaries,
        )
        self.period_tabs.setTabEnabled(self.week_tab_index, True)
        self._update_daily_summary(summary)
        self._update_weekly_summary(week_summary)

    def _show_storage_error(self, error: HistoryStorageError) -> None:
        self._selected_day_has_data = False
        self.empty_state.set_semantic_tone("safety")
        self.empty_state.setText(
            tr("The workday summary could not be loaded right now.")
        )
        self.empty_state.setToolTip(str(error))
        self.empty_state_container.show()
        self.daily_metrics_container.hide()
        self.totals_group.hide()
        self.chart_group.hide()
        self.timeline_group.hide()
        self.period_tabs.setTabEnabled(self.timeline_tab_index, False)
        self.period_tabs.setTabEnabled(self.week_tab_index, False)
        self.period_tabs.setCurrentIndex(self.day_tab_index)
        self.delete_day_button.setEnabled(False)
        self.posture_chart.clear()
        self.weekly_chart.clear()
        self.timeline.setRowCount(0)
        self.weekly_table.setRowCount(0)

    def _update_daily_summary(
        self,
        summary: DailyPostureSummary,
    ) -> None:
        tracked = summary.tracked_seconds
        self.posture_chart.set_summary(summary)
        self.empty_state.set_semantic_tone("info")
        self.empty_state.setText(self._empty_state_text)
        self.empty_state.setToolTip("")
        has_posture = tracked > 0 or bool(summary.episodes)
        self._selected_day_has_data = has_posture or bool(summary.breaks)
        self.empty_state_container.setVisible(
            not self._selected_day_has_data
        )
        self.daily_metrics_container.setVisible(
            self._selected_day_has_data
        )
        self.totals_group.setVisible(has_posture)
        self.chart_group.setVisible(has_posture)
        self.timeline_group.setVisible(has_posture)
        self.period_tabs.setTabEnabled(self.timeline_tab_index, has_posture)
        if (
            not has_posture
            and self.period_tabs.currentIndex() == self.timeline_tab_index
        ):
            self.period_tabs.setCurrentIndex(self.day_tab_index)
        if self._pending_delete is None:
            self.delete_day_button.setEnabled(self._selected_day_has_data)

        stats = daily_break_stats(summary)
        locale = ui_locale()
        is_today = summary.local_date == datetime.now().astimezone().date()
        _place_tiles(
            self.daily_metrics_container.layout(),
            1,
            [
                (self.daily_breaks_metric, stats.count > 0),
                (self.daily_moved_metric, stats.minutes_moved > 0),
                (self.daily_eye_metric, stats.eye_breaks > 0),
            ],
        )
        self.daily_headline.setVisible(stats.count > 0)
        self.daily_headline.setText(
            break_headline(
                stats.count,
                stats.minutes_moved,
                "today" if is_today else "day",
            )
        )
        self.no_breaks_label.setVisible(stats.count == 0)
        self.no_breaks_label.setText(
            tr("No breaks yet today — the next one is on its way.")
            if is_today
            else tr("No breaks logged this day")
        )
        self.daily_breaks_metric.set_value(locale.toString(stats.count))
        self.daily_moved_metric.set_value(
            locale.toString(stats.minutes_moved)
        )
        self.daily_eye_metric.set_value(locale.toString(stats.eye_breaks))
        self.daily_nudges_metric.set_value(
            locale.toString(summary.reminder_count)
        )
        self.daily_tracked_metric.set_value(format_duration(tracked))
        self._any_history = self._any_history or self._selected_day_has_data
        self._sync_delete_all_button()
        for posture, _title in SUMMARY_POSTURES:
            duration = summary.totals.get(posture, 0.0)
            percentage = duration / tracked * 100 if tracked > 0 else 0.0
            self.total_bars[posture].setValue(round(percentage * 10))
            self.total_labels[posture].setText(
                tr(
                    "{duration}  ({percentage}%)",
                    duration=format_duration(duration),
                    percentage=ui_locale().toString(percentage, "f", 1),
                )
            )

        self.timeline.setRowCount(len(summary.episodes))
        for row, episode in enumerate(summary.episodes):
            local_timezone = timezone(
                timedelta(minutes=episode.utc_offset_minutes)
            )
            local_start = episode.started_at.astimezone(local_timezone)
            values = (
                local_start.strftime("%H:%M:%S"),
                format_duration(episode.duration_seconds),
                tr(
                    POSTURE_TITLES.get(
                        episode.posture,
                        episode.posture.replace("_", " ").title(),
                    )
                ),
                tr(
                    REMINDER_STAGE_TITLES.get(
                        episode.peak_state,
                        episode.peak_state.value.replace("_", " ").title(),
                    )
                ),
                self._setup_names.get(
                    episode.setup_id,
                    tr("Deleted setup"),
                ),
            )
            for column, value in enumerate(values):
                self.timeline.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )

    def _update_weekly_summary(
        self,
        summary: RollingWeekData,
    ) -> None:
        self.weekly_range_label.setText(
            tr(
                "From {start} to {end}",
                start=self._localized_date(
                    summary.start_date,
                    _short_date_format(),
                ),
                end=self._localized_date(
                    summary.end_date,
                    _short_date_format(),
                ),
            )
        )
        _place_tiles(
            self.weekly_metrics_container.layout(),
            1,
            [
                (self.weekly_breaks_metric, summary.break_count > 0),
                (self.weekly_moved_metric, summary.minutes_moved > 0),
            ],
        )
        self.weekly_headline.setVisible(summary.break_count > 0)
        self.weekly_headline.setText(
            break_headline(
                summary.break_count, summary.minutes_moved, "week"
            )
        )
        self.weekly_no_breaks_label.setVisible(summary.break_count == 0)
        self.weekly_breaks_metric.set_value(
            ui_locale().toString(summary.break_count)
        )
        self.weekly_moved_metric.set_value(
            ui_locale().toString(summary.minutes_moved)
        )
        self.weekly_tracked_metric.set_value(
            format_duration(summary.tracked_seconds)
        )
        self.weekly_nudges_metric.set_value(
            ui_locale().toString(summary.reminder_count)
        )
        self.weekly_days_metric.set_value(
            tr("{count} of 7", count=summary.days_with_data)
        )
        self._any_history = self._any_history or summary.days_with_data > 0
        self._sync_delete_all_button()
        self.weekly_chart.set_summary(summary)

        self.weekly_table.setRowCount(7)
        for row, (day, totals, reminders, breaks) in enumerate(
            zip(
                summary.dates,
                summary.daily_totals,
                summary.daily_reminders,
                summary.daily_breaks,
                strict=True,
            )
        ):
            values = (
                self._localized_date(day, "ddd, d MMM"),
                ui_locale().toString(breaks),
                format_duration(sum(totals.values())),
                ui_locale().toString(reminders),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column > 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter
                    )
                if day == summary.end_date:
                    item.setFont(role_font(TextRole.BODY_STRONG))
                self.weekly_table.setItem(row, column, item)
        self.weekly_table.resizeRowsToContents()
        self._fit_weekly_table()

    def _refresh_today(self) -> None:
        if self.selected_date() == datetime.now().astimezone().date():
            self.refresh()

    def _delete_selected_day(self) -> None:
        selected_date = self.selected_date()
        self._pending_delete = ("day", selected_date)
        self.delete_confirmation.setAccessibleName(
            tr("Delete workday summary")
        )
        self.delete_confirmation.setText(
            tr(
                "Delete all saved posture episodes and reminders for {date}?",
                date=selected_date.isoformat(),
            )
        )
        self._show_delete_confirmation()

    def _delete_all_history(self) -> None:
        self._pending_delete = ("all", None)
        self.delete_confirmation.setAccessibleName(
            tr("Delete all workday history")
        )
        self.delete_confirmation.setText(
            tr(
                "Delete every saved posture episode and reminder? This cannot "
                "be undone."
            )
        )
        self._show_delete_confirmation()

    def _show_delete_confirmation(self) -> None:
        self.delete_confirmation.setToolTip("")
        self.delete_confirmation.show()
        self.cancel_delete_button.setText(tr("&Cancel"))
        self.cancel_delete_button.show()
        self.confirm_delete_button.setText(
            tr("Delete all &history")
            if self._pending_delete == ("all", None)
            else tr("&Delete selected day")
        )
        self.confirm_delete_button.show()
        self.delete_day_button.setEnabled(False)
        self.delete_all_button.setEnabled(False)

    def _cancel_history_delete(self) -> None:
        self._pending_delete = None
        self.delete_confirmation.hide()
        self.cancel_delete_button.hide()
        self.confirm_delete_button.hide()
        self.delete_day_button.setEnabled(self._selected_day_has_data)
        self.delete_all_button.setEnabled(self._any_history)

    def _confirm_history_delete(self) -> None:
        pending = self._pending_delete
        if pending is None:
            return
        try:
            action, selected_date = pending
            if action == "day" and selected_date is not None:
                self._delete_day_callback(selected_date)
            elif action == "all":
                self._delete_all_callback()
            # Without a store query the next refresh re-derives this.
            self._any_history = False
            self.refresh()
            self._cancel_history_delete()
        except HistoryStorageError as error:
            self._pending_delete = None
            self.delete_confirmation.setText(
                tr("History could not be deleted right now. Try again later.")
            )
            self.delete_confirmation.setToolTip(str(error))
            self.confirm_delete_button.hide()
            self.cancel_delete_button.setText(tr("Close"))
