"""Non-modal dialog for QC staff to review and optionally remove batch comments."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal


class QcCommentDialog(QDialog):
    """
    Non-modal dialog for reviewing a single QC comment in the batch.

    Displays: Page, Field name, Field value, Comment text.
    Buttons: Previous (go back), Remove (removes comment from CSV), Next (advance).
    """

    remove_clicked = pyqtSignal()
    previous_clicked = pyqtSignal()
    next_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowTitle("Review Comment")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._page_label = QLabel("Page: —")
        self._page_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._page_label)

        self._field_label = QLabel("Field: —")
        self._field_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._field_label)

        self._value_label = QLabel("Field value: —")
        layout.addWidget(self._value_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        self._comment_label = QLabel("Comment:")
        self._comment_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._comment_label)

        self._comment_value = QLabel("—")
        self._comment_value.setWordWrap(True)
        self._comment_value.setMinimumWidth(280)
        self._comment_value.setStyleSheet(
            "QLabel { white-space: pre-wrap; color: #c0392b; font-weight: bold; font-size: 12pt; }"
        )
        layout.addWidget(self._comment_value)

        layout.addSpacing(8)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._previous_btn = QPushButton("Previous")
        self._previous_btn.clicked.connect(self._on_previous)
        button_layout.addWidget(self._previous_btn)

        self._remove_btn = QPushButton("Remove")
        self._remove_btn.setStyleSheet("background-color: #c0392b; color: white;")
        self._remove_btn.clicked.connect(self._on_remove)
        button_layout.addWidget(self._remove_btn)

        self._next_btn = QPushButton("Next")
        self._next_btn.setDefault(True)
        self._next_btn.setStyleSheet("background-color: #27ae60; color: white;")
        self._next_btn.clicked.connect(self._on_next)
        button_layout.addWidget(self._next_btn)

        layout.addLayout(button_layout)

    def set_content(
        self,
        page: int,
        field_name: str,
        field_value: str,
        comment_text: str,
    ) -> None:
        """Set the displayed content for the current comment."""
        self._page_label.setText(f"Page: {page}")
        self._field_label.setText(f"Field: {field_name or '—'}")
        self._value_label.setText(f"Field value: {field_value or '(empty)'}")
        self._comment_value.setText(comment_text or "(empty)")

    def _on_remove(self) -> None:
        self.remove_clicked.emit()

    def _on_previous(self) -> None:
        self.previous_clicked.emit()

    def _on_next(self) -> None:
        self.next_clicked.emit()
