from datetime import datetime
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from fields import DateField

# Fixed height for the dialog: one line of text (line edit + minimal padding).
# Large enough to show one line; total window height includes title bar.
SINGLE_LINE_DIALOG_HEIGHT = 56


class IndexTextDialog(QDialog):
    """
    Dialog for entering text for an index TextField.
    Shown directly under the clicked TextField; width matches the field width.
    Window title is the name of the TextField.
    Text is synced with IndexDetailPanel's value_text_edit via field_value_changed.
    """

    # Emitted when the user changes the text. Payload: (field_name: str, new_value: str)
    text_changed = pyqtSignal(str, str)
    # Emitted when the user presses Enter to complete editing this TextField
    # Payload is (field_name: str)
    field_edit_completed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self._field_name = ""
        self._field = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._line_edit = QLineEdit()
        self._line_edit.setPlaceholderText("Enter field value...")
        self._line_edit.textChanged.connect(self._on_text_changed)
        self._line_edit.returnPressed.connect(self._on_return_pressed)
        layout.addWidget(self._line_edit)
        self.setFixedHeight(SINGLE_LINE_DIALOG_HEIGHT)

    def set_field(self, field_name: str, initial_value: str = "", field=None):
        """Set the field name (window title), initial text, and optional field for type-specific behaviour."""
        self._field_name = field_name or ""
        self._field = field
        self.setWindowTitle(self._field_name or "TextField")
        self._line_edit.blockSignals(True)
        self._line_edit.setText(initial_value or "")
        self._line_edit.blockSignals(False)

    def set_text(self, value: str):
        """Update the line edit from outside (e.g. when detail panel value changes)."""
        self._line_edit.blockSignals(True)
        self._line_edit.setText(value or "")
        self._line_edit.blockSignals(False)

    @property
    def field_name(self) -> str:
        return self._field_name

    def _on_text_changed(self, text: str):
        if not self._field_name:
            return

        # Auto-format DateField: when user types 4 digits (e.g. 3112), format as dd/mm/yyyy
        if isinstance(self._field, DateField) and len(text) == 4 and text.isdigit():
            dd, mm = text[:2], text[2:4]
            year = datetime.now().year
            formatted = f"{dd}/{mm}/{year}"
            self._line_edit.blockSignals(True)
            self._line_edit.setText(formatted)
            self._line_edit.blockSignals(False)
            text = formatted

        text = text.upper()
        self.text_changed.emit(self._field_name, text)

    def _on_return_pressed(self):
        """Handle Enter in the dialog: complete this field and hide the dialog."""
        if self._field_name:
            self.field_edit_completed.emit(self._field_name)

    def show_under_rect(self, global_bottom_left: QPoint, width: int):
        """
        Set dialog width and position it so its top-left is just under
        the given global point (bottom-left of the TextField), with the same width.
        Height is kept constant (one line of text).
        """
        self.setFixedWidth(max(80, width))
        self.setFixedHeight(SINGLE_LINE_DIALOG_HEIGHT)
        # Position top-left of dialog at (global_bottom_left.x(), global_bottom_left.y())
        # so dialog appears directly below the field
        self.move(global_bottom_left)
        self.show()
        self._line_edit.setFocus(Qt.FocusReason.OtherFocusReason)
