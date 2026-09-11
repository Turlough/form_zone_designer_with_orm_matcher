import sys
import os
import cv2
import numpy as np
from collections import Counter
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QScrollArea,
    QPushButton,
    QDialog,
    QFileDialog,
    QMessageBox,
    QToolButton,
)

from PyQt6.QtGui import QPixmap, QImage, QAction, QDesktopServices
from PIL import Image
from dotenv import load_dotenv
from util import (
    ORMMatcher,
    DesignerConfig,
    detect_rectangles,
    load_page_fields,
    save_page_fields,
    remove_inner_rectangles,
    RectangleDetectionSettings,
    load_rectangle_detection_settings,
    save_rectangle_detection_settings,
)
from util.designer_persistence import (
    find_duplicate_field_names,
    indexing_config_from_project,
    load_project_config,
    save_indexing_config,
)
from util.test_batch import (
    CreateTestBatchError,
    create_test_batch,
    resolve_template_pdf_source,
)
from util.fiducial_paths import find_default_logo, find_fiducial_for_page, per_page_logo_filename
from util.field_metadata import truncate_summary, sanitize_column_title
from util.radio_grid_layout import build_radio_group_from_frame
from util.field_edit import apply_field_edit
from util.field_geometry_edit import (
    geometry_edit_target,
    snapshot_field_geometry,
    restore_field_geometry,
)
from util.app_state import load_state, save_state
from util.path_utils import (
    resolve_path_case_insensitive,
    find_file_case_insensitive,
    find_project_template,
    user_instructions_html_path,
)
from util.document_loader import get_document_loader_for_path
import logging

