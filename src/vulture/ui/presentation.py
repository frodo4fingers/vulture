from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QApplication, QDialog, QWidget


class SecondaryWindowPresenter:
    def __init__(self, owner: QWidget) -> None:
        self._owner = owner
        self._windows: dict[str, QDialog] = {}
        self._sizes: dict[str, QSize] = {}
        self._hidden_for_owner: set[str] = set()

    def present(
        self,
        key: str,
        window: QDialog,
        *,
        modality: Qt.WindowModality = Qt.WindowModality.NonModal,
    ) -> QDialog:
        if key in self._windows:
            raise RuntimeError(
                f"Secondary window is already registered: {key}"
            )

        saved_size = self._sizes.get(key)
        if saved_size is not None:
            window.resize(saved_size)
        self._fit_to_screen(window)
        self._position_beside_owner(window)
        window.setWindowModality(modality)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        window.finished.connect(
            lambda _result, active_window=window: self._release(
                key,
                active_window,
            )
        )
        self._windows[key] = window
        self.focus(window, alert=False)
        return window

    def focus(self, window: QDialog, *, alert: bool = True) -> None:
        for key, active_window in self._windows.items():
            if active_window is window:
                self._hidden_for_owner.discard(key)
                break
        if window.windowState() & Qt.WindowState.WindowMinimized:
            window.showNormal()
        else:
            window.show()
        window.raise_()
        window.activateWindow()
        if alert:
            QApplication.alert(window)

    def hide_for_owner(self) -> None:
        self._hidden_for_owner.update(
            key for key, window in self._windows.items() if window.isVisible()
        )
        for key in self._hidden_for_owner:
            self._windows[key].hide()

    def restore_for_owner(self) -> None:
        hidden_keys = tuple(self._hidden_for_owner)
        self._hidden_for_owner.clear()
        for key in hidden_keys:
            window = self._windows.get(key)
            if window is not None:
                window.show()

    def close_all(self) -> None:
        for window in tuple(self._windows.values()):
            window.reject()

    def has_open_windows(self) -> bool:
        return bool(self._windows)

    def _release(self, key: str, window: QDialog) -> None:
        if self._windows.get(key) is not window:
            return
        self._sizes[key] = window.size()
        self._hidden_for_owner.discard(key)
        del self._windows[key]

    def _fit_to_screen(self, window: QDialog) -> None:
        screen = self._owner.screen()
        if screen is None:
            return
        available_size = screen.availableGeometry().size()
        minimum_size = window.minimumSize().boundedTo(available_size)
        target_size = window.size().boundedTo(available_size)
        window.resize(target_size.expandedTo(minimum_size))

    def _position_beside_owner(self, window: QDialog) -> None:
        screen = self._owner.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        owner_geometry = self._owner.frameGeometry()
        gap = 16
        cascade_offset = 28 * len(self._windows)
        x = owner_geometry.right() + gap + cascade_offset
        if x + window.width() > available.right() + 1:
            x = (
                owner_geometry.left()
                - window.width()
                - gap
                + cascade_offset
            )
        x = min(
            max(x, available.left()),
            max(available.left(), available.right() - window.width() + 1),
        )
        y = min(
            max(owner_geometry.top() + cascade_offset, available.top()),
            max(available.top(), available.bottom() - window.height() + 1),
        )
        window.move(x, y)
