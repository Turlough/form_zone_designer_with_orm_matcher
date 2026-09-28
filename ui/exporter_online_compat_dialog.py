"""Dialog for Tools → Make compatible with online version (Exporter)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class ExporterOnlineCompatDialog(QDialog):
    """Pick export_config, Qualtrics Excel template, and delivery CSV."""

    def __init__(
        self,
        parent=None,
        *,
        initial_config: Path | None = None,
        initial_config_dir: Path | None = None,
        initial_template: Path | None = None,
        initial_csv_dir: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Make compatible with online version")
        self.setMinimumWidth(560)

        self._config_browse_dir = initial_config_dir or Path.home()
        self._template_browse_dir = self._config_browse_dir
        self._csv_browse_dir = initial_csv_dir or Path.home()

        self._config_edit = QLineEdit(self)
        self._template_edit = QLineEdit(self)
        self._csv_edit = QLineEdit(self)
        if initial_config:
            self._config_edit.setText(str(initial_config))
            if initial_config.parent.is_dir():
                self._config_browse_dir = initial_config.parent
                self._template_browse_dir = initial_config.parent
        if initial_template:
            self._template_edit.setText(str(initial_template))
            if initial_template.parent.is_dir():
                self._template_browse_dir = initial_template.parent

        form = QFormLayout()
        form.addRow("Export config", self._config_row())
        form.addRow("Excel template", self._template_row())
        form.addRow("Delivery CSV", self._csv_row())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _config_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(self._config_edit, stretch=1)
        browse = QPushButton("Browse…", self)
        browse.clicked.connect(self._browse_config)
        row.addWidget(browse)
        return row

    def _template_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(self._template_edit, stretch=1)
        browse = QPushButton("Browse…", self)
        browse.clicked.connect(self._browse_template)
        row.addWidget(browse)
        return row

    def _csv_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(self._csv_edit, stretch=1)
        browse = QPushButton("Browse…", self)
        browse.clicked.connect(self._browse_csv)
        row.addWidget(browse)
        return row

    def _browse_start_dir(self, edit: QLineEdit, fallback: Path) -> str:
        text = edit.text().strip()
        if text:
            p = Path(text)
            if p.is_file():
                return str(p.parent)
            if p.is_dir():
                return str(p)
            parent = p.parent
            if parent.is_dir():
                return str(parent)
        return str(fallback)

    def _browse_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select export config",
            self._browse_start_dir(self._config_edit, self._config_browse_dir),
            "JSON (*.json);;All files (*.*)",
        )
        if path:
            self._config_edit.setText(path)
            parent = Path(path).parent
            if parent.is_dir():
                self._config_browse_dir = parent
                self._template_browse_dir = parent

    def _browse_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Qualtrics Excel template",
            self._browse_start_dir(self._template_edit, self._template_browse_dir),
            "Excel (*.xlsx);;All files (*.*)",
        )
        if path:
            self._template_edit.setText(path)

    def _browse_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select delivery CSV",
            self._browse_start_dir(self._csv_edit, self._csv_browse_dir),
            "CSV (*.csv);;All files (*.*)",
        )
        if path:
            self._csv_edit.setText(path)

    def config_path(self) -> Path | None:
        text = self._config_edit.text().strip()
        return Path(text) if text else None

    def template_path(self) -> Path | None:
        text = self._template_edit.text().strip()
        return Path(text) if text else None

    def csv_path(self) -> Path | None:
        text = self._csv_edit.text().strip()
        return Path(text) if text else None
