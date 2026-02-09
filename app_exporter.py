import os
import sys
import json
import csv
from pathlib import Path

from dotenv import load_dotenv
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QWidget,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)

from util.app_state import load_state
from util.path_utils import (
    resolve_path_case_insensitive,
    resolve_path_or_original,
    find_file_case_insensitive,
)


class ExporterMenuBar(QMenuBar):
    """
    Menu bar for the Exporter application.

    - **Project**: works like `IndexMenuBar._refresh_project_menu`, listing
      subfolders under `DESIGNER_CONFIG_FOLDER` and emitting the selected
      project path.
    - **Batch**: lets the main window open a completed-batch folder picker.
    - **Tools**: contains Summarise, Validate, and Export submenus.
    """

    project_selected = pyqtSignal(str)  # Emits the selected project config folder path
    batch_folder_requested = pyqtSignal()  # User chose the Batch > Open Completed Batches… menu
    summarise_requested = pyqtSignal()  # User chose Tools > Summarise
    validate_requested = pyqtSignal()  # User chose Tools > Validate
    export_requested = pyqtSignal()  # User chose Tools > Export

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._designer_config_folder = os.getenv("DESIGNER_CONFIG_FOLDER", "").strip()
        self._current_project_path: str | None = None

        self._init_project_menu()
        self._init_batch_menu()
        self._init_tools_menu()

    # ---- Project menu ----

    def _init_project_menu(self) -> None:
        """Build Project menu from top-level folders in DESIGNER_CONFIG_FOLDER."""
        self._project_menu = QMenu("Project", self)
        self.addMenu(self._project_menu)
        self._refresh_project_menu()

    def _refresh_project_menu(self) -> None:
        """Refresh the Project submenu with current folder list (same behavior as IndexMenuBar)."""
        self._project_menu.clear()

        base_resolved = (
            resolve_path_case_insensitive(self._designer_config_folder)
            if self._designer_config_folder
            else None
        )
        if not self._designer_config_folder or base_resolved is None:
            no_folder = self._project_menu.addAction("(No DESIGNER_CONFIG_FOLDER set)")
            no_folder.setEnabled(False)
            return

        base = base_resolved
        subdirs = sorted(
            d for d in base.iterdir() if d.is_dir() and not d.name.startswith(".")
        )

        if not subdirs:
            empty = self._project_menu.addAction("(No project folders)")
            empty.setEnabled(False)
            return

        for d in subdirs:
            action = self._project_menu.addAction(d.name)
            action.triggered.connect(
                lambda checked=False, p=str(d): self._on_project_selected(p)
            )

    def _on_project_selected(self, config_folder_path: str) -> None:
        """Handle selection of a project config folder."""
        self._current_project_path = config_folder_path
        self.project_selected.emit(config_folder_path)

    # ---- Batch menu ----

    def _init_batch_menu(self) -> None:
        """Build Batch menu with a single 'Open completed batches…' action."""
        self._batch_menu = QMenu("Batch", self)
        self.addMenu(self._batch_menu)
        self._refresh_batch_menu()

    def _refresh_batch_menu(self) -> None:
        """Refresh the Batch submenu (delegates folder picking to the main window)."""
        self._batch_menu.clear()
        open_action = self._batch_menu.addAction("Open completed batches…")
        open_action.triggered.connect(self._on_batch_menu_triggered)

    def _on_batch_menu_triggered(self) -> None:
        """Notify the main window that the user wants to choose completed batches."""
        self.batch_folder_requested.emit()

    # ---- Tools menu ----

    def _init_tools_menu(self) -> None:
        """Build Tools menu with Summarise, Validate, and Export submenus (as actions for now)."""
        self._tools_menu = QMenu("Tools", self)
        self.addMenu(self._tools_menu)
        self._refresh_tools_menu()

    def _refresh_tools_menu(self) -> None:
        """Refresh Tools menu actions; main window provides the actual behaviour."""
        self._tools_menu.clear()

        summarise_menu = self._tools_menu.addMenu("Summarise")
        summarise_action = summarise_menu.addAction("Run summary")
        summarise_action.triggered.connect(lambda: self.summarise_requested.emit())

        validate_menu = self._tools_menu.addMenu("Validate")
        validate_action = validate_menu.addAction("Run validation")
        validate_action.triggered.connect(lambda: self.validate_requested.emit())

        export_menu = self._tools_menu.addMenu("Export")
        export_action = export_menu.addAction("Run export")
        export_action.triggered.connect(lambda: self.export_requested.emit())


