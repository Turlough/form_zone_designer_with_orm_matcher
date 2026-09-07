"""GridDesigner window for designing radio grids.

Supports horizontal orientation (row = RadioGroup, columns = RadioButton names)
and vertical orientation (column = RadioGroup, rows = RadioButton names).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QToolButton,
    QRadioButton,
    QButtonGroup,
)
from PyQt6.QtCore import Qt, QRect, QPoint, QThread, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QMouseEvent, QShowEvent, QKeyEvent

from fields import RadioGrid
from field_factory import default_colour_tuple_for_type
from util.field_geometry_edit import hit_resize_handle, HANDLE_HIT_PX
from util.field_metadata import truncate_summary
from runtime_assistants.design_assistant.grid_assistant.geometry import (
    fiducial_rect_to_page,
    filter_rects_in_roi,
)

logger = logging.getLogger(__name__)

MIN_GRID_WIDTH_PX = 20
MIN_GRID_HEIGHT_PX = 20
ADD_LABEL_SHORTCUT_TTIP = "Press Enter or Tab in a label field to add another"


def question_number_prefix_from_name(name: str) -> str | None:
    """Leading numeric prefix from grid name: 1, 1.2, 1.2.3, …"""
    match = re.match(r"^(\d+(?:\.\d+)*)", name.lstrip())
    return match.group(1) if match else None


ASSISTANT_DISABLED_TTIP = (
    "Draw a grid rectangle that includes the question and answer labels, "
    "and ensure at least two answer rectangles (from Designer detection) "
    "fall inside it."
)
ASSISTANT_ENABLED_TTIP = (
    "Fill rows, columns, and metadata from the ROI image and answer rectangles "
    "(overwrites current labels)."
)


class GridAssistantWorker(QThread):
    """Background worker for Grid Designer → Assistant (external VLM)."""

    finished_ok = pyqtSignal(object)
    finished_error = pyqtSignal(str)

    def __init__(
        self,
        page_image,
        grid_rect_fiducial: tuple[int, int, int, int],
        fiducial_bbox,
        cv_rects: list,
        orientation: str,
        parent=None,
    ):
        super().__init__(parent)
        self._page_image = page_image
        self._grid_rect = grid_rect_fiducial
        self._fiducial_bbox = fiducial_bbox
        self._cv_rects = cv_rects
        self._orientation = orientation

    def run(self):
        try:
            from runtime_assistants.design_assistant.grid_assistant import analyse_grid

            result = analyse_grid(
                self._page_image,
                grid_rect_fiducial=self._grid_rect,
                fiducial_bbox=self._fiducial_bbox,
                cv_rects=self._cv_rects,
                orientation=self._orientation,
            )
            self.finished_ok.emit(result)
        except Exception as e:
            logger.exception("Grid Assistant failed")
            self.finished_error.emit(str(e))


class GridLabelLineEdit(QLineEdit):
    """Row/column label field; Enter or Tab adds the next field."""

    add_next = pyqtSignal()

    def focusNextPrevChild(self, next_child: bool) -> bool:
        if next_child:
            self.add_next.emit()
            return True
        return super().focusNextPrevChild(next_child)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Tab and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            event.accept()
            self.add_next.emit()
            return
        super().keyPressEvent(event)


class GridDesignerPageWidget(QLabel):
    """
    Displays page image + fiducial only. User draws a grid rectangle, then
    drags row/column boundaries. All coordinates output relative to fiducial.
    """

    grid_too_small = pyqtSignal()
    grid_rect_changed = pyqtSignal()

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

        self.dragging: Optional[str] = None  # 'col', 'row', 'handle', 'move', or None
        self.drag_index: int = -1
        self.last_pos: Optional[QPoint] = None
        self._resize_handle: Optional[str] = None
        self._drag_start_grid_rect: Optional[tuple[int, int, int, int]] = None
        self._drag_start_logo_pos: Optional[tuple[float, float]] = None

        self.zoom_mode = "fit_width"  # 'autofit', 'fit_width', 'fit_height', 'manual'
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

    def apply_grid_layout(
        self,
        n_rows: int,
        n_cols: int,
        row_fracs: list[float] | None = None,
        col_fracs: list[float] | None = None,
    ):
        """Set shape and optional split fractions (pads/truncates via _ensure_splits)."""
        self.n_rows = max(1, n_rows)
        self.n_cols = max(1, n_cols)
        if col_fracs is not None:
            self.col_fracs = list(col_fracs)
        elif self.n_cols >= 2:
            self.col_fracs = [i / self.n_cols for i in range(1, self.n_cols)]
        else:
            self.col_fracs = []
        if row_fracs is not None:
            self.row_fracs = list(row_fracs)
        elif self.n_rows >= 2:
            self.row_fracs = [i / self.n_rows for i in range(1, self.n_rows)]
        else:
            self.row_fracs = []
        self._ensure_splits()
        self.update_display()

    def load_grid_state(self, grid: RadioGrid):
        """Restore page widget from a saved RadioGrid."""
        self.grid_rect = (grid.x, grid.y, grid.width, grid.height)
        self.n_rows = max(1, len(grid.row_labels))
        self.n_cols = max(1, len(grid.col_labels))
        self.col_fracs = list(grid.col_fracs)
        self.row_fracs = list(grid.row_fracs)
        self._ensure_splits()
        self.is_drawing = False
        self.start_point = None
        self.current_point = None
        self.update_display()
        self.grid_rect_changed.emit()

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

            handle_pen = QPen(QColor(255, 255, 255), 1)
            handle_brush = QBrush(QColor(0, 150, 255))
            p.setPen(handle_pen)
            p.setBrush(handle_brush)
            hs = 6
            for hx, hy in self._handle_points_pixmap(rx, ry, rw, rh).values():
                p.drawRect(hx - hs, hy - hs, hs * 2, hs * 2)
            p.setBrush(Qt.BrushStyle.NoBrush)

        if self.is_drawing and self.start_point and self.current_point:
            x1 = self.start_point.x() - self.image_offset_x
            y1 = self.start_point.y() - self.image_offset_y
            x2 = self.current_point.x() - self.image_offset_x
            y2 = self.current_point.y() - self.image_offset_y
            p.setPen(QPen(QColor(0, 150, 255), 3))
            p.drawRect(QRect(QPoint(x1, y1), QPoint(x2, y2)))

        p.end()
        self.setPixmap(disp)
        self.setFixedSize(disp.size())

    def _to_image(self, px: int, py: int) -> tuple[float, float]:
        ix = (px - self.image_offset_x) / self.scale_x
        iy = (py - self.image_offset_y) / self.scale_y
        return (ix, iy)

    def _to_logo(self, px: int, py: int) -> tuple[float, float]:
        ix, iy = self._to_image(px, py)
        if self.bbox:
            ix -= self.bbox[0][0]
            iy -= self.bbox[0][1]
        return ix, iy

    @staticmethod
    def _handle_points_pixmap(rx: int, ry: int, rw: int, rh: int) -> dict[str, tuple[int, int]]:
        cx = rx + rw // 2
        cy = ry + rh // 2
        return {
            "nw": (rx, ry),
            "n": (cx, ry),
            "ne": (rx + rw, ry),
            "e": (rx + rw, cy),
            "se": (rx + rw, ry + rh),
            "s": (cx, ry + rh),
            "sw": (rx, ry + rh),
            "w": (rx, cy),
        }

    def _resize_grid_rect(self, handle: str, start: tuple[int, int, int, int], cur_x: float, cur_y: float):
        x, y, w, h = start
        if handle in ("nw", "n", "ne"):
            new_top = int(cur_y)
            bottom = y + h
            y = min(new_top, bottom - MIN_GRID_HEIGHT_PX)
            h = bottom - y
        if handle in ("sw", "s", "se"):
            h = max(MIN_GRID_HEIGHT_PX, int(cur_y) - y)
        if handle in ("nw", "w", "sw"):
            new_left = int(cur_x)
            right = x + w
            x = min(new_left, right - MIN_GRID_WIDTH_PX)
            w = right - x
        if handle in ("ne", "e", "se"):
            w = max(MIN_GRID_WIDTH_PX, int(cur_x) - x)
        self.grid_rect = (x, y, w, h)

    def _hit_resize_handle(self, pos: QPoint) -> Optional[str]:
        gr = self._grid_rect_display()
        if not gr:
            return None
        return hit_resize_handle(
            pos.x(), pos.y(),
            gr.x(), gr.y(), gr.width(), gr.height(),
            HANDLE_HIT_PX,
        )

    def _clear_drag(self):
        self.dragging = None
        self.drag_index = -1
        self.last_pos = None
        self._resize_handle = None
        self._drag_start_grid_rect = None
        self._drag_start_logo_pos = None
        if self.mouseGrabber() is self:
            self.releaseMouse()
        self.unsetCursor()

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
            handle = self._hit_resize_handle(pos)
            if handle:
                self.dragging = "handle"
                self._resize_handle = handle
                self._drag_start_grid_rect = self.grid_rect
                self.last_pos = pos
                self.grabMouse()
                return
            ci = self._hit_col_boundary(pos)
            ri = self._hit_row_boundary(pos)
            if ci is not None:
                self.dragging = "col"
                self.drag_index = ci
                self.last_pos = pos
                self.grabMouse()
                return
            if ri is not None:
                self.dragging = "row"
                self.drag_index = ri
                self.last_pos = pos
                self.grabMouse()
                return
            gr = self._grid_rect_display()
            if gr and gr.contains(pos.x(), pos.y()):
                self.dragging = "move"
                self._drag_start_logo_pos = self._to_logo(pos.x(), pos.y())
                self._drag_start_grid_rect = self.grid_rect
                self.last_pos = pos
                self.grabMouse()
                return
            return
        self.is_drawing = True
        self.start_point = pos
        self.current_point = pos

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.pos()
        if self.dragging == "handle" and self._resize_handle and self._drag_start_grid_rect:
            lx, ly = self._to_logo(pos.x(), pos.y())
            self._resize_grid_rect(self._resize_handle, self._drag_start_grid_rect, lx, ly)
            self.update_display()
            return
        if self.dragging == "move" and self._drag_start_grid_rect and self._drag_start_logo_pos:
            lx, ly = self._to_logo(pos.x(), pos.y())
            ox, oy = self._drag_start_logo_pos
            dx = int(lx - ox)
            dy = int(ly - oy)
            if dx or dy:
                x, y, w, h = self._drag_start_grid_rect
                self.grid_rect = (x + dx, y + dy, w, h)
                self.update_display()
            return
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
        if self.grid_rect is not None:
            handle = self._hit_resize_handle(pos)
            gr = self._grid_rect_display()
            if handle:
                cursors = {
                    "nw": Qt.CursorShape.SizeFDiagCursor,
                    "se": Qt.CursorShape.SizeFDiagCursor,
                    "ne": Qt.CursorShape.SizeBDiagCursor,
                    "sw": Qt.CursorShape.SizeBDiagCursor,
                    "n": Qt.CursorShape.SizeVerCursor,
                    "s": Qt.CursorShape.SizeVerCursor,
                    "e": Qt.CursorShape.SizeHorCursor,
                    "w": Qt.CursorShape.SizeHorCursor,
                }
                self.setCursor(cursors.get(handle, Qt.CursorShape.ArrowCursor))
            elif gr and gr.contains(pos.x(), pos.y()):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.unsetCursor()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        if self.dragging:
            self._clear_drag()
            self.grid_rect_changed.emit()
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
                self.grid_rect_changed.emit()
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
    """Window for designing a radio grid. Emits grid_submitted(RadioGrid) on Submit."""

    grid_submitted = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Grid Designer")
        self.setGeometry(200, 200, 900, 700)
        self.statusBar().showMessage("Add rows (questions) and columns (answers), then draw the grid on the page.")

        self._editing_grid: RadioGrid | None = None
        self._page_image = None  # PIL Image for Assistant
        self._fiducial_bbox = None
        self._cv_rects: list = []
        self._assistant_worker: GridAssistantWorker | None = None

        self.page_widget = GridDesignerPageWidget(self)
        self.page_widget.setMinimumSize(400, 400)
        self.page_widget.grid_too_small.connect(self._on_grid_too_small)
        self.page_widget.grid_rect_changed.connect(self._update_assistant_enabled)

        self.row_edits: list[QLineEdit] = []
        self.col_edits: list[QLineEdit] = []

        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)

        meta_row = QHBoxLayout()
        meta_row.addWidget(QLabel("Q#:"))
        self.question_number_edit = QLineEdit()
        self.question_number_edit.setPlaceholderText("e.g. 1.7")
        self.question_number_edit.setMaximumWidth(80)
        meta_row.addWidget(self.question_number_edit)
        meta_row.addWidget(QLabel("Name:"))
        self.grid_name_edit = QLineEdit()
        self.grid_name_edit.setPlaceholderText("Short overlay label (summary)")
        meta_row.addWidget(self.grid_name_edit, stretch=1)
        main.addLayout(meta_row)

        full_row = QHBoxLayout()
        full_row.addWidget(QLabel("Full text:"))
        self.full_text_edit = QTextEdit()
        self.full_text_edit.setPlaceholderText("Full question / stem text from the form")
        self.full_text_edit.setMaximumHeight(56)
        self.full_text_edit.setAcceptRichText(False)
        full_row.addWidget(self.full_text_edit, stretch=1)
        main.addLayout(full_row)

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
        self.assistant_btn = QPushButton("Assistant")
        self.assistant_btn.setToolTip(ASSISTANT_DISABLED_TTIP)
        self.assistant_btn.setEnabled(False)
        self.assistant_btn.clicked.connect(self._on_assistant_clicked)
        orient_row.addWidget(self.assistant_btn)
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
        add_col_btn.setToolTip(ADD_LABEL_SHORTCUT_TTIP)
        add_col_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add_col_btn.clicked.connect(lambda: self._add_col_edit(focus=True))
        mid.addWidget(add_col_btn)
        mid.addStretch()
        main.addLayout(mid)

        main.addWidget(QLabel(
            "Draw a rectangle on the page to define the grid. "
            "Then drag corner/edge handles or inner lines to match the template."
        ))

        content = QHBoxLayout()
        left_panel = QWidget()
        left_panel.setMaximumWidth(700)
        left_panel.setMinimumWidth(400)
        left_layout = QVBoxLayout(left_panel)
        left_layout.addStretch()
        self.row_label = QLabel("Rows (questions):")
        left_layout.addWidget(self.row_label)
        row_edits_widget = QWidget()
        self.row_container = QVBoxLayout(row_edits_widget)
        self._add_row_edit()
        left_layout.addWidget(row_edits_widget)
        add_row_btn = QPushButton("+ Add row")
        add_row_btn.setToolTip(ADD_LABEL_SHORTCUT_TTIP)
        add_row_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add_row_btn.clicked.connect(lambda: self._add_row_edit(focus=True))
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
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #2b2b2b; }")
        self.scroll_area.setWidget(self.page_widget)
        right_layout.addWidget(self.scroll_area, stretch=1)
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
        self.page_widget.set_fit_width()

    def _make_remove_button(self, tooltip: str) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        btn.setToolTip(tooltip)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setAutoRaise(True)
        return btn

    def _clear_row_edits(self):
        self.row_edits.clear()
        while self.row_container.count():
            item = self.row_container.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _clear_col_edits(self):
        self.col_edits.clear()
        while self.col_container.count():
            item = self.col_container.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _update_remove_buttons(self):
        # Called during __init__ while adding the first column, before row_container exists.
        row_container = getattr(self, "row_container", None)
        if row_container is not None:
            can_remove_row = len(self.row_edits) > 1
            for i in range(row_container.count()):
                w = row_container.itemAt(i).widget()
                if w is None:
                    continue
                btn = w.findChild(QToolButton)
                if btn is not None:
                    btn.setEnabled(can_remove_row)
        col_container = getattr(self, "col_container", None)
        if col_container is not None:
            can_remove_col = len(self.col_edits) > 1
            for i in range(col_container.count()):
                w = col_container.itemAt(i).widget()
                if w is None:
                    continue
                btn = w.findChild(QToolButton)
                if btn is not None:
                    btn.setEnabled(can_remove_col)

    def _remove_row_edit(self, edit: QLineEdit):
        if len(self.row_edits) <= 1:
            return
        try:
            self.row_edits.remove(edit)
        except ValueError:
            return
        wrapper = edit.parentWidget()
        if wrapper is not None:
            self.row_container.removeWidget(wrapper)
            wrapper.deleteLater()
        self._sync_grid_shape()
        self._update_remove_buttons()

    def _remove_col_edit(self, edit: QLineEdit):
        if len(self.col_edits) <= 1:
            return
        try:
            self.col_edits.remove(edit)
        except ValueError:
            return
        wrapper = edit.parentWidget()
        if wrapper is not None:
            self.col_container.removeWidget(wrapper)
            wrapper.deleteLater()
        self._sync_grid_shape()
        self._update_remove_buttons()

    def load_grid(self, grid: RadioGrid):
        """Open Grid Designer to edit an existing RadioGrid."""
        self._editing_grid = grid
        self.setWindowTitle(f"Grid Designer — {grid.name}")
        self.question_number_edit.setText(getattr(grid, "question_number", None) or "")
        self.grid_name_edit.setText(grid.name or grid.summary or "")
        self.full_text_edit.setPlainText(getattr(grid, "full_text", None) or "")
        if grid.orientation == "vertical":
            self.orient_vertical_rb.setChecked(True)
        else:
            self.orient_horizontal_rb.setChecked(True)
        self._clear_row_edits()
        self._clear_col_edits()
        for label in grid.row_labels:
            self._append_row_edit(label)
        for label in grid.col_labels:
            self._append_col_edit(label)
        if not self.row_edits:
            self._add_row_edit(focus=True)
        if not self.col_edits:
            self._add_col_edit(focus=True)
        self.page_widget.load_grid_state(grid)
        self._sync_grid_shape()
        self._update_remove_buttons()
        self._update_assistant_enabled()
        # Window may already be shown (rare); otherwise showEvent scrolls after layout.
        QTimer.singleShot(0, self._scroll_to_grid_rect)

    def set_assistant_inputs(self, page_image, fiducial_bbox, cv_rects: list | None):
        """Provide page image and detected rects for the Assistant button."""
        self._page_image = page_image
        self._fiducial_bbox = fiducial_bbox
        self._cv_rects = list(cv_rects or [])
        self._update_assistant_enabled()

    def _rects_in_roi_count(self) -> int:
        gr = self.page_widget.grid_rect
        if gr is None or not self._cv_rects:
            return 0
        roi_page = fiducial_rect_to_page(gr, self._fiducial_bbox)
        return len(filter_rects_in_roi(self._cv_rects, roi_page))

    def _update_assistant_enabled(self):
        running = self._assistant_worker is not None and self._assistant_worker.isRunning()
        ok = (
            not running
            and self._page_image is not None
            and self.page_widget.grid_rect is not None
            and self._rects_in_roi_count() >= 2
        )
        self.assistant_btn.setEnabled(ok)
        self.assistant_btn.setToolTip(
            ASSISTANT_ENABLED_TTIP if ok else ASSISTANT_DISABLED_TTIP
        )

    def _on_assistant_clicked(self):
        if self._assistant_worker is not None and self._assistant_worker.isRunning():
            return
        gr = self.page_widget.grid_rect
        if gr is None or self._page_image is None:
            self.statusBar().showMessage(ASSISTANT_DISABLED_TTIP, 6000)
            return
        if self._rects_in_roi_count() < 2:
            self.statusBar().showMessage(ASSISTANT_DISABLED_TTIP, 6000)
            return
        self.statusBar().showMessage("Grid Assistant analysing…")
        self.assistant_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        worker = GridAssistantWorker(
            self._page_image,
            gr,
            self._fiducial_bbox,
            self._cv_rects,
            "vertical" if self._orientation_is_vertical() else "horizontal",
            parent=self,
        )
        worker.finished_ok.connect(self._on_assistant_ok)
        worker.finished_error.connect(self._on_assistant_error)
        worker.finished.connect(self._on_assistant_finished)
        self._assistant_worker = worker
        worker.start()

    def _on_assistant_finished(self):
        QApplication.restoreOverrideCursor()
        self._assistant_worker = None
        self._update_assistant_enabled()

    def _on_assistant_error(self, message: str):
        self.statusBar().showMessage(f"Grid Assistant failed: {message}", 10000)

    def _on_assistant_ok(self, result):
        self._apply_assistant_result(result)

    def _apply_assistant_result(self, result):
        """Overwrite metadata, labels, and splits from AnalyseGridResult."""
        self.question_number_edit.setText(result.question_number or "")
        self.grid_name_edit.setText(result.name or result.summary or "")
        self.full_text_edit.setPlainText(result.full_text or "")

        self._clear_row_edits()
        self._clear_col_edits()
        for label in result.row_labels:
            self._append_row_edit(label)
        for label in result.col_labels:
            self._append_col_edit(label)
        if not self.row_edits:
            self._append_row_edit("Row 1")
        if not self.col_edits:
            self._append_col_edit("Column 1")

        framed = getattr(result, "grid_rect_fiducial", None)
        if framed is not None:
            self.page_widget.grid_rect = tuple(int(v) for v in framed)

        self.page_widget.apply_grid_layout(
            result.n_rows,
            result.n_cols,
            row_fracs=result.row_fracs,
            col_fracs=result.col_fracs,
        )
        self.page_widget.grid_rect_changed.emit()
        self._update_remove_buttons()
        QTimer.singleShot(0, self._scroll_to_grid_rect)

        msgs = []
        if result.warnings:
            msgs.extend(result.warnings)
        n = getattr(result, "rects_in_roi_count", 0)
        msgs.insert(
            0,
            f"Assistant filled {result.n_rows}×{result.n_cols} from {n} rectangles "
            "(grid framed to answer boxes).",
        )
        self.statusBar().showMessage(" ".join(msgs), 12000)

    def _scroll_to_grid_rect(self):
        """Center the scroll viewport on the current grid rectangle (ROI)."""
        gr = self.page_widget._grid_rect_display()
        if gr is None:
            return
        vp = self.scroll_area.viewport().size()
        if vp.width() <= 0 or vp.height() <= 0:
            return
        cx = gr.x() + gr.width() // 2
        cy = gr.y() + gr.height() // 2
        self.scroll_area.horizontalScrollBar().setValue(max(0, cx - vp.width() // 2))
        self.scroll_area.verticalScrollBar().setValue(max(0, cy - vp.height() // 2))

    def _append_row_edit(self, text: str = ""):
        e = GridLabelLineEdit()
        e.setPlaceholderText("Row label")
        e.setText(text)
        e.textChanged.connect(self._sync_grid_shape)
        e.returnPressed.connect(self._on_row_edit_enter)
        e.add_next.connect(self._on_row_edit_enter)
        remove_btn = self._make_remove_button("Remove this row")
        remove_btn.clicked.connect(lambda _checked=False, edit=e: self._remove_row_edit(edit))
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(remove_btn)
        lay.addWidget(e, stretch=1)
        self.row_edits.append(e)
        self.row_container.addWidget(row)
        self._update_remove_buttons()

    def _append_col_edit(self, text: str = ""):
        e = GridLabelLineEdit()
        e.setPlaceholderText("Column label")
        e.setText(text)
        e.textChanged.connect(self._sync_grid_shape)
        e.returnPressed.connect(self._on_col_edit_enter)
        e.add_next.connect(self._on_col_edit_enter)
        remove_btn = self._make_remove_button("Remove this column")
        remove_btn.clicked.connect(lambda _checked=False, edit=e: self._remove_col_edit(edit))
        col = QWidget()
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(e)
        lay.addWidget(remove_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.col_edits.append(e)
        self.col_container.addWidget(col)
        self._update_remove_buttons()

    def _question_number_prefix(self) -> str | None:
        qn = self.question_number_edit.text().strip()
        if qn:
            return qn
        return question_number_prefix_from_name(self.grid_name_edit.text())

    def _prefill_for_new_question(self) -> str:
        prefix = self._question_number_prefix()
        return f"{prefix} " if prefix else ""

    @staticmethod
    def _focus_label_edit(edit: QLineEdit | None) -> None:
        if edit is None:
            return
        edit.setFocus()
        edit.setCursorPosition(len(edit.text()))

    def _add_row_edit(self, *, focus: bool = False, prefill: str | None = None):
        if prefill is None and not self._orientation_is_vertical():
            prefill = self._prefill_for_new_question()
        elif prefill is None:
            prefill = ""
        self._append_row_edit(prefill)
        self._sync_grid_shape()
        if focus:
            self._focus_label_edit(self.row_edits[-1])

    def _add_col_edit(self, *, focus: bool = False, prefill: str | None = None):
        if prefill is None and self._orientation_is_vertical():
            prefill = self._prefill_for_new_question()
        elif prefill is None:
            prefill = ""
        self._append_col_edit(prefill)
        self._sync_grid_shape()
        if focus:
            self._focus_label_edit(self.col_edits[-1])

    def _on_row_edit_enter(self):
        self._add_row_edit(focus=True)
        QTimer.singleShot(
            0,
            lambda: self._focus_label_edit(self.row_edits[-1] if self.row_edits else None),
        )

    def _on_col_edit_enter(self):
        self._add_col_edit(focus=True)
        QTimer.singleShot(
            0,
            lambda: self._focus_label_edit(self.col_edits[-1] if self.col_edits else None),
        )

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

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        # Defer fit + ROI scroll until layout is applied (viewport size is 0 before show)
        if self.page_widget.base_pixmap:
            QTimer.singleShot(0, self._after_show_ready)

    def _after_show_ready(self):
        self.page_widget.update_display()
        self._scroll_to_grid_rect()
        # Second pass after maximize layout settles
        QTimer.singleShot(0, self._scroll_to_grid_rect)

    def set_page(self, pixmap: QPixmap, bbox=None):
        self.page_widget.set_image(pixmap, bbox)
        self.page_widget.set_fit_width()
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
        gx, gy, gw, gh = self.page_widget.grid_rect
        grid_name = self.grid_name_edit.text().strip()
        if not grid_name:
            grid_name = rows[0] if rows else "Grid"
        full_text = self.full_text_edit.toPlainText().strip()
        question_number = self.question_number_edit.text().strip()
        summary = truncate_summary(grid_name)
        grid = RadioGrid(
            colour=default_colour_tuple_for_type("RadioGrid"),
            name=grid_name,
            x=int(gx),
            y=int(gy),
            width=int(gw),
            height=int(gh),
            orientation="vertical" if self._orientation_is_vertical() else "horizontal",
            row_labels=rows,
            col_labels=cols,
            col_fracs=list(self.page_widget.col_fracs),
            row_fracs=list(self.page_widget.row_fracs),
            summary=summary,
            column_title=grid_name,
            full_text=full_text,
            question_number=question_number,
        )
        if self._editing_grid is not None:
            grid.grid_id = self._editing_grid.grid_id
        self.grid_submitted.emit(grid)
        self.statusBar().showMessage("Grid submitted.")
        self.close()
