from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QMouseEvent

from PyQt6.QtWidgets import QDialog
from fields import Field, RadioGroup, RadioButton, Tickbox, TextField
import logging

logger = logging.getLogger(__name__)

class ImageDisplayWidget(QLabel):
    """Custom widget to display scaled image with bounding box overlay and field drawing."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_pixmap = None
        self.bbox = None
        self.field_list = []  # List of Field objects for current page
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
        
        # Zoom state
        # zoom_mode: 'autofit', 'fit_width', 'fit_height', or 'manual'
        self.zoom_mode = 'autofit'
        self.zoom_factor = 1.0
        
        # Callback for when a rectangle is added
        self.on_rect_added = None

        # Callback for when an existing field / rectangle is selected
        self.on_field_selected = None
    
    def set_image(self, pixmap, bbox=None, field_list=None, detected_rects=None):
        """Set the image, bounding box, and field list to display."""
        self.base_pixmap = pixmap
        self.bbox = bbox
        self.field_list = field_list or []
        self.detected_rects = detected_rects or []
        self.is_drawing = False
        self.start_point = None
        self.current_point = None
        # Reset zoom to autofit whenever a new image is set
        self.zoom_mode = 'autofit'
        self.zoom_factor = 1.0
        self.update_display()

    # ---- Zoom / fit API used by the main window ----

    def set_fit_width(self):
        """Zoom so that the image fits the scroll area's width."""
        if not self.base_pixmap:
            return
        self.zoom_mode = 'fit_width'
        self.update_display()

    def set_fit_height(self):
        """Zoom so that the image fits the scroll area's height."""
        if not self.base_pixmap:
            return
        self.zoom_mode = 'fit_height'
        self.update_display()

    def set_autofit(self):
        """Zoom so the whole image fits within the scroll area."""
        if not self.base_pixmap:
            return
        self.zoom_mode = 'autofit'
        self.update_display()

    def zoom_in(self, factor: float = 1.25):
        """Incrementally zoom in."""
        if not self.base_pixmap:
            return
        if self.zoom_mode != 'manual':
            # Start manual zoom from current visible scale
            self.zoom_factor = self.scale_x or 1.0
            self.zoom_mode = 'manual'
        self.zoom_factor *= factor
        # Clamp to a reasonable upper bound
        if self.zoom_factor > 10.0:
            self.zoom_factor = 10.0
        self.update_display()

    def zoom_out(self, factor: float = 1.25):
        """Incrementally zoom out."""
        if not self.base_pixmap:
            return
        if self.zoom_mode != 'manual':
            # Start manual zoom from current visible scale
            self.zoom_factor = self.scale_x or 1.0
            self.zoom_mode = 'manual'
        self.zoom_factor /= factor
        # Clamp to a reasonable lower bound
        if self.zoom_factor < 0.05:
            self.zoom_factor = 0.05
        self.update_display()
    
    def find_radio_buttons_in_group(self, radio_group):
        """Find all RadioButton fields within the RadioGroup's bounds and add them to the group."""
        if not isinstance(radio_group, RadioGroup):
            return
        
        radio_buttons_to_remove = []
        
        # Iterate through all fields to find RadioButtons within the group's bounds
        for i, field in enumerate(self.field_list):
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
            self.field_list.pop(i)
    
    def update_display(self):
        """Redraw the image with bounding box overlay, applying current zoom/fit mode."""
        if self.base_pixmap and self.parent_scroll_area:
            viewport_size = self.parent_scroll_area.viewport().size()
            base_width = self.base_pixmap.width()
            base_height = self.base_pixmap.height()

            if base_width == 0 or base_height == 0:
                return

            # Determine scale based on zoom mode
            if self.zoom_mode == 'fit_width':
                scale = viewport_size.width() / base_width
            elif self.zoom_mode == 'fit_height':
                scale = viewport_size.height() / base_height
            elif self.zoom_mode == 'manual':
                scale = self.zoom_factor
            else:  # 'autofit' (fit within both dimensions)
                scale_w = viewport_size.width() / base_width
                scale_h = viewport_size.height() / base_height
                scale = min(scale_w, scale_h)

            # Guard against degenerate scales
            if scale <= 0:
                scale = 0.01

            target_width = int(base_width * scale)
            target_height = int(base_height * scale)

            # Scale the base pixmap while maintaining aspect ratio
            scaled_pixmap = self.base_pixmap.scaled(
                target_width,
                target_height,
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
            
            # Draw field rectangles with colors from field list
            if self.field_list:
                for field in self.field_list:
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
                    # Make coordinates relative to fiducial/logo bounding box if available
                    rel_x = x
                    rel_y = y
                    if self.bbox:
                        logo_top_left = self.bbox[0]
                        rel_x = x - logo_top_left[0]
                        rel_y = y - logo_top_left[1]

                    # Create a default Field object; the side edit panel will refine its type/name

                    field_obj = Field(
                        colour=None,
                        name=None,
                        x=int(rel_x),
                        y=int(rel_y),
                        width=int(w),
                        height=int(h),
                    )

                    # Remove from detected rectangles and add to fields
                    self.detected_rects.pop(i)
                    self.field_list.append(field_obj)
                    logger.info(f"Converted detected rectangle to Field")

                    # Notify parent via callbacks
                    if self.on_rect_added:
                        self.on_rect_added(field_obj)
                    if self.on_field_selected:
                        self.on_field_selected(field_obj, event.globalPosition().toPoint())

                    self.update_display()
                    break
        elif event.button() == Qt.MouseButton.LeftButton and self.base_pixmap:
            # First, check if the user clicked on an existing field; if so, treat as selection
            click_x = (event.pos().x() - self.image_offset_x) / self.scale_x
            click_y = (event.pos().y() - self.image_offset_y) / self.scale_y

            # Try to find a Field under the cursor
            selected_field = None
            if self.field_list:
                for field in self.field_list:
                    if isinstance(field, Field):
                        abs_x = field.x
                        abs_y = field.y
                        if self.bbox:
                            logo_top_left = self.bbox[0]
                            abs_x += logo_top_left[0]
                            abs_y += logo_top_left[1]

                        if (
                            abs_x <= click_x <= abs_x + field.width
                            and abs_y <= click_y <= abs_y + field.height
                        ):
                            selected_field = field
                            break

            if selected_field is not None:
                logger.info(f"Selected field '{selected_field.name}'")
                if self.on_field_selected:
                    self.on_field_selected(selected_field, event.globalPosition().toPoint())
                return

            # Otherwise, start drawing a new rectangle
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
                # Create a default Field object; the side edit panel will refine its type/name
                field_name = "Field"
                field_obj = Field(
                    colour=None,
                    name=field_name,
                    x=int(left),
                    y=int(top),
                    width=int(width),
                    height=int(height),
                )

                # Add field to list
                self.field_list.append(field_obj)
                logger.info(f"Added Field '{field_name}' at ({int(left)}, {int(top)}, {int(width)}, {int(height)})")

                # Notify parent via callbacks
                if self.on_rect_added:
                    self.on_rect_added(field_obj)
                if self.on_field_selected:
                    self.on_field_selected(field_obj, event.globalPosition().toPoint())
            
            self.start_point = None
            self.current_point = None
            self.update_display()
    
    def resizeEvent(self, event):
        """Handle resize events to rescale the image."""
        super().resizeEvent(event)
        if self.base_pixmap:
            self.update_display()

