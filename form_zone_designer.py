import sys
import os
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QScrollArea, QPushButton,
)

from PyQt6.QtGui import QPixmap, QImage
from PIL import Image
from dotenv import load_dotenv
from orm_matcher import ORMMatcher
from fields import Field
from util import detect_rectangles, load_page_fields, save_page_fields
import logging

from ui import ImageDisplayWidget, DesignerThumbnailPanel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FormZoneDesigner(QMainWindow):
    """Main application window for Form Zone Designer."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Form Zone Designer")
        self.setGeometry(100, 100, 1200, 800)
        
        # Load environment variables
        load_dotenv()
        self.logo_path = os.getenv('LOGO_PATH')
        self.tiff_path = os.getenv('MULTIPAGE_TIFF')
        self.json_folder = os.getenv('JSON_FOLDER', './json_data')
        
        # Create JSON folder if it doesn't exist
        if not os.path.exists(self.json_folder):
            os.makedirs(self.json_folder)
            logger.info(f"Created JSON folder: {self.json_folder}")
        
        # Initialize ORM matcher
        if self.logo_path and os.path.exists(self.logo_path):
            self.matcher = ORMMatcher(self.logo_path)
        else:
            self.matcher = None
            print(f"Warning: Logo path not found or not set: {self.logo_path}")
        
        # Storage for pages and their bounding boxes
        self.pages = []  # List of PIL Images
        self.page_bboxes = []  # List of (top_left, bottom_right) tuples for logos
        self.page_field_rects = []  # List of lists of field rectangles for each page
        self.page_field_data = []  # List of lists of (rect, field_type, field_name) for each page
        self.page_detected_rects = []  # List of lists of detected rectangles for each page
        self.current_page_idx = None  # Track currently displayed page
        
        # Initialize UI
        self.init_ui()
        
        # Load the TIFF file
        if self.tiff_path and os.path.exists(self.tiff_path):
            self.load_multipage_tiff(self.tiff_path)
        else:
            print(f"Warning: TIFF path not found or not set: {self.tiff_path}")
    
    def init_ui(self):
        """Initialize the user interface."""
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # Left panel: Thumbnail panel
        self.thumbnail_panel = DesignerThumbnailPanel()
        self.thumbnail_panel.thumbnail_clicked.connect(self.on_thumbnail_clicked)
        main_layout.addWidget(self.thumbnail_panel)
        
        # Right panel: Image display with controls
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.detect_button = QPushButton("Detect Rectangles")
        self.detect_button.clicked.connect(self.detect_rectangles)
        self.detect_button.setEnabled(False)
        button_layout.addWidget(self.detect_button)
        
        self.undo_button = QPushButton("Undo Last Field")
        self.undo_button.clicked.connect(self.undo_last_field)
        self.undo_button.setEnabled(False)
        button_layout.addWidget(self.undo_button)
        
        self.clear_button = QPushButton("Clear All Fields on Page")
        self.clear_button.clicked.connect(self.clear_current_page_fields)
        self.clear_button.setEnabled(False)
        button_layout.addWidget(self.clear_button)
        button_layout.addStretch()
        right_layout.addLayout(button_layout)
        
        # Image display
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #2b2b2b; }")
        
        self.image_display = ImageDisplayWidget(self.scroll_area)
        self.scroll_area.setWidget(self.image_display)
        right_layout.addWidget(self.scroll_area, stretch=1)
        
        main_layout.addWidget(right_panel, stretch=1)
    
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
        for idx in range(len(self.pages)):
            fields = load_page_fields(self.json_folder, idx)
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
                save_page_fields(self.json_folder, self.current_page_idx, self.page_field_data)
                self.update_thumbnail(self.current_page_idx)
                self.undo_button.setEnabled(True)
                logger.info(f"Page {self.current_page_idx + 1}: Added {field_obj.__class__.__name__} '{field_obj.name}' at ({field_obj.x}, {field_obj.y})")
            
            self.image_display.on_rect_added = on_rect_added_handler
            
            # Enable/disable buttons based on current state
            self.detect_button.setEnabled(True)
            self.clear_button.setEnabled(True)
            self.undo_button.setEnabled(len(field_rects) > 0)
    
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
                save_page_fields(self.json_folder, self.current_page_idx, self.page_field_data)
                
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
            save_page_fields(self.json_folder, self.current_page_idx, self.page_field_data)
            
            self.image_display.update_display()
            self.update_thumbnail(self.current_page_idx)
            self.undo_button.setEnabled(False)
            logger.info(f"Cleared all fields on page {self.current_page_idx + 1}")
    
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

