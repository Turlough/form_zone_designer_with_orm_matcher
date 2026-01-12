from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QRadioButton, QButtonGroup, QLineEdit, QDialogButtonBox



class FieldConfigDialog(QDialog):
    """Dialog to configure field type and name after drawing a rectangle."""
    
    def __init__(self, parent=None, cursor_pos=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Field")
        self.setModal(True)
        
        # Position dialog near cursor if provided
        if cursor_pos:
            # Offset slightly so cursor doesn't cover the dialog
            self.move(cursor_pos.x() + 10, cursor_pos.y() + 10)
        
        # Main layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Radio buttons for field type
        type_label = QLabel("Field Type:")
        layout.addWidget(type_label)
        
        self.button_group = QButtonGroup(self)
        
        self.field_radio = QRadioButton("Field")
        self.tickbox_radio = QRadioButton("Tickbox")
        self.radiobutton_radio = QRadioButton("RadioButton")
        self.radiogroup_radio = QRadioButton("RadioGroup")
        self.textfield_radio = QRadioButton("TextField")
        
        # Set default selection
        self.field_radio.setChecked(True)
        
        # Add to button group and layout
        self.button_group.addButton(self.field_radio, 0)
        self.button_group.addButton(self.tickbox_radio, 1)
        self.button_group.addButton(self.radiobutton_radio, 2)
        self.button_group.addButton(self.radiogroup_radio, 3)
        self.button_group.addButton(self.textfield_radio, 4)
        
        layout.addWidget(self.field_radio)
        layout.addWidget(self.tickbox_radio)
        layout.addWidget(self.radiobutton_radio)
        layout.addWidget(self.radiogroup_radio)
        layout.addWidget(self.textfield_radio)
        
        # Text input for field name
        name_label = QLabel("Field Name:")
        layout.addWidget(name_label)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter field name...")
        layout.addWidget(self.name_input)
        
        # Dialog buttons (OK/Cancel)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Set focus to name input
        self.name_input.setFocus()
    
    def get_field_type(self):
        """Return the selected field type as a string."""
        button_id = self.button_group.checkedId()
        field_types = ["Field", "Tickbox", "RadioButton", "RadioGroup", "TextField"]
        if 0 <= button_id < len(field_types):
            return field_types[button_id]
        return "Field"
    
    def get_field_name(self):
        """Return the field name entered by the user."""
        return self.name_input.text().strip() or "Unnamed"

