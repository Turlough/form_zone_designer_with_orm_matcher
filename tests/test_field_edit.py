"""Apply Designer field-editor config without dropping page-JSON metadata."""

from fields import RadioButton, RadioGroup, TextField, Tickbox
from util.field_edit import apply_field_edit, format_geometry, parse_geometry, type_has_checked_value
from field_factory import default_colour_tuple_for_type


def _tickbox(**kwargs) -> Tickbox:
    defaults = dict(
        colour=(50, 255, 0),
        name="Q1_4_Relief_Contract_workers_Part_time",
        x=163,
        y=584,
        width=49,
        height=49,
        summary="Q1_4_Relief_Contract_workers_Part_time",
        column_title="Q1_4_Relief_Contract_workers_Part_time",
        full_text="Who do you work with on the farm? (Tick all that apply)",
        question_number="1.4",
        checked_value="Ticked",
    )
    defaults.update(kwargs)
    return Tickbox(**defaults)


def test_format_and_parse_geometry_round_trip():
    text = format_geometry(163, 584, 49, 49)
    assert text == "163, 584, 49, 49"
    assert parse_geometry(text) == (163, 584, 49, 49)
    assert parse_geometry("163,584,49,49") == (163, 584, 49, 49)
    assert parse_geometry("163; 584; 49; 49") == (163, 584, 49, 49)


def test_parse_geometry_rejects_invalid():
    assert parse_geometry("") is None
    assert parse_geometry("163, 584, 49") is None
    assert parse_geometry("a, b, c, d") is None
    assert parse_geometry("163, 584, 5, 49") is None


def test_apply_field_edit_preserves_json_metadata_on_rename():
    old = _tickbox()
    updated = apply_field_edit(
        old,
        {
            "field_type": "Tickbox",
            "field_name": "Q1_4_Relief_renamed",
            "x": 163,
            "y": 584,
            "width": 49,
            "height": 49,
            "summary": old.summary,
            "column_title": old.column_title,
            "full_text": old.full_text,
            "question_number": old.question_number,
            "checked_value": old.checked_value,
        },
    )
    assert isinstance(updated, Tickbox)
    assert updated.name == "Q1_4_Relief_renamed"
    assert updated.full_text == old.full_text
    assert updated.summary == old.summary
    assert updated.column_title == old.column_title
    assert updated.question_number == "1.4"
    assert updated.checked_value == "Ticked"
    out = updated.to_dict()
    assert out["full_text"] == old.full_text
    assert tuple(out["colour"]) == default_colour_tuple_for_type("Tickbox")


def test_apply_field_edit_omits_empty_optional_keys():
    old = _tickbox()
    updated = apply_field_edit(
        old,
        {
            "field_type": "Tickbox",
            "field_name": old.name,
            "x": old.x,
            "y": old.y,
            "width": old.width,
            "height": old.height,
            "summary": "",
            "column_title": "",
            "full_text": "",
            "question_number": "",
            "checked_value": "Ticked",
        },
    )
    out = updated.to_dict()
    assert "full_text" not in out
    assert "summary" not in out
    assert "column_title" not in out
    assert "question_number" not in out


def test_apply_field_edit_type_change_keeps_question_text():
    old = _tickbox()
    updated = apply_field_edit(
        old,
        {
            "field_type": "TextField",
            "field_name": old.name,
            "x": old.x,
            "y": old.y,
            "width": old.width,
            "height": old.height,
            "full_text": old.full_text,
            "question_number": old.question_number,
        },
    )
    assert isinstance(updated, TextField)
    assert updated.full_text == old.full_text
    assert "checked_value" not in updated.to_dict()


def test_apply_field_edit_preserves_radio_group_children():
    buttons = [
        RadioButton(name="a", x=0, y=0, width=20, height=20, colour=(100, 150, 0)),
        RadioButton(name="b", x=20, y=0, width=20, height=20, colour=(100, 150, 0)),
    ]
    group = RadioGroup(
        name="q1",
        x=0,
        y=0,
        width=40,
        height=20,
        colour=(100, 150, 0),
        radio_buttons=buttons,
        full_text="Pick one",
        question_number="1.1",
    )
    updated = apply_field_edit(
        group,
        {
            "field_type": "RadioGroup",
            "field_name": "q1_renamed",
            "x": 0,
            "y": 0,
            "width": 40,
            "height": 20,
            "full_text": "Pick one",
            "question_number": "1.1",
        },
    )
    assert isinstance(updated, RadioGroup)
    assert updated.name == "q1_renamed"
    assert [rb.name for rb in updated.radio_buttons] == ["a", "b"]
    assert updated.full_text == "Pick one"


def test_apply_field_edit_name_only_config_keeps_metadata():
    """Legacy editor config only sent type+name; must not wipe JSON keys."""
    old = _tickbox()
    updated = apply_field_edit(old, {"field_type": "Tickbox", "field_name": "renamed"})
    assert updated.name == "renamed"
    assert updated.full_text == old.full_text
    assert updated.summary == old.summary
    assert updated.column_title == old.column_title
    assert updated.question_number == old.question_number
    assert updated.checked_value == "Ticked"
    assert (updated.x, updated.y, updated.width, updated.height) == (
        old.x,
        old.y,
        old.width,
        old.height,
    )


def test_apply_field_edit_applies_geometry():
    old = _tickbox()
    updated = apply_field_edit(
        old,
        {
            "field_type": "Tickbox",
            "field_name": old.name,
            "x": 10,
            "y": 20,
            "width": 30,
            "height": 40,
            "full_text": old.full_text,
        },
    )
    assert (updated.x, updated.y, updated.width, updated.height) == (10, 20, 30, 40)


def test_type_has_checked_value():
    assert type_has_checked_value("Tickbox")
    assert type_has_checked_value("RadioButton")
    assert type_has_checked_value("SignatureField")
    assert not type_has_checked_value("TextField")
    assert not type_has_checked_value("RadioGroup")
