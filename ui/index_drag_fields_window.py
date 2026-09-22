"""Indexer window: drag and scale the current page's fields as one group."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QRect, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from util.field_group_align import (
    Bounds,
    drag_group_bounds,
    hit_group_bounds,
    map_rect,
)

_HANDLE_PX = 8
_BG = QColor(43, 43, 43)
_OUTLINE = QColor(255, 214, 0)
_BOX = QColor(0, 170, 255)

_CURSORS = {
    "move": Qt.CursorShape.SizeAllCursor,
    "n": Qt.CursorShape.SizeVerCursor,
    "s": Qt.CursorShape.SizeVerCursor,
    "e": Qt.CursorShape.SizeHorCursor,
    "w": Qt.CursorShape.SizeHorCursor,
    "nw": Qt.CursorShape.SizeFDiagCursor,
    "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor,
    "sw": Qt.CursorShape.SizeBDiagCursor,
}


class _DragFieldsCanvas(QWidget):
    """Scan plus field outlines and one group box, in pixmap pixels."""

    def __init__(
        self,
        pixmap: QPixmap,
        outlines: list[Bounds],
        source_bounds: Bounds,
        bounds: Bounds,
        parent=None,
    ):
        super().__init__(parent)
        self._pixmap = pixmap
        self._outlines = outlines
        self._source = source_bounds
        self.bounds = bounds
        self._drag_mode: str | None = None
        self._drag_start: Bounds | None = None
        self._drag_origin: tuple[float, float] | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def result_bounds(self) -> Bounds:
        return self.bounds

    def _view_transform(self) -> tuple[float, float, float]:
        img_w = max(1, self._pixmap.width())
        img_h = max(1, self._pixmap.height())
        avail_w = max(1, self.width())
        avail_h = max(1, self.height())
        scale = min(avail_w / img_w, avail_h / img_h)
        if scale <= 0:
            scale = 1.0
        offset_x = (avail_w - img_w * scale) / 2
        offset_y = (avail_h - img_h * scale) / 2
        return scale, offset_x, offset_y

    def _widget_rect(self, rect: Bounds, scale: float, ox: float, oy: float) -> QRect:
        x, y, w, h = rect
        return QRect(
            int(round(ox + x * scale)),
            int(round(oy + y * scale)),
            max(1, int(round(w * scale))),
            max(1, int(round(h * scale))),
        )

    def _image_pos(self, pos, scale: float, ox: float, oy: float) -> tuple[float, float]:
        return ((pos.x() - ox) / scale, (pos.y() - oy) / scale)

    def _hit(self, pos) -> str | None:
        scale, ox, oy = self._view_transform()
        ix, iy = self._image_pos(pos, scale, ox, oy)
        return hit_group_bounds(ix, iy, self.bounds, _HANDLE_PX / scale)

    def paintEvent(self, event) -> None:
        scale, ox, oy = self._view_transform()
        painter = QPainter(self)
        painter.fillRect(self.rect(), _BG)
        scaled = self._pixmap.scaled(
            max(1, int(round(self._pixmap.width() * scale))),
            max(1, int(round(self._pixmap.height() * scale))),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(int(round(ox)), int(round(oy)), scaled)

        painter.setPen(QPen(_OUTLINE, 1))
        for rect in self._outlines:
            mapped = map_rect(self._source, self.bounds, rect)
            painter.drawRect(self._widget_rect(mapped, scale, ox, oy))

        box = self._widget_rect(self.bounds, scale, ox, oy)
        painter.setPen(QPen(_BOX, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box)

        painter.setBrush(_BOX)
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        half = _HANDLE_PX // 2
        x, y, w, h = box.x(), box.y(), box.width(), box.height()
        points = (
            (x, y),
            (x + w // 2, y),
            (x + w, y),
            (x + w, y + h // 2),
            (x + w, y + h),
            (x + w // 2, y + h),
            (x, y + h),
            (x, y + h // 2),
        )
        for hx, hy in points:
            painter.drawRect(hx - half, hy - half, _HANDLE_PX, _HANDLE_PX)
        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        mode = self._hit(event.position())
        if mode is None:
            return
        scale, ox, oy = self._view_transform()
        self._drag_mode = mode
        self._drag_start = self.bounds
        self._drag_origin = self._image_pos(event.position(), scale, ox, oy)
        self.setCursor(_CURSORS.get(mode, Qt.CursorShape.ArrowCursor))

    def mouseMoveEvent(self, event) -> None:
        if self._drag_mode is None or self._drag_start is None or self._drag_origin is None:
            mode = self._hit(event.position())
            self.setCursor(_CURSORS.get(mode, Qt.CursorShape.ArrowCursor))
            return
        scale, ox, oy = self._view_transform()
        ix, iy = self._image_pos(event.position(), scale, ox, oy)
        dx = ix - self._drag_origin[0]
        dy = iy - self._drag_origin[1]
        self.bounds = drag_group_bounds(self._drag_start, self._drag_mode, dx, dy)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_mode = None
        self._drag_start = None
        self._drag_origin = None
        mode = self._hit(event.position())
        self.setCursor(_CURSORS.get(mode, Qt.CursorShape.ArrowCursor))


class IndexDragFieldsWindow(QDialog):
    """Move and scale the current page's fields. Apply does not write JSON."""

    def __init__(
        self,
        parent,
        pixmap: QPixmap,
        outlines: list[Bounds],
        source_bounds: Bounds,
        bounds: Bounds,
    ):
        super().__init__(parent)
        self.setWindowTitle("Drag fields")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowState(Qt.WindowState.WindowMaximized)
        self._asked_maximize = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        hint = QLabel(
            "Drag inside the box to move all fields. "
            "Drag an edge to scale that way only. "
            "Drag a corner to scale and keep the current shape. "
            "Apply uses this placement until you leave the page.",
            self,
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._canvas = _DragFieldsCanvas(pixmap, outlines, source_bounds, bounds, self)
        layout.addWidget(self._canvas, stretch=1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        apply_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        apply_button.setText("Apply")
        apply_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_bounds(self) -> Bounds:
        return self._canvas.result_bounds()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._asked_maximize or self.isMaximized():
            return
        self._asked_maximize = True
        QTimer.singleShot(0, self.showMaximized)
