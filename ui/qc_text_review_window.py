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



class QcTextReviewWindow(QMainWindow):
    """
    Non-modal window showing a sortable table of quick_review field values.

    Columns: FieldName, Value.
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

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["FieldName", "Value"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
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

    def _on_toggle_highlight_errors(self) -> None:
        """Toggle highlights: apply or remove row highlighting for known errors."""
        if self._highlights_applied:
            self._clear_highlights()
        else:
            self._apply_highlights()

    def _apply_highlights(self) -> None:
        """Highlight rows: red for field validation failures, yellow for project validation (Comments)."""
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, 0)
            value_item = self._table.item(row, 1)
            if name_item is None or value_item is None:
                continue
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
            if has_field_error:
                brush = QBrush(ERROR_BG)
            elif has_project_error:
                brush = QBrush(PROJECT_VALIDATION_BG)
            else:
                brush = QBrush()
            for col in (0, 1):
                item = self._table.item(row, col)
                if item:
                    item.setBackground(brush)
        self._highlights_applied = True
        self._highlight_action.setText("Unhighlight errors")

    def _clear_highlights(self) -> None:
        """Remove all row highlights."""
        for row in range(self._table.rowCount()):
            for col in (0, 1):
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
        self._table.setSortingEnabled(True)
        self._table.scrollToTop()
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
