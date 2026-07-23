"""Prompt builders for the design-assistant VLM."""

from __future__ import annotations

from fields import FIELD_TYPE_MAP

ALLOWED_TYPES = sorted(FIELD_TYPE_MAP.keys())

PROMPT_VERSION = "1"

SYSTEM_INSTRUCTIONS = """You analyse blank scanned form templates for a form-indexing application.
Respond with JSON only (no markdown fences, no commentary).
You identify questions and answer-control locations so operators can define capture zones.
"""


def build_user_prompt(
    *,
    page_number: int,
    image_width: int,
    image_height: int,
    fiducial_top_left: tuple[int, int] | None,
    candidate_rects: list[tuple[int, int, int, int]],
) -> str:
    """Build the user text prompt sent with the page image."""
    fiducial_line = (
        f"Fiducial top-left (page-absolute pixels): {fiducial_top_left[0]}, {fiducial_top_left[1]}."
        if fiducial_top_left
        else "No fiducial on this page."
    )
    rect_lines = []
    for i, (x, y, w, h) in enumerate(candidate_rects):
        rect_lines.append(f"  {i}: [{x}, {y}, {w}, {h}]")
    rects_block = "\n".join(rect_lines) if rect_lines else "  (none detected)"

    types_csv = ", ".join(ALLOWED_TYPES)

    return f"""Analyse this blank form template page and return JSON matching the schema below.

Page number (1-based): {page_number}
Image size (page-absolute pixels): width={image_width}, height={image_height}
{fiducial_line}

Candidate answer rectangles from local computer vision (page-absolute [x, y, width, height]).
Prefer referencing these by rect_id for answer geometry instead of inventing pixel boxes:
{rects_block}

Allowed field _type values: {types_csv}

Rules:
1. Enumerate every question / answer control that should be captured.
2. For each field set:
   - full_text: full question or option text from the form
   - summary: short label, max 50 characters (shown on the design overlay)
   - column_title: CSV column heading (plain text, no commas if avoidable)
   - name: same as column_title for new fields (legacy key)
   - _type: one of the allowed types
   - answer_located: true if you found an answer control, else false
   - rect_id: integer index into the candidate list when the answer matches a CV rectangle
   - For RadioGroup / NumericRadioGroup: include radio_buttons array; each button may use its own rect_id
   - If no rect_id fits, you may set page_x, page_y, page_width, page_height (page-absolute) as a coarse hint
3. Discrimination:
   - Independent squares → Tickbox
   - Mutually exclusive options in a row/column → RadioGroup with nested radio_buttons
   - Blank boxes for handwriting/numbers → TextField / IntegerField / DecimalField / DateField as appropriate
4. If a question has no visible answer control, still emit metadata with answer_located=false and omit geometry.
5. If a regular matrix of identical controls is a good fit for grid layout, add a grid_suggestions entry
   (orientation "horizontal" or "vertical", n_rows, n_cols, page-absolute bbox, short label). Do not expand huge matrices into dozens of fields when a grid suggestion is better.
6. Naming: prefer a short section prefix when visible (e.g. "22. Full Time").

Return JSON object:
{{
  "schema_version": 1,
  "page_number": {page_number},
  "coordinate_system": "page_absolute",
  "fields": [
    {{
      "_type": "Tickbox",
      "full_text": "...",
      "summary": "...",
      "column_title": "...",
      "name": "...",
      "answer_located": true,
      "rect_id": 0
    }}
  ],
  "warnings": ["optional human-readable warnings"],
  "grid_suggestions": [
    {{
      "orientation": "horizontal",
      "n_rows": 2,
      "n_cols": 5,
      "x": 0,
      "y": 0,
      "width": 100,
      "height": 50,
      "label": "optional"
    }}
  ]
}}
"""
