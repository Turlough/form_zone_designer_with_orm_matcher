"""
Field Review app: QC staff review specific fields across one or many batches.

Fields to review are defined in project_config.json under "always_review".
User selects a field from the Field menu, then loads a batch folder or a parent
folder containing multiple batch folders (at any depth).
Displays a scrollable grid of field thumbnails (column count configurable). Text fields
are edited in the value box; tickboxes and radio groups use Indexer colours and click to change.
Values save to each document's batch import CSV.
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
from PyQt6.QtCore import QEvent, QObject, QPoint, Qt, QRect, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dotenv import load_dotenv
from field_factory import get_field_display_color
from fields import Field, RadioGroup, TextField, Tickbox
from util.document_loader import get_document_loader_for_path, load_page_dimensions
from util.fiducial_paths import find_default_logo, find_fiducial_for_page
from util.orm_matcher import ORMMatcher
from util.path_utils import find_file_case_insensitive, find_project_template, resolve_path_case_insensitive
from util.csv_manager import CSVManager
from util.print_crop import parse_print_crop, prepare_scan_page

VALUE_FONT_SIZE = 14
VALUE_OFFSET = 8  # Gap between thumbnail and value (matches index_main_image_panel)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_GRID_COLS = 4


def _discover_batch_folders(root: Path, import_filename: str) -> list[Path]:
    """Find every directory under *root* that contains the batch import file."""
    if not import_filename.strip():
        return []
    found: list[Path] = []
    for dirpath, _dirnames, _filenames in os.walk(root):
        folder = Path(dirpath)
        if find_file_case_insensitive(folder, import_filename) is not None:
            found.append(folder.resolve())
    found.sort(key=lambda p: (str(p).lower()))
    return found


def _batch_folders_key(folders: list[Path]) -> tuple[str, ...]:
    return tuple(str(p.resolve()) for p in folders)


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
    """Default logo/fiducial path (per-page logo-pN.png is resolved at match time)."""
    found = find_default_logo(config_folder / "fiducials")
    return str(found) if found else None


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
    config_folder: Path | None,
    pages_without_fiducial: set[int],
    print_crop=None,
    template_size: tuple[int, int] | None = None,
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
        if template_size is not None:
            pil_page = prepare_scan_page(pil_page, template_size, print_crop)
        bbox = None
        if config_folder is not None and page_idx not in pages_without_fiducial:
            logo_path = find_fiducial_for_page(config_folder / "fiducials", page_idx)
            if logo_path is not None:
                matcher = ORMMatcher(str(logo_path))
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


def _collect_review_items_from_batches(
    config_folder: Path,
    batch_folders: list[Path],
    import_filename: str,
    review_field_name: str,
) -> tuple[list[ReviewItem], Field | None, int, str | None]:
    """Collect review items from every batch folder; preserve folder order."""
    all_items: list[ReviewItem] = []
    field_obj: Field | None = None
    page_idx = 0
    logo_path: str | None = None
    for batch_folder in batch_folders:
        items, fo, pi, lp = _collect_review_items(
            config_folder,
            batch_folder,
            import_filename,
            review_field_name,
        )
        if field_obj is None and fo is not None:
            field_obj = fo
            page_idx = pi
            logo_path = lp
        all_items.extend(items)
    return all_items, field_obj, page_idx, logo_path


class GridLayoutDialog(QDialog):
    """Choose column count; rows grow to fit all review items (scroll to see the rest)."""

    def __init__(self, cols: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Grid layout")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 50)
        self.cols_spin.setValue(cols)
        form.addRow("Columns:", self.cols_spin)
        layout.addLayout(form)
        hint = QLabel("Each field lists every document; use the scroll bar to see more rows.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def column_count(self) -> int:
        return self.cols_spin.value()


class LoadBatchWorker(QThread):
    """Background worker: collect items from one batch, emit immediately; load thumbnails in parallel."""

    items_ready = pyqtSignal(list, str, object)  # items, review_field_name, field_obj
    thumbnail_ready = pyqtSignal(int, object)  # index, numpy array
    thumbnail_progress = pyqtSignal(int, int)  # completed count, total
    finished = pyqtSignal(str)  # review_field_name
    progress = pyqtSignal(str)

    def __init__(
        self,
        config_folder: Path,
        batch_folders: list[Path],
        import_filename: str,
        review_field_name: str,
        pages_without_fiducial: set[int],
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.config_folder = config_folder
        self.batch_folders = batch_folders
        self.import_filename = import_filename
        self.review_field_name = review_field_name
        self.pages_without_fiducial = pages_without_fiducial

    def run(self) -> None:
        n_batches = len(self.batch_folders)
        if n_batches > 1:
            self.progress.emit(f"Collecting documents from {n_batches} batches...")
        else:
            self.progress.emit("Collecting documents...")
        items, field_obj, page_idx, logo_path = _collect_review_items_from_batches(
            self.config_folder,
            self.batch_folders,
            self.import_filename,
            self.review_field_name,
        )
        if self.isInterruptionRequested():
            self.finished.emit(self.review_field_name)
            return
        if not items or field_obj is None:
            self.items_ready.emit([], self.review_field_name, field_obj)
            self.finished.emit(self.review_field_name)
            return

        self.items_ready.emit(items, self.review_field_name, field_obj)
        self.progress.emit(f"Loading {len(items)} thumbnails...")

        pages_without = self.pages_without_fiducial
        config = _load_project_config(self.config_folder) or {}
        print_crop = parse_print_crop(config.get("print_crop"))
        template_size = None
        template_path = find_project_template(self.config_folder)
        if template_path is not None:
            try:
                dims = load_page_dimensions(str(template_path))
                if page_idx < len(dims):
                    template_size = dims[page_idx]
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not read template dimensions: %s", exc)
        max_workers = min(8, os.cpu_count() or 4)

        def make_thumbnail(idx: int) -> tuple[int, np.ndarray | None]:
            item = items[idx]
            arr = _generate_one_thumbnail(
                doc_path=item.doc_path,
                field_obj=field_obj,
                page_idx=page_idx,
                config_folder=self.config_folder,
                pages_without_fiducial=pages_without,
                print_crop=print_crop,
                template_size=template_size,
            )
            return (idx, arr)

        total = len(items)
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(make_thumbnail, i): i for i in range(len(items))}
            for future in as_completed(futures):
                if self.isInterruptionRequested():
                    break
                idx, arr = future.result()
                if arr is not None:
                    self.thumbnail_ready.emit(idx, arr)
                completed += 1
                self.thumbnail_progress.emit(completed, total)

        self.finished.emit(self.review_field_name)


def _disconnect_worker_signals(worker: LoadBatchWorker) -> None:
    """Disconnect worker signals so stale slots cannot fire after cancellation."""
    for signal in (
        worker.progress,
        worker.items_ready,
        worker.thumbnail_ready,
        worker.thumbnail_progress,
        worker.finished,
    ):
        try:
            signal.disconnect()
        except (RuntimeError, TypeError):
            pass


def _release_worker(worker: LoadBatchWorker | None, *, defer: bool = False) -> None:
    """Wait for the QThread to exit, then delete it. Avoids destroy-while-running crashes."""
    if worker is None:
        return

    def do_release() -> None:
        _disconnect_worker_signals(worker)
        if worker.isRunning():
            worker.requestInterruption()
        worker.wait()
        worker.deleteLater()

    if defer:
        QTimer.singleShot(0, do_release)
    else:
        do_release()


def _cancel_and_wait_worker(worker: LoadBatchWorker | None) -> None:
    """Request worker to stop and wait for it. Disconnects signals to avoid stale callbacks."""
    _release_worker(worker, defer=False)


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
        from util.radio_grid_layout import expand_fields_for_runtime
        return expand_fields_for_runtime(fields)
    except Exception as e:
        logger.warning("Could not load fields from %s: %s", json_path, e)
        return []


def _tickbox_checked_from_csv(value: str, field: Tickbox) -> bool:
    """Match Indexer tickbox semantics for CSV values."""
    if not value or not str(value).strip():
        return False
    val_lower = str(value).strip().lower()
    return (
        val_lower in ("ticked", "true", "1", "yes", "checked", "tick", "signed")
        or val_lower == field.checked_value.lower()
    )


def _radio_button_at_crop_pos(group: RadioGroup, cx: int, cy: int) -> Field | None:
    """Return the radio button under crop-local coordinates (origin = group top-left)."""
    for rb in group.radio_buttons:
        rx = rb.x - group.x
        ry = rb.y - group.y
        if rx <= cx <= rx + rb.width and ry <= cy <= ry + rb.height:
            return rb
    return None


def _is_interactive_choice_field(field: Field | None) -> bool:
    if field is None:
        return False
    if isinstance(field, RadioGroup):
        return True
    return isinstance(field, Tickbox) and not isinstance(field, TextField)


def _paint_choice_overlays_on_crop(
    pixmap: QPixmap,
    field: Field,
    csv_value: str,
    crop_w: int,
    crop_h: int,
) -> QPixmap:
    """Paint Indexer-style selection overlays on a cropped field thumbnail."""
    if pixmap.isNull() or not crop_w or not crop_h:
        return pixmap
    sx = pixmap.width() / crop_w
    sy = pixmap.height() / crop_h
    result = pixmap.copy()
    painter = QPainter(result)
    try:
        if isinstance(field, RadioGroup):
            selected = (csv_value or "").strip()
            group_color = get_field_display_color(field)
            for rb in field.radio_buttons:
                rx = int((rb.x - field.x) * sx)
                ry = int((rb.y - field.y) * sy)
                rw = max(1, int(rb.width * sx))
                rh = max(1, int(rb.height * sy))
                rect = QRect(rx, ry, rw, rh)
                is_selected = rb.name == selected
                painter.setPen(QPen(group_color, 3 if is_selected else 1))
                painter.drawRect(rect)
                if is_selected:
                    fill = QColor(get_field_display_color(rb))
                    fill.setAlpha(100)
                    painter.fillRect(rect, fill)
        elif isinstance(field, Tickbox):
            checked = _tickbox_checked_from_csv(csv_value, field)
            color = get_field_display_color(field)
            full = QRect(0, 0, pixmap.width(), pixmap.height())
            painter.setPen(QPen(color, 3 if checked else 1))
            painter.drawRect(full.adjusted(0, 0, -1, -1))
            if checked:
                fill = QColor(color)
                fill.setAlpha(100)
                painter.fillRect(full, fill)
    finally:
        painter.end()
    return result


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

    def __init__(
        self,
        item: ReviewItem | None,
        item_index: int = -1,
        review_field: Field | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.item = item
        self.item_index = item_index
        self.review_field = review_field
        self._base_pixmap: QPixmap | None = None  # Thumbnail without overlay
        self._crop_w = review_field.width if review_field else 0
        self._crop_h = review_field.height if review_field else 0
        self._choice_field = _is_interactive_choice_field(review_field)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.thumb_label = QLabel()
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setMinimumSize(80, 60)
        self.thumb_label.setMaximumHeight(100)
        self.thumb_label.setStyleSheet("QLabel { background-color: #2b2b2b; border: 1px solid #444; }")
        if self._choice_field:
            self.thumb_label.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.thumb_label)
        self.thumb_label.installEventFilter(self)

        self.value_edit = QLineEdit()
        self.value_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.value_edit.font()
        font.setPointSize(VALUE_FONT_SIZE)
        self.value_edit.setFont(font)
        self.value_edit.setMaximumHeight(44)
        self.value_edit.setPlaceholderText("(empty)")
        if self._choice_field:
            self.value_edit.setReadOnly(True)
        else:
            self.value_edit.editingFinished.connect(self._on_editing_finished)
        layout.addWidget(self.value_edit)

        if item:
            if item.thumbnail:
                self._base_pixmap = item.thumbnail
                self._update_thumb_with_overlay(item.field_value or "")
            else:
                self.thumb_label.setText("(no image)")
            self._sync_value_edit(item.field_value or "")
            self.setToolTip(f"{item.batch_name} / {item.doc_path}\nValue: {item.field_value}")
        else:
            self.thumb_label.setText("—")
            self.value_edit.setReadOnly(True)
            self.value_edit.setPlaceholderText("—")

    def _sync_value_edit(self, value_str: str) -> None:
        if isinstance(self.review_field, Tickbox):
            display = self.review_field.checked_value if _tickbox_checked_from_csv(
                value_str, self.review_field
            ) else ""
            self.value_edit.setText(display)
            self.value_edit.setPlaceholderText("(unchecked)")
        elif isinstance(self.review_field, RadioGroup):
            self.value_edit.setText(value_str)
            self.value_edit.setPlaceholderText("(none selected)")
        else:
            self.value_edit.setText(value_str)

    def _update_thumb_with_overlay(self, value_str: str) -> None:
        """Paint field-state overlays and optional value caption onto the thumbnail."""
        if self._base_pixmap is None or self._base_pixmap.isNull():
            return
        painted = self._base_pixmap
        if self.review_field is not None and self._crop_w and self._crop_h:
            painted = _paint_choice_overlays_on_crop(
                self._base_pixmap, self.review_field, value_str, self._crop_w, self._crop_h
            )
        if self._choice_field:
            composite = painted
        else:
            composite = _paint_value_onto_pixmap(painted, value_str)
        self.thumb_label.setPixmap(composite)

    def _map_label_click_to_crop_px(self, pos: QPoint) -> tuple[int, int] | None:
        composite = self.thumb_label.pixmap()
        if composite is None or composite.isNull() or self._base_pixmap is None:
            return None
        bw, bh = self._base_pixmap.width(), self._base_pixmap.height()
        cw, ch = composite.width(), composite.height()
        if not cw or not ch or not bw or not bh:
            return None
        label_w, label_h = self.thumb_label.width(), self.thumb_label.height()
        scale = min(label_w / cw, label_h / ch, 1.0)
        disp_w, disp_h = int(cw * scale), int(ch * scale)
        ox = (label_w - disp_w) // 2
        oy = (label_h - disp_h) // 2
        if not (ox <= pos.x() < ox + disp_w and oy <= pos.y() < oy + disp_h):
            return None
        cx = (pos.x() - ox) * cw / disp_w
        cy = (pos.y() - oy) * ch / disp_h
        if cx >= bw:
            return None
        crop_x = int(cx * self._crop_w / bw)
        crop_y = int(cy * self._crop_h / bh)
        return crop_x, crop_y

    def eventFilter(self, obj, event) -> bool:
        if (
            obj is self.thumb_label
            and self._choice_field
            and event.type() == QEvent.Type.MouseButtonPress
        ):
            mouse = event
            if isinstance(mouse, QMouseEvent) and mouse.button() == Qt.MouseButton.LeftButton:
                self._on_thumb_clicked(mouse.pos())
                return True
        return super().eventFilter(obj, event)

    def _on_thumb_clicked(self, pos: QPoint) -> None:
        if not self._choice_field or self.item_index < 0 or self.item is None or self.review_field is None:
            return
        mapped = self._map_label_click_to_crop_px(pos)
        if mapped is None:
            return
        cx, cy = mapped
        if isinstance(self.review_field, RadioGroup):
            rb = _radio_button_at_crop_pos(self.review_field, cx, cy)
            if rb is None:
                return
            new_val = rb.name
            if new_val == (self.item.field_value or "").strip():
                return
        elif isinstance(self.review_field, Tickbox):
            checked = _tickbox_checked_from_csv(self.item.field_value, self.review_field)
            new_val = "" if checked else self.review_field.checked_value
        else:
            return
        self.item.field_value = new_val
        self._sync_value_edit(new_val)
        self._update_thumb_with_overlay(new_val)
        self.value_changed.emit(self.item_index, new_val)

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
        self._sync_value_edit(value)


class FieldReviewApp(QMainWindow):
    """Main window for the Field Review application."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Field Review")
        self.setGeometry(100, 100, 900, 700)

        load_dotenv()
        self.config_folder: Path | None = None
        self.batch_folder: Path | None = None
        self._active_batch_folders: list[Path] = []
        self._multi_batch_root: Path | None = None
        self.num_cols = DEFAULT_GRID_COLS
        self.matcher: ORMMatcher | None = None
        self.review_items: list[ReviewItem] = []
        self._load_worker: LoadBatchWorker | None = None
        self._cache_worker: LoadBatchWorker | None = None
        self._cell_widgets: list[ReviewCellWidget] = []  # index -> cell for thumbnail updates
        self._review_field_name = ""
        self._review_field_obj: Field | None = None
        self._field_obj_cache: dict[str, Field] = {}
        self._selected_review_field = ""  # Field chosen from Field menu
        self._field_actions: dict[str, QAction] = {}  # field_name -> action
        self._field_cache: dict[str, list[ReviewItem]] = {}  # field_name -> items with thumbnails
        self._cache_items: list[ReviewItem] = []  # temp during cache build
        self._cache_field_name = ""  # which field we're currently caching
        self._cache_batch_folders_key: tuple[str, ...] | None = None

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

        self.load_multiple_action = file_menu.addAction("Load multiple batches...")
        self.load_multiple_action.triggered.connect(self._on_load_multiple_batches)

        layout_menu = menubar.addMenu("Layout")
        grid_action = layout_menu.addAction("Grid...")
        grid_action.triggered.connect(self._on_grid_layout)

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

        self.thumbnail_progress_bar = QProgressBar()
        self.thumbnail_progress_bar.setFixedHeight(16)
        self.thumbnail_progress_bar.setTextVisible(True)
        self.thumbnail_progress_bar.setFormat("Thumbnails %v / %m")
        self.thumbnail_progress_bar.setVisible(False)
        layout.addWidget(self.thumbnail_progress_bar)

        self._populate_placeholder_grid()

    def closeEvent(self, event) -> None:
        """Cancel background workers before closing to avoid QThread destroyed-while-running."""
        _cancel_and_wait_worker(self._load_worker)
        _cancel_and_wait_worker(self._cache_worker)
        self._load_worker = None
        self._cache_worker = None
        super().closeEvent(event)

    def _begin_thumbnail_progress(self, total: int) -> None:
        if total <= 0:
            self._hide_thumbnail_progress()
            return
        self.thumbnail_progress_bar.setMaximum(total)
        self.thumbnail_progress_bar.setValue(0)
        self.thumbnail_progress_bar.setVisible(True)

    def _update_thumbnail_progress(self, completed: int, total: int) -> None:
        if total <= 0:
            return
        if not self.thumbnail_progress_bar.isVisible():
            self._begin_thumbnail_progress(total)
        self.thumbnail_progress_bar.setMaximum(total)
        self.thumbnail_progress_bar.setValue(completed)

    def _hide_thumbnail_progress(self) -> None:
        self.thumbnail_progress_bar.setVisible(False)
        self.thumbnail_progress_bar.setValue(0)

    def _clear_grid_layout(self) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cell_widgets = []

    def _batch_status_label(self) -> str:
        if self._multi_batch_root is not None and len(self._active_batch_folders) > 1:
            return (
                f"{len(self._active_batch_folders)} batches under "
                f"'{self._multi_batch_root.name}'"
            )
        if self.batch_folder is not None:
            return self.batch_folder.name
        return "?"

    def _lookup_review_field_definition(self, field_name: str) -> Field | None:
        if field_name in self._field_obj_cache:
            return self._field_obj_cache[field_name]
        if not self.config_folder or not field_name:
            return None
        json_folder = self.config_folder / "json"
        field_to_page = CSVManager().get_field_to_page(str(json_folder))
        page_num = field_to_page.get(field_name)
        if page_num is None:
            return None
        fields = _load_page_fields_for_review(json_folder, page_num)
        field_obj = next((f for f in fields if f.name == field_name), None)
        if field_obj is not None:
            self._field_obj_cache[field_name] = field_obj
        return field_obj

    def _populate_grid_from_items(self, items: list[ReviewItem]) -> None:
        """Lay out every item in a num_cols-wide grid; scroll the area to see more rows."""
        self._clear_grid_layout()
        if not items:
            for j in range(self.num_cols):
                cell = ReviewCellWidget(None)
                self.grid_layout.addWidget(cell, 0, j)
            return
        for idx, item in enumerate(items):
            row = idx // self.num_cols
            col = idx % self.num_cols
            cell = ReviewCellWidget(
                item, item_index=idx, review_field=self._review_field_obj
            )
            cell.value_changed.connect(self._on_value_changed)
            self.grid_layout.addWidget(cell, row, col)
            self._cell_widgets.append(cell)

    def _populate_placeholder_grid(self) -> None:
        """Fill grid with placeholder cells."""
        self._populate_grid_from_items([])

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
        if self._active_batch_folders and self.config_folder:
            self._reload_current_batch()

    def _project_load_prerequisites(self) -> tuple[dict, str, str] | None:
        """Return (config, import_filename, default_batch_dir) or None after showing a dialog."""
        if self.config_folder is None:
            QMessageBox.warning(
                self,
                "Select project first",
                "Select a project folder (File → Select project...) before loading batches.",
            )
            return None
        config = _load_project_config(self.config_folder)
        if not config:
            QMessageBox.warning(
                self, "No config", "project_config.json not found or invalid in the selected project."
            )
            return None
        always_review = config.get("always_review")
        if not always_review or not isinstance(always_review, list):
            QMessageBox.warning(
                self,
                "No always_review",
                "project_config.json must define 'always_review' as a list of field names.\n"
                'Example: "always_review": ["Field3", "Another field"]',
            )
            return None
        default_batch = str(config.get("batch_folder", "")).strip()
        import_filename = str(config.get("import_filename", "")).strip()
        if not default_batch or not import_filename:
            QMessageBox.warning(
                self,
                "Config incomplete",
                "project_config.json must define 'batch_folder' and 'import_filename'.",
            )
            return None
        default_dir = Path(default_batch)
        if not default_dir.exists():
            default_dir = Path.cwd()
        return config, import_filename, str(default_dir)

    def _reload_current_batch(self) -> None:
        """Reload the current batch(es) with the selected field (no folder dialog)."""
        if not self.config_folder or not self._active_batch_folders:
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
        self.load_multiple_action.setEnabled(False)
        batch_desc = self._batch_status_label()
        self.status_label.setText(f"Loading {batch_desc} for field '{review_field}'...")
        self._load_worker = LoadBatchWorker(
            config_folder=self.config_folder,
            batch_folders=list(self._active_batch_folders),
            import_filename=import_filename,
            review_field_name=review_field,
            pages_without_fiducial=pages_without_fiducial,
            parent=self,
        )
        self._hide_thumbnail_progress()
        self._load_worker.progress.connect(self._on_load_progress)
        self._load_worker.items_ready.connect(self._on_items_ready)
        self._load_worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self._load_worker.thumbnail_progress.connect(self._update_thumbnail_progress)
        self._load_worker.finished.connect(self._on_load_finished)
        self._load_worker.start()

    def _display_from_cache(self, field_name: str) -> None:
        """Display items from cache (instant switch)."""
        items = self._field_cache[field_name]
        self._review_field_name = field_name
        self._review_field_obj = self._lookup_review_field_definition(field_name)
        self.review_items = items
        self._populate_grid_from_items(items)
        batch_name = self._batch_status_label()
        self.status_label.setText(f"Batch: {batch_name} | Field: {field_name} | {len(items)} items (cached)")

    def _start_cache_next_field(self) -> None:
        """Start background caching of the next field in always_review."""
        _cancel_and_wait_worker(self._cache_worker)
        self._cache_worker = None
        if not self.config_folder or not self._active_batch_folders:
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
                self._cache_batch_folders_key = _batch_folders_key(self._active_batch_folders)
                self._cache_worker = LoadBatchWorker(
                    config_folder=self.config_folder,
                    batch_folders=list(self._active_batch_folders),
                    import_filename=import_filename,
                    review_field_name=next_field,
                    pages_without_fiducial=pages_without_fiducial,
                    parent=self,
                )
                self._cache_worker.items_ready.connect(self._on_cache_items_ready)
                self._cache_worker.thumbnail_ready.connect(self._on_cache_thumbnail_ready)
                self._cache_worker.finished.connect(self._on_cache_finished)
                self._cache_worker.start()
                logger.info("Caching field '%s' in background", next_field)
                return
        # No more fields to cache

    def _on_cache_items_ready(
        self, items: list[ReviewItem], field_name: str, _field_obj: Field | None = None
    ) -> None:
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
        worker = self._cache_worker
        self._cache_worker = None
        active_key = _batch_folders_key(self._active_batch_folders) if self._active_batch_folders else None
        if self._cache_batch_folders_key != active_key:
            self._cache_items = []
            self._cache_field_name = ""
            self._cache_batch_folders_key = None
            _release_worker(worker, defer=True)
            return  # Batch changed, discard cache
        if self._cache_items and self._cache_field_name:
            self._field_cache[self._cache_field_name] = list(self._cache_items)
            logger.info("Cached field '%s' (%d items)", self._cache_field_name, len(self._cache_items))
        self._cache_items = []
        self._cache_field_name = ""
        self._cache_batch_folders_key = None
        _release_worker(worker, defer=True)
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
        if find_default_logo(self.config_folder / "fiducials") is None:
            logger.warning("No default logo in project fiducials; per-page or missing logos may misalign thumbnails.")
        self._refresh_field_menu()
        self.status_label.setText(f"Project: {self.config_folder.name}. Select a field, then load a batch folder.")

    def _on_load_batch_folder(self) -> None:
        prereq = self._project_load_prerequisites()
        if prereq is None:
            return
        _config, _import_filename, default_dir = prereq

        batch_folder = QFileDialog.getExistingDirectory(
            self, "Select batch folder (containing import file)", default_dir
        )
        if not batch_folder:
            return

        resolved_batch = resolve_path_case_insensitive(batch_folder)
        if resolved_batch is None or not resolved_batch.is_dir():
            QMessageBox.warning(self, "Invalid path", f"Folder not found: {batch_folder}")
            return

        self.batch_folder = resolved_batch
        self._multi_batch_root = None
        self._active_batch_folders = [resolved_batch]
        self._field_cache.clear()
        self._field_obj_cache.clear()
        self._cache_batch_folders_key = None
        self._reload_current_batch()

    def _on_load_multiple_batches(self) -> None:
        prereq = self._project_load_prerequisites()
        if prereq is None:
            return
        _config, import_filename, default_dir = prereq

        root_folder = QFileDialog.getExistingDirectory(
            self,
            "Select folder containing batch folders (any depth)",
            default_dir,
        )
        if not root_folder:
            return

        resolved_root = resolve_path_case_insensitive(root_folder)
        if resolved_root is None or not resolved_root.is_dir():
            QMessageBox.warning(self, "Invalid path", f"Folder not found: {root_folder}")
            return

        batch_folders = _discover_batch_folders(resolved_root, import_filename)
        if not batch_folders:
            QMessageBox.information(
                self,
                "No batches found",
                f"No subfolders under\n{resolved_root}\ncontain the import file '{import_filename}'.",
            )
            return

        self.batch_folder = resolved_root
        self._multi_batch_root = resolved_root
        self._active_batch_folders = batch_folders
        self._field_cache.clear()
        self._field_obj_cache.clear()
        self._cache_batch_folders_key = None
        self._reload_current_batch()

    def _on_grid_layout(self) -> None:
        dialog = GridLayoutDialog(self.num_cols, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        cols = dialog.column_count()
        if cols == self.num_cols:
            return
        self.num_cols = cols
        if self.review_items:
            self._populate_grid_from_items(self.review_items)
            batch_name = self._batch_status_label()
            self.status_label.setText(
                f"Batch: {batch_name} | Field: {self._review_field_name} | "
                f"{len(self.review_items)} items"
            )
        else:
            self._populate_placeholder_grid()

    def _on_load_progress(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_items_ready(
        self, items: list[ReviewItem], review_field: str, field_obj: Field | None
    ) -> None:
        """Populate grid immediately with values; thumbnails will arrive as they load."""
        self._review_field_name = review_field
        self._review_field_obj = field_obj
        if field_obj is not None:
            self._field_obj_cache[review_field] = field_obj
        if not items:
            self.review_items = []
            self._populate_placeholder_grid()
            self._hide_thumbnail_progress()
            self.status_label.setText(f"No documents found for field '{review_field}'.")
            return

        self.review_items = items
        self._begin_thumbnail_progress(len(items))
        self._populate_grid_from_items(items)
        batch_name = self._batch_status_label()
        self.status_label.setText(
            f"Batch: {batch_name} | Field: {review_field} | {len(items)} items (loading thumbnails...)"
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
        worker = self._load_worker
        self._load_worker = None
        _release_worker(worker, defer=True)
        self._hide_thumbnail_progress()
        self.load_action.setEnabled(True)
        self.load_multiple_action.setEnabled(True)
        batch_name = self._batch_status_label()
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
