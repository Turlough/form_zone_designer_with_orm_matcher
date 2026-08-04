"""Field overlay theming via field_factory."""

from fields import Field, Tickbox, IntegerField, RadioGroup, RadioButton, RadioGrid
from field_factory import (
    default_colour_tuple_for_type,
    get_field_display_color,
)


def test_get_field_display_color_uses_type_map_not_json():
    tick = Tickbox(name="t", x=0, y=0, width=10, height=10, colour=(255, 0, 0))
    color = get_field_display_color(tick)
    assert (color.red(), color.green(), color.blue()) == (50, 255, 0)

    integer = IntegerField(name="n", x=0, y=0, width=10, height=10, colour=(0, 150, 150))
    color = get_field_display_color(integer)
    assert (color.red(), color.green(), color.blue()) == (0, 100, 200)


def test_default_colour_tuple_matches_display_map():
    for type_name in ("Tickbox", "TextField", "RadioGroup", "RadioGrid", "IntegerField"):
        rgb = default_colour_tuple_for_type(type_name)
        field = Field.from_dict(
            {
                "_type": type_name,
                "name": "x",
                "x": 0,
                "y": 0,
                "width": 10,
                "height": 10,
                "colour": list(rgb),
                **({"radio_buttons": []} if type_name == "RadioGroup" else {}),
                **(
                    {
                        "orientation": "horizontal",
                        "row_labels": ["a"],
                        "col_labels": ["b"],
                        "grid_id": "g",
                    }
                    if type_name == "RadioGrid"
                    else {}
                ),
            }
        )
        if type_name == "RadioGrid":
            assert isinstance(field, RadioGrid)
        display = get_field_display_color(field)
        assert (display.red(), display.green(), display.blue()) == rgb


def test_from_dict_ignores_stale_json_colour():
    field = Field.from_dict(
        {
            "_type": "IntegerField",
            "colour": [255, 0, 0],
            "name": "count",
            "x": 0,
            "y": 0,
            "width": 10,
            "height": 10,
        }
    )
    assert field.colour == default_colour_tuple_for_type("IntegerField")


def test_to_dict_writes_canonical_colour():
    tick = Tickbox(name="t", x=0, y=0, width=10, height=10, colour=(255, 0, 0))
    assert tick.to_dict()["colour"] == default_colour_tuple_for_type("Tickbox")


def test_radio_button_display_color():
    rb = RadioButton(name="a", x=0, y=0, width=10, height=10, colour=(255, 0, 0))
    color = get_field_display_color(rb)
    assert (color.red(), color.green(), color.blue()) == default_colour_tuple_for_type("RadioButton")
