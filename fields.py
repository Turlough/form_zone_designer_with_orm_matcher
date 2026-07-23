from dataclasses import dataclass, asdict, field, KW_ONLY


@dataclass
class Field:
    colour: tuple[int, int, int]
    name: str
    x: int
    y: int
    width: int
    height: int
    _: KW_ONLY
    summary: str = ""
    column_title: str = ""
    full_text: str = ""

    def __post_init__(self):
        self.width = self.width or 10
        self.height = self.height or 10
        self.name = self.name
        self.colour = self.colour or (255, 0, 0)
        self.summary = self.summary or ""
        self.column_title = self.column_title or ""
        self.full_text = self.full_text or ""

    def __str__(self):
        return f"{self.name} ({self.x}, {self.y}, {self.width}, {self.height})"

    def __repr__(self):
        return (
            f"Field(name={self.name}, x={self.x}, y={self.y}, "
            f"width={self.width}, height={self.height}, colour={self.colour})"
        )

    def _metadata_dict(self) -> dict:
        """Optional metadata keys for JSON (omit empties except when set)."""
        meta = {}
        if self.summary:
            meta["summary"] = self.summary
        if self.column_title:
            meta["column_title"] = self.column_title
        if self.full_text:
            meta["full_text"] = self.full_text
        return meta

    def to_dict(self):
        """Convert field to dictionary for JSON serialization."""

        # Prevent serializing base Field instances
        if type(self) == Field:
            raise ValueError(
                "Base Field class cannot be serialized. "
                "Field instances are temporary and must be converted to a concrete type "
                "(Tickbox, RadioButton, RadioGroup, or TextField) before serialization."
            )
        data = asdict(self)
        data.pop("_", None)
        data["_type"] = self.__class__.__name__
        # Drop empty optional metadata for leaner JSON (backward compatible on read)
        if not data.get("summary"):
            data.pop("summary", None)
        if not data.get("column_title"):
            data.pop("column_title", None)
        if not data.get("full_text"):
            data.pop("full_text", None)
        return data

    @staticmethod
    def from_dict(data: dict):
        """Create field from dictionary (JSON deserialization).

        Args:
            data: Dictionary containing field data
        """
        data = dict(data)
        field_type = data.pop("_type")
        data.pop("_", None)

        # Resolve concrete field class from global FIELD_TYPE_MAP
        field_class = FIELD_TYPE_MAP.get(field_type, Field)

        # Handle RadioGroup (and subclasses) special case
        if issubclass(field_class, RadioGroup) and "radio_buttons" in data:
            radio_buttons_data = data.pop("radio_buttons", [])
            radio_buttons = []
            for rb_data in radio_buttons_data:
                # Make a copy to avoid modifying the original
                rb_dict = rb_data.copy()
                # Remove _type if present, we know it's a RadioButton
                rb_dict.pop("_type", None)
                rb_dict.pop("_", None)
                radio_buttons.append(RadioButton(**rb_dict))
            return field_class(radio_buttons=radio_buttons, **data)

        return field_class(**data)


@dataclass
class Tickbox(Field):
    checked_value: str = "Ticked"

    def __post_init__(self):
        super().__post_init__()


@dataclass
class RadioButton(Tickbox):

    def __post_init__(self):
        super().__post_init__()
        self.colour = (100, 150, 0)


@dataclass
class RadioGroup(Field):
    radio_buttons: list[RadioButton] = field(default_factory=list)

    def __post_init__(self):
        super().__post_init__()
        self.radio_buttons = self.radio_buttons or []
        self.colour = (100, 150, 0)

    def add_radio_button(self, radio_button: RadioButton):
        self.radio_buttons.append(radio_button)

    def remove_radio_button(self, radio_button: RadioButton):
        self.radio_buttons.remove(radio_button)

    def to_dict(self):
        """Convert RadioGroup to dictionary with properly serialized radio buttons."""
        data = {
            "_type": self.__class__.__name__,
            "colour": self.colour,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "radio_buttons": [rb.to_dict() for rb in self.radio_buttons],
        }
        data.update(self._metadata_dict())
        return data


@dataclass
class NumericRadioGroup(RadioGroup):
    def __post_init__(self):
        super().__post_init__()
        self.colour = (0, 150, 150)
        self.radio_buttons = self.radio_buttons or []

    def add_radio_button(self, radio_button: RadioButton):
        self.radio_buttons.append(radio_button)

    def remove_radio_button(self, radio_button: RadioButton):
        self.radio_buttons.remove(radio_button)

    def to_dict(self):
        """Convert NumericRadioGroup to dictionary with properly serialized radio buttons."""
        data = super().to_dict()
        return data


@dataclass
class TextField(Field):

    def __post_init__(self):
        super().__post_init__()
        self.colour = (0, 150, 150)


@dataclass
class IntegerField(TextField):
    def __post_init__(self):
        super().__post_init__()
        self.colour = (0, 150, 150)


@dataclass
class DecimalField(TextField):
    def __post_init__(self):
        super().__post_init__()
        self.colour = (0, 150, 150)


@dataclass
class DateField(TextField):
    def __post_init__(self):
        super().__post_init__()
        self.colour = (0, 150, 150)


@dataclass
class EmailField(TextField):
    def __post_init__(self):
        super().__post_init__()
        self.colour = (0, 150, 150)


@dataclass
class IrishMobileField(TextField):
    def __post_init__(self):
        super().__post_init__()
        self.colour = (0, 150, 150)


@dataclass
class EircodeField(TextField):
    def __post_init__(self):
        super().__post_init__()
        self.colour = (0, 150, 150)


@dataclass
class SignatureField(Tickbox):
    checked_value: str = "Signed"

    def __post_init__(self):
        super().__post_init__()
        self.colour = (0, 150, 150)


FIELD_TYPE_MAP = {
    "Tickbox": Tickbox,
    "SignatureField": SignatureField,
    "RadioButton": RadioButton,
    "RadioGroup": RadioGroup,
    "TextField": TextField,
    "IntegerField": IntegerField,
    "DecimalField": DecimalField,
    "DateField": DateField,
    "EmailField": EmailField,
    "IrishMobileField": IrishMobileField,
    "EircodeField": EircodeField,
    "NumericRadioGroup": NumericRadioGroup,
}
