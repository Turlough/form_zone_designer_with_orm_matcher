import logging

from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QMouseEvent, QFont, QFontMetrics

from fields import Field, RadioGroup, Tickbox, TextField, IntegerField, DecimalField
from field_factory import FIELD_TYPE_MAP as FACTORY_FIELD_TYPE_MAP, get_field_display_color, INVALID_COLOUR
from util.field_group_align import placed_rect
from .index_details_panel import _format_number_for_display


TICK_CHAR = "\u2713"  # ✓
CROSS_CHAR = "\u2717"  # ✗
# Extra centre-pane width so Show Value overlays beside edge fields stay visible.
PAGE_FIT_RIGHT_PADDING_RATIO = 0.10

logger = logging.getLogger(__name__)


def page_fit_panel_width(
    page_width: int,
    page_height: int,
    available_height: int,
    available_width: int,
    min_trailing_width: int,
) -> int:
    """Width of the centre page pane so the page fits without upscaling.

    Matches MainImageIndexPanel scaling: scale = min(width_ratio, height_ratio, 1.0).
    Adds PAGE_FIT_RIGHT_PADDING_RATIO of the fitted page width on the right so
    field-value overlays are not clipped. min_trailing_width is reserved for
    the detail panel so a large page cannot consume the whole row.
    """
    if page_width <= 0 or page_height <= 0 or available_height <= 0:
        return 0
    scale = min(1.0, available_height / float(page_height))
    fitted = page_width * scale
    needed = int(round(fitted * (1.0 + PAGE_FIT_RIGHT_PADDING_RATIO)))
    max_center = max(0, available_width - max(0, min_trailing_width))
    return max(0, min(needed, max_center))


