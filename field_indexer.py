import sys
import os
import json
import csv
import cv2
import numpy as np
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QLabel, QScrollArea, QPushButton,
    QDialog, QLineEdit, QDialogButtonBox, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QSize, QPoint, QRect
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QMouseEvent, QFont, QIcon
from PIL import Image
from dotenv import load_dotenv
from util import ORMMatcher
from fields import Field, Tickbox, RadioButton, RadioGroup, TextField
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TextFieldDialog(QDialog):
    """Dialog for entering text in a TextField."""
    
    def __init__(self, parent=None, initial_value=""):
        super().__init__(parent)
        self.setWindowTitle("Enter Text")
        self.setModal(True)
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        label = QLabel("Enter text:")
        layout.addWidget(label)
        
        self.text_input = QLineEdit()
        self.text_input.setText(initial_value)
        self.text_input.setPlaceholderText("Enter text...")
        layout.addWidget(self.text_input)
        
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.text_input.setFocus()
    
    def get_text(self):
        return self.text_input.text()


class CSVManager:
    """Manages CSV file loading, header generation, and saving."""
    
    def __init__(self):
        self.csv_path = None
        self.csv_dir = None
        self.rows = []
        self.headers = []
        self.field_names = []  # Ordered list of field names from JSON files
    
    def load_csv(self, csv_path, json_folder):
        """Load CSV file and ensure it has proper structure."""
        self.csv_path = csv_path
        self.csv_dir = os.path.dirname(os.path.abspath(csv_path))
        
        # Read existing CSV
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            self.rows = list(reader)
        
        # Get field names from JSON files
        self.field_names = self._get_field_names_from_json(json_folder)
        
        # Check if headers exist
        if len(self.rows) == 0:
            # Empty file, add headers
            self.headers = ['tiff_path'] + self.field_names
            self.rows = [self.headers]
        else:
            # Check if first row looks like headers
            first_row = self.rows[0]
            if first_row and first_row[0].lower() in ['tiff_path', 'path', 'file']:
                # Has headers
                self.headers = first_row
                # Update headers if field names changed
                if self.headers != ['tiff_path'] + self.field_names:
                    self.headers = ['tiff_path'] + self.field_names
                    self.rows[0] = self.headers
            else:
                # No headers, insert them
                self.headers = ['tiff_path'] + self.field_names
                self.rows.insert(0, self.headers)
        
        # Ensure all rows have correct number of columns
        expected_cols = len(self.headers)
        for i, row in enumerate(self.rows):
            if len(row) < expected_cols:
                # Pad with empty strings
                self.rows[i] = row + [''] * (expected_cols - len(row))
            elif len(row) > expected_cols:
                # Truncate
                self.rows[i] = row[:expected_cols]
        
        logger.info(f"Loaded CSV with {len(self.rows)-1} data rows and {len(self.headers)} columns")
        return True
    
    def _get_field_names_from_json(self, json_folder):
        """Extract field names from all JSON files in order."""
        field_names = []
        page_num = 1
        
        while True:
            json_path = os.path.join(json_folder, f"{page_num}.json")
            if not os.path.exists(json_path):
                break
            
            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)
                
                # Iterate through top-level elements
                for item in data:
                    field = Field.from_dict(item)
                    if isinstance(field, RadioGroup):
                        # RadioGroup gets one column
                        if field.name not in field_names:
                            field_names.append(field.name)
                    else:
                        # Regular field
                        if field.name not in field_names:
                            field_names.append(field.name)
                
            except Exception as e:
                logger.warning(f"Error reading {json_path}: {e}")
            
            page_num += 1
        
        return field_names
    
    def get_tiff_paths(self):
        """Return list of TIFF paths from CSV (excluding header)."""
        if len(self.rows) <= 1:
            return []
        return [row[0] for row in self.rows[1:] if row[0]]
    
    def get_row_index_for_tiff(self, tiff_path):
        """Get the row index (0-based, excluding header) for a given TIFF path."""
        for i, row in enumerate(self.rows[1:]):
            if row[0] == tiff_path:
                return i
        return -1
    
    def get_field_value(self, row_index, field_name):
        """Get value for a field in a specific row."""
        if field_name not in self.headers:
            return None
        
        col_index = self.headers.index(field_name)
        actual_row = row_index + 1  # Skip header
        
        if actual_row >= len(self.rows):
            return None
        
        return self.rows[actual_row][col_index]
    
    def set_field_value(self, row_index, field_name, value):
        """Set value for a field in a specific row."""
        if field_name not in self.headers:
            logger.warning(f"Field {field_name} not in headers")
            return False
        
        col_index = self.headers.index(field_name)
        actual_row = row_index + 1  # Skip header
        
        if actual_row >= len(self.rows):
            return False
        
        self.rows[actual_row][col_index] = str(value)
        return True
    
    def save_csv(self):
        """Save CSV file back to disk."""
        if not self.csv_path:
            return False
        
        try:
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(self.rows)
            logger.info(f"Saved CSV to {self.csv_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving CSV: {e}")
            return False
    
    def get_absolute_tiff_path(self, relative_path):
        """Convert relative TIFF path to absolute path."""
        if os.path.isabs(relative_path):
            return relative_path
        return os.path.join(self.csv_dir, relative_path)


