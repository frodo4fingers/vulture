from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from .common import SemanticLabel
from .theme import SECTION_SPACING, CaptionLabel


def details_caption(text: str) -> CaptionLabel:
    """A wrapped caption whose text can be selected by mouse or keyboard."""
    label = CaptionLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
        | Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    # Tab reaches it, so keyboard users can copy the error for support.
    label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return label


class NoticeDialog(QDialog):
    def __init__(
        self,
        title: str,
        message: str,
        *,
        critical: bool = False,
        details: str | None = None,
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
        if details:
            self.details_label = details_caption(details)
            layout.addWidget(self.details_label)
        layout.addStretch()
