import sys
import os
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QLabel, QScrollArea, QPushButton
)
from PyQt6.QtCore import Qt, QSize, QPoint, QRect
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QMouseEvent
from PIL import Image
from dotenv import load_dotenv
from orm_matcher import ORMMatcher
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ThumbnailWidget(QWidget):
    """Custom widget to display a thumbnail with bounding box overlay."""
    
    def __init__(self, pixmap, bbox=None, field_rects=None, margin=10):
        super().__init__()
        self.pixmap = pixmap
        self.bbox = bbox  # (top_left, bottom_right) tuples for logo
        self.field_rects = field_rects or []  # List of field rectangles
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
        
        # Draw logo bounding box (green)
        if self.bbox:
            top_left, bottom_right = self.bbox
            pen = QPen(QColor(0, 255, 0), 2)  # Green pen with 2px width
            painter.setPen(pen)
            # Adjust bounding box coordinates for margin offset
            painter.drawRect(top_left[0] + self.margin, top_left[1] + self.margin, 
                           bottom_right[0] - top_left[0], 
                           bottom_right[1] - top_left[1])
        
        # Draw field rectangles (red)
        if self.field_rects:
            pen = QPen(QColor(255, 0, 0), 1)  # Red pen with 1px width
            painter.setPen(pen)
            for rect in self.field_rects:
                if rect:
                    painter.drawRect(rect[0] + self.margin, rect[1] + self.margin,
                                   rect[2], rect[3])
        
        painter.end()


