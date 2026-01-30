from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QGroupBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from .designer_field_list import DesignerFieldList


class DesignerEditPanel(QWidget):
    """
    Right-side panel: preview strip for the selected field and the Page Fields table.
    Converting rectangles to fields and editing name/type is done via RectangleSelectedDialog.
    """

    # Emitted whenever the field order changes due to drag/drop in the table.
    page_json_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(8)
        self.setLayout(main_layout)

        # ---- 1. Preview strip for selected Field ----
        self.preview_label = QLabel("No selection")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setMaximumHeight(200)
        self.preview_label.setStyleSheet(
            "QLabel { background-color: #3c3f41; color: #dddddd; border: 1px solid #555555; }"
        )
        main_layout.addWidget(self.preview_label)

        # ---- 2. Fields table for current page ----
        json_group = QGroupBox("Page Fields")
        json_layout = QVBoxLayout()
        json_group.setLayout(json_layout)

        self.fields_table = DesignerFieldList()
        self.fields_table.page_json_changed.connect(self.page_json_changed)

        json_layout.addWidget(self.fields_table)

        main_layout.addWidget(json_group, stretch=1)

    # ------------------------------------------------------------------
    # Public API used by the main window
    # ------------------------------------------------------------------

    def set_preview_pixmap(self, pixmap: QPixmap | None):
        """Update the preview strip with a prepared pixmap (full-width strip)."""
        if pixmap is None or pixmap.isNull():
            self.preview_label.setText("No selection")
            self.preview_label.setPixmap(QPixmap())
            return

        # Scale the image to fit within the label's width (and height) while
        # preserving aspect ratio.
        target_width = max(1, self.preview_label.width())
        target_height = max(1, self.preview_label.height())
        scaled = pixmap.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
        self.preview_label.setText("")

    def set_field_from_object(self, field_obj):
        """Clear the preview when selection is cleared (field_obj is None)."""
        if field_obj is None:
            self.preview_label.setText("No selection")
            self.preview_label.setPixmap(QPixmap())

    def set_page_json(self, json_text: str):
        """Set the fields table from JSON text without emitting change signals."""
        self.fields_table.set_page_json(json_text)

    def get_field_order(self) -> list:
        """Return the field order as a list of (field_name, field_type) tuples."""
        return self.fields_table.get_field_order()
