"""Validate and upgrade VLM analysis JSON into persistable field dicts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fields import FIELD_TYPE_MAP
from util.field_metadata import upgrade_field_dict, strip_analysis_keys, ANALYSIS_ONLY_KEYS


@dataclass
class PageAnalysisResult:
    fields: list[dict]
    warnings: list[str] = field(default_factory=list)
    grid_suggestions: list[dict] = field(default_factory=list)
    raw: dict | None = None


def _extract_json_object(text: str) -> dict:
    """Parse JSON from model text, tolerating optional markdown fences."""
    import json
    import re

    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("Empty VLM response")

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Attempt to find first { ... } block
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


def _normalise_field_type(field_dict: dict) -> dict:
    t = field_dict.get("_type") or field_dict.get("type")
    if not t:
        field_dict["_type"] = "TextField"
        return field_dict
    t = str(t)
    # Common aliases from prompts
    aliases = {
        "checkbox": "Tickbox",
        "tickbox": "Tickbox",
        "radio": "RadioButton",
        "radiobutton": "RadioButton",
        "radiogroup": "RadioGroup",
        "text": "TextField",
        "textarea": "TextField",
        "number": "IntegerField",
        "integer": "IntegerField",
    }
    key = t if t in FIELD_TYPE_MAP else aliases.get(t.lower(), t)
    if key not in FIELD_TYPE_MAP:
        key = "TextField"
    field_dict["_type"] = key
    field_dict.pop("type", None)
    return field_dict


def _default_colour_for_type(type_name: str) -> tuple[int, int, int]:
    colours = {
        "Tickbox": (255, 0, 0),
        "SignatureField": (0, 150, 150),
        "RadioButton": (100, 150, 0),
        "RadioGroup": (100, 150, 0),
        "NumericRadioGroup": (0, 150, 150),
        "TextField": (0, 150, 150),
        "IntegerField": (0, 100, 200),
        "DecimalField": (0, 100, 200),
        "DateField": (0, 100, 250),
        "EmailField": (0, 150, 150),
        "IrishMobileField": (0, 150, 150),
        "EircodeField": (0, 150, 150),
    }
    return colours.get(type_name, (255, 0, 0))


def prepare_field_for_persistence(field_dict: dict) -> dict:
    """Strip analysis keys, upgrade metadata, ensure colour and geometry ints."""
    d = _normalise_field_type(dict(field_dict))
    d = upgrade_field_dict(d)
    type_name = d["_type"]
    if "colour" not in d:
        d["colour"] = list(_default_colour_for_type(type_name))
    for key in ("x", "y", "width", "height"):
        if key in d and d[key] is not None:
            try:
                d[key] = int(d[key])
            except (TypeError, ValueError):
                d[key] = 0
    # Ensure required geometry exists for Field.from_dict
    d.setdefault("x", 0)
    d.setdefault("y", 0)
    d.setdefault("width", 10)
    d.setdefault("height", 10)

    if type_name in ("RadioGroup", "NumericRadioGroup"):
        rbs = d.get("radio_buttons") or []
        prepared = []
        for rb in rbs:
            if not isinstance(rb, dict):
                continue
            rb2 = prepare_field_for_persistence(rb)
            rb2["_type"] = "RadioButton"
            prepared.append(rb2)
        d["radio_buttons"] = prepared
    return d


def validate_and_upgrade(raw: dict) -> PageAnalysisResult:
    """Validate top-level analysis object and return persistable fields + extras."""
    warnings: list[str] = []
    if isinstance(raw.get("warnings"), list):
        warnings.extend(str(w) for w in raw["warnings"])

    fields_in = raw.get("fields")
    if fields_in is None:
        raise ValueError("Analysis JSON missing 'fields'")
    if not isinstance(fields_in, list):
        raise ValueError("'fields' must be a list")

    fields_out: list[dict] = []
    for i, item in enumerate(fields_in):
        if not isinstance(item, dict):
            warnings.append(f"Skipped non-object field at index {i}")
            continue
        # Keep analysis keys on a copy for the matcher; persistence prep is later
        fields_out.append(dict(item))

    grids = raw.get("grid_suggestions") or []
    if not isinstance(grids, list):
        grids = []
        warnings.append("Ignored invalid grid_suggestions")
    grid_out = [g for g in grids if isinstance(g, dict)]

    return PageAnalysisResult(
        fields=fields_out,
        warnings=warnings,
        grid_suggestions=grid_out,
        raw=raw,
    )


def fields_for_persistence(matched_fields: list[dict]) -> list[dict]:
    """Final persistable dicts (no analysis-only keys)."""
    out = []
    for f in matched_fields:
        prepared = prepare_field_for_persistence(f)
        # Double-check analysis keys gone
        cleaned = strip_analysis_keys(prepared)
        for k in list(cleaned.keys()):
            if k in ANALYSIS_ONLY_KEYS:
                cleaned.pop(k, None)
        out.append(cleaned)
    return out
