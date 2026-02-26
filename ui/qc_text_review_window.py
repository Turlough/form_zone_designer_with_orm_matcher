"""Window for QC staff to quickly review quick_review field values across a batch."""

import base64

from PyQt6.QtCore import Qt, pyqtSignal, QByteArray
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)

from util.app_state import load_state, save_state


class QcTextReviewWindow(QMainWindow):
    """
    Non-modal window showing a sortable table of quick_review field values.

    Columns: FieldName, Value.
    Clicking a row activates that field in the main Indexing app (navigate to doc,
    show thumbnail and value in the right-hand panel).
    """

    # Emitted when user clicks a row. Payload: (doc_index: int, field_name: str)
    row_activated = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quick Review Special Fields")
        self.setMinimumSize(400, 300)
        self._build_ui()

    def _build_ui(self) -> None:
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
        self._table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self._table)

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

    def set_data(self, rows: list[tuple[int, str, str]], doc_total: int = 0) -> None:
        """
        Populate the table with (doc_index, field_name, value) rows.

        doc_index and field_name are stored for activation; field_name and value are displayed.
        """
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
