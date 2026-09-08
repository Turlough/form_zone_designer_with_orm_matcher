from fields import Field
from fields import Tickbox
from fields import SignatureField
from fields import RadioButton
from fields import RadioGroup
from fields import RadioGrid
from fields import TextField
from fields import IntegerField
from fields import DecimalField
from fields import NumericRadioGroup
from fields import DateField
from fields import EmailField
from fields import IrishMobileField
from fields import EircodeField
from PyQt6.QtGui import QColor

from util.validation import TextValidator, IntegerValidator, DecimalValidator, DateValidator
from util.validation import EmailValidator, IrishMobileValidator, EircodeValidator

# Class, Display colour, Validation class
FIELD_TYPE_MAP = {
    "Tickbox": (Tickbox, QColor(50, 255, 0), TextValidator),
    "SignatureField": (SignatureField, QColor(0, 150, 150), TextValidator),
    "RadioButton": (RadioButton, QColor(100, 150, 0), TextValidator),
    "RadioGroup": (RadioGroup, QColor(100, 150, 0), TextValidator),
    "RadioGrid": (RadioGrid, QColor(100, 150, 0), TextValidator),
    "TextField": (TextField, QColor(0, 150, 50), TextValidator),
    "IntegerField": (IntegerField, QColor(0, 100, 200), IntegerValidator),
    "DecimalField": (DecimalField, QColor(0, 100, 200), DecimalValidator),
    "DateField": (DateField, QColor(0, 100, 250), DateValidator),
    "NumericRadioGroup": (NumericRadioGroup, QColor(0, 150, 150), IntegerValidator()),
    "EmailField": (EmailField, QColor(0, 150, 150), EmailValidator()),
    "IrishMobileField": (IrishMobileField, QColor(0, 150, 150), IrishMobileValidator()),
    "EircodeField": (EircodeField, QColor(0, 150, 150), EircodeValidator()),
}
INVALID_COLOUR = QColor(255, 0, 0)


def qcolor_to_tuple(color: QColor) -> tuple[int, int, int]:
    return (color.red(), color.green(), color.blue())


def default_colour_tuple_for_type(type_name: str) -> tuple[int, int, int]:
    """RGB tuple for JSON persistence / field construction."""
    entry = FIELD_TYPE_MAP.get(type_name)
    if entry is None:
        return qcolor_to_tuple(INVALID_COLOUR)
    _field_class, color, _validator = entry
    return qcolor_to_tuple(color)


def default_colour_tuple_for_class(field_class: type) -> tuple[int, int, int]:
    for _name, (cls, color, _validator) in FIELD_TYPE_MAP.items():
        if cls is field_class:
            return qcolor_to_tuple(color)
    return qcolor_to_tuple(INVALID_COLOUR)


def get_display_color_for_type(type_name: str) -> QColor:
    """Resolve type colour from FIELD_TYPE_MAP by type name."""
    entry = FIELD_TYPE_MAP.get(type_name)
    if entry is None:
        return INVALID_COLOUR
    _field_class, color, _validator = entry
    return color


def get_field_display_color(field: Field) -> QColor:
    """
    Resolve overlay colour from FIELD_TYPE_MAP by concrete field class.

    Ignores any colour stored in JSON so Designer and Indexer stay aligned.
    """
    for field_class, color, _validator in FIELD_TYPE_MAP.values():
        if type(field) is field_class:
            return color

    colour_attr = getattr(field, "colour", None)
    if isinstance(colour_attr, QColor):
        return colour_attr
    if isinstance(colour_attr, tuple) and len(colour_attr) == 3:
        try:
            return QColor(*colour_attr)
        except TypeError:
            pass

    return QColor(0, 255, 0)


def create_field(field_type: str, name: str, x: int, y: int, width: int, height: int) -> Field:
    entry = FIELD_TYPE_MAP.get(field_type)
    if not entry:
        raise ValueError(f"Invalid field type: {field_type}")
    field_class, _colour, _validator = entry
    return field_class(
        name=name,
        x=x,
        y=y,
        width=width,
        height=height,
        colour=default_colour_tuple_for_type(field_type),
    )

def create_field_from_dict(field_dict: dict) -> Field:
    field_type = field_dict.get("type")
    name = field_dict.get("name")
    x = field_dict.get("x")
    y = field_dict.get("y")
    width = field_dict.get("width")
    height = field_dict.get("height")
    return create_field(field_type, name, x, y, width, height)