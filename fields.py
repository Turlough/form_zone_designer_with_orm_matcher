from dataclasses import dataclass, asdict


@dataclass
class Field:
    colour: tuple[int, int, int]
    name: str
    x: int
    y: int
    width: int
    height: int


    def __post_init__(self):
        self.width = self.width or 10
        self.height = self.height or 10
        self.name = self.name
        self.colour = self.colour or (255, 0, 0)

    
    def __str__(self):
        return f"{self.name} ({self.x}, {self.y}, {self.width}, {self.height})"

    def __repr__(self):
        return f"Field(name={self.name}, x={self.x}, y={self.y}, width={self.width}, height={self.height}, colour={self.colour})"
        
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
        data['_type'] = self.__class__.__name__
        
        return data
    
    @staticmethod
    def from_dict(data: dict):
        """Create field from dictionary (JSON deserialization).
        
        Args:
            data: Dictionary containing field data
        """
        field_type = data.pop('_type')
        
        # Map type name to class
        type_map = {
            'Tickbox': Tickbox,
            'RadioButton': RadioButton,
            'RadioGroup': RadioGroup,
            'TextField': TextField
        }
        
        field_class = type_map.get(field_type, Field)
        
        # Handle RadioGroup special case
        if field_type == 'RadioGroup' and 'radio_buttons' in data:
            radio_buttons_data = data.pop('radio_buttons', [])
            radio_buttons = []
            for rb_data in radio_buttons_data:
                # Make a copy to avoid modifying the original
                rb_dict = rb_data.copy()
                # Remove _type if present, we know it's a RadioButton
                rb_dict.pop('_type', None)
                # Handle fiducial_path for radio buttons too
                radio_buttons.append(RadioButton(**rb_dict))
            return field_class(radio_buttons=radio_buttons, **data)
        
        return field_class(**data)


@dataclass
class Tickbox(Field):
    def __post_init__(self):
        super().__post_init__()
        

@dataclass
class RadioButton(Tickbox):
   
    def __post_init__(self):
        super().__post_init__()
        self.colour = (100, 150, 0)


@dataclass
class RadioGroup(Field):
    radio_buttons: list[RadioButton]
    
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
            '_type': self.__class__.__name__,
            'colour': self.colour,
            'name': self.name,
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'radio_buttons': [rb.to_dict() for rb in self.radio_buttons]
        }
        return data


@dataclass
class TextField(Field):
    
    def __post_init__(self):
        super().__post_init__()
        self.colour = (0, 150, 150)

@dataclass
class IngerField(TextField):
    def __post_init__(self):    
        super().__post_init__()
        self.colour = (0, 150, 150)

@dataclass
class DecimalField(TextField):
    def __post_init__(self):
        super().__post_init__()
        self.colour = (0, 150, 150)

@dataclass
class NumericRadioGroup(RadioGroup):
    def __post_init__(self):
        super().__post_init__()
        self.colour = (0, 150, 150)
    def add_radio_button(self, radio_button: RadioButton):
        self.radio_buttons.append(radio_button)
    
    def remove_radio_button(self, radio_button: RadioButton):
        self.radio_buttons.remove(radio_button)


FIELD_TYPE_MAP = {
    "Tickbox": Tickbox,
    "RadioButton": RadioButton,
    "RadioGroup": RadioGroup,
    "TextField": TextField,
    "IngerField": IngerField,
    "DecimalField": DecimalField,
    "NumericRadioGroup": NumericRadioGroup,
}