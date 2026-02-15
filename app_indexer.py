import sys
import os
import json
import csv
import cv2
import numpy as np
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QLabel, QScrollArea, QPushButton,
    QDialog, QLineEdit, QDialogButtonBox, QFileDialog, QMessageBox,
    QStyledItemDelegate,
)
from PyQt6.QtCore import Qt, QSize, QPoint, QRect
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QMouseEvent, QFont, QIcon
from PIL import Image
from dotenv import load_dotenv
from util import ORMMatcher, CSVManager, ProjectValidations
from util.index_comments import Comment, Comments
from util.app_state import load_state, save_state
from util.path_utils import (
    resolve_path_case_insensitive,
    resolve_path_or_original,
    find_file_case_insensitive,
)
from util.document_loader import get_document_loader_for_path
from fields import Field, Tickbox, RadioButton, RadioGroup, TextField
import logging
from ui import MainImageIndexPanel, IndexDetailPanel, IndexTextDialog, IndexCommentDialog, IndexMenuBar, IndexOcrDialog, QcCommentDialog
from util.gemini_ocr_client import ocr_image_region

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

nav_widget_height = 100 # pixels

# Bar dimensions for document list completion indicator
_completion_bar_width = 48
_completion_bar_height = 8


class DocumentListDelegate(QStyledItemDelegate):
    """Paints document list items with filename and a small completion bar (green=filled, red=blank)."""

    def paint(self, painter, option, index):
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        data = index.data(Qt.ItemDataRole.UserRole)
        filled, total = data if isinstance(data, tuple) and len(data) == 2 else (0, 0)

        rect = option.rect
        margin = 2
        bar_rect = QRect(
            rect.right() - _completion_bar_width - margin,
            rect.center().y() - _completion_bar_height // 2,
            _completion_bar_width,
            _completion_bar_height,
        )
        text_rect = rect.adjusted(margin, 0, -_completion_bar_width - margin * 2, 0)

        # Draw background and text in text area only (so text doesn't overlap bar)
        opt = type(option)(option)
        opt.rect = text_rect
        super().paint(painter, opt, index)

        # Draw completion bar: green (filled) | red (blank)
        if total > 0:
            filled_ratio = filled / total
            green_width = int(bar_rect.width() * filled_ratio)
            if green_width > 0:
                painter.fillRect(bar_rect.x(), bar_rect.y(), green_width, bar_rect.height(), QColor("#2e7d32"))
            if green_width < bar_rect.width():
                painter.fillRect(
                    bar_rect.x() + green_width, bar_rect.y(),
                    bar_rect.width() - green_width, bar_rect.height(),
                    QColor("#c62828"),
                )

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        return QSize(max(base.width(), 120), base.height())


