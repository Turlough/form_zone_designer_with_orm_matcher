from dataclasses import dataclass, asdict, field, KW_ONLY
import uuid


def _normalize_colour(value) -> tuple[int, int, int] | None:
    if value is None:
        return None
    if isinstance(value, tuple) and len(value) == 3:
        return tuple(int(c) for c in value)
    if isinstance(value, list) and len(value) == 3:
        return tuple(int(c) for c in value)
    return None


def _apply_canonical_colour(instance: "Field") -> None:
    from field_factory import default_colour_tuple_for_class

    instance.colour = default_colour_tuple_for_class(type(instance))


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
    question_number: str = ""
    export_column_id: str = ""

    def __post_init__(self):
        self.width = self.width or 10
        self.height = self.height or 10
        self.name = self.name
        self.summary = self.summary or ""
        self.column_title = self.column_title or ""
        self.full_text = self.full_text or ""
        self.question_number = self.question_number or ""
        self.export_column_id = self.export_column_id or ""
        if type(self) is Field:
            normalized = _normalize_colour(self.colour)
            self.colour = normalized or (255, 0, 0)
        else:
            _apply_canonical_colour(self)

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
        if self.question_number:
            meta["question_number"] = self.question_number
        if self.export_column_id:
            meta["export_column_id"] = self.export_column_id
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
        _apply_canonical_colour(self)
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
        if not data.get("question_number"):
            data.pop("question_number", None)
        if not data.get("export_column_id"):
            data.pop("export_column_id", None)
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
        data.pop("colour", None)

        # Resolve concrete field class from global FIELD_TYPE_MAP
        field_class = FIELD_TYPE_MAP.get(field_type, Field)

        if field_type == "RadioGrid":
            return RadioGrid.from_dict({"_type": "RadioGrid", **data})

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
                rb_dict.pop("colour", None)
                from field_factory import default_colour_tuple_for_type

                rb_dict["colour"] = default_colour_tuple_for_type("RadioButton")
                radio_buttons.append(RadioButton(**rb_dict))
            from field_factory import default_colour_tuple_for_type

            data["colour"] = default_colour_tuple_for_type(field_type)
            return field_class(radio_buttons=radio_buttons, **data)

        from field_factory import default_colour_tuple_for_type

        data["colour"] = default_colour_tuple_for_type(field_type)
        return field_class(**data)


@dataclass
class RadioGrid(Field):
    """Design-time radio grid; expands to RadioGroups for Indexer/Exporter."""

    orientation: str = "horizontal"  # "horizontal" | "vertical"
    row_labels: list[str] = field(default_factory=list)
    col_labels: list[str] = field(default_factory=list)
    col_fracs: list[float] = field(default_factory=list)
    row_fracs: list[float] = field(default_factory=list)
    grid_id: str = ""

    def __post_init__(self):
        super().__post_init__()
        if not self.grid_id:
            self.grid_id = str(uuid.uuid4())

    def expand_to_radio_groups(self) -> list["RadioGroup"]:
        from util.radio_grid_layout import expand_radio_grid

        return expand_radio_grid(self)

    def to_dict(self):
        _apply_canonical_colour(self)
        data = {
            "_type": self.__class__.__name__,
            "grid_id": self.grid_id,
            "colour": self.colour,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "orientation": self.orientation,
            "row_labels": list(self.row_labels),
            "col_labels": list(self.col_labels),
            "col_fracs": list(self.col_fracs),
            "row_fracs": list(self.row_fracs),
        }
        data.update(self._metadata_dict())
        return data

    @staticmethod
    def from_dict(data: dict) -> "RadioGrid":
        d = dict(data)
        d.pop("_type", None)
        d.pop("_", None)
        d.pop("colour", None)
        from field_factory import default_colour_tuple_for_type

        d["colour"] = default_colour_tuple_for_type("RadioGrid")
        return RadioGrid(**d)


@dataclass
class Tickbox(Field):
    checked_value: str = "Ticked"


@dataclass
class RadioButton(Tickbox):
    pass


@dataclass
class RadioGroup(Field):
    radio_buttons: list[RadioButton] = field(default_factory=list)

    def __post_init__(self):
        super().__post_init__()
        self.radio_buttons = self.radio_buttons or []

    def add_radio_button(self, radio_button: RadioButton):
        self.radio_buttons.append(radio_button)

    def remove_radio_button(self, radio_button: RadioButton):
        self.radio_buttons.remove(radio_button)

    def to_dict(self):
        """Convert RadioGroup to dictionary with properly serialized radio buttons."""
        _apply_canonical_colour(self)
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
    pass


@dataclass
class TextField(Field):
    pass


@dataclass
class IntegerField(TextField):
    pass


@dataclass
class DecimalField(TextField):
    pass


@dataclass
class DateField(TextField):
    pass


@dataclass
class EmailField(TextField):
    pass


@dataclass
class IrishMobileField(TextField):
    pass


@dataclass
class EircodeField(TextField):
    pass


@dataclass
class SignatureField(Tickbox):
    checked_value: str = "Signed"


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
    "RadioGrid": RadioGrid,
}
