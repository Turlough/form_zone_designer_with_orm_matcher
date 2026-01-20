from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen
from fields import Field, RadioGroup

class DesignerThumbnailWidget(QWidget):
    """Custom widget to display a thumbnail with bounding box overlay."""
    
    def __init__(self, pixmap, bbox=None, field_list=None, margin=10):
        super().__init__()
        self.pixmap = pixmap
        self.bbox = bbox  # (top_left, bottom_right) tuples for logo
        self.field_list = field_list or []  # List of Field objects
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
        
        # Draw field rectangles with colors from field list
        # Note: Field coordinates are already scaled and include logo offset for thumbnails
        if self.field_list:
            for field in self.field_list:
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
        
        painter.end()
