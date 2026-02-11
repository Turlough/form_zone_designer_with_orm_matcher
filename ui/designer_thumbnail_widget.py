from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from fields import Field, RadioGroup

# Space for page number to the right of thumbnail
PAGE_NUM_WIDTH = 28

class DesignerThumbnailWidget(QWidget):
    """Custom widget to display a thumbnail with bounding box overlay."""
    
    def __init__(self, pixmap, bbox=None, field_list=None, margin=10, is_current=False, page_number=1):
        super().__init__()
        self.pixmap = pixmap
        self.bbox = bbox  # (top_left, bottom_right) tuples for logo
        self.field_list = field_list or []  # List of Field objects
        self.margin = margin
        self.is_current = is_current
        self.page_number = page_number
        
        # Set fixed size: thumbnail + margins + page number on right
        thumb_width = pixmap.width() + 2 * margin
        total_width = thumb_width + PAGE_NUM_WIDTH
        total_height = pixmap.height() + 2 * margin
        self.setFixedSize(total_width, total_height)
    
    def set_highlighted(self, highlighted: bool):
        """Set whether this thumbnail is highlighted as the current page."""
        if self.is_current != highlighted:
            self.is_current = highlighted
            self.update()
    
    def paintEvent(self, event):
        """Paint the thumbnail with bounding box overlay."""
        painter = QPainter(self)
        
        # Fill background; use brighter color when current page
        if self.is_current:
            painter.fillRect(self.rect(), QColor(80, 80, 100))
            # Draw highlight border
            pen = QPen(QColor(100, 150, 255), 3)
            painter.setPen(pen)
            painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
        else:
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
        
        # Draw page number to the right of thumbnail
        thumb_width = self.pixmap.width() + 2 * self.margin
        num_rect = self.rect()
        num_rect.setLeft(thumb_width)
        painter.setPen(QColor(200, 200, 200))
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(num_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, str(self.page_number))
        
        painter.end()
