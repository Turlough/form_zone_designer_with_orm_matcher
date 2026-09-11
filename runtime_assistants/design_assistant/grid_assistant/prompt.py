"""Prompts for Grid Assistant VLM analysis of a grid ROI crop."""

from __future__ import annotations

from typing import Sequence

SYSTEM_INSTRUCTIONS = """\
You analyse a cropped region of a scanned paper survey form that contains one
radio / checkbox grid (matrix or a single row or column of options).

Return a single JSON object only (no markdown). Read printed text carefully.
Never invent options that are not visible. Do not put question numbers inside
row_labels or col_labels (question_number is a separate field).
"""


def build_user_prompt(
    *,
    orientation: str,
    n_rows: int,
    n_cols: int,
    image_width: int,
    image_height: int,
    candidate_rects: Sequence[tuple[int, int, int, int]],
) -> str:
    orient = (orientation or "horizontal").strip().lower()
    if orient not in ("horizontal", "vertical"):
        orient = "horizontal"

    rect_lines = []
    for i, (x, y, w, h) in enumerate(candidate_rects):
        rect_lines.append(f"  {i}: x={x}, y={y}, w={w}, h={h}")
    rect_block = "\n".join(rect_lines) if rect_lines else "  (none)"

    if orient == "vertical":
        if n_cols == 1:
            question_axis = (
                "- col_labels: one entry. For this single-column option list, "
                "the column label is the full question text (same as full_text)."
            )
        else:
            question_axis = (
                "- col_labels: one question text per column, left to right."
            )
        layout_rules = f"""\
Orientation is VERTICAL (column = question / RadioGroup; rows = answer options):
{question_axis}
- row_labels: the answer option texts (e.g. Under 35, 35 to 44, …), top to bottom.
- Do not put the question number in row_labels or col_labels.
"""
    else:
        if n_rows == 1:
            question_axis = (
                "- row_labels: one entry. For this single-row option list, "
                "the row label is the full question text (same as full_text)."
            )
        else:
            question_axis = (
                "- row_labels: sub-question texts top-to-bottom "
                "(no question-number prefix)."
            )
        layout_rules = f"""\
Orientation is HORIZONTAL (row = question / RadioGroup; columns = answer options):
- col_labels: shared answer headings left-to-right (e.g. Good, Average, Poor).
{question_axis}
- full_text is the stem / question wording as printed; summary is a short overlay title.
- Do not put the question number in row_labels or col_labels.
"""

    return f"""\
Crop size: {image_width} x {image_height} pixels (crop-absolute coordinates).
User-selected orientation: {orient}
Local geometry estimate from answer rectangles: {n_rows} rows × {n_cols} columns.
Match your label list lengths to that shape when possible.

Candidate answer rectangles (crop-absolute), indexed as rect_id:
{rect_block}

{layout_rules}

Also extract:
- question_number: printed number only (e.g. "1.7" or "1.2"), without trailing period if possible
- summary: short overlay label (max ~50 chars), e.g. "Health and Safety" or "Age group"
- full_text: full stem / question wording as printed
- orientation_observed: "horizontal" or "vertical" based on what you see
- warnings: optional human-readable notes

Return JSON:
{{
  "schema_version": 1,
  "question_number": "",
  "summary": "",
  "full_text": "",
  "orientation_observed": "{orient}",
  "row_labels": [],
  "col_labels": [],
  "warnings": []
}}
"""
