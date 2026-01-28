from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QMouseEvent, QFont

from fields import Field, RadioGroup, RadioButton, Tickbox, TextField

TICK_CHAR = "\u2713"  # ✓
import logging

logger = logging.getLogger(__name__)

class MainImageIndexPanel(QLabel):
    """Custom QLabel for displaying form pages with field overlays."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_pixmap = None
        self.bbox = None  # Logo bounding box
        self.field_data = []  # List of Field objects
        self.field_values = {}  # Dictionary mapping field name to field value
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.image_offset_x = 0
        self.image_offset_y = 0
        
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("QLabel { background-color: #2b2b2b; }")
        self.setMinimumSize(400, 400)
        
        # Callback for field clicks
        self.on_field_click = None

    def _draw_tick_to_right(self, painter: QPainter, scaled_rect: QRect, color: QColor) -> None:
        """Draw a tickmark slightly to the right of the right edge of scaled_rect, using color."""
        offset = 4
        tick_w = max(12, scaled_rect.height())
        tick_rect = QRect(
            scaled_rect.right() + offset,
            scaled_rect.y(),
            tick_w,
            scaled_rect.height(),
        )
        painter.setPen(color)
        font = QFont()
        font.setPointSize(max(8, scaled_rect.height() - 2))
        painter.setFont(font)
        painter.drawText(tick_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, TICK_CHAR)

    def set_image(self, pixmap, bbox=None, field_data=None, field_values=None):
        """Set the image, bounding box, fields, and field values to display."""
        self.base_pixmap = pixmap
        self.bbox = bbox
        self.field_data = field_data or []
        self.field_values = field_values or {}
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
                selected_rb_name = self.field_values.get(field.name, None)
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
                    is_selected = (rb.name == selected_rb_name)
                    rb_pen = QPen(color, 3 if is_selected else 1)
                    painter.setPen(rb_pen)
                    painter.drawRect(rb_scaled_rect)
                    
                    # Fill if selected
                    if is_selected:
                        fill_color = QColor(*rb.colour) if rb.colour else QColor(150, 255, 0)
                        fill_color.setAlpha(100)
                        painter.fillRect(rb_scaled_rect, fill_color)
                        rb_tick_color = QColor(*rb.colour) if rb.colour else QColor(150, 255, 0)
                        self._draw_tick_to_right(painter, rb_scaled_rect, rb_tick_color)
            
            elif isinstance(field, (Tickbox, TextField)):
                color = QColor(*field.colour) if field.colour else QColor(0, 255, 0)
                
                # Get field value from dictionary
                field_value = self.field_values.get(field.name, False if isinstance(field, Tickbox) else "")
                
                # Use thicker border if tickbox is checked or textfield has text
                border_width = 1
                if isinstance(field, Tickbox) and field_value:
                    border_width = 3
                elif isinstance(field, TextField) and field_value:
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
                if isinstance(field, Tickbox) and field_value:
                    fill_color = QColor(*field.colour) if field.colour else QColor(0, 255, 0)
                    fill_color.setAlpha(100)
                    painter.fillRect(scaled_rect, fill_color)
                    self._draw_tick_to_right(painter, scaled_rect, color)
                
                # Fill and show text for TextField
                if isinstance(field, TextField) and field_value:
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
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft, field_value)
                    self._draw_tick_to_right(painter, scaled_rect, color)
        
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

