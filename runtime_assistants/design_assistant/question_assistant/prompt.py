"""Prompts for Question Assistant VLM analysis of a multi-answer question ROI."""

from __future__ import annotations

from typing import Sequence

from runtime_assistants.design_assistant.question_assistant.schema import ALLOWED_FIELD_TYPES

SYSTEM_INSTRUCTIONS = """\
You analyse a cropped region of a scanned paper survey form containing one question
and its answer controls (checkboxes, text boxes, numeric fields, etc.).

Return a single JSON object only (no markdown). Read printed text carefully.
Assume independent checkboxes (Tickbox), not mutually exclusive radio buttons.
Use Grid Designer elsewhere for radio-button matrices.
"""


def build_user_prompt(
    *,
    n_answer_rects: int,
    image_width: int,
    image_height: int,
    candidate_rects: Sequence[tuple[int, int, int, int]],
    export_columns_block: str = "",
) -> str:
    types_csv = ", ".join(sorted(ALLOWED_FIELD_TYPES))

    rect_lines = []
    for i, (x, y, w, h) in enumerate(candidate_rects):
        rect_lines.append(f"  {i}: x={x}, y={y}, w={w}, h={h}")
    rect_block = "\n".join(rect_lines) if rect_lines else "  (none)"

    export_section = f"\n{export_columns_block}\n" if export_columns_block else ""

    return f"""\
Crop size: {image_width} x {image_height} pixels (crop-absolute coordinates).
There are {n_answer_rects} detected answer rectangles inside this ROI, indexed as rect_id
in reading order (top-to-bottom, left-to-right).

Candidate answer rectangles (crop-absolute):
{rect_block}
{export_section}
Allowed field _type values: {types_csv}

Rules:
1. Extract the shared question:
   - question_number: printed number only (e.g. "6.9")
   - full_text: full question wording as printed (the stem above the options)
2. For EACH answer rectangle, emit one entry in fields[] with:
   - rect_id: matching index above
   - _type: Tickbox for small squares beside option labels; TextField for wide
     "Other (please specify)" boxes; IntegerField / DecimalField / DateField when
     the blank clearly expects numbers or dates
   - full_text: option-specific text (e.g. "Mastitis and SCC") — NOT the whole question
   - summary: short overlay label, max ~50 chars
   - column_title: CSV column heading (plain text)
   - name: same as column_title
3. Return exactly {n_answer_rects} field objects when possible.
4. Do NOT emit RadioGroup, RadioButton, or RadioGrid types.
5. warnings: optional notes

Return JSON:
{{
  "schema_version": 1,
  "question_number": "",
  "full_text": "",
  "fields": [
    {{
      "rect_id": 0,
      "_type": "Tickbox",
      "full_text": "Option label",
      "summary": "Short label",
      "column_title": "Column heading",
      "name": "Column heading"
    }}
  ],
  "warnings": []
}}
"""
