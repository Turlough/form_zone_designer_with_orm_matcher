from PyQt6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView
from PyQt6.QtGui import QPixmap, QImage
from PIL import Image
import numpy as np
import logging

from .designer_thumbnail_widget import DesignerThumbnailWidget, PAGE_NUM_WIDTH
from fields import Field

logger = logging.getLogger(__name__)

thumbnail_width = 100
thumbnail_height = 100
thumbnail_margin = 10

class DesignerThumbnailPanel(QWidget):
    """Panel to display thumbnails of pages."""
    
    # Signal emitted when a thumbnail is clicked
    thumbnail_clicked = pyqtSignal(int)  # Emits page_idx
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Thumbnail list widget (no selection - we use custom highlight for current page)
        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.thumbnail_list.setMaximumWidth(thumbnail_width + 2 * thumbnail_margin + PAGE_NUM_WIDTH)
        self.thumbnail_list.setIconSize(QSize(thumbnail_width, thumbnail_height))
        self.thumbnail_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.thumbnail_list)
        
        # Internal storage for thumbnail data (references, not copies)
        self._pages = []
        self._page_bboxes = []
        self._page_field_list = []
        self._current_page_idx = None
    
    def set_current_page(self, page_idx):
        """Set the current page, highlight it, and scroll so it is at the top.
        
        Args:
            page_idx: Index of the page to set as current
        """
        if page_idx is None or page_idx < 0:
            return
        old_idx = self._current_page_idx
        self._current_page_idx = page_idx
        
        # Update highlight on previous and current widgets
        if old_idx is not None and old_idx != page_idx:
            self._set_item_highlighted(old_idx, False)
        self._set_item_highlighted(page_idx, True)
        
        # Scroll so current page is at the top of the visible area
        item = self.thumbnail_list.item(page_idx)
        if item:
            self.thumbnail_list.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtTop)
    
    def _set_item_highlighted(self, page_idx, highlighted):
        """Set highlight state for a thumbnail widget."""
        item = self.thumbnail_list.item(page_idx)
        if item:
            widget = self.thumbnail_list.itemWidget(item)
            if isinstance(widget, DesignerThumbnailWidget):
                widget.set_highlighted(highlighted)
    
    def populate_thumbnails(self, pages, page_bboxes, page_field_list):
        """Populate the thumbnail list with pages.
        
        Args:
            pages: List of PIL Images
            page_bboxes: List of (top_left, bottom_right) tuples for logos
            page_field_list: List of lists of Field objects for each page
        """
        # Clear existing items
        self.thumbnail_list.clear()
        self._current_page_idx = None
        
        # Store references to data
        self._pages = pages
        self._page_bboxes = page_bboxes
        self._page_field_list = page_field_list
        
        # Generate and add thumbnails
        for idx, page in enumerate(pages):
            bbox = page_bboxes[idx] if idx < len(page_bboxes) else None
            field_list = page_field_list[idx] if idx < len(page_field_list) else []
            self._add_thumbnail(idx, page, bbox, field_list)
    
    def update_thumbnail(self, page_idx, page, bbox, field_list):
        """Update a specific thumbnail after fields change.
        
        Args:
            page_idx: Index of the page to update
            page: PIL Image for the page
            bbox: Bounding box tuple (top_left, bottom_right) for logo
            field_list: List of Field objects for this page
        """
        if 0 <= page_idx < len(self._pages):
            # Update stored references
            self._pages[page_idx] = page
            if page_idx < len(self._page_bboxes):
                self._page_bboxes[page_idx] = bbox
            if page_idx < len(self._page_field_list):
                self._page_field_list[page_idx] = field_list
            
            # Regenerate the thumbnail widget
            self._update_thumbnail_widget(page_idx, page, bbox, field_list)
    
    def _add_thumbnail(self, page_idx, page, bbox, field_list):
        """Internal method to create and add a single thumbnail.
        
        Args:
            page_idx: Index of the page
            page: PIL Image for the page
            bbox: Bounding box tuple (top_left, bottom_right) for logo
            field_list: List of Field objects for this page
        """
        # Create thumbnail
        thumbnail = page.copy()
        thumbnail.thumbnail((thumbnail_width, thumbnail_height), Image.Resampling.LANCZOS)
        
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
            logger.warning(f"Page {page_idx + 1}: No bounding box found for page {page_idx + 1}")
        
        # Scale field list to thumbnail size
        scaled_field_list = []
        scale_x = thumbnail.width / page.width
        scale_y = thumbnail.height / page.height
        for field in field_list:
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
                scaled_field_list.append(scaled_field)
        
        # Create custom thumbnail widget with overlay
        is_current = self._current_page_idx is not None and page_idx == self._current_page_idx
        thumbnail_widget = DesignerThumbnailWidget(
            thumbnail_pixmap, scaled_bbox, scaled_field_list,
            is_current=is_current, page_number=page_idx + 1
        )
        
        # Create list item
        item = QListWidgetItem(self.thumbnail_list)
        # Use the actual widget size (including margins) for the item size hint
        item.setSizeHint(thumbnail_widget.size())
        item.setData(Qt.ItemDataRole.UserRole, page_idx)  # Store page index
        
        # Set the custom widget
        self.thumbnail_list.addItem(item)
        self.thumbnail_list.setItemWidget(item, thumbnail_widget)
    
    def _update_thumbnail_widget(self, page_idx, page, bbox, field_list):
        """Internal method to regenerate and update a thumbnail widget.
        
        Args:
            page_idx: Index of the page to update
            page: PIL Image for the page
            bbox: Bounding box tuple (top_left, bottom_right) for logo
            field_list: List of Field objects for this page
        """
        # Create thumbnail
        thumbnail = page.copy()
        thumbnail.thumbnail((thumbnail_width, thumbnail_height), Image.Resampling.LANCZOS)
        
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
        
        # Scale field list to thumbnail size
        scaled_field_list = []
        scale_x = thumbnail.width / page.width
        scale_y = thumbnail.height / page.height
        for field in field_list:
            if isinstance(field, Field):
                # Filter out base Field instances
                if type(field) == Field:
                    continue
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
                scaled_field_list.append(scaled_field)
        
        # Create custom thumbnail widget with overlay
        is_current = self._current_page_idx is not None and page_idx == self._current_page_idx
        thumbnail_widget = DesignerThumbnailWidget(
            thumbnail_pixmap, scaled_bbox, scaled_field_list,
            is_current=is_current, page_number=page_idx + 1
        )
        
        # Update the existing list item
        item = self.thumbnail_list.item(page_idx)
        if item:
            item.setSizeHint(thumbnail_widget.size())
            self.thumbnail_list.setItemWidget(item, thumbnail_widget)
    
    def _on_item_clicked(self, item):
        """Internal handler that emits the thumbnail_clicked signal."""
        page_idx = item.data(Qt.ItemDataRole.UserRole)
        if page_idx is not None:
            self.thumbnail_clicked.emit(page_idx)
