"""Window for QC staff to quickly review quick_review field values across a batch."""

import base64

from PyQt6.QtCore import Qt, pyqtSignal, QByteArray
from PyQt6.QtGui import QAction, QKeySequence, QColor, QBrush
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMainWindow,
    QMenu,
    QMenuBar,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.qc_comment_dialog import MAX_COMMENT_LENGTH
from field_factory import FIELD_TYPE_MAP
from util.app_state import load_state, save_state
from util.index_comments import Comments
from ui.table_row_divider import RowDivider

ERROR_BG = QColor(255, 200, 200)  # Red for field validation failures
PROJECT_VALIDATION_BG = QColor(255, 255, 200)  # Yellow for project validation failures (Comments)



def _has_non_ascii(s: str) -> bool:
    """Return True if string contains any non-ASCII character."""
    return s is not None and any(ord(c) > 127 for c in s)


def _is_inappropriate_value(field_name: str, value: str, field_to_type: dict[str, str]) -> bool:
    """Return True if value fails validation for the field's type."""
    if not value:
        return False
    field_type = field_to_type.get(field_name)
    if not field_type:
        return False
    entry = FIELD_TYPE_MAP.get(field_type)
    if not entry:
        return False
    _, _, validator = entry
    v = validator() if isinstance(validator, type) else validator
    return not v.is_valid(value)

def _failed_project_validations(
    field_name: str, doc_index: int, doc_index_to_comments: dict[int, str]
) -> bool:
    """Return True if the field is mentioned in the Comments column for that document row."""
    comments_str = doc_index_to_comments.get(doc_index) or ""
    if not comments_str.strip():
        return False
    row_comments = Comments.from_string(comments_str)
    return any(c.field == field_name for c in row_comments.comments.values())


def _get_project_comment_text(
    field_name: str, doc_index: int, doc_index_to_comments: dict[int, str]
) -> str:
    """Return the comment value(s) for the field in that document's Comments, or empty string."""
    comments_str = doc_index_to_comments.get(doc_index) or ""
    if not comments_str.strip():
        return ""
    row_comments = Comments.from_string(comments_str)
    parts = [
        (c.comment or "(empty)")[:MAX_COMMENT_LENGTH]
        for c in row_comments.comments.values()
        if c.field == field_name
    ]
    return " | ".join(parts) if parts else ""


def _get_validator_name(field_name: str, field_to_type: dict[str, str]) -> str:
    """Return the validator class name for the field's type, or empty string."""
    field_type = field_to_type.get(field_name)
    if not field_type:
        return ""
    entry = FIELD_TYPE_MAP.get(field_type)
    if not entry:
        return ""
    _, _, validator = entry
    if isinstance(validator, type):
        return validator.__name__
    return validator.__class__.__name__



