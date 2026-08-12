"""AI enrichment of export format descriptors (page_hint assignment)."""

from __future__ import annotations

import json
import logging
import os

from runtime_assistants.design_assistant.export_assistant_for_designer.schema import (
    ExportFormatDescriptor,
    KIND_META,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"


def get_api_key() -> str:
    return (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()


def get_model_name() -> str:
    return (os.getenv("DESIGN_ASSISTANT_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _build_enrich_prompt(descriptor: ExportFormatDescriptor, page_count: int) -> str:
    lines = []
    for col in descriptor.columns:
        if col.kind == KIND_META:
            continue
        lines.append(
            f"- {col.id}: header={col.header!r}, subheader={col.subheader!r}, kind={col.kind}"
        )
    column_block = "\n".join(lines) if lines else "(none)"

    return f"""Assign a 1-based page_hint to each export column id for a {page_count}-page scanned survey form.
Use question wording and typical survey flow. Every non-meta column must get a page_hint between 1 and {page_count}.
Return JSON only:

{{
  "schema_version": 1,
  "page_hints": {{
    "col_001": 1
  }},
  "warnings": []
}}

Columns:
{column_block}
"""


def _parse_enrich_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Enrich response must be a JSON object")
    return data


def enrich_page_hints(
    descriptor: ExportFormatDescriptor,
    *,
    page_count: int,
    model: str | None = None,
) -> ExportFormatDescriptor:
    """Assign page_hint on each non-meta column via external VLM (text-only)."""
    if page_count < 1:
        page_count = 1

    api_key = get_api_key()
    if not api_key:
        logger.warning("No API key; using heuristic page_hint assignment")
        return _heuristic_page_hints(descriptor, page_count)

    try:
        from google import genai
    except ImportError as e:
        logger.warning("google-genai not installed; using heuristic page_hint assignment")
        return _heuristic_page_hints(descriptor, page_count)

    model_name = model or get_model_name()
    prompt = _build_enrich_prompt(descriptor, page_count)
    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(model=model_name, contents=[prompt])
        text = (getattr(response, "text", "") or "").strip()
        parsed = _parse_enrich_response(text)
        hints = parsed.get("page_hints") or {}
        extra_warnings = list(parsed.get("warnings") or [])
        for col in descriptor.columns:
            if col.kind == KIND_META:
                continue
            hint = hints.get(col.id)
            if hint is not None:
                try:
                    col.page_hint = max(1, min(page_count, int(hint)))
                except (TypeError, ValueError):
                    pass
        for grp in descriptor.groups:
            cols = [descriptor.column_by_id(cid) for cid in grp.column_ids]
            pages = {c.page_hint for c in cols if c and c.page_hint}
            if len(pages) == 1:
                grp.page_hint = next(iter(pages))
        descriptor.warnings_from_ingest.extend(str(w) for w in extra_warnings)
        return descriptor
    except Exception as e:
        logger.warning("Export format enrich failed (%s); using heuristic assignment", e)
        return _heuristic_page_hints(descriptor, page_count)
    finally:
        client.close()


def _heuristic_page_hints(
    descriptor: ExportFormatDescriptor,
    page_count: int,
) -> ExportFormatDescriptor:
    """Evenly distribute non-meta columns across pages when AI is unavailable."""
    data_cols = [c for c in descriptor.columns if c.kind != KIND_META]
    if not data_cols:
        return descriptor
    n = len(data_cols)
    for i, col in enumerate(data_cols):
        page = min(page_count, max(1, int((i * page_count) / n) + 1))
        col.page_hint = page
    for grp in descriptor.groups:
        cols = [descriptor.column_by_id(cid) for cid in grp.column_ids]
        pages = {c.page_hint for c in cols if c and c.page_hint}
        if len(pages) == 1:
            grp.page_hint = next(iter(pages))
    descriptor.warnings_from_ingest.append(
        "page_hint assigned heuristically (AI enrich unavailable or failed)"
    )
    return descriptor
