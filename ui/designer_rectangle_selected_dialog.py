"""
Dialog shown when a rectangle is selected (clicked, drawn, or existing field).
Positioned to the right of the mouse (or left if no room), centered vertically.

Batch mode (drawn frame with inner answer rectangles): shared question metadata,
per-answer type/name rows (scroll if they would overflow the screen), and
Assistant autofill. Action buttons stay visible.
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
    QWidget,
    QComboBox,
    QTextEdit,
    QSizePolicy,
    QScrollArea,
    QFrame,
    QFormLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QTimer
from PyQt6.QtGui import QGuiApplication
from fields import FIELD_TYPE_MAP
from util.field_edit import format_geometry, parse_geometry, type_has_checked_value

FIELD_TYPES = list(FIELD_TYPE_MAP.keys())

QUESTION_FIELD_TYPES = [
    t
    for t in FIELD_TYPES
    if t
    not in (
        "RadioGroup",
        "RadioButton",
        "RadioGrid",
        "NumericRadioGroup",
    )
]

ASSISTANT_ENABLED_TTIP = (
    "Fill question text and answer field names/types from the framed region "
    "(overwrites current entries)."
)
ASSISTANT_DISABLED_TTIP = (
    "Draw a frame that includes the question and at least one detected answer rectangle."
)
RADIO_GROUP_TTIP = (
    "Create one RadioGroup from this frame. Inner rectangles become mutually "
    "exclusive options (layout need not be a grid)."
)
RADIO_GRID_TTIP = "Open Grid Designer for a radio-button matrix instead."


class _InnerFieldRow(QWidget):
    """One answer control row in batch mode."""

    def __init__(self, index: int, default_name: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(f"{index + 1}."))
        self.type_combo = QComboBox()
        self.type_combo.addItems(QUESTION_FIELD_TYPES)
        self.type_combo.setCurrentText("Tickbox")
        layout.addWidget(self.type_combo)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(f"Option {index + 1}")
        if default_name:
            self.name_edit.setText(default_name)
        layout.addWidget(self.name_edit, stretch=1)


class RectangleSelectedDialog(QDialog):
    """
    Dialog shown when a rectangle is selected (clicked within rect, drawn rect,
    or clicked within existing field). Provides name, type pick list, and
    Delete / Submit / Cancel. Existing-field edit shows JSON keys except colour
    (type palette); geometry is one compact x, y, width, height field.
    For drawn rect with inner rects, batch mode lists each answer with type and
    name plus Assistant autofill; answer rows scroll when the dialog would
    exceed the screen so Assistant / Radio group / Radio grid / Submit stay
    reachable. **Radio group** creates one RadioGroup from the frame;
    **Radio grid…** opens Grid Designer.
    """

    _last_pos = None  # Persists last position within app session

    submitted = pyqtSignal(dict)
    deleted = pyqtSignal()
    cancelled = pyqtSignal()
    assistant_requested = pyqtSignal()
    radio_grid_requested = pyqtSignal(str)
    geometry_edited = pyqtSignal(int, int, int, int)

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
        non_modal: bool | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Rectangle / Field")
        self._anchor_global = anchor_global_pos or QPoint(0, 0)
        self._is_just_drawn = is_just_drawn
        self._existing_field = existing_field
        self._inner_rect_count = max(0, inner_rect_count)
        self._inner_default_names = inner_default_names or []
        self._non_modal = existing_field is not None if non_modal is None else non_modal
        self._finished_action = False
        self._batch_mode = is_just_drawn and self._inner_rect_count >= 1
        self._assistant_running = False
        if self._non_modal:
            self.setModal(False)
            self.setWindowModality(Qt.WindowModality.NonModal)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self._single_name_widget = QWidget()
        single_layout = QVBoxLayout(self._single_name_widget)
        single_layout.setContentsMargins(0, 0, 0, 0)
        single_layout.addWidget(QLabel("Field name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter field name...")
        single_layout.addWidget(self.name_edit)
        layout.addWidget(self._single_name_widget)

        if existing_field is not None:
            hint = QLabel("Drag handles or grid lines on the page to reshape.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #666; font-size: 11px;")
            layout.addWidget(hint)

        self._existing_meta_widget = QWidget()
        meta_form = QFormLayout(self._existing_meta_widget)
        meta_form.setContentsMargins(0, 0, 0, 0)
        meta_form.setSpacing(6)

        self._edit_geometry_edit = QLineEdit()
        self._edit_geometry_edit.setPlaceholderText("x, y, width, height")
        self._edit_geometry_edit.setToolTip("Fiducial-relative x, y, width, height")
        self._edit_geometry_edit.editingFinished.connect(self._on_geometry_editing_finished)
        meta_form.addRow("Rect:", self._edit_geometry_edit)

        self._edit_question_number_edit = QLineEdit()
        self._edit_question_number_edit.setPlaceholderText("e.g. 1.4")
        meta_form.addRow("Q#:", self._edit_question_number_edit)

        self._edit_summary_edit = QLineEdit()
        self._edit_summary_edit.setPlaceholderText("Overlay label (max 50)")
        self._edit_summary_edit.setToolTip(
            "Shown next to the rectangle when Field names is on (up to 50 characters)."
        )
        meta_form.addRow("Summary:", self._edit_summary_edit)

        self._edit_column_title_edit = QLineEdit()
        self._edit_column_title_edit.setPlaceholderText("Customer export heading")
        self._edit_column_title_edit.setToolTip(
            "Customer-facing delivery heading. May repeat across fields; name must not."
        )
        meta_form.addRow("Column title:", self._edit_column_title_edit)

        self._edit_full_text_edit = QTextEdit()
        self._edit_full_text_edit.setPlaceholderText("Full question wording as printed")
        self._edit_full_text_edit.setMaximumHeight(56)
        self._edit_full_text_edit.setAcceptRichText(False)
        meta_form.addRow("Full text:", self._edit_full_text_edit)

        self._edit_checked_value_edit = QLineEdit()
        self._edit_checked_value_edit.setPlaceholderText("Ticked")
        meta_form.addRow("Checked value:", self._edit_checked_value_edit)
        self._checked_value_row = meta_form.rowCount() - 1

        self._edit_export_column_id_edit = QLineEdit()
        self._edit_export_column_id_edit.setPlaceholderText("From Export Check → Apply")
        self._edit_export_column_id_edit.setToolTip(
            "Linked export-format column id (set by Designer Check → Apply)."
        )
        meta_form.addRow("Export column:", self._edit_export_column_id_edit)

        self._meta_form = meta_form
        self._existing_meta_widget.setVisible(existing_field is not None)
        layout.addWidget(self._existing_meta_widget)

        self._single_type_widget = QWidget()
        type_outer = QVBoxLayout(self._single_type_widget)
        type_outer.setContentsMargins(0, 0, 0, 0)
        type_outer.addWidget(QLabel("Field type:"))
        self._button_group = QButtonGroup(self)
        self._type_radios = {}
        for i, ft in enumerate(FIELD_TYPES):
            rb = QRadioButton(ft)
            self._button_group.addButton(rb, i)
            self._type_radios[ft] = rb
            type_outer.addWidget(rb)
        self._radiogroup_radio = self._type_radios["RadioGroup"]
        if not is_just_drawn:
            self._radiogroup_radio.setEnabled(False)
        layout.addWidget(self._single_type_widget)

        # Batch mode: shared question metadata + per-answer rows
        self._batch_widget = QWidget()
        batch_layout = QVBoxLayout(self._batch_widget)
        batch_layout.setContentsMargins(0, 0, 0, 0)
        batch_layout.setSpacing(6)

        batch_layout.addWidget(QLabel("Question number:"))
        self.question_number_edit = QLineEdit()
        self.question_number_edit.setPlaceholderText("e.g. 6.9")
        batch_layout.addWidget(self.question_number_edit)

        batch_layout.addWidget(QLabel("Full question text:"))
        self.full_text_edit = QTextEdit()
        self.full_text_edit.setPlaceholderText("Full wording of the question stem…")
        self.full_text_edit.setMaximumHeight(72)
        batch_layout.addWidget(self.full_text_edit)

        batch_layout.addWidget(QLabel("Answer fields:"))
        self._inner_rows: list[_InnerFieldRow] = []
        self._inner_fields_panel = QWidget()
        self._inner_fields_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        self._inner_layout = QVBoxLayout(self._inner_fields_panel)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_fields_scroll = QScrollArea()
        self._inner_fields_scroll.setWidgetResizable(True)
        self._inner_fields_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._inner_fields_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._inner_fields_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._inner_fields_scroll.setMinimumHeight(72)
        self._inner_fields_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._inner_fields_scroll.setWidget(self._inner_fields_panel)
        batch_layout.addWidget(self._inner_fields_scroll, stretch=1)

        assistant_row = QHBoxLayout()
        self.assistant_btn = QPushButton("Assistant")
        self.assistant_btn.setToolTip(ASSISTANT_DISABLED_TTIP)
        self.assistant_btn.clicked.connect(self._on_assistant_clicked)
        assistant_row.addWidget(self.assistant_btn)
        self.radio_group_btn = QPushButton("Radio group")
        self.radio_group_btn.setToolTip(RADIO_GROUP_TTIP)
        self.radio_group_btn.clicked.connect(self._on_radio_group_clicked)
        assistant_row.addWidget(self.radio_group_btn)
        self.radio_grid_btn = QPushButton("Radio grid…")
        self.radio_grid_btn.setToolTip(RADIO_GRID_TTIP)
        self.radio_grid_btn.clicked.connect(self._on_radio_grid_clicked)
        assistant_row.addWidget(self.radio_grid_btn)
        assistant_row.addStretch()
        batch_layout.addLayout(assistant_row)

        self._batch_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._batch_widget, stretch=1)

        # Inner names (RadioGroup legacy path when batch off but inner rects exist)
        self._inner_name_widget = QWidget()
        self._inner_rg_layout = QVBoxLayout(self._inner_name_widget)
        self._inner_rg_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_name_edits: list[QLineEdit] = []
        if self._inner_rect_count > 0 and not self._batch_mode:
            layout.addWidget(QLabel("Names for options (RadioGroup):"))
            for i in range(self._inner_rect_count):
                le = QLineEdit()
                le.setPlaceholderText(f"Option {i + 1}")
                if i < len(self._inner_default_names) and self._inner_default_names[i]:
                    le.setText(self._inner_default_names[i])
                self._inner_name_edits.append(le)
                self._inner_rg_layout.addWidget(le)
            layout.addWidget(self._inner_name_widget)
        self._inner_name_widget.setVisible(False)
        self._button_group.buttonClicked.connect(self._on_type_changed)

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

        if self._batch_mode:
            self._single_name_widget.hide()
            self._single_type_widget.hide()
            self._batch_widget.show()
            for i in range(self._inner_rect_count):
                default = (
                    self._inner_default_names[i]
                    if i < len(self._inner_default_names)
                    else ""
                )
                row = _InnerFieldRow(i, default)
                self._inner_rows.append(row)
                self._inner_layout.addWidget(row)
            self._update_assistant_enabled()
        else:
            self._batch_widget.hide()
            if existing_field is not None:
                self.name_edit.setText(getattr(existing_field, "name", "") or "")
                t = type(existing_field).__name__
                if t in self._type_radios:
                    self._type_radios[t].setChecked(True)
                self._fill_existing_metadata(existing_field)
                self._on_type_changed()
            else:
                default = default_field_type if default_field_type in self._type_radios else "Tickbox"
                if default == "RadioGroup" and not is_just_drawn:
                    default = "Tickbox"
                self._type_radios[default].setChecked(True)
                self._on_type_changed()

        if self._batch_mode:
            min_w = 380
        elif existing_field is not None:
            min_w = 340
        else:
            min_w = 220
        self.setMinimumWidth(min_w)
        self._fit_vertical_size()

    def _available_screen_geo(self):
        screen = QGuiApplication.screenAt(self._anchor_global)
        if screen is None and self.isVisible():
            screen = QGuiApplication.screenAt(self.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry() if screen else None

    def _max_client_height(self) -> int:
        geo = self._available_screen_geo()
        if geo is None:
            return 800
        if self.isVisible():
            frame_extra = max(0, self.frameGeometry().height() - self.geometry().height())
        else:
            frame_extra = 40
        return max(200, geo.height() - frame_extra)

    def _fit_vertical_size(self) -> None:
        """Size to content, but never taller than the screen; answer rows scroll."""
        max_h = self._max_client_height()
        self.setMaximumHeight(max_h)
        if self._batch_mode:
            self._inner_fields_panel.adjustSize()
        hint = self.sizeHint()
        width = max(self.minimumWidth(), hint.width())
        height = hint.height()
        if self._batch_mode:
            # QScrollArea sizeHint does not include full option-list height;
            # grow so as many rows as possible fit, then scroll the rest.
            extra = max(
                0,
                self._inner_fields_panel.sizeHint().height()
                - self._inner_fields_scroll.minimumHeight(),
            )
            height = hint.height() + extra
            if height > max_h:
                width += self._inner_fields_scroll.verticalScrollBar().sizeHint().width()
        self.resize(width, min(height, max_h))

    def _clamp_to_screen(self) -> None:
        geo = self._available_screen_geo()
        if geo is None:
            return
        w = self.frameSize().width()
        h = self.frameSize().height()
        x = max(geo.x(), min(self.x(), geo.x() + geo.width() - w))
        y = max(geo.y(), min(self.y(), geo.y() + geo.height() - h))
        self.move(x, y)

    def _on_type_changed(self):
        is_rg = self._button_group.checkedId() == FIELD_TYPES.index("RadioGroup")
        self._inner_name_widget.setVisible(
            is_rg and self._inner_rect_count > 0 and not self._batch_mode
        )
        self._update_checked_value_visible()
        self._fit_vertical_size()

    def _fill_existing_metadata(self, field) -> None:
        self.sync_geometry_from_field(field)
        self._edit_question_number_edit.setText(getattr(field, "question_number", "") or "")
        self._edit_summary_edit.setText(getattr(field, "summary", "") or "")
        self._edit_column_title_edit.setText(getattr(field, "column_title", "") or "")
        self._edit_full_text_edit.setPlainText(getattr(field, "full_text", "") or "")
        self._edit_checked_value_edit.setText(getattr(field, "checked_value", "") or "")
        self._edit_export_column_id_edit.setText(getattr(field, "export_column_id", "") or "")

    def sync_geometry_from_field(self, field) -> None:
        if self._edit_geometry_edit.hasFocus():
            return
        text = format_geometry(field.x, field.y, field.width, field.height)
        if self._edit_geometry_edit.text() == text:
            return
        self._edit_geometry_edit.blockSignals(True)
        self._edit_geometry_edit.setText(text)
        self._edit_geometry_edit.blockSignals(False)

    def _selected_type_name(self) -> str:
        idx = self._button_group.checkedId()
        if 0 <= idx < len(FIELD_TYPES):
            return FIELD_TYPES[idx]
        if self._existing_field is not None:
            return type(self._existing_field).__name__
        return "Tickbox"

    def _update_checked_value_visible(self) -> None:
        if self._existing_field is None:
            return
        show = type_has_checked_value(self._selected_type_name())
        self._meta_form.setRowVisible(self._checked_value_row, show)
        if show and not self._edit_checked_value_edit.text().strip():
            default = "Signed" if self._selected_type_name() == "SignatureField" else "Ticked"
            self._edit_checked_value_edit.setText(
                getattr(self._existing_field, "checked_value", "") or default
            )

    def _on_geometry_editing_finished(self) -> None:
        if self._existing_field is None:
            return
        geo = parse_geometry(self._edit_geometry_edit.text())
        if geo is None:
            self.sync_geometry_from_field(self._existing_field)
            return
        self.geometry_edited.emit(*geo)

    def set_assistant_running(self, running: bool):
        self._assistant_running = running
        self._update_assistant_enabled()
        self.assistant_btn.setText("Analysing…" if running else "Assistant")

    def _update_assistant_enabled(self):
        if not self._batch_mode:
            return
        ok = not self._assistant_running and self._inner_rect_count >= 1
        self.assistant_btn.setEnabled(ok)
        self.assistant_btn.setToolTip(
            ASSISTANT_ENABLED_TTIP if ok else ASSISTANT_DISABLED_TTIP
        )
        busy = self._assistant_running
        self.radio_group_btn.setEnabled(not busy)
        self.radio_grid_btn.setEnabled(not busy)

    def _on_assistant_clicked(self):
        if self._assistant_running:
            return
        self.assistant_requested.emit()

    def _batch_answer_fields(self) -> list[dict] | None:
        """Return per-answer type/name rows, or None if any name is empty."""
        fields = []
        for row in self._inner_rows:
            name = row.name_edit.text().strip()
            if not name:
                return None
            fields.append(
                {
                    "field_type": row.type_combo.currentText(),
                    "field_name": name,
                }
            )
        return fields

    def _on_radio_group_clicked(self):
        if self._assistant_running:
            return
        fields = self._batch_answer_fields()
        if fields is None:
            return
        config = {
            "radio_group_mode": True,
            "question_number": self.question_number_edit.text().strip(),
            "full_text": self.full_text_edit.toPlainText().strip(),
            "fields": fields,
        }
        self._finished_action = True
        self.submitted.emit(config)
        self._close_dialog()

    def _on_radio_grid_clicked(self):
        if self._assistant_running:
            return
        name = self.full_text_edit.toPlainText().strip()
        if not name:
            name = self.question_number_edit.text().strip() or "Grid"
        self._finished_action = True
        self.radio_grid_requested.emit(name)
        self._close_dialog()

    def apply_assistant_result(self, result) -> None:
        """Apply AnalyseQuestionResult from Question Assistant."""
        self.question_number_edit.setText(result.question_number or "")
        self.full_text_edit.setPlainText(result.full_text or "")

        for i, row in enumerate(self._inner_rows):
            if i >= len(result.fields):
                break
            proposal = result.fields[i]
            ft = proposal.field_type
            if ft in QUESTION_FIELD_TYPES:
                row.type_combo.setCurrentText(ft)
            row.name_edit.setText(proposal.name or proposal.column_title or "")

        self._fit_vertical_size()

    def _on_delete(self):
        self._finished_action = True
        self.deleted.emit()
        self._close_dialog()

    def _on_submit(self):
        if self._batch_mode:
            fields = self._batch_answer_fields()
            if fields is None:
                return
            config = {
                "batch_mode": True,
                "question_number": self.question_number_edit.text().strip(),
                "full_text": self.full_text_edit.toPlainText().strip(),
                "fields": fields,
            }
            self._finished_action = True
            self.submitted.emit(config)
            self._close_dialog()
            return

        name = self.name_edit.text().strip()
        if not name:
            return
        idx = self._button_group.checkedId()
        if idx < 0 or idx >= len(FIELD_TYPES):
            return
        field_type = FIELD_TYPES[idx]
        config = {"field_type": field_type, "field_name": name}
        if field_type == "RadioGroup" and self._inner_name_edits:
            config["inner_names"] = [
                e.text().strip() or f"Option {i+1}"
                for i, e in enumerate(self._inner_name_edits)
            ]
        if self._existing_field is not None:
            extra = self._existing_field_config()
            if extra is None:
                return
            config.update(extra)
        self._finished_action = True
        self.submitted.emit(config)
        self._close_dialog()

    def _existing_field_config(self) -> dict | None:
        geo = parse_geometry(self._edit_geometry_edit.text())
        if geo is None and self._existing_field is not None:
            geo = (
                self._existing_field.x,
                self._existing_field.y,
                self._existing_field.width,
                self._existing_field.height,
            )
        if geo is None:
            return None
        x, y, width, height = geo
        config = {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "question_number": self._edit_question_number_edit.text().strip(),
            "summary": self._edit_summary_edit.text().strip(),
            "column_title": self._edit_column_title_edit.text().strip(),
            "full_text": self._edit_full_text_edit.toPlainText().strip(),
            "export_column_id": self._edit_export_column_id_edit.text().strip(),
        }
        if type_has_checked_value(self._selected_type_name()):
            checked = self._edit_checked_value_edit.text().strip()
            if self._selected_type_name() == "SignatureField":
                config["checked_value"] = checked or "Signed"
            else:
                config["checked_value"] = checked or "Ticked"
        return config

    def _close_dialog(self):
        if self._non_modal:
            self.close()
        else:
            self.accept()

    def reject(self):
        if not self._finished_action:
            self.cancelled.emit()
        if self._non_modal:
            self._finished_action = True
            self.close()
        else:
            super().reject()

    def done(self, result: int):
        self._save_geometry()
        super().done(result)

    def _save_geometry(self):
        RectangleSelectedDialog._last_pos = self.pos()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._finalize_show_geometry)

    def _finalize_show_geometry(self):
        self._fit_vertical_size()
        last = RectangleSelectedDialog._last_pos
        if last is not None:
            self.move(last)
            self._clamp_to_screen()
        else:
            self._position_near_anchor()

    def closeEvent(self, event):
        self._save_geometry()
        if self._non_modal and not self._finished_action:
            self.cancelled.emit()
            self._finished_action = True
        super().closeEvent(event)

    def _position_near_anchor(self):
        screen = QGuiApplication.screenAt(self._anchor_global)
        if not screen:
            screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        w = self.frameSize().width()
        h = self.frameSize().height()
        x_right = self._anchor_global.x() + 20
        x_left = self._anchor_global.x() - 20 - w
        y_center = self._anchor_global.y() - h // 2
        y = max(geo.y(), min(geo.y() + geo.height() - h, y_center))
        if x_right + w <= geo.x() + geo.width():
            x = x_right
        elif x_left >= geo.x():
            x = x_left
        else:
            x = max(geo.x(), min(geo.x() + geo.width() - w, x_right))
        self.move(x, y)
        self._clamp_to_screen()
