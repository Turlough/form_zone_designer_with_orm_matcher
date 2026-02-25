"""
Field Review app: QC staff review specific fields from a single batch.

Fields to review are defined in project_config.json under "always_review".
User selects a field from the Field menu, then loads a batch folder.
Displays a grid of field thumbnails with editable values.
"""
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QRect, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QColor, QFont, QFontMetrics, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from dotenv import load_dotenv
from fields import Field
from util.document_loader import get_document_loader_for_path
from util.orm_matcher import ORMMatcher
from util.path_utils import find_file_case_insensitive, resolve_path_case_insensitive
from util.csv_manager import CSVManager

VALUE_FONT_SIZE = 14
VALUE_OFFSET = 8  # Gap between thumbnail and value (matches index_main_image_panel)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

num_rows = 5
num_cols = 4   

@dataclass
class ReviewItem:
    """A single field instance to review: one document row, one field."""

    batch_name: str
    doc_path: str
    csv_path: str  # Path to batch import file for saving edits
    row_index: int
    field_name: str
    field_value: str
    thumbnail: QPixmap | np.ndarray | None = None  # ndarray from worker; convert to QPixmap on main thread


def _load_project_config(config_folder: Path) -> dict | None:
    """Load project_config.json for the project."""
    json_folder = config_folder / "json"
    config_path = find_file_case_insensitive(json_folder, "project_config.json")
    if config_path is None:
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Could not read project_config.json at %s: %s", config_path, e)
        return None


def _find_logo_path(config_folder: Path) -> str | None:
    """Find logo/fiducial image in project fiducials folder."""
    fiducials = config_folder / "fiducials"
    for candidate in ["logo.png", "logo.tif", "fiducial.png", "fiducial.jpg"]:
        found = find_file_case_insensitive(fiducials, candidate)
        if found is not None:
            return str(found)
    return None


def _crop_field_thumbnail(
    pil_image: Image.Image,
    field: Field,
    bbox: tuple[tuple[int, int], tuple[int, int]] | None,
) -> Image.Image:
    """Crop the field rectangle from the page image. Returns PIL Image."""
    logo_offset = bbox[0] if bbox else (0, 0)
    abs_x = field.x + logo_offset[0]
    abs_y = field.y + logo_offset[1]
    abs_w = field.width
    abs_h = field.height

    # Clamp to image bounds
    w, h = pil_image.size
    x1 = max(0, min(abs_x, w - 1))
    y1 = max(0, min(abs_y, h - 1))
    x2 = max(x1 + 1, min(abs_x + abs_w, w))
    y2 = max(y1 + 1, min(abs_y + abs_h, h))

    return pil_image.crop((x1, y1, x2, y2))


def _pil_to_qpixmap(pil_img: Image.Image, max_size: int = 120) -> QPixmap:
    """Convert PIL Image to QPixmap, scaled to fit max_size."""
    img_array = np.array(pil_img.convert("RGB"))
    return _numpy_to_qpixmap(img_array, max_size)


