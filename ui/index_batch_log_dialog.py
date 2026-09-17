"""Modal table of the current batch's batch.log events."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QDialog,
    QDialogButtonBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from util.batch_log import LOG_COLUMNS


class IndexBatchLogDialog(QDialog):
    """Tabulate batch.log rows; size to the table; Close only."""

    def __init__(self, parent=None, *, rows: list[tuple[str, ...]] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Batch log")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self._table = QTableWidget(0, len(LOG_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(list(LOG_COLUMNS))
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        layout.addWidget(self._table, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, alignment=Qt.AlignmentFlag.AlignRight)

        self.set_rows(rows or [])

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._size_to_fit()

    def set_rows(self, rows: list[tuple[str, ...]]) -> None:
        table = self._table
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                table.setItem(r, c, item)
        table.resizeColumnsToContents()
        table.resizeRowsToContents()
        self._size_to_fit()

    def _size_to_fit(self) -> None:
        self.adjustSize()
        screen = self.screen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        max_w = int(avail.width() * 0.9)
        max_h = int(avail.height() * 0.8)
        self.resize(min(self.width(), max_w), min(self.height(), max_h))
