from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

from .designer_main_image_widget import ImageDisplayWidget


class IndexOcrDialog(QDialog):
    """
    Modal dialog for selecting an OCR region on the current index page.

    Shows the current page image, allows the user to zoom (autofit / fit width /
    fit height) and draw a single rectangle to be sent to Google Cloud Vision.

    The selected rectangle is stored in page image coordinates (x, y, width, height).
    """

    def __init__(self, parent, page_pixmap: QPixmap, initial_rect=None):
        """
        Args:
            parent: Parent widget.
            page_pixmap: Full page image to select from.
            initial_rect: Optional (x, y, w, h) in page pixels to show as the selected area
                (e.g. current text field). User can submit this as-is or change it.
        """
        super().__init__(parent)
        self.setWindowTitle("OCR - Select Area")
        self.setModal(True)
        # Fill the screen
        # self.setGeometry(0, 0,
        # QApplication.primaryScreen().availableGeometry().width(),
        # int(QApplication.primaryScreen().availableGeometry().height() * 0.9))

        self._page_pixmap = page_pixmap

        main_layout = QVBoxLayout(self)

        # Zoom controls
        zoom_layout = QHBoxLayout()
        self.autofit_button = QPushButton("Autofit")
        self.fit_width_button = QPushButton("Fit width")
        self.fit_height_button = QPushButton("Fit height")
        zoom_layout.addWidget(self.autofit_button)
        zoom_layout.addWidget(self.fit_width_button)
        zoom_layout.addWidget(self.fit_height_button)
        zoom_layout.addStretch(1)
        main_layout.addLayout(zoom_layout)

        # Scroll area with image widget
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #2b2b2b; }")

        self.image_widget = ImageDisplayWidget(self.scroll_area)
        self.scroll_area.setWidget(self.image_widget)
        main_layout.addWidget(self.scroll_area, stretch=1)

        # Buttons: Clear, Cancel, Submit
        buttons_layout = QHBoxLayout()
        self.clear_button = QPushButton("Clear")
        self.cancel_button = QPushButton("Cancel")
        self.submit_button = QPushButton("Submit")

        buttons_layout.addStretch(1)
        buttons_layout.addWidget(self.clear_button)
        buttons_layout.addWidget(self.cancel_button)
        buttons_layout.addWidget(self.submit_button)
        main_layout.addLayout(buttons_layout)

        # Wire up behavior
        self.autofit_button.clicked.connect(self.image_widget.set_autofit)
        self.fit_width_button.clicked.connect(self.image_widget.set_fit_width)
        self.fit_height_button.clicked.connect(self.image_widget.set_fit_height)

        self.clear_button.clicked.connect(self._on_clear_clicked)
        self.cancel_button.clicked.connect(self.reject)
        self.submit_button.clicked.connect(self._on_submit_clicked)

        # Initialize image
        self.image_widget.set_image(self._page_pixmap, bbox=None, field_list=[], detected_rects=[])
        self.image_widget.set_autofit()
        # Show current text field as selected so user can submit it or adjust
        if initial_rect:
            self.image_widget.set_selection_rect(initial_rect)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selected_rect(self):
        """Return the selected rectangle as (x, y, w, h) in page pixels, or None."""
        return self.image_widget.get_selection_rect()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_clear_clicked(self):
        """Clear the current selection rectangle."""
        self.image_widget.clear_selection()

    def _on_submit_clicked(self):
        """Accept only if there is a valid selection."""
        rect = self.image_widget.get_selection_rect()
        if not rect:
            # No selection; do not close. User can Cancel instead.
            return
        self.accept()

