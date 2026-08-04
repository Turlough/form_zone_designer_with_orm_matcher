"""Per-project rectangle detection sensitivity settings."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class RectangleDetectionSettings:
    """OpenCV rectangle detection parameters (Canny path + optional adaptive method)."""

    blur_kernel_size: int = 3
    dilate_iterations: int = 7
    epsilon_factor: float = 0.02
    canny_low_threshold: int = 60
    canny_high_threshold: int = 150
    overlap_threshold_value: float = 0.7
    min_area: int = 500
    max_area: int = 30000
    include_adaptive_method: bool = True
    auto_remove_inner: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RectangleDetectionSettings:
        if not data:
            return cls()
        known = {f.name for f in fields(cls)}
        float_fields = {"epsilon_factor", "overlap_threshold_value"}
        bool_fields = {"include_adaptive_method", "auto_remove_inner"}
        kwargs: dict[str, Any] = {}
        for name in known:
            if name not in data:
                continue
            value = data[name]
            if name in bool_fields:
                kwargs[name] = bool(value)
            elif name in float_fields:
                kwargs[name] = float(value)
            else:
                kwargs[name] = int(value)
        settings = cls(**kwargs)
        settings.normalize()
        return settings

    def normalize(self) -> None:
        """Clamp values to sensible ranges."""
        self.blur_kernel_size = max(3, self.blur_kernel_size | 1)
        self.dilate_iterations = max(0, self.dilate_iterations)
        self.epsilon_factor = max(0.001, self.epsilon_factor)
        self.canny_low_threshold = max(1, self.canny_low_threshold)
        self.canny_high_threshold = max(
            self.canny_low_threshold + 1, self.canny_high_threshold
        )
        self.overlap_threshold_value = min(1.0, max(0.0, self.overlap_threshold_value))
        self.min_area = max(1, self.min_area)
        self.max_area = max(self.min_area, self.max_area)


DEFAULT_RECTANGLE_DETECTION_SETTINGS = RectangleDetectionSettings()

# Single source for dialog tooltips (summary + adjustment direction).
PARAM_TOOLTIPS: dict[str, str] = {
    "blur_kernel_size": (
        "Gaussian blur kernel size before edge detection. "
        "Higher → more blur, fewer spurious edges; lower → sharper edges, more noise. "
        "Higher values generally mean more rectangles detected (softer edges connect)."
    ),
    "dilate_iterations": (
        "How much to expand edges to connect nearby contours. "
        "Higher → accepts weaker or slightly broken lines; lower → stricter connected outlines."
    ),
    "epsilon_factor": (
        "Contour simplification accuracy (approxPolyDP). "
        "Higher → more irregular boundaries accepted as quadrilaterals."
    ),
    "canny_low_threshold": (
        "Canny edge detector low threshold. "
        "Increase to reduce noise; lower → more edge pixels, more rectangles."
    ),
    "canny_high_threshold": (
        "Canny edge detector high threshold. "
        "Adjust the low threshold first; lower → more rectangles detected."
    ),
    "overlap_threshold_value": (
        "IoU threshold for removing duplicate rectangles. "
        "Higher → keeps more overlapping candidates; lower → merges near-duplicates."
    ),
    "min_area": (
        "Minimum contour area to consider. "
        "Lower → more small rectangles (including text blocks); raise to filter small blobs."
    ),
    "max_area": (
        "Maximum contour area to consider. "
        "Higher → larger boxes kept; lower → discards big regions."
    ),
    "include_adaptive_method": (
        "Run adaptive-threshold detection in addition to Canny edges. "
        "Turn off to reduce text-block false positives; Canny-only is often cleaner for outlines."
    ),
    "auto_remove_inner": (
        "Remove rectangles entirely inside another (inner perimeters of the same box). "
        "Recommended when one field outline produces nested frames."
    ),
}
