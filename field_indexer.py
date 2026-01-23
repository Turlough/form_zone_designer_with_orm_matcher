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
from util import ORMMatcher, CSVManager
from fields import Field, Tickbox, RadioButton, RadioGroup, TextField
import logging
from ui import ImageLabel, IndexDetailPanel

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

class FieldIndexerWindow(QMainWindow):
    """Main window for the Field Indexer application."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Field Indexer")
        self.setGeometry(100, 100, 1200, 800)
        
        # Load environment variables
        load_dotenv()

        # TODO: Deprecate these two environment variables
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
        self.field_values = {}  # Dictionary mapping field names to values for current page
        
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
        
        # Center panel - Image display and navigation
        center_panel = QVBoxLayout()
        
        # Page info label
        self.page_info_label = QLabel("No file loaded")
        self.page_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_panel.addWidget(self.page_info_label)
        
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
        
        center_panel.addLayout(nav_layout)
        
        # Image display
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.image_label = ImageLabel()
        self.image_label.on_field_click = self.on_field_click
        scroll_area.setWidget(self.image_label)
        
        center_panel.addWidget(scroll_area)
        
        main_layout.addLayout(center_panel, 3)
        
        # Right panel - Field detail panel
        self.detail_panel = IndexDetailPanel()
        self.detail_panel.field_value_changed.connect(self.on_detail_panel_value_changed)
        main_layout.addWidget(self.detail_panel, stretch=1)
    
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
        self.image_label.set_image(pixmap, self.page_bbox, self.page_fields, self.field_values)
        
        # Update detail panel (clear selection when page changes)
        if hasattr(self, 'detail_panel'):
            self.detail_panel.set_current_field(
                None,
                page_image=pil_image,
                page_bbox=self.page_bbox,
                page_fields=self.page_fields,
                field_values=self.field_values
            )
    
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
        
        # Clear existing values for this page
        self.field_values = {}
        
        for field in self.page_fields:
            if isinstance(field, RadioGroup):
                # Get value for radio group
                value = self.csv_manager.get_field_value(self.current_tiff_index, field.name)
                if value:
                    self.field_values[field.name] = value
            
            elif isinstance(field, Tickbox):
                value = self.csv_manager.get_field_value(self.current_tiff_index, field.name)
                if value:
                    is_checked = value.lower() in ['ticked','true', '1', 'yes', 'checked', 'tick']
                    self.field_values[field.name] = is_checked
            
            elif isinstance(field, TextField):
                value = self.csv_manager.get_field_value(self.current_tiff_index, field.name)
                if value:
                    self.field_values[field.name] = value
    
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
        # Update detail panel to show the clicked field
        if hasattr(self, 'detail_panel') and self.current_tiff_images:
            current_pil_image = self.current_tiff_images[self.current_page_index]
            # For RadioGroups, show the group itself, not the individual button
            field_to_show = field
            self.detail_panel.set_current_field(
                field_to_show,
                page_image=current_pil_image,
                page_bbox=self.page_bbox,
                page_fields=self.page_fields,
                field_values=self.field_values
            )
        
        if isinstance(field, Tickbox):
            # Toggle tickbox
            current_value = self.field_values.get(field.name, False)
            new_value = not current_value
            self.field_values[field.name] = new_value
            
            # Update ImageLabel's field_values
            self.image_label.field_values = self.field_values.copy()
            
            # Save to CSV
            self.csv_manager.set_field_value(
                self.current_tiff_index,
                field.name,
                'Ticked' if new_value else ''
            )
            self.csv_manager.save_csv()
            
            # Update display
            self.image_label.update_display()
            
            # Update detail panel
            if hasattr(self, 'detail_panel') and self.current_tiff_images:
                current_pil_image = self.current_tiff_images[self.current_page_index]
                self.detail_panel.set_current_field(
                    field,
                    page_image=current_pil_image,
                    page_bbox=self.page_bbox,
                    page_fields=self.page_fields,
                    field_values=self.field_values
                )
            
            logger.info(f"Tickbox '{field.name}' set to {new_value}")
        
        elif isinstance(field, RadioGroup) and sub_field:
            # Select radio button
            self.field_values[field.name] = sub_field.name
            
            # Update ImageLabel's field_values
            self.image_label.field_values = self.field_values.copy()
            
            # Save to CSV
            self.csv_manager.set_field_value(
                self.current_tiff_index,
                field.name,
                sub_field.name
            )
            self.csv_manager.save_csv()
            
            # Update display
            self.image_label.update_display()
            
            # Update detail panel
            if hasattr(self, 'detail_panel') and self.current_tiff_images:
                current_pil_image = self.current_tiff_images[self.current_page_index]
                self.detail_panel.set_current_field(
                    field,
                    page_image=current_pil_image,
                    page_bbox=self.page_bbox,
                    page_fields=self.page_fields,
                    field_values=self.field_values
                )
            
            logger.info(f"RadioGroup '{field.name}' set to '{sub_field.name}'")
        
        elif isinstance(field, TextField):
            # Show text entry dialog
            current_value = self.field_values.get(field.name, "")
            dialog = TextFieldDialog(self, current_value)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_text = dialog.get_text()
                self.field_values[field.name] = new_text
                
                # Update ImageLabel's field_values
                self.image_label.field_values = self.field_values.copy()
                
                # Save to CSV
                self.csv_manager.set_field_value(
                    self.current_tiff_index,
                    field.name,
                    new_text
                )
                self.csv_manager.save_csv()
                
                # Update display
                self.image_label.update_display()
                
                # Update detail panel
                if hasattr(self, 'detail_panel') and self.current_tiff_images:
                    current_pil_image = self.current_tiff_images[self.current_page_index]
                    self.detail_panel.set_current_field(
                        field,
                        page_image=current_pil_image,
                        page_bbox=self.page_bbox,
                        page_fields=self.page_fields,
                        field_values=self.field_values
                    )
                
                logger.info(f"TextField '{field.name}' set to '{new_text}'")
    
    def on_detail_panel_value_changed(self, field_name: str, new_value: str):
        """Handle value changes from the detail panel."""
        # Update field_values
        self.field_values[field_name] = new_value
        
        # Update ImageLabel's field_values
        self.image_label.field_values = self.field_values.copy()
        
        # Save to CSV
        self.csv_manager.set_field_value(
            self.current_tiff_index,
            field_name,
            new_value
        )
        self.csv_manager.save_csv()
        
        # Update display
        self.image_label.update_display()
        
        logger.info(f"Field '{field_name}' value changed to '{new_value}' via detail panel")


def main():
    app = QApplication(sys.argv)
    window = FieldIndexerWindow()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

