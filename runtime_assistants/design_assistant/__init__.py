"""Design assistant: analyse a Designer template page via external VLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from PIL import Image

from fields import Field
from runtime_assistants.design_assistant.client import (
    call_vlm,
    downscale_for_upload,
    get_model_name,
)
from runtime_assistants.design_assistant.convert import analysis_dicts_to_fields
from runtime_assistants.design_assistant.match import match_fields_to_rects
from runtime_assistants.design_assistant.schema import (
    PageAnalysisResult,
    fields_for_persistence,
    validate_and_upgrade,
)


@dataclass
class AnalysePageResult:
    """Result ready for Designer preview / apply."""

    fields: list[Field]
    field_dicts: list[dict]
    warnings: list[str] = field(default_factory=list)
    grid_suggestions: list[dict] = field(default_factory=list)
    model: str = ""


def analyse_page(
    page_image: Image.Image,
    *,
    page_index: int,
    fiducial_bbox: tuple | None,
    cv_rects: Sequence[tuple[int, int, int, int]] | None = None,
    model: str | None = None,
) -> AnalysePageResult:
    """Analyse one template page and return Field objects + warnings.

    Coordinates on returned fields are fiducial-relative when ``fiducial_bbox``
    is provided, otherwise page-absolute.
    """
    model_name = model or get_model_name()
    _, upload_scale = downscale_for_upload(page_image)
    # upload_coord * inv_scale ≈ original page pixel
    inv_scale = (1.0 / upload_scale) if upload_scale > 0 else 1.0

    raw = call_vlm(
        page_image,
        page_index=page_index,
        fiducial_bbox=fiducial_bbox,
        cv_rects=cv_rects,
        model=model_name,
    )
    parsed = validate_and_upgrade(raw)

    # VLM page_* / grid coords are in upload space; rect_id indexes original cv_rects.
    fields_scaled = _scale_page_hints(parsed.fields, inv_scale)

    fiducial_tl = None
    if fiducial_bbox:
        fiducial_tl = (int(fiducial_bbox[0][0]), int(fiducial_bbox[0][1]))

    matched, match_warnings = match_fields_to_rects(
        fields_scaled,
        list(cv_rects or []),
        fiducial_top_left=fiducial_tl,
    )
    warnings = list(parsed.warnings) + match_warnings
    persistable = fields_for_persistence(matched)
    field_objs = analysis_dicts_to_fields(matched)

    grids = _scale_grid_suggestions(parsed.grid_suggestions, inv_scale)

    return AnalysePageResult(
        fields=field_objs,
        field_dicts=persistable,
        warnings=warnings,
        grid_suggestions=grids,
        model=model_name,
    )


def _scale_page_hints(fields: list[dict], inv_scale: float) -> list[dict]:
    if abs(inv_scale - 1.0) < 1e-6:
        return [dict(f) for f in fields]
    out = []
    for f in fields:
        f2 = dict(f)
        for key in ("page_x", "page_y", "page_width", "page_height"):
            if key in f2:
                try:
                    f2[key] = int(round(float(f2[key]) * inv_scale))
                except (TypeError, ValueError):
                    pass
        rbs = f2.get("radio_buttons")
        if isinstance(rbs, list):
            f2["radio_buttons"] = _scale_page_hints(
                [rb for rb in rbs if isinstance(rb, dict)],
                inv_scale,
            )
        out.append(f2)
    return out


def _scale_grid_suggestions(grids: list[dict], inv_scale: float) -> list[dict]:
    if abs(inv_scale - 1.0) < 1e-6:
        return list(grids)
    out = []
    for g in grids:
        g2 = dict(g)
        for key in ("x", "y", "width", "height"):
            if key in g2:
                try:
                    g2[key] = int(round(float(g2[key]) * inv_scale))
                except (TypeError, ValueError):
                    pass
        out.append(g2)
    return out


__all__ = [
    "AnalysePageResult",
    "PageAnalysisResult",
    "analyse_page",
]
