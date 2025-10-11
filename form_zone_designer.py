import sys
import os
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QLabel, QScrollArea
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor
from PIL import Image
from dotenv import load_dotenv
from orm_matcher import ORMMatcher
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ThumbnailWidget(QWidget):
    """Custom widget to display a thumbnail with bounding box overlay."""
    
    def __init__(self, pixmap, bbox=None, margin=10):
        super().__init__()
        self.pixmap = pixmap
        self.bbox = bbox  # (top_left, bottom_right) tuples
        self.margin = margin
        
        # Set fixed size to include margin
        total_width = pixmap.width() + 2 * margin
        total_height = pixmap.height() + 2 * margin
        self.setFixedSize(total_width, total_height)
    
    def paintEvent(self, event):
        """Paint the thumbnail with bounding box overlay."""
        painter = QPainter(self)
        
        # Fill background with light gray
        painter.fillRect(self.rect(), QColor(60, 60, 60))
        
        # Draw pixmap with margin offset
        painter.drawPixmap(self.margin, self.margin, self.pixmap)
        
        if self.bbox:
            top_left, bottom_right = self.bbox
            pen = QPen(QColor(0, 255, 0), 2)  # Green pen with 2px width
            painter.setPen(pen)
            # Adjust bounding box coordinates for margin offset
            painter.drawRect(top_left[0] + self.margin, top_left[1] + self.margin, 
                           bottom_right[0] - top_left[0], 
                           bottom_right[1] - top_left[1])
        
        painter.end()


