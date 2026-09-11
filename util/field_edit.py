"""Apply Designer field-editor config onto an existing field, preserving JSON keys."""

from __future__ import annotations

from dataclasses import fields as dc_fields

from fields import FIELD_TYPE_MAP, Field, Tickbox
from util.field_geometry_edit import MIN_FIELD_SIZE
from util.field_metadata import sanitize_column_title, truncate_summary

METADATA_KEYS = (
    "summary",
    "column_title",
    "full_text",
    "question_number",
    "export_column_id",
    "checked_value",
)


def format_geometry(x: int, y: int, width: int, height: int) -> str:
    return f"{int(x)}, {int(y)}, {int(width)}, {int(height)}"


def parse_geometry(text: str) -> tuple[int, int, int, int] | None:
    """Parse ``x, y, width, height`` (commas or semicolons). None if invalid."""
    parts = [p.strip() for p in (text or "").replace(";", ",").split(",") if p.strip()]
    if len(parts) != 4:
        return None
    try:
        x, y, width, height = (int(p) for p in parts)
    except ValueError:
        return None
    if width < MIN_FIELD_SIZE or height < MIN_FIELD_SIZE:
        return None
    return x, y, width, height


def type_has_checked_value(type_name: str) -> bool:
    field_class = FIELD_TYPE_MAP.get(type_name)
    return field_class is not None and issubclass(field_class, Tickbox)


def apply_field_edit(old_field: Field, config: dict) -> Field:
    """Rebuild ``old_field`` from editor config without dropping unspecified JSON keys.

    ``colour`` is never taken from config or stored JSON; ``Field.from_dict`` applies
    the canonical type colour. Nested ``radio_buttons`` are kept when the result
    type is still a RadioGroup.
    """
    data = old_field.to_dict()
    new_type = config.get("field_type") or data.get("_type")
    data["_type"] = new_type

    if "field_name" in config:
        data["name"] = (config.get("field_name") or "").strip() or data.get("name")

    if all(k in config for k in ("x", "y", "width", "height")):
        data["x"] = int(config["x"])
        data["y"] = int(config["y"])
        data["width"] = int(config["width"])
        data["height"] = int(config["height"])

    for key in METADATA_KEYS:
        if key not in config:
            continue
        value = config.get(key)
        if isinstance(value, str):
            value = value.strip()
        if key == "summary" and value:
            value = truncate_summary(value)
        if key == "column_title" and value:
            value = sanitize_column_title(value)
        if value:
            data[key] = value
        else:
            data.pop(key, None)

    data.pop("colour", None)

    field_class = FIELD_TYPE_MAP.get(new_type)
    if field_class is None:
        raise ValueError(f"Invalid field type: {new_type}")

    allowed = {f.name for f in dc_fields(field_class)} | {"_type"}
    filtered = {k: v for k, v in data.items() if k in allowed}
    return Field.from_dict(filtered)
