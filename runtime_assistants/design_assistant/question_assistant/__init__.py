"""Question Assistant: fill multi-answer question metadata from a drawn ROI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from PIL import Image

from runtime_assistants.design_assistant.question_assistant.client import (
    call_vlm,
    crop_roi,
    get_model_name,
    rects_relative_to_roi,
)
from runtime_assistants.design_assistant.question_assistant.geometry import (
    fiducial_rect_to_page,
    filter_rects_in_roi,
    guess_field_type_from_geometry,
    sort_rects_reading_order,
)
from runtime_assistants.design_assistant.question_assistant.schema import (
    QuestionFieldProposal,
    align_fields_to_rect_count,
    validate_question_analysis,
)
from util.field_metadata import truncate_summary, upgrade_field_dict


@dataclass
class AnalyseQuestionResult:
    """Result ready to apply into the Rectangle Selected dialog (batch mode)."""

    question_number: str = ""
    full_text: str = ""
    fields: list[QuestionFieldProposal] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    model: str = ""
    rects_in_roi_count: int = 0


def analyse_question(
    page_image: Image.Image,
    *,
    roi_fiducial: tuple[int, int, int, int],
    fiducial_bbox: tuple | None,
    cv_rects: Sequence[tuple[int, int, int, int]],
    inner_rects_fiducial: Sequence[tuple[int, int, int, int]] | None = None,
    export_columns_block: str = "",
    model: str | None = None,
) -> AnalyseQuestionResult:
    """Analyse one question ROI and return per-rectangle field proposals.

    ``roi_fiducial`` is the user-drawn frame (fiducial-relative).
    ``inner_rects_fiducial`` when provided are the inner answer boxes already
    known from Designer (fiducial-relative); otherwise CV rects inside ROI are used.
    """
    model_name = model or get_model_name()
    roi_page = fiducial_rect_to_page(roi_fiducial, fiducial_bbox)

    if inner_rects_fiducial:
        ox, oy = 0, 0
        if fiducial_bbox:
            ox, oy = int(fiducial_bbox[0][0]), int(fiducial_bbox[0][1])
        in_roi_page = [
            (rx + ox, ry + oy, rw, rh)
            for rx, ry, rw, rh in inner_rects_fiducial
        ]
    else:
        in_roi_page = filter_rects_in_roi(list(cv_rects or []), roi_page)

    in_roi_page = sort_rects_reading_order(in_roi_page)
    n = len(in_roi_page)
    if n < 1:
        raise ValueError(
            "Need at least one answer rectangle inside the question frame. "
            "Detect rectangles on the page or draw a frame that includes them."
        )

    warnings: list[str] = []
    crop = crop_roi(page_image, roi_page)
    crop_rects = rects_relative_to_roi(in_roi_page, roi_page)

    raw = call_vlm(
        crop,
        n_answer_rects=n,
        crop_rects=crop_rects,
        export_columns_block=export_columns_block,
        model=model_name,
    )
    parsed = validate_question_analysis(raw)
    warnings.extend(parsed.warnings)

    proposals, align_warnings = align_fields_to_rect_count(parsed.fields, n)
    warnings.extend(align_warnings)

    widths = [max(1, r[2]) for r in in_roi_page]
    median_w = sorted(widths)[len(widths) // 2] if widths else 12

    for i, proposal in enumerate(proposals):
        if not proposal.name or proposal.name.startswith("Option "):
            proposal.name = proposal.column_title or proposal.name or f"Option {i + 1}"
        if not proposal.summary:
            proposal.summary = truncate_summary(proposal.name)
        if not proposal.column_title:
            proposal.column_title = proposal.name

    if not parsed.fields:
        warnings.append("VLM returned no fields; using geometry heuristics for types.")
        for i, proposal in enumerate(proposals):
            proposal.field_type = guess_field_type_from_geometry(
                in_roi_page[i], median_width=median_w
            )

    return AnalyseQuestionResult(
        question_number=parsed.question_number,
        full_text=parsed.full_text,
        fields=proposals,
        warnings=warnings,
        model=model_name,
        rects_in_roi_count=n,
    )


def field_dict_from_proposal(
    proposal: QuestionFieldProposal,
    *,
    question_number: str,
    question_full_text: str,
) -> dict:
    """Build a normalised field config dict for persistence."""
    option_text = proposal.name
    d = upgrade_field_dict(
        {
            "_type": proposal.field_type,
            "name": proposal.name,
            "summary": proposal.summary or truncate_summary(proposal.name),
            "column_title": proposal.column_title or proposal.name,
            "full_text": question_full_text or option_text,
            "question_number": question_number,
        }
    )
    d["field_type"] = proposal.field_type
    return d


__all__ = [
    "AnalyseQuestionResult",
    "QuestionFieldProposal",
    "analyse_question",
    "field_dict_from_proposal",
]