class MainImageIndexPanel(QLabel):
    """Custom QLabel for displaying form pages with field overlays."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_pixmap = None
        self.bbox = None  # Logo bounding box
        self.field_data = []  # List of Field objects
        self.field_values = {}  # Dictionary mapping field name to field value
        # Dictionary mapping field name to QC comment (if any) for the current page
        self.field_comments = {}
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.image_offset_x = 0
        self.image_offset_y = 0
        # Prepared-canvas origin of the displayed crop (print_crop x, y). Overlays
        # and clicks stay in canvas/fiducial space; display subtracts this origin.
        self.canvas_origin = (0, 0)
        # Page-visit group move/scale (Page → Drag fields). None keeps logo placement.
        self.field_align = None
        
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet("QLabel { background-color: #2b2b2b; }")
        self.setMinimumSize(400, 400)
        # Clicks select fields; keyboard focus belongs in the close-up value box.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Whether to show field values to the right of each field (controlled by Show Value toggle)
        self.show_field_values = True

        # Callback for field clicks
        self.on_field_click = None

    def _canvas_rect_on_widget(self, abs_x: float, abs_y: float, width: float, height: float) -> QRect:
        """Map a prepared-canvas rect onto the displayed (possibly cropped) pixmap."""
        ox, oy = self.canvas_origin
        return QRect(
            self.image_offset_x + int((abs_x - ox) * self.scale_x),
            self.image_offset_y + int((abs_y - oy) * self.scale_y),
            int(width * self.scale_x),
            int(height * self.scale_y),
        )

    def _placed(self, x: float, y: float, w: float, h: float):
        """Canvas rect after logo offset and any page-visit group align."""
        logo = self.bbox[0] if self.bbox else (0, 0)
        return placed_rect(x, y, w, h, logo, self.field_align)

    def _get_field_color(self, field: Field) -> QColor:
        return get_field_display_color(field)

    def _get_validator_for_field(self, field: Field):
        """
        Look up the appropriate Validator instance for a given field, based on
        FIELD_TYPE_MAP from field_factory.
        """
        for field_class, _color, validator in FACTORY_FIELD_TYPE_MAP.values():
            if type(field) is field_class:
                # Map may store either a Validator class or an instance
                try:
                    if isinstance(validator, type):
                        return validator()
                    return validator
                except Exception:
                    logger.exception("Error creating validator for field %s", getattr(field, "name", ""))
                    return None
        return None

    def _get_value_for_validation(self, field: Field):
        """
        Normalise the current value for validation, per field type.
        """
        # Tickbox: treat checked/unchecked as a non-empty/empty string so that
        # TextValidator (is_empty) semantics work as expected.
        if isinstance(field, Tickbox):
            checked = bool(self.field_values.get(field.name, False))
            return field.checked_value if checked else ""

        # RadioGroup (and subclasses): value is the selected radio button name.
        if isinstance(field, RadioGroup):
            value = self.field_values.get(field.name, "")
            return value or ""

        # Text-like fields (TextField, IntegerField, DecimalField, etc.)
        value = self.field_values.get(field.name, "")
        if value is None:
            return ""
        return str(value)

    def _is_field_invalid(self, field: Field) -> bool:
        """
        Determine whether the current value for this field fails validation.

        If no validator is configured for a field type, it is treated as valid.
        """
        validator = self._get_validator_for_field(field)
        if validator is None:
            return False

        value = self._get_value_for_validation(field)
        try:
            return not validator.is_valid(value)
        except Exception:
            logger.error("Validation error for field %s", getattr(field, "name", ""))
            return False

    def _draw_tick_to_right(self, painter: QPainter, scaled_rect: QRect, color: QColor, character: str) -> None:
        """Draw a tickmark slightly to the right of the right edge of scaled_rect, using color."""
        offset = 4
        tick_w = 16
        tick_rect = QRect(
            scaled_rect.right() + offset,
            scaled_rect.y(),
            tick_w,
            tick_w,
        )
        painter.setPen(color)
        font = QFont()
        font.setPointSize(16)
        painter.setFont(font)
        painter.drawText(tick_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, character)

    def _draw_tick_to_left(self, painter: QPainter, scaled_rect: QRect, color: QColor, character: str) -> None:
        """Draw a tickmark slightly to the left of the left edge of scaled_rect, using color."""
        offset = 4
        tick_w = 16
        tick_rect = QRect(
            scaled_rect.left() - offset - tick_w,
            scaled_rect.y(),
            tick_w,
            tick_w,
        )
        painter.setPen(color)
        font = QFont()
        font.setPointSize(16)
        painter.setFont(font)
        painter.drawText(tick_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, character)

    def _draw_value_to_right(
        self,
        painter: QPainter,
        scaled_rect: QRect,
        base_color: QColor,
        value_str: str,
        is_invalid: bool,
        min_x: int | None = None,
    ) -> None:
        """
        Draw field value to the right of the field rect.
        Black text on 70% opaque white background.
        Truncates to 30 characters.
        If min_x is provided, the value is placed at least at min_x (avoids overlap with
        other fields in the same horizontal band).
        """
        if not value_str:
            return
        display_text = (value_str[:30] + "…") if len(value_str) > 30 else value_str
        offset = 8
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text_w = metrics.horizontalAdvance(display_text)
        text_h = metrics.height()
        pad_h = 8
        pad_v = 4
        value_w = text_w + pad_h * 2
        value_h = text_h + pad_v * 2
        left = scaled_rect.right() + offset
        if min_x is not None and left < min_x:
            left = min_x
        value_rect = QRect(left, scaled_rect.y(), value_w, value_h)
        bg_color = QColor(255, 255, 255)
        bg_color.setAlpha(int(255 * 0.8))
        painter.fillRect(value_rect, bg_color)
        bg_color.setAlpha(int(255))
        painter.drawRect(value_rect)
        painter.setPen(QColor(100, 100, 100))
        painter.drawText(
            value_rect.adjusted(pad_h, pad_v, -pad_h, -pad_v),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            display_text,
        )

    def _compute_value_placements(self) -> dict:
        """
        Compute min_x for each field that will show a value, so values in the same
        horizontal band (overlapping y range) don't overlap. Values start at the
        right edge of the rightmost field in the band (all fields, not just those
        with values). Fields with values in a band are ordered left-to-right;
        the first value starts there, subsequent values are placed 1px after the
        previous value.
        Returns dict mapping field name -> min_x (widget coords).
        """
        if not self.show_field_values:
            return {}
        VALUE_OFFSET = 8
        BAND_MARGIN = 1
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        metrics = QFontMetrics(font)
        pad_h = 8

        def vertical_overlap(y1: int, h1: int, y2: int, h2: int) -> bool:
            return y1 < y2 + h2 and y2 < y1 + h1

        # Build bands from ALL fields (overlapping y ranges)
        all_entries: list[tuple] = []
        for field in self.field_data:
            abs_x, abs_y, abs_w, abs_h = self._placed(
                field.x, field.y, field.width, field.height
            )
            scaled_rect = self._canvas_rect_on_widget(abs_x, abs_y, abs_w, abs_h)
            all_entries.append((field, abs_x, abs_y, abs_h, scaled_rect))

        bands: list[list[tuple]] = []
        for entry in all_entries:
            field, ax, ay, ah, srect = entry
            placed = False
            for band in bands:
                for _, bx, by, bh, *_ in band:
                    if vertical_overlap(ay, ah, by, bh):
                        band.append(entry)
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                bands.append([entry])

        # Collect (field, abs_x, abs_y, abs_h, scaled_rect, value_w, band_idx) for fields that show values
        value_entries: list[tuple] = []
        for band_idx, band in enumerate(bands):
            for field, ax, ay, ah, srect in band:
                value_str = None
                if isinstance(field, RadioGroup):
                    selected = self.field_values.get(field.name, None)
                    if selected:
                        value_str = selected
                elif isinstance(field, TextField):
                    val = self.field_values.get(field.name, "")
                    if val:
                        value_str = str(val)
                        if isinstance(field, (IntegerField, DecimalField)):
                            value_str = _format_number_for_display(value_str)
                if value_str is None:
                    continue
                display_text = (value_str[:30] + "…") if len(value_str) > 30 else value_str
                text_w = metrics.horizontalAdvance(display_text)
                value_w = text_w + pad_h * 2
                value_entries.append((field, ax, ay, ah, srect, value_w, band_idx))

        # For each band: rightmost_right = max over ALL fields; sort value fields by x, compute min_x
        result: dict[str, int] = {}
        for band_idx, band in enumerate(bands):
            rightmost_right = max(srect.right() for (_, _, _, _, srect) in band)
            band_value_entries = [(e[0], e[1], e[2], e[3], e[4], e[5]) for e in value_entries if e[6] == band_idx]
            band_value_entries.sort(key=lambda e: e[1])  # by abs_x
            running_x = rightmost_right + VALUE_OFFSET
            for field, _ax, _ay, _ah, srect, value_w in band_value_entries:
                min_x = max(srect.right() + VALUE_OFFSET, running_x)
                result[field.name] = min_x
                running_x = min_x + value_w + BAND_MARGIN
        return result

    def set_image(
        self,
        pixmap,
        bbox=None,
        field_data=None,
        field_values=None,
        field_comments=None,
        canvas_origin=(0, 0),
        field_align=None,
    ):
        """Set the image, bounding box, fields, and field values/comments to display.

        canvas_origin is the top-left of the displayed crop in prepared-canvas
        pixels (print_crop x, y). Use (0, 0) when the full canvas is shown.
        field_align is the page-visit group move/scale, or None.
        """
        self.base_pixmap = pixmap
        self.bbox = bbox
        self.field_data = field_data or []
        self.field_values = field_values or {}
        self.field_comments = field_comments or {}
        self.field_align = field_align
        self.canvas_origin = canvas_origin if canvas_origin is not None else (0, 0)
        if pixmap is None:
            self.canvas_origin = (0, 0)
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
        
        # Left-align so extra page-fit width stays on the right for value overlays.
        self.image_offset_x = 0
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
            scaled_rect = self._canvas_rect_on_widget(
                top_left[0],
                top_left[1],
                bottom_right[0] - top_left[0],
                bottom_right[1] - top_left[1],
            )
            painter.drawRect(scaled_rect)
        
        # Draw fields
        value_placements = self._compute_value_placements()

        for field in self.field_data:
            if isinstance(field, RadioGroup):
                # RadioGroup: invalid selection (no option chosen) shows INVALID_COLOUR
                is_invalid = self._is_field_invalid(field)
                base_color = self._get_field_color(field)
                color = INVALID_COLOUR if is_invalid else base_color

                pen = QPen(color, 1)
                painter.setPen(pen)

                abs_x, abs_y, abs_w, abs_h = self._placed(
                    field.x, field.y, field.width, field.height
                )
                scaled_rect = self._canvas_rect_on_widget(abs_x, abs_y, abs_w, abs_h)
                painter.drawRect(scaled_rect)

                has_comment = bool(self.field_comments.get(field.name, "").strip())
                # QC red X to left when field has any comment
                if has_comment:
                    self._draw_tick_to_left(painter, scaled_rect, QColor(255, 0, 0), CROSS_CHAR)

                # Draw individual radio buttons
                selected_rb_name = self.field_values.get(field.name, None)
                
                for rb in field.radio_buttons:
                    rb_abs_x, rb_abs_y, rb_w, rb_h = self._placed(
                        rb.x, rb.y, rb.width, rb.height
                    )
                    rb_scaled_rect = self._canvas_rect_on_widget(
                        rb_abs_x, rb_abs_y, rb_w, rb_h
                    )
                    
                    # Use thicker border if selected
                    is_selected = (rb.name == selected_rb_name)
                    rb_pen = QPen(color, 3 if is_selected else 1)
                    painter.setPen(rb_pen)
                    painter.drawRect(rb_scaled_rect)
                    
                    # Fill if selected
                    if is_selected:
                        fill_color = INVALID_COLOUR if is_invalid else self._get_field_color(rb)
                        fill_color.setAlpha(100)
                        painter.fillRect(rb_scaled_rect, fill_color)

                        self._draw_tick_to_right(painter, rb_scaled_rect, QColor(0, 255, 0), TICK_CHAR)
                # Show RadioGroup selected value to the right when Show Value is on
                if self.show_field_values and selected_rb_name:
                    min_x = value_placements.get(field.name)
                    self._draw_value_to_right(
                        painter, scaled_rect, base_color, selected_rb_name, is_invalid,
                        min_x=min_x,
                    )

            elif isinstance(field, (Tickbox, TextField)):
                # Tickbox/TextField (and subclasses): colour reflects validation
                is_invalid = self._is_field_invalid(field)
                base_color = self._get_field_color(field)
                color = INVALID_COLOUR if is_invalid else base_color
                has_comment = bool(self.field_comments.get(field.name, "").strip())
                
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

                abs_x, abs_y, abs_w, abs_h = self._placed(
                    field.x, field.y, field.width, field.height
                )
                scaled_rect = self._canvas_rect_on_widget(abs_x, abs_y, abs_w, abs_h)
                painter.drawRect(scaled_rect)
                
                # Fill tickbox if checked
                if isinstance(field, Tickbox) and field_value:
                    fill_color = INVALID_COLOUR if is_invalid else base_color
                    fill_color.setAlpha(100)
                    painter.fillRect(scaled_rect, fill_color)
                    # Green tick when checked and no QC comment
                    if not has_comment:
                        self._draw_tick_to_right(painter, scaled_rect, QColor(0, 255, 0), TICK_CHAR)

                # Fill and show text for TextField
                if isinstance(field, TextField) and field_value:
                    # Fill with semitransparent color
                    fill_color = INVALID_COLOUR if is_invalid else base_color
                    fill_color.setAlpha(100)
                    painter.fillRect(scaled_rect, fill_color)

                    # Draw value to the right when Show Value is on
                    if self.show_field_values:
                        min_x = value_placements.get(field.name)
                        value_str = str(field_value)
                        if isinstance(field, (IntegerField, DecimalField)):
                            value_str = _format_number_for_display(value_str)
                        self._draw_value_to_right(
                            painter, scaled_rect, base_color, value_str, is_invalid,
                            min_x=min_x,
                        )

                # QC red X to left when field has any comment (any field type)
                if has_comment:
                    self._draw_tick_to_left(painter, scaled_rect, QColor(255, 0, 0), CROSS_CHAR)
        
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
        
        # Convert click coordinates to prepared-canvas coordinates
        ox, oy = self.canvas_origin
        click_x = (event.pos().x() - self.image_offset_x) / self.scale_x + ox
        click_y = (event.pos().y() - self.image_offset_y) / self.scale_y + oy
        
        # Check which field was clicked
        for field in self.field_data:
            if isinstance(field, RadioGroup):
                # Check individual radio buttons
                for rb in field.radio_buttons:
                    rb_abs_x, rb_abs_y, rb_w, rb_h = self._placed(
                        rb.x, rb.y, rb.width, rb.height
                    )
                    if (rb_abs_x <= click_x <= rb_abs_x + rb_w and
                        rb_abs_y <= click_y <= rb_abs_y + rb_h):
                        self.on_field_click(field, rb)
                        return
            else:
                abs_x, abs_y, abs_w, abs_h = self._placed(
                    field.x, field.y, field.width, field.height
                )
                if (abs_x <= click_x <= abs_x + abs_w and
                    abs_y <= click_y <= abs_y + abs_h):
                    self.on_field_click(field, None)
                    return

    def get_field_rect_in_widget(self, field) -> QRect | None:
        """
        Return the field's bounding rectangle in widget coordinates, or None
        if the field is not a simple rect (e.g. RadioGroup has multiple rects).
        Used to position IndexTextDialog under a TextField.
        """
        if not self.base_pixmap or not self.field_data:
            return None
        abs_x, abs_y, abs_w, abs_h = self._placed(
            field.x, field.y, field.width, field.height
        )
        return self._canvas_rect_on_widget(abs_x, abs_y, abs_w, abs_h)