class ImageLabel(QLabel):
    """Custom QLabel for displaying form pages with field overlays."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_pixmap = None
        self.bbox = None  # Logo bounding box
        self.field_data = []  # List of Field objects
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.image_offset_x = 0
        self.image_offset_y = 0
        
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("QLabel { background-color: #2b2b2b; }")
        self.setMinimumSize(400, 400)
        
        # Callback for field clicks
        self.on_field_click = None
    
    def set_image(self, pixmap, bbox=None, field_data=None):
        """Set the image, bounding box, and fields to display."""
        self.base_pixmap = pixmap
        self.bbox = bbox
        self.field_data = field_data or []
        self.update_display()
    
    def update_display(self):
        """Update the displayed image with overlays."""
        if not self.base_pixmap:
            self.clear()
            return
        
        # Calculate scaling to fit in widget
        widget_width = self.width()
        widget_height = self.height()
        pixmap_width = self.base_pixmap.width()
        pixmap_height = self.base_pixmap.height()
        
        scale_x = widget_width / pixmap_width
        scale_y = widget_height / pixmap_height
        scale = min(scale_x, scale_y, 1.0)  # Don't scale up
        
        self.scale_x = scale
        self.scale_y = scale
        
        scaled_width = int(pixmap_width * scale)
        scaled_height = int(pixmap_height * scale)
        
        scaled_pixmap = self.base_pixmap.scaled(
            scaled_width, scaled_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # Center the image
        self.image_offset_x = (widget_width - scaled_width) // 2
        self.image_offset_y = (widget_height - scaled_height) // 2
        
        # Create display pixmap with overlays
        display_pixmap = QPixmap(widget_width, widget_height)
        display_pixmap.fill(QColor(43, 43, 43))
        
        painter = QPainter(display_pixmap)
        painter.drawPixmap(self.image_offset_x, self.image_offset_y, scaled_pixmap)
        
        # Draw logo bounding box (green) if available
        if self.bbox:
            top_left, bottom_right = self.bbox
            pen = QPen(QColor(0, 255, 0), 2)
            painter.setPen(pen)
            scaled_rect = QRect(
                self.image_offset_x + int(top_left[0] * self.scale_x),
                self.image_offset_y + int(top_left[1] * self.scale_y),
                int((bottom_right[0] - top_left[0]) * self.scale_x),
                int((bottom_right[1] - top_left[1]) * self.scale_y)
            )
            painter.drawRect(scaled_rect)
        
        # Draw fields
        logo_offset = self.bbox[0] if self.bbox else (0, 0)
        
        for field in self.field_data:
            if isinstance(field, RadioGroup):
                # Draw radio group container
                color = QColor(*field.colour) if field.colour else QColor(150, 255, 0)
                pen = QPen(color, 1)
                painter.setPen(pen)
                
                abs_x = field.x + logo_offset[0]
                abs_y = field.y + logo_offset[1]
                
                scaled_rect = QRect(
                    self.image_offset_x + int(abs_x * self.scale_x),
                    self.image_offset_y + int(abs_y * self.scale_y),
                    int(field.width * self.scale_x),
                    int(field.height * self.scale_y)
                )
                painter.drawRect(scaled_rect)
                
                # Draw individual radio buttons
                for rb in field.radio_buttons:
                    rb_abs_x = rb.x + logo_offset[0]
                    rb_abs_y = rb.y + logo_offset[1]
                    
                    rb_scaled_rect = QRect(
                        self.image_offset_x + int(rb_abs_x * self.scale_x),
                        self.image_offset_y + int(rb_abs_y * self.scale_y),
                        int(rb.width * self.scale_x),
                        int(rb.height * self.scale_y)
                    )
                    
                    # Use thicker border if selected
                    rb_pen = QPen(color, 3 if rb.value else 1)
                    painter.setPen(rb_pen)
                    painter.drawRect(rb_scaled_rect)
                    
                    # Fill if selected
                    if rb.value:
                        fill_color = QColor(*rb.colour) if rb.colour else QColor(150, 255, 0)
                        fill_color.setAlpha(100)
                        painter.fillRect(rb_scaled_rect, fill_color)
            
            elif isinstance(field, (Tickbox, TextField)):
                color = QColor(*field.colour) if field.colour else QColor(0, 255, 0)
                
                # Use thicker border if tickbox is checked or textfield has text
                border_width = 1
                if isinstance(field, Tickbox) and field.value:
                    border_width = 3
                elif isinstance(field, TextField) and field.value:
                    border_width = 3
                
                pen = QPen(color, border_width)
                painter.setPen(pen)
                
                abs_x = field.x + logo_offset[0]
                abs_y = field.y + logo_offset[1]
                
                scaled_rect = QRect(
                    self.image_offset_x + int(abs_x * self.scale_x),
                    self.image_offset_y + int(abs_y * self.scale_y),
                    int(field.width * self.scale_x),
                    int(field.height * self.scale_y)
                )
                painter.drawRect(scaled_rect)
                
                # Fill tickbox if checked
                if isinstance(field, Tickbox) and field.value:
                    fill_color = QColor(*field.colour) if field.colour else QColor(0, 255, 0)
                    fill_color.setAlpha(100)
                    painter.fillRect(scaled_rect, fill_color)
                
                # Fill and show text for TextField
                if isinstance(field, TextField) and field.value:
                    # Fill with semitransparent color
                    fill_color = QColor(*field.colour) if field.colour else QColor(0, 255, 0)
                    fill_color.setAlpha(100)
                    painter.fillRect(scaled_rect, fill_color)
                    
                    # Draw text below the field
                    painter.setPen(QColor(*field.colour))
                    font = QFont()
                    font.setPointSize(8)
                    painter.setFont(font)
                    text_rect = QRect(
                        scaled_rect.x(),
                        scaled_rect.y() + scaled_rect.height(),
                        scaled_rect.width() * 3,  # Allow text to extend
                        20
                    )
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft, field.value)
        
        painter.end()
        self.setPixmap(display_pixmap)
    
    def resizeEvent(self, event):
        """Handle resize events."""
        super().resizeEvent(event)
        self.update_display()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse clicks on fields."""
        if event.button() != Qt.MouseButton.LeftButton:
            return
        
        if not self.base_pixmap or not self.on_field_click:
            return
        
        # Convert click coordinates to image coordinates
        click_x = (event.pos().x() - self.image_offset_x) / self.scale_x
        click_y = (event.pos().y() - self.image_offset_y) / self.scale_y
        
        logo_offset = self.bbox[0] if self.bbox else (0, 0)
        
        # Check which field was clicked
        for field in self.field_data:
            if isinstance(field, RadioGroup):
                # Check individual radio buttons
                for rb in field.radio_buttons:
                    rb_abs_x = rb.x + logo_offset[0]
                    rb_abs_y = rb.y + logo_offset[1]
                    
                    if (rb_abs_x <= click_x <= rb_abs_x + rb.width and
                        rb_abs_y <= click_y <= rb_abs_y + rb.height):
                        self.on_field_click(field, rb)
                        return
            else:
                abs_x = field.x + logo_offset[0]
                abs_y = field.y + logo_offset[1]
                
                if (abs_x <= click_x <= abs_x + field.width and
                    abs_y <= click_y <= abs_y + field.height):
                    self.on_field_click(field, None)
                    return