class ImageDisplayWidget(QLabel):
    """Custom widget to display scaled image with bounding box overlay and field drawing."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_pixmap = None
        self.bbox = None
        self.field_rects = []  # List of field rectangles for current page
        self.parent_scroll_area = parent
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("QLabel { background-color: #2b2b2b; }")
        self.setScaledContents(False)
        self.setMouseTracking(True)
        
        # Drawing state
        self.is_drawing = False
        self.start_point = None
        self.current_point = None
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.image_offset_x = 0
        self.image_offset_y = 0
        
        # Callback for when a rectangle is added
        self.on_rect_added = None
    
    def set_image(self, pixmap, bbox=None, field_rects=None):
        """Set the image, bounding box, and field rectangles to display."""
        self.base_pixmap = pixmap
        self.bbox = bbox
        self.field_rects = field_rects or []
        self.is_drawing = False
        self.start_point = None
        self.current_point = None
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
            self.scale_x = scaled_pixmap.width() / self.base_pixmap.width()
            self.scale_y = scaled_pixmap.height() / self.base_pixmap.height()
            
            # Calculate image offset (for centering)
            self.image_offset_x = (self.width() - scaled_pixmap.width()) // 2
            self.image_offset_y = (self.height() - scaled_pixmap.height()) // 2
            
            # Create a new pixmap with the bounding box drawn on it
            display_pixmap = QPixmap(scaled_pixmap.size())
            display_pixmap.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(display_pixmap)
            painter.drawPixmap(0, 0, scaled_pixmap)
            
            # Draw logo bounding box (green)
            if self.bbox:
                top_left, bottom_right = self.bbox
                # Scale bounding box coordinates
                scaled_top_left = (int(top_left[0] * self.scale_x), int(top_left[1] * self.scale_y))
                scaled_bottom_right = (int(bottom_right[0] * self.scale_x), int(bottom_right[1] * self.scale_y))
                
                pen = QPen(QColor(0, 255, 0), 1)  # Green pen with 1px width
                painter.setPen(pen)
                painter.drawRect(scaled_top_left[0], scaled_top_left[1], 
                               scaled_bottom_right[0] - scaled_top_left[0], 
                               scaled_bottom_right[1] - scaled_top_left[1])
            
            # Draw field rectangles (red)
            if self.field_rects:
                pen = QPen(QColor(255, 0, 0), 1)  # Red pen with 1px width
                painter.setPen(pen)
                for rect in self.field_rects:
                    if rect:
                        # rect is in original image coordinates: (x, y, width, height)
                        scaled_rect = QRect(
                            int(rect[0] * self.scale_x),
                            int(rect[1] * self.scale_y),
                            int(rect[2] * self.scale_x),
                            int(rect[3] * self.scale_y)
                        )
                        painter.drawRect(scaled_rect)
            
            # Draw current rectangle being drawn (blue)
            if self.is_drawing and self.start_point and self.current_point:
                pen = QPen(QColor(0, 150, 255), 3)  # Blue pen with 3px width
                painter.setPen(pen)
                x1 = self.start_point.x() - self.image_offset_x
                y1 = self.start_point.y() - self.image_offset_y
                x2 = self.current_point.x() - self.image_offset_x
                y2 = self.current_point.y() - self.image_offset_y
                painter.drawRect(QRect(QPoint(x1, y1), QPoint(x2, y2)))
            
            painter.end()
            self.setPixmap(display_pixmap)
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press to start drawing a rectangle."""
        if event.button() == Qt.MouseButton.LeftButton and self.base_pixmap:
            self.is_drawing = True
            self.start_point = event.pos()
            self.current_point = event.pos()
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move to update the rectangle being drawn."""
        if self.is_drawing and self.base_pixmap:
            self.current_point = event.pos()
            self.update_display()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release to complete drawing a rectangle."""
        if event.button() == Qt.MouseButton.LeftButton and self.is_drawing and self.base_pixmap:
            self.is_drawing = False
            self.current_point = event.pos()
            
            # Convert to original image coordinates
            x1 = (self.start_point.x() - self.image_offset_x) / self.scale_x
            y1 = (self.start_point.y() - self.image_offset_y) / self.scale_y
            x2 = (self.current_point.x() - self.image_offset_x) / self.scale_x
            y2 = (self.current_point.y() - self.image_offset_y) / self.scale_y
            
            # Normalize coordinates (ensure top-left and bottom-right)
            left = min(x1, x2)
            top = min(y1, y2)
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            
            # Only add rectangle if it has some size
            if width > 5 and height > 5:
                new_rect = (int(left), int(top), int(width), int(height))
                self.field_rects.append(new_rect)
                logger.info(f"Added field rectangle: {new_rect}")
                
                # Notify parent via callback
                if self.on_rect_added:
                    self.on_rect_added(new_rect)
            
            self.start_point = None
            self.current_point = None
            self.update_display()
    
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
        self.page_bboxes = []  # List of (top_left, bottom_right) tuples for logos
        self.page_field_rects = []  # List of lists of field rectangles for each page
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
        
        # Left panel: Thumbnail list
        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setMaximumWidth(250)
        # Icon size includes margin (200 + 2*10 = 220)
        self.thumbnail_list.setIconSize(QSize(220, 220))
        self.thumbnail_list.itemClicked.connect(self.on_thumbnail_clicked)
        main_layout.addWidget(self.thumbnail_list)
        
        # Right panel: Image display with controls
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Control buttons
        button_layout = QHBoxLayout()
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
            self.page_field_rects = [[] for _ in range(len(self.pages))]
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
            
            # Initialize empty field rectangles for this page
            self.page_field_rects.append([])
    
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
            
            # Scale field rectangles to thumbnail size
            scaled_field_rects = []
            if idx < len(self.page_field_rects):
                scale_x = thumbnail.width / page.width
                scale_y = thumbnail.height / page.height
                for rect in self.page_field_rects[idx]:
                    scaled_rect = (
                        int(rect[0] * scale_x),
                        int(rect[1] * scale_y),
                        int(rect[2] * scale_x),
                        int(rect[3] * scale_y)
                    )
                    scaled_field_rects.append(scaled_rect)
            
            # Create custom thumbnail widget with overlay
            thumbnail_widget = ThumbnailWidget(thumbnail_pixmap, scaled_bbox, scaled_field_rects)
            
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
            self.current_page_idx = page_idx
            page = self.pages[page_idx]
            bbox = self.page_bboxes[page_idx]
            field_rects = self.page_field_rects[page_idx]
            
            # Convert PIL Image to QPixmap
            page_array = np.array(page)
            height, width, channel = page_array.shape
            bytes_per_line = 3 * width
            q_image = QImage(page_array.data, width, height, 
                           bytes_per_line, QImage.Format.Format_RGB888)
            page_pixmap = QPixmap.fromImage(q_image)
            
            # Display with bounding box overlay and field rectangles
            self.image_display.set_image(page_pixmap, bbox, field_rects)
            
            # Set callback to update thumbnail when a rectangle is added
            def on_rect_added_handler(rect):
                self.update_thumbnail(self.current_page_idx)
                self.undo_button.setEnabled(True)
            
            self.image_display.on_rect_added = on_rect_added_handler
            
            # Enable/disable buttons based on current state
            self.clear_button.setEnabled(True)
            self.undo_button.setEnabled(len(field_rects) > 0)
    
    def undo_last_field(self):
        """Remove the last field rectangle drawn on the current page."""
        if self.current_page_idx is not None and 0 <= self.current_page_idx < len(self.page_field_rects):
            if self.page_field_rects[self.current_page_idx]:
                removed = self.page_field_rects[self.current_page_idx].pop()
                self.image_display.update_display()
                self.update_thumbnail(self.current_page_idx)
                logger.info(f"Removed last field rectangle on page {self.current_page_idx + 1}: {removed}")
                
                # Disable undo button if no more rectangles
                if not self.page_field_rects[self.current_page_idx]:
                    self.undo_button.setEnabled(False)
    
    def clear_current_page_fields(self):
        """Clear all field rectangles on the current page."""
        if self.current_page_idx is not None and 0 <= self.current_page_idx < len(self.page_field_rects):
            self.page_field_rects[self.current_page_idx].clear()
            self.image_display.field_rects.clear()
            self.image_display.update_display()
            self.update_thumbnail(self.current_page_idx)
            self.undo_button.setEnabled(False)
            logger.info(f"Cleared field rectangles on page {self.current_page_idx + 1}")
    
    def update_thumbnail(self, page_idx):
        """Update the thumbnail for a specific page to reflect current field rectangles."""
        if 0 <= page_idx < len(self.pages):
            page = self.pages[page_idx]
            bbox = self.page_bboxes[page_idx]
            
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
            
            # Scale field rectangles to thumbnail size
            scaled_field_rects = []
            if page_idx < len(self.page_field_rects):
                scale_x = thumbnail.width / page.width
                scale_y = thumbnail.height / page.height
                for rect in self.page_field_rects[page_idx]:
                    scaled_rect = (
                        int(rect[0] * scale_x),
                        int(rect[1] * scale_y),
                        int(rect[2] * scale_x),
                        int(rect[3] * scale_y)
                    )
                    scaled_field_rects.append(scaled_rect)
            
            # Create custom thumbnail widget with overlay
            thumbnail_widget = ThumbnailWidget(thumbnail_pixmap, scaled_bbox, scaled_field_rects)
            
            # Update the existing list item
            item = self.thumbnail_list.item(page_idx)
            if item:
                item.setSizeHint(thumbnail_widget.size())
                self.thumbnail_list.setItemWidget(item, thumbnail_widget)


def main():
    """Main entry point for the application."""
    app = QApplication(sys.argv)
    window = FormZoneDesigner()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

