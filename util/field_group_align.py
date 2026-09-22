"""Temporary group move/scale for Indexer field outlines on one page visit.

Field JSON stays logo-relative. A FieldGroupAlign maps those rectangles onto
the prepared canvas after the user drags the group. Nothing here is saved.
"""

from __future__ import annotations

from dataclasses import dataclass

from fields import RadioGroup

Bounds = tuple[float, float, float, float]  # x, y, width, height

MIN_GROUP_SIZE = 10.0

_CORNER_FIXED = {
    # corner -> (fixed x edge, fixed y edge)
    "se": ("left", "top"),
    "nw": ("right", "bottom"),
    "ne": ("left", "bottom"),
    "sw": ("right", "top"),
}


@dataclass(frozen=True)
class FieldGroupAlign:
    """Logo used when the group was captured, plus source and dest canvas bounds."""

    logo: tuple[float, float]
    source: Bounds
    dest: Bounds


def iter_outline_rects(fields) -> list[Bounds]:
    """Logo-relative outline of each field, plus each radio button."""
    rects: list[Bounds] = []
    for field in fields:
        rects.append(
            (float(field.x), float(field.y), float(field.width), float(field.height))
        )
        if isinstance(field, RadioGroup):
            for rb in field.radio_buttons:
                rects.append((float(rb.x), float(rb.y), float(rb.width), float(rb.height)))
    return rects


def group_bounds(rects: list[Bounds]) -> Bounds | None:
    """Axis-aligned union. None when there is nothing to enclose."""
    if not rects:
        return None
    left = min(r[0] for r in rects)
    top = min(r[1] for r in rects)
    right = max(r[0] + r[2] for r in rects)
    bottom = max(r[1] + r[3] for r in rects)
    return (left, top, right - left, bottom - top)


def translate_bounds(bounds: Bounds, dx: float, dy: float) -> Bounds:
    x, y, w, h = bounds
    return (x + dx, y + dy, w, h)


def same_bounds(a: Bounds, b: Bounds, eps: float = 0.5) -> bool:
    return all(abs(a[i] - b[i]) <= eps for i in range(4))


def map_rect(source: Bounds, dest: Bounds, rect: Bounds) -> Bounds:
    """Map rect from source's box into dest's box (independent x/y scale)."""
    sx, sy, sw, sh = source
    dx, dy, dw, dh = dest
    rx, ry, rw, rh = rect
    scale_x = dw / sw if sw else 1.0
    scale_y = dh / sh if sh else 1.0
    return (
        dx + (rx - sx) * scale_x,
        dy + (ry - sy) * scale_y,
        rw * scale_x,
        rh * scale_y,
    )


def placed_rect(
    x: float,
    y: float,
    w: float,
    h: float,
    logo_offset: tuple[float, float],
    align: FieldGroupAlign | None,
) -> Bounds:
    """Canvas rectangle for a logo-relative field.

    With an align, the logo frozen on that align is used so a later fiducial
    result cannot shift the group a second time.
    """
    if align is not None:
        lx, ly = align.logo
        return map_rect(align.source, align.dest, (x + lx, y + ly, w, h))
    lx, ly = logo_offset
    return (x + lx, y + ly, w, h)


def hit_group_bounds(
    px: float,
    py: float,
    bounds: Bounds,
    hit_px: float,
) -> str | None:
    """Return move, an edge (n/s/e/w), a corner, or None.

    Corners win over edges. The whole edge is a hit, not only its midpoint.
    """
    x, y, w, h = bounds
    corners = {
        "nw": (x, y),
        "ne": (x + w, y),
        "sw": (x, y + h),
        "se": (x + w, y + h),
    }
    for name, (cx, cy) in corners.items():
        if abs(px - cx) <= hit_px and abs(py - cy) <= hit_px:
            return name
    span_x = x - hit_px <= px <= x + w + hit_px
    span_y = y - hit_px <= py <= y + h + hit_px
    if abs(py - y) <= hit_px and span_x:
        return "n"
    if abs(py - (y + h)) <= hit_px and span_x:
        return "s"
    if abs(px - x) <= hit_px and span_y:
        return "w"
    if abs(px - (x + w)) <= hit_px and span_y:
        return "e"
    if x <= px <= x + w and y <= py <= y + h:
        return "move"
    return None


def _corner_growth(corner: str, dx: float, dy: float) -> tuple[float, float]:
    """Mouse delta as growth of width and height (positive grows the box)."""
    if corner == "se":
        return dx, dy
    if corner == "nw":
        return -dx, -dy
    if corner == "ne":
        return dx, -dy
    if corner == "sw":
        return -dx, dy
    return dx, dy


def _place_from_fixed(
    start: Bounds,
    new_w: float,
    new_h: float,
    fix_x: str,
    fix_y: str,
) -> Bounds:
    x, y, w, h = start
    nx = x if fix_x == "left" else x + w - new_w
    ny = y if fix_y == "top" else y + h - new_h
    return (nx, ny, new_w, new_h)


def _drag_corner(start: Bounds, corner: str, dx: float, dy: float, min_size: float) -> Bounds:
    x, y, w, h = start
    aspect = w / h if h else 1.0
    grow_w, grow_h = _corner_growth(corner, dx, dy)
    use_w = abs(grow_w) / w >= abs(grow_h) / h if w and h else True
    if use_w:
        new_w = max(min_size, w + grow_w)
        new_h = new_w / aspect if aspect else min_size
    else:
        new_h = max(min_size, h + grow_h)
        new_w = new_h * aspect
    if new_h < min_size:
        new_h = min_size
        new_w = new_h * aspect
    if new_w < min_size:
        new_w = min_size
        new_h = new_w / aspect if aspect else min_size
    fix_x, fix_y = _CORNER_FIXED[corner]
    return _place_from_fixed(start, new_w, new_h, fix_x, fix_y)


def drag_group_bounds(
    start: Bounds,
    mode: str,
    dx: float,
    dy: float,
    min_size: float = MIN_GROUP_SIZE,
) -> Bounds:
    """Apply one drag step from the bounds at press time.

    move: translate. n/s/e/w: scale that axis only, opposite edge fixed.
    Corners: uniform scale so the box keeps its aspect ratio.
    """
    x, y, w, h = start
    if mode == "move":
        return (x + dx, y + dy, w, h)
    if mode == "e":
        return (x, y, max(min_size, w + dx), h)
    if mode == "w":
        new_w = max(min_size, w - dx)
        return (x + w - new_w, y, new_w, h)
    if mode == "s":
        return (x, y, w, max(min_size, h + dy))
    if mode == "n":
        new_h = max(min_size, h - dy)
        return (x, y + h - new_h, w, new_h)
    if mode in _CORNER_FIXED:
        return _drag_corner(start, mode, dx, dy, min_size)
    return start
