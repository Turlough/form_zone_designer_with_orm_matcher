from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QStyle,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent
from PyQt6.QtGui import QPixmap, QImage, QFont, QIcon, QTextCursor
from PIL import Image
import numpy as np
from datetime import datetime
from fields import Field, Tickbox, RadioButton, RadioGroup, TextField, DateField, IntegerField, DecimalField
from field_factory import FIELD_TYPE_MAP as FACTORY_FIELD_TYPE_MAP, INVALID_COLOUR
import logging

logger = logging.getLogger(__name__)


_THOUSANDS_SEP = "\u202f"  # Narrow no-break space


def _add_thousands(s: str, sep: str = _THOUSANDS_SEP) -> str:
    """Add thousands separator. Preserves leading minus."""
    neg = s.startswith("-")
    s = s.lstrip("-")
    parts = []
    for i in range(len(s), 0, -3):
        parts.append(s[max(0, i - 3) : i])
    return ("-" if neg else "") + sep.join(reversed(parts))


def _format_number_for_display(s: str) -> str:
    """Add thousands separator for display only. Returns s unchanged if not a valid number."""
    s = s.strip()
    if not s:
        return s
    s_clean = _strip_thousands_separators(s)
    try:
        if "." in s_clean:
            int_part, dec_part = s_clean.rsplit(".", 1)
            if dec_part.isdigit() and (int_part.replace("-", "").isdigit() or int_part in ("-", "")):
                return _add_thousands(int_part) + "." + dec_part
        if s_clean.replace("-", "").isdigit():
            return _add_thousands(s_clean)
    except Exception:
        pass
    return s


def _strip_thousands_separators(s: str) -> str:
    """Remove thousands separators. Keeps decimal point."""
    return s.replace(" ", "").replace(_THOUSANDS_SEP, "").replace(",", "")


