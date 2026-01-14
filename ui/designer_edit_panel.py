from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QRadioButton,
    QButtonGroup,
    QLineEdit,
    QPlainTextEdit,
    QGroupBox,
    QHBoxLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QFont


class DesignerEditPanel(QWidget):
    """
    Right-side panel used for inspecting and editing Fields / Rectangles and
    the JSON backing for the current page.

    Layout (top to bottom):
      1. Preview strip (fixed 500px high) showing a horizontal strip of the
         currently selected Field / Rectangle.
      2. Field configuration controls (ported from FieldConfigDialog).
      3. Editable JSON view for the current page.
    """

    # Emitted when the user changes the field controls (type or name).
    # Payload is a simple dict: {"field_type": str, "field_name": str}
    field_config_changed = pyqtSignal(dict)

    # Emitted whenever the JSON text changes and is syntactically valid.
    # Payload is the raw JSON string.
    page_json_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(8)
        self.setLayout(main_layout)

        # ---- 1. Preview strip for selected Field / Rectangle ----
        self.preview_label = QLabel("No selection")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setMaximumHeight(200)
        self.preview_label.setStyleSheet(
            "QLabel { background-color: #3c3f41; color: #dddddd; border: 1px solid #555555; }"
        )
        main_layout.addWidget(self.preview_label)

        # ---- 2. Field configuration controls (from FieldConfigDialog) ----
        field_group = QGroupBox("Field Configuration")
        field_layout = QVBoxLayout()
        field_group.setLayout(field_layout)

        type_label = QLabel("Field Type:")
        field_layout.addWidget(type_label)

        self.button_group = QButtonGroup(self)

        self.tickbox_radio = QRadioButton("Tickbox")
        self.radiobutton_radio = QRadioButton("RadioButton")
        self.radiogroup_radio = QRadioButton("RadioGroup")
        self.textfield_radio = QRadioButton("TextField")

        # default selection
        self.tickbox_radio.setChecked(True)

        self.button_group.addButton(self.tickbox_radio, 1)
        self.button_group.addButton(self.radiobutton_radio, 2)
        self.button_group.addButton(self.radiogroup_radio, 3)
        self.button_group.addButton(self.textfield_radio, 4)

        field_layout.addWidget(self.tickbox_radio)
        field_layout.addWidget(self.radiobutton_radio)
        field_layout.addWidget(self.radiogroup_radio)
        field_layout.addWidget(self.textfield_radio)

        name_label = QLabel("Field Name:")
        field_layout.addWidget(name_label)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter field name...")
        field_layout.addWidget(self.name_input)

        # Simple horizontal layout for future action buttons if needed
        actions_layout = QHBoxLayout()
        field_layout.addLayout(actions_layout)

        # Only emit signal when Enter key is pressed in name input (not on every text change)
        self.name_input.returnPressed.connect(self._emit_field_config_changed)

        main_layout.addWidget(field_group)

        # ---- 3. JSON editor for current page ----
        json_group = QGroupBox("Page JSON")
        json_layout = QVBoxLayout()
        json_group.setLayout(json_layout)

        self.json_editor = QPlainTextEdit()
        self.json_editor.setPlaceholderText("Page JSON will appear here when a page is loaded...")
        font = QFont("Courier New")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.json_editor.setFont(font)
        self.json_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        json_layout.addWidget(self.json_editor)

        # Connect JSON changes; validation / application is handled by the main window.
        self.json_editor.textChanged.connect(self._on_json_text_changed)

        main_layout.addWidget(json_group, stretch=1)

    # ------------------------------------------------------------------
    # Public API used by the main window
    # ------------------------------------------------------------------

    def set_preview_pixmap(self, pixmap: QPixmap | None):
        """Update the preview strip with a prepared pixmap (full-width strip)."""
        if pixmap is None or pixmap.isNull():
            self.preview_label.setText("No selection")
            self.preview_label.setPixmap(QPixmap())
            return

        # Scale the image to fit within the label's width (and height) while
        # preserving aspect ratio.
        target_width = max(1, self.preview_label.width())
        target_height = max(1, self.preview_label.height())
        scaled = pixmap.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
        self.preview_label.setText("")

    def set_field_from_object(self, field_obj):
        """
        Update the controls based on the given Field-like object.
        field_obj is expected to be one of: Field, Tickbox, RadioButton,
        RadioGroup, TextField (or compatible).
        """
        if field_obj is None:
            # Reset to defaults
            self.tickbox_radio.setChecked(True)
            self.name_input.clear()
            return

        type_name = field_obj.__class__.__name__
        mapping = {
            "Tickbox": self.tickbox_radio,
            "RadioButton": self.radiobutton_radio,
            "RadioGroup": self.radiogroup_radio,
            "TextField": self.textfield_radio,
        }
        radio = mapping.get(type_name, self.tickbox_radio)
        radio.setChecked(True)

        # Block signal emission while we programmatically update the name
        old_block = self.name_input.blockSignals(True)
        self.name_input.setText(getattr(field_obj, "name", "") or "")
        self.name_input.blockSignals(old_block)

        # After syncing, explicitly emit current config (without relying on events)
        self._emit_field_config_changed()

    def get_current_field_config(self) -> dict:
        """Return a dict with the currently selected field type and name."""
        button_id = self.button_group.checkedId()
        field_types = ["Field", "Tickbox", "RadioButton", "RadioGroup", "TextField"]
        if 0 <= button_id < len(field_types):
            field_type = field_types[button_id]
        else:
            field_type = "Field"
        field_name = self.name_input.text().strip() or "Unnamed"
        return {"field_type": field_type, "field_name": field_name}

    def set_page_json(self, json_text: str):
        """Set the JSON text for the current page without emitting change signals."""
        old_block = self.json_editor.blockSignals(True)
        self.json_editor.setPlainText(json_text or "")
        self.json_editor.blockSignals(old_block)

    def get_page_json(self) -> str:
        """Return the raw JSON text from the editor."""
        return self.json_editor.toPlainText()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit_field_config_changed(self, *args, **kwargs):
        config = self.get_current_field_config()
        self.field_config_changed.emit(config)

    def _on_json_text_changed(self):
        text = self.get_page_json()
        # Emit raw text; the main window decides when/how to validate & apply.
        self.page_json_changed.emit(text)
