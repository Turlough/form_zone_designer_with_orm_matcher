"""Grid Assistant: analyse a Grid Designer ROI via local CV + external VLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from PIL import Image

from runtime_assistants.design_assistant.grid_assistant.client import (
    call_vlm,
    crop_roi,
    get_model_name,
    rects_relative_to_roi,
)
from runtime_assistants.design_assistant.grid_assistant.geometry import (
    ClusterResult,
    align_labels_to_counts,
    cluster_grid_rects,
    fiducial_rect_to_page,
    filter_rects_in_roi,
)
from runtime_assistants.design_assistant.grid_assistant.schema import (
    GridAnalysisResult,
    validate_grid_analysis,
)
from util.field_metadata import truncate_summary


@dataclass
class AnalyseGridResult:
    """Result ready to apply into Grid Designer."""

    question_number: str = ""
    summary: str = ""
    full_text: str = ""
    name: str = ""
    row_labels: list[str] = field(default_factory=list)
    col_labels: list[str] = field(default_factory=list)
    n_rows: int = 1
    n_cols: int = 1
    row_fracs: list[float] = field(default_factory=list)
    col_fracs: list[float] = field(default_factory=list)
    orientation_observed: str = ""
    warnings: list[str] = field(default_factory=list)
    model: str = ""
    rects_in_roi_count: int = 0


def analyse_grid(
    page_image: Image.Image,
    *,
    grid_rect_fiducial: tuple[int, int, int, int],
    fiducial_bbox: tuple | None,
    cv_rects: Sequence[tuple[int, int, int, int]],
    orientation: str,
    model: str | None = None,
) -> AnalyseGridResult:
    """Analyse one grid ROI and return labels + layout for Grid Designer.

    ``grid_rect_fiducial`` is fiducial-relative (x, y, w, h).
    ``cv_rects`` are page-absolute.
    """
    model_name = model or get_model_name()
    orientation = (orientation or "horizontal").strip().lower()
    if orientation not in ("horizontal", "vertical"):
        orientation = "horizontal"

    roi_page = fiducial_rect_to_page(grid_rect_fiducial, fiducial_bbox)
    in_roi = filter_rects_in_roi(list(cv_rects or []), roi_page)
    if len(in_roi) < 2:
        raise ValueError(
            "Need at least two answer rectangles inside the grid ROI. "
            "Detect or reshape rectangles on the main Designer page first."
        )

    cluster: ClusterResult = cluster_grid_rects(
        in_roi, roi_page, user_orientation=orientation
    )
    warnings = list(cluster.warnings)

    crop = crop_roi(page_image, roi_page)
    crop_rects = rects_relative_to_roi(in_roi, roi_page)

    raw = call_vlm(
        crop,
        orientation=orientation,
        n_rows=cluster.n_rows,
        n_cols=cluster.n_cols,
        crop_rects=crop_rects,
        model=model_name,
    )
    parsed: GridAnalysisResult = validate_grid_analysis(raw)
    warnings.extend(parsed.warnings)

    row_labels, col_labels, label_warnings = align_labels_to_counts(
        parsed.row_labels,
        parsed.col_labels,
        cluster.n_rows,
        cluster.n_cols,
    )
    warnings.extend(label_warnings)

    if (
        parsed.orientation_observed
        and parsed.orientation_observed != orientation
    ):
        warnings.append(
            f"VLM observed orientation {parsed.orientation_observed!r}, "
            f"but Grid Designer is set to {orientation!r}."
        )

    summary = parsed.summary or truncate_summary(parsed.full_text or "Grid")
    name = summary
    full_text = parsed.full_text
    # Single-column vertical: column label should be full question text
    if orientation == "vertical" and cluster.n_cols == 1 and full_text:
        if not col_labels or col_labels[0].startswith("Column "):
            col_labels = [full_text]

    return AnalyseGridResult(
        question_number=parsed.question_number,
        summary=summary,
        full_text=full_text,
        name=name,
        row_labels=row_labels,
        col_labels=col_labels,
        n_rows=cluster.n_rows,
        n_cols=cluster.n_cols,
        row_fracs=list(cluster.row_fracs),
        col_fracs=list(cluster.col_fracs),
        orientation_observed=parsed.orientation_observed,
        warnings=warnings,
        model=model_name,
        rects_in_roi_count=len(in_roi),
    )


__all__ = [
    "AnalyseGridResult",
    "GridAnalysisResult",
    "analyse_grid",
]
