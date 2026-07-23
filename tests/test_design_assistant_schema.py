"""Schema upgrade / persistence helpers for design assistant (no live API)."""

from fields import Field, Tickbox, RadioGroup, RadioButton
from util.field_metadata import (
    display_label,
    column_header,
    upgrade_field_dict,
    strip_analysis_keys,
)
from runtime_assistants.design_assistant.schema import (
    parse_vlm_response,
    validate_and_upgrade,
    fields_for_persistence,
    prepare_field_for_persistence,
)


def test_old_json_round_trip():
    old = {
        "_type": "Tickbox",
        "colour": [255, 0, 0],
        "name": "22. Consent",
        "x": 10,
        "y": 20,
        "width": 15,
        "height": 15,
        "checked_value": "Ticked",
    }
    field = Field.from_dict(dict(old))
    assert isinstance(field, Tickbox)
    assert field.name == "22. Consent"
    assert field.summary == ""
    assert display_label(field) == "22. Consent"
    assert column_header(field) == "22. Consent"
    out = field.to_dict()
    assert out["name"] == "22. Consent"
    assert "summary" not in out or not out.get("summary")


def test_upgrade_field_dict_fills_metadata():
    upgraded = upgrade_field_dict(
        {
            "_type": "TextField",
            "full_text": "What is your herd number?",
            "summary": "Herd number question that is way too long for the overlay label",
            "column_title": "Herd Number",
        }
    )
    assert upgraded["name"] == "Herd Number"
    assert upgraded["column_title"] == "Herd Number"
    assert len(upgraded["summary"]) <= 50
    assert "answer_located" not in upgraded


def test_strip_analysis_keys():
    d = strip_analysis_keys(
        {"name": "a", "rect_id": 3, "answer_located": True, "x": 1}
    )
    assert d == {"name": "a", "x": 1}


def test_parse_vlm_response_with_fence():
    text = """```json
{"schema_version": 1, "fields": [], "warnings": [], "grid_suggestions": []}
```"""
    data = parse_vlm_response(text)
    assert data["schema_version"] == 1
    assert data["fields"] == []


def test_validate_and_upgrade_and_persist():
    raw = {
        "schema_version": 1,
        "fields": [
            {
                "_type": "Tickbox",
                "full_text": "I agree",
                "summary": "Agree",
                "column_title": "Agree",
                "name": "Agree",
                "answer_located": True,
                "rect_id": 0,
                "x": 5,
                "y": 6,
                "width": 12,
                "height": 12,
            }
        ],
        "warnings": ["note"],
        "grid_suggestions": [{"n_rows": 2, "n_cols": 3, "x": 0, "y": 0, "width": 10, "height": 10}],
    }
    result = validate_and_upgrade(raw)
    assert len(result.fields) == 1
    assert result.warnings == ["note"]
    assert len(result.grid_suggestions) == 1

    persistable = fields_for_persistence(result.fields)
    assert len(persistable) == 1
    assert "rect_id" not in persistable[0]
    assert "answer_located" not in persistable[0]
    field = Field.from_dict(dict(persistable[0]))
    assert field.summary == "Agree"
    assert field.column_title == "Agree"


def test_prepare_radio_group():
    d = prepare_field_for_persistence(
        {
            "_type": "RadioGroup",
            "name": "Season",
            "summary": "Season",
            "column_title": "Season",
            "x": 0,
            "y": 0,
            "width": 100,
            "height": 40,
            "radio_buttons": [
                {
                    "_type": "RadioButton",
                    "name": "Spring",
                    "x": 0,
                    "y": 0,
                    "width": 10,
                    "height": 10,
                    "rect_id": 1,
                }
            ],
        }
    )
    assert d["_type"] == "RadioGroup"
    assert len(d["radio_buttons"]) == 1
    assert "rect_id" not in d["radio_buttons"][0]
    obj = Field.from_dict(dict(d))
    assert isinstance(obj, RadioGroup)
    assert isinstance(obj.radio_buttons[0], RadioButton)
