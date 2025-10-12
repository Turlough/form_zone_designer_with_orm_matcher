from dataclasses import dataclass

@dataclass
class Field:
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
    
    def __str__(self):
        return f"{self.name} ({self.x}, {self.y}, {self.width}, {self.height})"

    def __repr__(self):
        return f"Field(name={self.name}, x={self.x}, y={self.y}, width={self.width}, height={self.height}, label={self.label}, value={self.value})"


@dataclass
class Tickbox(Field):
    value: bool

    def __post_init__(self):
        super().__post_init__()
        self.value = self.value or False


@dataclass
class RadioButton(Tickbox):
    value: bool
    
    def __post_init__(self):
        super().__post_init__()


@dataclass
class RadioGroup(Field):
    radio_buttons: list[RadioButton]
    value: str
    
    def __post_init__(self):
        super().__post_init__()
        self.value = self.value or ""
        self.radio_buttons = self.radio_buttons or []

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
    
    def __post_init__(self):
        super().__post_init__()
        self.value = self.value or ""


