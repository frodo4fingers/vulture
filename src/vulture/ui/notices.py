from __future__ import annotations

from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from .common import SemanticLabel
from .theme import SECTION_SPACING


class NoticeDialog(QDialog):
    def __init__(
        self,
        title: str,
        message: str,
        *,
        critical: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(SECTION_SPACING)
        message_label = SemanticLabel(
            message,
            tone="safety" if critical else "info",
        )
        layout.addWidget(message_label)
        layout.addStretch()
