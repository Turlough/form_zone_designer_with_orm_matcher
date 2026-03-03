from PyQt6.QtWidgets import QStyledItemDelegate, QTableWidget

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

DIVIDER_COLOR = QColor(200, 200, 200)
DIVIDER_HEIGHT = 3

class RowDivider(QStyledItemDelegate):
    """A divider between rows of a QTableWidget."""

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