def _numpy_to_qpixmap(arr: np.ndarray, max_size: int = 120) -> QPixmap:
    """Convert RGB numpy array to QPixmap, scaled to fit max_size."""
    h, w, ch = arr.shape
    bytes_per_line = ch * w
    qimg = QImage(arr.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
    pixmap = QPixmap.fromImage(qimg)
    if pixmap.width() > max_size or pixmap.height() > max_size:
        pixmap = pixmap.scaled(
            max_size, max_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return pixmap


def _generate_one_thumbnail(
    doc_path: str,
    field_obj: Field,
    page_idx: int,
    logo_path: str | None,
    pages_without_fiducial: set[int],
) -> np.ndarray | None:
    """
    Generate thumbnail for one document. Runs in worker thread.
    Returns RGB numpy array or None on failure.
    """
    try:
        loader = get_document_loader_for_path(doc_path)
        pages = loader.load_pages(doc_path)
        if page_idx >= len(pages):
            return None

        pil_page = pages[page_idx]
        bbox = None
        if logo_path and page_idx not in pages_without_fiducial:
            matcher = ORMMatcher(logo_path)
            img_cv = cv2.cvtColor(np.array(pil_page), cv2.COLOR_RGB2BGR)
            matcher.locate_from_cv2_image(img_cv)
            if matcher.top_left and matcher.bottom_right:
                bbox = (matcher.top_left, matcher.bottom_right)

        cropped = _crop_field_thumbnail(pil_page, field_obj, bbox)
        return np.array(cropped.convert("RGB"))
    except Exception as e:
        logger.debug("Could not generate thumbnail for %s: %s", doc_path, e)
        return None


def _collect_review_items(
    config_folder: Path,
    batch_folder: Path,
    import_filename: str,
    review_field_name: str,
) -> tuple[list[ReviewItem], Field, int, str | None]:
    """
    Collect review items from a single batch folder (metadata only, no thumbnails).
    Returns (items, field_obj, page_idx, logo_path).
    """
    json_folder = config_folder / "json"
    items: list[ReviewItem] = []

    field_to_page = CSVManager().get_field_to_page(str(json_folder))
    page_num = field_to_page.get(review_field_name)
    if page_num is None:
        logger.warning("Field %s not found in project JSON", review_field_name)
        return items, None, 0, None

    page_idx = page_num - 1
    fields = _load_page_fields_for_review(json_folder, page_num)
    field_obj = next((f for f in fields if f.name == review_field_name), None)
    if field_obj is None:
        return items, None, 0, None

    logo_path = _find_logo_path(config_folder)

    import_path = find_file_case_insensitive(batch_folder, import_filename)
    if import_path is None:
        logger.warning("Import file %s not found in %s", import_filename, batch_folder)
        return items, field_obj, page_idx, logo_path

    batch_name = batch_folder.name
    csv_manager = CSVManager()
    try:
        csv_manager.load_csv(str(import_path), str(json_folder))
    except Exception as e:
        logger.warning("Could not load CSV for batch %s: %s", batch_name, e)
        return items, field_obj, page_idx, logo_path

    if review_field_name not in csv_manager.field_names:
        logger.warning("Field %s not in batch %s", review_field_name, batch_name)
        return items, field_obj, page_idx, logo_path

    doc_paths = csv_manager.get_document_paths()
    for row_idx, rel_path in enumerate(doc_paths):
        if not rel_path.strip():
            continue
        abs_path = csv_manager.get_absolute_document_path(rel_path)
        resolved = resolve_path_case_insensitive(abs_path)
        if resolved is None or not resolved.is_file():
            logger.debug("Document not found: %s", abs_path)
            continue

        value = csv_manager.get_field_value(row_idx, review_field_name)
        value_str = "" if value is None else str(value).strip()

        items.append(
            ReviewItem(
                batch_name=batch_name,
                doc_path=str(resolved),
                csv_path=str(import_path),
                row_index=row_idx,
                field_name=review_field_name,
                field_value=value_str,
                thumbnail=None,
            )
        )

    return items, field_obj, page_idx, logo_path


class LoadBatchWorker(QThread):
    """Background worker: collect items from one batch, emit immediately; load thumbnails in parallel."""

    items_ready = pyqtSignal(list, str)  # items (no thumbnails), review_field_name
    thumbnail_ready = pyqtSignal(int, object)  # index, numpy array
    finished = pyqtSignal(str)  # review_field_name
    progress = pyqtSignal(str)

    def __init__(
        self,
        config_folder: Path,
        batch_folder: Path,
        import_filename: str,
        review_field_name: str,
        pages_without_fiducial: set[int],
    ):
        super().__init__()
        self.config_folder = config_folder
        self.batch_folder = batch_folder
        self.import_filename = import_filename
        self.review_field_name = review_field_name
        self.pages_without_fiducial = pages_without_fiducial

    def run(self) -> None:
        self.progress.emit("Collecting documents...")
        items, field_obj, page_idx, logo_path = _collect_review_items(
            self.config_folder,
            self.batch_folder,
            self.import_filename,
            self.review_field_name,
        )
        if self.isInterruptionRequested():
            self.finished.emit(self.review_field_name)
            return
        if not items:
            self.items_ready.emit([], self.review_field_name)
            self.finished.emit(self.review_field_name)
            return
        if field_obj is None:
            self.items_ready.emit([], self.review_field_name)
            self.finished.emit(self.review_field_name)
            return

        self.items_ready.emit(items, self.review_field_name)
        self.progress.emit(f"Loading {len(items)} thumbnails...")

        pages_without = self.pages_without_fiducial
        max_workers = min(8, os.cpu_count() or 4)

        def make_thumbnail(idx: int) -> tuple[int, np.ndarray | None]:
            item = items[idx]
            arr = _generate_one_thumbnail(
                doc_path=item.doc_path,
                field_obj=field_obj,
                page_idx=page_idx,
                logo_path=logo_path,
                pages_without_fiducial=pages_without,
            )
            return (idx, arr)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(make_thumbnail, i): i for i in range(len(items))}
            for future in as_completed(futures):
                if self.isInterruptionRequested():
                    break
                idx, arr = future.result()
                if arr is not None:
                    self.thumbnail_ready.emit(idx, arr)

        self.finished.emit(self.review_field_name)


def _cancel_and_wait_worker(worker: LoadBatchWorker | None) -> None:
    """Request worker to stop and wait for it. Disconnects signals to avoid stale callbacks."""
    if worker is None or not worker.isRunning():
        return
    try:
        worker.progress.disconnect()
        worker.items_ready.disconnect()
        worker.thumbnail_ready.disconnect()
        worker.finished.disconnect()
    except RuntimeError:
        pass  # Slot already destroyed
    worker.requestInterruption()
    worker.wait()


def _load_page_fields_for_review(json_folder: Path, page_num: int) -> list[Field]:
    """Load field definitions for a page (1-based page number)."""
    json_path = find_file_case_insensitive(json_folder, f"{page_num}.json")
    if json_path is None:
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        fields = []
        for item in data:
            field = Field.from_dict(item)
            fields.append(field)
        return fields
    except Exception as e:
        logger.warning("Could not load fields from %s: %s", json_path, e)
        return []


def _paint_value_onto_pixmap(base_pixmap: QPixmap, value_str: str) -> QPixmap:
    """
    Paint the field value to the right of the thumbnail, with translucent white background.
    Matches index_main_image_panel's _draw_value_to_right style.
    """
    if base_pixmap.isNull():
        return base_pixmap
    display_text = (value_str[:30] + "…") if len(value_str) > 30 else (value_str or "(empty)")
    offset = VALUE_OFFSET
    pad_h, pad_v = 8, 4

    font = QFont()
    font.setPointSize(8)
    font.setBold(True)
    metrics = QFontMetrics(font)
    text_w = metrics.horizontalAdvance(display_text)
    text_h = metrics.height()
    value_w = text_w + pad_h * 2
    value_h = text_h + pad_v * 2

    thumb_w = base_pixmap.width()
    thumb_h = base_pixmap.height()
    # Value aligned with top of thumbnail (like scaled_rect.y())
    value_y = 0
    value_left = thumb_w + offset

    total_w = value_left + value_w
    total_h = max(thumb_h, value_h)

    result = QPixmap(total_w, total_h)
    result.fill(QColor(43, 43, 43))  # Match thumb_label background
    painter = QPainter(result)
    painter.drawPixmap(0, 0, base_pixmap)
    # Value rect to the right of thumbnail
    value_rect = QRect(value_left, value_y, value_w, value_h)
    bg_color = QColor(255, 255, 255)
    bg_color.setAlpha(int(255 * 0.8))
    painter.fillRect(value_rect, bg_color)
    painter.setPen(QColor(100, 100, 100))
    painter.setFont(font)
    painter.drawText(
        value_rect.adjusted(pad_h, pad_v, -pad_h, -pad_v),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        display_text,
    )
    painter.end()
    return result


class ReviewCellWidget(QWidget):
    """A single cell: thumbnail with value painted onto pixmap, editable value below."""

    value_changed = pyqtSignal(int, str)  # item_index, new_value

    def __init__(self, item: ReviewItem | None, item_index: int = -1, parent=None):
        super().__init__(parent)
        self.item = item
        self.item_index = item_index
        self._base_pixmap: QPixmap | None = None  # Thumbnail without overlay

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.thumb_label = QLabel()
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setMinimumSize(80, 60)
        self.thumb_label.setMaximumHeight(100)
        self.thumb_label.setStyleSheet("QLabel { background-color: #2b2b2b; border: 1px solid #444; }")
        layout.addWidget(self.thumb_label)

        self.value_edit = QLineEdit()
        self.value_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.value_edit.font()
        font.setPointSize(VALUE_FONT_SIZE)
        self.value_edit.setFont(font)
        self.value_edit.setMaximumHeight(44)
        self.value_edit.setPlaceholderText("(empty)")
        self.value_edit.editingFinished.connect(self._on_editing_finished)
        layout.addWidget(self.value_edit)

        if item:
            if item.thumbnail:
                self._base_pixmap = item.thumbnail
                self._update_thumb_with_overlay(item.field_value or "")
            else:
                self.thumb_label.setText("(no image)")
            self.value_edit.setText(item.field_value)
            self.setToolTip(f"{item.batch_name} / {item.doc_path}\nValue: {item.field_value}")
        else:
            self.thumb_label.setText("—")
            self.value_edit.setReadOnly(True)
            self.value_edit.setPlaceholderText("—")

    def _update_thumb_with_overlay(self, value_str: str) -> None:
        """Paint value onto pixmap and update thumb_label."""
        if self._base_pixmap is None or self._base_pixmap.isNull():
            return
        composite = _paint_value_onto_pixmap(self._base_pixmap, value_str)
        self.thumb_label.setPixmap(composite)

    def _on_editing_finished(self) -> None:
        if self.item_index >= 0 and self.item is not None:
            new_val = self.value_edit.text().strip()
            self.value_changed.emit(self.item_index, new_val)

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        """Update the thumbnail display (for progressive loading)."""
        self._base_pixmap = pixmap
        value_str = self.item.field_value if self.item else ""
        self._update_thumb_with_overlay(value_str or "")
        self.thumb_label.setText("")

    def set_value_overlay(self, value: str) -> None:
        """Repaint thumbnail with updated value overlay."""
        self._update_thumb_with_overlay(value)


class FieldReviewApp(QMainWindow):
    """Main window for the Field Review application."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Field Review")
        self.setGeometry(100, 100, 900, 700)

        load_dotenv()
        self.config_folder: Path | None = None
        self.batch_folder: Path | None = None
        self.matcher: ORMMatcher | None = None
        self.review_items: list[ReviewItem] = []
        self._load_worker: LoadBatchWorker | None = None
        self._cache_worker: LoadBatchWorker | None = None
        self._cell_widgets: list[ReviewCellWidget] = []  # index -> cell for thumbnail updates
        self._review_field_name = ""
        self._selected_review_field = ""  # Field chosen from Field menu
        self._field_actions: dict[str, QAction] = {}  # field_name -> action
        self._field_cache: dict[str, list[ReviewItem]] = {}  # field_name -> items with thumbnails
        self._cache_items: list[ReviewItem] = []  # temp during cache build
        self._cache_field_name = ""  # which field we're currently caching
        self._cache_batch_folder: Path | None = None  # batch we're caching for (ignore if batch changed)

        self._init_ui()

    def _init_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Menu
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        project_action = file_menu.addAction("Select project...")
        project_action.triggered.connect(self._on_select_project)

        self.load_action = file_menu.addAction("Load batch folder...")
        self.load_action.setShortcut("Ctrl+O")
        self.load_action.triggered.connect(self._on_load_batch_folder)

        # Field menu (populated when project is selected)
        self.field_menu = menubar.addMenu("Field")
        self._field_action_group = QActionGroup(self)
        self._field_action_group.setExclusive(True)

        # Instructions / status
        self.status_label = QLabel("Select a project (File → Select project...), then Load batch folder.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Grid: 
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        grid_widget = QWidget()
        self.grid_layout = QGridLayout(grid_widget)
        self.grid_layout.setSpacing(8)
        scroll.setWidget(grid_widget)
        layout.addWidget(scroll)

        self._populate_placeholder_grid()

    def closeEvent(self, event) -> None:
        """Cancel background workers before closing to avoid QThread destroyed-while-running."""
        _cancel_and_wait_worker(self._load_worker)
        _cancel_and_wait_worker(self._cache_worker)
        self._load_worker = None
        self._cache_worker = None
        super().closeEvent(event)

    def _populate_placeholder_grid(self) -> None:
        """Fill grid with placeholder cells."""
        for i in range(num_rows):
            for j in range(num_cols):
                cell = ReviewCellWidget(None)
                self.grid_layout.addWidget(cell, i, j)

    def _refresh_field_menu(self) -> None:
        """Populate Field menu from project_config always_review."""
        self.field_menu.clear()
        self._field_actions.clear()
        self._field_action_group = QActionGroup(self)
        self._field_action_group.setExclusive(True)

        if not self.config_folder:
            action = self.field_menu.addAction("(Select a project first)")
            action.setEnabled(False)
            return

        config = _load_project_config(self.config_folder)
        always_review = config.get("always_review") if config else None
        if not always_review or not isinstance(always_review, list):
            action = self.field_menu.addAction("(No always_review in config)")
            action.setEnabled(False)
            return

        if not self._selected_review_field or self._selected_review_field not in always_review:
            self._selected_review_field = always_review[0] if always_review else ""

        for field_name in always_review:
            action = QAction(field_name, self)
            action.setCheckable(True)
            action.setChecked(field_name == self._selected_review_field)
            action.triggered.connect(lambda checked, fn=field_name: self._on_field_selected(fn))
            self._field_action_group.addAction(action)
            self.field_menu.addAction(action)
            self._field_actions[field_name] = action

    def _on_field_selected(self, field_name: str) -> None:
        """Handle Field menu selection."""
        self._selected_review_field = field_name
        if field_name in self._field_actions:
            self._field_actions[field_name].setChecked(True)
        if self.batch_folder and self.config_folder:
            self._reload_current_batch()

    def _reload_current_batch(self) -> None:
        """Reload the current batch with the selected field (no folder dialog)."""
        if not self.config_folder or not self.batch_folder:
            return
        config = _load_project_config(self.config_folder)
        if not config:
            return
        import_filename = str(config.get("import_filename", "")).strip()
        if not import_filename:
            return
        raw_pages = config.get("pages_without_fiducial", [])
        pages_without_fiducial = {int(x) for x in raw_pages}
        review_field = self._selected_review_field or (config.get("always_review") or [""])[0]
        if not review_field:
            return

        # Use cache if available
        if review_field in self._field_cache:
            self._display_from_cache(review_field)
            return

        _cancel_and_wait_worker(self._load_worker)
        self._load_worker = None
        _cancel_and_wait_worker(self._cache_worker)
        self._cache_worker = None

        self.load_action.setEnabled(False)
        self.status_label.setText(f"Loading batch '{self.batch_folder.name}' for field '{review_field}'...")
        self._load_worker = LoadBatchWorker(
            config_folder=self.config_folder,
            batch_folder=self.batch_folder,
            import_filename=import_filename,
            review_field_name=review_field,
            pages_without_fiducial=pages_without_fiducial,
        )
        self._load_worker.progress.connect(self._on_load_progress)
        self._load_worker.items_ready.connect(self._on_items_ready)
        self._load_worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self._load_worker.finished.connect(self._on_load_finished)
        self._load_worker.start()

    def _display_from_cache(self, field_name: str) -> None:
        """Display items from cache (instant switch)."""
        items = self._field_cache[field_name]
        self._review_field_name = field_name
        self.review_items = items
        self._cell_widgets = []
        for i in range(num_rows):
            for j in range(num_cols):
                existing = self.grid_layout.itemAtPosition(i, j)
                if existing and existing.widget():
                    existing.widget().deleteLater()
                idx = i * num_cols + j
                item = items[idx] if idx < len(items) else None
                cell = ReviewCellWidget(item, item_index=idx)
                cell.value_changed.connect(self._on_value_changed)
                self.grid_layout.addWidget(cell, i, j)
                self._cell_widgets.append(cell)
        batch_name = self.batch_folder.name if self.batch_folder else "?"
        self.status_label.setText(f"Batch: {batch_name} | Field: {field_name} | {len(items)} items (cached)")

    def _start_cache_next_field(self) -> None:
        """Start background caching of the next field in always_review."""
        _cancel_and_wait_worker(self._cache_worker)
        self._cache_worker = None
        if not self.config_folder or not self.batch_folder:
            return
        config = _load_project_config(self.config_folder)
        if not config:
            return
        always_review = config.get("always_review")
        if not always_review or not isinstance(always_review, list):
            return
        import_filename = str(config.get("import_filename", "")).strip()
        if not import_filename:
            return
        raw_pages = config.get("pages_without_fiducial", [])
        pages_without_fiducial = {int(x) for x in raw_pages}

        # Find next uncached field
        current_idx = always_review.index(self._review_field_name) if self._review_field_name in always_review else -1
        for i in range(current_idx + 1, len(always_review)):
            next_field = always_review[i]
            if next_field not in self._field_cache:
                self._cache_field_name = next_field
                self._cache_batch_folder = self.batch_folder
                self._cache_worker = LoadBatchWorker(
                    config_folder=self.config_folder,
                    batch_folder=self.batch_folder,
                    import_filename=import_filename,
                    review_field_name=next_field,
                    pages_without_fiducial=pages_without_fiducial,
                )
                self._cache_worker.items_ready.connect(self._on_cache_items_ready)
                self._cache_worker.thumbnail_ready.connect(self._on_cache_thumbnail_ready)
                self._cache_worker.finished.connect(self._on_cache_finished)
                self._cache_worker.start()
                logger.info("Caching field '%s' in background", next_field)
                return
        # No more fields to cache

    def _on_cache_items_ready(self, items: list[ReviewItem], field_name: str) -> None:
        """Store items for cache build."""
        self._cache_items = list(items)

    def _on_cache_thumbnail_ready(self, index: int, arr: np.ndarray) -> None:
        """Update cached item with thumbnail."""
        if 0 <= index < len(self._cache_items) and arr is not None:
            pixmap = _numpy_to_qpixmap(arr)
            old = self._cache_items[index]
            self._cache_items[index] = ReviewItem(
                batch_name=old.batch_name,
                doc_path=old.doc_path,
                csv_path=old.csv_path,
                row_index=old.row_index,
                field_name=old.field_name,
                field_value=old.field_value,
                thumbnail=pixmap,
            )

    def _on_cache_finished(self, field_name: str) -> None:
        """Store completed cache and start next."""
        self._cache_worker = None
        if self._cache_batch_folder != self.batch_folder:
            self._cache_items = []
            self._cache_field_name = ""
            self._cache_batch_folder = None
            return  # Batch changed, discard cache
        if self._cache_items and self._cache_field_name:
            self._field_cache[self._cache_field_name] = list(self._cache_items)
            logger.info("Cached field '%s' (%d items)", self._cache_field_name, len(self._cache_items))
        self._cache_items = []
        self._cache_field_name = ""
        self._cache_batch_folder = None
        self._start_cache_next_field()

    def _on_select_project(self) -> None:
        default = os.getenv("DESIGNER_CONFIG_FOLDER", "")
        folder = QFileDialog.getExistingDirectory(
            self, "Select project folder", default or os.getcwd()
        )
        if not folder:
            return
        resolved = resolve_path_case_insensitive(folder)
        if resolved is None or not resolved.is_dir():
            QMessageBox.warning(self, "Invalid path", f"Folder not found: {folder}")
            return
        self.config_folder = resolved
        logo_path = _find_logo_path(self.config_folder)
        if logo_path:
            self.matcher = ORMMatcher(logo_path)
        else:
            self.matcher = None
            logger.warning("No logo found in project fiducials; thumbnails may be misaligned.")
        self._refresh_field_menu()
        self.status_label.setText(f"Project: {self.config_folder.name}. Select a field, then load a batch folder.")

    def _on_load_batch_folder(self) -> None:
        if self.config_folder is None:
            QMessageBox.warning(
                self,
                "Select project first",
                "Select a project folder (File → Select project...) before loading a batch folder.",
            )
            return

        config = _load_project_config(self.config_folder)
        if not config:
            QMessageBox.warning(
                self, "No config", "project_config.json not found or invalid in the selected project."
            )
            return

        always_review = config.get("always_review")
        if not always_review or not isinstance(always_review, list):
            QMessageBox.warning(
                self,
                "No always_review",
                "project_config.json must define 'always_review' as a list of field names.\n"
                'Example: "always_review": ["Field3", "Another field"]',
            )
            return

        default_batch = str(config.get("batch_folder", "")).strip()
        import_filename = str(config.get("import_filename", "")).strip()
        if not default_batch or not import_filename:
            QMessageBox.warning(
                self,
                "Config incomplete",
                "project_config.json must define 'batch_folder' and 'import_filename'.",
            )
            return

        default_dir = Path(default_batch)
        if not default_dir.exists():
            default_dir = Path.cwd()

        batch_folder = QFileDialog.getExistingDirectory(
            self, "Select batch folder (containing import file)", str(default_dir)
        )
        if not batch_folder:
            return

        resolved_batch = resolve_path_case_insensitive(batch_folder)
        if resolved_batch is None or not resolved_batch.is_dir():
            QMessageBox.warning(self, "Invalid path", f"Folder not found: {batch_folder}")
            return

        self.batch_folder = resolved_batch
        self._field_cache.clear()  # New batch, clear cache
        self._cache_batch_folder = None  # Invalidate any in-flight cache
        self._reload_current_batch()

    def _on_load_progress(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_items_ready(self, items: list[ReviewItem], review_field: str) -> None:
        """Populate grid immediately with values; thumbnails will arrive as they load."""
        self._review_field_name = review_field
        self._cell_widgets = []
        if not items:
            self.review_items = []
            self._populate_placeholder_grid()
            self.status_label.setText(f"No documents found for field '{review_field}'.")
            return

        self.review_items = items
        for i in range(num_rows):
            for j in range(num_cols):
                existing = self.grid_layout.itemAtPosition(i, j)
                if existing and existing.widget():
                    existing.widget().deleteLater()

                idx = i * num_cols + j
                item = items[idx] if idx < len(items) else None
                cell = ReviewCellWidget(item, item_index=idx)
                cell.value_changed.connect(self._on_value_changed)
                self.grid_layout.addWidget(cell, i, j)
                self._cell_widgets.append(cell)

        self.status_label.setText(
            f"Batch: {self.batch_folder.name} | Field: {review_field} | {len(items)} items (loading thumbnails...)"
        )

    def _on_thumbnail_ready(self, index: int, arr: np.ndarray) -> None:
        """Update the grid cell and item when a thumbnail is ready."""
        if 0 <= index < len(self._cell_widgets):
            pixmap = _numpy_to_qpixmap(arr)
            self._cell_widgets[index].set_thumbnail(pixmap)
            if index < len(self.review_items):
                old = self.review_items[index]
                self.review_items[index] = ReviewItem(
                    batch_name=old.batch_name,
                    doc_path=old.doc_path,
                    csv_path=old.csv_path,
                    row_index=old.row_index,
                    field_name=old.field_name,
                    field_value=old.field_value,
                    thumbnail=pixmap,
                )

    def _on_value_changed(self, item_index: int, new_value: str) -> None:
        """Save edited value to CSV."""
        if item_index < 0 or item_index >= len(self.review_items) or not self.config_folder:
            return
        item = self.review_items[item_index]
        json_folder = self.config_folder / "json"
        csv_manager = CSVManager()
        try:
            csv_manager.load_csv(item.csv_path, str(json_folder))
            csv_manager.set_field_value(item.row_index, item.field_name, new_value)
            csv_manager.save_csv()
            item.field_value = new_value
            if item_index < len(self._cell_widgets):
                self._cell_widgets[item_index].set_value_overlay(new_value)
            self.status_label.setText(f"Saved: {item.batch_name} / row {item.row_index + 1}")
        except Exception as e:
            logger.warning("Could not save value: %s", e)
            self.status_label.setText(f"Save failed: {e}")

    def _on_load_finished(self, review_field: str) -> None:
        self._load_worker = None
        self.load_action.setEnabled(True)
        batch_name = self.batch_folder.name if self.batch_folder else "?"
        self.status_label.setText(
            f"Batch: {batch_name} | Field: {review_field} | {len(self.review_items)} items"
        )
        # Store current field in cache (we have it loaded) and start caching next
        if self.review_items:
            self._field_cache[review_field] = list(self.review_items)
        self._start_cache_next_field()


def main() -> None:
    app = QApplication([])
    window = FieldReviewApp()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
