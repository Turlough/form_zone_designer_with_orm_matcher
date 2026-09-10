"""Check Designer page fields against an export format descriptor."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from fields import Field, RadioGroup, RadioGrid, Tickbox
from util.field_metadata import export_column_id_of, export_display_title, full_question_text

from runtime_assistants.design_assistant.export_assistant_for_designer.schema import (
    ExportColumn,
    ExportFormatDescriptor,
    KIND_META,
    KIND_MULTI_SELECT_OPTION,
    KIND_OPEN_TEXT,
    KIND_SINGLE_CHOICE,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
MATCH_THRESHOLD = 0.72


@dataclass
class FieldExportProposal:
    """Proposed metadata update for one field (or nested radio button)."""

    field_index: int
    radio_index: int | None = None
    export_column_id: str = ""
    column_title: str = ""
    name: str = ""
    full_text: str = ""
    summary: str = ""
    reason: str = ""


@dataclass
class ExportCheckResult:
    page_number: int
    proposals: list[FieldExportProposal] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    matched_count: int = 0
    model: str = ""


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().split()).casefold()


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _expected_column_title(col: ExportColumn) -> str:
    return col.delivery_title()


def _field_targets(fields: list[Field]) -> list[tuple[int, int | None, Field]]:
    """Flatten page fields to checkable units (field_index, radio_index, field_obj)."""
    targets: list[tuple[int, int | None, Field]] = []
    for i, f in enumerate(fields):
        if isinstance(f, RadioGrid):
            targets.append((i, None, f))
            continue
        if isinstance(f, RadioGroup):
            targets.append((i, None, f))
            for j, rb in enumerate(f.radio_buttons):
                targets.append((i, j, rb))
            continue
        if isinstance(f, Tickbox):
            targets.append((i, None, f))
            continue
        if type(f) is not Field:
            targets.append((i, None, f))
    return targets


def _linked_column(
    field_obj: Field,
    descriptor: ExportFormatDescriptor,
) -> ExportColumn | None:
    col_id = export_column_id_of(field_obj)
    if not col_id:
        return None
    return descriptor.column_by_id(col_id)


def _best_column_match(
    field_obj: Field,
    candidates: list[ExportColumn],
    *,
    used_ids: set[str],
) -> ExportColumn | None:
    title = export_display_title(field_obj)
    full = full_question_text(field_obj)
    best: ExportColumn | None = None
    best_score = 0.0
    for col in candidates:
        if col.id in used_ids:
            continue
        expected = _expected_column_title(col)
        score = max(
            _similarity(title, expected),
            _similarity(full, col.header),
            _similarity(full, expected),
            _similarity(title, col.header),
        )
        if col.kind == KIND_MULTI_SELECT_OPTION and isinstance(field_obj, Tickbox):
            score = max(score, _similarity(title, col.subheader), _similarity(full, col.subheader))
        if score > best_score:
            best_score = score
            best = col
    if best and best_score >= MATCH_THRESHOLD:
        return best
    return None


def _proposal_for_field(
    field_index: int,
    radio_index: int | None,
    field_obj: Field,
    col: ExportColumn,
    *,
    reason: str,
) -> FieldExportProposal:
    expected = _expected_column_title(col)
    full = full_question_text(field_obj) or expected
    return FieldExportProposal(
        field_index=field_index,
        radio_index=radio_index,
        export_column_id=col.id,
        column_title=expected,
        name=expected if radio_index is not None else (field_obj.name or expected),
        full_text=full,
        summary=field_obj.summary or "",
        reason=reason,
    )


def check_page_export_format(
    fields: list[Field],
    descriptor: ExportFormatDescriptor,
    *,
    page_number: int,
    page_image=None,
    use_vlm: bool = True,
    model: str | None = None,
) -> ExportCheckResult:
    """Compare page fields to export columns for the given 1-based page_number."""
    page_cols = descriptor.columns_for_page(page_number)
    data_cols = [c for c in page_cols if c.kind != KIND_META]
    result = ExportCheckResult(page_number=page_number)

    if not data_cols:
        result.warnings.append(
            f"No export columns with page_hint={page_number} in active export format."
        )
        return result

    used_col_ids: set[str] = set()
    matched_field_keys: set[tuple[int, int | None]] = set()

    # Pass 1: stable links via export_column_id
    for field_index, radio_index, field_obj in _field_targets(fields):
        col = _linked_column(field_obj, descriptor)
        if col is None:
            continue
        if col.page_hint != page_number and col.kind != KIND_META:
            result.warnings.append(
                f"Field {export_display_title(field_obj)!r} links to {col.id} "
                f"(page_hint={col.page_hint}, expected {page_number})."
            )
        expected = _expected_column_title(col)
        current = export_display_title(field_obj)
        if _normalize(current) != _normalize(expected):
            result.proposals.append(
                _proposal_for_field(
                    field_index,
                    radio_index,
                    field_obj,
                    col,
                    reason=f"Linked column text mismatch: {current!r} → {expected!r}",
                )
            )
        else:
            result.matched_count += 1
        used_col_ids.add(col.id)
        matched_field_keys.add((field_index, radio_index))

    # Pass 2: fuzzy match unmatched fields
    remaining_cols = [c for c in data_cols if c.id not in used_col_ids]
    for field_index, radio_index, field_obj in _field_targets(fields):
        key = (field_index, radio_index)
        if key in matched_field_keys:
            continue
        if isinstance(field_obj, RadioGrid):
            continue
        if radio_index is None and isinstance(field_obj, RadioGroup):
            continue

        col = _best_column_match(field_obj, remaining_cols, used_ids=used_col_ids)
        if col:
            result.proposals.append(
                _proposal_for_field(
                    field_index,
                    radio_index,
                    field_obj,
                    col,
                    reason="Fuzzy match to export column (Apply to store export_column_id)",
                )
            )
            used_col_ids.add(col.id)
            matched_field_keys.add(key)
        else:
            full = full_question_text(field_obj)
            if full:
                result.warnings.append(
                    f"Form field {export_display_title(field_obj)!r} has no export column match; "
                    f"default to full text verbatim for delivery heading."
                )
                result.proposals.append(
                    FieldExportProposal(
                        field_index=field_index,
                        radio_index=radio_index,
                        export_column_id="",
                        column_title=full,
                        name=field_obj.name or full,
                        full_text=full,
                        summary=field_obj.summary or "",
                        reason="No export column; propose full text verbatim",
                    )
                )

    # Pass 3: export columns on page with no field
    for col in data_cols:
        if col.id not in used_col_ids:
            result.warnings.append(
                f"Export column {col.id} ({_expected_column_title(col)!r}) "
                f"has no matching form field on page {page_number}."
            )

    # Optional VLM refinement for remaining ambiguous proposals
    if use_vlm and page_image is not None and result.proposals:
        vlm_proposals = _vlm_refine_matches(
            fields,
            descriptor,
            page_number=page_number,
            page_image=page_image,
            existing=result.proposals,
            model=model,
        )
        if vlm_proposals:
            result.proposals = vlm_proposals
            result.model = model or os.getenv("DESIGN_ASSISTANT_MODEL") or DEFAULT_MODEL

    return result


def _vlm_refine_matches(
    fields: list[Field],
    descriptor: ExportFormatDescriptor,
    *,
    page_number: int,
    page_image,
    existing: list[FieldExportProposal],
    model: str | None,
) -> list[FieldExportProposal]:
    api_key = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return existing

    try:
        import io

        from google import genai
        from runtime_assistants.design_assistant.client import downscale_for_upload
    except ImportError:
        return existing

    def _image_to_jpeg_bytes(image) -> bytes:
        buf = io.BytesIO()
        rgb = image.convert("RGB")
        rgb.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue()

    page_cols = descriptor.columns_for_page(page_number)
    col_lines = [
        f"- {c.id}: header={c.header!r}, subheader={c.subheader!r}, kind={c.kind}"
        for c in page_cols
        if c.kind != KIND_META
    ]
    field_lines = []
    for i, f in enumerate(fields):
        if isinstance(f, RadioGroup):
            field_lines.append(
                f"- field[{i}] RadioGroup: {full_question_text(f)!r} "
                f"options={[rb.name for rb in f.radio_buttons]}"
            )
        elif type(f) is not Field:
            field_lines.append(
                f"- field[{i}] {type(f).__name__}: {full_question_text(f)!r}"
            )

    prompt = f"""Match form fields on page {page_number} to export column ids.
