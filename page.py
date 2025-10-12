from dataclasses import dataclass
from fields import Field

@dataclass
class Page:
    name: str
    fields: list[Field]
    
    def __post_init__(self):
        self.name = self.name or "Page"
        self.fields = self.fields or []
        
    def add_field(self, field: Field):
        self.fields.append(field)
        
    def remove_field(self, field: Field):
        self.fields.remove(field)