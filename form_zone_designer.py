import sys
import os
import json
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QLabel, QScrollArea, QPushButton,
    QDialog, QRadioButton, QButtonGroup, QLineEdit, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QSize, QPoint, QRect
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QMouseEvent
from PIL import Image
from dotenv import load_dotenv
from orm_matcher import ORMMatcher
from fields import Field, Tickbox, RadioButton, RadioGroup, TextField
from rectangle_detector import detect_rectangles_multi_method
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FieldConfigDialog(QDialog):
    """Dialog to configure field type and name after drawing a rectangle."""
    
    def __init__(self, parent=None, cursor_pos=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Field")
        self.setModal(True)
        
        # Position dialog near cursor if provided
        if cursor_pos:
            # Offset slightly so cursor doesn't cover the dialog
            self.move(cursor_pos.x() + 10, cursor_pos.y() + 10)
        
        # Main layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Radio buttons for field type
        type_label = QLabel("Field Type:")
        layout.addWidget(type_label)
        
        self.button_group = QButtonGroup(self)
        
        self.field_radio = QRadioButton("Field")
        self.tickbox_radio = QRadioButton("Tickbox")
        self.radiobutton_radio = QRadioButton("RadioButton")
        self.radiogroup_radio = QRadioButton("RadioGroup")
        self.textfield_radio = QRadioButton("TextField")
        
        # Set default selection
        self.field_radio.setChecked(True)
        
        # Add to button group and layout
        self.button_group.addButton(self.field_radio, 0)
        self.button_group.addButton(self.tickbox_radio, 1)
        self.button_group.addButton(self.radiobutton_radio, 2)
        self.button_group.addButton(self.radiogroup_radio, 3)
        self.button_group.addButton(self.textfield_radio, 4)
        
        layout.addWidget(self.field_radio)
        layout.addWidget(self.tickbox_radio)
        layout.addWidget(self.radiobutton_radio)
        layout.addWidget(self.radiogroup_radio)
        layout.addWidget(self.textfield_radio)
        
        # Text input for field name
        name_label = QLabel("Field Name:")
        layout.addWidget(name_label)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter field name...")
        layout.addWidget(self.name_input)
        
        # Dialog buttons (OK/Cancel)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Set focus to name input
        self.name_input.setFocus()
    
    def get_field_type(self):
        """Return the selected field type as a string."""
        button_id = self.button_group.checkedId()
        field_types = ["Field", "Tickbox", "RadioButton", "RadioGroup", "TextField"]
        if 0 <= button_id < len(field_types):
            return field_types[button_id]
        return "Field"
    
    def get_field_name(self):
        """Return the field name entered by the user."""
        return self.name_input.text().strip() or "Unnamed"


class ThumbnailWidget(QWidget):
    """Custom widget to display a thumbnail with bounding box overlay."""
    
    def __init__(self, pixmap, bbox=None, field_rects=None, field_data=None, margin=10):
        super().__init__()
        self.pixmap = pixmap
        self.bbox = bbox  # (top_left, bottom_right) tuples for logo
        self.field_rects = field_rects or []  # List of field rectangles (fallback)
        self.field_data = field_data or []  # List of Field objects
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
        
        # Draw field rectangles with colors from field data
        # Note: Field coordinates are already scaled and include logo offset for thumbnails
        if self.field_data:
            for field in self.field_data:
                if isinstance(field, Field):
                    color = QColor(*field.colour)
                    pen = QPen(color, 1)
                    painter.setPen(pen)
                    painter.drawRect(field.x + self.margin, field.y + self.margin,
                                   field.width, field.height)
                    
                    # If this is a RadioGroup, also draw its RadioButtons
                    if isinstance(field, RadioGroup):
                        for radio_button in field.radio_buttons:
                            rb_color = QColor(*radio_button.colour)
                            rb_pen = QPen(rb_color, 1)
                            painter.setPen(rb_pen)
                            painter.drawRect(radio_button.x + self.margin, radio_button.y + self.margin,
                                           radio_button.width, radio_button.height)
        elif self.field_rects:
            # Fallback to red if no field data available
            pen = QPen(QColor(255, 0, 0), 1)
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
        self.field_data = []  # List of (rect, field_type, field_name) tuples
        self.detected_rects = []  # List of detected rectangles (not yet converted to fields)
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
    
    def set_image(self, pixmap, bbox=None, field_rects=None, field_data=None, detected_rects=None):
        """Set the image, bounding box, and field rectangles to display."""
        self.base_pixmap = pixmap
        self.bbox = bbox
        self.field_rects = field_rects or []
        self.field_data = field_data or []
        self.detected_rects = detected_rects or []
        self.is_drawing = False
        self.start_point = None
        self.current_point = None
        self.update_display()
    
    def find_radio_buttons_in_group(self, radio_group):
        """Find all RadioButton fields within the RadioGroup's bounds and add them to the group."""
        if not isinstance(radio_group, RadioGroup):
            return
        
        radio_buttons_to_remove = []
        
        # Iterate through all fields to find RadioButtons within the group's bounds
        for i, field in enumerate(self.field_data):
            if isinstance(field, RadioButton):
                # Check if the RadioButton is within the RadioGroup's bounds
                # RadioButton center point
                rb_center_x = field.x + field.width // 2
                rb_center_y = field.y + field.height // 2
                
                # Check if center is within RadioGroup bounds
                if (radio_group.x <= rb_center_x <= radio_group.x + radio_group.width and
                    radio_group.y <= rb_center_y <= radio_group.y + radio_group.height):
                    radio_group.add_radio_button(field)
                    radio_buttons_to_remove.append(i)
                    logger.info(f"Added RadioButton '{field.name}' to RadioGroup '{radio_group.name}'")
        
        # Remove RadioButtons from the main field list (in reverse order to maintain indices)
        for i in reversed(radio_buttons_to_remove):
            self.field_data.pop(i)
            if i < len(self.field_rects):
                self.field_rects.pop(i)
    
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
            
            # Draw field rectangles with colors from field data
            if self.field_data:
                for field in self.field_data:
                    if isinstance(field, Field):
                        # Get color from field object
                        color = QColor(*field.colour)
                        pen = QPen(color, 1)  # 1px width as requested
                        painter.setPen(pen)
                        
                        # Field coordinates are relative to logo, convert to absolute image coordinates
                        abs_x = field.x
                        abs_y = field.y
                        if self.bbox:
                            logo_top_left = self.bbox[0]
                            abs_x += logo_top_left[0]
                            abs_y += logo_top_left[1]
                        
                        # Scale to display coordinates
                        scaled_rect = QRect(
                            int(abs_x * self.scale_x),
                            int(abs_y * self.scale_y),
                            int(field.width * self.scale_x),
                            int(field.height * self.scale_y)
                        )
                        painter.drawRect(scaled_rect)
                        
                        # If this is a RadioGroup, also draw its RadioButtons
                        if isinstance(field, RadioGroup):
                            for radio_button in field.radio_buttons:
                                rb_color = QColor(*radio_button.colour)
                                rb_pen = QPen(rb_color, 1)
                                painter.setPen(rb_pen)
                                
                                rb_abs_x = radio_button.x
                                rb_abs_y = radio_button.y
                                if self.bbox:
                                    rb_abs_x += logo_top_left[0]
                                    rb_abs_y += logo_top_left[1]
                                
                                rb_scaled_rect = QRect(
                                    int(rb_abs_x * self.scale_x),
                                    int(rb_abs_y * self.scale_y),
                                    int(radio_button.width * self.scale_x),
                                    int(radio_button.height * self.scale_y)
                                )
                                painter.drawRect(rb_scaled_rect)
            elif self.field_rects:
                # Fallback to red if no field data available
                pen = QPen(QColor(255, 0, 0), 1)
                painter.setPen(pen)
                for rect in self.field_rects:
                    if rect:
                        # Field coordinates are relative to logo, convert to absolute
                        abs_x = rect[0]
                        abs_y = rect[1]
                        if self.bbox:
                            logo_top_left = self.bbox[0]
                            abs_x += logo_top_left[0]
                            abs_y += logo_top_left[1]
                        
                        scaled_rect = QRect(
                            int(abs_x * self.scale_x),
                            int(abs_y * self.scale_y),
                            int(rect[2] * self.scale_x),
                            int(rect[3] * self.scale_y)
                        )
                        painter.drawRect(scaled_rect)
            
            # Draw detected rectangles (red)
            if self.detected_rects:
                pen = QPen(QColor(255, 0, 0), 2)  # Red pen with 2px width
                painter.setPen(pen)
                for rect in self.detected_rects:
                    if rect:
                        # Detected rectangles are in absolute image coordinates
                        abs_x = rect[0]
                        abs_y = rect[1]
                        
                        # Scale to display coordinates
                        scaled_rect = QRect(
                            int(abs_x * self.scale_x),
                            int(abs_y * self.scale_y),
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
        """Handle mouse press to start drawing a rectangle or right-click on detected rect."""
        if event.button() == Qt.MouseButton.RightButton and self.base_pixmap:
            # Check if right-clicked on a detected rectangle
            click_x = (event.pos().x() - self.image_offset_x) / self.scale_x
            click_y = (event.pos().y() - self.image_offset_y) / self.scale_y
            
            # Find the detected rectangle that was clicked
            for i, rect in enumerate(self.detected_rects):
                x, y, w, h = rect
                if x <= click_x <= x + w and y <= click_y <= y + h:
                    # Show dialog to configure field
                    dialog = FieldConfigDialog(self.window(), event.globalPosition().toPoint())
                    if dialog.exec() == QDialog.DialogCode.Accepted:
                        field_type = dialog.get_field_type()
                        field_name = dialog.get_field_name()
                        
                        # Make coordinates relative to fiducial/logo bounding box if available
                        rel_x = x
                        rel_y = y
                        if self.bbox:
                            logo_top_left = self.bbox[0]
                            rel_x = x - logo_top_left[0]
                            rel_y = y - logo_top_left[1]
                        
                        # Create appropriate Field object based on type
                        field_classes = {
                            'Field': Field,
                            'Tickbox': Tickbox,
                            'RadioButton': RadioButton,
                            'RadioGroup': RadioGroup,
                            'TextField': TextField
                        }
                        
                        field_class = field_classes.get(field_type, Field)
                        
                        # Create field object with default parameters
                        if field_type == 'RadioGroup':
                            field_obj = field_class(
                                name=field_name,
                                x=int(rel_x),
                                y=int(rel_y),
                                width=int(w),
                                height=int(h),
                                label=field_name,
                                value="",
                                radio_buttons=[],
                                colour=None
                            )
                        else:
                            field_obj = field_class(
                                name=field_name,
                                x=int(rel_x),
                                y=int(rel_y),
                                width=int(w),
                                height=int(h),
                                label=field_name,
                                value=False if field_type in ['Tickbox', 'RadioButton'] else "",
                                colour=None
                            )
                        
                        # Remove from detected rectangles and add to fields
                        self.detected_rects.pop(i)
                        new_rect = (int(rel_x), int(rel_y), int(w), int(h))
                        self.field_rects.append(new_rect)
                        self.field_data.append(field_obj)
                        logger.info(f"Converted detected rectangle to {field_type} field '{field_name}'")
                        
                        # If RadioGroup, find and add all RadioButtons within its bounds
                        if field_type == 'RadioGroup':
                            self.find_radio_buttons_in_group(field_obj)
                        
                        # Notify parent via callback
                        if self.on_rect_added:
                            self.on_rect_added(field_obj)
                        
                        self.update_display()
                    break
        elif event.button() == Qt.MouseButton.LeftButton and self.base_pixmap:
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
            
            # Make coordinates relative to fiducial/logo bounding box if available
            if self.bbox:
                logo_top_left = self.bbox[0]
                left = left - logo_top_left[0]
                top = top - logo_top_left[1]
            
            # Only add rectangle if it has some size
            if width > 5 and height > 5:
                new_rect = (int(left), int(top), int(width), int(height))
                
                # Show dialog to configure field
                dialog = FieldConfigDialog(self.window(), event.globalPosition().toPoint())
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    field_type = dialog.get_field_type()
                    field_name = dialog.get_field_name()
                    
                    # Create appropriate Field object based on type
                    field_classes = {
                        'Field': Field,
                        'Tickbox': Tickbox,
                        'RadioButton': RadioButton,
                        'RadioGroup': RadioGroup,
                        'TextField': TextField
                    }
                    
                    field_class = field_classes.get(field_type, Field)
                    
                    # Create field object with default parameters
                    if field_type == 'RadioGroup':
                        field_obj = field_class(
                            name=field_name,
                            x=int(left),
                            y=int(top),
                            width=int(width),
                            height=int(height),
                            label=field_name,
                            value="",
                            radio_buttons=[],
                            colour=None  # Will use default from __post_init__
                        )
                    else:
                        field_obj = field_class(
                            name=field_name,
                            x=int(left),
                            y=int(top),
                            width=int(width),
                            height=int(height),
                            label=field_name,
                            value=False if field_type in ['Tickbox', 'RadioButton'] else "",
                            colour=None  # Will use default from __post_init__
                        )
                    
                    # Add rectangle and field data
                    self.field_rects.append(new_rect)
                    self.field_data.append(field_obj)
                    logger.info(f"Added {field_type} field '{field_name}': {new_rect}")
                    
                    # If RadioGroup, find and add all RadioButtons within its bounds
                    if field_type == 'RadioGroup':
                        self.find_radio_buttons_in_group(field_obj)
                    
                    # Notify parent via callback
                    if self.on_rect_added:
                        self.on_rect_added(field_obj)
                else:
                    logger.info("Field creation cancelled")
            
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
    
    def save_page_fields_to_json(self, page_idx):
        """Save fields for a specific page to JSON file."""
        if 0 <= page_idx < len(self.page_field_data):
            json_path = os.path.join(self.json_folder, f"{page_idx + 1}.json")
            
            # Convert field data to Field objects and then to dict
            fields_data = []
            for field_obj in self.page_field_data[page_idx]:
                if isinstance(field_obj, Field):
                    fields_data.append(field_obj.to_dict())
            
            try:
                with open(json_path, 'w') as f:
                    json.dump(fields_data, f, indent=2)
                logger.info(f"Saved {len(fields_data)} fields to {json_path}")
            except Exception as e:
                logger.error(f"Error saving fields to {json_path}: {e}")
    
    def load_page_fields_from_json(self, page_idx):
        """Load fields for a specific page from JSON file."""
        json_path = os.path.join(self.json_folder, f"{page_idx + 1}.json")
        
        if not os.path.exists(json_path):
            logger.info(f"No JSON file found for page {page_idx + 1}")
            return []
        
        try:
            with open(json_path, 'r') as f:
                fields_data = json.load(f)
            
            # Convert JSON data to Field objects
            fields = []
            for field_dict in fields_data:
                field_obj = Field.from_dict(field_dict)
                fields.append(field_obj)
            
            logger.info(f"Loaded {len(fields)} fields from {json_path}")
            return fields
        except Exception as e:
            logger.error(f"Error loading fields from {json_path}: {e}")
            return []
    
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
            fields = self.load_page_fields_from_json(idx)
            self.page_field_data[idx] = fields
            # Update field_rects from loaded fields
            for field in fields:
                self.page_field_rects[idx].append((field.x, field.y, field.width, field.height))
    
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
            
            # Scale field data to thumbnail size
            scaled_field_data = []
            if idx < len(self.page_field_data):
                scale_x = thumbnail.width / page.width
                scale_y = thumbnail.height / page.height
                for field in self.page_field_data[idx]:
                    if isinstance(field, Field):
                        # Create a scaled copy of the field for thumbnail
                        # Field coordinates are relative to logo, convert to absolute first
                        abs_x = field.x
                        abs_y = field.y
                        if bbox:
                            abs_x += bbox[0][0]
                            abs_y += bbox[0][1]
                        
                        field_dict = field.to_dict()
                        field_dict['x'] = int(abs_x * scale_x)
                        field_dict['y'] = int(abs_y * scale_y)
                        field_dict['width'] = int(field.width * scale_x)
                        field_dict['height'] = int(field.height * scale_y)
                        scaled_field = Field.from_dict(field_dict)
                        scaled_field_data.append(scaled_field)
            
            # Create custom thumbnail widget with overlay
            thumbnail_widget = ThumbnailWidget(thumbnail_pixmap, scaled_bbox, [], scaled_field_data)
            
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
                self.save_page_fields_to_json(self.current_page_idx)
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
                self.save_page_fields_to_json(self.current_page_idx)
                
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
            self.save_page_fields_to_json(self.current_page_idx)
            
            self.image_display.update_display()
            self.update_thumbnail(self.current_page_idx)
            self.undo_button.setEnabled(False)
            logger.info(f"Cleared all fields on page {self.current_page_idx + 1}")
    
    def detect_rectangles(self):
        """Detect rectangles on the current page using computer vision."""
        if self.current_page_idx is None or not (0 <= self.current_page_idx < len(self.pages)):
            logger.warning("No page selected for rectangle detection")
            return
        
        page = self.pages[self.current_page_idx]
        
        # Convert PIL Image to OpenCV format
        page_array = np.array(page)
        page_cv = cv2.cvtColor(page_array, cv2.COLOR_RGB2BGR)
        
        # Run rectangle detection
        logger.info(f"Detecting rectangles on page {self.current_page_idx + 1}...")
        detected_rects = detect_rectangles_multi_method(page_cv, min_area=500, max_area=50000)
        
        # Store detected rectangles
        self.page_detected_rects[self.current_page_idx] = detected_rects
        self.image_display.detected_rects = detected_rects
        
        logger.info(f"Detected {len(detected_rects)} rectangles on page {self.current_page_idx + 1}")
        
        # Update display to show detected rectangles
        self.image_display.update_display()
        
        # Show info message
        if detected_rects:
            logger.info(f"Right-click on a detected rectangle (shown in red) to convert it to a field")
    
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
            
            # Scale field data to thumbnail size
            scaled_field_data = []
            if page_idx < len(self.page_field_data):
                scale_x = thumbnail.width / page.width
                scale_y = thumbnail.height / page.height
                for field in self.page_field_data[page_idx]:
                    if isinstance(field, Field):
                        # Create a scaled copy of the field for thumbnail
                        # Field coordinates are relative to logo, convert to absolute first
                        abs_x = field.x
                        abs_y = field.y
                        if bbox:
                            abs_x += bbox[0][0]
                            abs_y += bbox[0][1]
                        
                        field_dict = field.to_dict()
                        field_dict['x'] = int(abs_x * scale_x)
                        field_dict['y'] = int(abs_y * scale_y)
                        field_dict['width'] = int(field.width * scale_x)
                        field_dict['height'] = int(field.height * scale_y)
                        scaled_field = Field.from_dict(field_dict)
                        scaled_field_data.append(scaled_field)
            
            # Create custom thumbnail widget with overlay
            thumbnail_widget = ThumbnailWidget(thumbnail_pixmap, scaled_bbox, [], scaled_field_data)
            
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

