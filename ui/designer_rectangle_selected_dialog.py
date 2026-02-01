"""
Dialog shown when a rectangle is selected (clicked, drawn, or existing field).
Positioned to the right of the mouse (or left if no room), centered vertically.
"""
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QButtonGroup,
    QPushButton,
    QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QGuiApplication

FIELD_TYPES = ["Tickbox", "RadioButton", "RadioGroup", "TextField"]


class RectangleSelectedDialog(QDialog):
    """
    Dialog shown when a rectangle is selected (clicked within rect, drawn rect,
    or clicked within existing field). Provides name, type pick list, and
    Delete / Submit / Cancel. For drawn rect with RadioGroup, shows name
    inputs for each inner rectangle.
    """

    # Emitted with config dict: {"field_type": str, "field_name": str}
    # or for RadioGroup: {"field_type": "RadioGroup", "field_name": str, "inner_names": [str, ...]}
    submitted = pyqtSignal(dict)
    # Emitted when user clicks Delete (caller should remove rect/field and refresh)
    deleted = pyqtSignal()
    # Emitted when user cancels (dialog closed without submit/delete)
    cancelled = pyqtSignal()

    def __init__(
        self,
        parent=None,
        anchor_global_pos: QPoint | None = None,
        *,
        is_just_drawn: bool = False,
        existing_field=None,
        inner_rect_count: int = 0,
        inner_default_names: list[str] | None = None,
        default_field_type: str = "Tickbox",
    ):
        super().__init__(parent)
        self.setWindowTitle("Rectangle / Field")
        self._anchor_global = anchor_global_pos or QPoint(0, 0)
        self._is_just_drawn = is_just_drawn
        self._existing_field = existing_field
        self._inner_rect_count = max(0, inner_rect_count)
        self._inner_default_names = inner_default_names or []

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Name
        layout.addWidget(QLabel("Field name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter field name...")
        layout.addWidget(self.name_edit)

        # Type: vertical pick list (radio buttons)
        layout.addWidget(QLabel("Field type:"))
        self._button_group = QButtonGroup(self)
        self._type_radios = {}
        for i, ft in enumerate(FIELD_TYPES):
            rb = QRadioButton(ft)
            self._button_group.addButton(rb, i)
            self._type_radios[ft] = rb
            layout.addWidget(rb)
        self._radiogroup_radio = self._type_radios["RadioGroup"]
        if not is_just_drawn:
            self._radiogroup_radio.setEnabled(False)

        # Inner names (for RadioGroup when just drawn with inner rects)
        self._inner_name_widget = QWidget()
        self._inner_layout = QVBoxLayout(self._inner_name_widget)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_name_edits: list[QLineEdit] = []
        if self._inner_rect_count > 0:
            layout.addWidget(QLabel("Names for options (RadioGroup):"))
            for i in range(self._inner_rect_count):
                le = QLineEdit()
                le.setPlaceholderText(f"Option {i + 1}")
                if i < len(self._inner_default_names) and self._inner_default_names[i]:
                    le.setText(self._inner_default_names[i])
                self._inner_name_edits.append(le)
                self._inner_layout.addWidget(le)
            layout.addWidget(self._inner_name_widget)
        self._inner_name_widget.setVisible(False)
        self._button_group.buttonClicked.connect(self._on_type_changed)

        # Buttons
        btn_layout = QHBoxLayout()

        self.submit_btn = QPushButton("Submit")
        self.submit_btn.setDefault(True)
        self.submit_btn.clicked.connect(self._on_submit)
        self.cancel_btn = QPushButton("Cancel")    
        self.cancel_btn.clicked.connect(self.reject)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._on_delete)

        btn_layout.addWidget(self.delete_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.submit_btn)
        layout.addLayout(btn_layout)

        # Pre-fill for existing field
        if existing_field is not None:
            self.name_edit.setText(getattr(existing_field, "name", "") or "")
            t = type(existing_field).__name__
            if t in self._type_radios:
                self._type_radios[t].setChecked(True)
            self._on_type_changed()
        else:
            default = default_field_type if default_field_type in self._type_radios else "Tickbox"
            if default == "RadioGroup" and not is_just_drawn:
                default = "Tickbox"
            self._type_radios[default].setChecked(True)
            self._on_type_changed()

        self.setMinimumWidth(220)
        self.adjustSize()

    def _on_type_changed(self):
        is_rg = self._button_group.checkedId() == FIELD_TYPES.index("RadioGroup")
        self._inner_name_widget.setVisible(is_rg and self._inner_rect_count > 0)

    def _on_delete(self):
        self.deleted.emit()
        self.accept()

    def _on_submit(self):
        name = self.name_edit.text().strip()
        if not name:
            return
        idx = self._button_group.checkedId()
        if idx < 0 or idx >= len(FIELD_TYPES):
            return
        field_type = FIELD_TYPES[idx]
        config = {"field_type": field_type, "field_name": name}
        if field_type == "RadioGroup" and self._inner_name_edits:
            config["inner_names"] = [e.text().strip() or f"Option {i+1}" for i, e in enumerate(self._inner_name_edits)]
        self.submitted.emit(config)
        self.accept()

    def reject(self):
        self.cancelled.emit()
        super().reject()

    def showEvent(self, event):
        super().showEvent(event)
        self._position_near_anchor()

    def _position_near_anchor(self):
        """Position dialog to the right of anchor (or left if no room), vertically centered."""
        screen = QGuiApplication.screenAt(self._anchor_global)
        if not screen:
            screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        # Dialog size
        w = self.frameSize().width()
        h = self.frameSize().height()
        # Prefer right of anchor, vertically centered on anchor
        x_right = self._anchor_global.x() + 20
        x_left = self._anchor_global.x() - 20 - w
        y_center = self._anchor_global.y() - h // 2
        # Clamp y to screen
        y = max(geo.y(), min(geo.y() + geo.height() - h, y_center))
        # Choose left or right based on space
        if x_right + w <= geo.x() + geo.width():
            x = x_right
        elif x_left >= geo.x():
            x = x_left
        else:
            x = max(geo.x(), min(geo.x() + geo.width() - w, x_right))
        self.move(x, y)
