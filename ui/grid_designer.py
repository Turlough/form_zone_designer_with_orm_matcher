"""GridDesigner window for designing radio grids.

Supports horizontal orientation (row = RadioGroup, columns = RadioButton names)
and vertical orientation (column = RadioGroup, rows = RadioButton names).
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QRadioButton,
    QButtonGroup,
)
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QMouseEvent

from fields import RadioGroup, RadioButton

logger = logging.getLogger(__name__)

LABEL_MAX_LENGTH = 50
MIN_GRID_WIDTH_PX = 20
MIN_GRID_HEIGHT_PX = 20


class GridDesignerPageWidget(QLabel):
    """
    Displays page image + fiducial only. User draws a grid rectangle, then
    drags row/column boundaries. All coordinates output relative to fiducial.
    """

    grid_too_small = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("QLabel { background-color: #2b2b2b; }")
        self.setMouseTracking(True)
        self.base_pixmap: Optional[QPixmap] = None
        self.bbox = None  # (top_left, bottom_right) or None
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.image_offset_x = 0
        self.image_offset_y = 0

        self.is_drawing = False
        self.start_point: Optional[QPoint] = None
        self.current_point: Optional[QPoint] = None

        self.grid_rect: Optional[tuple[int, int, int, int]] = None  # (x, y, w, h) fiducial-relative
        self.n_cols = 2
        self.n_rows = 1
        # Column boundaries as fractions of grid width (0..1), excluding 0 and 1. len == n_cols - 1.
        self.col_fracs: list[float] = []
        self.row_fracs: list[float] = []

        self.dragging: Optional[str] = None  # 'col', 'row', or None
        self.drag_index: int = -1
        self.last_pos: Optional[QPoint] = None

        self.zoom_mode = "autofit"  # 'autofit', 'fit_width', 'fit_height', 'manual'
        self.zoom_factor = 1.0

    def set_fit_width(self):
        if not self.base_pixmap:
            return
        self.zoom_mode = "fit_width"
        self.update_display()

    def set_fit_height(self):
        if not self.base_pixmap:
            return
        self.zoom_mode = "fit_height"
        self.update_display()

    def set_autofit(self):
        if not self.base_pixmap:
            return
        self.zoom_mode = "autofit"
        self.update_display()

    def set_image(self, pixmap: QPixmap, bbox=None):
        self.base_pixmap = pixmap
        self.bbox = bbox
        self.grid_rect = None
        self.is_drawing = False
        self.start_point = None
        self.current_point = None
        self._reset_splits()
        self.update_display()

    def set_grid_shape(self, n_rows: int, n_cols: int):
        self.n_rows = max(1, n_rows)
        self.n_cols = max(1, n_cols)
        self._reset_splits()

    def _reset_splits(self):
        if self.n_cols >= 2:
            self.col_fracs = [i / self.n_cols for i in range(1, self.n_cols)]
        else:
            self.col_fracs = []
        if self.n_rows >= 2:
            self.row_fracs = [i / self.n_rows for i in range(1, self.n_rows)]
        else:
            self.row_fracs = []

    def _ensure_splits(self):
        while len(self.col_fracs) < self.n_cols - 1:
            self.col_fracs.append((len(self.col_fracs) + 1) / self.n_cols)
        self.col_fracs = self.col_fracs[: self.n_cols - 1]
        while len(self.row_fracs) < self.n_rows - 1:
            self.row_fracs.append((len(self.row_fracs) + 1) / self.n_rows)
        self.row_fracs = self.row_fracs[: self.n_rows - 1]

    def _scroll_viewport_size(self) -> QSize:
        """Size of the scroll viewport if we're inside a QScrollArea, else self.size()."""
        view = self
        while view.parent():
            p = view.parent()
            if hasattr(p, "viewport"):
                return p.viewport().size()
            view = p
        return self.size()

    def update_display(self):
        if not self.base_pixmap:
            return
        sz = self._scroll_viewport_size()
        base_w = self.base_pixmap.width()
        base_h = self.base_pixmap.height()
        if base_w <= 0 or base_h <= 0:
            return
        if self.zoom_mode == "fit_width":
            scale = sz.width() / base_w
        elif self.zoom_mode == "fit_height":
            scale = sz.height() / base_h
        elif self.zoom_mode == "manual":
            scale = self.zoom_factor
        else:
            scale = min(sz.width() / base_w, sz.height() / base_h)
        if scale <= 0:
            scale = 0.01
        target_w = int(base_w * scale)
        target_h = int(base_h * scale)
        scaled = self.base_pixmap.scaled(
            target_w, target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.scale_x = scaled.width() / base_w
        self.scale_y = scaled.height() / base_h
        self.image_offset_x = (self.width() - scaled.width()) // 2
        self.image_offset_y = (self.height() - scaled.height()) // 2

        disp = QPixmap(scaled.size())
        disp.fill(Qt.GlobalColor.transparent)
        p = QPainter(disp)
        p.drawPixmap(0, 0, scaled)

        if self.bbox:
            tl, br = self.bbox
            sx = int(tl[0] * self.scale_x)
            sy = int(tl[1] * self.scale_y)
            w = int((br[0] - tl[0]) * self.scale_x)
            h = int((br[1] - tl[1]) * self.scale_y)
            p.setPen(QPen(QColor(0, 255, 0), 1))
            p.drawRect(sx, sy, w, h)

        if self.grid_rect is not None:
            gx, gy, gw, gh = self.grid_rect
            abs_x = gx + (self.bbox[0][0] if self.bbox else 0)
            abs_y = gy + (self.bbox[0][1] if self.bbox else 0)
            rx = int(abs_x * self.scale_x)
            ry = int(abs_y * self.scale_y)
            rw = int(gw * self.scale_x)
            rh = int(gh * self.scale_y)
            p.setPen(QPen(QColor(0, 150, 255), 2))
            p.drawRect(rx, ry, rw, rh)

            self._ensure_splits()
            for f in self.col_fracs:
                xx = rx + int(rw * f)
                p.setPen(QPen(QColor(200, 200, 100), 1))
                p.drawLine(xx, ry, xx, ry + rh)
            for f in self.row_fracs:
                yy = ry + int(rh * f)
                p.setPen(QPen(QColor(200, 200, 100), 1))
                p.drawLine(rx, yy, rx + rw, yy)

        if self.is_drawing and self.start_point and self.current_point:
            x1 = self.start_point.x() - self.image_offset_x
            y1 = self.start_point.y() - self.image_offset_y
            x2 = self.current_point.x() - self.image_offset_x
            y2 = self.current_point.y() - self.image_offset_y
            p.setPen(QPen(QColor(0, 150, 255), 3))
            p.drawRect(QRect(QPoint(x1, y1), QPoint(x2, y2)))

        p.end()
        self.setPixmap(disp)

    def _to_image(self, px: int, py: int) -> tuple[float, float]:
        ix = (px - self.image_offset_x) / self.scale_x
        iy = (py - self.image_offset_y) / self.scale_y
        return (ix, iy)

    def _grid_rect_display(self) -> Optional[QRect]:
        if not self.grid_rect or not self.base_pixmap:
            return None
        gx, gy, gw, gh = self.grid_rect
        ox = self.bbox[0][0] if self.bbox else 0
        oy = self.bbox[0][1] if self.bbox else 0
        rx = int((gx + ox) * self.scale_x) + self.image_offset_x
        ry = int((gy + oy) * self.scale_y) + self.image_offset_y
        rw = int(gw * self.scale_x)
        rh = int(gh * self.scale_y)
        return QRect(rx, ry, rw, rh)

    def _hit_col_boundary(self, pos: QPoint) -> Optional[int]:
        gr = self._grid_rect_display()
        if not gr or not self.col_fracs:
            return None
        x = pos.x()
        hit = 8
        for i, f in enumerate(self.col_fracs):
            xx = gr.x() + int(gr.width() * f)
            if abs(x - xx) <= hit:
                return i
        return None

    def _hit_row_boundary(self, pos: QPoint) -> Optional[int]:
        gr = self._grid_rect_display()
        if not gr or not self.row_fracs:
            return None
        y = pos.y()
        hit = 8
        for i, f in enumerate(self.row_fracs):
            yy = gr.y() + int(gr.height() * f)
            if abs(y - yy) <= hit:
                return i
        return None

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton or not self.base_pixmap:
            super().mousePressEvent(event)
            return
        pos = event.pos()
        if self.grid_rect is not None:
            ci = self._hit_col_boundary(pos)
            ri = self._hit_row_boundary(pos)
            if ci is not None:
                self.dragging = "col"
                self.drag_index = ci
                self.last_pos = pos
                return
            if ri is not None:
                self.dragging = "row"
                self.drag_index = ri
                self.last_pos = pos
                return
        self.is_drawing = True
        self.start_point = pos
        self.current_point = pos

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.pos()
        if self.dragging == "col" and self.last_pos is not None and self.grid_rect is not None:
            gr = self._grid_rect_display()
            if gr:
                dx = (pos.x() - self.last_pos.x()) / max(1, gr.width())
                f = self.col_fracs[self.drag_index] + dx
                f = max(0.05, min(0.95, f))
                if self.drag_index > 0 and f <= self.col_fracs[self.drag_index - 1] + 0.05:
                    f = self.col_fracs[self.drag_index - 1] + 0.05
                if self.drag_index < len(self.col_fracs) - 1 and f >= self.col_fracs[self.drag_index + 1] - 0.05:
                    f = self.col_fracs[self.drag_index + 1] - 0.05
                self.col_fracs[self.drag_index] = f
                self.last_pos = pos
                self.update_display()
            return
        if self.dragging == "row" and self.last_pos is not None and self.grid_rect is not None:
            gr = self._grid_rect_display()
            if gr:
                dy = (pos.y() - self.last_pos.y()) / max(1, gr.height())
                f = self.row_fracs[self.drag_index] + dy
                f = max(0.05, min(0.95, f))
                if self.drag_index > 0 and f <= self.row_fracs[self.drag_index - 1] + 0.05:
                    f = self.row_fracs[self.drag_index - 1] + 0.05
                if self.drag_index < len(self.row_fracs) - 1 and f >= self.row_fracs[self.drag_index + 1] - 0.05:
                    f = self.row_fracs[self.drag_index + 1] - 0.05
                self.row_fracs[self.drag_index] = f
                self.last_pos = pos
                self.update_display()
            return
        if self.is_drawing:
            self.current_point = pos
            self.update_display()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        if self.dragging:
            self.dragging = None
            self.drag_index = -1
            self.last_pos = None
            return
        if self.is_drawing and self.start_point and self.current_point:
            self.is_drawing = False
            x1, y1 = self._to_image(self.start_point.x(), self.start_point.y())
            x2, y2 = self._to_image(self.current_point.x(), self.current_point.y())
            left = min(x1, x2)
            top = min(y1, y2)
            w = abs(x2 - x1)
            h = abs(y2 - y1)
            if self.bbox:
                ox, oy = self.bbox[0]
                left -= ox
                top -= oy
            if w < MIN_GRID_WIDTH_PX or h < MIN_GRID_HEIGHT_PX:
                self.grid_too_small.emit()
            else:
                self.grid_rect = (int(left), int(top), int(w), int(h))
                self._ensure_splits()
            self.start_point = None
            self.current_point = None
            self.update_display()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.base_pixmap:
            self.update_display()

    def get_cell_rects(self) -> list[list[tuple[int, int, int, int]]]:
        """Return [row][col] = (x, y, w, h) fiducial-relative."""
        if not self.grid_rect:
            return []
        self._ensure_splits()
        gx, gy, gw, gh = self.grid_rect
        cx = [0.0] + list(self.col_fracs) + [1.0]
        cy = [0.0] + list(self.row_fracs) + [1.0]
        out = []
        for i in range(len(cy) - 1):
            row = []
            y = gy + int(cy[i] * gh)
            h = int(cy[i + 1] * gh) - int(cy[i] * gh)
            for j in range(len(cx) - 1):
                x = gx + int(cx[j] * gw)
                w = int(cx[j + 1] * gw) - int(cx[j] * gw)
                row.append((x, y, w, h))
            out.append(row)
        return out


class GridDesigner(QMainWindow):
    """Window for designing a radio grid. Emits groups_submitted(list[RadioGroup]) on Submit."""

    groups_submitted = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Grid Designer")
        self.setGeometry(200, 200, 900, 700)
        self.statusBar().showMessage("Add rows (questions) and columns (answers), then draw the grid on the page.")

        self.page_widget = GridDesignerPageWidget(self)
        self.page_widget.setMinimumSize(400, 400)
        self.page_widget.grid_too_small.connect(self._on_grid_too_small)

        self.row_edits: list[QLineEdit] = []
        self.col_edits: list[QLineEdit] = []

        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)

        orient_row = QHBoxLayout()
        orient_row.addWidget(QLabel("Orientation:"))
        self.orient_horizontal_rb = QRadioButton("Horizontal (row = group)")
        self.orient_vertical_rb = QRadioButton("Vertical (column = group)")
        self.orient_horizontal_rb.setChecked(True)
        orient_group = QButtonGroup(self)
        orient_group.addButton(self.orient_horizontal_rb)
        orient_group.addButton(self.orient_vertical_rb)
        self.orient_horizontal_rb.toggled.connect(self._on_orientation_changed)
        orient_row.addWidget(self.orient_horizontal_rb)
        orient_row.addWidget(self.orient_vertical_rb)
        orient_row.addStretch()
        main.addLayout(orient_row)

        mid = QHBoxLayout()
        self.col_label = QLabel("Columns (answers):")
        self.col_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        mid.addWidget(self.col_label)
        self.col_container = QHBoxLayout()
        self._add_col_edit()
        mid.addLayout(self.col_container)
        add_col_btn = QPushButton("+ Add column")
        add_col_btn.clicked.connect(self._add_col_edit)
        mid.addWidget(add_col_btn)
        mid.addStretch()
        main.addLayout(mid)

        main.addWidget(QLabel("Draw a rectangle on the page to define the grid, then drag boundaries to match the template."))

        content = QHBoxLayout()
        left_panel = QWidget()
        left_panel.setMaximumWidth(220)
        left_layout = QVBoxLayout(left_panel)
        left_layout.addStretch()
        self.row_label = QLabel("Rows (questions):")
        left_layout.addWidget(self.row_label)
        row_edits_widget = QWidget()
        self.row_container = QVBoxLayout(row_edits_widget)
        self._add_row_edit()
        left_layout.addWidget(row_edits_widget)
        add_row_btn = QPushButton("+ Add row")
        add_row_btn.clicked.connect(self._add_row_edit)
        left_layout.addWidget(add_row_btn)
        left_layout.addStretch()
        content.addWidget(left_panel)

        right_part = QWidget()
        right_layout = QVBoxLayout(right_part)
        right_layout.setContentsMargins(0, 0, 0, 0)
        zoom_row = QHBoxLayout()
        self.autofit_button = QToolButton()
        self.autofit_button.setText("⤢")
        self.autofit_button.setToolTip("Autofit")
        self.autofit_button.clicked.connect(self.page_widget.set_autofit)
        self.autofit_button.setEnabled(False)
        zoom_row.addWidget(self.autofit_button)
        self.fit_width_button = QToolButton()
        self.fit_width_button.setText("↔")
        self.fit_width_button.setToolTip("Fit Width")
        self.fit_width_button.clicked.connect(self.page_widget.set_fit_width)
        self.fit_width_button.setEnabled(False)
        zoom_row.addWidget(self.fit_width_button)
        self.fit_height_button = QToolButton()
        self.fit_height_button.setText("↕")
        self.fit_height_button.setToolTip("Fit Height")
        self.fit_height_button.clicked.connect(self.page_widget.set_fit_height)
        self.fit_height_button.setEnabled(False)
        zoom_row.addWidget(self.fit_height_button)
        zoom_row.addStretch()
        right_layout.addLayout(zoom_row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background-color: #2b2b2b; }")
        scroll.setWidget(self.page_widget)
        right_layout.addWidget(scroll, stretch=1)
        content.addWidget(right_part, stretch=1)
        main.addLayout(content, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.submit_btn = QPushButton("Submit")
        self.submit_btn.clicked.connect(self._on_submit)
        btn_row.addWidget(self.submit_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        btn_row.addWidget(cancel_btn)
        main.addLayout(btn_row)

        self._sync_grid_shape()

    def _add_row_edit(self):
        e = QLineEdit()
        e.setPlaceholderText("Row label")
        e.setMaxLength(LABEL_MAX_LENGTH)
        e.textChanged.connect(self._sync_grid_shape)
        e.returnPressed.connect(self._on_row_edit_enter)
        self.row_edits.append(e)
        self.row_container.addWidget(e)
        self._sync_grid_shape()

    def _add_col_edit(self):
        e = QLineEdit()
        e.setPlaceholderText("Column label")
        e.setMaxLength(LABEL_MAX_LENGTH)
        e.textChanged.connect(self._sync_grid_shape)
        e.returnPressed.connect(self._on_col_edit_enter)
        self.col_edits.append(e)
        self.col_container.addWidget(e)
        self._sync_grid_shape()

    def _on_row_edit_enter(self):
        self._add_row_edit()
        self.row_edits[-1].setFocus()

    def _on_col_edit_enter(self):
        self._add_col_edit()
        self.col_edits[-1].setFocus()

    def _orientation_is_vertical(self) -> bool:
        return self.orient_vertical_rb.isChecked()

    def _on_orientation_changed(self):
        vertical = self._orientation_is_vertical()
        if vertical:
            self.row_label.setText("Rows (answers):")
            self.col_label.setText("Columns (questions):")
        else:
            self.row_label.setText("Rows (questions):")
            self.col_label.setText("Columns (answers):")

    def _sync_grid_shape(self):
        n_rows = max(1, len(self.row_edits))
        n_cols = max(1, len(self.col_edits))
        self.page_widget.set_grid_shape(n_rows, n_cols)
        if self.page_widget.grid_rect is not None:
            self.page_widget._ensure_splits()
            self.page_widget.update_display()

    def set_page(self, pixmap: QPixmap, bbox=None):
        self.page_widget.set_image(pixmap, bbox)
        self.autofit_button.setEnabled(True)
        self.fit_width_button.setEnabled(True)
        self.fit_height_button.setEnabled(True)

    def _on_grid_too_small(self):
        self.statusBar().showMessage("Grid rectangle too small. Draw a larger area.", 4000)

    def _row_labels(self) -> list[str]:
        return [e.text().strip() for e in self.row_edits]

    def _col_labels(self) -> list[str]:
        return [e.text().strip() for e in self.col_edits]

    def _validate(self) -> Optional[str]:
        rows = self._row_labels()
        cols = self._col_labels()
        vertical = self._orientation_is_vertical()
        if vertical:
            if len(rows) < 2:
                return "Vertical: add at least two rows (answers)."
            if len(cols) < 1:
                return "Vertical: add at least one column (question)."
        else:
            if len(rows) < 1:
                return "Add at least one row (question)."
            if len(cols) < 2:
                return "Add at least two columns (answers)."
        dup = [x for x in set(rows) if rows.count(x) > 1]
        if dup:
            return f"Duplicate row name: {dup[0]!r}."
        dup = [x for x in set(cols) if cols.count(x) > 1]
        if dup:
            return f"Duplicate column name: {dup[0]!r}."
        empty_rows = [i for i, r in enumerate(rows) if not r]
        if empty_rows:
            return "All row labels must be non-empty."
        empty_cols = [i for i, c in enumerate(cols) if not c]
        if empty_cols:
            return "All column labels must be non-empty."
        if self.page_widget.grid_rect is None:
            return "Draw a grid rectangle on the page first."
        return None

    def _on_submit(self):
        err = self._validate()
        if err:
            self.statusBar().showMessage(err, 5000)
            return
        rows = self._row_labels()
        cols = self._col_labels()
        cells = self.page_widget.get_cell_rects()
        if len(cells) != len(rows) or (cells and len(cells[0]) != len(cols)):
            self.statusBar().showMessage("Grid shape mismatch.", 4000)
            return
        groups: list[RadioGroup] = []
        if self._orientation_is_vertical():
            for j, col_name in enumerate(cols):
                buttons: list[RadioButton] = []
                for i, row_name in enumerate(rows):
                    x, y, w, h = cells[i][j]
                    rb = RadioButton(
                        colour=(100, 150, 0),
                        name=row_name,
                        x=x, y=y, width=w, height=h,
                    )
                    buttons.append(rb)
                col_height = sum(cells[k][j][3] for k in range(len(rows)))
                rg = RadioGroup(
                    colour=(100, 150, 0),
                    name=col_name,
                    x=cells[0][j][0],
                    y=cells[0][j][1],
                    width=cells[0][j][2],
                    height=col_height,
                    radio_buttons=buttons,
                )
                groups.append(rg)
        else:
            for i, row_name in enumerate(rows):
                buttons: list[RadioButton] = []
                for j, col_name in enumerate(cols):
                    x, y, w, h = cells[i][j]
                    rb = RadioButton(
                        colour=(100, 150, 0),
                        name=col_name,
                        x=x, y=y, width=w, height=h,
                    )
                    buttons.append(rb)
                rg = RadioGroup(
                    colour=(100, 150, 0),
                    name=row_name,
                    x=cells[i][0][0],
                    y=cells[i][0][1],
                    width=sum(cells[i][k][2] for k in range(len(cols))),
                    height=cells[i][0][3],
                    radio_buttons=buttons,
                )
                groups.append(rg)
        self.groups_submitted.emit(groups)
        self.statusBar().showMessage("Grid submitted.")
        self.close()
