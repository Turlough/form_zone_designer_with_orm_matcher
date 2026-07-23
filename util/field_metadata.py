"""Helpers for optional field metadata (summary, column_title, full_text).

Backward compatible: when new keys are absent, fall back to ``name``.
"""

from __future__ import annotations

from typing import Any

SUMMARY_MAX_LEN = 50

# Keys that must never be persisted in page JSON
ANALYSIS_ONLY_KEYS = frozenset(
    {
        "answer_located",
        "confidence",
        "rect_id",
        "rect_ids",
        "page_x",
        "page_y",
        "page_width",
        "page_height",
        "grid_suggestion",
    }
)


def display_label(field: Any, max_len: int = SUMMARY_MAX_LEN) -> str:
    """Label for Designer overlay when Field names is enabled."""
    summary = (getattr(field, "summary", None) or "").strip()
    name = (getattr(field, "name", None) or "").strip()
    text = summary or name
    if max_len > 0 and len(text) > max_len:
        return text[:max_len]
    return text


def column_header(field: Any) -> str:
    """CSV column heading for a field."""
    title = (getattr(field, "column_title", None) or "").strip()
    name = (getattr(field, "name", None) or "").strip()
    return title or name


def full_question_text(field: Any) -> str:
    """Full question text, with fallbacks."""
    full = (getattr(field, "full_text", None) or "").strip()
    if full:
        return full
    summary = (getattr(field, "summary", None) or "").strip()
    if summary:
        return summary
    return (getattr(field, "name", None) or "").strip()


def sanitize_column_title(text: str) -> str:
    """Produce a CSV-safe column title from free text."""
    cleaned = " ".join((text or "").strip().split())
    return cleaned[:80] if cleaned else "field"


def truncate_summary(text: str, max_len: int = SUMMARY_MAX_LEN) -> str:
    cleaned = " ".join((text or "").strip().split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def strip_analysis_keys(data: dict) -> dict:
    """Return a shallow copy without analysis-only keys."""
    return {k: v for k, v in data.items() if k not in ANALYSIS_ONLY_KEYS}


def upgrade_field_dict(data: dict) -> dict:
    """Normalise metadata keys on a field dict (and nested radio_buttons).

    Ensures ``name``, ``summary``, and ``column_title`` are consistent for
    new/analysed fields while preserving existing ``name`` when present.
    """
    d = strip_analysis_keys(dict(data))
    name = (d.get("name") or "").strip()
    summary = (d.get("summary") or "").strip()
    column_title = (d.get("column_title") or "").strip()
    full_text = (d.get("full_text") or "").strip()

    if summary:
        summary = truncate_summary(summary)
    elif name:
        summary = truncate_summary(name)

    if not column_title:
        column_title = sanitize_column_title(name or summary or "field")
    else:
        column_title = sanitize_column_title(column_title)

    if not name:
        name = column_title

    d["name"] = name
    d["summary"] = summary
    d["column_title"] = column_title
    if full_text:
        d["full_text"] = full_text
    elif "full_text" in d and not full_text:
        d.pop("full_text", None)

    if "radio_buttons" in d and isinstance(d["radio_buttons"], list):
        d["radio_buttons"] = [
            upgrade_field_dict(rb) if isinstance(rb, dict) else rb
            for rb in d["radio_buttons"]
        ]
    return d
