from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QMouseEvent, QFont

from fields import Field, RadioGroup, RadioButton, Tickbox, TextField
from field_factory import FIELD_TYPE_MAP as FACTORY_FIELD_TYPE_MAP, INVALID_COLOUR


TICK_CHAR = "\u2713"  # ✓
CROSS_CHAR = "\u2717"  # ✗
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
        # Dictionary mapping field name to QC comment (if any) for the current page
        self.field_comments = {}
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.image_offset_x = 0
        self.image_offset_y = 0
        
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("QLabel { background-color: #2b2b2b; }")
        self.setMinimumSize(400, 400)

        # Whether to show field values to the right of each field (controlled by Show Value toggle)
        self.show_field_values = True

        # Callback for field clicks
        self.on_field_click = None

    def _get_field_color(self, field: Field) -> QColor:
        """
        Resolve the display colour for a field using FIELD_TYPE_MAP from field_factory.

        This deliberately ignores any colour stored in the JSON and instead
        maps by concrete field class so that Indexer colours follow Designer.
        """
        # Prefer the shared FIELD_TYPE_MAP definition from field_factory.
        # Match on the *exact* concrete class, not subclasses, so that
        # specialised types (e.g. NumericRadioGroup) don't get treated
        # as their parent type by accident.
        for field_class, color, _validator in FACTORY_FIELD_TYPE_MAP.values():
            if type(field) is field_class:
                return color

        # Fallbacks: honour an existing colour attribute if present
        colour_attr = getattr(field, "colour", None)
        if isinstance(colour_attr, QColor):
            return colour_attr
        if isinstance(colour_attr, tuple) and len(colour_attr) == 3:
            try:
                return QColor(*colour_attr)
            except TypeError:
                pass

        # Ultimate fallback – a generic green
        return QColor(0, 255, 0)

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
            return "Ticked" if checked else ""

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

    def _draw_value_to_right(
        self,
        painter: QPainter,
        scaled_rect: QRect,
        base_color: QColor,
        value_str: str,
        is_invalid: bool,
    ) -> None:
        """
        Draw field value to the right of the field rect.
        Black text on 70% opaque white background.
        Truncates to 30 characters.
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
        value_rect = QRect(
            scaled_rect.right() + offset,
            scaled_rect.y(),
            text_w + pad_h * 2,
            text_h + pad_v * 2,
        )
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

    def set_image(self, pixmap, bbox=None, field_data=None, field_values=None, field_comments=None):
        """Set the image, bounding box, fields, and field values/comments to display."""
        self.base_pixmap = pixmap
        self.bbox = bbox
        self.field_data = field_data or []
        self.field_values = field_values or {}
        self.field_comments = field_comments or {}
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
                # RadioGroup: invalid selection (no option chosen) shows INVALID_COLOUR
                is_invalid = self._is_field_invalid(field)
                base_color = self._get_field_color(field)
                color = INVALID_COLOUR if is_invalid else base_color

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

                has_comment = bool(self.field_comments.get(field.name, "").strip())
                # QC tick/cross independent of data validation
                if has_comment:
                    self._draw_tick_to_right(painter, scaled_rect, QColor(255, 0, 0), CROSS_CHAR)
                # else:
                #     self._draw_tick_to_right(painter, scaled_rect, QColor(0, 255, 0), TICK_CHAR)

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
                        fill_color = INVALID_COLOUR if is_invalid else self._get_field_color(rb)
                        fill_color.setAlpha(100)
                        painter.fillRect(rb_scaled_rect, fill_color)

                        self._draw_tick_to_right(painter, rb_scaled_rect, QColor(0, 255, 0), TICK_CHAR)
                # Show RadioGroup selected value to the right when Show Value is on
                if self.show_field_values and selected_rb_name:
                    self._draw_value_to_right(
                        painter, scaled_rect, base_color, selected_rb_name, is_invalid
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
                    fill_color = INVALID_COLOUR if is_invalid else base_color
                    fill_color.setAlpha(100)
                    painter.fillRect(scaled_rect, fill_color)
                    # QC tick/cross beside tickbox
                    if has_comment:
                        self._draw_tick_to_right(painter, scaled_rect, QColor(255, 0, 0), CROSS_CHAR)
                    else:
                        self._draw_tick_to_right(painter, scaled_rect, QColor(0, 255, 0), TICK_CHAR)
                
                # Fill and show text for TextField
                if isinstance(field, TextField) and field_value:
                    # Fill with semitransparent color
                    fill_color = INVALID_COLOUR if is_invalid else base_color
                    fill_color.setAlpha(100)
                    painter.fillRect(scaled_rect, fill_color)

                    # Draw value to the right when Show Value is on
                    if self.show_field_values:
                        self._draw_value_to_right(
                            painter, scaled_rect, base_color, str(field_value), is_invalid
                        )
                    # QC tick/cross beside text field
                    if has_comment:
                        self._draw_tick_to_right(painter, scaled_rect, QColor(255, 0, 0), CROSS_CHAR)
        
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

    def get_field_rect_in_widget(self, field) -> QRect | None:
        """
        Return the field's bounding rectangle in widget coordinates, or None
        if the field is not a simple rect (e.g. RadioGroup has multiple rects).
        Used to position IndexTextDialog under a TextField.
        """
        if not self.base_pixmap or not self.field_data:
            return None
        logo_offset = self.bbox[0] if self.bbox else (0, 0)
        if isinstance(field, RadioGroup):
            # Return the group container rect
            abs_x = field.x + logo_offset[0]
            abs_y = field.y + logo_offset[1]
        else:
            abs_x = field.x + logo_offset[0]
            abs_y = field.y + logo_offset[1]
        x = self.image_offset_x + int(abs_x * self.scale_x)
        y = self.image_offset_y + int(abs_y * self.scale_y)
        w = int(field.width * self.scale_x)
        h = int(field.height * self.scale_y)
        return QRect(x, y, w, h)

