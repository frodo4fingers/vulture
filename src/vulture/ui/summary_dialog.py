from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from PySide6.QtCore import QDate, QEvent, QLocale, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vulture.history import (
    BASELINE_POSTURE,
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
from .summary import (
    REMINDER_STAGE_TITLES,
    PostureAreaChart,
    PostureProgressBar,
    RollingWeekChart,
    RollingWeekData,
    SummaryMetric,
    build_rolling_week_data,
)


class WorkdaySummaryDialog(QDialog):
    def __init__(
        self,
        summary_provider: Callable[[date], DailyPostureSummary],
        delete_day: Callable[[date], None],
        delete_all: Callable[[], None],
        setup_names: dict[str, str],
        recording_enabled: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self._applying_summary_palette = False
        self._summary_provider = summary_provider
        self._delete_day_callback = delete_day
        self._delete_all_callback = delete_all
        self._setup_names = setup_names
        self._pending_delete: tuple[str, date | None] | None = None
        self.setWindowTitle(tr("Workday posture summary"))
        self.setMinimumSize(480, 420)
        self.resize(780, 640)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel(tr("Date")))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.setMinimumDate(QDate.currentDate().addDays(-365))
        self.date_edit.dateChanged.connect(lambda _value: self.refresh())
        self.date_edit.setAccessibleName(tr("Date"))
        top_row.addWidget(self.date_edit)
        refresh_button = QPushButton(tr("Refresh"))
        refresh_button.clicked.connect(self.refresh)
        top_row.addWidget(refresh_button)
        top_row.addStretch()
        layout.addLayout(top_row)

        self.recording_label = SemanticLabel(
            tr("Daily history recording is enabled.")
            if recording_enabled
            else tr(
                "Daily history recording is disabled; saved days remain "
                "viewable."
            ),
            tone="info",
        )
        layout.addWidget(self.recording_label)

        self.period_tabs = QTabWidget()
        self.period_tabs.setDocumentMode(True)
        self.period_tabs.setAccessibleName(tr("Workday summary views"))
        layout.addWidget(self.period_tabs, 1)

        self.day_page = QWidget()
        day_layout = QVBoxLayout(self.day_page)
        day_layout.setContentsMargins(8, 8, 8, 8)
        day_layout.setSpacing(8)

        self.daily_metrics_container = QWidget()
        daily_metrics_layout = QGridLayout(self.daily_metrics_container)
        daily_metrics_layout.setContentsMargins(0, 0, 0, 0)
        daily_metrics_layout.setHorizontalSpacing(8)
        daily_metrics_layout.setVerticalSpacing(8)
        self.daily_tracked_metric = SummaryMetric(
            tr("Tracked posture time")
        )
        self.daily_notifications_metric = SummaryMetric(
            tr("Notifications")
        )
        daily_metrics_layout.addWidget(self.daily_tracked_metric, 0, 0)
        daily_metrics_layout.addWidget(
            self.daily_notifications_metric,
            0,
            1,
        )
        daily_metrics_layout.setColumnStretch(0, 1)
        daily_metrics_layout.setColumnStretch(1, 1)
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
        totals_layout.setVerticalSpacing(6)
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
        day_layout.addWidget(self.totals_group)

        self.chart_group = QGroupBox(
            tr("Posture over time (15-minute intervals)")
        )
        chart_layout = QVBoxLayout(self.chart_group)
        self.posture_chart = PostureAreaChart()
        chart_layout.addWidget(self.posture_chart)
        day_layout.addWidget(self.chart_group, 1)
        self.day_tab_index = self.period_tabs.addTab(
            self.day_page,
            tr("Day overview"),
        )

        self.timeline_page = QWidget()
        timeline_page_layout = QVBoxLayout(self.timeline_page)
        timeline_page_layout.setContentsMargins(8, 8, 8, 8)
        self.timeline_group = QGroupBox(tr("Timeline"))
        timeline_layout = QVBoxLayout(self.timeline_group)
        self.timeline = QTableWidget(0, 5)
        self.timeline.setHorizontalHeaderLabels(
            [
                tr("Started"),
                tr("Duration"),
                tr("Posture"),
                tr("Highest reminder stage"),
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
        week_layout.setContentsMargins(6, 6, 6, 6)
        week_layout.setSpacing(6)
        self.weekly_range_label = QLabel()
        weekly_range_font = self.weekly_range_label.font()
        weekly_range_font.setBold(True)
        self.weekly_range_label.setFont(weekly_range_font)
        week_layout.addWidget(self.weekly_range_label)

        self.weekly_metrics_container = QWidget()
        weekly_metrics_layout = QGridLayout(
            self.weekly_metrics_container
        )
        weekly_metrics_layout.setContentsMargins(0, 0, 0, 0)
        weekly_metrics_layout.setHorizontalSpacing(8)
        weekly_metrics_layout.setVerticalSpacing(8)
        self.weekly_tracked_metric = SummaryMetric(
            tr("Tracked posture time")
        )
        self.weekly_notifications_metric = SummaryMetric(
            tr("Notifications")
        )
        self.weekly_days_metric = SummaryMetric(tr("Days with data"))
        self.weekly_baseline_metric = SummaryMetric(tr("Within baseline"))
        weekly_metrics_layout.addWidget(
            self.weekly_tracked_metric,
            0,
            0,
        )
        weekly_metrics_layout.addWidget(
            self.weekly_notifications_metric,
            0,
            1,
        )
        weekly_metrics_layout.addWidget(
            self.weekly_days_metric,
            1,
            0,
        )
        weekly_metrics_layout.addWidget(
            self.weekly_baseline_metric,
            1,
            1,
        )
        weekly_metrics_layout.setColumnStretch(0, 1)
        weekly_metrics_layout.setColumnStretch(1, 1)
        week_layout.addWidget(self.weekly_metrics_container)

        self.weekly_chart_label = QLabel(tr("Posture across 7 days"))
        weekly_chart_label_font = self.weekly_chart_label.font()
        weekly_chart_label_font.setBold(True)
        self.weekly_chart_label.setFont(weekly_chart_label_font)
        week_layout.addWidget(self.weekly_chart_label)
        self.weekly_chart = RollingWeekChart()
        week_layout.addWidget(self.weekly_chart, 1)

        self.weekly_table_label = QLabel(tr("Daily totals"))
        weekly_table_label_font = self.weekly_table_label.font()
        weekly_table_label_font.setBold(True)
        self.weekly_table_label.setFont(weekly_table_label_font)
        week_layout.addWidget(self.weekly_table_label)
        self.weekly_table = QTableWidget(0, 4)
        self.weekly_table.setHorizontalHeaderLabels(
            [
                tr("Date"),
                tr("Tracked posture time"),
                tr("Within baseline"),
                tr("Notifications"),
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
        self.weekly_table.setMinimumHeight(150)
        self.weekly_table.setMaximumHeight(164)
        self.weekly_table.setAccessibleName(tr("Rolling 7-day posture report"))
        week_layout.addWidget(self.weekly_table)
        self.week_tab_index = self.period_tabs.addTab(
            self.week_page,
            tr("7-day report"),
        )

        controls = QHBoxLayout()
        self.delete_day_button = QPushButton(tr("Delete selected day"))
        self.delete_day_button.clicked.connect(self._delete_selected_day)
        self.delete_all_button = QPushButton(tr("Delete all history"))
        self.delete_all_button.clicked.connect(self._delete_all_history)
        controls.addWidget(self.delete_day_button)
        controls.addWidget(self.delete_all_button)
        controls.addStretch()
        layout.addLayout(controls)

        self.delete_confirmation = SemanticLabel(tone="safety")
        self.delete_confirmation.hide()
        layout.addWidget(self.delete_confirmation)
        confirmation_controls = QHBoxLayout()
        confirmation_controls.addStretch()
        self.cancel_delete_button = QPushButton(tr("Cancel"))
        self.cancel_delete_button.clicked.connect(
            self._cancel_history_delete
        )
        self.cancel_delete_button.hide()
        self.confirm_delete_button = QPushButton(tr("Delete this day"))
        self.confirm_delete_button.clicked.connect(
            self._confirm_history_delete
        )
        self.confirm_delete_button.hide()
        confirmation_controls.addWidget(self.cancel_delete_button)
        confirmation_controls.addWidget(self.confirm_delete_button)
        layout.addLayout(confirmation_controls)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(15_000)
        self.refresh_timer.timeout.connect(self._refresh_today)
        self.refresh_timer.start()
        self._selected_day_has_data = False
        self.refresh()

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

    @staticmethod
    def _localized_date(value: date, pattern: str) -> str:
        return QLocale().toString(
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
            tr(
                "Could not read the workday summary: {error}",
                error=error,
            )
        )
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
        self._selected_day_has_data = tracked > 0 or bool(summary.episodes)
        self.empty_state_container.setVisible(
            not self._selected_day_has_data
        )
        self.daily_metrics_container.setVisible(
            self._selected_day_has_data
        )
        self.totals_group.setVisible(self._selected_day_has_data)
        self.chart_group.setVisible(self._selected_day_has_data)
        self.timeline_group.setVisible(self._selected_day_has_data)
        self.period_tabs.setTabEnabled(
            self.timeline_tab_index,
            self._selected_day_has_data,
        )
        if (
            not self._selected_day_has_data
            and self.period_tabs.currentIndex() == self.timeline_tab_index
        ):
            self.period_tabs.setCurrentIndex(self.day_tab_index)
        if self._pending_delete is None:
            self.delete_day_button.setEnabled(self._selected_day_has_data)
        self.daily_tracked_metric.set_value(format_duration(tracked))
        self.daily_notifications_metric.set_value(
            QLocale().toString(summary.reminder_count)
        )
        for posture, _title in SUMMARY_POSTURES:
            duration = summary.totals.get(posture, 0.0)
            percentage = duration / tracked * 100 if tracked > 0 else 0.0
            self.total_bars[posture].setValue(round(percentage * 10))
            self.total_labels[posture].setText(
                tr(
                    "{duration}  ({percentage}%)",
                    duration=format_duration(duration),
                    percentage=QLocale().toString(percentage, "f", 1),
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
                    QLocale.FormatType.ShortFormat,
                ),
                end=self._localized_date(
                    summary.end_date,
                    QLocale.FormatType.ShortFormat,
                ),
            )
        )
        self.weekly_tracked_metric.set_value(
            format_duration(summary.tracked_seconds)
        )
        self.weekly_notifications_metric.set_value(
            QLocale().toString(summary.reminder_count)
        )
        self.weekly_days_metric.set_value(
            tr("{count} of 7", count=summary.days_with_data)
        )
        baseline_percentage = (
            summary.totals[BASELINE_POSTURE]
            / summary.tracked_seconds
            * 100
            if summary.tracked_seconds > 0
            else 0.0
        )
        self.weekly_baseline_metric.set_value(
            f"{QLocale().toString(baseline_percentage, 'f', 1)}%"
        )
        self.weekly_chart.set_summary(summary)

        self.weekly_table.setRowCount(7)
        for row, (day, totals, reminders) in enumerate(
            zip(
                summary.dates,
                summary.daily_totals,
                summary.daily_reminders,
                strict=True,
            )
        ):
            tracked = sum(totals.values())
            baseline_share = (
                totals[BASELINE_POSTURE] / tracked * 100
                if tracked > 0
                else None
            )
            values = (
                self._localized_date(day, "ddd, d MMM"),
                format_duration(tracked),
                (
                    f"{QLocale().toString(baseline_share, 'f', 1)}%"
                    if baseline_share is not None
                    else "-"
                ),
                QLocale().toString(reminders),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column > 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter
                    )
                if day == summary.end_date:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.weekly_table.setItem(row, column, item)
        self.weekly_table.resizeRowsToContents()

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
        self.delete_confirmation.show()
        self.cancel_delete_button.setText(tr("Cancel"))
        self.cancel_delete_button.show()
        self.confirm_delete_button.setText(
            tr("Delete all history")
            if self._pending_delete == ("all", None)
            else tr("Delete selected day")
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
        self.delete_all_button.setEnabled(True)

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
            self.refresh()
            self._cancel_history_delete()
        except HistoryStorageError as error:
            self._pending_delete = None
            self.delete_confirmation.setText(
                f"{tr('Could not delete history')}: {error}"
            )
            self.confirm_delete_button.hide()
            self.cancel_delete_button.setText(tr("Close"))
