"""Print-finish crop: map a trimmed scan onto the untrimmed template canvas.

``print_crop`` in project_config.json is one axis-aligned rectangle in template
pixels, shared by every page. Indexer resizes each scan page to that size and
pastes it at (x, y) on a white canvas the size of the template page, then runs
fiducial matching as usual. The Indexer centre panel crops that canvas back to
the pasted scan so operators do not see the white margins.
"""

from __future__ import annotations

import logging
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

PrintCrop = tuple[int, int, int, int]  # x, y, width, height
MIN_PRINT_CROP_SIZE = 20
DEFAULT_INSET_FRACTION = 0.05


def parse_print_crop(raw) -> Optional[PrintCrop]:
    """Return (x, y, width, height) from project_config, or None if missing/invalid."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        logger.warning("print_crop must be an object with x, y, width, height")
        return None
    try:
        x = int(raw["x"])
        y = int(raw["y"])
        width = int(raw["width"])
        height = int(raw["height"])
    except (KeyError, TypeError, ValueError):
        logger.warning("print_crop is missing or has non-integer x, y, width, height")
        return None
    if width < MIN_PRINT_CROP_SIZE or height < MIN_PRINT_CROP_SIZE:
        logger.warning("print_crop is smaller than %d px", MIN_PRINT_CROP_SIZE)
        return None
    return (x, y, width, height)


def print_crop_to_dict(crop: PrintCrop) -> dict[str, int]:
    x, y, width, height = crop
    return {"x": int(x), "y": int(y), "width": int(width), "height": int(height)}


def clamp_print_crop(crop: PrintCrop, page_size: tuple[int, int]) -> PrintCrop:
    """Keep the rect inside the page and at least MIN_PRINT_CROP_SIZE."""
    page_w, page_h = page_size
    x, y, w, h = crop
    max_w = max(MIN_PRINT_CROP_SIZE, page_w)
    max_h = max(MIN_PRINT_CROP_SIZE, page_h)
    w = max(MIN_PRINT_CROP_SIZE, min(int(w), max_w))
    h = max(MIN_PRINT_CROP_SIZE, min(int(h), max_h))
    x = max(0, min(int(x), max(0, page_w - w)))
    y = max(0, min(int(y), max(0, page_h - h)))
    if x + w > page_w:
        w = max(MIN_PRINT_CROP_SIZE, page_w - x)
    if y + h > page_h:
        h = max(MIN_PRINT_CROP_SIZE, page_h - y)
    return (x, y, w, h)


def default_print_crop(page_size: tuple[int, int]) -> PrintCrop:
    """Inset rectangle so crop-mark handles are not on the page edge."""
    page_w, page_h = page_size
    inset_x = max(0, int(page_w * DEFAULT_INSET_FRACTION))
    inset_y = max(0, int(page_h * DEFAULT_INSET_FRACTION))
    width = max(MIN_PRINT_CROP_SIZE, page_w - 2 * inset_x)
    height = max(MIN_PRINT_CROP_SIZE, page_h - 2 * inset_y)
    return clamp_print_crop((inset_x, inset_y, width, height), page_size)


def prepare_scan_page(
    scan: Image.Image,
    template_size: tuple[int, int],
    print_crop: Optional[PrintCrop],
) -> Image.Image:
    """Fit a scan page onto the template pixel canvas.

    With no crop: resize the whole scan to ``template_size`` (existing Indexer
    behaviour for DPI mismatch). With a crop: resize the scan to the crop size
    and paste it at the crop origin on a white template-sized canvas.
    """
    target_w, target_h = template_size
    if target_w <= 0 or target_h <= 0:
        return scan
    if print_crop is None:
        if scan.size == (target_w, target_h):
            return scan
        return scan.resize((target_w, target_h), Image.Resampling.LANCZOS)

    cx, cy, cw, ch = clamp_print_crop(print_crop, (target_w, target_h))
    canvas = Image.new("RGB", (target_w, target_h), (255, 255, 255))
    fitted = scan.convert("RGB").resize((cw, ch), Image.Resampling.LANCZOS)
    canvas.paste(fitted, (cx, cy))
    return canvas


def display_origin(
    print_crop: Optional[PrintCrop],
    page_size: tuple[int, int],
) -> tuple[int, int]:
    """Canvas offset to subtract when showing the pasted scan without margins."""
    if print_crop is None:
        return (0, 0)
    cx, cy, _cw, _ch = clamp_print_crop(print_crop, page_size)
    return (cx, cy)


def crop_prepared_page_for_display(
    prepared: Image.Image,
    print_crop: Optional[PrintCrop],
) -> Image.Image:
    """Return the pasted scan from a prepared canvas, with no white margins.

    Matching still uses the full template-sized canvas. Display crops to the
    print_crop rectangle. With no crop, the prepared page is unchanged.
    """
    if print_crop is None:
        return prepared
    cx, cy, cw, ch = clamp_print_crop(print_crop, prepared.size)
    if cx == 0 and cy == 0 and (cw, ch) == prepared.size:
        return prepared
    return prepared.crop((cx, cy, cx + cw, cy + ch))


def resize_rect_by_handle(
    start: PrintCrop,
    handle: str,
    current_x: int,
    current_y: int,
    page_size: tuple[int, int],
) -> PrintCrop:
    """Resize a crop rect from a drag, then clamp to the page."""
    x, y, w, h = start
    if handle in ("nw", "n", "ne"):
        new_top = current_y
        bottom = y + h
        y = min(new_top, bottom - MIN_PRINT_CROP_SIZE)
        h = bottom - y
    if handle in ("sw", "s", "se"):
        h = max(MIN_PRINT_CROP_SIZE, current_y - y)
    if handle in ("nw", "w", "sw"):
        new_left = current_x
        right = x + w
        x = min(new_left, right - MIN_PRINT_CROP_SIZE)
        w = right - x
    if handle in ("ne", "e", "se"):
        w = max(MIN_PRINT_CROP_SIZE, current_x - x)
    return clamp_print_crop((x, y, w, h), page_size)


def move_rect(
    crop: PrintCrop,
    dx: int,
    dy: int,
    page_size: tuple[int, int],
) -> PrintCrop:
    x, y, w, h = crop
    return clamp_print_crop((x + dx, y + dy, w, h), page_size)


def fiducial_bbox_inside_crop(bbox: tuple, crop: PrintCrop) -> bool:
    """True when an ORMMatcher (top_left, bottom_right) box lies fully inside crop.

    The prepared scan only has form pixels inside the print-crop rectangle.
    A fiducial patch taken from outside that rect would include blank canvas.
    """
    top_left, bottom_right = bbox
    x0, y0 = int(top_left[0]), int(top_left[1])
    x1, y1 = int(bottom_right[0]), int(bottom_right[1])
    cx, cy, cw, ch = crop
    return x0 >= cx and y0 >= cy and x1 <= cx + cw and y1 <= cy + ch


def crop_uv_to_canvas(u: float, v: float, crop: PrintCrop) -> tuple[float, float]:
    """Map crop-normalised (u, v) to template/canvas pixels."""
    cx, cy, cw, ch = crop
    return cx + u * cw, cy + v * ch


def canvas_to_crop_uv(x: float, y: float, crop: PrintCrop) -> tuple[float, float] | None:
    """Map canvas pixels to crop-normalised (u, v), or None if outside the crop."""
    cx, cy, cw, ch = crop
    if cw <= 0 or ch <= 0:
        return None
    if x < cx or y < cy or x > cx + cw or y > cy + ch:
        return None
    return (x - cx) / cw, (y - cy) / ch
