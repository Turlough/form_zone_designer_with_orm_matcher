"""Geometry helpers for reshaping fields and radio-button grids in Designer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fields import Field, RadioButton, RadioGroup, NumericRadioGroup

MIN_FIELD_SIZE = 10
HANDLE_HIT_PX = 8
LINE_HIT_PX = 8

RESIZE_HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")


@dataclass
class FieldGeometrySnapshot:
    """Deep copy of field coordinates for cancel/revert."""

    x: int
    y: int
    width: int
    height: int
    radio_buttons: list[tuple[int, int, int, int]] | None = None


def snapshot_field_geometry(field: Field) -> FieldGeometrySnapshot:
    rb_snap = None
    if isinstance(field, RadioGroup):
        rb_snap = [(rb.x, rb.y, rb.width, rb.height) for rb in field.radio_buttons]
    return FieldGeometrySnapshot(field.x, field.y, field.width, field.height, rb_snap)


def restore_field_geometry(field: Field, snap: FieldGeometrySnapshot) -> None:
    field.x = snap.x
    field.y = snap.y
    field.width = snap.width
    field.height = snap.height
    if isinstance(field, RadioGroup) and snap.radio_buttons is not None:
        for rb, coords in zip(field.radio_buttons, snap.radio_buttons):
            rb.x, rb.y, rb.width, rb.height = coords


def sync_radio_group_bounds(radio_group: RadioGroup) -> None:
    """Set RadioGroup outer rect to the bounding box of its buttons."""
    if not radio_group.radio_buttons:
        return
    left = min(rb.x for rb in radio_group.radio_buttons)
    top = min(rb.y for rb in radio_group.radio_buttons)
    right = max(rb.x + rb.width for rb in radio_group.radio_buttons)
    bottom = max(rb.y + rb.height for rb in radio_group.radio_buttons)
    radio_group.x = left
    radio_group.y = top
    radio_group.width = max(MIN_FIELD_SIZE, right - left)
    radio_group.height = max(MIN_FIELD_SIZE, bottom - top)


def geometry_edit_target(field: Field, parent_group: RadioGroup | None = None) -> Field:
    """Field whose outer shape and grid lines are edited."""
    if isinstance(field, RadioButton) and parent_group is not None and len(parent_group.radio_buttons) >= 2:
        return parent_group
    if isinstance(field, RadioGroup) and len(field.radio_buttons) >= 2:
        return field
    return field


def grid_division_lines(field: Field) -> tuple[list[int], list[int]]:
    """Return internal vertical (x) and horizontal (y) division lines for a button grid."""
    if not isinstance(field, RadioGroup) or len(field.radio_buttons) < 2:
        return [], []
    buttons = field.radio_buttons
    xs = sorted({b.x for b in buttons} | {b.x + b.width for b in buttons})
    ys = sorted({b.y for b in buttons} | {b.y + b.height for b in buttons})
    if len(xs) < 2 and len(ys) < 2:
        return [], []
    return xs[1:-1], ys[1:-1]


def drag_vertical_division(radio_group: RadioGroup, line_x: int, new_x: int) -> bool:
    """Move an internal vertical grid line; return False if move rejected."""
    dx = int(new_x) - int(line_x)
    if dx == 0:
        return True
    left_width = None
    right_width = None
    for rb in radio_group.radio_buttons:
        if rb.x + rb.width == line_x:
            left_width = rb.width + dx
        elif rb.x == line_x:
            right_width = rb.width - dx
    if left_width is not None and left_width < MIN_FIELD_SIZE:
        return False
    if right_width is not None and right_width < MIN_FIELD_SIZE:
        return False
    for rb in radio_group.radio_buttons:
        if rb.x + rb.width == line_x:
            rb.width = max(MIN_FIELD_SIZE, rb.width + dx)
        elif rb.x == line_x:
            rb.x += dx
            rb.width = max(MIN_FIELD_SIZE, rb.width - dx)
    sync_radio_group_bounds(radio_group)
    return True


def drag_horizontal_division(radio_group: RadioGroup, line_y: int, new_y: int) -> bool:
    """Move an internal horizontal grid line; return False if move rejected."""
    dy = int(new_y) - int(line_y)
    if dy == 0:
        return True
    top_height = None
    bottom_height = None
    for rb in radio_group.radio_buttons:
        if rb.y + rb.height == line_y:
            top_height = rb.height + dy
        elif rb.y == line_y:
            bottom_height = rb.height - dy
    if top_height is not None and top_height < MIN_FIELD_SIZE:
        return False
    if bottom_height is not None and bottom_height < MIN_FIELD_SIZE:
        return False
    for rb in radio_group.radio_buttons:
        if rb.y + rb.height == line_y:
            rb.height = max(MIN_FIELD_SIZE, rb.height + dy)
        elif rb.y == line_y:
            rb.y += dy
            rb.height = max(MIN_FIELD_SIZE, rb.height - dy)
    sync_radio_group_bounds(radio_group)
    return True


def _clamp_rect(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    w = max(MIN_FIELD_SIZE, w)
    h = max(MIN_FIELD_SIZE, h)
    return x, y, w, h


def resize_field_by_handle(
    field: Field,
    handle: str,
    anchor_x: int,
    anchor_y: int,
    current_x: int,
    current_y: int,
) -> None:
    """Resize a simple field (or lone button) by dragging a handle in logo-relative coords."""
    x, y, w, h = field.x, field.y, field.width, field.height
    if handle in ("nw", "n", "ne"):
        new_top = current_y
        bottom = y + h
        y = min(new_top, bottom - MIN_FIELD_SIZE)
        h = bottom - y
    if handle in ("sw", "s", "se"):
        new_bottom = current_y
        h = max(MIN_FIELD_SIZE, new_bottom - y)
    if handle in ("nw", "w", "sw"):
        new_left = current_x
        right = x + w
        x = min(new_left, right - MIN_FIELD_SIZE)
        w = right - x
    if handle in ("ne", "e", "se"):
        new_right = current_x
        w = max(MIN_FIELD_SIZE, new_right - x)
    field.x, field.y, field.width, field.height = _clamp_rect(x, y, w, h)


def resize_radio_group_by_handle(
    radio_group: RadioGroup,
    handle: str,
    start_bounds: tuple[int, int, int, int],
    start_buttons: list[tuple[int, int, int, int]],
    current_x: int,
    current_y: int,
) -> None:
    """Scale all radio buttons proportionally when the group outline is reshaped."""
    ox, oy, ow, oh = start_bounds
    if ow <= 0 or oh <= 0 or len(start_buttons) != len(radio_group.radio_buttons):
        return
    nx, ny, nw, nh = ox, oy, ow, oh
    if handle in ("nw", "n", "ne"):
        ny = min(current_y, oy + oh - MIN_FIELD_SIZE)
        nh = (oy + oh) - ny
    if handle in ("sw", "s", "se"):
        nh = max(MIN_FIELD_SIZE, current_y - oy)
    if handle in ("nw", "w", "sw"):
        nx = min(current_x, ox + ow - MIN_FIELD_SIZE)
        nw = (ox + ow) - nx
    if handle in ("ne", "e", "se"):
        nw = max(MIN_FIELD_SIZE, current_x - ox)
    nx, ny, nw, nh = _clamp_rect(nx, ny, nw, nh)
    for rb, (bx, by, bw, bh) in zip(radio_group.radio_buttons, start_buttons):
        rx = (bx - ox) / ow
        ry = (by - oy) / oh
        rw = bw / ow
        rh = bh / oh
        rb.x = int(nx + rx * nw)
        rb.y = int(ny + ry * nh)
        rb.width = max(MIN_FIELD_SIZE, int(rw * nw))
        rb.height = max(MIN_FIELD_SIZE, int(rh * nh))
    radio_group.x = nx
    radio_group.y = ny
    radio_group.width = nw
    radio_group.height = nh


def button_rects_snapshot(radio_group: RadioGroup) -> list[tuple[int, int, int, int]]:
    return [(rb.x, rb.y, rb.width, rb.height) for rb in radio_group.radio_buttons]


def group_bounds_from_buttons(
    buttons: list[tuple[int, int, int, int]],
) -> tuple[int, int, int, int]:
    if not buttons:
        return 0, 0, MIN_FIELD_SIZE, MIN_FIELD_SIZE
    left = min(b[0] for b in buttons)
    top = min(b[1] for b in buttons)
    right = max(b[0] + b[2] for b in buttons)
    bottom = max(b[1] + b[3] for b in buttons)
    return left, top, max(MIN_FIELD_SIZE, right - left), max(MIN_FIELD_SIZE, bottom - top)


def move_field(field: Field, dx: int, dy: int) -> None:
    field.x += dx
    field.y += dy
    if isinstance(field, RadioGroup):
        for rb in field.radio_buttons:
            rb.x += dx
            rb.y += dy


def field_logo_rect(field: Field) -> tuple[int, int, int, int]:
    return field.x, field.y, field.width, field.height


def abs_rect_from_logo(
    rect: tuple[int, int, int, int],
    logo_top_left: tuple[int, int],
) -> tuple[int, int, int, int]:
    ox, oy = logo_top_left
    x, y, w, h = rect
    return x + ox, y + oy, w, h


def logo_rect_from_abs(
    abs_x: float,
    abs_y: float,
    logo_top_left: tuple[int, int],
) -> tuple[int, int]:
    ox, oy = logo_top_left
    return int(abs_x - ox), int(abs_y - oy)


def hit_resize_handle(
    pos_x: int,
    pos_y: int,
    rect_x: int,
    rect_y: int,
    rect_w: int,
    rect_h: int,
    hit_px: int = HANDLE_HIT_PX,
) -> Optional[str]:
    """Return handle id if pos is near a corner/edge handle (display coords)."""
    cx = rect_x + rect_w // 2
    cy = rect_y + rect_h // 2
    points = {
        "nw": (rect_x, rect_y),
        "n": (cx, rect_y),
        "ne": (rect_x + rect_w, rect_y),
        "e": (rect_x + rect_w, cy),
        "se": (rect_x + rect_w, rect_y + rect_h),
        "s": (cx, rect_y + rect_h),
        "sw": (rect_x, rect_y + rect_h),
        "w": (rect_x, cy),
    }
    for handle, (hx, hy) in points.items():
        if abs(pos_x - hx) <= hit_px and abs(pos_y - hy) <= hit_px:
            return handle
    return None


def hit_division_line(
    pos_x: int,
    pos_y: int,
    line_x: int | None,
    line_y: int | None,
    rect_x: int,
    rect_y: int,
    rect_w: int,
    rect_h: int,
    scale_x: float,
    scale_y: float,
    logo_top_left: tuple[int, int],
    hit_px: int = LINE_HIT_PX,
) -> tuple[Optional[str], Optional[int]]:
    """Hit-test internal grid lines; returns ('col'|'row', line_coord_logo) or (None, None)."""
    ox, oy = logo_top_left
    if line_x is not None:
        disp_x = int((line_x + ox) * scale_x)
        if (
            rect_x <= pos_x <= rect_x + rect_w
            and rect_y <= pos_y <= rect_y + rect_h
            and abs(pos_x - disp_x) <= hit_px
        ):
            return "col", line_x
    if line_y is not None:
        disp_y = int((line_y + oy) * scale_y)
        if (
            rect_x <= pos_x <= rect_x + rect_w
            and rect_y <= pos_y <= rect_y + rect_h
            and abs(pos_y - disp_y) <= hit_px
        ):
            return "row", line_y
    return None, None
