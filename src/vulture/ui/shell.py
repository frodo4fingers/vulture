from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vulture.camera import CameraThread, resolve_camera_descriptor
from vulture.i18n import tr
from vulture.models import TrackerState
from vulture.tracking import PostureEvaluator

from .calibration import SetupDialog
from .common import SemanticLabel, create_state_icon
from .theme import (
    CONTROL_SPACING,
    HAIRLINE,
    MEDIA_TEXT,
    SECTION_SPACING,
    SETUP_SELECTOR_WIDTH,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
    STATUS_DOT_SIZE,
    WINDOW_MARGIN,
    Card,
    CaptionLabel,
    Separator,
    TextRole,
    align_first_baseline,
    apply_text_role,
    media_surface_style,
)


_WINDOW_CONTENT_MARGIN = WINDOW_MARGIN
_WINDOW_CONTENT_SPACING = SECTION_SPACING
# The hosted side panel keeps the divider clear on its left and stays flush
# with the workspace footer at the bottom so both columns share one baseline.
SIDE_PANEL_CONTENT_MARGINS = (0, SPACE_MD, 0, 0)


class ShellMixin:
    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(
            _WINDOW_CONTENT_MARGIN,
            _WINDOW_CONTENT_MARGIN,
            _WINDOW_CONTENT_MARGIN,
            _WINDOW_CONTENT_MARGIN,
        )
        layout.setSpacing(_WINDOW_CONTENT_SPACING)
        self.setCentralWidget(central)

        self.command_bar = QToolBar()
        self.command_bar.setMovable(False)
        self.command_bar.setFloatable(False)
        self.command_bar.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        self.command_bar.setAccessibleName(tr("Camera setup controls"))

        setup_control = QWidget()
        setup_control.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        setup_row = QHBoxLayout(setup_control)
        setup_row.setContentsMargins(0, 0, SPACE_SM, 0)
        setup_row.setSpacing(SPACE_SM)
        setup_row.addWidget(QLabel(tr("Setup")))
        self.setup_combo = QComboBox()
        self.setup_combo.setMinimumWidth(180)
        self.setup_combo.setMaximumWidth(SETUP_SELECTOR_WIDTH)
        self.setup_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setup_combo.currentIndexChanged.connect(self._setup_changed)
        setup_row.addWidget(self.setup_combo, 1)
        setup_row.addStretch(0)
        self.command_bar.addWidget(setup_control)

        command_bar_spacer = QWidget()
        command_bar_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.command_bar.addWidget(command_bar_spacer)

        self.add_setup_command = QAction(tr("Add setup"), self)
        self.add_setup_command.triggered.connect(self._add_setup)
        self.command_bar.addAction(self.add_setup_command)
        self.pause_command = QAction(
            tr("Release camera")
            if self._tracking_enabled
            else tr("Resume tracking"),
            self,
        )
        self.pause_command.triggered.connect(self._toggle_tracking)
        self.command_bar.addAction(self.pause_command)
        self.command_bar.addSeparator()
        self.calibrate_command = QAction(tr("Calibrate"), self)
        self.calibrate_command.triggered.connect(self._calibrate)
        self.command_bar.addAction(self.calibrate_command)
        self.recalibrate_step_command = QAction(
            tr("Recalibrate step"),
            self,
        )
        self.recalibrate_step_command.setToolTip(
            tr(
                "Record the good baseline or one unwanted-posture stage again."
            )
        )
        self.recalibrate_step_command.triggered.connect(
            self._recalibrate_step
        )
        self.command_bar.addAction(self.recalibrate_step_command)
        self.command_bar.addSeparator()
        self.settings_command = QAction(tr("Settings"), self)
        self.settings_command.triggered.connect(self._show_settings)
        self.command_bar.addAction(self.settings_command)

        self.add_setup_button = self.command_bar.widgetForAction(
            self.add_setup_command
        )
        self.pause_button = self.command_bar.widgetForAction(
            self.pause_command
        )
        self.calibrate_button = self.command_bar.widgetForAction(
            self.calibrate_command
        )
        self.recalibrate_step_button = self.command_bar.widgetForAction(
            self.recalibrate_step_command
        )
        self.settings_button = self.command_bar.widgetForAction(
            self.settings_command
        )
        layout.addWidget(self.command_bar)

        self.break_timer_group = Card(tr("Next break"))
        self.move_now_button = QPushButton(tr("Move now"))
        self.move_now_button.setAutoDefault(False)
        self.move_now_button.clicked.connect(
            lambda: self._offer_exercise()
        )
        self.break_timer_group.add_header_action(self.move_now_button)

        break_timer_layout = QGridLayout()
        break_timer_layout.setContentsMargins(0, 0, 0, 0)
        break_timer_layout.setHorizontalSpacing(SPACE_MD)
        break_timer_layout.setVerticalSpacing(0)
        self.next_break_label = QLabel()
        apply_text_role(self.next_break_label, TextRole.TITLE)
        self.next_break_label.setWordWrap(True)
        self.next_break_detail = CaptionLabel(
            tr("Break timing continues with or without the camera.")
        )
        self.break_countdown = QLabel("--:--")
        apply_text_role(self.break_countdown, TextRole.DISPLAY)
        self.break_countdown.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        self.break_countdown.setAccessibleName(tr("Time until next break"))
        self.break_countdown_caption = CaptionLabel(tr("until next break"))
        self.break_countdown_caption.setWordWrap(False)
        self.break_countdown_caption.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        align_first_baseline(self.next_break_label, self.break_countdown)

        # The cells are filled rather than aligned so wrapping copy uses the
        # full column width; each label carries its own text alignment.
        break_timer_layout.addWidget(self.next_break_label, 0, 0)
        break_timer_layout.addWidget(self.break_countdown, 0, 1)
        break_timer_layout.addWidget(self.next_break_detail, 1, 0)
        break_timer_layout.addWidget(self.break_countdown_caption, 1, 1)
        break_timer_layout.setColumnStretch(0, 1)
        break_timer_layout.setRowStretch(2, 1)
        self.break_timer_group.body.addLayout(break_timer_layout)

        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setHandleWidth(SPACE_MD)
        camera_workspace = QWidget()
        camera_layout = QVBoxLayout(camera_workspace)
        camera_layout.setContentsMargins(0, 0, 0, 0)
        camera_layout.setSpacing(_WINDOW_CONTENT_SPACING)

        self.status_group = Card(tr("Tracking status"))
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(SPACE_MD)
        self.status_dot = QLabel("V")
        self.status_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_dot.setFixedSize(STATUS_DOT_SIZE, STATUS_DOT_SIZE)
        apply_text_role(self.status_dot, TextRole.TITLE)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        status_layout.addWidget(
            self.status_dot,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        status_layout.addWidget(self.status_label, 1)
        self.status_group.body.addLayout(status_layout)
        self.status_group.body.addStretch(1)
        signal_row = QHBoxLayout()
        signal_row.setContentsMargins(0, 0, 0, 0)
        signal_row.setSpacing(_WINDOW_CONTENT_SPACING)
        signal_row.addWidget(self.break_timer_group, 2)
        signal_row.addWidget(self.status_group, 1)
        camera_layout.addLayout(signal_row)

        self.preview_stack = QStackedWidget()
        self.preview_stack.setMinimumSize(640, 360)

        self.first_run_panel = QFrame()
        self.first_run_panel.setStyleSheet(
            f"QFrame {{ {media_surface_style()} }}"
        )
        first_run_outer = QVBoxLayout(self.first_run_panel)
        first_run_outer.setContentsMargins(
            SPACE_MD,
            SPACE_MD,
            SPACE_MD,
            SPACE_MD,
        )
        first_run_outer.addStretch(1)
        first_run_content = QWidget()
        first_run_content.setMinimumWidth(380)
        first_run_content.setMaximumWidth(500)
        first_run_layout = QVBoxLayout(first_run_content)
        first_run_layout.setContentsMargins(0, 0, 0, 0)
        first_run_layout.setSpacing(SPACE_MD)
        self.first_run_heading = QLabel(tr("Camera tracking is optional"))
        self.first_run_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_text_role(self.first_run_heading, TextRole.TITLE)
        self.first_run_heading.setStyleSheet("color: #f2f6fb")
        first_run_layout.addWidget(self.first_run_heading)
        first_run_copy = QLabel(
            tr(
                "Break reminders are already running. Add a camera setup only "
                "if you also want private posture feedback."
            )
        )
        first_run_copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        first_run_copy.setWordWrap(True)
        first_run_copy.setMinimumHeight(40)
        first_run_copy.setStyleSheet(f"color: {MEDIA_TEXT}")
        first_run_layout.addWidget(first_run_copy)
        self.first_run_add_button = QPushButton(tr("Add camera setup"))
        self.first_run_add_button.setDefault(True)
        self.first_run_add_button.clicked.connect(self._add_setup)
        first_run_actions = QHBoxLayout()
        first_run_actions.setContentsMargins(0, SPACE_XS, 0, 0)
        first_run_actions.addStretch(1)
        first_run_actions.addWidget(self.first_run_add_button)
        first_run_actions.addStretch(1)
        first_run_layout.addLayout(first_run_actions)
        first_run_outer.addWidget(
            first_run_content,
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        first_run_outer.addStretch(1)
        self.preview_stack.addWidget(self.first_run_panel)

        self.preview = QLabel(tr("Camera preview"))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet(media_surface_style())
        self.preview_stack.addWidget(self.preview)
        camera_layout.addWidget(self.preview_stack, 1)

        privacy = SemanticLabel(
            tr(
                "<b>Private by design:</b> camera frames are analyzed locally "
                "and discarded immediately. Stored workday history contains "
                "only posture labels, reminder stages, setups, timestamps, "
                "and durations."
            ),
            tone="info",
            role=TextRole.CAPTION,
        )
        camera_layout.addWidget(privacy)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(CONTROL_SPACING)
        self.summary_button = QPushButton(tr("Workday summary"))
        self.summary_button.setAutoDefault(False)
        self.summary_button.clicked.connect(self._show_workday_summary)
        self.summary_button.setEnabled(self.history_store is not None)
        footer.addWidget(self.summary_button)
        self.evidence_button = QPushButton(tr("Evidence and safety"))
        self.evidence_button.setAutoDefault(False)
        self.evidence_button.clicked.connect(self._show_evidence)
        footer.addWidget(self.evidence_button)
        footer.addStretch()
        self.footer_disclaimer = CaptionLabel(
            tr("Personalized reminder — not a medical device")
        )
        self.footer_disclaimer.setWordWrap(False)
        footer.addWidget(
            self.footer_disclaimer,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        camera_layout.addLayout(footer)

        self.side_panel_frame = QWidget()
        side_panel_layout = QVBoxLayout(self.side_panel_frame)
        side_panel_layout.setContentsMargins(0, 0, 0, 0)
        side_panel_layout.setSpacing(0)

        side_panel_header = QWidget()
        side_panel_header_layout = QHBoxLayout(side_panel_header)
        # The header's top inset matches a card's, so the panel title and the
        # workspace card titles start on the same line.
        side_panel_header_layout.setContentsMargins(
            0,
            SPACE_MD + HAIRLINE,
            0,
            SPACE_MD,
        )
        side_panel_header_layout.setSpacing(CONTROL_SPACING)
        self.side_panel_title = QLabel()
        apply_text_role(self.side_panel_title, TextRole.TITLE)
        self.side_panel_title.setWordWrap(True)
        side_panel_header_layout.addWidget(self.side_panel_title, 1)
        self.side_panel_close_button = QToolButton()
        self.side_panel_close_button.setText(tr("Close"))
        self.side_panel_close_button.setAutoRaise(True)
        self.side_panel_close_button.clicked.connect(
            self._dismiss_side_panel
        )
        side_panel_header_layout.addWidget(self.side_panel_close_button)
        side_panel_layout.addWidget(side_panel_header)

        side_panel_layout.addWidget(Separator())

        self.side_panel_host = QScrollArea()
        self.side_panel_host.setWidgetResizable(True)
        self.side_panel_host.setFrameShape(QFrame.Shape.NoFrame)
        self.side_panel_host.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.side_panel_host.verticalScrollBar().rangeChanged.connect(
            self._side_panel_scroll_range_changed
        )
        side_panel_layout.addWidget(self.side_panel_host, 1)
        self.side_panel_frame.setMinimumWidth(380)
        self.side_panel_frame.setMaximumWidth(760)
        self.side_panel_frame.hide()

        self.workspace_splitter.addWidget(camera_workspace)
        self.workspace_splitter.addWidget(self.side_panel_frame)
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 0)
        layout.addWidget(self.workspace_splitter, 1)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(create_state_icon(self._state), self)
        self.tray_menu = QMenu(self)
        self.tray.setContextMenu(self.tray_menu)
        show_action = QAction(tr("Show Vulture"), self)
        show_action.triggered.connect(self._show_window)
        self.pause_action = QAction(
            tr("Release camera")
            if self._tracking_enabled
            else tr("Resume tracking"),
            self,
        )
        self.pause_action.triggered.connect(self._toggle_tracking)
        self.calibrate_action = QAction(
            tr("Calibrate current setup"),
            self,
        )
        self.calibrate_action.triggered.connect(self._calibrate)
        self.recalibrate_step_action = QAction(
            tr("Recalibrate step"),
            self,
        )
        self.recalibrate_step_action.triggered.connect(
            self._recalibrate_step
        )
        self.summary_action = QAction(tr("Workday summary"), self)
        self.summary_action.setEnabled(self.history_store is not None)
        self.summary_action.triggered.connect(self._show_workday_summary)
        self.open_exercise_action = QAction(tr("Open movement"), self)
        self.open_exercise_action.setVisible(False)
        self.open_exercise_action.triggered.connect(
            self._open_pending_exercise
        )
        quit_action = QAction(tr("Quit"), self)
        quit_action.triggered.connect(self.quit_application)
        self.tray_menu.addAction(show_action)
        self.tray_menu.addAction(self.pause_action)
        self.tray_menu.addAction(self.calibrate_action)
        self.tray_menu.addAction(self.recalibrate_step_action)
        self.tray_menu.addAction(self.summary_action)
        self.tray_menu.addAction(self.open_exercise_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(quit_action)
        self.tray.activated.connect(self._tray_activated)
        self.tray.messageClicked.connect(self._tray_message_clicked)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _refresh_setup_combo(self) -> None:
        self.setup_combo.blockSignals(True)
        self.setup_combo.clear()
        for setup in self.data.setups:
            label = setup.name
            if setup.calibration is None:
                label += tr(" (not calibrated)")
            self.setup_combo.addItem(label, setup.id)
        if self.data.active_setup_id is not None:
            index = self.setup_combo.findData(self.data.active_setup_id)
            if index >= 0:
                self.setup_combo.setCurrentIndex(index)
        self.setup_combo.blockSignals(False)
        has_setup = bool(self.data.setups)
        controls_enabled = not self._calibration_flow_active
        camera_controls_enabled = (
            has_setup and controls_enabled and self._tracking_enabled
        )
        self.preview_stack.setCurrentWidget(
            self.preview if has_setup else self.first_run_panel
        )
        self.status_group.setVisible(has_setup)
        self.setup_combo.setEnabled(has_setup and controls_enabled)
        self.add_setup_command.setEnabled(controls_enabled)
        self.first_run_add_button.setEnabled(controls_enabled)
        self.calibrate_command.setEnabled(camera_controls_enabled)
        self.calibrate_action.setEnabled(camera_controls_enabled)
        self.pause_command.setEnabled(has_setup and controls_enabled)
        self.settings_command.setEnabled(controls_enabled)
        can_recalibrate_step = (
            camera_controls_enabled
            and self.data.active_setup() is not None
            and self.data.active_setup().calibration is not None
        )
        self.recalibrate_step_command.setEnabled(can_recalibrate_step)
        self.recalibrate_step_action.setEnabled(can_recalibrate_step)
        self.pause_action.setEnabled(has_setup and controls_enabled)
        self.summary_button.setEnabled(
            controls_enabled and self.history_store is not None
        )
        self.summary_action.setEnabled(
            controls_enabled and self.history_store is not None
        )
        self.evidence_button.setEnabled(controls_enabled)
        self.move_now_button.setEnabled(controls_enabled)

    def _add_setup(self) -> None:
        if self._language_reload_preparing:
            return
        if self._setup_dialog is not None:
            self._secondary_window_presenter.focus(self._setup_dialog)
            return
        dialog = SetupDialog(self)
        self._setup_dialog = dialog
        self._secondary_window_presenter.present(
            "setup",
            dialog,
            modality=Qt.WindowModality.WindowModal,
        )
        dialog.finished.connect(
            lambda result, active_dialog=dialog: (
                self._finish_add_setup(active_dialog, result)
            )
        )

    def _finish_add_setup(
        self,
        dialog: SetupDialog,
        result: int,
    ) -> None:
        if dialog is not self._setup_dialog:
            return
        self._setup_dialog = None
        if result != QDialog.DialogCode.Accepted:
            return
        setup = dialog.setup_profile()
        if not self._stop_camera():
            self._show_camera_release_error()
            return
        self.data.setups.append(setup)
        self.data.active_setup_id = setup.id
        self._save_data()
        self._refresh_setup_combo()
        self._activate_setup()
        if self._tracking_enabled:
            self._calibrate()

    def _setup_changed(self, index: int) -> None:
        if self._language_reload_preparing:
            return
        setup_id = self.setup_combo.itemData(index)
        if not setup_id or setup_id == self.data.active_setup_id:
            return
        previous_setup_id = self.data.active_setup_id
        if not self._stop_camera():
            self.setup_combo.blockSignals(True)
            previous_index = self.setup_combo.findData(previous_setup_id)
            if previous_index >= 0:
                self.setup_combo.setCurrentIndex(previous_index)
            self.setup_combo.blockSignals(False)
            self._show_camera_release_error()
            return
        self.data.active_setup_id = setup_id
        self._save_data()
        self._refresh_setup_combo()
        self._activate_setup()

    def _activate_setup(self) -> None:
        if self._language_reload_preparing:
            return
        if not self._stop_camera():
            self._show_camera_release_error()
            return
        setup = self.data.active_setup()
        if setup is None:
            self.evaluator = None
            self._set_state(
                TrackerState.UNCALIBRATED,
                tr("Select or add a setup."),
            )
            return
        self.evaluator = (
            PostureEvaluator(setup.calibration, self.data.alert_policy)
            if setup.calibration is not None
            else None
        )
        if not self._tracking_enabled:
            self._show_camera_released_state()
            return
        camera = resolve_camera_descriptor(setup.camera)
        if camera is None:
            self._set_state(
                TrackerState.CAMERA_UNAVAILABLE,
                tr("The camera saved for this setup is not available."),
            )
            return
        self._latest_image = None
        self.preview.clear()
        self.preview.setText(tr("Starting camera..."))
        self.preview.setAccessibleName(tr("Camera preview"))
        self.camera_thread = CameraThread(camera, parent=self)
        self.camera_thread.set_preview_enabled(
            self._camera_preview_visible()
        )
        self.camera_thread.preview_ready.connect(self._on_preview)
        self.camera_thread.feature_ready.connect(self._on_feature)
        self.camera_thread.tracking_lost.connect(self._on_tracking_lost)
        self.camera_thread.camera_error.connect(self._on_camera_error)
        self.camera_thread.start()
        self._reset_camera_liveness()
        if setup.calibration is None:
            self._set_state(
                TrackerState.UNCALIBRATED,
                tr(
                    "Camera is ready. Calibrate this physical setup before "
                    "tracking."
                ),
            )
        elif self._tracking_enabled:
            self._set_state(
                TrackerState.LOW_CONFIDENCE,
                tr("Finding your face and shoulders..."),
            )

    def _stop_camera(self, timeout_milliseconds: int = 3000) -> bool:
        self._suspend_history()
        if self.camera_thread is None:
            return True
        camera_thread = self.camera_thread
        if camera_thread.stop(timeout_milliseconds):
            camera_thread.deleteLater()
            self.camera_thread = None
            return True
        return False

    def _camera_is_healthy(self) -> bool:
        return (
            self.camera_thread is not None
            and self.camera_thread.isRunning()
            and self.camera_thread.failure_message is None
            and self._camera_liveness_stage < 2
        )

    def _show_camera_release_error(self) -> None:
        self._set_state(
            TrackerState.CAMERA_UNAVAILABLE,
            tr(
                "The previous camera has not released yet; setup switching "
                "is paused."
            ),
        )
        self._show_notice(
            tr("Camera still busy"),
            tr(
                "The current camera driver has not released safely. Wait a "
                "moment or disconnect the camera before switching setups."
            ),
            critical=True,
        )

    def _begin_calibration_flow(self) -> bool:
        if self._calibration_flow_active:
            self._focus_calibration_window()
            self._show_tray_message(
                tr("Calibration already open"),
                tr(
                    "Finish or cancel the current calibration before starting "
                    "another."
                ),
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )
            return False
        self._calibration_flow_active = True
        if self._side_panel is not None:
            self._dismiss_side_panel()
        self._refresh_setup_combo()
        return True

    @staticmethod
    def _adopt_panel_width(panel: QDialog) -> None:
        """Hand the panel's width budget over to the side-panel host.

        Dialogs carry a minimum width that suits them as free-floating
        windows. Hosted in the scroll area that minimum becomes a floor the
        viewport cannot go below, so the last pixels are clipped as soon as a
        vertical scrollbar appears. The dialog's preference is preserved as
        the requested panel width instead.
        """
        requested = max(
            panel.minimumWidth(),
            panel.property("preferredSidePanelWidth") or 0,
        )
        if requested > 0:
            panel.setProperty("preferredSidePanelWidth", requested)
        panel.setMinimumWidth(0)

    def _show_side_panel(self, panel: QDialog) -> None:
        previous = self._side_panel
        if previous is not None and previous is not panel:
            if previous.isVisible():
                previous.reject()
            if self._side_panel is previous:
                self._hide_side_panel(previous)

        if (
            self._size_before_side_panel is None
            and not self.isMaximized()
            and not self.isFullScreen()
        ):
            self._size_before_side_panel = self.size()

        orphaned = self.side_panel_host.takeWidget()
        if orphaned is not None and orphaned is not panel:
            orphaned.hide()
            orphaned.deleteLater()
        panel.setWindowFlags(Qt.WindowType.Widget)
        panel_layout = panel.layout()
        if panel_layout is not None:
            panel_layout.setContentsMargins(*SIDE_PANEL_CONTENT_MARGINS)
        self._adopt_panel_width(panel)
        self.side_panel_host.setWidget(panel)
        self._side_panel = panel
        title = panel.windowTitle()
        self.side_panel_title.setText(title)
        self.side_panel_close_button.setAccessibleName(
            tr("Close {title}", title=title)
        )
        self.preview_stack.setMinimumSize(340, 191)
        self.side_panel_frame.show()
        self.side_panel_host.show()
        panel.show()
        central_layout = self.centralWidget().layout()
        if central_layout is not None:
            central_layout.activate()

        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            requested_panel_size = panel.sizeHint().expandedTo(
                panel.minimumSizeHint()
            ).expandedTo(panel.minimumSize())
            preferred_width = panel.property("preferredSidePanelWidth")
            if not isinstance(preferred_width, int):
                preferred_width = 0
            requested_panel_width = min(
                max(
                    panel.minimumWidth(),
                    requested_panel_size.width(),
                    preferred_width,
                    380,
                ),
                760,
            )
            panel_vertical_overhead = max(
                0,
                self.height()
                - self.side_panel_host.viewport().height(),
            )
            requested_window_height = (
                requested_panel_size.height() + panel_vertical_overhead
            )
            if self.isMaximized() or self.isFullScreen():
                target_width = self.width()
                target_height = self.height()
            else:
                target_width = min(
                    max(self.width(), 620 + requested_panel_width),
                    available.width(),
                )
                target_height = min(
                    max(self.height(), 720, requested_window_height),
                    available.height(),
                )
                self.resize(target_width, target_height)
            panel_width = min(
                requested_panel_width,
                max(380, target_width - 340),
            )
            self.side_panel_frame.setMaximumWidth(
                max(620, requested_panel_width)
            )
            self.workspace_splitter.setSizes(
                [max(340, target_width - panel_width), panel_width]
            )
        self._show_window()
        panel.setFocus(Qt.FocusReason.OtherFocusReason)
        QTimer.singleShot(0, lambda: self._fit_side_panel_height(panel))

    def _fit_side_panel_height(self, panel: QDialog) -> None:
        """Grow for overflow that appears only after native layout settles."""
        if (
            panel is not self._side_panel
            or not panel.isVisible()
            or getattr(self, "_side_panel_height_fit_active", False)
        ):
            return
        overflow = self.side_panel_host.verticalScrollBar().maximum()
        if overflow <= 0 or self.isMaximized() or self.isFullScreen():
            return
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        target_height = min(
            self.height() + overflow,
            screen.availableGeometry().height(),
        )
        if target_height <= self.height():
            return
        self._side_panel_height_fit_active = True
        try:
            self.resize(self.width(), target_height)
            central_layout = self.centralWidget().layout()
            if central_layout is not None:
                central_layout.activate()
        finally:
            self._side_panel_height_fit_active = False

    def _side_panel_scroll_range_changed(
        self,
        _minimum: int,
        maximum: int,
    ) -> None:
        if maximum > 0 and self._side_panel is not None:
            self._fit_side_panel_height(self._side_panel)

    def _show_calibration_window(
        self,
        window: QDialog,
        *,
        key: str,
    ) -> None:
        self._calibration_window = window
        self._show_window()
        self._secondary_window_presenter.present(
            key,
            window,
            modality=Qt.WindowModality.ApplicationModal,
        )

    def _focus_side_panel(self, panel: QDialog | None = None) -> None:
        target = panel or self._side_panel
        self._show_window()
        self.side_panel_frame.show()
        self.side_panel_host.show()
        if target is not None:
            target.show()
            target.setFocus(Qt.FocusReason.OtherFocusReason)
        QApplication.alert(self)

    def _focus_calibration_window(self) -> None:
        self._show_window()
        if self._calibration_window is not None:
            self._secondary_window_presenter.focus(
                self._calibration_window
            )

    def _hide_side_panel(
        self,
        panel: QDialog | None = None,
        *,
        allow_deferred_exercise: bool = True,
    ) -> None:
        if panel is not None and panel is not self._side_panel:
            return
        hosted = self.side_panel_host.takeWidget()
        if hosted is not None:
            hosted.hide()
            hosted.deleteLater()
        self.preview_stack.setMinimumSize(640, 360)
        self.side_panel_host.hide()
        self.side_panel_frame.hide()
        self.side_panel_title.clear()
        self._side_panel = None
        QTimer.singleShot(
            0,
            lambda: self._finish_side_panel_close(
                allow_exercise=allow_deferred_exercise
            ),
        )

    def _finish_side_panel_close(self, *, allow_exercise: bool) -> None:
        self._show_deferred_panel(allow_exercise=allow_exercise)
        if self._side_panel is not None:
            return
        if self._language_reload_preparing or self._quitting:
            self._size_before_side_panel = None
            return
        self._restore_pre_panel_size()

    def _restore_pre_panel_size(self) -> None:
        previous_size = self._size_before_side_panel
        if (
            previous_size is None
            or self._side_panel is not None
            or self.isMaximized()
            or self.isFullScreen()
        ):
            return
        self._size_before_side_panel = None
        self.resize(previous_size)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_camera_preview_state()
        if (
            event.type() == QEvent.Type.WindowStateChange
            and getattr(self, "_size_before_side_panel", None) is not None
            and self._side_panel is None
        ):
            QTimer.singleShot(0, self._restore_pre_panel_size)

    def _show_deferred_panel(self, *, allow_exercise: bool) -> None:
        if (
            self._language_reload_preparing
            or self._quitting
            or self._calibration_flow_active
            or self._side_panel is not None
        ):
            return
        if self._pending_notice is not None:
            title, message, critical = self._pending_notice
            self._pending_notice = None
            self._show_notice(title, message, critical=critical)
            return
        if (
            allow_exercise
            and self._pending_exercise is not None
            and self._exercise_dialog is None
            and not self._exercise_postpone_timer.isActive()
        ):
            self._present_exercise()

    def _dismiss_side_panel(self) -> None:
        panel = self._side_panel
        if panel is None:
            return
        panel.reject()
        if self._side_panel is panel:
            self._hide_side_panel(panel)