class FieldIndexerWindow(QMainWindow):
    """Main window for the Field Indexer application."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Field Indexer")
        self.setGeometry(100, 100, 1200, 800)
        
        # Load environment variables
        load_dotenv()
        self.logo_path = os.getenv('LOGO_PATH')
        self.json_folder = os.getenv('JSON_FOLDER', './json_data')
        
        # Initialize ORM matcher
        if self.logo_path and os.path.exists(self.logo_path):
            self.matcher = ORMMatcher(self.logo_path)
        else:
            self.matcher = None
            logger.warning(f"Logo path not found or not set: {self.logo_path}")
        
        # CSV manager
        self.csv_manager = CSVManager()
        
        # Current state
        self.tiff_paths = []  # List of relative TIFF paths
        self.current_tiff_index = -1
        self.current_page_index = 0
        self.current_tiff_images = []  # List of PIL Images for current TIFF
        self.page_fields = []  # Fields for current page
        self.page_bbox = None  # Logo bbox for current page
        
        # Initialize UI
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Left panel - TIFF list
        left_panel = QVBoxLayout()
        
        load_button = QPushButton("Load Import File")
        load_button.clicked.connect(self.load_import_file)
        left_panel.addWidget(load_button)
        
        self.tiff_list = QListWidget()
        self.tiff_list.currentRowChanged.connect(self.on_tiff_selected)
        left_panel.addWidget(self.tiff_list)
        
        main_layout.addLayout(left_panel, 1)
        
        # Right panel - Image display and navigation
        right_panel = QVBoxLayout()
        
        # Page info label
        self.page_info_label = QLabel("No file loaded")
        self.page_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_panel.addWidget(self.page_info_label)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.prev_button = QPushButton("◀ Previous")
        self.prev_button.clicked.connect(self.previous_page)
        self.prev_button.setEnabled(False)
        nav_layout.addWidget(self.prev_button)
        
        self.next_button = QPushButton("Next ▶")
        self.next_button.clicked.connect(self.next_page)
        self.next_button.setEnabled(False)
        nav_layout.addWidget(self.next_button)
        
        right_panel.addLayout(nav_layout)
        
        # Image display
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.image_label = ImageLabel()
        self.image_label.on_field_click = self.on_field_click
        scroll_area.setWidget(self.image_label)
        
        right_panel.addWidget(scroll_area)
        
        main_layout.addLayout(right_panel, 3)
    
    def load_import_file(self):
        """Load the import CSV/TXT file."""
        import_folder = os.getenv('IMPORT_FOLDER', './default/folder/for/importing/filelist')
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Import File",
            import_folder,
            "Text Files (*.txt *.csv);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            # Load CSV
            self.csv_manager.load_csv(file_path, self.json_folder)
            
            # Get TIFF paths
            self.tiff_paths = self.csv_manager.get_tiff_paths()
            
            # Populate TIFF list
            self.tiff_list.clear()
            for tiff_path in self.tiff_paths:
                # Show just the filename
                filename = os.path.basename(tiff_path)
                self.tiff_list.addItem(filename)
            
            logger.info(f"Loaded {len(self.tiff_paths)} TIFF files")
            
            # Select first TIFF if available
            if self.tiff_paths:
                self.tiff_list.setCurrentRow(0)
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading import file: {e}")
            logger.error(f"Error loading import file: {e}", exc_info=True)
    
    def on_tiff_selected(self, index):
        """Handle TIFF selection from list."""
        if index < 0 or index >= len(self.tiff_paths):
            return
        
        self.current_tiff_index = index
        self.current_page_index = 0
        
        # Load TIFF
        relative_path = self.tiff_paths[index]
        absolute_path = self.csv_manager.get_absolute_tiff_path(relative_path)
        
        try:
            self.load_tiff(absolute_path)
            self.display_current_page()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading TIFF: {e}")
            logger.error(f"Error loading TIFF {absolute_path}: {e}", exc_info=True)
    
    def load_tiff(self, tiff_path):
        """Load a multipage TIFF file."""
        self.current_tiff_images = []
        
        try:
            img = Image.open(tiff_path)
            page_num = 0
            
            while True:
                try:
                    img.seek(page_num)
                    # Convert to RGB
                    page_img = img.convert('RGB')
                    self.current_tiff_images.append(page_img)
                    page_num += 1
                except EOFError:
                    break
            
            logger.info(f"Loaded {len(self.current_tiff_images)} pages from {tiff_path}")
            
        except Exception as e:
            raise Exception(f"Failed to load TIFF: {e}")
    
    def display_current_page(self):
        """Display the current page with fields."""
        if not self.current_tiff_images:
            return
        
        page_num = self.current_page_index
        
        if page_num >= len(self.current_tiff_images):
            return
        
        # Update page info
        self.page_info_label.setText(
            f"Page {page_num + 1} of {len(self.current_tiff_images)} - {os.path.basename(self.tiff_paths[self.current_tiff_index])}"
        )
        
        # Enable/disable navigation buttons
        self.prev_button.setEnabled(page_num > 0)
        self.next_button.setEnabled(page_num < len(self.current_tiff_images) - 1)
        
        # Get PIL image
        pil_image = self.current_tiff_images[page_num]
        
        # Convert to QPixmap
        img_array = np.array(pil_image)
        height, width, channel = img_array.shape
        bytes_per_line = 3 * width
        q_image = QImage(img_array.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        
        # Detect logo
        self.page_bbox = self.detect_logo(pil_image)
        
        # Load fields for this page
        self.page_fields = self.load_page_fields(page_num + 1)  # JSON files are 1-indexed
        
        # Pre-populate field values from CSV
        self.populate_field_values()
        
        # Display
        self.image_label.set_image(pixmap, self.page_bbox, self.page_fields)
    
    def detect_logo(self, pil_image):
        """Detect logo in the image, return bounding box or None."""
        if not self.matcher:
            return None
        
        try:
            # Convert PIL to OpenCV
            img_array = np.array(pil_image)
            img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            # Detect logo
            self.matcher.locate_from_cv2_image(img_cv)
            
            if self.matcher.top_left and self.matcher.bottom_right:
                logger.info(f"Logo detected at {self.matcher.top_left}")
                return (self.matcher.top_left, self.matcher.bottom_right)
            else:
                logger.warning("Logo detection failed, using (0,0)")
                return None
        
        except Exception as e:
            logger.error(f"Error detecting logo: {e}")
            return None
    
    def load_page_fields(self, page_num):
        """Load field definitions from JSON file for a given page number."""
        json_path = os.path.join(self.json_folder, f"{page_num}.json")
        
        if not os.path.exists(json_path):
            logger.warning(f"JSON file not found: {json_path}")
            return []
        
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            fields = []
            for item in data:
                field = Field.from_dict(item)
                fields.append(field)
            
            logger.info(f"Loaded {len(fields)} fields from {json_path}")
            return fields
        
        except Exception as e:
            logger.error(f"Error loading fields from {json_path}: {e}")
            return []
    
    def populate_field_values(self):
        """Pre-populate field values from CSV data."""
        if self.current_tiff_index < 0:
            return
        
        for field in self.page_fields:
            if isinstance(field, RadioGroup):
                # Get value for radio group
                value = self.csv_manager.get_field_value(self.current_tiff_index, field.name)
                if value:
                    field.value = value
                    # Set the corresponding radio button
                    for rb in field.radio_buttons:
                        rb.value = (rb.name == value)
            
            elif isinstance(field, Tickbox):
                value = self.csv_manager.get_field_value(self.current_tiff_index, field.name)
                if value:
                    field.value = value.lower() in ['true', '1', 'yes', 'checked', 'ticked', 'tick']
            
            elif isinstance(field, TextField):
                value = self.csv_manager.get_field_value(self.current_tiff_index, field.name)
                if value:
                    field.value = value
    
    def previous_page(self):
        """Navigate to previous page."""
        if self.current_page_index > 0:
            self.current_page_index -= 1
            self.display_current_page()
    
    def next_page(self):
        """Navigate to next page."""
        if self.current_page_index < len(self.current_tiff_images) - 1:
            self.current_page_index += 1
            self.display_current_page()
    
    def on_field_click(self, field, sub_field=None):
        """Handle field click events."""
        if isinstance(field, Tickbox):
            # Toggle tickbox
            field.value = not field.value
            
            # Save to CSV
            self.csv_manager.set_field_value(
                self.current_tiff_index,
                field.name,
                'Ticked' if field.value else ''
            )
            self.csv_manager.save_csv()
            
            # Update display
            self.image_label.update_display()
            logger.info(f"Tickbox '{field.name}' set to {field.value}")
        
        elif isinstance(field, RadioGroup) and sub_field:
            # Select radio button
            for rb in field.radio_buttons:
                rb.value = (rb == sub_field)
            
            field.value = sub_field.name
            
            # Save to CSV
            self.csv_manager.set_field_value(
                self.current_tiff_index,
                field.name,
                sub_field.name
            )
            self.csv_manager.save_csv()
            
            # Update display
            self.image_label.update_display()
            logger.info(f"RadioGroup '{field.name}' set to '{sub_field.name}'")
        
        elif isinstance(field, TextField):
            # Show text entry dialog
            dialog = TextFieldDialog(self, field.value)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_text = dialog.get_text()
                field.value = new_text
                
                # Save to CSV
                self.csv_manager.set_field_value(
                    self.current_tiff_index,
                    field.name,
                    new_text
                )
                self.csv_manager.save_csv()
                
                # Update display
                self.image_label.update_display()
                logger.info(f"TextField '{field.name}' set to '{new_text}'")


def main():
    app = QApplication(sys.argv)
    window = FieldIndexerWindow()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

