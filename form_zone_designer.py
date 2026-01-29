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
    GridDesigner,
)
from fields import Field, Tickbox, RadioButton, RadioGroup, TextField
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
        self.fiducials = []  # List of (top_left, bottom_right) tuples for logos
        self.page_field_list = []  # List of lists of Field objects for each page
        self.page_detected_rects = []  # List of lists of detected rectangles for each page
        self.current_page_idx = None  # Track currently displayed page
        
        # Track currently selected field for config updates
        self.selected_field_obj = None  # The currently selected Field object
        self.selected_field_index = None  # Index of selected field in page_field_list
        
        # ORM matcher (initialized when config is loaded)
        self.matcher = None
        
        # Initialize UI
        self.init_ui()
        # Connect edit panel signals
        if hasattr(self, "edit_panel"):
            self.edit_panel.page_json_changed.connect(self.on_page_json_changed)
            self.edit_panel.field_config_changed.connect(self.on_field_config_changed)
    
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
            self.thumbnail_panel.populate_thumbnails(self.pages, self.fiducials, self.page_field_list)
            
        except Exception as e:
            print(f"Error loading TIFF: {e}")
    
    def process_pages(self):
        """Run ORM matcher on each page to find logo bounding boxes."""
        if not self.matcher:
            logger.warning("No matcher available, skipping logo detection")
            self.fiducials = [None] * len(self.pages)
            self.page_field_list = [[] for _ in range(len(self.pages))]
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
                self.fiducials.append((self.matcher.top_left, self.matcher.bottom_right))
                logger.info(f"Page {idx + 1}: Logo found at {self.matcher.top_left}")
            else:
                self.fiducials.append(None)
                logger.warning(f"Page {idx + 1}: No logo found")
            
            # Initialize empty field list for this page
            self.page_field_list.append([])
            self.page_detected_rects.append([])
        
        # Load fields from JSON for each page
        if self.config:
            for idx in range(len(self.pages)):
                fields = load_page_fields(str(self.config.json_folder), idx, self.config.config_folder)
                self.page_field_list[idx] = fields
    
    def on_thumbnail_clicked(self, page_idx):
        """Handle thumbnail click event to display full-size page."""
        
        if 0 <= page_idx < len(self.pages):
            # Clear selected field when changing pages
            self.selected_field_obj = None
            self.selected_field_index = None
            if self.edit_panel:
                self.edit_panel.set_field_from_object(None)
            
            self.current_page_idx = page_idx
            page = self.pages[page_idx]
            bbox = self.fiducials[page_idx]
            field_list = self.page_field_list[page_idx]
            detected_rects = self.page_detected_rects[page_idx]
            
            # Convert PIL Image to QPixmap
            page_array = np.array(page)
            height, width, channel = page_array.shape
            bytes_per_line = 3 * width
            q_image = QImage(page_array.data, width, height, 
                           bytes_per_line, QImage.Format.Format_RGB888)
            page_pixmap = QPixmap.fromImage(q_image)

            # Display with bounding box overlay and field list
            self.image_display.set_image(page_pixmap, bbox, field_list, detected_rects)
            
            # Set callback to update thumbnail when a rectangle is added
            def on_rect_added_handler(field_obj):
                self.page_field_list[self.current_page_idx].append(field_obj)
                self.update_thumbnail(self.current_page_idx)
                self.undo_button.setEnabled(True)
                logger.info(f"Page {self.current_page_idx + 1}: Added {field_obj.__class__.__name__} '{field_obj.name}' at ({field_obj.x}, {field_obj.y})")
            
            self.image_display.on_rect_added = on_rect_added_handler

            # Update JSON editor for the current page
            self._update_edit_panel_json(page_idx)
            
            # Enable/disable buttons based on current state
            self.detect_button.setEnabled(True)
            self.clear_button.setEnabled(True)
            self.undo_button.setEnabled(len(field_list) > 0)
            self.grid_designer_button.setEnabled(bbox is not None)

            # Enable zoom/fit controls now that an image is available
            self.fit_width_button.setEnabled(True)
            self.fit_height_button.setEnabled(True)
            self.autofit_button.setEnabled(True)
            self.zoom_in_button.setEnabled(True)
            self.zoom_out_button.setEnabled(True)

            # Update JSON editor for the current page
            self._update_edit_panel_json(page_idx)

    def open_grid_designer(self):
        """Open the Grid Designer window for the current page. Enabled only when page has a fiducial."""
        if self.current_page_idx is None or not (0 <= self.current_page_idx < len(self.pages)):
            return
        bbox = self.fiducials[self.current_page_idx] if self.current_page_idx < len(self.fiducials) else None
        if bbox is None:
            return
        page = self.pages[self.current_page_idx]
        page_array = np.array(page)
        h, w = page_array.shape[:2]
        bytes_per_line = 3 * w
        q_image = QImage(page_array.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        page_pixmap = QPixmap.fromImage(q_image)
        gd = GridDesigner(self)
        gd.set_page(page_pixmap, bbox)
        gd.groups_submitted.connect(self._on_grid_designer_submitted)
        gd.show()

    def _on_grid_designer_submitted(self, groups: list):
        """Append emitted radio groups to the current page, persist, and refresh UI."""
        if self.current_page_idx is None or not (0 <= self.current_page_idx < len(self.page_field_list)):
            return
        for g in groups:
            self.page_field_list[self.current_page_idx].append(g)
        if self.config:
            save_page_fields(
                str(self.config.json_folder),
                self.current_page_idx,
                self.page_field_list,
                self.config.config_folder,
            )
        self.image_display.field_list = self.page_field_list[self.current_page_idx]
        self.image_display.update_display()
        self.update_thumbnail(self.current_page_idx)
        self._update_edit_panel_json(self.current_page_idx)
        self.undo_button.setEnabled(True)
        logger.info(
            "Page %s: Added %d RadioGroup(s) from Grid Designer",
            self.current_page_idx + 1,
            len(groups),
        )

    def on_page_json_changed(self, field_order: list):
        """
        Handle field order changes from the field list table (drag/drop).
        
        Args:
            field_order: List of (field_name, field_type) tuples in the new order
        """
        if self.current_page_idx is None:
            return

        if not field_order:
            # Empty order - treat as no-op
            return

        page_idx = self.current_page_idx
        if page_idx < 0 or page_idx >= len(self.page_field_list):
            return

        # Get current fields for this page
        current_fields = self.page_field_list[page_idx]
        
        # Create lookup: (name, type) -> list of Field objects (handles duplicates)
        # We use a list because there could be multiple fields with same name+type
        field_lookup = {}
        for idx, field in enumerate(current_fields):
            if type(field) == Field:
                # Skip base Field instances
                continue
            field_type = field.__class__.__name__
            key = (field.name, field_type)
            if key not in field_lookup:
                field_lookup[key] = []
            field_lookup[key].append((idx, field))
        
        # Reorder fields based on the new order
        reordered_fields = []
        used_indices = set()
        
        # First pass: match fields by (name, type)
        for field_name, field_type in field_order:
            key = (field_name, field_type)
            if key in field_lookup and field_lookup[key]:
                # Get the first unused field with this name+type
                for idx, field in field_lookup[key]:
                    if idx not in used_indices:
                        reordered_fields.append(field)
                        used_indices.add(idx)
                        break
                else:
                    # All fields with this name+type are used, log warning
                    logger.warning(
                        f"Field '{field_name}' (type: {field_type}) in order list "
                        f"but all matching fields already used"
                    )
            else:
                # Field not found in current fields
                logger.warning(
                    f"Field '{field_name}' (type: {field_type}) in order list "
                    f"but not found in page_field_list"
                )
        
        # Second pass: add any remaining fields that weren't in the order list
        # (preserve them at the end)
        for idx, field in enumerate(current_fields):
            if idx not in used_indices and type(field) != Field:
                reordered_fields.append(field)
                logger.debug(
                    f"Preserving field '{field.name}' (type: {field.__class__.__name__}) "
                    f"that wasn't in order list"
                )

        # Update in-memory structures
        self.page_field_list[page_idx] = reordered_fields

        # Persist to disk
        if self.config:
            save_page_fields(str(self.config.json_folder), page_idx, self.page_field_list, self.config.config_folder)

        # Update UI (image display + thumbnail)
        self.image_display.field_list = reordered_fields
        self.image_display.update_display()
        self.update_thumbnail(page_idx)
        
        # Update JSON editor to reflect the reordered fields
        self._update_edit_panel_json(page_idx)

    def _update_edit_panel_json(self, page_idx: int):
        """Populate the edit panel JSON area with the current page's fields."""
        if not self.edit_panel:
            return

        if page_idx < 0 or page_idx >= len(self.page_field_list):
            self.edit_panel.set_page_json("")
            return

        fields_for_page = self.page_field_list[page_idx]

        # Convert field objects to serializable dicts using the same logic as save_page_fields
        fields_data = []
        for field_obj in fields_for_page:
            if isinstance(field_obj, Field):
                # Filter out base Field instances
                if type(field_obj) != Field:
                    fields_data.append(field_obj.to_dict())

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

        # Store reference to selected field and find its index
        self.selected_field_obj = field_obj
        self.selected_field_index = None
        
        # Find the field index in page_field_list
        if 0 <= self.current_page_idx < len(self.page_field_list):
            field_list = self.page_field_list[self.current_page_idx]
            for idx, field in enumerate(field_list):
                # Match by identity or by position/size (in case object was recreated)
                if field is field_obj or (
                    field.x == field_obj.x and
                    field.y == field_obj.y and
                    field.width == field_obj.width and
                    field.height == field_obj.height
                ):
                    self.selected_field_index = idx
                    break

        # Update the field controls to reflect this field
        self.edit_panel.set_field_from_object(field_obj)

        # Build a horizontal strip preview for the selected field.
        page = self.pages[self.current_page_idx]
        page_array = np.array(page)
        height, width, _ = page_array.shape

        # Field coordinates are relative to logo; convert to absolute image coords
        abs_x = field_obj.x
        abs_y = field_obj.y
        if self.fiducials[self.current_page_idx]:
            logo_top_left = self.fiducials[self.current_page_idx][0]
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

    def on_field_config_changed(self, config: dict):
        """
        Handle changes to field type or name from the edit panel.
        Updates the currently selected field with the new configuration.
        """
        if self.current_page_idx is None or self.selected_field_index is None:
            return
        
        if not (0 <= self.current_page_idx < len(self.page_field_list)):
            return
        
        if not (0 <= self.selected_field_index < len(self.page_field_list[self.current_page_idx])):
            return
        
        # Get the old field to preserve position, dimensions, and other properties
        old_field = self.page_field_list[self.current_page_idx][self.selected_field_index]
        
        # Extract new type and name from config
        field_type = config.get("field_type")
        field_name = config.get("field_name")
        
        # Create a new field of the correct type, preserving position and dimensions
        field_kwargs = {
            "colour": old_field.colour,
            "name": field_name,
            "x": old_field.x,
            "y": old_field.y,
            "width": old_field.width,
            "height": old_field.height,
        }
        
        # Create appropriate field type based on selection
        type_map = {
            "Tickbox": Tickbox,
            "RadioButton": RadioButton,
            "RadioGroup": RadioGroup,
            "TextField": TextField,
        }
        
        field_class = type_map.get(field_type)

        if not field_class:
            logger.error(f"Invalid field type: {field_type}")
            return
        
        # Set default value based on field type
        if field_class == RadioGroup:
            field_kwargs["radio_buttons"] = []

        
        # Create new field instance
        new_field = field_class(**field_kwargs)
        
        # If the new field is a RadioGroup, find and move RadioButtons within its bounds
        if isinstance(new_field, RadioGroup):
            page_fields = self.page_field_list[self.current_page_idx]
            radio_buttons_to_remove = []
            
            # Find all RadioButtons that lie within the RadioGroup's bounds
            for i, field in enumerate(page_fields):
                # Skip the field being converted (at selected_field_index)
                if i == self.selected_field_index:
                    continue
                
                if isinstance(field, RadioButton):
                    # Check if the RadioButton's center point is within the RadioGroup's bounds
                    rb_center_x = field.x + field.width // 2
                    rb_center_y = field.y + field.height // 2
                    
                    # Check if center is within RadioGroup bounds
                    if (new_field.x <= rb_center_x <= new_field.x + new_field.width and
                        new_field.y <= rb_center_y <= new_field.y + new_field.height):
                        # Add to RadioGroup
                        new_field.add_radio_button(field)
                        radio_buttons_to_remove.append(i)
                        logger.info(
                            f"Page {self.current_page_idx + 1}: Moved RadioButton '{field.name}' "
                            f"into RadioGroup '{new_field.name}'"
                        )
            
            # Remove RadioButtons from top-level list (in reverse order to maintain indices)
            # Also adjust selected_field_index if we remove items before it
            for i in reversed(radio_buttons_to_remove):
                page_fields.pop(i)
                # Adjust selected_field_index if we removed an item before it
                if i < self.selected_field_index:
                    self.selected_field_index -= 1
        
        # Replace the field in the data structure
        self.page_field_list[self.current_page_idx][self.selected_field_index] = new_field
        
        # Update stored reference
        self.selected_field_obj = new_field
        
        # Persist to disk
        if self.config:
            save_page_fields(
                str(self.config.json_folder),
                self.current_page_idx,
                self.page_field_list,
                self.config.config_folder
            )
        
        # Update image display
        if self.image_display:
            self.image_display.field_list = self.page_field_list[self.current_page_idx]
            self.image_display.update_display()
        
        # Update thumbnail
        self.update_thumbnail(self.current_page_idx)
        
        # Update JSON editor to reflect the change
        self._update_edit_panel_json(self.current_page_idx)
        
        logger.info(
            f"Page {self.current_page_idx + 1}: Updated field to {field_type} '{field_name}' "
            f"at ({new_field.x}, {new_field.y})"
        )

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
        if self.current_page_idx is not None and 0 <= self.current_page_idx < len(self.page_field_list):
            if self.page_field_list[self.current_page_idx]:
                removed_data = self.page_field_list[self.current_page_idx].pop()
                logger.info(f"Removed last field on page {self.current_page_idx + 1}: {removed_data}")
                
                # Update image display
                if self.image_display.field_list:
                    self.image_display.field_list.pop()
                
                # Save updated fields to JSON
                if self.config:
                    save_page_fields(str(self.config.json_folder), self.current_page_idx, self.page_field_list, self.config.config_folder)
                
                self.image_display.update_display()
                self.update_thumbnail(self.current_page_idx)
                
                # Clear selected field if it was the one removed
                if (self.selected_field_index is not None and 
                    self.selected_field_index >= len(self.page_field_list[self.current_page_idx])):
                    self.selected_field_obj = None
                    self.selected_field_index = None
                    if self.edit_panel:
                        self.edit_panel.set_field_from_object(None)
                
                # Disable undo button if no more fields
                if not self.page_field_list[self.current_page_idx]:
                    self.undo_button.setEnabled(False)
    
    def delete_current_rectangle(self):
        """Delete the currently selected field rectangle on the current page."""
        if self.current_page_idx is None or self.selected_field_index is None:
            return
        
        if not (0 <= self.current_page_idx < len(self.page_field_list)):
            return
        
        if not (0 <= self.selected_field_index < len(self.page_field_list[self.current_page_idx])):
            return
        
        # Remove the selected field from data structures
        removed_data = self.page_field_list[self.current_page_idx].pop(self.selected_field_index)
        
        logger.info(f"Removed field on page {self.current_page_idx + 1}: {removed_data}")
        
        # Update image display
        if (self.image_display.field_list and 
            self.selected_field_index < len(self.image_display.field_list)):
            self.image_display.field_list.pop(self.selected_field_index)
        
        # Save updated fields to JSON
        if self.config:
            save_page_fields(
                str(self.config.json_folder), 
                self.current_page_idx, 
                self.page_field_list, 
                self.config.config_folder
            )
        
        # Clear selected field since it was deleted
        self.selected_field_obj = None
        self.selected_field_index = None
        if self.edit_panel:
            self.edit_panel.set_field_from_object(None)
            self.edit_panel.set_preview_pixmap(None)
        
        # Update display and thumbnail
        self.image_display.update_display()
        self.update_thumbnail(self.current_page_idx)
        
        # Update JSON editor to reflect the change
        self._update_edit_panel_json(self.current_page_idx)
        
        # Disable undo button if no more fields
        if not self.page_field_list[self.current_page_idx]:
            self.undo_button.setEnabled(False)
    
    def clear_current_page_fields(self):
        """Clear all field rectangles on the current page."""
        if self.current_page_idx is not None and 0 <= self.current_page_idx < len(self.page_field_list):
            self.page_field_list[self.current_page_idx].clear()
            self.image_display.field_list.clear()
            
            # Save updated (empty) fields to JSON
            if self.config:
                save_page_fields(str(self.config.json_folder), self.current_page_idx, self.page_field_list, self.config.config_folder)
            
            self.image_display.update_display()
            self.update_thumbnail(self.current_page_idx)
            self.undo_button.setEnabled(False)
            
            # Clear selected field since all fields were removed
            self.selected_field_obj = None
            self.selected_field_index = None
            if self.edit_panel:
                self.edit_panel.set_field_from_object(None)
            
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
            bbox = self.fiducials[page_idx] if page_idx < len(self.fiducials) else None
            field_list = self.page_field_list[page_idx] if page_idx < len(self.page_field_list) else []
            self.thumbnail_panel.update_thumbnail(page_idx, page, bbox, field_list)


def main():
    """Main entry point for the application."""
    app = QApplication(sys.argv)
    window = FormZoneDesigner()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

