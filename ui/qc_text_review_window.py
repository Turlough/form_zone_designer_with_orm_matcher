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

ERROR_BG = QColor(255, 200, 200)
DIVIDER_COLOR = QColor(0x55, 0x55, 0x55)
DIVIDER_HEIGHT = 3


class _FieldTransitionDelegate(QStyledItemDelegate):
    """Draw a divider line at top of row when field_name differs from previous row."""

    def __init__(self, table: QTableWidget):
        super().__init__(table)
        self._table = table

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        row = index.row()
        col = index.column()
        if row == 0 or col != 0:
            return
        prev_item = self._table.item(row - 1, 0)
        curr_item = self._table.item(row, 0)
        if prev_item is None or curr_item is None:
            return
        prev_field = (prev_item.text() or "").strip()
        curr_field = (curr_item.text() or "").strip()
        if prev_field != curr_field:
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(DIVIDER_COLOR)
            y = option.rect.top()
            w = self._table.viewport().width()
            painter.drawRect(0, y, w, DIVIDER_HEIGHT)
            painter.restore()


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
        highlight_action = QAction("Highlight known errors", self)
        highlight_action.setToolTip(
            "Highlight rows in red: non-ASCII characters, or values that fail field validation "
            "(e.g. invalid email, date, integer, eircode)."
        )
        highlight_action.triggered.connect(self._on_highlight_known_errors)
        tools_menu.addAction(highlight_action)

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
        self._table.setItemDelegate(_FieldTransitionDelegate(self._table))
        self._table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self._table)

    def _on_refresh_requested(self) -> None:
        """Emit refresh_requested so parent can flush CSV queue and refresh the list."""
        self.refresh_requested.emit()

    def _on_highlight_known_errors(self) -> None:
        """Highlight rows in red: non-ASCII characters or values that fail field validation."""
        brush = QBrush(ERROR_BG)
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, 0)
            value_item = self._table.item(row, 1)
            if name_item is None or value_item is None:
                continue
            field_name = name_item.text() or ""
            value = value_item.text() or ""
            has_error = (
                _has_non_ascii(field_name)
                or _has_non_ascii(value)
                or _is_inappropriate_value(field_name, value, self._field_to_type)
            )
            for col in (0, 1):
                item = self._table.item(row, col)
                if item:
                    item.setBackground(brush if has_error else QBrush())

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
    ) -> None:
        """
        Populate the table with (doc_index, field_name, value) rows.

        doc_index and field_name are stored for activation; field_name and value are displayed.
        field_to_type maps field_name -> type name for validation (e.g. Highlight known errors).
        """
        self._field_to_type = field_to_type or {}
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