class IndexDetailPanel(QWidget):
    """
    Right-side panel for the Field Indexer showing details about the current field.
    
    Layout (top to bottom):
      1. Field name label
      2. Close-up image of the current rectangle
      3. Editable text area for field value
      4. Table showing all fields with their values
    """
    
    # Emitted when the field value is changed
    # Payload is (field_name: str, new_value: str)
    field_value_changed = pyqtSignal(str, str)
    # Emitted when the user presses Enter in the value editor to complete a TextField
    # Payload is (field_name: str)
    field_edit_completed = pyqtSignal(str)

    ocr_requested = pyqtSignal()
    # Emitted when the user presses the OCR button
    # Payload is (field_name: str)
    ocr_completed = pyqtSignal(str, str)
    # Emitted when the user requests editing QC comments for a field
    # Payload is (field_name: str)
    field_comment_requested = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(8)
        self.setLayout(main_layout)
        
        # ---- 1. Field name label ----
        self.field_name_label = QLabel("No field selected")
        self.field_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.field_name_label.setFont(font)
        self.field_name_label.setStyleSheet(
            "QLabel { background-color: #3c3f41; color: #dddddd; padding: 8px; border: 1px solid #555555; }"
        )
        main_layout.addWidget(self.field_name_label)
        
        # ---- 2. Close-up image of current rectangle ----
        self.closeup_label = QLabel("No field selected")
        self.closeup_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.closeup_label.setMinimumHeight(200)
        self.closeup_label.setMaximumHeight(200)
        self.closeup_label.setScaledContents(False)  # We'll handle scaling manually
        self.closeup_label.setStyleSheet(
            "QLabel { background-color: #3c3f41; color: #dddddd; border: 1px solid #555555; }"
        )
        main_layout.addWidget(self.closeup_label)
        
        # ---- 3. Field value label + OCR (Read) button in one row ----
        value_row = QHBoxLayout()
        value_label = QLabel("Field Value:")
        value_row.addWidget(value_label)
        self.ocr_button = QPushButton()
        self.ocr_button.setIcon(
            QIcon.fromTheme(
                "document-open",
                self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView),
            )
        )
        self.ocr_button.setToolTip("OCR")
        self.ocr_button.clicked.connect(self.ocr_requested.emit)
        value_row.addWidget(self.ocr_button)
        main_layout.addLayout(value_row)
        # ---- Editable text area for field value ----
        self.value_text_edit = QTextEdit()
        self.value_text_edit.setPlaceholderText("Enter field value...")
        self.value_text_edit.setMinimumHeight(100)
        self.value_text_edit.setFont(QFont("Arial", 12))
        self.value_text_edit.textChanged.connect(self._on_value_changed)
        # Catch Enter presses so we can advance to the next TextField without inserting a newline
        self.value_text_edit.installEventFilter(self)
        main_layout.addWidget(self.value_text_edit)
        
        # ---- 4. Table showing all fields ----
        table_label = QLabel("All Fields on Current Page:")
        main_layout.addWidget(table_label)
        
        self.fields_table = QTableWidget()
        self.fields_table.setColumnCount(2)
        self.fields_table.setHorizontalHeaderLabels(["Field Name", "Field Value"])
        self.fields_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.fields_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.fields_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)  # Read-only
        self.fields_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # Double-clicking a row opens the QC comments editor for that field.
        self.fields_table.cellDoubleClicked.connect(self._on_field_row_double_clicked)
        main_layout.addWidget(self.fields_table, stretch=1)
        
        # Internal state
        self.current_field = None
        self.current_page_image = None
        self.page_bbox = None
        self.page_fields = []
        self.field_values = {}
        # Mapping of field_name -> comment string for the current page
        self.field_comments = {}

    def _get_validator_for_field(self, field: Field):
        """Look up the appropriate Validator instance for a given field."""
        for field_class, _color, validator in FACTORY_FIELD_TYPE_MAP.values():
            if type(field) is field_class:
                try:
                    if isinstance(validator, type):
                        return validator()
                    return validator
                except Exception:
                    logger.exception("Error creating validator for field %s", getattr(field, "name", ""))
                    return None
        return None

    def _get_value_for_validation(self, field: Field):
        """Normalise the current value for validation, per field type."""
        if isinstance(field, Tickbox):
            checked = bool(self.field_values.get(field.name, False))
            return "Ticked" if checked else ""
        if isinstance(field, RadioGroup):
            value = self.field_values.get(field.name, "")
            return value or ""
        value = self.field_values.get(field.name, "")
        if value is None:
            return ""
        return str(value)

    def _is_field_invalid(self, field: Field) -> bool:
        """Determine whether the current value for this field fails validation."""
        validator = self._get_validator_for_field(field)
        if validator is None:
            return False
        value = self._get_value_for_validation(field)
        try:
            return not validator.is_valid(value)
        except Exception:
            logger.error("Validation error for field %s", getattr(field, "name", ""))
            return False

    def _update_value_edit_style(self):
        """Set value_text_edit background to INVALID_COLOUR when current field is invalid."""
        if self.current_field and self._is_field_invalid(self.current_field):
            self.value_text_edit.setStyleSheet(
                f"QTextEdit {{ background-color: rgba({INVALID_COLOUR.red()}, {INVALID_COLOUR.green()}, {INVALID_COLOUR.blue()}, 0.10); }}"
            )
        else:
            self.value_text_edit.setStyleSheet("")
    
    def set_current_field(self, field: Field | None, page_image: Image.Image | None = None,
                          page_bbox=None, page_fields=None, field_values=None, field_comments=None):
        """
        Update the panel to show details for the current field.
        
        Args:
            field: The currently selected field (or None)
            page_image: PIL Image of the current page
            page_bbox: Logo bounding box tuple (top_left, bottom_right) or None
            page_fields: List of all Field objects on the current page
            field_values: Dictionary mapping field names to their values
        """
        self.current_field = field
        if page_image is not None:
            self.current_page_image = page_image
        if page_bbox is not None:
            self.page_bbox = page_bbox
        if page_fields is not None:
            self.page_fields = page_fields
        if field_values is not None:
            self.field_values = field_values
        if field_comments is not None:
            self.field_comments = field_comments
        
        self._update_display()
        
        # Schedule a delayed update of the closeup to ensure the widget is laid out
        # This helps when the widget size isn't available immediately
        QTimer.singleShot(10, self._update_closeup)
    
    def _update_display(self):
        """Update all UI elements based on current state."""
        # Update field name
        if self.current_field:
            self.field_name_label.setText(self.current_field.name or "Unnamed Field")
        else:
            self.field_name_label.setText("No field selected")
        
        # Update close-up image
        self._update_closeup()
        
        # Update value text area
        if self.current_field:
            current_value = self.field_values.get(self.current_field.name, "")
            # Convert value to string, handling different types
            if isinstance(current_value, bool):
                value_str = "Ticked" if current_value else ""
            else:
                value_str = str(current_value) if current_value else ""
            if isinstance(self.current_field, (IntegerField, DecimalField)):
                value_str = _format_number_for_display(value_str)
            
            # Block signals to avoid triggering change event while updating
            self.value_text_edit.blockSignals(True)
            self.value_text_edit.setPlainText(value_str)
            self.value_text_edit.blockSignals(False)
            self.value_text_edit.setEnabled(True)
            self.value_text_edit.selectAll()
        else:
            self.value_text_edit.blockSignals(True)
            self.value_text_edit.clear()
            self.value_text_edit.blockSignals(False)
            self.value_text_edit.setEnabled(False)

        self._update_value_edit_style()
        
        # Update fields table
        self._update_fields_table()

    def _on_field_row_double_clicked(self, row: int, column: int):
        """Handle double-clicks on the fields table to request QC comments editing."""
        if row < 0 or row >= len(self.page_fields):
            return
        field = self.page_fields[row]
        if not field or not getattr(field, "name", None):
            return
        self.field_comment_requested.emit(field.name)
    
    def _update_closeup(self):
        """Update the close-up image of the current rectangle."""
        if not self.current_field or not self.current_page_image:
            self.closeup_label.setText("No field selected")
            self.closeup_label.setPixmap(QPixmap())
            return
        
        try:
            # Get field coordinates
            field = self.current_field
            
            # Convert to absolute coordinates if bbox exists
            abs_x = field.x
            abs_y = field.y
            if self.page_bbox:
                logo_top_left = self.page_bbox[0]
                abs_x += logo_top_left[0]
                abs_y += logo_top_left[1]
            
            # Add padding around the rectangle
            padding = 20
            img_array = np.array(self.current_page_image)
            height, width = img_array.shape[:2]
            
            # Calculate crop region with padding
            crop_x1 = max(0, abs_x - padding)
            crop_y1 = max(0, abs_y - padding)
            crop_x2 = min(width, abs_x + field.width + padding)
            crop_y2 = min(height, abs_y + field.height + padding)
            
            # Extract the region and make a contiguous copy for QImage
            crop_region = img_array[crop_y1:crop_y2, crop_x1:crop_x2].copy()
            
            if crop_region.size == 0:
                self.closeup_label.setText("Invalid region")
                self.closeup_label.setPixmap(QPixmap())
                return
            
            # Convert to QPixmap
            crop_height, crop_width = crop_region.shape[:2]
            bytes_per_line = 3 * crop_width
            q_image = QImage(
                crop_region.data,
                crop_width,
                crop_height,
                bytes_per_line,
                QImage.Format.Format_RGB888
            )
            pixmap = QPixmap.fromImage(q_image)
            
            # Get the available size of the label (fixed height, variable width)
            label_size = self.closeup_label.size()
            
            # If label doesn't have a valid size yet, use minimum dimensions
            if label_size.width() <= 0 or label_size.height() <= 0:
                # Use the label's minimum/maximum size hints
                label_size = self.closeup_label.sizeHint()
                if label_size.width() <= 0:
                    label_size = self.closeup_label.minimumSizeHint()
            
            # Scale the image to fit the available area while preserving aspect ratio
            # Account for any margins/padding in the label
            available_width = max(1, label_size.width() - 4)  # Subtract small margin
            available_height = max(1, label_size.height() - 4)  # Subtract small margin
            
            scaled = pixmap.scaled(
                available_width,
                available_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.closeup_label.setPixmap(scaled)
            self.closeup_label.setText("")
            # Force an update to ensure the label repaints
            self.closeup_label.update()
        
        except Exception as e:
            self.closeup_label.setText(f"Error: {str(e)}")
            self.closeup_label.setPixmap(QPixmap())
            import traceback
            traceback.print_exc()
    
    def _update_fields_table(self):
        """Update the table showing all fields and their values."""
        self.fields_table.setRowCount(len(self.page_fields))
        
        current_field_name = self.current_field.name if self.current_field else None
        
        for row, field in enumerate(self.page_fields):
            # Field name
            name_item = QTableWidgetItem(field.name or "Unnamed")
            self.fields_table.setItem(row, 0, name_item)
            
            # Field value (truncated if long)
            value = self.field_values.get(field.name, "")
            if isinstance(value, bool):
                value_str = "Ticked" if value else ""
            else:
                value_str = str(value) if value else ""
            if isinstance(field, (IntegerField, DecimalField)):
                value_str = _format_number_for_display(value_str)
            
            # Truncate if too long
            max_length = 50
            if len(value_str) > max_length:
                value_str = value_str[:max_length] + "..."
            
            value_item = QTableWidgetItem(value_str)
            self.fields_table.setItem(row, 1, value_item)

            has_comment = bool(self.field_comments.get(field.name or "", "").strip())

            # Emphasize current field
            if field.name == current_field_name:
                name_item.setBackground(Qt.GlobalColor.darkBlue)
                name_item.setForeground(Qt.GlobalColor.white)
                value_item.setBackground(Qt.GlobalColor.darkBlue)
                value_item.setForeground(Qt.GlobalColor.white)
                # Make it bold
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
                value_item.setFont(font)
            elif has_comment:
                # Red background for commented fields (non-selected)
                name_item.setBackground(Qt.GlobalColor.red)
                name_item.setForeground(Qt.GlobalColor.white)
                value_item.setBackground(Qt.GlobalColor.red)
                value_item.setForeground(Qt.GlobalColor.white)
    
    def _on_value_changed(self):
        """Handle changes to the value text area."""
        if not self.current_field:
            return

        new_value = self.value_text_edit.toPlainText()

        # Auto-format DateField: when user types 4 digits (e.g. 3112), format as dd/mm/yyyy
        if isinstance(self.current_field, DateField) and len(new_value) == 4 and new_value.isdigit():
            dd, mm = new_value[:2], new_value[2:4]
            year = datetime.now().year
            formatted = f"{dd}/{mm}/{year}"
            self.value_text_edit.blockSignals(True)
            self.value_text_edit.setPlainText(formatted)
            self.value_text_edit.blockSignals(False)
            new_value = formatted

        # IntegerField/DecimalField: strip thousands separators before storing
        if isinstance(self.current_field, (IntegerField, DecimalField)):
            new_value = _strip_thousands_separators(new_value)
            formatted = _format_number_for_display(new_value)
            if formatted != self.value_text_edit.toPlainText():
                self.value_text_edit.blockSignals(True)
                self.value_text_edit.setPlainText(formatted)
                cursor = self.value_text_edit.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.value_text_edit.setTextCursor(cursor)
                self.value_text_edit.blockSignals(False)
        else:
            new_value = new_value.upper()
        field_name = self.current_field.name
        
        # Update local field_values
        self.field_values[field_name] = new_value
        
        # Emit signal
        self.field_value_changed.emit(field_name, new_value)
        
        # Update the table to reflect the change
        self._update_fields_table()
        self._update_value_edit_style()
    
    def resizeEvent(self, event):
        """Handle resize events to update close-up image."""
        super().resizeEvent(event)
        if self.current_field:
            self._update_closeup()

    def eventFilter(self, obj, event):
        """Catch Enter presses in the value editor to mark a TextField as completed."""
        if obj is self.value_text_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.current_field and isinstance(self.current_field, TextField) and self.current_field.name:
                    self.field_edit_completed.emit(self.current_field.name)
                    # Swallow the event so we don't insert a newline
                    return True
        return super().eventFilter(obj, event)
