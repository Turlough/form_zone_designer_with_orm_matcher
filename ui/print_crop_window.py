"""Designer Print Crop window: align finished-page crop marks and preview on a real scan."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QBrush, QColor, QFont, QImage, QMouseEvent, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from field_factory import get_field_display_color
from fields import RadioGroup
from util.designer_persistence import load_print_crop, load_project_config, save_print_crop
from util.document_loader import get_document_loader_for_path
from util.fiducial_paths import (
    default_logo_write_path,
    find_fiducial_for_page,
    save_detected_fiducial,
)
from util.field_geometry_edit import hit_resize_handle
from util.field_group_align import (
    FieldGroupAlign,
    drag_group_bounds,
    hit_group_bounds,
    placed_rect,
    same_bounds,
)
from util.orm_matcher import ORMMatcher
from util.print_crop import (
    PrintCrop,
    canvas_to_crop_uv,
    clamp_print_crop,
    crop_uv_to_canvas,
    default_print_crop,
    fiducial_bbox_inside_crop,
    move_rect,
    prepare_scan_page,
    resize_rect_by_handle,
)
from util.path_utils import resolve_path_case_insensitive
from util.radio_grid_layout import expand_fields_for_display

logger = logging.getLogger(__name__)

HANDLE_CURSORS = {
    "nw": Qt.CursorShape.SizeFDiagCursor,
    "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor,
    "sw": Qt.CursorShape.SizeBDiagCursor,
    "n": Qt.CursorShape.SizeVerCursor,
    "s": Qt.CursorShape.SizeVerCursor,
    "e": Qt.CursorShape.SizeHorCursor,
    "w": Qt.CursorShape.SizeHorCursor,
}

MARK_COLORS = (
    QColor(255, 40, 120),
    QColor(255, 170, 0),
    QColor(40, 220, 180),
    QColor(160, 80, 255),
    QColor(255, 90, 40),
)
FIDUCIAL_COLOR = QColor(0, 255, 0)
FIDUCIAL_HIT_PX = 8


def _pil_to_pixmap(image: Image.Image) -> QPixmap:
    rgb = image.convert("RGB")
    arr = np.array(rgb)
    h, w, _ch = arr.shape
    q_image = QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(q_image.copy())


def _handle_points(rect: QRect) -> dict[str, tuple[int, int]]:
    cx = rect.x() + rect.width() // 2
    cy = rect.y() + rect.height() // 2
    return {
        "nw": (rect.x(), rect.y()),
        "n": (cx, rect.y()),
        "ne": (rect.x() + rect.width(), rect.y()),
        "e": (rect.x() + rect.width(), cy),
        "se": (rect.x() + rect.width(), rect.y() + rect.height()),
        "s": (cx, rect.y() + rect.height()),
        "sw": (rect.x(), rect.y() + rect.height()),
        "w": (rect.x(), cy),
    }


def _bbox_to_bounds(bbox) -> tuple[float, float, float, float]:
    (x0, y0), (x1, y1) = bbox
    return (float(x0), float(y0), float(x1 - x0), float(y1 - y0))


def _bounds_to_bbox(bounds) -> tuple[tuple[int, int], tuple[int, int]]:
    x, y, w, h = bounds
    x0, y0 = int(round(x)), int(round(y))
    return ((x0, y0), (x0 + max(1, int(round(w))), y0 + max(1, int(round(h)))))


def _draw_registration_marks(
    painter: QPainter,
    scale: float,
    marks_uv: list[tuple[float, float]],
    crop: PrintCrop | None,
) -> None:
    if not crop or not marks_uv:
        return
    font = QFont()
    font.setBold(True)
    font.setPixelSize(12)
    painter.setFont(font)
    arm = 8
    for i, (u, v) in enumerate(marks_uv):
        x, y = crop_uv_to_canvas(u, v, crop)
        px = int(x * scale)
        py = int(y * scale)
        color = MARK_COLORS[i % len(MARK_COLORS)]
        painter.setPen(QPen(QColor(0, 0, 0), 4))
        painter.drawLine(px - arm, py, px + arm, py)
        painter.drawLine(px, py - arm, px, py + arm)
        painter.setPen(QPen(color, 2))
        painter.drawLine(px - arm, py, px + arm, py)
        painter.drawLine(px, py - arm, px, py + arm)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(px - 5, py - 5, 10, 10)
        label = str(i + 1)
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.drawText(px + 8, py - 8, label)
        painter.setPen(QPen(color, 1))
        painter.drawText(px + 7, py - 9, label)


class LinkedZoomPageWidget(QLabel):
    """Page image at an externally supplied zoom factor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("QLabel { background-color: #2b2b2b; }")
        self.setMouseTracking(True)
        self.base_pixmap: Optional[QPixmap] = None
        self._scaled_pixmap: Optional[QPixmap] = None
        self.scale = 1.0

    def set_base_pixmap(self, pixmap: Optional[QPixmap]) -> None:
        self.base_pixmap = pixmap
        self._rebuild_scaled()
        self.update_display()

    def set_zoom(self, scale: float) -> None:
        self.scale = max(0.05, min(10.0, scale))
        self._rebuild_scaled()
        self.update_display()

    def _rebuild_scaled(self) -> None:
        """Scale the page image once; crop drags must not call this."""
        if not self.base_pixmap:
            self._scaled_pixmap = None
            return
        target_w = max(1, int(self.base_pixmap.width() * self.scale))
        target_h = max(1, int(self.base_pixmap.height() * self.scale))
        scaled = self.base_pixmap.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.scale = scaled.width() / self.base_pixmap.width()
        self._scaled_pixmap = scaled

    def update_display(self) -> None:
        if self._scaled_pixmap is None:
            self.clear()
            self.setFixedSize(200, 200)
            return
        self._paint_overlays()
        self.setFixedSize(self._scaled_pixmap.size())

    def _paint_overlays(self) -> None:
        if self._scaled_pixmap is None:
            return
        self.setPixmap(self._scaled_pixmap)

    def to_image(self, px: int, py: int) -> tuple[int, int]:
        if self.scale <= 0:
            return 0, 0
        return int(px / self.scale), int(py / self.scale)