Use full printed text verbatim for radio option labels and column_title.
Do not change checked_value. Return JSON only:

{{
  "schema_version": 1,
  "matches": [
    {{"field_index": 0, "radio_index": null, "export_column_id": "col_001", "column_title": "...", "full_text": "..."}}
  ],
  "warnings": []
}}

Export columns:
{chr(10).join(col_lines)}

Form fields:
{chr(10).join(field_lines)}
"""
    model_name = (model or os.getenv("DESIGN_ASSISTANT_MODEL") or DEFAULT_MODEL).strip()
    upload_img, _ = downscale_for_upload(page_image)
    image_bytes = _image_to_jpeg_bytes(upload_img)
    client = genai.Client(api_key=api_key)
    try:
        from google.genai import types

        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        response = client.models.generate_content(
            model=model_name,
            contents=[image_part, prompt],
        )
        text = (getattr(response, "text", "") or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        data = json.loads(text)
        matches = data.get("matches") or []
        refined: list[FieldExportProposal] = []
        for m in matches:
            try:
                fi = int(m.get("field_index"))
            except (TypeError, ValueError):
                continue
            ri = m.get("radio_index")
            radio_index = int(ri) if ri is not None else None
            col_id = str(m.get("export_column_id") or "")
            col = descriptor.column_by_id(col_id) if col_id else None
            title = str(m.get("column_title") or "")
            if col and not title:
                title = _expected_column_title(col)
            full = str(m.get("full_text") or "")
            if not full and fi < len(fields):
                full = full_question_text(fields[fi])
            refined.append(
                FieldExportProposal(
                    field_index=fi,
                    radio_index=radio_index,
                    export_column_id=col_id,
                    column_title=title,
                    name=title,
                    full_text=full,
                    reason="VLM match",
                )
            )
        return refined or existing
    except Exception as e:
        logger.warning("Export check VLM refine failed: %s", e)
        return existing
    finally:
        client.close()


def apply_export_proposals(fields: list[Field], proposals: list[FieldExportProposal]) -> list[Field]:
    """Apply metadata proposals. Top-level ``name`` is not changed (identity key)."""
    updated = list(fields)
    for prop in proposals:
        if prop.field_index < 0 or prop.field_index >= len(updated):
            continue
        target = updated[prop.field_index]
        if prop.radio_index is not None and isinstance(target, RadioGroup):
            if prop.radio_index < 0 or prop.radio_index >= len(target.radio_buttons):
                continue
            rb = target.radio_buttons[prop.radio_index]
            if prop.column_title:
                rb.column_title = prop.column_title
            if prop.name:
                rb.name = prop.name
            if prop.full_text:
                rb.full_text = prop.full_text
            if prop.export_column_id:
                rb.export_column_id = prop.export_column_id
            continue

        if prop.column_title:
            target.column_title = prop.column_title
        # field.name is the project-wide identity key; Check/Apply must not overwrite it.
        if prop.full_text:
            target.full_text = prop.full_text
        if prop.summary:
            target.summary = prop.summary
        if prop.export_column_id:
            target.export_column_id = prop.export_column_id
    return updated


def export_columns_for_prompt(descriptor: ExportFormatDescriptor, page_number: int) -> list[dict]:
    """Slice of export columns for Analyse / Grid prompts."""
    out = []
    for col in descriptor.columns_for_page(page_number):
        if col.kind == KIND_META:
            continue
        out.append(
            {
                "id": col.id,
                "header": col.header,
                "subheader": col.subheader,
                "kind": col.kind,
                "delivery_title": col.delivery_title(),
            }
        )
    return out