class Indexer(QMainWindow):
    """Main window for the Field Indexer application."""
    
    def __init__(self):
        super().__init__()
        self.setGeometry(100, 100, 1200, 800)
        
        # Load environment variables
        load_dotenv()

        # Config folder (project folder under DESIGNER_CONFIG_FOLDER). When set, json_folder and logo_path are derived from it.
        # TODO: Deprecate LOGO_PATH and JSON_FOLDER env vars; use Project menu selection instead.
        self.config_folder: str | None = None
        self.json_folder = os.getenv('JSON_FOLDER', './json_data')  # Fallback until project selected
        self.logo_path = os.getenv('LOGO_PATH')  # Fallback until project selected
        self.matcher = None
        self._init_matcher_from_fallbacks()
        
        # CSV manager
        self.csv_manager = CSVManager()

        # Project validations (created when batch loads; one per batch)
        self.project_validations: ProjectValidations | None = None
        
        # Template page dimensions (width, height) per page, loaded when project is selected
        self.template_page_dimensions: list[tuple[int, int]] = []
        
        # Current state
        # NOTE: Historically this indexer worked only with TIFFs. These fields
        # are now document-agnostic and can point at TIFF, PDF, etc.
        self.document_paths: list[str] = []  # List of relative document paths
        self.current_document_index: int = -1
        self.current_page_index: int = 0
        self.current_page_images: list[Image.Image] = []  # PIL Images for current document
        self.page_fields = []  # Fields for current page
        self.page_bbox = None  # Logo bbox for current page
        self.field_values = {}  # Dictionary mapping field names to values for current page
        # Mapping of field name -> QC comment string for the current page
        self.page_comments: dict[str, str] = {}
        self.current_field: Field | None = None  # Currently selected field on this page
        
        # Initialize UI
        self.init_ui()
        # Restore last import file, page, and config folder if available
        self._try_restore_last_session()
        self._update_window_title()

    def _update_window_title(self) -> None:
        """Set window title to 'Field Indexer' with optional project and batch name."""
        title = "Field Indexer"
        parts = []
        if self.config_folder:
            parts.append(Path(self.config_folder).name)
        csv_path = getattr(self.csv_manager, "csv_path", None)
        if csv_path:
            parts.append(Path(csv_path).parent.name)
        if parts:
            title += " - " + " - ".join(parts)
        self.setWindowTitle(title)

    def _init_matcher_from_fallbacks(self) -> None:
        """Initialize ORM matcher from logo_path (env or config_folder)."""
        if self.logo_path and resolve_path_case_insensitive(self.logo_path) is not None:
            self.matcher = ORMMatcher(self.logo_path)
        else:
            self.matcher = None
            if not self.logo_path:
                logger.warning("No logo path set. Select a project from Project menu or set LOGO_PATH.")

    def _apply_config_folder(self, config_folder_path: str) -> None:
        """Set current project config folder, derive json_folder and logo_path, reinit matcher."""
        config_resolved = resolve_path_case_insensitive(config_folder_path)
        if config_resolved is None or not config_resolved.is_dir():
            logger.warning("Config folder does not exist: %s", config_folder_path)
            return

        config_path = config_resolved
        self.config_folder = str(config_path)
        self.json_folder = str(config_path / "json")
        self.project_validations = None  # Reset when switching project

        # Load template page dimensions for rescaling survey pages
        self._load_template_page_dimensions(config_path)

        # Find logo in fiducials subfolder (same convention as form_zone_designer)
        fiducials = config_path / 'fiducials'
        logo_candidates = ['logo.png', 'logo.tif', 'fiducial.png', 'fiducial.jpg']
        self.logo_path = None
        for candidate in logo_candidates:
            found = find_file_case_insensitive(fiducials, candidate)
            if found is not None:
                self.logo_path = str(found)
                break

        self._init_matcher_from_fallbacks()
        # Load QC comment presets for this project (if available)
        self._load_qc_comment_presets(config_path)
        if hasattr(self, '_index_menu_bar'):
            self._index_menu_bar.set_current_project_path(self.config_folder)
        save_state(last_indexer_config_folder=self.config_folder)
        logger.info("Project selected: %s (json=%s, logo=%s)", self.config_folder, self.json_folder, self.logo_path)
        # New project invalidates current batch; clear documents and display
        self._clear_batch()
        self._update_window_title()

    def _load_qc_comment_presets(self, config_path: Path) -> None:
        """Load preset QC comments from qc_comments.txt for the current project, if present."""
        self._qc_comment_presets: list[str] = []
        qc_found = find_file_case_insensitive(config_path, "qc_comments.txt")
        if qc_found is None:
            return
        try:
            with qc_found.open("r", encoding="utf-8") as f:
                for line in f:
                    text = line.strip()
                    if text:
                        self._qc_comment_presets.append(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read qc_comments.txt at %s: %s", qc_found, exc)

    def _load_template_page_dimensions(self, config_path: Path) -> None:
        """Load (width, height) for each page of the project template. Clears on failure."""
        self.template_page_dimensions = []
        template_path = find_file_case_insensitive(config_path, "template.tif")
        if template_path is None or not template_path.is_file():
            logger.warning("Template not found in %s, rescaling disabled", config_path)
            return
        try:
            with Image.open(template_path) as img:
                page_num = 0
                while True:
                    try:
                        img.seek(page_num)
                        self.template_page_dimensions.append((img.width, img.height))
                        page_num += 1
                    except EOFError:
                        break
            logger.info("Loaded template dimensions for %d pages", len(self.template_page_dimensions))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read template dimensions from %s: %s", template_path, exc)
            self.template_page_dimensions = []

    def _clear_batch(self) -> None:
        """Clear current batch, document list, and displayed images."""
        self.document_paths = []
        self.current_document_index = -1
        self.current_page_index = 0
        self.current_page_images = []
        self.page_fields = []
        self.page_bbox = None
        self.field_values = {}
        self.page_comments = {}
        self.current_field = None
        self.csv_manager.csv_path = None
        self.csv_manager.csv_dir = None
        self.csv_manager.rows = []
        self.csv_manager.headers = []
        self.csv_manager.field_names = []
        self.tiff_list.clear()
        self.page_info_label.setText("No file loaded")
        self.image_label.set_image(None)
        if hasattr(self, "detail_panel"):
            self.detail_panel.set_current_field(None, page_fields=[], field_values={}, field_comments={})
        if self.prev_button is not None:
            self.prev_button.setEnabled(False)
        if self.next_button is not None:
            self.next_button.setEnabled(False)
    
    def init_ui(self):
        """Initialize the user interface."""
        # Menu bar
        self._index_menu_bar = IndexMenuBar(self)
        self._index_menu_bar.project_selected.connect(self._apply_config_folder)
        self._index_menu_bar.batch_import_selected.connect(self._on_batch_import_selected)
        self._index_menu_bar.ocr_requested.connect(self._on_ocr_requested)
        # QC menu
        self._index_menu_bar.validate_document_requested.connect(self._on_validate_document_requested)
        self._index_menu_bar.review_document_comments_requested.connect(self._on_review_document_comments_requested)

        self._index_menu_bar.validate_batch_requested.connect(self._on_validate_batch_requested)
        self._index_menu_bar.review_batch_comments_requested.connect(self._on_review_batch_comments_requested)

        self.setMenuBar(self._index_menu_bar)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Left panel - document list
        left_panel = QVBoxLayout()
        
        self.tiff_list = QListWidget()
        self.tiff_list.setItemDelegate(DocumentListDelegate(self.tiff_list))
        self.tiff_list.currentRowChanged.connect(self.on_document_selected)
        left_panel.addWidget(self.tiff_list)
        
        main_layout.addLayout(left_panel, 1)
        
        # Center panel - Image display and navigation
        center_panel = QVBoxLayout()
        
        # Page info label
        self.page_info_label = QLabel("No file loaded")
        self.page_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_panel.addWidget(self.page_info_label)
        
        # Image display
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.image_label = MainImageIndexPanel()
        self.image_label.on_field_click = self.on_field_click
        scroll_area.setWidget(self.image_label)
        
        center_panel.addWidget(scroll_area)
        
        main_layout.addLayout(center_panel, 3)
        
        # Right panel - Field detail panel
        self.detail_panel = IndexDetailPanel()
        self.detail_panel.field_value_changed.connect(self.on_detail_panel_value_changed)
        # Enter in the detail panel's value editor completes the current TextField
        self.detail_panel.field_edit_completed.connect(self.on_detail_panel_edit_completed)
        self.detail_panel.ocr_requested.connect(self._on_ocr_requested)
        # Double-clicking a row in the detail panel's fields table opens the QC comment dialog
        self.detail_panel.field_comment_requested.connect(self._on_field_comment_requested)
        main_layout.addWidget(self.detail_panel, stretch=1)

                
        # Navigation buttons
        nav_widget = QWidget()
        nav_widget.setFixedHeight(nav_widget_height)
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        
        self.prev_button = QPushButton("◀ Previous")
        self.prev_button.setFixedHeight(nav_widget_height)
        self.prev_button.setStyleSheet("background-color: #555555; color: white;")
        self.prev_button.clicked.connect(self.previous_page)
        self.prev_button.setEnabled(False)
        nav_layout.addWidget(self.prev_button, 1)
        
        self.next_button = QPushButton("Next ▶")
        self.next_button.setFixedHeight(nav_widget_height)
        self.next_button.setStyleSheet("background-color: #555555; color: white;")
        self.next_button.clicked.connect(self.next_page)
        self.next_button.setEnabled(False)
        nav_layout.addWidget(self.next_button, 3)
        
        center_panel.addWidget(nav_widget)

        # Text field popup dialog (shown under clicked TextField; synced with detail panel)
        self._index_text_dialog = IndexTextDialog(self)
        self._index_text_dialog.text_changed.connect(self.on_index_text_dialog_value_changed)
        # Enter in the floating dialog also completes the current TextField
        self._index_text_dialog.field_edit_completed.connect(self.on_index_text_dialog_edit_completed)

        # QC comments dialog (shown to the left of the selected field)
        self._comment_dialog = IndexCommentDialog(self)
        self._comment_dialog.comment_submitted.connect(self._on_comment_submitted)

        # QC batch review dialog (non-modal, for Review batch comments)
        self._qc_comment_dialog = QcCommentDialog(self)
        self._qc_comment_dialog.remove_clicked.connect(self._on_qc_review_remove)
        self._qc_comment_dialog.next_clicked.connect(self._on_qc_review_next)
    
    def _load_import_file_from_path(self, file_path: str, json_folder_override: str | None = None) -> bool:
        """Load import file from path (no dialog). If json_folder_override is set, use it for this load. Returns True on success."""
        try:
            if json_folder_override:
                self.json_folder = json_folder_override
            self.csv_manager.load_csv(file_path, self.json_folder)
            self.document_paths = self.csv_manager.get_document_paths()
            self.tiff_list.clear()
            for i, document_path in enumerate(self.document_paths):
                filename = os.path.basename(document_path)
                item = QListWidgetItem(filename)
                filled, total = self._get_document_completion(i)
                item.setData(Qt.ItemDataRole.UserRole, (filled, total))
                self.tiff_list.addItem(item)
            logger.info("Loaded %d documents", len(self.document_paths))

            # Create ProjectValidations for this batch (owns LookupManager)
            config = self._load_project_config()
            if config and self.csv_manager.csv_path:
                self.project_validations = ProjectValidations(
                    config, Path(self.csv_manager.csv_path), self.config_folder
                )
            else:
                self.project_validations = None

            self._update_window_title()
            return True
        except Exception as e:
            logger.warning("Could not load import file from path %s: %s", file_path, e)
            return False

    def _get_document_completion(self, row_index: int) -> tuple[int, int]:
        """Return (filled_count, total_count) for the given document row. Excludes File and Comments."""
        total = len(self.csv_manager.field_names)
        if total == 0:
            return (0, 0)
        filled = 0
        for name in self.csv_manager.field_names:
            val = self.csv_manager.get_field_value(row_index, name)
            if val is not None and str(val).strip():
                filled += 1
        return (filled, total)

    def _refresh_document_completion_bar(self, row_index: int) -> None:
        """Update the completion bar for the document at row_index."""
        item = self.tiff_list.item(row_index)
        if item is not None:
            filled, total = self._get_document_completion(row_index)
            item.setData(Qt.ItemDataRole.UserRole, (filled, total))
            idx = self.tiff_list.indexFromItem(item)
            self.tiff_list.viewport().update(self.tiff_list.visualRect(idx))

    def _try_restore_last_session(self) -> None:
        """Restore last import file, config folder (project), and page from persisted state if valid."""
        state = load_state()
        last_import = (state.get("last_import_file") or "").strip()
        if not last_import or resolve_path_case_insensitive(last_import) is None:
            return
        # Prefer config_folder (project); fall back to inferring from last_indexer_json_folder for older sessions
        last_config = (state.get("last_indexer_config_folder") or "").strip()
        if last_config and resolve_path_case_insensitive(last_config) is not None:
            self._apply_config_folder(last_config)
        else:
            last_json = (state.get("last_indexer_json_folder") or "").strip()
            if last_json:
                p_resolved = resolve_path_case_insensitive(last_json)
                # Infer config folder: if last_json ends with "json", parent is likely the project folder
                if p_resolved is not None and p_resolved.name.lower() == "json" and p_resolved.parent.exists():
                    self._apply_config_folder(str(p_resolved.parent))
                else:
                    self.json_folder = last_json
        try:
            if not self._load_import_file_from_path(last_import):
                return
            if not self.document_paths:
                return
            doc_idx = state.get("last_indexer_tiff_index")
            if doc_idx is None or doc_idx < 0 or doc_idx >= len(self.document_paths):
                doc_idx = 0
            self.tiff_list.setCurrentRow(doc_idx)
            self.on_document_selected(doc_idx)
            page_idx = state.get("last_indexer_page_index")
            if page_idx is not None and page_idx >= 0 and page_idx < len(self.current_page_images):
                self.current_page_index = page_idx
                self.display_current_page()
            save_state(
                last_import_file=last_import,
                last_indexer_config_folder=self.config_folder,
                last_indexer_json_folder=self.json_folder,
                last_indexer_tiff_index=self.current_document_index,
                last_indexer_page_index=self.current_page_index,
            )
        except Exception as e:
            logger.warning("Could not restore last session: %s", e)

    def _load_project_config(self) -> dict | None:
        """Load project_config.json for the current project, if available."""
        if not self.config_folder:
            return None
        json_folder = Path(resolve_path_or_original(self.config_folder)) / "json"
        config_path = find_file_case_insensitive(json_folder, "project_config.json")
        if config_path is None:
            return None
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Could not read project_config.json at %s: %s", config_path, e)
            return None

    def _get_default_import_folder(self) -> str:
        """
        Determine the default folder for importing the file list.

        Priority:
        1) batch_folder from project_config.json for the current project (if valid)
        2) Current working directory as a final fallback.
        """
        config = self._load_project_config()
        if config:
            batch_folder = str(config.get("batch_folder", "")).strip()
            if batch_folder and resolve_path_case_insensitive(batch_folder) is not None:
                return batch_folder
        # Fallback: current working directory
        return os.getcwd()

    def _on_batch_import_selected(self, import_file_path: str) -> None:
        """Handle selection of a batch import file from the Batch menu."""
        if not import_file_path:
            return
        # Load the import file directly, using the current json_folder/config_folder
        if not self._load_import_file_from_path(import_file_path):
            QMessageBox.critical(
                self,
                "Error",
                f"Error loading import file:\n{import_file_path}",
            )
            return
        save_state(
            last_import_file=import_file_path,
            last_indexer_config_folder=self.config_folder,
            last_indexer_json_folder=self.json_folder,
            last_indexer_tiff_index=0,
            last_indexer_page_index=0,
        )
        if self.document_paths:
            self.tiff_list.setCurrentRow(0)

    def on_document_selected(self, index: int) -> None:
        """Handle document selection from the list widget."""
        if index < 0 or index >= len(self.document_paths):
            return
        
        self.current_document_index = index
        self.current_page_index = 0
        
        # Load document
        relative_path = self.document_paths[index]
        absolute_path = self.csv_manager.get_absolute_document_path(relative_path)
        
        try:
            self.load_document(absolute_path)
            self.display_current_page()
            save_state(last_indexer_tiff_index=index, last_indexer_page_index=self.current_page_index)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading document: {e}")
            logger.error("Error loading document %s: %s", absolute_path, e, exc_info=True)

    def on_tiff_selected(self, index: int) -> None:
        """Backward-compatible wrapper; prefer on_document_selected."""
        self.on_document_selected(index)

    def load_document(self, document_path: str) -> None:
        """Load a multipage document (TIFF, PDF, etc.) into memory."""
        loader = get_document_loader_for_path(document_path)
        self.current_page_images = loader.load_pages(document_path)
    
    def display_current_page(self):
        """Display the current page with fields."""
        if not self.current_page_images:
            return
        
        page_num = self.current_page_index
        
        if page_num >= len(self.current_page_images):
            return
        
        # Update page info
        self.page_info_label.setText(
            f"Page {page_num + 1} of {len(self.current_page_images)} - {os.path.basename(self.document_paths[self.current_document_index])}"
        )

        # Enable/disable navigation buttons based on pages that actually have fields.
        # The "Next" button stays enabled even when there are no more pages with fields
        # so that we can show completion dialogs (form/batch completed) when clicked.
        has_prev_with_fields = self._find_previous_page_with_fields(page_num) is not None
        self.prev_button.setEnabled(has_prev_with_fields)
        if self.next_button is not None:
            self.next_button.setEnabled(True)
        
        # Get PIL image
        pil_image = self.current_page_images[page_num]
        
        # Rescale to template dimensions if they differ (survey pages may have different size)
        if (self.template_page_dimensions and
                page_num < len(self.template_page_dimensions)):
            target_w, target_h = self.template_page_dimensions[page_num]
            w, h = pil_image.size
            if (w, h) != (target_w, target_h):
                pil_image = pil_image.resize(
                    (target_w, target_h),
                    Image.Resampling.LANCZOS,
                )
                logger.debug("Rescaled page %d from %dx%d to %dx%d", page_num + 1, w, h, target_w, target_h)
        
        # Convert to QPixmap
        img_array = np.array(pil_image)
        height, width, channel = img_array.shape
        bytes_per_line = 3 * width
        q_image = QImage(img_array.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        
        # Detect logo (skip for pages in pages_without_fiducial from project_config.json)
        config = self._load_project_config()
        raw = config.get("pages_without_fiducial", []) if config else []
        pages_without_fiducial = {int(x) for x in raw}
        if page_num in pages_without_fiducial:
            self.page_bbox = None
            logger.info("Page %d: Skipping fiducial (pages_without_fiducial)", page_num + 1)
        else:
            self.page_bbox = self.detect_logo(pil_image)
        
        # Load fields for this page
        self.page_fields = self.load_page_fields(page_num + 1)  # JSON files are 1-indexed
        
        # Pre-populate field values from CSV
        self.populate_field_values()
        # Load QC comments for this page from the Comments column
        self._load_comments_for_current_page()
        
        # Display
        self.image_label.set_image(pixmap, self.page_bbox, self.page_fields, self.field_values, self.page_comments)
        
        # Update detail panel (clear selection when page changes)
        if hasattr(self, 'detail_panel'):
            self.detail_panel.set_current_field(
                None,
                page_image=pil_image,
                page_bbox=self.page_bbox,
                page_fields=self.page_fields,
                field_values=self.field_values,
                field_comments=self.page_comments,
            )
        # No current field selected on new page
        self._set_current_field(None)
    
    def detect_logo(self, pil_image):
        """Detect logo in the image, return bounding box or None."""
        if not self.matcher:
            return None
        
        try:
            # Convert PIL to OpenCV
            img_array = np.array(pil_image)
            img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            # Detect logo
            self.matcher.locate_from_cv2_image(img_cv)
            
            if self.matcher.top_left and self.matcher.bottom_right:
                logger.info(f"Logo detected at {self.matcher.top_left}")
                return (self.matcher.top_left, self.matcher.bottom_right)
            else:
                logger.warning("Logo detection failed, using (0,0)")
                return None
        
        except Exception as e:
            logger.error(f"Error detecting logo: {e}")
            return None
    
    def load_page_fields(self, page_num):
        """Load field definitions from JSON file for a given page number."""
        json_folder = Path(resolve_path_or_original(self.json_folder))
        json_path = find_file_case_insensitive(json_folder, f"{page_num}.json")
        
        if json_path is None:
            logger.warning(f"JSON file not found for page {page_num}")
            return []
        
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            fields = []
            for item in data:
                field = Field.from_dict(item)
                fields.append(field)
            
            logger.info(f"Loaded {len(fields)} fields from {json_path}")
            return fields
        
        except Exception as e:
            logger.error(f"Error loading fields from {json_path}: {e}")
            return []
    
    def populate_field_values(self):
        """Pre-populate field values from CSV data."""
        if self.current_document_index < 0:
            return
        
        # Clear existing values for this page
        self.field_values = {}
        
        for field in self.page_fields:
            if isinstance(field, RadioGroup):
                # Get value for radio group
                value = self.csv_manager.get_field_value(self.current_document_index, field.name)
                if value:
                    self.field_values[field.name] = value
            
            elif isinstance(field, Tickbox):
                value = self.csv_manager.get_field_value(self.current_document_index, field.name)
                if value:
                    is_checked = value.lower() in ['ticked','true', '1', 'yes', 'checked', 'tick']
                    self.field_values[field.name] = is_checked
            
            elif isinstance(field, TextField):
                value = self.csv_manager.get_field_value(self.current_document_index, field.name)
                if value:
                    self.field_values[field.name] = value

    # ------------------------------------------------------------------
    # QC comments: managed via Comments (page+field keyed) to avoid duplicates
    # ------------------------------------------------------------------

    def _load_comments_for_current_page(self) -> None:
        """Populate page_comments from the Comments column for the current page (deduplicated)."""
        self.page_comments = {}
        if self.current_document_index < 0:
            return
        comments_str = self.csv_manager.get_field_value(self.current_document_index, "Comments") or ""
        row_comments = Comments.from_string(comments_str)
        page_num = self.current_page_index + 1  # 1-indexed in Comments column
        self.page_comments = row_comments.get_for_page(page_num)

    def _set_comment_for_field(self, field_name: str, comment: str) -> None:
        """
        Update the Comments column for the current form row, setting or clearing
        the comment for (current_page, field_name). Uses Comments so (page, field)
        is unique and duplicates are never written.
        """
        if self.current_document_index < 0:
            return
        existing = self.csv_manager.get_field_value(self.current_document_index, "Comments") or ""
        row_comments = Comments.from_string(existing)
        page_num = self.current_page_index + 1
        comment = comment.strip()
        if comment:
            row_comments.add_comment(Comment(page_num, field_name, comment))
        else:
            row_comments.remove_comment(Comment(page_num, field_name, "").identity)
        new_str = row_comments.to_csv_string()
        self.csv_manager.set_field_value(self.current_document_index, "Comments", new_str)
        self.csv_manager.save_csv()
        self._load_comments_for_current_page()

    def _find_next_page_with_fields(self, start_index: int) -> int | None:
        """Return index of next page that has any fields, or None if none exist."""
        if not self.current_page_images:
            return None
        for idx in range(start_index + 1, len(self.current_page_images)):
            fields = self.load_page_fields(idx + 1)  # JSON is 1-indexed
            if fields:
                return idx
        return None

    def _find_previous_page_with_fields(self, start_index: int) -> int | None:
        """Return index of previous page that has any fields, or None if none exist."""
        if not self.current_page_images:
            return None
        for idx in range(start_index - 1, -1, -1):
            fields = self.load_page_fields(idx + 1)
            if fields:
                return idx
        return None

    def previous_page(self):
        """Navigate to previous page that has fields (skipping blank pages)."""
        prev_idx = self._find_previous_page_with_fields(self.current_page_index)
        if prev_idx is None:
            return
        self.current_page_index = prev_idx
        self.display_current_page()
        save_state(last_indexer_tiff_index=self.current_document_index, last_indexer_page_index=self.current_page_index)

    def next_page(self):
        """Navigate to next page that has fields (skipping blank pages).

        If there are no more pages with fields in the current form:
        - If there is another file in the batch, prompt with "Form completed" (Yes/No).
          If the user clicks Yes, advance to the next file.
        - If the current form is the last file in the batch, show "Batch completed"
          dialog with Yes/No buttons (Yes action will be defined later).
        """
        next_idx = self._find_next_page_with_fields(self.current_page_index)

        # Case 1: there *is* another page with fields in this document – go there.
        if next_idx is not None:
            self.current_page_index = next_idx
            self.display_current_page()
            save_state(
                last_indexer_tiff_index=self.current_document_index,
                last_indexer_page_index=self.current_page_index,
            )
            return

        # Case 2: no more pages with fields in this document.
        if not self.document_paths or self.current_document_index < 0:
            return

        is_last_file_in_batch = self.current_document_index >= len(self.document_paths) - 1

        if not is_last_file_in_batch:
            # There is another file in the batch – ask whether to advance to it.
            reply = QMessageBox.question(
                self,
                "Form completed",
                "Form completed.\n\nGo to the next document in the batch?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.tiff_list.setCurrentRow(self.current_document_index + 1)
            return

        # Case 3: current form is the last file in the batch – batch completed.
        reply = QMessageBox.question(
            self,
            "Batch completed",
            "Click 'Yes' to complete the batch (or No if you want review it first)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._complete_current_batch()
    
    def on_field_click(self, field, sub_field=None):
        """Handle field click events."""
        # Update detail panel to show the clicked field
        if hasattr(self, 'detail_panel') and self.current_page_images:
            current_pil_image = self.current_page_images[self.current_page_index]
            # For RadioGroups, show the group itself, not the individual button
            field_to_show = field
            self.detail_panel.set_current_field(
                field_to_show,
                page_image=current_pil_image,
                page_bbox=self.page_bbox,
                page_fields=self.page_fields,
                field_values=self.field_values,
                field_comments=self.page_comments,
            )
            self._set_current_field(field_to_show)
        
        if isinstance(field, Tickbox):
            # Toggle tickbox
            current_value = self.field_values.get(field.name, False)
            new_value = not current_value
            self.field_values[field.name] = new_value
            
            # Update ImageLabel's field_values
            self.image_label.field_values = self.field_values.copy()
            
            # Save to CSV
            self.csv_manager.set_field_value(
                self.current_document_index,
                field.name,
                'Ticked' if new_value else ''
            )
            self.csv_manager.save_csv()
            self._refresh_document_completion_bar(self.current_document_index)
            
            # Update display
            self.image_label.update_display()
            
            # Update detail panel
            if hasattr(self, 'detail_panel') and self.current_page_images:
                current_pil_image = self.current_page_images[self.current_page_index]
                self.detail_panel.set_current_field(
                    field,
                    page_image=current_pil_image,
                    page_bbox=self.page_bbox,
                    page_fields=self.page_fields,
                    field_values=self.field_values,
                    field_comments=self.page_comments,
                )
                self._set_current_field(field)
            
            logger.info(f"Tickbox '{field.name}' set to {new_value}")
        
        elif isinstance(field, RadioGroup) and sub_field:
            # Select radio button
            self.field_values[field.name] = sub_field.name
            
            # Update ImageLabel's field_values
            self.image_label.field_values = self.field_values.copy()
            
            # Save to CSV
            self.csv_manager.set_field_value(
                self.current_document_index,
                field.name,
                sub_field.name
            )
            self.csv_manager.save_csv()
            self._refresh_document_completion_bar(self.current_document_index)
            
            # Update display
            self.image_label.update_display()
            
            # Update detail panel
            if hasattr(self, 'detail_panel') and self.current_page_images:
                current_pil_image = self.current_page_images[self.current_page_index]
                self.detail_panel.set_current_field(
                    field,
                    page_image=current_pil_image,
                    page_bbox=self.page_bbox,
                    page_fields=self.page_fields,
                    field_values=self.field_values,
                    field_comments=self.page_comments,
                )
                self._set_current_field(field)
            
            logger.info(f"RadioGroup '{field.name}' set to '{sub_field.name}'")
        
        elif isinstance(field, TextField):
            # Update detail panel first so it shows the clicked field
            self.image_label.field_values = self.field_values.copy()
            self.image_label.update_display()

            # Show IndexTextDialog directly under the bottom of the TextField
            rect = self.image_label.get_field_rect_in_widget(field)
            if rect is not None:
                global_bottom_left = self.image_label.mapToGlobal(rect.bottomLeft())
                current_value = self.field_values.get(field.name, "")
                self._index_text_dialog.set_field(field.name or "TextField", current_value, field=field)
                self._index_text_dialog.show_under_rect(global_bottom_left, rect.width())

            if hasattr(self, 'detail_panel') and self.current_page_images:
                current_pil_image = self.current_page_images[self.current_page_index]
                self.detail_panel.set_current_field(
                    field,
                    page_image=current_pil_image,
                    page_bbox=self.page_bbox,
                    page_fields=self.page_fields,
                    field_values=self.field_values,
                    field_comments=self.page_comments,
                )

            logger.info(f"TextField '{field.name}' clicked, value='{self.field_values.get(field.name, '')}'")
    
    def on_detail_panel_value_changed(self, field_name: str, new_value: str):
        """Handle value changes from the detail panel."""
        # Update field_values
        self.field_values[field_name] = new_value

        # Keep IndexTextDialog in sync when user types in the detail panel
        if self._index_text_dialog.isVisible() and self._index_text_dialog.field_name == field_name:
            self._index_text_dialog.set_text(new_value)

        # Update ImageLabel's field_values
        self.image_label.field_values = self.field_values.copy()

        # Save to CSV
        self.csv_manager.set_field_value(
            self.current_document_index,
            field_name,
            new_value
        )
        self.csv_manager.save_csv()
        self._refresh_document_completion_bar(self.current_document_index)

        # Update display
        self.image_label.update_display()

        logger.info(f"Field '{field_name}' value changed to '{new_value}' via detail panel")

    def on_index_text_dialog_value_changed(self, field_name: str, new_value: str):
        """Handle value changes from the IndexTextDialog (shown under TextField)."""
        self.field_values[field_name] = new_value

        # Keep detail panel in sync
        if hasattr(self, 'detail_panel') and self.detail_panel.current_field and self.detail_panel.current_field.name == field_name:
            self.detail_panel.set_current_field(
                self.detail_panel.current_field,
                page_image=self.detail_panel.current_page_image,
                page_bbox=self.detail_panel.page_bbox,
                page_fields=self.detail_panel.page_fields,
                field_values=self.field_values,
                field_comments=self.page_comments,
            )

        self.image_label.field_values = self.field_values.copy()
        self.csv_manager.set_field_value(self.current_document_index, field_name, new_value)
        self.csv_manager.save_csv()
        self._refresh_document_completion_bar(self.current_document_index)
        self.image_label.update_display()
        logger.info(f"Field '{field_name}' value changed to '{new_value}' via text dialog")

    def _focus_next_text_field(self, current_field_name: str):
        """Move focus to the next TextField on the current page and open the dialog there."""
        if not self.page_fields:
            return

        # Get all TextFields on this page in their defined order
        text_fields = [f for f in self.page_fields if isinstance(f, TextField)]
        if not text_fields:
            return

        try:
            idx = next(i for i, f in enumerate(text_fields) if f.name == current_field_name)
        except StopIteration:
            self._index_text_dialog.hide()
            return

        # Only advance within this page
        if idx + 1 >= len(text_fields):
            self._index_text_dialog.hide()
            return

        next_field = text_fields[idx + 1]

        if not self.current_page_images:
            self._index_text_dialog.hide()
            return

        current_pil_image = self.current_page_images[self.current_page_index]

        # Update detail panel selection
        if hasattr(self, 'detail_panel'):
            self.detail_panel.set_current_field(
                next_field,
                page_image=current_pil_image,
                page_bbox=self.page_bbox,
                page_fields=self.page_fields,
                field_values=self.field_values,
                field_comments=self.page_comments,
            )
        self._set_current_field(next_field)

        # Show IndexTextDialog under the next TextField
        rect = self.image_label.get_field_rect_in_widget(next_field)
        if rect is not None:
            global_bottom_left = self.image_label.mapToGlobal(rect.bottomLeft())
            current_value = self.field_values.get(next_field.name, "")
            self._index_text_dialog.set_field(next_field.name or "TextField", current_value, field=next_field)
            self._index_text_dialog.show_under_rect(global_bottom_left, rect.width())

    def on_detail_panel_edit_completed(self, field_name: str):
        """User pressed Enter in the detail panel for this field."""
        self._focus_next_text_field(field_name)

    def on_index_text_dialog_edit_completed(self, field_name: str):
        """User pressed Enter in the floating text dialog for this field."""
        self._focus_next_text_field(field_name)

    # ------------------------------------------------------------------
    # Helpers for current field / OCR
    # ------------------------------------------------------------------

    def _set_current_field(self, field: Field | None) -> None:
        """Track the currently selected field and update OCR menu state."""
        self.current_field = field
        can_ocr = isinstance(field, TextField) and bool(self.current_page_images)
        if hasattr(self, "_index_menu_bar"):
            self._index_menu_bar.set_ocr_enabled(can_ocr)

    def _normalize_comment_field_name(self, field_name: str) -> str:
        """
        For QC comments, ensure radio-button selections map back to their
        RadioGroup name so comments are stored on the group, not the option.
        """
        if not field_name:
            return field_name
        for field in self.page_fields or []:
            if isinstance(field, RadioGroup):
                if field.name == field_name:
                    return field_name
                for rb in field.radio_buttons:
                    if rb.name == field_name:
                        return field.name
        return field_name

    # ------------------------------------------------------------------
    # QC comments dialog handlers
    # ------------------------------------------------------------------

    def _on_field_comment_requested(self, field_name: str) -> None:
        """Handle a request from the detail panel to edit QC comments for a field."""
        if not hasattr(self, "detail_panel") or not self.page_fields:
            return

        # Always resolve radio-button names back to their RadioGroup
        field_name = self._normalize_comment_field_name(field_name)

        table = self.detail_panel.fields_table
        # Find the row corresponding to this field name
        row_index = next(
            (i for i, f in enumerate(self.page_fields) if f.name == field_name),
            None,
        )
        if row_index is None or row_index < 0 or row_index >= table.rowCount():
            logger.warning("QC comment requested for unknown field '%s'", field_name)
            return

        # Use the table row rect to position the dialog to the left of the fields table
        model_index = table.model().index(row_index, 0)
        row_rect = table.visualRect(model_index)
        if not row_rect.isValid():
            return

        # visualRect is in viewport coordinates; convert to global
        top_left_global = table.viewport().mapToGlobal(row_rect.topLeft())
        global_rect = QRect(top_left_global, row_rect.size())

        existing_comment = self.page_comments.get(field_name, "")
        presets = getattr(self, "_qc_comment_presets", [])
        self._comment_dialog.set_field(field_name, existing_comment, presets)
        self._comment_dialog.show_left_of_rect(global_rect)

    def _on_comment_submitted(self, field_name: str, comment: str) -> None:
        """Persist a submitted QC comment and refresh highlights/X markers."""
        # Ensure comments for radio selections are stored on the RadioGroup
        field_name = self._normalize_comment_field_name(field_name)
        self._set_comment_for_field(field_name, comment)

        # Keep image overlay in sync
        self.image_label.field_comments = self.page_comments.copy()
        self.image_label.update_display()

        # Refresh detail panel table to update red backgrounds
        if hasattr(self, "detail_panel") and self.current_page_images:
            current_pil_image = self.current_page_images[self.current_page_index]
            self.detail_panel.set_current_field(
                self.current_field,
                page_image=current_pil_image,
                page_bbox=self.page_bbox,
                page_fields=self.page_fields,
                field_values=self.field_values,
                field_comments=self.page_comments,
            )

    def _on_review_document_comments_requested(self) -> None:
        """Handle QC > Review document comments: show only comments for the current document."""
        if not self.document_paths:
            QMessageBox.information(
                self,
                "No batch loaded",
                "Load a batch first (Batch menu).",
            )
            return

        row_idx = self.current_document_index
        comments_str = self.csv_manager.get_field_value(row_idx, "Comments") or ""
        row_comments = Comments.from_string(comments_str)
        checklist: list[tuple[int, Comment]] = []
        for c in sorted(row_comments.comments.values(), key=lambda x: (x.page, x.field)):
            if c.comment.strip():
                checklist.append((row_idx, c))

        if not checklist:
            QMessageBox.information(
                self,
                "No comments",
                "There are no QC comments in this document.",
            )
            return

        self._qc_review_checklist = checklist
        self._qc_review_index = 0
        self._qc_review_dialog_positioned = False
        self._show_current_qc_review_comment()

    def _on_review_batch_comments_requested(self) -> None:
        """Handle QC > Review batch comments: iterate through all comments in the batch."""
        if not self.document_paths:
            QMessageBox.information(
                self,
                "No batch loaded",
                "Load a batch first (Batch menu).",
            )
            return

        # Build checklist: (row_index, Comment) for all comments in the batch
        checklist: list[tuple[int, Comment]] = []
        for row_idx in range(len(self.document_paths)):
            comments_str = self.csv_manager.get_field_value(row_idx, "Comments") or ""
            row_comments = Comments.from_string(comments_str)
            for c in sorted(row_comments.comments.values(), key=lambda x: (x.page, x.field)):
                if c.comment.strip():
                    checklist.append((row_idx, c))

        if not checklist:
            QMessageBox.information(
                self,
                "No comments",
                "There are no QC comments in this batch.",
            )
            return

        self._qc_review_checklist = checklist
        self._qc_review_index = 0
        self._qc_review_dialog_positioned = False  # Position only on first show; then keep user's placement
        self._show_current_qc_review_comment()

    def _on_validate_document_requested(self) -> None:
        """Handle QC > Validate document: run project validations on current row."""
        if not self.document_paths:
            QMessageBox.information(
                self,
                "No batch loaded",
                "Load a batch first (Batch menu).",
            )
            return
        if not self.project_validations:
            QMessageBox.information(
                self,
                "No validations",
                "No project validations configured for this project.",
            )
            return
        if not self.project_validations.validations:
            QMessageBox.information(
                self,
                "No validations",
                "No project validations configured for this project.",
            )
            return

        if self.project_validations.lookup_manager:
            self.project_validations.lookup_manager.load_output_csv()
        row_index = self.current_document_index
        field_values = {
            name: self.csv_manager.get_field_value(row_index, name) or ""
            for name in self.csv_manager.field_names
        }
        field_to_page = self.csv_manager.get_field_to_page(self.json_folder)

        failures = self.project_validations.run_validations(
            row_index, field_values, field_to_page
        )

        if failures:
            existing = self.csv_manager.get_field_value(row_index, "Comments") or ""
            row_comments = Comments.from_string(existing)
            for page, field_name, message in failures:
                row_comments.add_comment(Comment(page, field_name, message))
            self.csv_manager.set_field_value(
                row_index, "Comments", row_comments.to_csv_string()
            )
            self.csv_manager.save_csv()

        msg = (
            f"Validated 1 document. {len(failures)} validation failure(s) added as comments."
            if failures
            else "No validation failures found."
        )
        if failures:
            self._on_review_document_comments_requested()
        QMessageBox.information(self, "Validation", msg)

    def _on_validate_batch_requested(self) -> None:
        """Handle QC > Validate batch: run project validations on all rows."""
        if not self.document_paths:
            QMessageBox.information(
                self,
                "No batch loaded",
                "Load a batch first (Batch menu).",
            )
            return
        if not self.project_validations:
            QMessageBox.information(
                self,
                "No validations",
                "No project validations configured for this project.",
            )
            return
        if not self.project_validations.validations:
            QMessageBox.information(
                self,
                "No validations",
                "No project validations configured for this project.",
            )
            return

        if self.project_validations.lookup_manager:
            self.project_validations.lookup_manager.load_output_csv()
        field_to_page = self.csv_manager.get_field_to_page(self.json_folder)
        total_failures = 0

        for row_index in range(len(self.document_paths)):
            field_values = {
                name: self.csv_manager.get_field_value(row_index, name) or ""
                for name in self.csv_manager.field_names
            }
            failures = self.project_validations.run_validations(
                row_index, field_values, field_to_page
            )
            if failures:
                existing = self.csv_manager.get_field_value(row_index, "Comments") or ""
                row_comments = Comments.from_string(existing)
                for page, field_name, message in failures:
                    row_comments.add_comment(Comment(page, field_name, message))
                self.csv_manager.set_field_value(
                    row_index, "Comments", row_comments.to_csv_string()
                )
                total_failures += len(failures)

        if total_failures > 0:
            self.csv_manager.save_csv()

        n_docs = len(self.document_paths)
        msg = (
            f"Validated {n_docs} document(s). {total_failures} validation failure(s) added as comments."
            if total_failures
            else f"Validated {n_docs} document(s). No validation failures found."
        )
        if total_failures > 0:
            self._on_review_batch_comments_requested()
        QMessageBox.information(self, "Validation", msg)

    def _show_current_qc_review_comment(self) -> None:
        """Navigate to the current comment's page and show the QC dialog."""
        if not hasattr(self, "_qc_review_checklist") or self._qc_review_index >= len(self._qc_review_checklist):
            self._qc_comment_dialog.close()
            QMessageBox.information(self, "Review complete", "No more comments to review.")
            return

        row_idx, comment = self._qc_review_checklist[self._qc_review_index]

        # Navigate to the document and page
        if self.current_document_index != row_idx:
            self.tiff_list.setCurrentRow(row_idx)
            self.on_document_selected(row_idx)
        self.current_page_index = comment.page - 1  # 1-indexed in Comments
        self.display_current_page()

        # Get field value
        field_value = self.csv_manager.get_field_value(row_idx, comment.field) or ""

        self._qc_comment_dialog.set_content(
            page=comment.page,
            field_name=comment.field,
            field_value=field_value,
            comment_text=comment.comment,
        )

        self._qc_comment_dialog.adjustSize()
        # Position only on first show in session; preserve user's placement thereafter
        if not getattr(self, "_qc_review_dialog_positioned", True):
            # Default: to the left of the field list (detail panel), vertically centered
            panel_top_left = self.detail_panel.mapToGlobal(QPoint(0, 0))
            panel_height = self.detail_panel.height()
            margin = 8
            dx = panel_top_left.x() - self._qc_comment_dialog.width() - margin
            dy = panel_top_left.y() + (panel_height - self._qc_comment_dialog.height()) // 2
            if dx < 0:
                dx = 0
            if dy < 0:
                dy = 0
            self._qc_comment_dialog.move(dx, dy)
            self._qc_review_dialog_positioned = True
        self._qc_comment_dialog.show()
        self._qc_comment_dialog.raise_()
        self._qc_comment_dialog.activateWindow()

    def _on_qc_review_remove(self) -> None:
        """Remove the current comment from the CSV and advance to next."""
        if not hasattr(self, "_qc_review_checklist") or self._qc_review_index >= len(self._qc_review_checklist):
            return
        row_idx, comment = self._qc_review_checklist[self._qc_review_index]
        existing = self.csv_manager.get_field_value(row_idx, "Comments") or ""
        row_comments = Comments.from_string(existing)
        row_comments.remove_comment(comment.identity)
        new_str = row_comments.to_csv_string()
        self.csv_manager.set_field_value(row_idx, "Comments", new_str)
        self.csv_manager.save_csv()
        self._qc_review_index += 1
        self._show_current_qc_review_comment()

    def _on_qc_review_next(self) -> None:
        """Advance to the next comment without removing."""
        if not hasattr(self, "_qc_review_checklist"):
            return
        self._qc_review_index += 1
        self._show_current_qc_review_comment()

    def _on_ocr_requested(self) -> None:
        """Handle OCR menu action: open selection dialog and run Cloud Vision."""
        if not isinstance(self.current_field, TextField):
            QMessageBox.warning(self, "OCR", "OCR is only available for text fields.")
            return
        if not self.current_page_images:
            QMessageBox.warning(self, "OCR", "No page is currently loaded.")
            return

        # Use the current page image at original resolution
        pil_image = self.current_page_images[self.current_page_index]

        # Convert to QPixmap (same as display_current_page)
        img_array = np.array(pil_image)
        height, width, channel = img_array.shape
        bytes_per_line = 3 * width
        q_image = QImage(img_array.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)

        # Field coords in JSON are logo-relative; convert to page pixel coords for dialog and OCR
        logo_tl = self.page_bbox[0] if self.page_bbox else (0, 0)
        field_rect_page = (
            self.current_field.x + logo_tl[0],
            self.current_field.y + logo_tl[1],
            self.current_field.width,
            self.current_field.height,
        )
        self._index_text_dialog.hide()
        dialog = IndexOcrDialog(self, pixmap, initial_rect=field_rect_page)
        # Block the main window while dialog is open
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        rect = dialog.selected_rect()
        if not rect:
            return

        # Run OCR with a wait cursor
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            text = ocr_image_region(pil_image, rect)
        except Exception as e:  # noqa: BLE001 - show any OCR failure to the user
            QMessageBox.information(
                self,
                "OCR failed",
                f"OCR (Gemini) failed or is not available.\n\n{e}",
            )
            return
        finally:
            QApplication.restoreOverrideCursor()

        if text is None:
            text = ""

        # Apply OCR result to the current TextField value, reusing existing plumbing
        field_name = self.current_field.name or ""
        if not field_name:
            return
        self.on_index_text_dialog_value_changed(field_name, text)

    def _complete_current_batch(self) -> None:
        """
        Mark the current batch as completed by moving its folder into the
        '_qc' subfolder of the configured batch_folder, when possible.

        This relies on the current CSV path being located somewhere under the
        configured batch_folder (typically under '_in_progress/<batch_name>').
        """
        csv_path = getattr(self.csv_manager, "csv_path", None)
        if not csv_path:
            return

        config = self._load_project_config()
        if not config:
            return

        batch_folder = str(config.get("batch_folder", "")).strip()
        if not batch_folder:
            return

        batch_resolved = resolve_path_case_insensitive(batch_folder)
        if batch_resolved is None or not batch_resolved.is_dir():
            return

        batch_root = batch_resolved

        csv_dir = Path(resolve_path_or_original(os.path.dirname(os.path.abspath(csv_path))))

        # Ensure the CSV directory is somewhere under the batch_root.
        try:
            rel = csv_dir.relative_to(batch_root)
        except ValueError:
            # CSV is not part of this batch coordination tree.
            return

        parts = rel.parts
        if not parts:
            return

        # Possible layouts:
        # - <batch_root>/<batch_name>
        # - <batch_root>/_in_progress/<batch_name>
        # - <batch_root>/_complete/<batch_name> (already completed)
        if len(parts) == 1:
            # Direct child of batch_root.
            source_dir = batch_root / parts[0]
        elif len(parts) == 2 and parts[0] == "_in_progress":
            source_dir = batch_root / "_in_progress" / parts[1]
        elif len(parts) == 2 and parts[0] == "_complete":
            # Already marked complete.
            return
        else:
            # Unexpected nesting; don't attempt to move.
            return

        if not source_dir.exists():
            return

        qc_root = batch_root / "_qc"
        try:
            qc_root.mkdir(exist_ok=True)
        except Exception:
            logger.warning("Could not ensure _qc folder exists under %s", batch_root)
            return

        complete_root = batch_root / "_complete"
        try:
            complete_root.mkdir(exist_ok=True)
        except Exception:
            logger.warning("Could not ensure _complete folder exists under %s", batch_root)
            return

        dest_dir = qc_root / source_dir.name

        # If destination already exists, do not overwrite – just log it.
        if dest_dir.exists():
            logger.warning("Destination batch folder already exists in _qc: %s", dest_dir)
            return

        try:
            source_dir.rename(dest_dir)
            logger.info("Moved batch folder from %s to %s", source_dir, dest_dir)
        except Exception as e:
            logger.warning("Could not move batch folder %s to %s: %s", source_dir, dest_dir, e)


def main():
    app = QApplication(sys.argv)
    window = Indexer()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

