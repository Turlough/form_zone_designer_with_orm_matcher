from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QToolButton, QCheckBox


class DesignerButtonLayout(QHBoxLayout):
    """Layout containing the main control and zoom buttons for the designer.

    This layout is responsible for creating the buttons and wiring them to the
    given main window (parent). The buttons themselves are exposed on the
    parent as attributes so existing code in the main window can continue to
    reference e.g. self.detect_button, self.undo_button, etc.
    """

    def __init__(self, parent):
        super().__init__()

        # Control buttons
        parent.detect_button = QPushButton("Detect Rectangles")
        parent.detect_button.clicked.connect(parent.detect_rectangles)
        parent.detect_button.setEnabled(False)
        self.addWidget(parent.detect_button)

        parent.remove_inner_button = QPushButton("Remove inner rectangles")
        parent.remove_inner_button.setToolTip("Remove detected rectangles that are entirely inside another (inner perimeters of the same box)")
        parent.remove_inner_button.clicked.connect(parent.remove_inner_rectangles_clicked)
        parent.remove_inner_button.setEnabled(False)
        self.addWidget(parent.remove_inner_button)

        parent.undo_button = QPushButton("Undo Last Field")
        parent.undo_button.clicked.connect(parent.undo_last_field)
        parent.undo_button.setEnabled(False)
        self.addWidget(parent.undo_button)

        parent.clear_button = QPushButton("Clear All Fields on Page")
        parent.clear_button.clicked.connect(parent.clear_current_page_fields)
        parent.clear_button.setEnabled(False)
        self.addWidget(parent.clear_button)

        parent.grid_designer_button = QPushButton("Grid Designer")
        parent.grid_designer_button.setToolTip("Design a radio grid (rows = questions, columns = answers)")
        parent.grid_designer_button.clicked.connect(parent.open_grid_designer)
        parent.grid_designer_button.setEnabled(False)
        self.addWidget(parent.grid_designer_button)

        # Zoom / fit controls (icon-only buttons affecting ImageDisplayWidget zoom)
        parent.fit_width_button = QToolButton()
        parent.fit_width_button.setText("↔")
        parent.fit_width_button.setToolTip("Fit Width")
        parent.fit_width_button.clicked.connect(parent.on_fit_width_clicked)
        parent.fit_width_button.setEnabled(False)
        self.addWidget(parent.fit_width_button)

        parent.fit_height_button = QToolButton()
        parent.fit_height_button.setText("↕")
        parent.fit_height_button.setToolTip("Fit Height")
        parent.fit_height_button.clicked.connect(parent.on_fit_height_clicked)
        parent.fit_height_button.setEnabled(False)
        self.addWidget(parent.fit_height_button)

        parent.autofit_button = QToolButton()
        parent.autofit_button.setText("⤢")
        parent.autofit_button.setToolTip("Autofit")
        parent.autofit_button.clicked.connect(parent.on_autofit_clicked)
        parent.autofit_button.setEnabled(False)
        self.addWidget(parent.autofit_button)

        parent.zoom_in_button = QToolButton()
        parent.zoom_in_button.setText("+")
        parent.zoom_in_button.setToolTip("Zoom In")
        parent.zoom_in_button.clicked.connect(parent.on_zoom_in_clicked)
        parent.zoom_in_button.setEnabled(False)
        self.addWidget(parent.zoom_in_button)

        parent.zoom_out_button = QToolButton()
        parent.zoom_out_button.setText("−")
        parent.zoom_out_button.setToolTip("Zoom Out")
        parent.zoom_out_button.clicked.connect(parent.on_zoom_out_clicked)
        parent.zoom_out_button.setEnabled(False)
        self.addWidget(parent.zoom_out_button)

        # Toggle to show field names on the image
        parent.field_names_toggle = QCheckBox("Field names")
        parent.field_names_toggle.setToolTip("Show first 20 characters of each field name next to its rectangle")
        parent.field_names_toggle.stateChanged.connect(parent.on_field_names_toggled)
        self.addWidget(parent.field_names_toggle)

        self.addStretch()