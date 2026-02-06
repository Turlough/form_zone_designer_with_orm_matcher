from fields import Field
from fields import Tickbox
from fields import RadioButton
from fields import RadioGroup
from fields import TextField
from fields import IngerField
from fields import DecimalField
from fields import NumericRadioGroup
from PyQt6.QtGui import QColor

FIELD_TYPE_MAP = {
    "Tickbox": (Tickbox, QColor(150, 150, 100)),
    "RadioButton": (RadioButton, QColor(100, 150, 0)),
    "RadioGroup": (RadioGroup, QColor(100, 150, 0)),
    "TextField": (TextField, QColor(0, 150, 150)),
    "IngerField": (IngerField, QColor(0, 150, 150)),
    "DecimalField": (DecimalField, QColor(0, 150, 150)),
    "NumericRadioGroup": (NumericRadioGroup, QColor(0, 150, 150)),
}

def create_field(field_type: str, name: str, x: int, y: int, width: int, height: int) -> Field:
    field_class, colour = FIELD_TYPE_MAP.get(field_type)
    if not field_class:
        raise ValueError(f"Invalid field type: {field_type}")
    return field_class(name=name, x=x, y=y, width=width, height=height, colour=colour)