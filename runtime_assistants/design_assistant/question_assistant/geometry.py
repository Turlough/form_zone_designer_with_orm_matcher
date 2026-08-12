"""Geometry helpers for Question Assistant ROI analysis."""

from __future__ import annotations

from typing import Sequence

from runtime_assistants.design_assistant.grid_assistant.geometry import (
    Rect,
    fiducial_rect_to_page,
    filter_rects_in_roi,
)

__all__ = [
    "Rect",
    "fiducial_rect_to_page",
    "filter_rects_in_roi",
    "sort_rects_reading_order",
    "guess_field_type_from_geometry",
]


def sort_rects_reading_order(rects: Sequence[Rect]) -> list[Rect]:
    """Sort rectangles top-to-bottom, then left-to-right (reading order)."""
    return sorted(
        (tuple(int(v) for v in r) for r in rects),  # type: ignore[misc]
        key=lambda r: (r[1] + r[3] / 2.0, r[0] + r[2] / 2.0),
    )


def guess_field_type_from_geometry(rect: Rect, *, median_width: float) -> str:
    """Heuristic fallback when VLM omits or mis-assigns type."""
    _x, _y, w, h = rect
    w, h = max(1, w), max(1, h)
    aspect = w / h
    if aspect >= 2.5 or (median_width > 0 and w >= median_width * 1.8):
        return "TextField"
    if h >= w * 1.5 and w >= 40:
        return "TextField"
    return "Tickbox"
