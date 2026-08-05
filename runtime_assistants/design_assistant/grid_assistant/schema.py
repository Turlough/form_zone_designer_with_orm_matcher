"""Validate Grid Assistant VLM JSON into a structured result."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


@dataclass
class GridAnalysisResult:
    question_number: str = ""
    summary: str = ""
    full_text: str = ""
    orientation_observed: str = ""
    row_labels: list[str] = field(default_factory=list)
    col_labels: list[str] = field(default_factory=list)
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


def _str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        s = str(item).strip() if item is not None else ""
        if s:
            out.append(s)
    return out


def validate_grid_analysis(raw: dict) -> GridAnalysisResult:
    """Validate top-level grid analysis object."""
    if not isinstance(raw, dict):
        raise ValueError("Grid analysis JSON must be an object")

    warnings: list[str] = []
    if isinstance(raw.get("warnings"), list):
        warnings.extend(str(w) for w in raw["warnings"])

    row_labels = _str_list(raw.get("row_labels"))
    col_labels = _str_list(raw.get("col_labels"))
    if not row_labels and not col_labels:
        warnings.append("VLM returned no row_labels or col_labels.")

    orientation = str(raw.get("orientation_observed") or "").strip().lower()
    if orientation and orientation not in ("horizontal", "vertical"):
        warnings.append(f"Ignored invalid orientation_observed: {orientation!r}")
        orientation = ""

    return GridAnalysisResult(
        question_number=str(raw.get("question_number") or "").strip(),
        summary=str(raw.get("summary") or "").strip(),
        full_text=str(raw.get("full_text") or "").strip(),
        orientation_observed=orientation,
        row_labels=row_labels,
        col_labels=col_labels,
        warnings=warnings,
        raw=raw,
    )
