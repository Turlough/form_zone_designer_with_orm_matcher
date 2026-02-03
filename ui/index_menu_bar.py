"""Menu bar for the Field Indexer application."""

import os
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QMenuBar, QMenu


class IndexMenuBar(QMenuBar):
    """Menu bar with Project and Batch menus. Project lists config folders from DESIGNER_CONFIG_FOLDER."""

    project_selected = pyqtSignal(str)  # Emits the selected project config folder path

    def __init__(self, parent=None):
        super().__init__(parent)
        self._designer_config_folder = os.getenv("DESIGNER_CONFIG_FOLDER", "").strip()
        self._current_project_path: str | None = None
        self._init_project_menu()
        self._init_batch_menu()

    def _init_project_menu(self) -> None:
        """Build Project menu from top-level folders in DESIGNER_CONFIG_FOLDER."""
        self._project_menu = QMenu("Project", self)
        self.addMenu(self._project_menu)
        self._refresh_project_menu()

    def _refresh_project_menu(self) -> None:
        """Refresh the Project submenu with current folder list."""
        self._project_menu.clear()

        if not self._designer_config_folder or not Path(self._designer_config_folder).exists():
            no_folder = self._project_menu.addAction("(No DESIGNER_CONFIG_FOLDER set)")
            no_folder.setEnabled(False)
            return

        base = Path(self._designer_config_folder)
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
        """Build Batch menu (placeholder for later)."""
        self._batch_menu = QMenu("Batch", self)
        self.addMenu(self._batch_menu)
        # Placeholder for future Batch functionality
        placeholder = self._batch_menu.addAction("(Coming soon)")
        placeholder.setEnabled(False)

    def get_current_project_path(self) -> str | None:
        """Return the currently selected project config folder, or None."""
        return self._current_project_path

    def set_current_project_path(self, path: str | None) -> None:
        """Set the current project path (e.g. when restoring from session)."""
        self._current_project_path = path
