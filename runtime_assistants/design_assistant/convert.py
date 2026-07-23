"""Convert analysis field dicts to Field objects."""

from __future__ import annotations

from fields import Field
from runtime_assistants.design_assistant.schema import fields_for_persistence


def analysis_dicts_to_fields(matched_fields: list[dict]) -> list[Field]:
    """Upgrade matched analysis dicts and instantiate Field subclasses."""
    persistable = fields_for_persistence(matched_fields)
    fields: list[Field] = []
    for d in persistable:
        # Skip fields with no located answer and zero-ish placeholder only if
        # caller filters; here we keep all for preview (user may edit).
        try:
            obj = Field.from_dict(dict(d))
        except (TypeError, ValueError, KeyError):
            continue
        if type(obj) is Field:
            continue
        fields.append(obj)
    return fields