class PrintCropTemplateWidget(LinkedZoomPageWidget):
    """Template page with a resizable finished-page rectangle."""

    crop_changed = pyqtSignal()
    crop_released = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.crop: Optional[PrintCrop] = None
        self.page_size = (1, 1)
        self._drag: Optional[str] = None
        self._handle: Optional[str] = None
        self._start_crop: Optional[PrintCrop] = None
        self._last_pos: Optional[tuple[int, int]] = None
        self.reg_marks: list[tuple[float, float]] = []

    def set_page(self, pixmap: QPixmap, crop: PrintCrop) -> None:
        self.page_size = (pixmap.width(), pixmap.height())
        self.crop = clamp_print_crop(crop, self.page_size)
        self.set_base_pixmap(pixmap)

    def _paint_overlays(self) -> None:
        if self._scaled_pixmap is None:
            return
        disp = QPixmap(self._scaled_pixmap)
        if self.crop:
            x, y, w, h = self.crop
            rx = int(x * self.scale)
            ry = int(y * self.scale)
            rw = int(w * self.scale)
            rh = int(h * self.scale)
            painter = QPainter(disp)
            painter.setPen(QPen(QColor(0, 200, 255), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rx, ry, rw, rh)
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            painter.setBrush(QBrush(QColor(0, 150, 255)))
            hs = 6
            for hx, hy in _handle_points(QRect(rx, ry, rw, rh)).values():
                painter.drawRect(hx - hs, hy - hs, hs * 2, hs * 2)
            _draw_registration_marks(painter, self.scale, self.reg_marks, self.crop)
            painter.end()
        self.setPixmap(disp)

    def _hit_handle(self, px: int, py: int) -> Optional[str]:
        if not self.crop:
            return None
        x, y, w, h = self.crop
        return hit_resize_handle(
            px,
            py,
            int(x * self.scale),
            int(y * self.scale),
            int(w * self.scale),
            int(h * self.scale),
        )

    def _inside_crop(self, px: int, py: int) -> bool:
        if not self.crop:
            return False
        x, y, w, h = self.crop
        rx, ry, rw, rh = int(x * self.scale), int(y * self.scale), int(w * self.scale), int(h * self.scale)
        return rx <= px <= rx + rw and ry <= py <= ry + rh

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self.crop:
            return
        pos = event.position().toPoint()
        handle = self._hit_handle(pos.x(), pos.y())
        if handle:
            self._drag = "handle"
            self._handle = handle
            self._start_crop = self.crop
            self.grabMouse()
            return
        if self._inside_crop(pos.x(), pos.y()):
            self._drag = "move"
            self._last_pos = self.to_image(pos.x(), pos.y())
            self.grabMouse()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()
        if self._drag is None:
            handle = self._hit_handle(pos.x(), pos.y())
            if handle:
                self.setCursor(HANDLE_CURSORS.get(handle, Qt.CursorShape.ArrowCursor))
            elif self._inside_crop(pos.x(), pos.y()):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        ix, iy = self.to_image(pos.x(), pos.y())
        if self._drag == "handle" and self._start_crop and self._handle:
            self.crop = resize_rect_by_handle(
                self._start_crop, self._handle, ix, iy, self.page_size
            )
            self._paint_overlays()
            self.crop_changed.emit()
        elif self._drag == "move" and self._last_pos and self.crop:
            dx = ix - self._last_pos[0]
            dy = iy - self._last_pos[1]
            self.crop = move_rect(self.crop, dx, dy, self.page_size)
            self._last_pos = (ix, iy)
            self._paint_overlays()
            self.crop_changed.emit()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.mouseGrabber() is self:
            self.releaseMouse()
        if self._drag is not None:
            self._drag = None
            self._handle = None
            self._start_crop = None
            self._last_pos = None
            self.crop_released.emit()


class PrintCropPreviewWidget(LinkedZoomPageWidget):
    """Prepared scan canvas with a draggable fiducial box and the fields that follow it.

    Dragging inside the green box moves it; an edge scales that axis; a corner
    keeps its aspect ratio. Field outlines are mapped from the matched box to the
    dragged box. Clicks outside the box place registration marks.
    """

    point_clicked = pyqtSignal(int, int)
    fiducial_adjusted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.match_box = None
        self.box = None
        self.field_list = []
        self.placeholder = "Load a cropped scan (File → Load cropped version)"
        self.preview_crop: Optional[PrintCrop] = None
        self.reg_marks: list[tuple[float, float]] = []
        self._drag_mode: Optional[str] = None
        self._press_pos: Optional[tuple[float, float]] = None
        self._press_box = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip(
            "Drag the green fiducial box onto the real mark (fields follow). "
            "Edges scale one axis; corners keep the aspect ratio. "
            "Click elsewhere to place registration points."
        )

    def set_preview(self, pixmap: Optional[QPixmap], bbox=None, field_list=None) -> None:
        self.match_box = _bbox_to_bounds(bbox) if bbox else None
        self.box = self.match_box
        self.field_list = field_list or []
        self.set_base_pixmap(pixmap)

    def is_adjusted(self) -> bool:
        if self.box is None or self.match_box is None:
            return False
        return not same_bounds(self.box, self.match_box)

    def current_bbox(self):
        return _bounds_to_bbox(self.box) if self.box is not None else None

    def _align(self) -> Optional[FieldGroupAlign]:
        if self.box is None or self.match_box is None:
            return None
        return FieldGroupAlign(
            logo=(self.match_box[0], self.match_box[1]),
            source=self.match_box,
            dest=self.box,
        )

    def _to_image_f(self, px: float, py: float) -> tuple[float, float]:
        if self.scale <= 0:
            return 0.0, 0.0
        return px / self.scale, py / self.scale

    def update_display(self) -> None:
        if not self.base_pixmap:
            self.clear()
            self.setText(self.placeholder)
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setFixedSize(400, 300)
            return
        super().update_display()

    def _paint_overlays(self) -> None:
        if self._scaled_pixmap is None:
            return
        disp = QPixmap(self._scaled_pixmap)
        painter = QPainter(disp)
        align = self._align()
        s = self.scale

        def draw(x, y, w, h, color, width):
            rx, ry, rw, rh = placed_rect(x, y, w, h, (0, 0), align)
            painter.setPen(QPen(color, width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(int(rx * s), int(ry * s), int(rw * s), int(rh * s))

        for field in expand_fields_for_display(self.field_list):
            draw(field.x, field.y, field.width, field.height, get_field_display_color(field), 2)
            if isinstance(field, RadioGroup):
                for rb in field.radio_buttons:
                    draw(rb.x, rb.y, rb.width, rb.height, get_field_display_color(rb), 1)
        if self.box is not None:
            bx, by, bw, bh = self.box
            rect = QRect(int(bx * s), int(by * s), int(bw * s), int(bh * s))
            painter.setPen(QPen(FIDUCIAL_COLOR, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.setBrush(QBrush(FIDUCIAL_COLOR))
            hs = 4
            for name, (hx, hy) in _handle_points(rect).items():
                if len(name) == 2:
                    painter.drawRect(hx - hs, hy - hs, hs * 2, hs * 2)
        _draw_registration_marks(painter, s, self.reg_marks, self.preview_crop)
        painter.end()
        self.setPixmap(disp)

    def _hit_box(self, px: float, py: float) -> Optional[str]:
        if self.box is None or self.scale <= 0:
            return None
        ix, iy = self._to_image_f(px, py)
        return hit_group_bounds(ix, iy, self.box, FIDUCIAL_HIT_PX / self.scale)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self.base_pixmap:
            return
        pos = event.position()
        mode = self._hit_box(pos.x(), pos.y())
        if mode:
            self._drag_mode = mode
            self._press_pos = self._to_image_f(pos.x(), pos.y())
            self._press_box = self.box
            self.grabMouse()
            return
        ix, iy = self.to_image(int(pos.x()), int(pos.y()))
        if 0 <= ix < self.base_pixmap.width() and 0 <= iy < self.base_pixmap.height():
            self.point_clicked.emit(ix, iy)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if self._drag_mode is None:
            mode = self._hit_box(pos.x(), pos.y())
            if mode == "move":
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            elif mode:
                self.setCursor(HANDLE_CURSORS.get(mode, Qt.CursorShape.CrossCursor))
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)
            return
        ix, iy = self._to_image_f(pos.x(), pos.y())
        dx = ix - self._press_pos[0]
        dy = iy - self._press_pos[1]
        self.box = drag_group_bounds(self._press_box, self._drag_mode, dx, dy)
        self._paint_overlays()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._drag_mode is None:
            return
        if self.mouseGrabber() is self:
            self.releaseMouse()
        self._drag_mode = None
        self._press_pos = None
        self._press_box = None
        self.fiducial_adjusted.emit()


class PrintCropWindow(QMainWindow):
    """Align crop marks on the template and confirm fiducials/fields on a real scan."""

    def __init__(
        self,
        template_pages: list,
        page_fields: list,
        json_folder: str,
        config_folder: str,
        initial_page: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Print crop")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(1280, 800)
        self.template_pages = template_pages
        self.page_fields = page_fields
        self.json_folder = json_folder
        self.config_folder = config_folder
        self.sample_pages: list = []
        self._prepared: Optional[Image.Image] = None
        self._detected_bbox = None
        self._detected_score: Optional[float] = None
        self.page_index = max(0, min(initial_page, len(template_pages) - 1)) if template_pages else 0
        self.zoom_mode = "autofit"
        self.zoom_factor = 1.0
        first_size = template_pages[0].size if template_pages else (100, 100)
        saved = load_print_crop(json_folder)
        self.crop = clamp_print_crop(saved, first_size) if saved else default_print_crop(first_size)

        file_menu = self.menuBar().addMenu("File")
        load_action = QAction("Load cropped version…", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self._load_sample)
        file_menu.addAction(load_action)

        self.left_page = PrintCropTemplateWidget(self)
        self.right_page = PrintCropPreviewWidget(self)
        self._reg_marks: list[tuple[float, float]] = []
        self.left_page.reg_marks = self._reg_marks
        self.right_page.reg_marks = self._reg_marks
        self.left_page.crop_changed.connect(self._on_crop_dragged)
        self.left_page.crop_released.connect(self._refresh_preview)
        self.right_page.point_clicked.connect(self._on_registration_clicked)
        self.right_page.fiducial_adjusted.connect(self._on_fiducial_adjusted)

        self.left_scroll = QScrollArea()
        self.left_scroll.setWidgetResizable(False)
        self.left_scroll.setStyleSheet("QScrollArea { background-color: #2b2b2b; }")
        self.left_scroll.setWidget(self.left_page)
        self.right_scroll = QScrollArea()
        self.right_scroll.setWidgetResizable(False)
        self.right_scroll.setStyleSheet("QScrollArea { background-color: #2b2b2b; }")
        self.right_scroll.setWidget(self.right_page)
        self._scroll_syncing = False
        self._link_scrollbars()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left_wrap = QWidget()
        left_layout = QVBoxLayout(left_wrap)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Template (align crop marks)"))
        left_layout.addWidget(self.left_scroll, stretch=1)
        right_wrap = QWidget()
        right_layout = QVBoxLayout(right_wrap)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(
            QLabel("Prepared scan — drag the green box onto the fiducial; click to mark points")
        )
        right_layout.addWidget(self.right_scroll, stretch=1)
        splitter.addWidget(left_wrap)
        splitter.addWidget(right_wrap)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)
        main.addWidget(splitter, stretch=1)

        controls = QHBoxLayout()
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setToolTip("Previous page")
        self.prev_btn.clicked.connect(lambda: self._step_page(-1))
        self.next_btn = QPushButton("▶")
        self.next_btn.setToolTip("Next page")
        self.next_btn.clicked.connect(lambda: self._step_page(1))
        self.page_label = QLabel()
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.page_label)

        for text, tip, slot in (
            ("⤢", "Autofit", self._zoom_autofit),
            ("↔", "Fit width", self._zoom_fit_width),
            ("↕", "Fit height", self._zoom_fit_height),
            ("+", "Zoom in", self._zoom_in),
            ("−", "Zoom out", self._zoom_out),
        ):
            btn = QToolButton()
            btn.setText(text)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            controls.addWidget(btn)

        controls.addStretch()
        self.status_label = QLabel("Load a cropped scan to preview fiducial matching.")
        self.status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        controls.addWidget(self.status_label)

        save_btn = QPushButton("Save print crop")
        save_btn.setToolTip("Write print_crop to json/project_config.json for Indexer.")
        save_btn.clicked.connect(self._save)
        self.save_fiducial_btn = QPushButton("Save detected fiducial")
        self.save_fiducial_btn.setToolTip(
            "Overwrite the default fiducial (fiducial.png or logo.png) with the scan "
            "patch inside the green box. If the box is on the wrong spot, drag it onto "
            "the real mark first (fields follow). Enabled when the match score is 0.7 "
            "or higher, or after you move the box, and the box is inside the print crop."
        )
        self.save_fiducial_btn.setEnabled(False)
        self.save_fiducial_btn.clicked.connect(self._save_detected_fiducial)
        self.clear_marks_btn = QPushButton("Clear registration marks")
        self.clear_marks_btn.setToolTip(
            "Remove clicked registration points so you can mark again."
        )
        self.clear_marks_btn.setEnabled(False)
        self.clear_marks_btn.clicked.connect(self._clear_registration_marks)
        clear_btn = QPushButton("Clear")
        clear_btn.setToolTip("Remove print_crop so Indexer stretches scans to the full template again.")
        clear_btn.clicked.connect(self._clear)
        controls.addWidget(save_btn)
        controls.addWidget(self.save_fiducial_btn)
        controls.addWidget(self.clear_marks_btn)
        controls.addWidget(clear_btn)
        main.addLayout(controls)

        self.statusBar().showMessage(
            "Click sharp marks on the right-hand scan. Matching numbered crosses appear "
            "on the template; adjust the crop until they sit on the same printed features."
        )
        self._show_current_page(run_preview=True)
        QTimer.singleShot(0, self._sync_zoom)

    def _link_scrollbars(self) -> None:
        left_v = self.left_scroll.verticalScrollBar()
        right_v = self.right_scroll.verticalScrollBar()
        left_h = self.left_scroll.horizontalScrollBar()
        right_h = self.right_scroll.horizontalScrollBar()
        left_v.valueChanged.connect(lambda v: self._mirror_scroll(right_v, v))
        right_v.valueChanged.connect(lambda v: self._mirror_scroll(left_v, v))
        left_h.valueChanged.connect(lambda v: self._mirror_scroll(right_h, v))
        right_h.valueChanged.connect(lambda v: self._mirror_scroll(left_h, v))

    def _mirror_scroll(self, bar, value: int) -> None:
        if self._scroll_syncing:
            return
        self._scroll_syncing = True
        bar.setValue(value)
        self._scroll_syncing = False

    def _current_template(self) -> Image.Image:
        return self.template_pages[self.page_index]

    def _current_page_size(self) -> tuple[int, int]:
        return self._current_template().size

    def _pages_without_fiducial(self) -> set[int]:
        config = load_project_config(self.json_folder)
        raw = config.get("pages_without_fiducial", []) if config else []
        try:
            return {int(x) for x in raw}
        except (TypeError, ValueError):
            return set()

    def _on_crop_dragged(self) -> None:
        if self.left_page.crop:
            self.crop = self.left_page.crop

    def _on_registration_clicked(self, x: int, y: int) -> None:
        crop = self.right_page.preview_crop
        if crop is None:
            return
        uv = canvas_to_crop_uv(x, y, crop)
        if uv is None:
            return
        self._reg_marks.append(uv)
        self._paint_registration()

    def _clear_registration_marks(self) -> None:
        self._reg_marks.clear()
        self._paint_registration()

    def _paint_registration(self) -> None:
        self.clear_marks_btn.setEnabled(bool(self._reg_marks))
        self.left_page._paint_overlays()
        self.right_page._paint_overlays()

    def _step_page(self, delta: int) -> None:
        nxt = self.page_index + delta
        if 0 <= nxt < len(self.template_pages):
            self.page_index = nxt
            self._reg_marks.clear()
            self.clear_marks_btn.setEnabled(False)
            self._show_current_page(run_preview=True)

    def _show_current_page(self, run_preview: bool) -> None:
        page_size = self._current_page_size()
        self.crop = clamp_print_crop(self.crop, page_size)
        self.left_page.set_page(_pil_to_pixmap(self._current_template()), self.crop)
        total = len(self.template_pages)
        self.page_label.setText(f"Page {self.page_index + 1} of {total}")
        self.prev_btn.setEnabled(self.page_index > 0)
        self.next_btn.setEnabled(self.page_index < total - 1)
        if run_preview:
            self._refresh_preview()
        self._sync_zoom()

    def _sample_dialog_start_dir(self) -> str:
        """Prefer project_config batch_folder; relative paths are from the project folder."""
        config = load_project_config(self.json_folder)
        raw = str((config or {}).get("batch_folder", "") or "").strip()
        if raw:
            folder = Path(raw)
            if not folder.is_absolute():
                folder = Path(self.config_folder) / folder
            resolved = resolve_path_case_insensitive(folder)
            if resolved is not None:
                return str(resolved if resolved.is_dir() else resolved.parent)
        project = resolve_path_case_insensitive(self.config_folder)
        return str(project) if project is not None else ""

    def _load_sample(self) -> None:
        path, _filt = QFileDialog.getOpenFileName(
            self,
            "Load cropped version",
            self._sample_dialog_start_dir(),
            "Documents (*.pdf *.tif *.tiff *.png *.jpg *.jpeg);;All files (*.*)",
        )
        if not path:
            return
        try:
            loader = get_document_loader_for_path(path)
            pages = loader.load_pages(path)
        except Exception as e:
            QMessageBox.warning(self, "Load cropped version", str(e))
            return
        if not pages:
            QMessageBox.warning(self, "Load cropped version", "No pages found in that file.")
            return
        self.sample_pages = pages
        self.setWindowTitle(f"Print crop — {Path(path).name}")
        self._reg_marks.clear()
        self.clear_marks_btn.setEnabled(False)
        self._refresh_preview()
        self._sync_zoom()

    def _refresh_preview(self) -> None:
        if self.left_page.crop:
            self.crop = self.left_page.crop
        if not self.sample_pages:
            self._clear_detected_fiducial()
            self.right_page.preview_crop = None
            self.right_page.set_preview(None)
            self.status_label.setText("Load a cropped scan to preview fiducial matching.")
            return
        if self.page_index >= len(self.sample_pages):
            self._clear_detected_fiducial()
            self.right_page.preview_crop = None
            self.right_page.set_preview(None)
            self.status_label.setText("No sample page for this template page.")
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            template_size = self._current_page_size()
            prepared = prepare_scan_page(
                self.sample_pages[self.page_index],
                template_size,
                self.crop,
            )
            fields = []
            if self.page_index < len(self.page_fields):
                fields = list(self.page_fields[self.page_index] or [])
            bbox = None
            score = None
            skipped = self.page_index in self._pages_without_fiducial()
            if skipped:
                self.status_label.setText("Page skipped (pages_without_fiducial).")
            else:
                logo_path = find_fiducial_for_page(
                    Path(self.config_folder) / "fiducials", self.page_index
                )
                if logo_path is None:
                    self.status_label.setText("No fiducial image for this page.")
                else:
                    img_cv = cv2.cvtColor(np.array(prepared), cv2.COLOR_RGB2BGR)
                    matcher = ORMMatcher(str(logo_path))
                    matcher.locate_from_cv2_image(img_cv)
                    if matcher.top_left and matcher.bottom_right:
                        bbox = (matcher.top_left, matcher.bottom_right)
                        score = matcher.best_val
                    if score is None:
                        self.status_label.setText("Fiducial not found.")
                    elif score >= 0.7:
                        self.status_label.setText(
                            f"Fiducial match: {score:.3f} — drag the green box if it is on the wrong spot."
                        )
                    else:
                        self.status_label.setText(
                            f"Fiducial match: {score:.3f} (weak — adjust the crop or drag the green box)"
                        )
            self.right_page.preview_crop = self.crop
            self.right_page.set_preview(_pil_to_pixmap(prepared), bbox, fields)
            self._set_detected_fiducial(prepared, bbox, score)
        except Exception as e:
            logger.exception("Print crop preview failed")
            self._clear_detected_fiducial()
            self.status_label.setText(f"Preview failed: {e}")
        finally:
            QApplication.restoreOverrideCursor()
        self._sync_zoom()

    def _viewport_scale(self, mode: str) -> float:
        img_w, img_h = self._current_page_size()
        if img_w <= 0 or img_h <= 0:
            return 1.0
        left = self.left_scroll.viewport().size()
        right = self.right_scroll.viewport().size()
        vw = left.width()
        vh = left.height()
        if self.sample_pages:
            vw = min(vw, max(1, right.width()))
            vh = min(vh, max(1, right.height()))
        if mode == "fit_width":
            return vw / img_w
        if mode == "fit_height":
            return vh / img_h
        return min(vw / img_w, vh / img_h)

    def _sync_zoom(self) -> None:
        if self.zoom_mode != "manual":
            self.zoom_factor = self._viewport_scale(self.zoom_mode)
        scale = max(0.05, min(10.0, self.zoom_factor))
        self.left_page.set_zoom(scale)
        self.right_page.set_zoom(scale)
        self._mirror_scroll(
            self.right_scroll.verticalScrollBar(),
            self.left_scroll.verticalScrollBar().value(),
        )
        self._mirror_scroll(
            self.right_scroll.horizontalScrollBar(),
            self.left_scroll.horizontalScrollBar().value(),
        )

    def _zoom_autofit(self) -> None:
        self.zoom_mode = "autofit"
        self._sync_zoom()

    def _zoom_fit_width(self) -> None:
        self.zoom_mode = "fit_width"
        self._sync_zoom()

    def _zoom_fit_height(self) -> None:
        self.zoom_mode = "fit_height"
        self._sync_zoom()

    def _zoom_in(self) -> None:
        self.zoom_mode = "manual"
        self.zoom_factor = min(10.0, (self.zoom_factor or 1.0) * 1.25)
        self._sync_zoom()

    def _zoom_out(self) -> None:
        self.zoom_mode = "manual"
        self.zoom_factor = max(0.05, (self.zoom_factor or 1.0) / 1.25)
        self._sync_zoom()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if getattr(self.left_page, "_drag", None):
            return
        if self.zoom_mode != "manual":
            self._sync_zoom()

    def _clear_detected_fiducial(self) -> None:
        self._prepared = None
        self._detected_bbox = None
        self._detected_score = None
        if hasattr(self, "save_fiducial_btn"):
            self.save_fiducial_btn.setEnabled(False)

    def _set_detected_fiducial(
        self,
        prepared: Image.Image,
        bbox,
        score: Optional[float],
    ) -> None:
        self._prepared = prepared
        self._detected_bbox = bbox
        self._detected_score = score
        self._update_save_fiducial_button()

    def _update_save_fiducial_button(self) -> None:
        bbox = self._detected_bbox
        good_match = self._detected_score is not None and self._detected_score >= 0.7
        ready = (
            self._prepared is not None
            and bbox is not None
            and (good_match or self.right_page.is_adjusted())
            and fiducial_bbox_inside_crop(bbox, self.crop)
        )
        self.save_fiducial_btn.setEnabled(ready)

    def _on_fiducial_adjusted(self) -> None:
        bbox = self.right_page.current_bbox()
        if bbox is None or self._prepared is None:
            return
        self._detected_bbox = bbox
        self._update_save_fiducial_button()
        if not fiducial_bbox_inside_crop(bbox, self.crop):
            self.status_label.setText(
                "Green box is outside the print crop — move it onto the pasted scan."
            )
        elif self.right_page.is_adjusted():
            (x0, y0), (x1, y1) = bbox
            self.status_label.setText(
                f"Fiducial placed by hand at {x0},{y0} ({x1 - x0}×{y1 - y0}). "
                "Save detected fiducial when fields line up."
            )

    def _fiducials_folder(self) -> Path:
        return Path(self.config_folder) / "fiducials"

    def _size_change_warning(self) -> str:
        match = self.right_page.match_box
        box = self.right_page.box
        if match is None or box is None or match[2] <= 0 or match[3] <= 0:
            return ""
        sx = box[2] / match[2]
        sy = box[3] / match[3]
        if abs(sx - 1) < 0.02 and abs(sy - 1) < 0.02:
            return ""
        return (
            f"\n\nThe box was resized ({sx:.0%} wide, {sy:.0%} high). Indexer does not "
            "rescale fields, so if the fields only line up after resizing, adjust the "
            "print crop on the left instead."
        )

    def _save_detected_fiducial(self) -> None:
        if self._prepared is None or self._detected_bbox is None:
            return
        folder = self._fiducials_folder()
        out_path = default_logo_write_path(folder)
        if self.right_page.is_adjusted():
            source_text = "placed by hand"
        elif self._detected_score is not None:
            source_text = f"score {self._detected_score:.3f}"
        else:
            source_text = "score unknown"
        exists = out_path.is_file()
        action = "Overwrite" if exists else "Save"
        reply = QMessageBox.question(
            self,
            "Save detected fiducial",
            (
                f"{action} {out_path.name} with the patch inside the green box on this scan "
                f"(page {self.page_index + 1}, {source_text})?\n\n"
                "Indexer will then match against this scanned appearance. "
                "The app does not keep a backup of the current file."
                + self._size_change_warning()
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            saved = save_detected_fiducial(folder, self._prepared, self._detected_bbox)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Save detected fiducial", f"Could not save {out_path.name}:\n{e}")
            return
        self.statusBar().showMessage(
            f"Saved {saved.name} from page {self.page_index + 1}. "
            "Page through to check pages that still use the default fiducial.",
            8000,
        )
        self._refresh_preview()

    def _save(self) -> None:
        if self.left_page.crop:
            self.crop = self.left_page.crop
        crop = clamp_print_crop(self.crop, self._current_page_size())
        save_print_crop(self.json_folder, crop)
        self.crop = crop
        self.statusBar().showMessage(
            f"Saved print_crop {crop[0]},{crop[1]} {crop[2]}×{crop[3]} — Indexer will paste scans into this rect.",
            8000,
        )

    def _clear(self) -> None:
        save_print_crop(self.json_folder, None)
        self.crop = default_print_crop(self._current_page_size())
        self._show_current_page(run_preview=True)
        self.statusBar().showMessage("Removed print_crop from project_config.json.", 8000)
