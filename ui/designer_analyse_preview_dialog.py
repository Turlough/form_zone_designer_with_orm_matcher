"""Preview dialog for Design Assistant Analyse results before applying."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QRadioButton,
    QButtonGroup,
    QDialogButtonBox,
)

from util.field_metadata import display_label


class DesignerAnalysePreviewDialog(QDialog):
    """Show proposed fields, warnings, and apply mode (replace / merge)."""

    MODE_REPLACE = "replace"
    MODE_MERGE = "merge"

    def __init__(
        self,
        parent=None,
        *,
        fields: list,
        warnings: list[str],
        grid_suggestions: list[dict],
        model: str = "",
        page_number: int = 1,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Analyse preview — page {page_number}")
        self.setMinimumWidth(480)
        self._fields = fields
        self._grid_suggestions = grid_suggestions or []

        layout = QVBoxLayout(self)

        header = QLabel(
            f"Model: {model or '(default)'}\n"
            f"Proposed fields: {len(fields)}"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        layout.addWidget(QLabel("Proposed fields:"))
        field_list = QListWidget()
        for f in fields:
            type_name = type(f).__name__
            label = display_label(f) or getattr(f, "name", "")
            geom = f"({f.x}, {f.y}, {f.width}×{f.height})"
            field_list.addItem(f"{type_name}: {label}  {geom}")
        field_list.setMinimumHeight(160)
        layout.addWidget(field_list)

        layout.addWidget(QLabel("Warnings:"))
        warn_list = QListWidget()
        if warnings:
            for w in warnings:
                warn_list.addItem(str(w))
        else:
            warn_list.addItem("(none)")
        warn_list.setMinimumHeight(100)
        layout.addWidget(warn_list)

        if self._grid_suggestions:
            grid_label = QLabel(
                f"Grid suggestions: {len(self._grid_suggestions)} "
                "(open Grid Designer after apply if needed)"
            )
            grid_label.setWordWrap(True)
            layout.addWidget(grid_label)

        layout.addWidget(QLabel("On apply:"))
        self._mode_group = QButtonGroup(self)
        self._merge_radio = QRadioButton("Merge with existing fields (by name)")
        self._replace_radio = QRadioButton("Replace all fields on this page")
        self._merge_radio.setChecked(True)
        self._mode_group.addButton(self._merge_radio)
        self._mode_group.addButton(self._replace_radio)
        layout.addWidget(self._merge_radio)
        layout.addWidget(self._replace_radio)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply_mode(self) -> str:
        if self._replace_radio.isChecked():
            return self.MODE_REPLACE
        return self.MODE_MERGE

    def grid_suggestions(self) -> list[dict]:
        return list(self._grid_suggestions)
