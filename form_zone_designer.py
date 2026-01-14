import sys
import os
import cv2
import numpy as np
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QScrollArea,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QToolButton,
)

from PyQt6.QtGui import QPixmap, QImage, QAction
from PIL import Image
from dotenv import load_dotenv
from util import ORMMatcher, DesignerConfig
from util import detect_rectangles, load_page_fields, save_page_fields
import logging

from ui import (
    ImageDisplayWidget,
    DesignerThumbnailPanel,
    DesignerButtonLayout,
    DesignerEditPanel,
)
from fields import Field
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FormZoneDesigner(QMainWindow):
    """Main application window for Form Zone Designer."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Form Zone Designer")
        self.setGeometry(100, 100, 1200, 800)
        
        # Load environment variables for default folder location
        load_dotenv()
        self.default_config_folder = os.getenv('DESIGNER_CONFIG_FOLDER', '')
        
        # DesignerConfig instance (set when user loads a config folder)
        self.config = None
        
        # Storage for pages and their bounding boxes
        self.pages = []  # List of PIL Images
        self.page_bboxes = []  # List of (top_left, bottom_right) tuples for logos
        self.page_field_rects = []  # List of lists of field rectangles for each page
        self.page_field_data = []  # List of lists of (rect, field_type, field_name) for each page
        self.page_detected_rects = []  # List of lists of detected rectangles for each page
        self.current_page_idx = None  # Track currently displayed page
        
        # ORM matcher (initialized when config is loaded)
        self.matcher = None
        
        # Initialize UI
        self.init_ui()
        # Connect edit panel JSON changes
        if hasattr(self, "edit_panel"):
            self.edit_panel.page_json_changed.connect(self.on_page_json_changed)
    
    def init_ui(self):
        """Initialize the user interface."""
        # Create menu bar
        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')
        
        load_config_action = QAction('Load Config Folder', self)
        load_config_action.setShortcut('Ctrl+O')
        load_config_action.triggered.connect(self.load_config_folder)
        file_menu.addAction(load_config_action)
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # Left panel: Thumbnail panel
        self.thumbnail_panel = DesignerThumbnailPanel()
        self.thumbnail_panel.thumbnail_clicked.connect(self.on_thumbnail_clicked)
        main_layout.addWidget(self.thumbnail_panel)
        
        # Center panel: Image display with controls
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Control buttons (moved into DesignerButtonLayout)
        button_layout = DesignerButtonLayout(self)
        right_layout.addLayout(button_layout)
        
        # Image display
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #2b2b2b; }")
        
        self.image_display = ImageDisplayWidget(self.scroll_area)
        self.scroll_area.setWidget(self.image_display)
        right_layout.addWidget(self.scroll_area, stretch=1)

        main_layout.addWidget(right_panel, stretch=2)

        # Right-side panel: field / rectangle editor and JSON view
        self.edit_panel = DesignerEditPanel(self)
        main_layout.addWidget(self.edit_panel, stretch=1)

        # Wire selection callback from image widget to edit panel
        self.image_display.on_field_selected = self.on_field_selected
    
    def load_config_folder(self):
        """Open folder picker to select a config folder and load it."""
        # Get default folder from environment variable
        default_path = self.default_config_folder if self.default_config_folder else str(Path.home())
        
        # Open folder picker
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Config Folder",
            default_path,
            QFileDialog.Option.ShowDirsOnly
        )
        
        if not folder_path:
            # User cancelled
            return
        
        try:
            # Create DesignerConfig instance
            config_folder = Path(folder_path)
            self.config = DesignerConfig(config_folder)
            
            logger.info(f"Loaded config folder: {config_folder}")
            
            # Initialize ORM matcher if logo exists in fiducials folder
            # Look for common logo file names
            logo_candidates = ['logo.png', 'logo.tif', 'fiducial.png', 'fiducial.jpg']
            logo_path = None
            for candidate in logo_candidates:
                candidate_path = self.config.fiducials_folder / candidate
                if candidate_path.exists():
                    logo_path = str(candidate_path)
                    break
            
            if logo_path:
                self.matcher = ORMMatcher(logo_path)
                logger.info(f"Initialized ORM matcher with logo: {logo_path}")
            else:
                self.matcher = None
                logger.warning("No logo found in fiducials folder, ORM matcher not initialized")
            
            # Load the template TIFF file
            if self.config.template_path.exists():
                self.load_multipage_tiff(str(self.config.template_path))
            else:
                QMessageBox.warning(
                    self,
                    "Template Not Found",
                    f"Template file not found: {self.config.template_path}"
                )
            
        except FileNotFoundError as e:
            QMessageBox.critical(
                self,
                "Config Error",
                f"Failed to load config folder:\n{str(e)}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while loading config folder:\n{str(e)}"
            )
            logger.error(f"Error loading config folder: {e}", exc_info=True)
    
    def load_multipage_tiff(self, tiff_path):
        """Load a multipage TIFF file and process each page."""
        try:
            # Open the multipage TIFF
            with Image.open(tiff_path) as img:
                page_num = 0
                while True:
                    try:
                        img.seek(page_num)
                        # Convert to RGB if necessary
                        page = img.convert('RGB')
                        self.pages.append(page.copy())
                        page_num += 1
                    except EOFError:
                        break
            
            logger.debug(f"Loaded {len(self.pages)} pages from {tiff_path}")
            
            # Process each page with ORM matcher
            self.process_pages()
            
            # Generate thumbnails and populate list
            self.thumbnail_panel.populate_thumbnails(self.pages, self.page_bboxes, self.page_field_data)
            
        except Exception as e:
            print(f"Error loading TIFF: {e}")
    
    def process_pages(self):
        """Run ORM matcher on each page to find logo bounding boxes."""
        if not self.matcher:
            logger.warning("No matcher available, skipping logo detection")
            self.page_bboxes = [None] * len(self.pages)
            self.page_field_rects = [[] for _ in range(len(self.pages))]
            self.page_field_data = [[] for _ in range(len(self.pages))]
            self.page_detected_rects = [[] for _ in range(len(self.pages))]
            return
        
        for idx, page in enumerate(self.pages):
            # Convert PIL Image to OpenCV format
            page_array = np.array(page)
            page_cv = cv2.cvtColor(page_array, cv2.COLOR_RGB2BGR)
            
            # Run the matcher
            self.matcher.locate_from_cv2_image(page_cv)
            
            # Store the bounding box
            if self.matcher.top_left and self.matcher.bottom_right:
                self.page_bboxes.append((self.matcher.top_left, self.matcher.bottom_right))
                logger.info(f"Page {idx + 1}: Logo found at {self.matcher.top_left}")
            else:
                self.page_bboxes.append(None)
                logger.warning(f"Page {idx + 1}: No logo found")
            
            # Initialize empty field rectangles and data for this page
            self.page_field_rects.append([])
            self.page_field_data.append([])
            self.page_detected_rects.append([])
        
        # Load fields from JSON for each page
        if self.config:
            for idx in range(len(self.pages)):
                fields = load_page_fields(str(self.config.json_folder), idx, self.config.config_folder)
                self.page_field_data[idx] = fields
                # Update field_rects from loaded fields
                for field in fields:
                    self.page_field_rects[idx].append((field.x, field.y, field.width, field.height))
    
    def on_thumbnail_clicked(self, page_idx):
        """Handle thumbnail click event to display full-size page."""
        
        if 0 <= page_idx < len(self.pages):
            self.current_page_idx = page_idx
            page = self.pages[page_idx]
            bbox = self.page_bboxes[page_idx]
            field_rects = self.page_field_rects[page_idx]
            field_data = self.page_field_data[page_idx]
            detected_rects = self.page_detected_rects[page_idx]
            
            # Convert PIL Image to QPixmap
            page_array = np.array(page)
            height, width, channel = page_array.shape
            bytes_per_line = 3 * width
            q_image = QImage(page_array.data, width, height, 
                           bytes_per_line, QImage.Format.Format_RGB888)
            page_pixmap = QPixmap.fromImage(q_image)

            # Display with bounding box overlay and field rectangles
            self.image_display.set_image(page_pixmap, bbox, field_rects, field_data, detected_rects)
            
            # Set callback to update thumbnail when a rectangle is added
            def on_rect_added_handler(field_obj):
                self.page_field_data[self.current_page_idx].append(field_obj)
                if self.config:
                    save_page_fields(str(self.config.json_folder), self.current_page_idx, self.page_field_data, self.config.config_folder)
                self.update_thumbnail(self.current_page_idx)
                self.undo_button.setEnabled(True)
                logger.info(f"Page {self.current_page_idx + 1}: Added {field_obj.__class__.__name__} '{field_obj.name}' at ({field_obj.x}, {field_obj.y})")
            
            self.image_display.on_rect_added = on_rect_added_handler

            # Update JSON editor for the current page
            self._update_edit_panel_json(page_idx)
            
            # Enable/disable buttons based on current state
            self.detect_button.setEnabled(True)
            self.clear_button.setEnabled(True)
            self.undo_button.setEnabled(len(field_rects) > 0)

            # Enable zoom/fit controls now that an image is available
            self.fit_width_button.setEnabled(True)
            self.fit_height_button.setEnabled(True)
            self.autofit_button.setEnabled(True)
            self.zoom_in_button.setEnabled(True)
            self.zoom_out_button.setEnabled(True)

            # Update JSON editor for the current page
            self._update_edit_panel_json(page_idx)

    def on_page_json_changed(self, json_text: str):
        """Handle edits to the page JSON from the edit panel."""
        if self.current_page_idx is None:
            return

        if not json_text.strip():
            # Empty JSON area - treat as no-op for now
            return

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            # Ignore invalid JSON while the user is typing
            logger.warning("Invalid JSON in edit panel; ignoring until valid")
            return

        if not isinstance(data, list):
            logger.warning("Page JSON is not a list; ignoring")
            return

        # Recreate Field objects from JSON dicts
        fields = []
        for item in data:
            if isinstance(item, dict):
                try:
                    fields.append(Field.from_dict(item, self.config.config_folder if self.config else None))
                except Exception as e:
                    logger.error(f"Error converting JSON item to Field: {e}")

        page_idx = self.current_page_idx
        if page_idx < 0 or page_idx >= len(self.page_field_data):
            return

        # Update in-memory structures
        self.page_field_data[page_idx] = fields
        self.page_field_rects[page_idx] = [
            (field.x, field.y, field.width, field.height) for field in fields
        ]

        # Persist to disk
        if self.config:
            save_page_fields(str(self.config.json_folder), page_idx, self.page_field_data, self.config.config_folder)

        # Update UI (image display + thumbnail)
        self.image_display.field_data = fields
        self.image_display.field_rects = self.page_field_rects[page_idx]
        self.image_display.update_display()
        self.update_thumbnail(page_idx)

    def _update_edit_panel_json(self, page_idx: int):
        """Populate the edit panel JSON area with the current page's fields."""
        if not self.edit_panel:
            return

        if page_idx < 0 or page_idx >= len(self.page_field_data):
            self.edit_panel.set_page_json("")
            return

        fields_for_page = self.page_field_data[page_idx]

        # Convert field objects to serializable dicts using the same logic as save_page_fields
        fields_data = []
        for field_obj in fields_for_page:
            if isinstance(field_obj, Field):
                fields_data.append(field_obj.to_dict(self.config.config_folder if self.config else None))

        try:
            json_text = json.dumps(fields_data, indent=2, default=str)
        except TypeError:
            json_text = ""

        self.edit_panel.set_page_json(json_text)

    def on_field_selected(self, field_obj, global_pos):
        """
        Called when the user clicks on an existing field / rectangle on the image.
        Updates the edit panel's preview strip and field controls.
        """
        if not self.edit_panel or self.current_page_idx is None:
            return

        # Update the field controls to reflect this field
        self.edit_panel.set_field_from_object(field_obj)

        # Build a horizontal strip preview for the selected field.
        page = self.pages[self.current_page_idx]
        page_array = np.array(page)
        height, width, _ = page_array.shape

        # Field coordinates are relative to logo; convert to absolute image coords
        abs_x = field_obj.x
        abs_y = field_obj.y
        if self.page_bboxes[self.current_page_idx]:
            logo_top_left = self.page_bboxes[self.current_page_idx][0]
            abs_x += logo_top_left[0]
            abs_y += logo_top_left[1]

        top = max(0, abs_y - 50)
        bottom = min(height, abs_y + field_obj.height + 50)

        # Create a strip spanning full width, between top and bottom
        strip = page_array[top:bottom, :, :]

        if strip.size == 0:
            self.edit_panel.set_preview_pixmap(QPixmap())
            return

        strip_height, strip_width, channel = strip.shape
        bytes_per_line = 3 * strip_width
        q_image = QImage(
            strip.data,
            strip_width,
            strip_height,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        )
        strip_pixmap = QPixmap.fromImage(q_image)
        self.edit_panel.set_preview_pixmap(strip_pixmap)

    # ---- Zoom / fit button handlers ----

    def on_fit_width_clicked(self):
        if self.image_display:
            self.image_display.set_fit_width()

    def on_fit_height_clicked(self):
        if self.image_display:
            self.image_display.set_fit_height()

    def on_autofit_clicked(self):
        if self.image_display:
            self.image_display.set_autofit()

    def on_zoom_in_clicked(self):
        if self.image_display:
            self.image_display.zoom_in()

    def on_zoom_out_clicked(self):
        if self.image_display:
            self.image_display.zoom_out()
    
    def undo_last_field(self):
        """Remove the last field rectangle drawn on the current page."""
        if self.current_page_idx is not None and 0 <= self.current_page_idx < len(self.page_field_rects):
            if self.page_field_rects[self.current_page_idx]:
                removed = self.page_field_rects[self.current_page_idx].pop()
                if self.page_field_data[self.current_page_idx]:
                    removed_data = self.page_field_data[self.current_page_idx].pop()
                    logger.info(f"Removed last field on page {self.current_page_idx + 1}: {removed_data}")
                
                # Update image display
                if self.image_display.field_rects:
                    self.image_display.field_rects.pop()
                if self.image_display.field_data:
                    self.image_display.field_data.pop()
                
                # Save updated fields to JSON
                if self.config:
                    save_page_fields(str(self.config.json_folder), self.current_page_idx, self.page_field_data, self.config.config_folder)
                
                self.image_display.update_display()
                self.update_thumbnail(self.current_page_idx)
                
                # Disable undo button if no more rectangles
                if not self.page_field_rects[self.current_page_idx]:
                    self.undo_button.setEnabled(False)
    
    def clear_current_page_fields(self):
        """Clear all field rectangles on the current page."""
        if self.current_page_idx is not None and 0 <= self.current_page_idx < len(self.page_field_rects):
            self.page_field_rects[self.current_page_idx].clear()
            self.page_field_data[self.current_page_idx].clear()
            self.image_display.field_rects.clear()
            self.image_display.field_data.clear()
            
            # Save updated (empty) fields to JSON
            if self.config:
                save_page_fields(str(self.config.json_folder), self.current_page_idx, self.page_field_data, self.config.config_folder)
            
            self.image_display.update_display()
            self.update_thumbnail(self.current_page_idx)
            self.undo_button.setEnabled(False)
            logger.debug(f"Cleared all fields on page {self.current_page_idx + 1}")
    
    def detect_rectangles(self):
        """Detect rectangles on the current page using computer vision."""
        if self.current_page_idx is None or not (0 <= self.current_page_idx < len(self.pages)):
            logger.warning("No page selected for rectangle detection")
            return

        logger.debug(f"Detecting rectangles on page {self.current_page_idx + 1}...")
        page = self.pages[self.current_page_idx]
        
        # Convert PIL Image to OpenCV format
        page_array = np.array(page)
        page_cv = cv2.cvtColor(page_array, cv2.COLOR_RGB2BGR)
        
        # Run rectangle detection
        
        detected_rects = detect_rectangles(page_cv, min_area=500, max_area=50000)
        
        # Store detected rectangles
        self.page_detected_rects[self.current_page_idx] = detected_rects
        self.image_display.detected_rects = detected_rects
        
        logger.debug(f"Detected {len(detected_rects)} rectangles on page {self.current_page_idx + 1}")
        
        # Update display to show detected rectangles
        self.image_display.update_display()
        
    
    def update_thumbnail(self, page_idx):
        """Update the thumbnail for a specific page to reflect current field rectangles."""
        if 0 <= page_idx < len(self.pages):
            page = self.pages[page_idx]
            bbox = self.page_bboxes[page_idx] if page_idx < len(self.page_bboxes) else None
            field_data = self.page_field_data[page_idx] if page_idx < len(self.page_field_data) else []
            self.thumbnail_panel.update_thumbnail(page_idx, page, bbox, field_data)


def main():
    """Main entry point for the application."""
    app = QApplication(sys.argv)
    window = FormZoneDesigner()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

