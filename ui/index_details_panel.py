from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent
from PyQt6.QtGui import QPixmap, QImage, QFont
from PIL import Image
import numpy as np
from fields import Field, Tickbox, RadioButton, RadioGroup, TextField


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
        
        # ---- 3. Editable text area for field value ----
        value_label = QLabel("Field Value:")
        main_layout.addWidget(value_label)
        
        self.value_text_edit = QTextEdit()
        self.value_text_edit.setPlaceholderText("Enter field value...")
        self.value_text_edit.setMinimumHeight(100)
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
        main_layout.addWidget(self.fields_table, stretch=1)
        
        # Internal state
        self.current_field = None
        self.current_page_image = None
        self.page_bbox = None
        self.page_fields = []
        self.field_values = {}
    
    def set_current_field(self, field: Field | None, page_image: Image.Image | None = None, 
                          page_bbox=None, page_fields=None, field_values=None):
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
            
            # Block signals to avoid triggering change event while updating
            self.value_text_edit.blockSignals(True)
            self.value_text_edit.setPlainText(value_str)
            self.value_text_edit.blockSignals(False)
            self.value_text_edit.setEnabled(True)
        else:
            self.value_text_edit.blockSignals(True)
            self.value_text_edit.clear()
            self.value_text_edit.blockSignals(False)
            self.value_text_edit.setEnabled(False)
        
        # Update fields table
        self._update_fields_table()
    
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
            
            # Truncate if too long
            max_length = 50
            if len(value_str) > max_length:
                value_str = value_str[:max_length] + "..."
            
            value_item = QTableWidgetItem(value_str)
            self.fields_table.setItem(row, 1, value_item)
            
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
    
    def _on_value_changed(self):
        """Handle changes to the value text area."""
        if not self.current_field:
            return
        
        new_value = self.value_text_edit.toPlainText()
        field_name = self.current_field.name
        
        # Update local field_values
        self.field_values[field_name] = new_value
        
        # Emit signal
        self.field_value_changed.emit(field_name, new_value)
        
        # Update the table to reflect the change
        self._update_fields_table()
    
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