from PyQt6.QtCore import QPoint, QThread, QTimer, QUrl, pyqtSignal, Qt
from ui import (
    ImageDisplayWidget,
    DesignerThumbnailPanel,
    DesignerButtonLayout,
    DesignerEditPanel,
    GridDesigner,
    RectangleSelectedDialog,
    DesignerAnalysePreviewDialog,
    DesignerIndexingConfigDialog,
    DesignerCreateTestBatchDialog,
    DesignerRectangleDetectDialog,
)
from fields import Field, Tickbox, RadioButton, RadioGroup, RadioGrid, TextField, FIELD_TYPE_MAP
from field_factory import default_colour_tuple_for_type
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QuestionAssistantWorker(QThread):
    """Background worker for drawn-question frame → Question Assistant."""

    finished_ok = pyqtSignal(object)
    finished_error = pyqtSignal(str)

    def __init__(
        self,
        page_image,
        roi_fiducial: tuple[int, int, int, int],
        fiducial_bbox,
        cv_rects: list,
        inner_rects_fiducial: list,
        export_columns_block: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._page_image = page_image
        self._roi_fiducial = roi_fiducial
        self._fiducial_bbox = fiducial_bbox
        self._cv_rects = cv_rects
        self._inner_rects_fiducial = inner_rects_fiducial
        self._export_columns_block = export_columns_block

    def run(self):
        try:
            from runtime_assistants.design_assistant.question_assistant import analyse_question

            result = analyse_question(
                self._page_image,
                roi_fiducial=self._roi_fiducial,
                fiducial_bbox=self._fiducial_bbox,
                cv_rects=self._cv_rects,
                inner_rects_fiducial=self._inner_rects_fiducial,
                export_columns_block=self._export_columns_block,
            )
            self.finished_ok.emit(result)
        except Exception as e:
            logger.exception("Question Assistant failed")
            self.finished_error.emit(str(e))


class DesignAnalyseWorker(QThread):
    """Background worker for Assistant → Analyse (external VLM)."""

    finished_ok = pyqtSignal(object)
    finished_error = pyqtSignal(str)

    def __init__(
        self,
        page_image,
        page_index: int,
        fiducial_bbox,
        cv_rects: list,
        parent=None,
    ):
        super().__init__(parent)
        self._page_image = page_image
        self._page_index = page_index
        self._fiducial_bbox = fiducial_bbox
        self._cv_rects = cv_rects

    def run(self):
        try:
            from runtime_assistants.design_assistant import analyse_page

            result = analyse_page(
                self._page_image,
                page_index=self._page_index,
                fiducial_bbox=self._fiducial_bbox,
                cv_rects=self._cv_rects,
            )
            self.finished_ok.emit(result)
        except Exception as e:
            logger.exception("Design Analyse failed")
            self.finished_error.emit(str(e))


class Designer(QMainWindow):
    """Main application window for Designer."""
    
    def __init__(self):
        super().__init__()
        self.setGeometry(100, 100, 1200, 800)
        
        # Load environment variables for default folder location
        load_dotenv()
        self.default_config_folder = os.getenv('DESIGNER_CONFIG_FOLDER', '')
        
        # DesignerConfig instance (set when user loads a config folder)
        self.config = None
        
        # Storage for pages and their bounding boxes
        self.pages = []  # List of PIL Images
        self.fiducials = []  # List of (top_left, bottom_right) tuples for logos
        self.page_field_list = []  # List of lists of Field objects for each page
        self.page_detected_rects = []  # List of lists of detected rectangles for each page
        self.current_page_idx = None  # Track currently displayed page
        
        # Track currently selected field for config updates
        self.selected_field_obj = None  # The currently selected Field object
        self.selected_field_index = None  # Index of selected field in page_field_list
        
        # ORM matcher (initialized when config is loaded; default logo only — per-page logos resolved in process_pages)
        self.matcher = None
        self.fiducial_select_mode = False
        
        # Last field type chosen when converting a detected rect (for default in dialog)
        self._last_field_type = "Tickbox"

        self._analyse_worker: DesignAnalyseWorker | None = None
        self._question_assistant_worker: QuestionAssistantWorker | None = None
        self._question_assistant_dialog: RectangleSelectedDialog | None = None
        self.rectangle_detection_settings = RectangleDetectionSettings()
        self._rect_detect_dialog: DesignerRectangleDetectDialog | None = None
        self._field_edit_dialog: RectangleSelectedDialog | None = None
        self._field_geometry_snapshot = None
        self._grid_designer: GridDesigner | None = None
        self._editing_grid_index: int | None = None
        
        # Initialize UI
        self.init_ui()
        if hasattr(self, "edit_panel"):
            self.edit_panel.page_json_changed.connect(self.on_page_json_changed)
        # Restore last folder and page from AppData if available
        self._try_restore_last_session()
        self._update_window_title()
    
    def init_ui(self):
        """Initialize the user interface."""
        # Create menu bar
        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')
        
        load_config_action = QAction('Load Config Folder', self)
        load_config_action.setShortcut('Ctrl+O')
        load_config_action.triggered.connect(self.load_config_folder)
        file_menu.addAction(load_config_action)

        indexing_menu = menubar.addMenu("Indexing Config")
        self.indexing_config_action = QAction("Basic Indexing Config", self)
        self.indexing_config_action.setEnabled(False)
        self.indexing_config_action.setToolTip(
            "Set project_name, batch_folder, import file, lookup list, and pages without fiducial."
        )
        self.indexing_config_action.triggered.connect(self._open_indexing_config_dialog)
        indexing_menu.addAction(self.indexing_config_action)

        self.create_test_batch_action = QAction("Create Test Batch", self)
        self.create_test_batch_action.setEnabled(False)
        self.create_test_batch_action.setToolTip(
            "Create a sample batch under batch_folder for Indexer (copies of template.pdf)."
        )
        self.create_test_batch_action.triggered.connect(self._open_create_test_batch_dialog)
        indexing_menu.addAction(self.create_test_batch_action)

        fiducials_menu = menubar.addMenu("Fiducials")
        self.fiducial_select_action = QAction("Select rectangle", self)
        self.fiducial_select_action.setCheckable(True)
        self.fiducial_select_action.setEnabled(False)
        self.fiducial_select_action.setToolTip(
            "Draw a rectangle on the current page to save fiducials/logo-pN.png "
            "(overrides logo.png for that page when matching)."
        )
        self.fiducial_select_action.triggered.connect(self._on_fiducial_select_toggled)
        fiducials_menu.addAction(self.fiducial_select_action)

        assistant_menu = menubar.addMenu("Assistant")
        self.analyse_action = QAction("Analyse", self)
        self.analyse_action.setShortcut("Ctrl+Shift+A")
        self.analyse_action.setEnabled(False)
        self.analyse_action.setToolTip(
            "Send the current page to an external vision model (Gemini) "
            "to propose field zones and question metadata. Requires GOOGLE_API_KEY or GEMINI_API_KEY."
        )
        self.analyse_action.triggered.connect(self.run_design_analyse)
        assistant_menu.addAction(self.analyse_action)

        help_menu = menubar.addMenu("Help")
        designer_help_action = QAction("Designer", self)
        designer_help_action.setShortcut("F1")
        designer_help_action.setToolTip("Open Designer user instructions in your browser.")
        designer_help_action.triggered.connect(
            lambda _checked=False: self._open_help_page("designer.html")
        )
        help_menu.addAction(designer_help_action)

        templates_help_action = QAction("Templates", self)
        templates_help_action.setToolTip(
            "Open Templates and project setup instructions in your browser."
        )
        templates_help_action.triggered.connect(
            lambda _checked=False: self._open_help_page("templates.html")
        )
        help_menu.addAction(templates_help_action)
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # Left panel: Thumbnail panel
        self.thumbnail_panel = DesignerThumbnailPanel()
        self.thumbnail_panel.thumbnail_clicked.connect(self.on_thumbnail_clicked)
        main_layout.addWidget(self.thumbnail_panel)
        
        # Center panel: Image display with controls
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Control buttons (moved into DesignerButtonLayout)
        button_layout = DesignerButtonLayout(self)
        right_layout.addLayout(button_layout)
        
        # Image display
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #2b2b2b; }")
        
        self.image_display = ImageDisplayWidget(self.scroll_area)
        self.scroll_area.setWidget(self.image_display)
        right_layout.addWidget(self.scroll_area, stretch=1)

        main_layout.addWidget(right_panel, stretch=2)

        # Right-side panel: field / rectangle editor and JSON view
        self.edit_panel = DesignerEditPanel(self)
        main_layout.addWidget(self.edit_panel, stretch=1)

        # Wire selection callback from image widget to edit panel
        self.image_display.on_field_selected = self.on_field_selected
        self.image_display.on_geometry_changed = self._on_field_geometry_changed
        self.image_display.on_grid_selected = self.on_grid_selected
    
    def _load_config_from_path(self, folder_path: str) -> bool:
        """Load config from a folder path (no dialog). Clears existing pages. Returns True on success."""
        # Clear existing state so we don't append to a previous load
        self.pages.clear()
        self.fiducials.clear()
        self.page_field_list.clear()
        self.page_detected_rects.clear()
        self.current_page_idx = None
        self.fiducial_select_mode = False
        if hasattr(self, "fiducial_select_action"):
            self.fiducial_select_action.setChecked(False)
            self.fiducial_select_action.setEnabled(False)
        if hasattr(self, "analyse_action"):
            self.analyse_action.setEnabled(False)
        if hasattr(self, "indexing_config_action"):
            self.indexing_config_action.setEnabled(False)
            self.create_test_batch_action.setEnabled(False)
        self._close_rectangle_detect_dialog()

        config_resolved = resolve_path_case_insensitive(folder_path)
        if config_resolved is None or not config_resolved.is_dir():
            return False
        config_folder = config_resolved
        self.config = DesignerConfig(config_folder)

        logger.info(f"Loaded config folder: {config_folder}")

        logo_path = find_default_logo(self.config.fiducials_folder)

        if logo_path:
            self.matcher = ORMMatcher(str(logo_path))
            logger.info(f"Initialized ORM matcher with default logo: {logo_path}")
        else:
            self.matcher = None
            logger.warning(
                "No default logo in fiducials folder; per-page logo-pN.png files may still be used"
            )

        if not self.config.template_path.exists():
            return False
        self.rectangle_detection_settings = load_rectangle_detection_settings(
            str(self.config.json_folder)
        )
        self.load_multipage_tiff(str(self.config.template_path))
        if hasattr(self, "indexing_config_action"):
            self.indexing_config_action.setEnabled(True)
            self.create_test_batch_action.setEnabled(True)
        self._update_window_title()
        return True

    def _update_window_title(self) -> None:
        """Set window title to 'Form Zone Designer' with optional project name."""
        title = "Form Zone Designer"
        if self.config:
            config = self._load_project_config() or {}
            name = str(config.get("project_name") or "").strip() or Path(self.config.config_folder).name
            title += " - " + name
        self.setWindowTitle(title)

    def _load_project_config(self) -> dict | None:
        """Load project_config.json for the current project, if available."""
        if not self.config:
            return None
        config = load_project_config(self.config.json_folder)
        return config or None

    def _open_help_page(self, filename: str) -> None:
        """Open a USER_INSTRUCTIONS HTML page in the default browser."""
        path = user_instructions_html_path(filename)
        if path is None:
            QMessageBox.warning(
                self,
                "Help",
                f"Could not find help file '{filename}'.",
            )
            return
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
        if not opened:
            QMessageBox.warning(
                self,
                "Help",
                f"Could not open help file:\n{path}",
            )

    def _open_indexing_config_dialog(self) -> None:
        """Edit Basic Indexing Config and merge into project_config.json."""
        if not self.config:
            QMessageBox.warning(
                self,
                "Indexing Config",
                "Load a config folder first (File → Load Config Folder).",
            )
            return
        initial = indexing_config_from_project(
            self._load_project_config() or {},
            default_project_name=Path(self.config.config_folder).name,
        )
        dialog = DesignerIndexingConfigDialog(
            self,
            initial=initial,
            start_dir=str(self.config.config_folder),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        save_indexing_config(self.config.json_folder, dialog.values())
        self._update_window_title()
        self._refresh_fiducials_from_config()

    def _open_create_test_batch_dialog(self) -> None:
        """Create a test batch folder under the configured batch_folder."""
        if not self.config:
            QMessageBox.warning(
                self,
                "Create Test Batch",
                "Load a config folder first (File → Load Config Folder).",
            )
            return
        config = self._load_project_config() or {}
        batch_folder = str(config.get("batch_folder", "")).strip()
        import_filename = str(config.get("import_filename", "")).strip()
        if not batch_folder or not import_filename:
            QMessageBox.warning(
                self,
                "Create Test Batch",
                "Set batch_folder and import_filename in Indexing Config → Basic Indexing Config first.",
            )
            return
        dialog = DesignerCreateTestBatchDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        batch_root = Path(batch_folder)
        if not batch_root.is_absolute():
            batch_root = Path(self.config.config_folder) / batch_root
        try:
            template_path = resolve_template_pdf_source(self.config.config_folder)
            dest = create_test_batch(
                batch_folder=batch_root,
                batch_name=dialog.batch_name(),
                document_count=dialog.document_count(),
                template_path=template_path,
                import_filename=import_filename,
            )
        except CreateTestBatchError as e:
            QMessageBox.warning(self, "Create Test Batch", str(e))
            return
        except Exception as e:
            logger.exception("Create Test Batch failed")
            QMessageBox.critical(self, "Create Test Batch", str(e))
            return
        QMessageBox.information(self, "Create Test Batch", f"Created test batch:\n{dest}")

    def _refresh_fiducials_from_config(self) -> None:
        """Re-run fiducial detection after pages_without_fiducial changes."""
        if not self.config or not self.pages:
            return
        config = self._load_project_config() or {}
        pages_without = {int(x) for x in config.get("pages_without_fiducial", [])}
        self.fiducials = []
        for idx, page in enumerate(self.pages):
            if idx in pages_without:
                self.fiducials.append(None)
                logger.info("Page %d: Skipping fiducial (pages_without_fiducial)", idx + 1)
            else:
                self.fiducials.append(self._detect_fiducial_on_page(idx, page))
        self.thumbnail_panel.populate_thumbnails(self.pages, self.fiducials, self.page_field_list)
        if self.current_page_idx is not None:
            self.on_thumbnail_clicked(self.current_page_idx)

    def _try_restore_last_session(self) -> None:
        """Restore last config folder and page from AppData if valid."""
        state = load_state()
        folder = (state.get("last_config_folder") or "").strip()
        if not folder or resolve_path_case_insensitive(folder) is None:
            return
        folder_resolved = resolve_path_case_insensitive(folder)
        if find_project_template(folder_resolved) is None:
            return
        try:
            if not self._load_config_from_path(folder):
                return
            save_state(last_config_folder=folder)
            page_idx = state.get("last_page_index")
            if page_idx is None or page_idx < 0 or page_idx >= len(self.pages):
                page_idx = 0
            self.on_thumbnail_clicked(page_idx)
            save_state(last_page_index=page_idx)
        except Exception as e:
            logger.warning("Could not restore last session: %s", e)

    def load_config_folder(self):
        """Open folder picker to select a config folder and load it."""
        state = load_state()
        default_path = (
            (state.get("last_config_folder") or "").strip()
            or self.default_config_folder
            or str(Path.home())
        )

        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Config Folder",
            default_path,
            QFileDialog.Option.ShowDirsOnly
        )

        if not folder_path:
            return

        try:
            if not self._load_config_from_path(folder_path):
                QMessageBox.warning(
                    self,
                    "Template Not Found",
                    f"Template file not found: {self.config.template_path}"
                )
                return
            save_state(last_config_folder=folder_path)
            state = load_state()
            page_idx = state.get("last_page_index")
            if page_idx is None or page_idx < 0 or page_idx >= len(self.pages):
                page_idx = 0
            self.on_thumbnail_clicked(page_idx)
            save_state(last_page_index=page_idx)
        except FileNotFoundError as e:
            QMessageBox.critical(
                self,
                "Config Error",
                f"Failed to load config folder:\n{str(e)}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while loading config folder:\n{str(e)}"
            )
            logger.error(f"Error loading config folder: {e}", exc_info=True)
    
    def load_multipage_tiff(self, document_path):
        """Load a multipage template (TIFF or PDF) and process each page."""
        try:
            loader = get_document_loader_for_path(document_path)
            self.pages.extend(loader.load_pages(document_path))

            logger.debug("Loaded %d pages from %s", len(self.pages), document_path)

            self.process_pages()
            self.thumbnail_panel.populate_thumbnails(self.pages, self.fiducials, self.page_field_list)

        except Exception as e:
            logger.error("Error loading template %s: %s", document_path, e)
    
    def process_pages(self):
        """Run ORM matcher on each page to find logo bounding boxes."""
        pages_without_fiducial = []
        if self.config:
            config = self._load_project_config()
            if config:
                pages_without_fiducial = list(config.get("pages_without_fiducial", []))

        self.fiducials = []
        for idx, page in enumerate(self.pages):
            if idx in pages_without_fiducial:
                self.fiducials.append(None)
                logger.info(f"Page {idx + 1}: Skipping fiducial (pages_without_fiducial)")
            else:
                bbox = self._detect_fiducial_on_page(idx, page)
                self.fiducials.append(bbox)
                if bbox:
                    logger.info(f"Page {idx + 1}: Logo found at {bbox[0]}")
                else:
                    logger.warning(f"Page {idx + 1}: No logo found")

            self.page_field_list.append([])
            self.page_detected_rects.append([])

        if self.config:
            for idx in range(len(self.pages)):
                fields = load_page_fields(str(self.config.json_folder), idx, self.config.config_folder)
                self.page_field_list[idx] = fields

    def _detect_fiducial_on_page(self, page_idx: int, page: Image.Image):
        """Return (top_left, bottom_right) for page_idx or None."""
        if not self.config:
            return None
        logo_path = find_fiducial_for_page(self.config.fiducials_folder, page_idx)
        if logo_path is None:
            return None
        page_array = np.array(page)
        page_cv = cv2.cvtColor(page_array, cv2.COLOR_RGB2BGR)
        matcher = ORMMatcher(str(logo_path))
        matcher.locate_from_cv2_image(page_cv)
        if matcher.top_left and matcher.bottom_right:
            return (matcher.top_left, matcher.bottom_right)
        return None

    def _save_page_fields(self, page_idx: int) -> None:
        """Persist fields for page_idx, then warn if any field name is now a duplicate.

        Centralised so every save site gets the project-wide duplicate-name check.
        """
        if not self.config:
            return
        save_page_fields(
            str(self.config.json_folder),
            page_idx,
            self.page_field_list,
            self.config.config_folder,
        )
        self._check_duplicate_field_names()

    def _check_duplicate_field_names(self) -> None:
        """Warn (non-blocking) if any field name is duplicated across or within pages.

        Indexer and Exporter key CSV columns and values by ``field.name``, so names must
        be unique project-wide.
        """
        duplicates = find_duplicate_field_names(self.page_field_list)
        if not duplicates:
            return
        lines = []
        for name, pages in sorted(duplicates.items()):
            counts = Counter(pages)
            page_desc = ", ".join(
                f"page {p}" + (f" (×{n})" if n > 1 else "")
                for p, n in sorted(counts.items())
            )
            lines.append(f"'{name}' — {page_desc}")
        QMessageBox.warning(
            self,
            "Duplicate field names",
            "Field names must be unique across the whole project (Indexer and Exporter "
            "key CSV columns and values by name). Rename these before indexing:\n\n"
            + "\n".join(lines),
        )

    def on_thumbnail_clicked(self, page_idx):
        """Handle thumbnail click event to display full-size page."""
        
        if 0 <= page_idx < len(self.pages):
            # Clear selected field when changing pages
            self.selected_field_obj = None
            self.selected_field_index = None
            if self.edit_panel:
                self.edit_panel.set_field_from_object(None)
            
            self.current_page_idx = page_idx
            self.thumbnail_panel.set_current_page(page_idx)
            page = self.pages[page_idx]
            bbox = self.fiducials[page_idx]
            field_list = self.page_field_list[page_idx]
            detected_rects = self.page_detected_rects[page_idx]
            
            # Convert PIL Image to QPixmap
            page_array = np.array(page)
            height, width, channel = page_array.shape
            bytes_per_line = 3 * width
            q_image = QImage(page_array.data, width, height, 
                           bytes_per_line, QImage.Format.Format_RGB888)
            page_pixmap = QPixmap.fromImage(q_image)

            # Display with bounding box overlay and field list
            self.image_display.set_image(page_pixmap, bbox, field_list, detected_rects)
            
            # Set callback to update thumbnail when a rectangle is added (e.g. from dialog submit)
            def on_rect_added_handler(field_obj):
                self.page_field_list[self.current_page_idx].append(field_obj)
                self.update_thumbnail(self.current_page_idx)
                self.undo_button.setEnabled(True)
                logger.info(f"Page {self.current_page_idx + 1}: Added {field_obj.__class__.__name__} '{field_obj.name}' at ({field_obj.x}, {field_obj.y})")

            self.image_display.on_rect_added = on_rect_added_handler
            self.image_display.on_detected_rect_clicked = self._on_detected_rect_clicked
            self.image_display.on_rect_drawn = self._on_rect_drawn
            self.image_display.fiducial_select_mode = self.fiducial_select_mode
            self.image_display.on_fiducial_rect_drawn = self._on_fiducial_rect_drawn

            self.fiducial_select_action.setEnabled(True)
            if hasattr(self, "analyse_action"):
                self.analyse_action.setEnabled(True)

            # Update JSON editor for the current page
            self._update_edit_panel_json(page_idx)
            
            # Enable/disable buttons based on current state
            self.detect_button.setEnabled(True)
            self.clear_button.setEnabled(True)
            self.undo_button.setEnabled(len(field_list) > 0)
            self.grid_designer_button.setEnabled(bbox is not None)
            self._update_remove_inner_button_state()

            if (
                self._rect_detect_dialog is not None
                and self._rect_detect_dialog.isVisible()
            ):
                self._run_rectangle_detection(self.rectangle_detection_settings)

            # Enable zoom/fit controls now that an image is available
            self.fit_width_button.setEnabled(True)
            self.fit_height_button.setEnabled(True)
            self.autofit_button.setEnabled(True)
            self.zoom_in_button.setEnabled(True)
            self.zoom_out_button.setEnabled(True)

            # Update JSON editor for the current page
            self._update_edit_panel_json(page_idx)

            # Persist last page viewed so it restores on next launch
            if self.config:
                save_state(last_page_index=page_idx)

    def open_grid_designer(self, existing_grid: RadioGrid | None = None):
        """Open Grid Designer to create or edit a RadioGrid on the current page."""
        if not isinstance(existing_grid, RadioGrid):
            existing_grid = None
        if self.current_page_idx is None or not (0 <= self.current_page_idx < len(self.pages)):
            return
        bbox = self.fiducials[self.current_page_idx] if self.current_page_idx < len(self.fiducials) else None
        if bbox is None:
            return
        self._close_field_edit_dialog(revert=True)
        page = self.pages[self.current_page_idx]
        page_array = np.array(page)
        h, w = page_array.shape[:2]
        bytes_per_line = 3 * w
        q_image = QImage(page_array.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        page_pixmap = QPixmap.fromImage(q_image)
        gd = GridDesigner(self)
        gd.set_page(page_pixmap, bbox)
        detected = (
            self.page_detected_rects[self.current_page_idx]
            if self.current_page_idx < len(self.page_detected_rects)
            else []
        )
        gd.set_assistant_inputs(page, bbox, detected)
        if existing_grid is not None:
            self._editing_grid_index = self._index_of_grid(existing_grid)
            gd.load_grid(existing_grid)
        else:
            self._editing_grid_index = None
        gd.grid_submitted.connect(self._on_grid_designer_submitted)
        self._grid_designer = gd
        gd.showMaximized()

    def _index_of_grid(self, grid: RadioGrid) -> int | None:
        if self.current_page_idx is None:
            return None
        fields = self.page_field_list[self.current_page_idx]
        for idx, field in enumerate(fields):
            if isinstance(field, RadioGrid) and field.grid_id == grid.grid_id:
                return idx
            if field is grid:
                return idx
        return None

    def _on_grid_designer_submitted(self, grid: RadioGrid):
        """Create or update a RadioGrid on the current page."""
        if self.current_page_idx is None or not (0 <= self.current_page_idx < len(self.page_field_list)):
            return
        page_fields = self.page_field_list[self.current_page_idx]
        if self._editing_grid_index is not None and 0 <= self._editing_grid_index < len(page_fields):
            page_fields[self._editing_grid_index] = grid
            logger.info("Page %s: Updated RadioGrid '%s'", self.current_page_idx + 1, grid.name)
        else:
            page_fields.append(grid)
            logger.info("Page %s: Added RadioGrid '%s'", self.current_page_idx + 1, grid.name)
        self._editing_grid_index = None
        self._grid_designer = None
        if self.config:
            self._save_page_fields(self.current_page_idx)
        self.image_display.field_list = page_fields
        self.image_display.update_display()
        self.update_thumbnail(self.current_page_idx)
        self._update_edit_panel_json(self.current_page_idx)
        self.undo_button.setEnabled(True)

    def on_grid_selected(self, grid: RadioGrid, global_pos):
        """User clicked a RadioGrid on the page — reopen Grid Designer to reshape."""
        if self.edit_panel:
            self.edit_panel.fields_table.highlight_field(grid.name, "RadioGrid")
        self.open_grid_designer(existing_grid=grid)

    def _on_fiducial_select_toggled(self, checked: bool) -> None:
        self.fiducial_select_mode = checked
        if hasattr(self, "image_display"):
            self.image_display.fiducial_select_mode = checked
        if checked:
            self.statusBar().showMessage(
                "Fiducial mode: draw a rectangle on the template to define this page's logo patch.",
                8000,
            )
        else:
            self.statusBar().clearMessage()

    def _on_fiducial_rect_drawn(self, rect: tuple[int, int, int, int]) -> None:
        """Save cropped template region as fiducials/logo-pN.png and refresh fiducial on this page."""
        if self.current_page_idx is None or not self.config:
            return
        x, y, w, h = rect
        page = self.pages[self.current_page_idx]
        pw, ph = page.size
        x = max(0, min(x, pw - 1))
        y = max(0, min(y, ph - 1))
        w = max(1, min(w, pw - x))
        h = max(1, min(h, ph - y))

        out_name = per_page_logo_filename(self.current_page_idx)
        out_path = self.config.fiducials_folder / out_name
        try:
            crop = page.crop((x, y, x + w, y + h))
            crop.save(out_path, "PNG")
        except OSError as e:
            QMessageBox.warning(self, "Save fiducial", f"Could not save {out_name}:\n{e}")
            return

        bbox = self._detect_fiducial_on_page(self.current_page_idx, page)
        self.fiducials[self.current_page_idx] = bbox
        self.image_display.bbox = bbox
        self.image_display.update_display()
        self.update_thumbnail(self.current_page_idx)
        self.grid_designer_button.setEnabled(bbox is not None)

        if self.fiducial_select_action.isChecked():
            self.fiducial_select_action.setChecked(False)

        self.statusBar().showMessage(
            f"Saved {out_name} and updated fiducial for page {self.current_page_idx + 1}.",
            6000,
        )
        logger.info("Saved per-page fiducial %s (%dx%d at %d,%d)", out_path, w, h, x, y)

    def on_page_json_changed(self, field_order: list):
        """
        Handle field order changes from the field list table (drag/drop).
        
        Args:
            field_order: List of (field_name, field_type) tuples in the new order
        """
        if self.current_page_idx is None:
            return

        if not field_order:
            # Empty order - treat as no-op
            return

        page_idx = self.current_page_idx
        if page_idx < 0 or page_idx >= len(self.page_field_list):
            return

        # Get current fields for this page
        current_fields = self.page_field_list[page_idx]
        
        # Create lookup: (name, type) -> list of Field objects (handles duplicates)
        # We use a list because there could be multiple fields with same name+type
        field_lookup = {}
        for idx, field in enumerate(current_fields):
            if type(field) == Field:
                # Skip base Field instances
                continue
            field_type = field.__class__.__name__
            key = (field.name, field_type)
            if key not in field_lookup:
                field_lookup[key] = []
            field_lookup[key].append((idx, field))
        
        # Reorder fields based on the new order
        reordered_fields = []
        used_indices = set()
        
        # First pass: match fields by (name, type)
        for field_name, field_type in field_order:
            key = (field_name, field_type)
            if key in field_lookup and field_lookup[key]:
                # Get the first unused field with this name+type
                for idx, field in field_lookup[key]:
                    if idx not in used_indices:
                        reordered_fields.append(field)
                        used_indices.add(idx)
                        break
                else:
                    # All fields with this name+type are used, log warning
                    logger.warning(
                        f"Field '{field_name}' (type: {field_type}) in order list "
                        f"but all matching fields already used"
                    )
            else:
                # Field not found in current fields
                logger.warning(
                    f"Field '{field_name}' (type: {field_type}) in order list "
                    f"but not found in page_field_list"
                )
        
        # Second pass: add any remaining fields that weren't in the order list
        # (preserve them at the end)
        for idx, field in enumerate(current_fields):
            if idx not in used_indices and type(field) != Field:
                reordered_fields.append(field)
                logger.debug(
                    f"Preserving field '{field.name}' (type: {field.__class__.__name__}) "
                    f"that wasn't in order list"
                )

        # Update in-memory structures
        self.page_field_list[page_idx] = reordered_fields

        # Persist to disk
        if self.config:
            self._save_page_fields(page_idx)

        # Update UI (image display + thumbnail)
        self.image_display.field_list = reordered_fields
        self.image_display.update_display()
        self.update_thumbnail(page_idx)
        
        # Update JSON editor to reflect the reordered fields
        self._update_edit_panel_json(page_idx)

    def _update_edit_panel_json(self, page_idx: int):
        """Populate the edit panel JSON area with the current page's fields."""
        if not self.edit_panel:
            return

        if page_idx < 0 or page_idx >= len(self.page_field_list):
            self.edit_panel.set_page_json("")
            return

        fields_for_page = self.page_field_list[page_idx]

        # Convert field objects to serializable dicts using the same logic as save_page_fields
        fields_data = []
        for field_obj in fields_for_page:
            if isinstance(field_obj, Field):
                # Filter out base Field instances
                if type(field_obj) != Field:
                    fields_data.append(field_obj.to_dict())

        try:
            json_text = json.dumps(fields_data, indent=2, default=str)
        except TypeError:
            json_text = ""

        self.edit_panel.set_page_json(json_text)

    def _on_field_geometry_changed(self):
        """Refresh JSON preview while reshaping a field (dialog stays open)."""
        if self.current_page_idx is not None:
            self._update_edit_panel_json(self.current_page_idx)
        if self._field_edit_dialog is not None and self.selected_field_obj is not None:
            self._field_edit_dialog.sync_geometry_from_field(self.selected_field_obj)

    def _on_field_edit_geometry_typed(self, x: int, y: int, width: int, height: int):
        field = self.selected_field_obj
        if field is None:
            return
        field.x = x
        field.y = y
        field.width = width
        field.height = height
        if self.image_display:
            self.image_display.update_display()
        if self.current_page_idx is not None:
            self._update_edit_panel_json(self.current_page_idx)

    def _close_field_edit_dialog(self, *, revert: bool = False):
        if self._field_edit_dialog is not None:
            self._field_edit_dialog.blockSignals(True)
            self._field_edit_dialog.close()
            self._field_edit_dialog.deleteLater()
            self._field_edit_dialog = None
        if (
            revert
            and self._field_geometry_snapshot is not None
            and self.image_display.edit_geometry_field is not None
        ):
            restore_field_geometry(
                self.image_display.edit_geometry_field,
                self._field_geometry_snapshot,
            )
            self.image_display.update_display()
        self._field_geometry_snapshot = None
        self.image_display.end_field_edit()

    def _on_field_edit_cancelled(self):
        self._close_field_edit_dialog(revert=True)

    def _on_field_edit_submitted(self, config: dict):
        self._close_field_edit_dialog(revert=False)
        self.on_field_config_changed(config)

    def _on_field_edit_deleted(self):
        self._close_field_edit_dialog(revert=False)
        self.delete_current_rectangle()

    def on_field_selected(self, field_obj, global_pos):
        """
        Called when the user clicks on an existing field on the image.
        Updates preview, highlights the field in the list, opens non-modal dialog,
        and enables reshape handles on the canvas.
        """
        if not self.edit_panel or self.current_page_idx is None:
            return

        self._close_field_edit_dialog(revert=True)

        # Store reference to selected field and find its index
        self.selected_field_obj = field_obj
        self.selected_field_index = None
        parent_group = None
        if 0 <= self.current_page_idx < len(self.page_field_list):
            field_list = self.page_field_list[self.current_page_idx]
            # If the selected field is a RadioButton, it may belong to a RadioGroup (not in list)
            if isinstance(field_obj, RadioButton):
                for idx, field in enumerate(field_list):
                    if isinstance(field, RadioGroup) and field_obj in field.radio_buttons:
                        self.selected_field_index = idx
                        parent_group = field
                        break
            if self.selected_field_index is None:
                for idx, field in enumerate(field_list):
                    if field is field_obj or (
                        field.x == field_obj.x and
                        field.y == field_obj.y and
                        field.width == field_obj.width and
                        field.height == field_obj.height
                    ):
                        self.selected_field_index = idx
                        break
            if parent_group is None and isinstance(field_obj, RadioGroup):
                parent_group = field_obj

        geo_target = geometry_edit_target(field_obj, parent_group)
        self._field_geometry_snapshot = snapshot_field_geometry(geo_target)
        self.image_display.start_field_edit(field_obj, parent_group)

        # Update preview strip
        page = self.pages[self.current_page_idx]
        page_array = np.array(page)
        height, width, _ = page_array.shape
        abs_x = field_obj.x
        abs_y = field_obj.y
        if self.fiducials[self.current_page_idx]:
            logo_top_left = self.fiducials[self.current_page_idx][0]
            abs_x += logo_top_left[0]
            abs_y += logo_top_left[1]
        top = max(0, abs_y - 50)
        bottom = min(height, abs_y + field_obj.height + 50)
        strip = page_array[top:bottom, :, :]
        if strip.size == 0:
            self.edit_panel.set_preview_pixmap(QPixmap())
        else:
            strip_height, strip_width, channel = strip.shape
            bytes_per_line = 3 * strip_width
            q_image = QImage(
                strip.data, strip_width, strip_height,
                bytes_per_line, QImage.Format.Format_RGB888,
            )
            self.edit_panel.set_preview_pixmap(QPixmap.fromImage(q_image))

        # Highlight field in the field list
        self.edit_panel.fields_table.highlight_field(field_obj.name, type(field_obj).__name__)

        # Open RectangleSelectedDialog (existing field: pre-fill name/type, RadioGroup disabled)
        dialog = RectangleSelectedDialog(
            self,
            QPoint(int(global_pos.x()), int(global_pos.y())),
            is_just_drawn=False,
            existing_field=field_obj,
            inner_rect_count=0,
            non_modal=True,
        )
        dialog.submitted.connect(self._on_field_edit_submitted)
        dialog.deleted.connect(self._on_field_edit_deleted)
        dialog.cancelled.connect(self._on_field_edit_cancelled)
        dialog.geometry_edited.connect(self._on_field_edit_geometry_typed)
        self._field_edit_dialog = dialog
        dialog.show()

    def on_field_config_changed(self, config: dict):
        """
        Handle changes to field type or name from the edit panel.
        Updates the currently selected field with the new configuration.
        """
        if self.current_page_idx is None or self.selected_field_index is None:
            return
        
        if not (0 <= self.current_page_idx < len(self.page_field_list)):
            return
        
        if not (0 <= self.selected_field_index < len(self.page_field_list[self.current_page_idx])):
            return
        
        # Get the field at the selected index (may be a RadioGroup when we selected a RadioButton)
        field_at_index = self.page_field_list[self.current_page_idx][self.selected_field_index]
        
        # If the user edited a RadioButton inside a RadioGroup, update that button in place
        if (isinstance(field_at_index, RadioGroup) and
                isinstance(self.selected_field_obj, RadioButton) and
                self.selected_field_obj in field_at_index.radio_buttons):
            rb = self.selected_field_obj
            nested_config = dict(config)
            nested_config["field_type"] = type(rb).__name__
            updated = apply_field_edit(rb, nested_config)
            idx = field_at_index.radio_buttons.index(rb)
            field_at_index.radio_buttons[idx] = updated
            self.selected_field_obj = updated
            if self.config:
                self._save_page_fields(self.current_page_idx)
            if self.image_display:
                self.image_display.update_display()
            self._update_edit_panel_json(self.current_page_idx)
            return

        old_field = field_at_index
        try:
            new_field = apply_field_edit(old_field, config)
        except ValueError:
            logger.error("Invalid field type: %s", config.get("field_type"))
            return

        # Converting into a RadioGroup: scoop top-level RadioButtons inside the frame.
        # Existing RadioGroups keep nested buttons via apply_field_edit.
        if isinstance(new_field, RadioGroup) and not isinstance(old_field, RadioGroup):
            page_fields = self.page_field_list[self.current_page_idx]
            radio_buttons_to_remove = []

            for i, field in enumerate(page_fields):
                if i == self.selected_field_index:
                    continue

                if isinstance(field, RadioButton):
                    rb_center_x = field.x + field.width // 2
                    rb_center_y = field.y + field.height // 2
                    if (new_field.x <= rb_center_x <= new_field.x + new_field.width and
                        new_field.y <= rb_center_y <= new_field.y + new_field.height):
                        new_field.add_radio_button(field)
                        radio_buttons_to_remove.append(i)
                        logger.info(
                            f"Page {self.current_page_idx + 1}: Moved RadioButton '{field.name}' "
                            f"into RadioGroup '{new_field.name}'"
                        )

            for i in reversed(radio_buttons_to_remove):
                page_fields.pop(i)
                if i < self.selected_field_index:
                    self.selected_field_index -= 1

        self.page_field_list[self.current_page_idx][self.selected_field_index] = new_field
        self.selected_field_obj = new_field
        
        # Persist to disk
        if self.config:
            self._save_page_fields(self.current_page_idx)
        
        # Update image display
        if self.image_display:
            self.image_display.field_list = self.page_field_list[self.current_page_idx]
            self.image_display.update_display()
        
        # Update thumbnail
        self.update_thumbnail(self.current_page_idx)
        
        # Update JSON editor to reflect the change
        self._update_edit_panel_json(self.current_page_idx)
        
        logger.info(
            "Page %s: Updated field to %s '%s' at (%s, %s)",
            self.current_page_idx + 1,
            type(new_field).__name__,
            new_field.name,
            new_field.x,
            new_field.y,
        )

    def _on_detected_rect_clicked(self, rect_index: int, rect_xywh_abs, global_pos):
        """User left-clicked a detected rectangle: show dialog; on submit convert to field, on delete remove rect."""
        if self.current_page_idx is None or not (0 <= self.current_page_idx < len(self.page_detected_rects)):
            return
        rects = self.page_detected_rects[self.current_page_idx]
        if rect_index < 0 or rect_index >= len(rects):
            return
        x_abs, y_abs, w, h = rects[rect_index]
        logo_top_left = self.fiducials[self.current_page_idx][0] if self.fiducials[self.current_page_idx] else (0, 0)
        x_rel = x_abs - logo_top_left[0]
        y_rel = y_abs - logo_top_left[1]

        dialog = RectangleSelectedDialog(
            self,
            QPoint(int(global_pos.x()), int(global_pos.y())),
            is_just_drawn=False,
            existing_field=None,
            inner_rect_count=0,
            default_field_type=self._last_field_type,
        )

        def on_submit(config: dict):
            field_type = config.get("field_type", "Tickbox")
            field_name = config.get("field_name", "").strip()
            if not field_name:
                return
            self._last_field_type = field_type
            field_class = FIELD_TYPE_MAP.get(field_type, Tickbox)
            kwargs = {"name": field_name, "x": int(x_rel), "y": int(y_rel), "width": int(w), "height": int(h)}
            if field_class == RadioGroup:
                kwargs["radio_buttons"] = []
            kwargs["colour"] = default_colour_tuple_for_type(field_type)
            new_field = field_class(**kwargs)
            self.page_detected_rects[self.current_page_idx].pop(rect_index)
            self.page_field_list[self.current_page_idx].append(new_field)
            self.image_display.detected_rects = self.page_detected_rects[self.current_page_idx]
            self.image_display.field_list = self.page_field_list[self.current_page_idx]
            if self.config:
                self._save_page_fields(self.current_page_idx)
            self.image_display.update_display()
            self.update_thumbnail(self.current_page_idx)
            self._update_edit_panel_json(self.current_page_idx)
            self.undo_button.setEnabled(True)
            logger.info(f"Page {self.current_page_idx + 1}: Converted detected rect to {field_type} '{field_name}'")

        def on_deleted():
            self.page_detected_rects[self.current_page_idx].pop(rect_index)
            self.image_display.detected_rects = self.page_detected_rects[self.current_page_idx]
            self.image_display.update_display()
            self._update_remove_inner_button_state()
            logger.info(f"Page {self.current_page_idx + 1}: Deleted detected rectangle")

        dialog.submitted.connect(on_submit)
        dialog.deleted.connect(on_deleted)
        dialog.exec()

    def _export_columns_block_for_current_page(self) -> str:
        if not self.config:
            return ""
        try:
            from runtime_assistants.design_assistant.export_assistant_for_designer.io import (
                load_active_export_format,
            )
            from runtime_assistants.design_assistant.export_assistant_for_designer.check import (
                export_columns_for_prompt,
            )
            from runtime_assistants.design_assistant.export_assistant_for_designer.prompt_context import (
                format_export_columns_block,
            )

            descriptor = load_active_export_format(self.config.config_folder)
            if descriptor is None or self.current_page_idx is None:
                return ""
            cols = export_columns_for_prompt(descriptor, self.current_page_idx + 1)
            return format_export_columns_block(cols)
        except Exception:
            logger.debug("Export format context unavailable for Question Assistant", exc_info=True)
            return ""

    def _open_radio_grid_from_drawn_rect(
        self,
        field_name: str,
        drawn_rect_rel: tuple[int, int, int, int],
    ) -> None:
        left_rel, top_rel, w, h = drawn_rect_rel
        if self.image_display:
            self.image_display.clear_selection()
        bbox = (
            self.fiducials[self.current_page_idx]
            if self.current_page_idx is not None
            and self.current_page_idx < len(self.fiducials)
            else None
        )
        if bbox is None:
            QMessageBox.warning(
                self,
                "Grid Designer",
                "A fiducial (logo) must be detected on this page before designing a Radio Grid.",
            )
            return
        provisional = RadioGrid(
            colour=default_colour_tuple_for_type("RadioGrid"),
            name=field_name.strip() or "Grid",
            x=int(left_rel),
            y=int(top_rel),
            width=int(w),
            height=int(h),
        )
        QTimer.singleShot(0, lambda g=provisional: self.open_grid_designer(existing_grid=g))

    def _pop_detected_rects_matching(self, inner_rects_rel: list) -> None:
        """Remove OpenCV rects that match the given fiducial-relative inner boxes."""
        logo = (
            self.fiducials[self.current_page_idx][0]
            if self.fiducials[self.current_page_idx]
            else (0, 0)
        )
        det = self.page_detected_rects[self.current_page_idx]
        to_remove = []
        for j, rect in enumerate(det):
            ra, rb_val, rw_val, rh_val = rect
            for irx, iry, iw, ih in inner_rects_rel:
                if (
                    ra == irx + logo[0]
                    and rb_val == iry + logo[1]
                    and rw_val == iw
                    and rh_val == ih
                ):
                    to_remove.append(j)
                    break
        for j in reversed(to_remove):
            det.pop(j)

    def _after_page_fields_changed(self, *, clear_selection: bool = False) -> None:
        """Persist current page fields and refresh Designer views."""
        page_fields = self.page_field_list[self.current_page_idx]
        det = self.page_detected_rects[self.current_page_idx]
        if self.image_display:
            if clear_selection:
                self.image_display.clear_selection()
            self.image_display.detected_rects = det
            self.image_display.field_list = page_fields
            self.image_display.update_display()
        if self.config:
            self._save_page_fields(self.current_page_idx)
        self.update_thumbnail(self.current_page_idx)
        self._update_edit_panel_json(self.current_page_idx)
        self._update_remove_inner_button_state()
        self.undo_button.setEnabled(True)

    def _submit_radio_group_from_question_frame(
        self,
        config: dict,
        drawn_rect_rel: tuple[int, int, int, int],
        combined_inner: list,
        field_indices_to_remove: list[int],
        inner_rects_rel: list,
    ) -> None:
        page_fields = self.page_field_list[self.current_page_idx]
        question_number = config.get("question_number", "").strip()
        full_text = config.get("full_text", "").strip()
        field_configs = config.get("fields") or []
        options: list[tuple[str, int, int, int, int]] = []
        for i, fc in enumerate(field_configs):
            if i >= len(combined_inner):
                break
            rx, ry, rw, rh, _ = combined_inner[i]
            field_name = fc.get("field_name", "").strip()
            if not field_name:
                continue
            options.append((field_name, int(rx), int(ry), int(rw), int(rh)))
        if not options:
            return
        left_rel, top_rel, w, h = drawn_rect_rel
        rg = build_radio_group_from_frame(
            x=int(left_rel),
            y=int(top_rel),
            width=int(w),
            height=int(h),
            options=options,
            question_number=question_number,
            full_text=full_text,
        )
        for j in reversed(field_indices_to_remove):
            page_fields.pop(j)
        page_fields.append(rg)
        self._last_field_type = "RadioGroup"
        self._pop_detected_rects_matching(inner_rects_rel)
        self._after_page_fields_changed(clear_selection=True)
        logger.info(
            "Page %s: Added RadioGroup '%s' with %d option(s) from question frame",
            self.current_page_idx + 1,
            rg.name,
            len(rg.radio_buttons),
        )

    def _submit_batch_question_fields(
        self,
        config: dict,
        combined_inner: list,
        field_indices_to_remove: list[int],
        inner_rects_rel: list,
    ) -> None:
        page_fields = self.page_field_list[self.current_page_idx]
        question_number = config.get("question_number", "").strip()
        full_text = config.get("full_text", "").strip()
        field_configs = config.get("fields") or []

        for j in reversed(field_indices_to_remove):
            page_fields.pop(j)

        for i, fc in enumerate(field_configs):
            if i >= len(combined_inner):
                break
            rx, ry, rw, rh, _ = combined_inner[i]
            field_type = fc.get("field_type", "Tickbox")
            field_name = fc.get("field_name", "").strip()
            if not field_name:
                continue
            self._last_field_type = field_type
            field_class = FIELD_TYPE_MAP.get(field_type, Tickbox)
            kwargs = {
                "name": field_name,
                "x": int(rx),
                "y": int(ry),
                "width": int(rw),
                "height": int(rh),
                "colour": default_colour_tuple_for_type(field_type),
                "summary": truncate_summary(field_name),
                "column_title": sanitize_column_title(field_name),
            }
            if question_number:
                kwargs["question_number"] = question_number
            if full_text:
                kwargs["full_text"] = full_text
            if field_class == RadioGroup:
                kwargs["radio_buttons"] = []
            page_fields.append(field_class(**kwargs))

        self._pop_detected_rects_matching(inner_rects_rel)
        self._after_page_fields_changed(clear_selection=True)
        logger.info(
            "Page %s: Added %d fields from question frame",
            self.current_page_idx + 1,
            len(field_configs),
        )

    def _run_question_assistant(
        self,
        dialog: RectangleSelectedDialog,
        drawn_rect_rel: tuple[int, int, int, int],
        inner_rects_fiducial: list[tuple[int, int, int, int]],
    ) -> None:
        if self.current_page_idx is None or not (0 <= self.current_page_idx < len(self.pages)):
            return
        if (
            self._question_assistant_worker is not None
            and self._question_assistant_worker.isRunning()
        ):
            return

        page = self.pages[self.current_page_idx]
        bbox = (
            self.fiducials[self.current_page_idx]
            if self.current_page_idx < len(self.fiducials)
            else None
        )
        cv_rects = list(self.page_detected_rects[self.current_page_idx])

        self._question_assistant_dialog = dialog
        dialog.set_assistant_running(True)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage("Question Assistant analysing…", 0)

        worker = QuestionAssistantWorker(
            page.copy(),
            drawn_rect_rel,
            bbox,
            cv_rects,
            list(inner_rects_fiducial),
            self._export_columns_block_for_current_page(),
            parent=self,
        )
        self._question_assistant_worker = worker
        worker.finished_ok.connect(self._on_question_assistant_ok)
        worker.finished_error.connect(self._on_question_assistant_error)
        worker.finished.connect(self._on_question_assistant_finished)
        worker.start()

    def _on_question_assistant_finished(self):
        QApplication.restoreOverrideCursor()
        if self._question_assistant_dialog is not None:
            self._question_assistant_dialog.set_assistant_running(False)
        self._question_assistant_worker = None
        self.statusBar().clearMessage()

    def _on_question_assistant_error(self, message: str):
        self.statusBar().showMessage(f"Question Assistant failed: {message}", 10000)
        QMessageBox.warning(self, "Question Assistant", message)

    def _on_question_assistant_ok(self, result):
        dialog = self._question_assistant_dialog
        if dialog is None:
            return
        dialog.apply_assistant_result(result)
        msgs = []
        if result.warnings:
            msgs.extend(result.warnings)
        n = getattr(result, "rects_in_roi_count", 0)
        msgs.insert(
            0,
            f"Assistant filled {len(result.fields)} answer field(s) from {n} rectangle(s).",
        )
        self.statusBar().showMessage(" ".join(msgs), 12000)

    def _on_rect_drawn(self, drawn_rect_rel, inner_rects_rel, global_pos):
        """User finished drawing a rectangle: show dialog (RadioGroup enabled); on submit add field(s), on delete discard."""
        if self.current_page_idx is None or not (0 <= self.current_page_idx < len(self.page_field_list)):
            return
        left_rel, top_rel, w, h = drawn_rect_rel
        right_rel = left_rel + w
        bottom_rel = top_rel + h

        # Build combined inner items: detected rects + existing fields fully inside the drawn rect.
        # Sort top-to-bottom then left-to-right so dialog rows / Option N match visual reading order
        # (OpenCV detection order is area-based, not reading order). See sort_rects_reading_order.
        combined_inner = []  # list of (x, y, w, h, default_name)
        field_indices_to_remove = []  # indices in page_field_list to remove when creating RadioGroup
        for rx, ry, rw, rh in inner_rects_rel:
            combined_inner.append((rx, ry, rw, rh, ""))
        page_fields = self.page_field_list[self.current_page_idx]
        for idx, field in enumerate(page_fields):
            if isinstance(field, RadioGroup):
                if (left_rel <= field.x and top_rel <= field.y and
                    field.x + field.width <= right_rel and field.y + field.height <= bottom_rel):
                    for rb in field.radio_buttons:
                        combined_inner.append((rb.x, rb.y, rb.width, rb.height, rb.name))
                    field_indices_to_remove.append(idx)
            else:
                # Tickbox, RadioButton, TextField
                if (left_rel <= field.x and top_rel <= field.y and
                    field.x + field.width <= right_rel and field.y + field.height <= bottom_rel):
                    combined_inner.append((field.x, field.y, field.width, field.height, field.name))
                    field_indices_to_remove.append(idx)

        combined_inner.sort(
            key=lambda item: (item[1] + item[3] / 2.0, item[0] + item[2] / 2.0)
        )
        combined_inner = [
            (x, y, w, h, name or f"Option {i + 1}")
            for i, (x, y, w, h, name) in enumerate(combined_inner)
        ]
        # Keep detection-list removal in sync with sorted geometry
        inner_rects_rel = [(x, y, w, h) for (x, y, w, h, _) in combined_inner]
        inner_count = len(combined_inner)
        inner_default_names = [name for (_, _, _, _, name) in combined_inner]
        inner_geom = list(inner_rects_rel)

        dialog = RectangleSelectedDialog(
            self,
            QPoint(int(global_pos.x()), int(global_pos.y())),
            is_just_drawn=True,
            existing_field=None,
            inner_rect_count=inner_count,
            inner_default_names=inner_default_names,
            default_field_type=self._last_field_type,
        )

        def on_submit(config: dict):
            if config.get("radio_group_mode"):
                self._submit_radio_group_from_question_frame(
                    config,
                    drawn_rect_rel,
                    combined_inner,
                    field_indices_to_remove,
                    inner_rects_rel,
                )
                return
            if config.get("batch_mode"):
                self._submit_batch_question_fields(
                    config,
                    combined_inner,
                    field_indices_to_remove,
                    inner_rects_rel,
                )
                return

            field_type = config.get("field_type", "Tickbox")
            field_name = config.get("field_name", "").strip()
            if not field_name:
                return
            self._last_field_type = field_type
            if field_type == "RadioGrid":
                self._open_radio_grid_from_drawn_rect(field_name, drawn_rect_rel)
                logger.info(
                    "Page %s: Opening Grid Designer for RadioGrid '%s' from drawn rect",
                    self.current_page_idx + 1,
                    field_name,
                )
                return
            if field_type == "RadioGroup" and inner_count > 0:
                inner_names = config.get("inner_names", [])
                while len(inner_names) < inner_count:
                    inner_names.append(f"Option {len(inner_names) + 1}")
                radio_colour = default_colour_tuple_for_type("RadioButton")
                group_colour = default_colour_tuple_for_type("RadioGroup")
                radio_buttons = []
                for i, (rx, ry, rw, rh, _) in enumerate(combined_inner):
                    name = inner_names[i] if i < len(inner_names) else f"Option {i + 1}"
                    rb = RadioButton(name=name, x=rx, y=ry, width=rw, height=rh, colour=radio_colour)
                    radio_buttons.append(rb)
                # Remove converted fields from page_field_list first (reverse order to preserve indices)
                for j in reversed(field_indices_to_remove):
                    page_fields.pop(j)
                rg = RadioGroup(
                    name=field_name,
                    x=left_rel, y=top_rel, width=w, height=h,
                    radio_buttons=radio_buttons,
                    colour=group_colour
                )
                self.page_field_list[self.current_page_idx].append(rg)
                # Remove inner rects from detected_rects (match by position)
                logo = self.fiducials[self.current_page_idx][0] if self.fiducials[self.current_page_idx] else (0, 0)
                det = self.page_detected_rects[self.current_page_idx]
                to_remove = []
                for j, rect in enumerate(det):
                    ra, rb_val, rw_val, rh_val = rect
                    for (irx, iry, iw, ih) in inner_rects_rel:
                        if (ra == irx + logo[0] and rb_val == iry + logo[1] and rw_val == iw and rh_val == ih):
                            to_remove.append(j)
                            break
                for j in reversed(to_remove):
                    det.pop(j)
                self.image_display.detected_rects = self.page_detected_rects[self.current_page_idx]
            else:
                field_class = FIELD_TYPE_MAP.get(field_type, Tickbox)
                kwargs = {
                    "name": field_name,
                    "x": left_rel,
                    "y": top_rel,
                    "width": w,
                    "height": h,
                    "colour": default_colour_tuple_for_type(field_type),
                }
                if field_class == RadioGroup:
                    kwargs["radio_buttons"] = []
                new_field = field_class(**kwargs)
                self.page_field_list[self.current_page_idx].append(new_field)
            self.image_display.field_list = self.page_field_list[self.current_page_idx]
            if self.config:
                self._save_page_fields(self.current_page_idx)
            self.image_display.update_display()
            self.update_thumbnail(self.current_page_idx)
            self._update_edit_panel_json(self.current_page_idx)
            self.undo_button.setEnabled(True)
            logger.info(f"Page {self.current_page_idx + 1}: Added {field_type} '{field_name}' from drawn rect")

        def on_deleted():
            # Discard drawn rect only; do not delete inner rectangles
            self.image_display.update_display()
            logger.info(f"Page {self.current_page_idx + 1}: Discarded drawn rectangle (RadioGroup not added)")

        def on_assistant_requested():
            self._run_question_assistant(dialog, drawn_rect_rel, inner_geom)

        def on_radio_grid_requested(name: str):
            self._open_radio_grid_from_drawn_rect(name, drawn_rect_rel)

        dialog.submitted.connect(on_submit)
        dialog.deleted.connect(on_deleted)
        dialog.assistant_requested.connect(on_assistant_requested)
        dialog.radio_grid_requested.connect(on_radio_grid_requested)
        dialog.exec()

    # ---- Zoom / fit button handlers ----

    def on_fit_width_clicked(self):
        if self.image_display:
            self.image_display.set_fit_width()

    def on_fit_height_clicked(self):
        if self.image_display:
            self.image_display.set_fit_height()

    def on_autofit_clicked(self):
        if self.image_display:
            self.image_display.set_autofit()

    def on_zoom_in_clicked(self):
        if self.image_display:
            self.image_display.zoom_in()

    def on_zoom_out_clicked(self):
        if self.image_display:
            self.image_display.zoom_out()

    def on_field_names_toggled(self):
        if self.image_display:
            self.image_display.show_field_names = self.field_names_toggle.isChecked()
            self.image_display.update_display()
    
    def undo_last_field(self):
        """Remove the last field rectangle drawn on the current page."""
        if self.current_page_idx is not None and 0 <= self.current_page_idx < len(self.page_field_list):
            if self.page_field_list[self.current_page_idx]:
                removed_data = self.page_field_list[self.current_page_idx].pop()
                logger.info(f"Removed last field on page {self.current_page_idx + 1}: {removed_data}")
                
                # Update image display
                if self.image_display.field_list:
                    self.image_display.field_list.pop()
                
                # Save updated fields to JSON
                if self.config:
                    self._save_page_fields(self.current_page_idx)
                
                self.image_display.update_display()
                self.update_thumbnail(self.current_page_idx)
                
                # Clear selected field if it was the one removed
                if (self.selected_field_index is not None and 
                    self.selected_field_index >= len(self.page_field_list[self.current_page_idx])):
                    self.selected_field_obj = None
                    self.selected_field_index = None
                    if self.edit_panel:
                        self.edit_panel.set_field_from_object(None)
                
                # Disable undo button if no more fields
                if not self.page_field_list[self.current_page_idx]:
                    self.undo_button.setEnabled(False)
    
    def delete_current_rectangle(self):
        """Delete the currently selected field rectangle on the current page."""
        if self.current_page_idx is None or self.selected_field_index is None:
            return
        
        if not (0 <= self.current_page_idx < len(self.page_field_list)):
            return
        
        if not (0 <= self.selected_field_index < len(self.page_field_list[self.current_page_idx])):
            return
        
        field_at_index = self.page_field_list[self.current_page_idx][self.selected_field_index]
        # If the selection is a RadioButton inside a RadioGroup, remove only that button from the group
        if (isinstance(field_at_index, RadioGroup) and
                isinstance(self.selected_field_obj, RadioButton) and
                self.selected_field_obj in field_at_index.radio_buttons):
            field_at_index.remove_radio_button(self.selected_field_obj)
            logger.info(f"Removed RadioButton '{self.selected_field_obj.name}' from RadioGroup on page {self.current_page_idx + 1}")
        else:
            # Remove the selected field from data structures
            removed_data = self.page_field_list[self.current_page_idx].pop(self.selected_field_index)
            logger.info(f"Removed field on page {self.current_page_idx + 1}: {removed_data}")
            # Update image display
            if (self.image_display.field_list and
                    self.selected_field_index < len(self.image_display.field_list)):
                self.image_display.field_list.pop(self.selected_field_index)
        
        # Save updated fields to JSON
        if self.config:
            self._save_page_fields(self.current_page_idx)
        
        # Clear selected field since it was deleted
        self.selected_field_obj = None
        self.selected_field_index = None
        if self.edit_panel:
            self.edit_panel.set_field_from_object(None)
            self.edit_panel.set_preview_pixmap(None)
        
        # Update display and thumbnail
        self.image_display.update_display()
        self.update_thumbnail(self.current_page_idx)
        
        # Update JSON editor to reflect the change
        self._update_edit_panel_json(self.current_page_idx)
        
        # Disable undo button if no more fields
        if not self.page_field_list[self.current_page_idx]:
            self.undo_button.setEnabled(False)
    
    def clear_current_page_fields(self):
        """Clear all field rectangles on the current page."""
        if self.current_page_idx is not None and 0 <= self.current_page_idx < len(self.page_field_list):
            self.page_field_list[self.current_page_idx].clear()
            self.image_display.field_list.clear()
            
            # Save updated (empty) fields to JSON
            if self.config:
                self._save_page_fields(self.current_page_idx)
            
            self.image_display.update_display()
            self.update_thumbnail(self.current_page_idx)
            self.undo_button.setEnabled(False)
            
            # Clear selected field since all fields were removed
            self.selected_field_obj = None
            self.selected_field_index = None
            if self.edit_panel:
                self.edit_panel.set_field_from_object(None)
            
            logger.debug(f"Cleared all fields on page {self.current_page_idx + 1}")
    
    def detect_rectangles(self):
        """Open the rectangle detection settings dialog and run detection."""
        self.open_rectangle_detect_dialog()

    def open_rectangle_detect_dialog(self):
        """Show non-modal sensitivity dialog and detect rectangles on the current page."""
        if self.current_page_idx is None or not (0 <= self.current_page_idx < len(self.pages)):
            logger.warning("No page selected for rectangle detection")
            return

        if self._rect_detect_dialog is None:
            dlg = DesignerRectangleDetectDialog(self)
            dlg.settings_changed.connect(self._on_rectangle_detection_settings_changed)
            dlg.save_requested.connect(self._on_rectangle_detection_settings_save)
            self._rect_detect_dialog = dlg

        dlg = self._rect_detect_dialog
        dlg.set_settings(self.rectangle_detection_settings)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        self._run_rectangle_detection(self.rectangle_detection_settings)

    def _close_rectangle_detect_dialog(self) -> None:
        if self._rect_detect_dialog is not None:
            self._rect_detect_dialog.flush_pending()
            self._rect_detect_dialog.close()
            self._rect_detect_dialog.deleteLater()
            self._rect_detect_dialog = None

    def _on_rectangle_detection_settings_changed(
        self, settings: RectangleDetectionSettings
    ) -> None:
        self.rectangle_detection_settings = settings
        self._run_rectangle_detection(settings)

    def _on_rectangle_detection_settings_save(
        self, settings: RectangleDetectionSettings
    ) -> None:
        self.rectangle_detection_settings = settings
        if self.config:
            save_rectangle_detection_settings(
                str(self.config.json_folder), settings
            )

    def _run_rectangle_detection(self, settings: RectangleDetectionSettings) -> None:
        """Detect rectangles on the current page using the given settings."""
        if self.current_page_idx is None or not (0 <= self.current_page_idx < len(self.pages)):
            return

        logger.debug(
            "Detecting rectangles on page %s...", self.current_page_idx + 1
        )
        page = self.pages[self.current_page_idx]

        page_array = np.array(page)
        page_cv = cv2.cvtColor(page_array, cv2.COLOR_RGB2BGR)

        detected_rects = detect_rectangles(page_cv, settings=settings)

        self.page_detected_rects[self.current_page_idx] = detected_rects
        self.image_display.detected_rects = detected_rects

        logger.debug(
            "Detected %d rectangles on page %d",
            len(detected_rects),
            self.current_page_idx + 1,
        )

        self.image_display.update_display()
        self._update_remove_inner_button_state()

        if self._rect_detect_dialog is not None:
            self._rect_detect_dialog.set_detection_status(
                len(detected_rects), self.current_page_idx + 1
            )

    def run_design_analyse(self):
        """Assistant → Analyse: propose fields for the current page via external VLM."""
        if self.current_page_idx is None or not (0 <= self.current_page_idx < len(self.pages)):
            QMessageBox.information(self, "Analyse", "Load a project and select a page first.")
            return
        if self._analyse_worker is not None and self._analyse_worker.isRunning():
            QMessageBox.information(self, "Analyse", "Analysis is already running.")
            return

        page = self.pages[self.current_page_idx]
        bbox = (
            self.fiducials[self.current_page_idx]
            if self.current_page_idx < len(self.fiducials)
            else None
        )
        # Ensure CV candidates exist for the matcher / prompt
        cv_rects = self.page_detected_rects[self.current_page_idx]
        if not cv_rects:
            self._run_rectangle_detection(self.rectangle_detection_settings)
            cv_rects = self.page_detected_rects[self.current_page_idx]

        self.analyse_action.setEnabled(False)
        self.statusBar().showMessage("Analysing page with Design Assistant…", 0)

        worker = DesignAnalyseWorker(
            page.copy(),
            self.current_page_idx,
            bbox,
            list(cv_rects),
            parent=self,
        )
        self._analyse_worker = worker
        worker.finished_ok.connect(self._on_analyse_finished)
        worker.finished_error.connect(self._on_analyse_error)
        worker.finished.connect(self._on_analyse_thread_finished)
        worker.start()

    def _on_analyse_thread_finished(self):
        if hasattr(self, "analyse_action"):
            self.analyse_action.setEnabled(
                self.current_page_idx is not None and bool(self.pages)
            )
        self.statusBar().clearMessage()

    def _on_analyse_error(self, message: str):
        QMessageBox.warning(self, "Analyse failed", message)

    def _on_analyse_finished(self, result):
        if self.current_page_idx is None:
            return
        dialog = DesignerAnalysePreviewDialog(
            self,
            fields=result.fields,
            warnings=result.warnings,
            grid_suggestions=result.grid_suggestions,
            model=result.model,
            page_number=self.current_page_idx + 1,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._apply_analyse_result(result.fields, dialog.apply_mode())

    def _apply_analyse_result(self, new_fields: list, mode: str):
        """Merge or replace page fields from Analyse, then persist."""
        if self.current_page_idx is None:
            return
        page_idx = self.current_page_idx
        if mode == DesignerAnalysePreviewDialog.MODE_REPLACE:
            self.page_field_list[page_idx] = list(new_fields)
        else:
            existing = self.page_field_list[page_idx]
            by_name = {f.name: i for i, f in enumerate(existing) if getattr(f, "name", None)}
            for f in new_fields:
                if f.name in by_name:
                    existing[by_name[f.name]] = f
                else:
                    existing.append(f)
                    by_name[f.name] = len(existing) - 1
            self.page_field_list[page_idx] = existing

        if self.config:
            self._save_page_fields(page_idx)
        self.image_display.field_list = self.page_field_list[page_idx]
        self.image_display.update_display()
        self.update_thumbnail(page_idx)
        self._update_edit_panel_json(page_idx)
        self.undo_button.setEnabled(len(self.page_field_list[page_idx]) > 0)
        logger.info(
            "Page %s: Applied Analyse (%s) — %d field(s)",
            page_idx + 1,
            mode,
            len(new_fields),
        )
        self.statusBar().showMessage(
            f"Applied Analyse ({mode}): {len(new_fields)} field(s)",
            5000,
        )

    def remove_inner_rectangles_clicked(self):
        """Remove detected rectangles that are entirely inside another (inner perimeters)."""
        if self.current_page_idx is None or not (0 <= self.current_page_idx < len(self.pages)):
            return
        rects = self.page_detected_rects[self.current_page_idx]
        if not rects:
            return
        filtered = remove_inner_rectangles(rects)
        removed = len(rects) - len(filtered)
        self.page_detected_rects[self.current_page_idx] = filtered
        self.image_display.detected_rects = filtered
        self.image_display.update_display()
        self._update_remove_inner_button_state()
        logger.info(f"Removed {removed} inner rectangle(s) on page {self.current_page_idx + 1}")

    def _update_remove_inner_button_state(self):
        """Enable Remove inner rectangles when current page has detected rects."""
        if hasattr(self, "remove_inner_button") and self.current_page_idx is not None:
            rects = self.page_detected_rects[self.current_page_idx] if 0 <= self.current_page_idx < len(self.page_detected_rects) else []
            self.remove_inner_button.setEnabled(len(rects) > 0)

    def update_thumbnail(self, page_idx):
        """Update the thumbnail for a specific page to reflect current field rectangles."""
        if 0 <= page_idx < len(self.pages):
            page = self.pages[page_idx]
            bbox = self.fiducials[page_idx] if page_idx < len(self.fiducials) else None
            field_list = self.page_field_list[page_idx] if page_idx < len(self.page_field_list) else []
            self.thumbnail_panel.update_thumbnail(page_idx, page, bbox, field_list)


def main():
    """Main entry point for the application."""
    app = QApplication(sys.argv)
    window = Designer()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

