from dataclasses import dataclass, asdict
import json

@dataclass
class Field:
    colour: tuple[int, int, int]
    name: str
    x: int
    y: int
    width: int
    height: int
    label: str
    value: bool | str

    def __post_init__(self):
        self.width = self.width or 10
        self.height = self.height or 10
        self.label = self.label or "Field"
        self.value = self.value or False
        self.name = self.name or "Field"
        self.colour = (255, 0, 0)
    
    def __str__(self):
        return f"{self.name} ({self.x}, {self.y}, {self.width}, {self.height})"

    def __repr__(self):
        return f"Field(name={self.name}, x={self.x}, y={self.y}, width={self.width}, height={self.height}, label={self.label}, value={self.value})"
    
    def to_dict(self):
        """Convert field to dictionary for JSON serialization."""
        data = asdict(self)
        data['_type'] = self.__class__.__name__
        return data
    
    @staticmethod
    def from_dict(data):
        """Create field from dictionary (JSON deserialization)."""
        field_type = data.pop('_type', 'Field')
        
        # Map type name to class
        type_map = {
            'Field': Field,
            'Tickbox': Tickbox,
            'RadioButton': RadioButton,
            'RadioGroup': RadioGroup,
            'TextField': TextField
        }
        
        field_class = type_map.get(field_type, Field)
        
        # Handle RadioGroup special case
        if field_type == 'RadioGroup' and 'radio_buttons' in data:
            radio_buttons_data = data.pop('radio_buttons', [])
            radio_buttons = [RadioButton(**rb) for rb in radio_buttons_data]
            return field_class(radio_buttons=radio_buttons, **data)
        
        return field_class(**data)


@dataclass
class Tickbox(Field):
    value: bool

    def __post_init__(self):
        super().__post_init__()
        self.value = self.value or False
        self.colour = (0, 255, 0)


@dataclass
class RadioButton(Tickbox):
    value: bool
    
    def __post_init__(self):
        super().__post_init__()
        self.colour = (150, 255, 0)


@dataclass
class RadioGroup(Field):
    radio_buttons: list[RadioButton]
    value: str
    
    def __post_init__(self):
        super().__post_init__()
        self.value = self.value or ""
        self.radio_buttons = self.radio_buttons or []
        self.colour = (150, 255, 0)

    def add_radio_button(self, radio_button: RadioButton):
        self.radio_buttons.append(radio_button)
    
    def remove_radio_button(self, radio_button: RadioButton):
        self.radio_buttons.remove(radio_button)


@dataclass
class TextField(Field):
    value: str
    
    def __post_init__(self):
        super().__post_init__()
        self.value = self.value or ""
        self.colour = (0, 255, 255)
    



