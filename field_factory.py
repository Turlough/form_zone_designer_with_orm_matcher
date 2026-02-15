from fields import Field
from fields import Tickbox
from fields import RadioButton
from fields import RadioGroup
from fields import TextField
from fields import IntegerField
from fields import DecimalField
from fields import NumericRadioGroup
from fields import DateField
from PyQt6.QtGui import QColor

from util.validation.indexer_validations import TextValidator, IntegerValidator, DecimalValidator, DateValidator

# Class, Display colour, Validation class
FIELD_TYPE_MAP = {
    "Tickbox": (Tickbox, QColor(50, 255, 0), TextValidator),
    "RadioButton": (RadioButton, QColor(100, 150, 0), TextValidator),
    "RadioGroup": (RadioGroup, QColor(100, 150, 0), TextValidator),
    "TextField": (TextField, QColor(0, 150, 50), TextValidator),
    "IntegerField": (IntegerField, QColor(0, 150, 150), IntegerValidator),
    "DecimalField": (DecimalField, QColor(0, 150, 150), DecimalValidator),
    "DateField": (DateField, QColor(0, 150, 150), DateValidator),
    "NumericRadioGroup": (NumericRadioGroup, QColor(0, 150, 150), IntegerValidator()),
}
INVALID_COLOUR = QColor(255, 0, 0)

def create_field(field_type: str, name: str, x: int, y: int, width: int, height: int) -> Field:
    field_class, colour, validator = FIELD_TYPE_MAP.get(field_type)
    if not field_class:
        raise ValueError(f"Invalid field type: {field_type}")
    return field_class(name=name, x=x, y=y, width=width, height=height, colour=colour, validator=validator)

def create_field_from_dict(field_dict: dict) -> Field:
    field_type = field_dict.get("type")
    name = field_dict.get("name")
    x = field_dict.get("x")
    y = field_dict.get("y")
    width = field_dict.get("width")
    height = field_dict.get("height")
    return create_field(field_type, name, x, y, width, height)