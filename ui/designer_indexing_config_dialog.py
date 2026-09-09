"""Dialogs for Designer Indexing Config menu."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from util.designer_persistence import (
    DEFAULT_IMPORT_FILENAME,
    DEFAULT_LOOKUP_PRIME_INDEX,
    DEFAULT_TEST_BATCH_NAME,
    format_pages_without_fiducial,
    parse_pages_without_fiducial,
)


def _browse_row(parent: QWidget, line_edit: QLineEdit, on_browse) -> QWidget:
    row = QWidget(parent)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(line_edit, stretch=1)
    btn = QPushButton("Browse…")
    btn.clicked.connect(on_browse)
    layout.addWidget(btn)
    return row


class DesignerIndexingConfigDialog(QDialog):
    """Edit Basic Indexing Config keys in project_config.json."""

    def __init__(
        self,
        parent=None,
        *,
        initial: dict,
        start_dir: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle("Basic Indexing Config")
        self.setMinimumWidth(520)
        self._start_dir = start_dir or str(Path.home())
        self._values: dict = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._project_name = QLineEdit()
        self._project_name.setText(str(initial.get("project_name", "")))
        self._project_name.setToolTip("project_name — display name for this project (defaults to the folder name).")
        form.addRow("Project name", self._project_name)

        self._batch_folder = QLineEdit()
        self._batch_folder.setText(str(initial.get("batch_folder", "")))
        self._batch_folder.setToolTip(
            "batch_folder — root folder that will contain Indexer batch directories."
        )
        form.addRow(
            "Batch folder",
            _browse_row(self, self._batch_folder, self._browse_batch_folder),
        )

        self._import_filename = QLineEdit()
        self._import_filename.setText(str(initial.get("import_filename", "") or DEFAULT_IMPORT_FILENAME))
        self._import_filename.setToolTip(
            "import_filename — name of each batch’s import/list file (for example EXPORT.TXT)."
        )
        form.addRow("Import filename", self._import_filename)

        self._lookup_list = QLineEdit()
        self._lookup_list.setText(str(initial.get("lookup_list", "")))
        self._lookup_list.setToolTip(
            "lookup_list — optional CSV used by lookup-backed validations. Leave blank if unused."
        )
        form.addRow(
            "Lookup list",
            _browse_row(self, self._lookup_list, self._browse_lookup_list),
        )

        self._lookup_prime_index = QSpinBox()
        self._lookup_prime_index.setRange(0, 999)
        self._lookup_prime_index.setValue(int(initial.get("lookup_prime_index", DEFAULT_LOOKUP_PRIME_INDEX)))
        self._lookup_prime_index.setToolTip(
            "lookup_prime_index — zero-based key column in the lookup CSV (default 0)."
        )
        form.addRow("Lookup prime index", self._lookup_prime_index)

        self._pages_without_fiducial = QLineEdit()
        pages = initial.get("pages_without_fiducial")
        if pages is None:
            pages = [0, 1]
        self._pages_without_fiducial.setText(format_pages_without_fiducial(list(pages)))
        self._pages_without_fiducial.setToolTip(
            "pages_without_fiducial — zero-based page indices with no fiducial search, e.g. [0, 1]."
        )
        form.addRow("Pages without fiducial", self._pages_without_fiducial)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._project_name.setFocus()

    def _dir_for_dialog(self, path_text: str) -> str:
        text = (path_text or "").strip()
        if text:
            candidate = Path(text)
            if candidate.is_file():
                candidate = candidate.parent
            if candidate.is_dir():
                return str(candidate)
        return self._start_dir

    def _browse_batch_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select batch folder",
            self._dir_for_dialog(self._batch_folder.text()),
            QFileDialog.Option.ShowDirsOnly,
        )
        if chosen:
            self._batch_folder.setText(chosen)

    def _browse_lookup_list(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Select lookup list",
            self._dir_for_dialog(self._lookup_list.text() or self._batch_folder.text()),
            "CSV files (*.csv);;All files (*)",
        )
        if chosen:
            self._lookup_list.setText(chosen)

    def _collect(self) -> dict:
        import_filename = self._import_filename.text().strip()
        if not import_filename:
            raise ValueError("Import filename is required (default EXPORT.TXT).")
        if Path(import_filename).name != import_filename:
            raise ValueError("Import filename must be a file name, not a path.")
        return {
            "project_name": self._project_name.text().strip(),
            "batch_folder": self._batch_folder.text().strip(),
            "import_filename": import_filename,
            "lookup_list": self._lookup_list.text().strip(),
            "lookup_prime_index": self._lookup_prime_index.value(),
            "pages_without_fiducial": parse_pages_without_fiducial(
                self._pages_without_fiducial.text()
            ),
        }

    def accept(self) -> None:
        try:
            self._values = self._collect()
        except ValueError as e:
            QMessageBox.warning(self, "Basic Indexing Config", str(e))
            return
        super().accept()

    def values(self) -> dict:
        return dict(self._values)


class DesignerCreateTestBatchDialog(QDialog):
    """Ask for batch name and document count, then create a test batch on OK."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Test Batch")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._batch_name = QLineEdit()
        self._batch_name.setText(DEFAULT_TEST_BATCH_NAME)
        self._batch_name.setToolTip("Folder name created under batch_folder (from Basic Indexing Config).")
        form.addRow("Batch name", self._batch_name)

        self._document_count = QSpinBox()
        self._document_count.setRange(1, 9999)
        self._document_count.setValue(1)
        self._document_count.setToolTip("How many copies of template.pdf to place in the batch folder.")
        form.addRow("Number of documents", self._document_count)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._batch_name.setFocus()
        self._batch_name.selectAll()

    def accept(self) -> None:
        name = self._batch_name.text().strip()
        if not name or Path(name).name != name or name in {".", ".."}:
            QMessageBox.warning(
                self,
                "Create Test Batch",
                "Enter a batch folder name without path separators.",
            )
            return
        super().accept()

    def batch_name(self) -> str:
        return self._batch_name.text().strip()

    def document_count(self) -> int:
        return self._document_count.value()