class QcTextReviewWindow(QMainWindow):
    """
    Non-modal window showing a sortable table of quick_review field values.

    Columns: FieldName, Value, Error.
    Error shows comment value for project validation failures, validator name for field validation failures.
    Clicking a row activates that field in the main Indexing app (navigate to doc,
    show thumbnail and value in the right-hand panel).
    """

    # Emitted when user clicks a row. Payload: (doc_index: int, field_name: str)
    row_activated = pyqtSignal(int, str)

    # Emitted when user requests File -> Refresh (parent should flush CSV queue and refresh list)
    refresh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quick Review Special Fields")
        self.setMinimumSize(400, 300)
        self._field_to_type: dict[str, str] = {}
        self._doc_index_to_comments: dict[int, str] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        menubar = QMenuBar(self)
        self.setMenuBar(menubar)
        file_menu = menubar.addMenu("File")
        refresh_action = QAction("Refresh", self)
        refresh_action.setShortcut(QKeySequence.StandardKey.Refresh)
        refresh_action.triggered.connect(self._on_refresh_requested)
        file_menu.addAction(refresh_action)

        tools_menu = menubar.addMenu("Tools")
        self._highlight_action = QAction("Highlight known errors", self)
        self._highlight_action.setToolTip(
            "Highlight rows: red for non-ASCII or invalid field values (email, date, etc.); "
            "yellow for fields mentioned in the Comments column (project validation failures)."
        )
        self._highlight_action.triggered.connect(self._on_toggle_highlight_errors)
        tools_menu.addAction(self._highlight_action)
        self._highlights_applied = False

        self._filter_action = QAction("Filter errors", self)
        self._filter_action.setToolTip("Show only rows with field or project validation errors.")
        self._filter_action.triggered.connect(self._on_toggle_filter_errors)
        tools_menu.addAction(self._filter_action)
        self._filter_active = False

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["FieldName", "Value", "Error"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.setItemDelegate(RowDivider(self._table))
        self._table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self._table)

    def _on_refresh_requested(self) -> None:
        """Emit refresh_requested so parent can flush CSV queue and refresh the list."""
        self.refresh_requested.emit()

    def _get_row_error_info(self, row: int) -> tuple[bool, bool]:
        """Return (has_field_error, has_project_error) for the row."""
        name_item = self._table.item(row, 0)
        value_item = self._table.item(row, 1)
        if name_item is None or value_item is None:
            return False, False
        data = name_item.data(Qt.ItemDataRole.UserRole)
        doc_index = data[0] if data else -1
        field_name = name_item.text() or ""
        value = value_item.text() or ""
        has_field_error = (
            _has_non_ascii(field_name)
            or _has_non_ascii(value)
            or _is_inappropriate_value(field_name, value, self._field_to_type)
        )
        has_project_error = _failed_project_validations(
            field_name, doc_index, self._doc_index_to_comments
        )
        return has_field_error, has_project_error

    def _get_error_description_for(
        self, doc_index: int, field_name: str, value: str
    ) -> str:
        """Return the error description for the Error column."""
        parts: list[str] = []
        if _failed_project_validations(
            field_name, doc_index, self._doc_index_to_comments
        ):
            comment = _get_project_comment_text(
                field_name, doc_index, self._doc_index_to_comments
            )
            if comment:
                parts.append(comment)
        has_non_ascii = _has_non_ascii(field_name) or _has_non_ascii(value)
        if has_non_ascii:
            parts.append("Non-ASCII")
        if _is_inappropriate_value(field_name, value, self._field_to_type):
            validator_name = _get_validator_name(field_name, self._field_to_type)
            if validator_name:
                parts.append(validator_name)
        return " | ".join(parts)

    def _row_has_error(self, row: int) -> bool:
        """Return True if row has field or project validation errors."""
        has_field, has_project = self._get_row_error_info(row)
        return has_field or has_project

    def _on_toggle_highlight_errors(self) -> None:
        """Toggle highlights: apply or remove row highlighting for known errors."""
        if self._highlights_applied:
            self._clear_highlights()
        else:
            self._apply_highlights()

    def _on_toggle_filter_errors(self) -> None:
        """Toggle filter: show only error rows or show all rows."""
        if self._filter_active:
            self._clear_filter()
        else:
            self._apply_filter()

    def _apply_filter(self) -> None:
        """Hide rows that have no field or project errors."""
        for row in range(self._table.rowCount()):
            self._table.setRowHidden(row, not self._row_has_error(row))
        self._filter_active = True
        self._filter_action.setText("Unfilter")

    def _clear_filter(self) -> None:
        """Show all rows."""
        for row in range(self._table.rowCount()):
            self._table.setRowHidden(row, False)
        self._filter_active = False
        self._filter_action.setText("Filter errors")

    def _apply_highlights(self) -> None:
        """Highlight rows: red for field validation failures, yellow for project validation (Comments)."""
        for row in range(self._table.rowCount()):
            has_field_error, has_project_error = self._get_row_error_info(row)
            if has_field_error:
                brush = QBrush(ERROR_BG)
            elif has_project_error:
                brush = QBrush(PROJECT_VALIDATION_BG)
            else:
                brush = QBrush()
            for col in (0, 1, 2):
                item = self._table.item(row, col)
                if item:
                    item.setBackground(brush)
        self._highlights_applied = True
        self._highlight_action.setText("Unhighlight errors")

    def _clear_highlights(self) -> None:
        """Remove all row highlights."""
        for row in range(self._table.rowCount()):
            for col in (0, 1, 2):
                item = self._table.item(row, col)
                if item:
                    item.setBackground(QBrush())
        self._highlights_applied = False
        self._highlight_action.setText("Highlight known errors")

    def showEvent(self, event):
        """Restore previous size and position when showing."""
        super().showEvent(event)
        state = load_state()
        geom_b64 = state.get("qc_quick_review_geometry")
        if geom_b64:
            try:
                geom = QByteArray(base64.b64decode(geom_b64))
                if not geom.isEmpty():
                    self.restoreGeometry(geom)
            except Exception:
                pass

    def closeEvent(self, event):
        """Save size and position when closing."""
        geom = self.saveGeometry()
        if not geom.isEmpty():
            save_state(qc_quick_review_geometry=base64.b64encode(geom.data()).decode("ascii"))
        super().closeEvent(event)

    def set_data(
        self,
        rows: list[tuple[int, str, str]],
        doc_total: int = 0,
        field_to_type: dict[str, str] | None = None,
        doc_index_to_comments: dict[int, str] | None = None,
    ) -> None:
        """
        Populate the table with (doc_index, field_name, value) rows.

        doc_index and field_name are stored for activation; field_name and value are displayed.
        field_to_type maps field_name -> type name for validation (e.g. Highlight known errors).
        doc_index_to_comments maps row index -> Comments column value for highlighting fields with QC comments.
        """
        self._field_to_type = field_to_type or {}
        self._doc_index_to_comments = doc_index_to_comments or {}
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for doc_index, field_name, value in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)
            name_item = QTableWidgetItem(field_name or "")
            value_item = QTableWidgetItem(str(value) if value is not None else "")
            # Store (doc_index, field_name) for activation; use first column's UserRole
            name_item.setData(Qt.ItemDataRole.UserRole, (doc_index, field_name))
            if doc_total:
                name_item.setToolTip(f"Document {doc_index + 1} of {doc_total}")
            self._table.setItem(row, 0, name_item)
            self._table.setItem(row, 1, value_item)
            error_text = self._get_error_description_for(doc_index, field_name, value or "")
            self._table.setItem(row, 2, QTableWidgetItem(error_text))
        self._table.setSortingEnabled(True)
        self._table.scrollToTop()
        self._clear_filter()
        self._apply_highlights()

    def _on_cell_clicked(self, row: int, column: int) -> None:
        """Emit row_activated with stored doc_index and field_name."""
        name_item = self._table.item(row, 0)
        if name_item is None:
            return
        data = name_item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return
        doc_index, field_name = data
        self.row_activated.emit(doc_index, field_name)
