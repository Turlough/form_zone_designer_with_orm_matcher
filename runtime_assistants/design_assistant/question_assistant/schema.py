"""Validate Question Assistant VLM JSON into structured results."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from fields import FIELD_TYPE_MAP
from util.field_metadata import truncate_summary, upgrade_field_dict

# Types the question assistant may assign (no radio grids / groups).
ALLOWED_FIELD_TYPES = frozenset(
    t
    for t in FIELD_TYPE_MAP
    if t
    not in (
        "RadioGroup",
        "RadioButton",
        "RadioGrid",
        "NumericRadioGroup",
    )
)


@dataclass
class QuestionFieldProposal:
    field_type: str = "Tickbox"
    name: str = ""
    summary: str = ""
    column_title: str = ""
    rect_id: int = 0


@dataclass
class QuestionAnalysisResult:
    question_number: str = ""
    full_text: str = ""
    fields: list[QuestionFieldProposal] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw: dict | None = None


def _extract_json_object(text: str) -> dict:
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("Empty VLM response")

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(cleaned[start : end + 1])

    if not isinstance(data, dict):
        raise ValueError("VLM response JSON must be an object")
    return data


def parse_vlm_response(text: str) -> dict:
    return _extract_json_object(text)


def _normalize_field_type(value: str) -> str:
    t = (value or "").strip()
    if t in ALLOWED_FIELD_TYPES:
        return t
    if t == "Field":
        return "TextField"
    return "Tickbox"


def validate_question_analysis(raw: dict) -> QuestionAnalysisResult:
    if not isinstance(raw, dict):
        raise ValueError("Question analysis JSON must be an object")

    warnings: list[str] = []
    if isinstance(raw.get("warnings"), list):
        warnings.extend(str(w) for w in raw["warnings"])

    proposals: list[QuestionFieldProposal] = []
    items = raw.get("fields")
    if not isinstance(items, list):
        warnings.append("VLM returned no fields array.")
        items = []

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            warnings.append(f"Skipped non-object field entry at index {i}.")
            continue
        upgraded = upgrade_field_dict(dict(item))
        ft = _normalize_field_type(str(item.get("_type") or item.get("field_type") or ""))
        if ft not in ALLOWED_FIELD_TYPES:
            ft = "Tickbox"
        rect_id = item.get("rect_id")
        try:
            rid = int(rect_id) if rect_id is not None else i
        except (TypeError, ValueError):
            rid = i
        proposals.append(
            QuestionFieldProposal(
                field_type=ft,
                name=upgraded.get("name") or upgraded.get("column_title") or f"Option {i + 1}",
                summary=upgraded.get("summary") or truncate_summary(upgraded.get("name") or ""),
                column_title=upgraded.get("column_title") or upgraded.get("name") or "",
                rect_id=rid,
            )
        )

    return QuestionAnalysisResult(
        question_number=str(raw.get("question_number") or "").strip(),
        full_text=str(raw.get("full_text") or "").strip(),
        fields=proposals,
        warnings=warnings,
        raw=raw,
    )


def align_fields_to_rect_count(
    proposals: list[QuestionFieldProposal],
    n_rects: int,
) -> tuple[list[QuestionFieldProposal], list[str]]:
    """Pad or truncate field proposals to match detected rectangle count."""
    warnings: list[str] = []
    if n_rects <= 0:
        return [], warnings

    out = list(proposals)
    if len(out) > n_rects:
        warnings.append(
            f"VLM returned {len(out)} fields but ROI has {n_rects} rectangles; truncating."
        )
        out = out[:n_rects]
    while len(out) < n_rects:
        idx = len(out)
        warnings.append(f"Padding missing field proposal for rectangle {idx}.")
        out.append(
            QuestionFieldProposal(
                field_type="Tickbox",
                name=f"Option {idx + 1}",
                summary=f"Option {idx + 1}",
                column_title=f"Option {idx + 1}",
                rect_id=idx,
            )
        )

    # Re-index rect_id to reading order when counts match
    for i, p in enumerate(out):
        p.rect_id = i
    return out, warnings
