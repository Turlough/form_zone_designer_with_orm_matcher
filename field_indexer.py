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
from util.app_state import load_state, save_state
from fields import Field, Tickbox, RadioButton, RadioGroup, TextField
import logging
from ui import MainImageIndexPanel, IndexDetailPanel, IndexTextDialog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        # Restore last import file, page, and config folder if available
        self._try_restore_last_session()
    
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
        
        self.image_label = MainImageIndexPanel()
        self.image_label.on_field_click = self.on_field_click
        scroll_area.setWidget(self.image_label)
        
        center_panel.addWidget(scroll_area)
        
        main_layout.addLayout(center_panel, 3)
        
        # Right panel - Field detail panel
        self.detail_panel = IndexDetailPanel()
        self.detail_panel.field_value_changed.connect(self.on_detail_panel_value_changed)
        # Enter in the detail panel's value editor completes the current TextField
        self.detail_panel.field_edit_completed.connect(self.on_detail_panel_edit_completed)
        main_layout.addWidget(self.detail_panel, stretch=1)

        # Text field popup dialog (shown under clicked TextField; synced with detail panel)
        self._index_text_dialog = IndexTextDialog(self)
        self._index_text_dialog.text_changed.connect(self.on_index_text_dialog_value_changed)
        # Enter in the floating dialog also completes the current TextField
        self._index_text_dialog.field_edit_completed.connect(self.on_index_text_dialog_edit_completed)
    
    def _load_import_file_from_path(self, file_path: str, json_folder_override: str | None = None) -> bool:
        """Load import file from path (no dialog). If json_folder_override is set, use it for this load. Returns True on success."""
        try:
            if json_folder_override:
                self.json_folder = json_folder_override
            self.csv_manager.load_csv(file_path, self.json_folder)
            self.tiff_paths = self.csv_manager.get_tiff_paths()
            self.tiff_list.clear()
            for tiff_path in self.tiff_paths:
                filename = os.path.basename(tiff_path)
                self.tiff_list.addItem(filename)
            logger.info(f"Loaded {len(self.tiff_paths)} TIFF files")
            return True
        except Exception as e:
            logger.warning("Could not load import file from path %s: %s", file_path, e)
            return False

    def _try_restore_last_session(self) -> None:
        """Restore last import file, config folder (json_folder), and page from persisted state if valid."""
        state = load_state()
        last_import = (state.get("last_import_file") or "").strip()
        if not last_import or not Path(last_import).exists():
            return
        last_json = (state.get("last_indexer_json_folder") or "").strip()
        if last_json:
            self.json_folder = last_json
        try:
            if not self._load_import_file_from_path(last_import):
                return
            if not self.tiff_paths:
                return
            tiff_idx = state.get("last_indexer_tiff_index")
            if tiff_idx is None or tiff_idx < 0 or tiff_idx >= len(self.tiff_paths):
                tiff_idx = 0
            self.tiff_list.setCurrentRow(tiff_idx)
            self.on_tiff_selected(tiff_idx)
            page_idx = state.get("last_indexer_page_index")
            if page_idx is not None and page_idx >= 0 and page_idx < len(self.current_tiff_images):
                self.current_page_index = page_idx
                self.display_current_page()
            save_state(
                last_import_file=last_import,
                last_indexer_json_folder=self.json_folder,
                last_indexer_tiff_index=self.current_tiff_index,
                last_indexer_page_index=self.current_page_index,
            )
        except Exception as e:
            logger.warning("Could not restore last session: %s", e)

    def load_import_file(self):
        """Load the import CSV/TXT file."""
        state = load_state()
        last_import = (state.get("last_import_file") or "").strip()
        default_dir = str(Path(last_import).parent) if last_import and Path(last_import).exists() else ""
        if not default_dir or not Path(default_dir).exists():
            default_dir = os.getenv('IMPORT_FOLDER', './default/folder/for/importing/filelist')
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Import File",
            default_dir,
            "Text Files (*.txt *.csv);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            self.csv_manager.load_csv(file_path, self.json_folder)
            self.tiff_paths = self.csv_manager.get_tiff_paths()
            self.tiff_list.clear()
            for tiff_path in self.tiff_paths:
                filename = os.path.basename(tiff_path)
                self.tiff_list.addItem(filename)
            logger.info(f"Loaded {len(self.tiff_paths)} TIFF files")
            save_state(
                last_import_file=file_path,
                last_indexer_json_folder=self.json_folder,
                last_indexer_tiff_index=0,
                last_indexer_page_index=0,
            )
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
            save_state(last_indexer_tiff_index=index, last_indexer_page_index=self.current_page_index)
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
            save_state(last_indexer_tiff_index=self.current_tiff_index, last_indexer_page_index=self.current_page_index)
    
    def next_page(self):
        """Navigate to next page."""
        if self.current_page_index < len(self.current_tiff_images) - 1:
            self.current_page_index += 1
            self.display_current_page()
            save_state(last_indexer_tiff_index=self.current_tiff_index, last_indexer_page_index=self.current_page_index)
    
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
            # Update detail panel first so it shows the clicked field
            self.image_label.field_values = self.field_values.copy()
            self.image_label.update_display()

            # Show IndexTextDialog directly under the bottom of the TextField
            rect = self.image_label.get_field_rect_in_widget(field)
            if rect is not None:
                global_bottom_left = self.image_label.mapToGlobal(rect.bottomLeft())
                current_value = self.field_values.get(field.name, "")
                self._index_text_dialog.set_field(field.name or "TextField", current_value)
                self._index_text_dialog.show_under_rect(global_bottom_left, rect.width())

            if hasattr(self, 'detail_panel') and self.current_tiff_images:
                current_pil_image = self.current_tiff_images[self.current_page_index]
                self.detail_panel.set_current_field(
                    field,
                    page_image=current_pil_image,
                    page_bbox=self.page_bbox,
                    page_fields=self.page_fields,
                    field_values=self.field_values
                )

            logger.info(f"TextField '{field.name}' clicked, value='{self.field_values.get(field.name, '')}'")
    
    def on_detail_panel_value_changed(self, field_name: str, new_value: str):
        """Handle value changes from the detail panel."""
        # Update field_values
        self.field_values[field_name] = new_value

        # Keep IndexTextDialog in sync when user types in the detail panel
        if self._index_text_dialog.isVisible() and self._index_text_dialog.field_name == field_name:
            self._index_text_dialog.set_text(new_value)

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

    def on_index_text_dialog_value_changed(self, field_name: str, new_value: str):
        """Handle value changes from the IndexTextDialog (shown under TextField)."""
        self.field_values[field_name] = new_value

        # Keep detail panel in sync
        if hasattr(self, 'detail_panel') and self.detail_panel.current_field and self.detail_panel.current_field.name == field_name:
            self.detail_panel.set_current_field(
                self.detail_panel.current_field,
                page_image=self.detail_panel.current_page_image,
                page_bbox=self.detail_panel.page_bbox,
                page_fields=self.detail_panel.page_fields,
                field_values=self.field_values
            )

        self.image_label.field_values = self.field_values.copy()
        self.csv_manager.set_field_value(self.current_tiff_index, field_name, new_value)
        self.csv_manager.save_csv()
        self.image_label.update_display()
        logger.info(f"Field '{field_name}' value changed to '{new_value}' via text dialog")

    def _focus_next_text_field(self, current_field_name: str):
        """Move focus to the next TextField on the current page and open the dialog there."""
        if not self.page_fields:
            return

        # Get all TextFields on this page in their defined order
        text_fields = [f for f in self.page_fields if isinstance(f, TextField)]
        if not text_fields:
            return

        try:
            idx = next(i for i, f in enumerate(text_fields) if f.name == current_field_name)
        except StopIteration:
            return

        # Only advance within this page
        if idx + 1 >= len(text_fields):
            return

        next_field = text_fields[idx + 1]

        if not self.current_tiff_images:
            return

        current_pil_image = self.current_tiff_images[self.current_page_index]

        # Update detail panel selection
        if hasattr(self, 'detail_panel'):
            self.detail_panel.set_current_field(
                next_field,
                page_image=current_pil_image,
                page_bbox=self.page_bbox,
                page_fields=self.page_fields,
                field_values=self.field_values
            )

        # Show IndexTextDialog under the next TextField
        rect = self.image_label.get_field_rect_in_widget(next_field)
        if rect is not None:
            global_bottom_left = self.image_label.mapToGlobal(rect.bottomLeft())
            current_value = self.field_values.get(next_field.name, "")
            self._index_text_dialog.set_field(next_field.name or "TextField", current_value)
            self._index_text_dialog.show_under_rect(global_bottom_left, rect.width())

    def on_detail_panel_edit_completed(self, field_name: str):
        """User pressed Enter in the detail panel for this field."""
        self._focus_next_text_field(field_name)

    def on_index_text_dialog_edit_completed(self, field_name: str):
        """User pressed Enter in the floating text dialog for this field."""
        self._focus_next_text_field(field_name)


def main():
    app = QApplication(sys.argv)
    window = FieldIndexerWindow()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

