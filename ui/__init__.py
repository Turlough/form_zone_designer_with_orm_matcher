"""PyQt6 widgets; public names are loaded lazily so Indexer builds avoid Designer-only modules."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "DesignerThumbnailWidget",
    "DesignerThumbnailPanel",
    "ImageDisplayWidget",
    "DesignerButtonLayout",
    "DesignerEditPanel",
    "RectangleSelectedDialog",
    "DesignerRectangleDetectDialog",
    "DesignerAnalysePreviewDialog",
    "DesignerIndexingConfigDialog",
    "DesignerCreateTestBatchDialog",
    "GridDesigner",
    "PrintCropWindow",
    "MainImageIndexPanel",
    "IndexDetailPanel",
    "IndexTextDialog",
    "IndexCommentDialog",
    "IndexMenuBar",
    "IndexOcrDialog",
    "QcCommentDialog",
    "QcSpecialFieldReviewDialog",
    "QcTextReviewWindow",
    "RowDivider",
]

_LAZY: dict[str, tuple[str, str]] = {
    "DesignerThumbnailWidget": (".designer_thumbnail_widget", "DesignerThumbnailWidget"),
    "DesignerThumbnailPanel": (".designer_thumbnail_panel", "DesignerThumbnailPanel"),
    "ImageDisplayWidget": (".designer_main_image_widget", "ImageDisplayWidget"),
    "DesignerButtonLayout": (".designer_button_layout", "DesignerButtonLayout"),
    "DesignerEditPanel": (".designer_edit_panel", "DesignerEditPanel"),
    "RectangleSelectedDialog": (".designer_rectangle_selected_dialog", "RectangleSelectedDialog"),
    "DesignerRectangleDetectDialog": (".designer_rectangle_detect_dialog", "DesignerRectangleDetectDialog"),
    "DesignerAnalysePreviewDialog": (".designer_analyse_preview_dialog", "DesignerAnalysePreviewDialog"),
    "DesignerIndexingConfigDialog": (".designer_indexing_config_dialog", "DesignerIndexingConfigDialog"),
    "DesignerCreateTestBatchDialog": (".designer_indexing_config_dialog", "DesignerCreateTestBatchDialog"),
    "GridDesigner": (".grid_designer", "GridDesigner"),
    "PrintCropWindow": (".print_crop_window", "PrintCropWindow"),
    "MainImageIndexPanel": (".index_main_image_panel", "MainImageIndexPanel"),
    "IndexDetailPanel": (".index_details_panel", "IndexDetailPanel"),
    "IndexTextDialog": (".index_text_dialog", "IndexTextDialog"),
    "IndexCommentDialog": (".index_comment_dialog", "IndexCommentDialog"),
    "IndexMenuBar": (".index_menu_bar", "IndexMenuBar"),
    "IndexOcrDialog": (".index_ocr_dialog", "IndexOcrDialog"),
    "QcCommentDialog": (".qc_comment_dialog", "QcCommentDialog"),
    "QcSpecialFieldReviewDialog": (".qc_comment_dialog", "QcSpecialFieldReviewDialog"),
    "QcTextReviewWindow": (".qc_text_review_window", "QcTextReviewWindow"),
    "RowDivider": (".table_row_divider", "RowDivider"),
}


def __getattr__(name: str) -> Any:
    spec = _LAZY.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_path, attr = spec
    module = import_module(module_path, __name__)
    return getattr(module, attr)