class ImageDisplayWidget(QLabel):
    """Custom widget to display scaled image with bounding box overlay."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_pixmap = None
        self.bbox = None
        self.parent_scroll_area = parent
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("QLabel { background-color: #2b2b2b; }")
        self.setScaledContents(False)
    
    def set_image(self, pixmap, bbox=None):
        """Set the image and bounding box to display."""
        self.base_pixmap = pixmap
        self.bbox = bbox
        self.update_display()
    
    def update_display(self):
        """Redraw the image with bounding box overlay, scaled to fit."""
        if self.base_pixmap and self.parent_scroll_area:
            # Get available size from parent scroll area
            available_size = self.parent_scroll_area.viewport().size()
            
            # Scale the base pixmap to fit within available space while maintaining aspect ratio
            scaled_pixmap = self.base_pixmap.scaled(
                available_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            # Calculate scale factor for bounding box
            scale_x = scaled_pixmap.width() / self.base_pixmap.width()
            scale_y = scaled_pixmap.height() / self.base_pixmap.height()
            
            # Create a new pixmap with the bounding box drawn on it
            display_pixmap = QPixmap(scaled_pixmap.size())
            display_pixmap.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(display_pixmap)
            painter.drawPixmap(0, 0, scaled_pixmap)
            
            if self.bbox:
                top_left, bottom_right = self.bbox
                # Scale bounding box coordinates
                scaled_top_left = (int(top_left[0] * scale_x), int(top_left[1] * scale_y))
                scaled_bottom_right = (int(bottom_right[0] * scale_x), int(bottom_right[1] * scale_y))
                
                pen = QPen(QColor(0, 255, 0), 3)  # Green pen with 3px width
                painter.setPen(pen)
                painter.drawRect(scaled_top_left[0], scaled_top_left[1], 
                               scaled_bottom_right[0] - scaled_top_left[0], 
                               scaled_bottom_right[1] - scaled_top_left[1])
            
            painter.end()
            self.setPixmap(display_pixmap)
    
    def resizeEvent(self, event):
        """Handle resize events to rescale the image."""
        super().resizeEvent(event)
        if self.base_pixmap:
            self.update_display()


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
        
        # Initialize ORM matcher
        if self.logo_path and os.path.exists(self.logo_path):
            self.matcher = ORMMatcher(self.logo_path)
        else:
            self.matcher = None
            print(f"Warning: Logo path not found or not set: {self.logo_path}")
        
        # Storage for pages and their bounding boxes
        self.pages = []  # List of PIL Images
        self.page_bboxes = []  # List of (top_left, bottom_right) tuples
        
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
        
        # Left panel: Thumbnail list
        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setMaximumWidth(250)
        # Icon size includes margin (200 + 2*10 = 220)
        self.thumbnail_list.setIconSize(QSize(220, 220))
        self.thumbnail_list.itemClicked.connect(self.on_thumbnail_clicked)
        main_layout.addWidget(self.thumbnail_list)
        
        # Right panel: Image display
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #2b2b2b; }")
        
        self.image_display = ImageDisplayWidget(self.scroll_area)
        self.scroll_area.setWidget(self.image_display)
        main_layout.addWidget(self.scroll_area, stretch=1)
    
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
            
            print(f"Loaded {len(self.pages)} pages from {tiff_path}")
            
            # Process each page with ORM matcher
            self.process_pages()
            
            # Generate thumbnails and populate list
            self.generate_thumbnails()
            
        except Exception as e:
            print(f"Error loading TIFF: {e}")
    
    def process_pages(self):
        """Run ORM matcher on each page to find logo bounding boxes."""
        if not self.matcher:
            logger.warning("No matcher available, skipping logo detection")
            self.page_bboxes = [None] * len(self.pages)
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
    
    def generate_thumbnails(self):
        """Generate thumbnails for each page and add them to the list."""
        for idx, (page, bbox) in enumerate(zip(self.pages, self.page_bboxes)):
            # Create thumbnail
            thumbnail = page.copy()
            thumbnail.thumbnail((200, 200), Image.Resampling.LANCZOS)
            
            # Convert PIL Image to QPixmap
            thumbnail_array = np.array(thumbnail)
            height, width, channel = thumbnail_array.shape
            bytes_per_line = 3 * width
            q_image = QImage(thumbnail_array.data, width, height, 
                           bytes_per_line, QImage.Format.Format_RGB888)
            thumbnail_pixmap = QPixmap.fromImage(q_image)
            
            # Scale bounding box to thumbnail size if it exists
            scaled_bbox = None
            if bbox:
                scale_x = thumbnail.width / page.width
                scale_y = thumbnail.height / page.height
                top_left = (int(bbox[0][0] * scale_x), int(bbox[0][1] * scale_y))
                bottom_right = (int(bbox[1][0] * scale_x), int(bbox[1][1] * scale_y))
                scaled_bbox = (top_left, bottom_right)
            else:
                logger.warning(f"Page {idx + 1}: No bounding box found for page {idx + 1}")
            
            # Create custom thumbnail widget with overlay
            thumbnail_widget = ThumbnailWidget(thumbnail_pixmap, scaled_bbox)
            
            # Create list item
            item = QListWidgetItem(self.thumbnail_list)
            item.setText(f"Page {idx + 1}")
            # Use the actual widget size (including margins) for the item size hint
            item.setSizeHint(thumbnail_widget.size())
            item.setData(Qt.ItemDataRole.UserRole, idx)  # Store page index
            
            # Set the custom widget
            self.thumbnail_list.addItem(item)
            self.thumbnail_list.setItemWidget(item, thumbnail_widget)
    
    def on_thumbnail_clicked(self, item):
        """Handle thumbnail click event to display full-size page."""
        page_idx = item.data(Qt.ItemDataRole.UserRole)
        
        if 0 <= page_idx < len(self.pages):
            page = self.pages[page_idx]
            bbox = self.page_bboxes[page_idx]
            
            # Convert PIL Image to QPixmap
            page_array = np.array(page)
            height, width, channel = page_array.shape
            bytes_per_line = 3 * width
            q_image = QImage(page_array.data, width, height, 
                           bytes_per_line, QImage.Format.Format_RGB888)
            page_pixmap = QPixmap.fromImage(q_image)
            
            # Display with bounding box overlay
            self.image_display.set_image(page_pixmap, bbox)


def main():
    """Main entry point for the application."""
    app = QApplication(sys.argv)
    window = FormZoneDesigner()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

