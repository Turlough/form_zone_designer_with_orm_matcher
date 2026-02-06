"""Menu bar for the Field Indexer application."""

import os
import json
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from util.path_utils import resolve_path_case_insensitive, find_file_case_insensitive
from PyQt6.QtWidgets import QMenuBar, QMenu, QMessageBox


class IndexMenuBar(QMenuBar):
    """Menu bar with Project and Batch menus. Project lists config folders from DESIGNER_CONFIG_FOLDER."""

    project_selected = pyqtSignal(str)  # Emits the selected project config folder path
    batch_import_selected = pyqtSignal(str)  # Emits full path to selected batch import file
    ocr_requested = pyqtSignal()  # User chose to OCR the current text field

    def __init__(self, parent=None):
        super().__init__(parent)
        self._designer_config_folder = os.getenv("DESIGNER_CONFIG_FOLDER", "").strip()
        self._current_project_path: str | None = None
        self._init_project_menu()
        self._init_batch_menu()
        self._init_cloud_vision_menu()

    def _init_project_menu(self) -> None:
        """Build Project menu from top-level folders in DESIGNER_CONFIG_FOLDER."""
        self._project_menu = QMenu("Project", self)
        self.addMenu(self._project_menu)
        self._refresh_project_menu()

    def _refresh_project_menu(self) -> None:
        """Refresh the Project submenu with current folder list."""
        self._project_menu.clear()

        base_resolved = resolve_path_case_insensitive(self._designer_config_folder) if self._designer_config_folder else None
        if not self._designer_config_folder or base_resolved is None:
            no_folder = self._project_menu.addAction("(No DESIGNER_CONFIG_FOLDER set)")
            no_folder.setEnabled(False)
            return

        base = base_resolved
        subdirs = sorted(
            d for d in base.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

        if not subdirs:
            empty = self._project_menu.addAction("(No project folders)")
            empty.setEnabled(False)
            return

        for d in subdirs:
            action = self._project_menu.addAction(d.name)
            action.triggered.connect(lambda checked=False, p=str(d): self._on_project_selected(p))

    def _on_project_selected(self, config_folder_path: str) -> None:
        """Handle selection of a project config folder."""
        self._current_project_path = config_folder_path
        self.project_selected.emit(config_folder_path)

    def _init_batch_menu(self) -> None:
        """Build Batch menu from project_config.json (per project)."""
        self._batch_menu = QMenu("Batch", self)
        self.addMenu(self._batch_menu)
        # Populate lazily each time the menu is opened
        self._batch_menu.aboutToShow.connect(self._refresh_batch_menu)

    def _refresh_batch_menu(self) -> None:
        """Refresh the Batch submenu based on current project_config.json."""
        self._batch_menu.clear()

        if not self._current_project_path:
            action = self._batch_menu.addAction("(Select a project first)")
            action.setEnabled(False)
            return

        project_resolved = resolve_path_case_insensitive(self._current_project_path)
        if project_resolved is None:
            action = self._batch_menu.addAction("(Project path not found)")
            action.setEnabled(False)
            return
        config_path = find_file_case_insensitive(project_resolved / "json", "project_config.json")
        if config_path is None:
            action = self._batch_menu.addAction("(No project_config.json found)")
            action.setEnabled(False)
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            action = self._batch_menu.addAction("(Error reading project_config.json)")
            action.setEnabled(False)
            return

        batch_folder = str(config.get("batch_folder", "")).strip()
        import_filename = str(config.get("import_filename", "")).strip()

        if not batch_folder or not import_filename:
            action = self._batch_menu.addAction("(batch_folder/import_filename not set)")
            action.setEnabled(False)
            return

        base = resolve_path_case_insensitive(batch_folder)
        if base is None or not base.is_dir():
            action = self._batch_menu.addAction("(batch_folder does not exist)")
            action.setEnabled(False)
            return

        # Collect direct subfolders that contain the import file.
        # Skip special folders used for coordination between indexers.
        candidates = []
        for d in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")):
            if d.name in {"_in_progress", "_complete", "_qc"}:
                continue
            candidate_file = find_file_case_insensitive(d, import_filename)
            if candidate_file is not None:
                candidates.append((d.name, candidate_file))

        if not candidates:
            action = self._batch_menu.addAction("(No batch folders found)")
            action.setEnabled(False)
            return

        for folder_name, file_path in candidates:
            action = self._batch_menu.addAction(folder_name)
            action.triggered.connect(
                lambda checked=False, p=str(file_path): self._on_batch_selected(p)
            )

    def _on_batch_selected(self, import_file_path: str) -> None:
        """
        Claim the selected batch by moving its folder into _in_progress, then
        emit the updated import file path to the main window.
        """
        if not import_file_path:
            return

        path = Path(import_file_path)
        batch_dir = path.parent

        if not batch_dir.exists():
            # The batch was likely moved or deleted by another user.
            QMessageBox.information(
                self.parent() or self,
                "Batch unavailable",
                "The selected batch is no longer available.",
            )
            return

        batch_root = batch_dir.parent

        # If the batch is already under _in_progress (e.g. resumed path), just emit it.
        if batch_root.name == "_in_progress":
            self.batch_import_selected.emit(str(path))
            return

        in_progress_root = batch_root / "_in_progress"
        try:
            in_progress_root.mkdir(exist_ok=True)
        except Exception:
            # If we can't ensure the coordination folder exists, treat as unavailable.
            QMessageBox.information(
                self.parent() or self,
                "Batch unavailable",
                "The selected batch could not be reserved.",
            )
            return

        dest_dir = in_progress_root / batch_dir.name

        # If another user has already moved this batch into _in_progress, refuse selection.
        if dest_dir.exists():
            QMessageBox.information(
                self.parent() or self,
                "Batch in use",
                "This batch is already being indexed by another user.",
            )
            return

        try:
            batch_dir.rename(dest_dir)
        except Exception:
            # Most likely a race where another user moved or completed the batch.
            QMessageBox.information(
                self.parent() or self,
                "Batch unavailable",
                "The selected batch is no longer available.",
            )
            return

        new_import_file_path = dest_dir / path.name
        self.batch_import_selected.emit(str(new_import_file_path))

    def get_current_project_path(self) -> str | None:
        """Return the currently selected project config folder, or None."""
        return self._current_project_path

    def set_current_project_path(self, path: str | None) -> None:
        """Set the current project path (e.g. when restoring from session)."""
        self._current_project_path = path

    def _init_cloud_vision_menu(self) -> None:
        """Build Cloud Vision menu."""
        self._cloud_vision_menu = QMenu("OCR", self)
        self.addMenu(self._cloud_vision_menu)
        self._refresh_cloud_vision_menu()

    def _refresh_cloud_vision_menu(self) -> None:
        """Refresh the Cloud Vision submenu."""
        self._cloud_vision_menu.clear()
        # Single OCR action; enabled/disabled by main window depending on field type
        self._ocr_action = self._cloud_vision_menu.addAction("OCR current text field")
        self._ocr_action.setEnabled(False)
        self._ocr_action.triggered.connect(self._on_ocr_triggered)

    def _on_ocr_triggered(self) -> None:
        """Emit signal when OCR menu item is chosen."""
        self.ocr_requested.emit()

    def set_ocr_enabled(self, enabled: bool) -> None:
        """Enable or disable the OCR menu item."""
        if hasattr(self, "_ocr_action") and self._ocr_action is not None:
            self._ocr_action.setEnabled(enabled)
