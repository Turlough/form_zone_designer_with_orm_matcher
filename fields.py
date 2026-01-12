from dataclasses import dataclass, asdict
from pathlib import Path

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
    fiducial_path: str

    def __post_init__(self):
        self.width = self.width or 10
        self.height = self.height or 10
        self.label = self.label or "Field"
        self.value = self.value if self.value is not False and self.value is not None else False
        self.name = self.name or "Field"
        self.colour = self.colour or (255, 0, 0)
        self.fiducial_path = self.fiducial_path or ""
    
    def __str__(self):
        return f"{self.name} ({self.x}, {self.y}, {self.width}, {self.height})"

    def __repr__(self):
        return f"Field(name={self.name}, x={self.x}, y={self.y}, width={self.width}, height={self.height}, label={self.label}, value={self.value})"
    
    def to_dict(self, config_folder=None):
        """Convert field to dictionary for JSON serialization.
        
        Args:
            config_folder: Optional Path to config folder. If provided, fiducial_path
                          will be stored as relative to this folder.
        """
        data = asdict(self)
        data['_type'] = self.__class__.__name__
        
        # Convert absolute fiducial_path to relative string if config_folder is provided
        if 'fiducial_path' in data and data['fiducial_path']:
            if config_folder:
                fiducial_path = Path(data['fiducial_path'])
                if fiducial_path.is_absolute():
                    try:
                        data['fiducial_path'] = str(fiducial_path.relative_to(config_folder))
                    except ValueError:
                        # Path is not relative to config_folder, store as-is
                        pass
                # If already relative, keep as-is
            # If no config_folder, keep as-is (already a string)
        
        return data
    
    @staticmethod
    def from_dict(data, config_folder=None):
        """Create field from dictionary (JSON deserialization).
        
        Args:
            data: Dictionary containing field data
            config_folder: Optional Path to config folder. If provided, relative
                          fiducial_path will be converted to absolute string.
        """
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
        
        # Convert relative fiducial_path string to absolute string if config_folder is provided
        if 'fiducial_path' in data and data['fiducial_path']:
            fiducial_str = data['fiducial_path']
            if config_folder:
                fiducial_path = Path(fiducial_str)
                if not fiducial_path.is_absolute():
                    data['fiducial_path'] = str(config_folder / fiducial_path)
                # If already absolute, keep as-is
            # If no config_folder, keep as-is
        else:
            data['fiducial_path'] = ""
        
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
                if 'fiducial_path' in rb_dict:
                    fiducial_str = rb_dict.get('fiducial_path', '')
                    if fiducial_str and config_folder:
                        fiducial_path = Path(fiducial_str)
                        if not fiducial_path.is_absolute():
                            rb_dict['fiducial_path'] = str(config_folder / fiducial_path)
                    else:
                        rb_dict['fiducial_path'] = fiducial_str or ""
                else:
                    rb_dict['fiducial_path'] = ""
                radio_buttons.append(RadioButton(**rb_dict))
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
    
    def to_dict(self, config_folder=None):
        """Convert RadioGroup to dictionary with properly serialized radio buttons."""
        # Handle fiducial_path conversion - it's already a string
        fiducial_path_str = self.fiducial_path or ""
        if fiducial_path_str and config_folder:
            fiducial_path = Path(fiducial_path_str)
            if fiducial_path.is_absolute():
                try:
                    fiducial_path_str = str(fiducial_path.relative_to(config_folder))
                except ValueError:
                    pass  # Keep as absolute string
        
        data = {
            '_type': self.__class__.__name__,
            'fiducial_path': fiducial_path_str,
            'colour': self.colour,
            'name': self.name,
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'label': self.label,
            'value': self.value,
            'radio_buttons': [rb.to_dict(config_folder) for rb in self.radio_buttons]
        }
        return data


@dataclass
class TextField(Field):
    value: str
    
    def __post_init__(self):
        super().__post_init__()
        self.value = self.value or ""
        self.colour = (0, 255, 255)
    



