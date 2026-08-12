"""Preview dialog for Export Format Check results before applying."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QDialogButtonBox,
)

from runtime_assistants.design_assistant.export_assistant_for_designer.check import (
    ExportCheckResult,
)


class DesignerExportCheckPreviewDialog(QDialog):
    """Show export format check warnings and proposed metadata fixes."""

    def __init__(
        self,
        parent=None,
        *,
        result: ExportCheckResult,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Check export format — page {result.page_number}")
        self.setMinimumWidth(520)
        self._result = result

        layout = QVBoxLayout(self)

        header = QLabel(
            f"Matched: {result.matched_count}\n"
            f"Proposed updates: {len(result.proposals)}\n"
            f"Warnings: {len(result.warnings)}"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        layout.addWidget(QLabel("Proposed updates:"))
        prop_list = QListWidget()
        if result.proposals:
            for p in result.proposals:
                target = f"field[{p.field_index}]"
                if p.radio_index is not None:
                    target += f".radio[{p.radio_index}]"
                line = f"{target}: {p.reason}"
                if p.column_title:
                    line += f" → column_title={p.column_title!r}"
                if p.export_column_id:
                    line += f" (export_column_id={p.export_column_id})"
                prop_list.addItem(line)
        else:
            prop_list.addItem("(none)")
        prop_list.setMinimumHeight(160)
        layout.addWidget(prop_list)

        layout.addWidget(QLabel("Warnings:"))
        warn_list = QListWidget()
        if result.warnings:
            for w in result.warnings:
                warn_list.addItem(str(w))
        else:
            warn_list.addItem("(none)")
        warn_list.setMinimumHeight(120)
        layout.addWidget(warn_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def result(self) -> ExportCheckResult:
        return self._result
