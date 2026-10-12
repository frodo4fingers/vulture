from __future__ import annotations

import gc

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def _destroy_qt_widgets_before_interpreter_exit():
    """Tear Qt down while Python still controls the order.

    Tests leave parentless windows, dialogs and tray icons alive. Without this,
    interpreter shutdown can free the QApplication wrapper before them and the
    process aborts with heap corruption after every test has passed.
    """
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    gc.collect()
