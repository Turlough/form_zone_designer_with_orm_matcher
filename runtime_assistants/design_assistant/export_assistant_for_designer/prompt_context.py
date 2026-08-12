"""Format export column slices for Analyse / Grid VLM prompts."""

from __future__ import annotations


def format_export_columns_block(export_columns: list[dict]) -> str:
    if not export_columns:
        return ""
    lines = [
        "Customer export format columns for this page (prefer these for column_title and option labels):"
    ]
    for col in export_columns:
        delivery = col.get("delivery_title") or col.get("header") or ""
        lines.append(
            f"  - {col.get('id', '?')}: kind={col.get('kind', '?')}, "
            f"header={col.get('header', '')!r}, subheader={col.get('subheader', '')!r}, "
            f"delivery_title={delivery!r}"
        )
    lines.append(
        "Rules when export columns are listed:\n"
        "- Prefer delivery_title (or header/subheader) for column_title and name.\n"
        "- Radio option labels: use full printed answer text verbatim.\n"
        "- If no export column matches a form question, use full printed text verbatim.\n"
        "- Do not change tickbox checked_value (stays Ticked during indexing)."
    )
    return "\n".join(lines)
