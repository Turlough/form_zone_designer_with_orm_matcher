from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect


class IndexCommentDialog(QDialog):
    """
    Dialog for adding or editing QC comments for a field.

    - Shows a list of preset comments loaded from qc_comments.txt.
    - Selecting a preset populates the editable text box.
    - Submit confirms the comment; Cancel closes without changes.
    - Positioned to the left of the associated field rectangle on the image.
    """

    # Emitted when the user submits a comment.
    # Payload: (field_name: str, comment: str)
    comment_submitted = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self._field_name: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Preset comments list
        self._preset_list = QListWidget()
        self._preset_list.itemClicked.connect(self._on_preset_clicked)
        layout.addWidget(self._preset_list)

        # Editable comment box
        self._comment_edit = QTextEdit()
        self._comment_edit.setPlaceholderText("Enter comment...")
        layout.addWidget(self._comment_edit)

        # Buttons (Submit default, Cancel)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Submit")
        button_box.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)
        button_box.accepted.connect(self._on_submit)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def set_field(self, field_name: str, initial_comment: str, presets: list[str]):
        """Set the target field, initial comment text, and preset list."""
        self._field_name = field_name or ""
        self.setWindowTitle(self._field_name or "Field Comment")

        # Populate presets list
        self._preset_list.clear()
        for text in presets or []:
            text = (text or "").strip()
            if not text:
                continue
            self._preset_list.addItem(QListWidgetItem(text))

        # Set initial comment text
        self._comment_edit.blockSignals(True)
        self._comment_edit.setPlainText(initial_comment or "")
        self._comment_edit.blockSignals(False)

    def show_left_of_rect(self, global_rect: QRect):
        """
        Position the dialog to the left of the given global QRect representing
        the field on screen, vertically centered relative to the field.
        """
        self.adjustSize()
        size_hint = self.sizeHint()
        margin = 8

        x = global_rect.left() - size_hint.width() - margin
        y = global_rect.top() + (global_rect.height() - size_hint.height()) // 2

        if x < 0:
            x = 0
        if y < 0:
            y = 0

        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_preset_clicked(self, item: QListWidgetItem):
        """Populate the comment edit box when a preset is selected."""
        if not item:
            return
        text = item.text() or ""
        self._comment_edit.blockSignals(True)
        self._comment_edit.setPlainText(text)
        self._comment_edit.blockSignals(False)

    def _on_submit(self):
        """Emit the submitted comment and close the dialog."""
        if not self._field_name:
            self.accept()
            return
        comment = self._comment_edit.toPlainText().strip()
        self.comment_submitted.emit(self._field_name, comment)
        self.accept()

