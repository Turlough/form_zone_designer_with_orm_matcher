from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QFont, QFontMetrics, QMouseEvent

from PyQt6.QtWidgets import QDialog
from fields import Field, RadioGroup, RadioButton, RadioGrid, Tickbox, TextField, NumericRadioGroup
from util.field_metadata import display_label
from util.radio_grid_layout import expand_fields_for_display
from util.field_geometry_edit import (
    geometry_edit_target,
    grid_division_lines,
    drag_vertical_division,
    drag_horizontal_division,
    resize_field_by_handle,
    resize_radio_group_by_handle,
    move_field,
    sync_radio_group_bounds,
    hit_resize_handle,
    field_logo_rect,
    logo_rect_from_abs,
    button_rects_snapshot,
    group_bounds_from_buttons,
    HANDLE_HIT_PX,
    LINE_HIT_PX,
)
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

        # Persistent selection rectangle in absolute image coordinates
        # (x, y, width, height). Used by tools such as OCR dialogs.
        self.selection_rect = None
        
        # Callback for when a rectangle is added (used after dialog submit for new field)
        self.on_rect_added = None

        # Callback for when an existing field / rectangle is selected (opens dialog)
        self.on_field_selected = None

        # Callback when user left-clicks a detected rect: on_detected_rect_clicked(rect_index, rect_xywh_abs, global_pos)
        self.on_detected_rect_clicked = None

        # Callback when user finishes drawing a rect: on_rect_drawn(drawn_rect_rel, inner_rects_rel, global_pos)
        # drawn_rect_rel / inner_rects_rel are (x,y,w,h) relative to logo
        self.on_rect_drawn = None

        # Callback when user clicks a RadioGrid: on_grid_selected(grid, global_pos)
        self.on_grid_selected = None

        # When True, drawing a rectangle invokes on_fiducial_rect_drawn (page coords) instead of field flow.
        self.fiducial_select_mode = False
        self.on_fiducial_rect_drawn = None  # (x, y, w, h) in absolute page pixels

        # When True, show first 20 chars of field name to the right of each field (set by main window from toggle)
        self.show_field_names = False

        # Field reshape edit mode (non-modal dialog open)
        self.edit_geometry_field: Field | None = None
        self.edit_parent_group: RadioGroup | None = None
        self._edit_drag: str | None = None  # 'handle', 'move', 'col', 'row'
        self._edit_handle: str | None = None
        self._edit_line_coord: int | None = None
        self._edit_start_bounds: tuple[int, int, int, int] | None = None
        self._edit_start_button_rects: list[tuple[int, int, int, int]] | None = None
        self._edit_last_pos: tuple[float, float] | None = None
        self.on_geometry_changed = None  # callback after live geometry edit
    
    def set_image(self, pixmap, bbox=None, field_list=None, detected_rects=None):
        """Set the image, bounding box, and field list to display."""
        self.base_pixmap = pixmap
        self.bbox = bbox
        self.field_list = field_list or []
        self.detected_rects = detected_rects or []
        self.is_drawing = False
        self.start_point = None
        self.current_point = None
        self.selection_rect = None
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
    
    def _draw_field_name_label(self, painter, text, scaled_rect, field_color):
        """Draw first 20 chars of field name to the right of the field with translucent white background."""
        if not text:
            return
        padding = 4
        font = QFont()
        font.setPointSize(12)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        text_rect = metrics.boundingRect(text)
        # Position slightly to the right of the field
        label_x = scaled_rect.right() + 4
        label_y = scaled_rect.y()
        bg_rect = QRect(
            label_x,
            label_y,
            text_rect.width() + padding * 2,
            text_rect.height() + padding * 2
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 150)))
        painter.drawRoundedRect(bg_rect, 2, 2)
        painter.setPen(QPen(field_color))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawText(bg_rect.adjusted(padding, padding, -padding, -padding), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)

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
            
            # Draw field rectangles with colors from field list (RadioGrids expand to groups)
            draw_fields = expand_fields_for_display(self.field_list)
            if draw_fields:
                for field in draw_fields:
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
                        label = display_label(field)
                        if self.show_field_names and label:
                            self._draw_field_name_label(painter, label, scaled_rect, color)
                        
                        # If this is a RadioGroup, also draw its RadioButtons
                        if isinstance(field, RadioGroup) or isinstance(field, NumericRadioGroup):
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
                                rb_label = display_label(radio_button)
                                if self.show_field_names and rb_label:
                                    self._draw_field_name_label(painter, rb_label, rb_scaled_rect, rb_color)

            # RadioGrid outer bounds (dashed) for design-time selection
            if self.field_list:
                for field in self.field_list:
                    if isinstance(field, RadioGrid):
                        logo_top_left = self.bbox[0] if self.bbox else (0, 0)
                        abs_x = field.x + logo_top_left[0]
                        abs_y = field.y + logo_top_left[1]
                        scaled_rect = QRect(
                            int(abs_x * self.scale_x),
                            int(abs_y * self.scale_y),
                            int(field.width * self.scale_x),
                            int(field.height * self.scale_y),
                        )
                        pen = QPen(QColor(180, 100, 255), 2)
                        pen.setStyle(Qt.PenStyle.DashLine)
                        painter.setPen(pen)
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
                pen.setDashPattern([1, 4])
                painter.setPen(pen)
                x1 = self.start_point.x() - self.image_offset_x
                y1 = self.start_point.y() - self.image_offset_y
                x2 = self.current_point.x() - self.image_offset_x
                y2 = self.current_point.y() - self.image_offset_y
                painter.drawRect(QRect(QPoint(x1, y1), QPoint(x2, y2)))

            # Draw persistent selection rectangle (also blue) if present
            if self.selection_rect:
                sx, sy, sw, sh = self.selection_rect
                pen = QPen(QColor(0, 150, 255), 3)
                painter.setPen(pen)
                scaled_rect = QRect(
                    int(sx * self.scale_x),
                    int(sy * self.scale_y),
                    int(sw * self.scale_x),
                    int(sh * self.scale_y),
                )
                painter.drawRect(scaled_rect)

            if self.edit_geometry_field is not None:
                self._draw_edit_overlay(painter)
            
            painter.end()
            self.setPixmap(display_pixmap)

    def _logo_top_left(self) -> tuple[int, int]:
        return self.bbox[0] if self.bbox else (0, 0)

    def _field_pixmap_rect(self, field: Field) -> QRect:
        """Field rect in coordinates of the displayed pixmap (before widget centering offset)."""
        logo_top_left = self._logo_top_left()
        abs_x = field.x + logo_top_left[0]
        abs_y = field.y + logo_top_left[1]
        return QRect(
            int(abs_x * self.scale_x),
            int(abs_y * self.scale_y),
            int(field.width * self.scale_x),
            int(field.height * self.scale_y),
        )

    def _field_widget_rect(self, field: Field) -> QRect:
        """Field rect in widget coordinates (matches QMouseEvent.pos())."""
        rect = self._field_pixmap_rect(field)
        rect.translate(self.image_offset_x, self.image_offset_y)
        return rect

    def _draw_edit_overlay(self, painter: QPainter):
        field = self.edit_geometry_field
        if field is None:
            return
        scaled_rect = self._field_pixmap_rect(field)
        pen = QPen(QColor(0, 200, 255), 2)
        painter.setPen(pen)
        painter.drawRect(scaled_rect)

        if isinstance(field, RadioGroup) and len(field.radio_buttons) >= 2:
            logo_top_left = self._logo_top_left()
            ox, oy = logo_top_left
            col_lines, row_lines = grid_division_lines(field)
            div_pen = QPen(QColor(200, 200, 100), 2)
            painter.setPen(div_pen)
            for lx in col_lines:
                xx = int((lx + ox) * self.scale_x)
                painter.drawLine(xx, scaled_rect.y(), xx, scaled_rect.y() + scaled_rect.height())
            for ly in row_lines:
                yy = int((ly + oy) * self.scale_y)
                painter.drawLine(scaled_rect.x(), yy, scaled_rect.x() + scaled_rect.width(), yy)

        handle_pen = QPen(QColor(255, 255, 255), 1)
        handle_brush = QBrush(QColor(0, 150, 255))
        painter.setPen(handle_pen)
        painter.setBrush(handle_brush)
        hs = 6
        for hx, hy in self._handle_points(scaled_rect).values():
            painter.drawRect(hx - hs, hy - hs, hs * 2, hs * 2)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    @staticmethod
    def _handle_points(rect: QRect) -> dict[str, tuple[int, int]]:
        cx = rect.x() + rect.width() // 2
        cy = rect.y() + rect.height() // 2
        return {
            "nw": (rect.x(), rect.y()),
            "n": (cx, rect.y()),
            "ne": (rect.x() + rect.width(), rect.y()),
            "e": (rect.x() + rect.width(), cy),
            "se": (rect.x() + rect.width(), rect.y() + rect.height()),
            "s": (cx, rect.y() + rect.height()),
            "sw": (rect.x(), rect.y() + rect.height()),
            "w": (rect.x(), cy),
        }

    def start_field_edit(self, field: Field, parent_group: RadioGroup | None = None):
        self.edit_geometry_field = geometry_edit_target(field, parent_group)
        self.edit_parent_group = parent_group
        self._clear_edit_drag()
        if isinstance(self.edit_geometry_field, RadioGroup):
            sync_radio_group_bounds(self.edit_geometry_field)
        self.update_display()

    def end_field_edit(self):
        if self.mouseGrabber() is self:
            self.releaseMouse()
        self.edit_geometry_field = None
        self.edit_parent_group = None
        self._clear_edit_drag()
        self.update_display()

    def _clear_edit_drag(self):
        self._edit_drag = None
        self._edit_handle = None
        self._edit_line_coord = None
        self._edit_start_bounds = None
        self._edit_start_button_rects = None
        self._edit_last_pos = None
        self.unsetCursor()

    def _notify_geometry_changed(self):
        if self.on_geometry_changed:
            self.on_geometry_changed()

    def _image_coords(self, pos: QPoint) -> tuple[float, float]:
        return (
            (pos.x() - self.image_offset_x) / self.scale_x,
            (pos.y() - self.image_offset_y) / self.scale_y,
        )

    def _try_start_edit_drag(self, pos: QPoint) -> bool:
        field = self.edit_geometry_field
        if field is None:
            return False
        widget_rect = self._field_widget_rect(field)
        px, py = pos.x(), pos.y()

        if isinstance(field, RadioGroup) and len(field.radio_buttons) >= 2:
            logo_top_left = self._logo_top_left()
            col_lines, row_lines = grid_division_lines(field)
            for lx in col_lines:
                disp_x = int((lx + logo_top_left[0]) * self.scale_x) + self.image_offset_x
                if (
                    widget_rect.x() <= px <= widget_rect.x() + widget_rect.width()
                    and widget_rect.y() <= py <= widget_rect.y() + widget_rect.height()
                    and abs(px - disp_x) <= LINE_HIT_PX
                ):
                    self._edit_drag = "col"
                    self._edit_line_coord = lx
                    self._edit_last_pos = self._image_coords(pos)
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                    return True
            for ly in row_lines:
                disp_y = int((ly + logo_top_left[1]) * self.scale_y) + self.image_offset_y
                if (
                    widget_rect.x() <= px <= widget_rect.x() + widget_rect.width()
                    and widget_rect.y() <= py <= widget_rect.y() + widget_rect.height()
                    and abs(py - disp_y) <= LINE_HIT_PX
                ):
                    self._edit_drag = "row"
                    self._edit_line_coord = ly
                    self._edit_last_pos = self._image_coords(pos)
                    self.setCursor(Qt.CursorShape.SizeVerCursor)
                    return True

        handle = hit_resize_handle(
            px, py,
            widget_rect.x(), widget_rect.y(),
            widget_rect.width(), widget_rect.height(),
            HANDLE_HIT_PX,
        )
        if handle:
            self._edit_drag = "handle"
            self._edit_handle = handle
            self._edit_last_pos = self._image_coords(pos)
            if isinstance(field, RadioGroup) and field.radio_buttons:
                self._edit_start_button_rects = button_rects_snapshot(field)
                self._edit_start_bounds = group_bounds_from_buttons(self._edit_start_button_rects)
            else:
                self._edit_start_button_rects = None
                self._edit_start_bounds = field_logo_rect(field)
            cursors = {
                "nw": Qt.CursorShape.SizeFDiagCursor,
                "se": Qt.CursorShape.SizeFDiagCursor,
                "ne": Qt.CursorShape.SizeBDiagCursor,
                "sw": Qt.CursorShape.SizeBDiagCursor,
                "n": Qt.CursorShape.SizeVerCursor,
                "s": Qt.CursorShape.SizeVerCursor,
                "e": Qt.CursorShape.SizeHorCursor,
                "w": Qt.CursorShape.SizeHorCursor,
            }
            self.setCursor(cursors.get(handle, Qt.CursorShape.ArrowCursor))
            return True

        if widget_rect.contains(px, py):
            self._edit_drag = "move"
            self._edit_last_pos = self._image_coords(pos)
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            return True
        return False

    def _apply_edit_drag(self, pos: QPoint):
        field = self.edit_geometry_field
        if field is None or self._edit_drag is None or self._edit_last_pos is None:
            return
        ix, iy = self._image_coords(pos)
        logo_top_left = self._logo_top_left()
        cur_x, cur_y = logo_rect_from_abs(ix, iy, logo_top_left)

        if self._edit_drag == "col" and isinstance(field, RadioGroup) and self._edit_line_coord is not None:
            if drag_vertical_division(field, self._edit_line_coord, cur_x):
                self._edit_line_coord = cur_x
                self._notify_geometry_changed()
                self.update_display()
            return
        if self._edit_drag == "row" and isinstance(field, RadioGroup) and self._edit_line_coord is not None:
            if drag_horizontal_division(field, self._edit_line_coord, cur_y):
                self._edit_line_coord = cur_y
                self._notify_geometry_changed()
                self.update_display()
            return
        if self._edit_drag == "handle" and self._edit_handle and self._edit_start_bounds:
            if isinstance(field, RadioGroup) and field.radio_buttons and self._edit_start_button_rects:
                resize_radio_group_by_handle(
                    field,
                    self._edit_handle,
                    self._edit_start_bounds,
                    self._edit_start_button_rects,
                    cur_x,
                    cur_y,
                )
            else:
                resize_field_by_handle(field, self._edit_handle, 0, 0, cur_x, cur_y)
            self._notify_geometry_changed()
            self.update_display()
            return
        if self._edit_drag == "move":
            last_ix, last_iy = self._edit_last_pos
            dx = int(ix - last_ix)
            dy = int(iy - last_iy)
            if dx or dy:
                move_field(field, dx, dy)
                self._edit_last_pos = (ix, iy)
                self._notify_geometry_changed()
                self.update_display()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press: left-click selects field/detected rect or starts drawing; right-click no longer converts."""
        if event.button() != Qt.MouseButton.LeftButton or not self.base_pixmap:
            return

        if self.edit_geometry_field is not None and self._try_start_edit_drag(event.pos()):
            self.grabMouse()
            return

        click_x = (event.pos().x() - self.image_offset_x) / self.scale_x
        click_y = (event.pos().y() - self.image_offset_y) / self.scale_y

        # RadioGrid selection (before individual fields)
        logo_top_left = self.bbox[0] if self.bbox else (0, 0)
        if self.field_list:
            for field in reversed(self.field_list):
                if isinstance(field, RadioGrid):
                    abs_x = field.x + logo_top_left[0]
                    abs_y = field.y + logo_top_left[1]
                    if (
                        abs_x <= click_x <= abs_x + field.width
                        and abs_y <= click_y <= abs_y + field.height
                    ):
                        logger.info(f"Selected RadioGrid '{field.name}'")
                        if self.on_grid_selected:
                            self.on_grid_selected(field, event.globalPosition().toPoint())
                        return

        # 1) Check if the user clicked on an existing field → selection (dialog opened by main window)
        if self.field_list:
            for field in self.field_list:
                if isinstance(field, Field):
                    abs_x = field.x
                    abs_y = field.y
                    if self.bbox:
                        abs_x += logo_top_left[0]
                        abs_y += logo_top_left[1]
                    if (
                        abs_x <= click_x <= abs_x + field.width
                        and abs_y <= click_y <= abs_y + field.height
                    ):
                        # RadioButton has priority over RadioGroup: if click is inside a RadioGroup,
                        # first check if it falls inside any of the group's RadioButtons.
                        if isinstance(field, RadioGroup) and field.radio_buttons:
                            for rb in field.radio_buttons:
                                rb_abs_x = rb.x + logo_top_left[0]
                                rb_abs_y = rb.y + logo_top_left[1]
                                if (
                                    rb_abs_x <= click_x <= rb_abs_x + rb.width
                                    and rb_abs_y <= click_y <= rb_abs_y + rb.height
                                ):
                                    logger.info(f"Selected RadioButton '{rb.name}' (inside RadioGroup)")
                                    if self.on_field_selected:
                                        self.on_field_selected(rb, event.globalPosition().toPoint())
                                    return
                        logger.info(f"Selected field '{field.name}'")
                        if self.on_field_selected:
                            self.on_field_selected(field, event.globalPosition().toPoint())
                        return

        # 2) Check if the user clicked on a detected rectangle → show dialog (no convert here)
        for i, rect in enumerate(self.detected_rects):
            x, y, w, h = rect
            if x <= click_x <= x + w and y <= click_y <= y + h:
                if self.on_detected_rect_clicked:
                    self.on_detected_rect_clicked(i, rect, event.globalPosition().toPoint())
                return

        # 3) Otherwise, start drawing a new rectangle
        if self.edit_geometry_field is not None:
            return
        self.is_drawing = True
        self.start_point = event.pos()
        self.current_point = event.pos()
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move to update the rectangle being drawn."""
        if self._edit_drag and self.base_pixmap:
            self._apply_edit_drag(event.pos())
            return
        if self.edit_geometry_field is not None and self.base_pixmap:
            widget_rect = self._field_widget_rect(self.edit_geometry_field)
            px, py = event.pos().x(), event.pos().y()
            if hit_resize_handle(
                px, py,
                widget_rect.x(), widget_rect.y(),
                widget_rect.width(), widget_rect.height(),
                HANDLE_HIT_PX,
            ):
                self.setCursor(Qt.CursorShape.CrossCursor)
            elif widget_rect.contains(px, py):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.unsetCursor()
        if self.is_drawing and self.base_pixmap:
            self.current_point = event.pos()
            self.update_display()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release: finish drawing and notify main window to show dialog (no add until submit)."""
        if event.button() == Qt.MouseButton.LeftButton and self._edit_drag:
            if self.mouseGrabber() is self:
                self.releaseMouse()
            self._clear_edit_drag()
            return
        if event.button() != Qt.MouseButton.LeftButton or not self.is_drawing or not self.base_pixmap:
            return

        self.is_drawing = False
        self.current_point = event.pos()

        x1 = (self.start_point.x() - self.image_offset_x) / self.scale_x
        y1 = (self.start_point.y() - self.image_offset_y) / self.scale_y
        x2 = (self.current_point.x() - self.image_offset_x) / self.scale_x
        y2 = (self.current_point.y() - self.image_offset_y) / self.scale_y

        left_abs = min(x1, x2)
        top_abs = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)

        logo_top_left = self.bbox[0] if self.bbox else (0, 0)
        left_rel = left_abs - logo_top_left[0]
        top_rel = top_abs - logo_top_left[1]
        drawn_rect_rel = (int(left_rel), int(top_rel), int(width), int(height))

        self.start_point = None
        self.current_point = None
        # Store persistent selection in absolute image coordinates
        if width > 5 and height > 5:
            self.selection_rect = (int(left_abs), int(top_abs), int(width), int(height))
        else:
            self.selection_rect = None

        self.update_display()

        if width <= 5 or height <= 5:
            return

        if self.fiducial_select_mode:
            if self.on_fiducial_rect_drawn:
                self.on_fiducial_rect_drawn(
                    (int(left_abs), int(top_abs), int(width), int(height))
                )
            return

        # Rectangles fully within the drawn rect (from detected_rects, in absolute coords)
        right_abs = left_abs + width
        bottom_abs = top_abs + height
        inner_rects_rel = []
        for rect in self.detected_rects:
            rx, ry, rw, rh = rect
            if (left_abs <= rx and top_abs <= ry and
                rx + rw <= right_abs and ry + rh <= bottom_abs):
                rel_x = rx - logo_top_left[0]
                rel_y = ry - logo_top_left[1]
                inner_rects_rel.append((int(rel_x), int(rel_y), int(rw), int(rh)))

        if self.on_rect_drawn:
            self.on_rect_drawn(drawn_rect_rel, inner_rects_rel, event.globalPosition().toPoint())

    # ------------------------------------------------------------------
    # Public helpers for tools (e.g. OCR dialog)
    # ------------------------------------------------------------------

    def get_selection_rect(self):
        """Return the current persistent selection rectangle, or None."""
        return self.selection_rect

    def clear_selection(self):
        """Clear the persistent selection rectangle and redraw."""
        self.selection_rect = None
        self.update_display()

    def set_selection_rect(self, rect):
        """Set the persistent selection rectangle from (x, y, w, h) in image coords and redraw."""
        self.selection_rect = tuple(rect) if rect else None
        self.update_display()

    def resizeEvent(self, event):
        """Handle resize events to rescale the image."""
        super().resizeEvent(event)
        if self.base_pixmap:
            self.update_display()