class Exporter(QMainWindow):
    """Main window for the Exporter application."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Exporter")
        self.setGeometry(100, 100, 1000, 800)

        load_dotenv()

        self.config_folder: str | None = None
        self.import_file_path: str | None = None
        # List of (batch_name, import_file_path) tuples discovered under the chosen folder
        self._batches: list[tuple[str, str]] = []
        # Map import_file_path -> (row_count, rows_with_comments, total_comments)
        self._batch_stats: dict[str, tuple[int, int, int]] = {}

        self.batch_table: QTableWidget | None = None

        self._init_menu_bar()
        self._init_central_widget()
        self._try_restore_last_session()

    def _init_menu_bar(self) -> None:
        """Create and wire up the application menu bar."""
        self._menu_bar = ExporterMenuBar(self)
        self._menu_bar.project_selected.connect(self._on_project_selected)
        self._menu_bar.batch_folder_requested.connect(self._on_batch_folder_requested)
        self._menu_bar.summarise_requested.connect(self._on_summarise_requested)
        self._menu_bar.validate_requested.connect(self._on_validate_requested)
        self._menu_bar.export_requested.connect(self._on_export_requested)
        self.setMenuBar(self._menu_bar)

    def _init_central_widget(self) -> None:
        """Create the central table showing batches discovered for export."""
        central = QWidget(self)
        layout = QVBoxLayout(central)

        # Columns: Batch name, Rows, Rows with comments, Total comments
        table = QTableWidget(0, 4, central)
        table.setHorizontalHeaderLabels(
            ["Batch name", "Rows", "Rows with comments", "Total comments"]
        )
        header: QHeaderView = table.horizontalHeader()
        header.setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        layout.addWidget(table)
        self.batch_table = table
        self.setCentralWidget(central)

    def _on_project_selected(self, config_folder_path: str) -> None:
        """Record the selected project folder (hook for future logic)."""
        self.config_folder = config_folder_path

    def _try_restore_last_session(self) -> None:
        """
        On launch, restore the last project used by Designer/Indexer (if valid)
        and treat it as the current project for the Exporter.
        """
        state = load_state()
        folder = (state.get("last_config_folder") or "").strip()
        if not folder:
            return
        if resolve_path_case_insensitive(folder) is None:
            return
        self._on_project_selected(folder)

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
        except Exception:
            return None

    def _on_batch_folder_requested(self) -> None:
        """
        Handle the Batch menu action:

        1. Let the user pick a completed-batch root folder (folder picker),
           defaulting to `batch_folder/_complete` from project_config.json.
        2. Search that folder for all files named `import_filename` from
           project_config.json, treating the parent folder name as the batch name.
        3. Populate the central table with one row per batch.
        """
        if not self.config_folder:
            QMessageBox.warning(self, "Exporter", "Select a project from the Project menu first.")
            return

        config = self._load_project_config()
        if not config:
            QMessageBox.warning(self, "Exporter", "No project_config.json found for the selected project.")
            return

        batch_folder = str(config.get("batch_folder", "")).strip()
        import_filename = str(config.get("import_filename", "")).strip()
        if not batch_folder or not import_filename:
            QMessageBox.warning(
                self,
                "Exporter",
                "project_config.json must define both 'batch_folder' and 'import_filename'.",
            )
            return

        batch_root = Path(batch_folder)
        default_dir = batch_root / "_complete"
        if not default_dir.exists():
            default_dir = batch_root

        start_dir = str(default_dir)

        selected_folder = QFileDialog.getExistingDirectory(
            self,
            "Select completed batch folder",
            start_dir,
            QFileDialog.Option.ShowDirsOnly,
        )
        if not selected_folder:
            return

        self._load_batches_from_folder(selected_folder, import_filename)

    def _load_batches_from_folder(self, root_folder: str, import_filename: str) -> None:
        """Search for import files under the selected folder and populate the batch table."""
        root_path = Path(root_folder)
        if not root_path.exists() or not root_path.is_dir():
            QMessageBox.warning(self, "Exporter", f"Folder does not exist:\n{root_folder}")
            return

        batches: list[tuple[str, str]] = []

        # Look for import_filename in each direct subfolder of the chosen root.
        for subdir in sorted(
            p for p in root_path.iterdir() if p.is_dir() and not p.name.startswith(".")
        ):
            candidate = find_file_case_insensitive(subdir, import_filename)
            if candidate is not None:
                batch_name = subdir.name
                batches.append((batch_name, str(candidate)))

        self._batches = batches
        self._batch_stats.clear()
        self._populate_batch_table()

        if not batches:
            QMessageBox.information(
                self,
                "Exporter",
                f"No batches found in:\n{root_folder}\n\n"
                f"(looked for '{import_filename}' in each immediate subfolder).",
            )

    def _populate_batch_table(self) -> None:
        """Render the current batch list into the table (one column: batch name)."""
        if not self.batch_table:
            return

        table = self.batch_table
        table.setRowCount(len(self._batches))

        for row, (batch_name, path) in enumerate(self._batches):
            # Column 0: batch name
            table.setItem(row, 0, QTableWidgetItem(batch_name))

            # Columns 1–3: summary stats if available
            stats = self._batch_stats.get(path)
            if stats:
                row_count, rows_with_comments, total_comments = stats
                table.setItem(row, 1, QTableWidgetItem(str(row_count)))
                table.setItem(row, 2, QTableWidgetItem(str(rows_with_comments)))
                table.setItem(row, 3, QTableWidgetItem(str(total_comments)))
            else:
                # Empty cells when no summary has been computed yet
                table.setItem(row, 1, QTableWidgetItem(""))
                table.setItem(row, 2, QTableWidgetItem(""))
                table.setItem(row, 3, QTableWidgetItem(""))

    def _on_import_file_selected(self, import_file_path: str) -> None:
        """
        (Legacy hook, currently unused.) Handle a single import file path.

        For now this just stores the path and shows a confirmation dialog; hook
        your export logic in here later.
        """
        self.import_file_path = import_file_path

    # ---- Tools menu handlers (stubs for now) ----

    def _on_summarise_requested(self) -> None:
        """
        Compute and display summary statistics for each import file:

        1. Total number of data rows (excluding header).
        2. Number of rows containing comments (non-empty Comments field).
        3. Total number of comments across all rows (pipe-delimited in Comments).
        """
        if not self._batches:
            QMessageBox.information(self, "Summarise", "No batches loaded to summarise.")
            return

        stats: dict[str, tuple[int, int, int]] = {}

        for _, import_path in self._batches:
            row_count = 0
            rows_with_comments = 0
            total_comments = 0

            try:
                with open(import_path, newline="", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        row_count += 1
                        comments_val = (row.get("Comments") or "").strip()
                        if comments_val:
                            rows_with_comments += 1
                            # Split on '|' and count non-empty segments
                            parts = [p.strip() for p in comments_val.split("|")]
                            total_comments += sum(1 for p in parts if p)
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "Summarise",
                    f"Could not read import file:\n{import_path}\n\n{exc}",
                )
                continue

            stats[import_path] = (row_count, rows_with_comments, total_comments)

        self._batch_stats = stats
        self._populate_batch_table()

    def _on_validate_requested(self) -> None:
        """Placeholder handler for Tools > Validate."""
        QMessageBox.information(self, "Validate", "Validate is not implemented yet.")

    def _on_export_requested(self) -> None:
        """Placeholder handler for Tools > Export."""
        QMessageBox.information(self, "Export", "Export is not implemented yet.")


def main() -> None:
    """Entry point for launching the Exporter application."""
    app = QApplication(sys.argv)
    window = Exporter()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()