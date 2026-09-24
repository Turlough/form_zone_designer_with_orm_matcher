"""Reorder pages in multipage PDF or TIFF documents on disk."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import pymupdf as fitz  # type: ignore[import-not-found]
from PIL import Image

from util.document_loader import get_document_loader_for_path

logger = logging.getLogger(__name__)


def move_page_after(document_path: str, left_index: int, right_index: int) -> bool:
    """
    Move the page at ``right_index`` to sit immediately after ``left_index`` (0-based).

    Requires ``right_index > left_index``. Returns False when the page is already
    in that position (``right_index == left_index + 1``). Raises on invalid indices
    or I/O failure.
    """
    if right_index <= left_index:
        raise ValueError("right_index must be greater than left_index")
    loader = get_document_loader_for_path(document_path)
    page_count = loader.get_page_count(document_path)
    if left_index < 0 or right_index >= page_count:
        raise IndexError("page index out of range")
    if right_index == left_index + 1:
        return False

    suffix = Path(document_path).suffix.lower()
    if suffix == ".pdf":
        _move_pdf_page(document_path, right_index, left_index + 1)
    else:
        _move_image_page(document_path, right_index, left_index + 1)
    logger.info(
        "Moved page %d after page %d in %s",
        right_index + 1,
        left_index + 1,
        document_path,
    )
    return True


def _atomic_replace(src: str, dest: str) -> None:
    os.replace(src, dest)


def _move_pdf_page(document_path: str, from_index: int, to_index: int) -> None:
    directory = os.path.dirname(os.path.abspath(document_path))
    fd, temp_path = tempfile.mkstemp(suffix=".pdf", dir=directory or None)
    os.close(fd)
    try:
        doc = fitz.open(document_path)
        try:
            doc.move_page(from_index, to_index)
            doc.save(temp_path, deflate=True)
        finally:
            doc.close()
        _atomic_replace(temp_path, document_path)
    except Exception:
        if os.path.isfile(temp_path):
            os.remove(temp_path)
        raise


def _move_image_page(document_path: str, from_index: int, to_index: int) -> None:
    loader = get_document_loader_for_path(document_path)
    pages = loader.load_pages(document_path)
    page = pages.pop(from_index)
    pages.insert(to_index, page)
    directory = os.path.dirname(os.path.abspath(document_path))
    suffix = Path(document_path).suffix.lower() or ".tif"
    fd, temp_path = tempfile.mkstemp(suffix=suffix, dir=directory or None)
    os.close(fd)
    try:
        first, *rest = pages
        save_kwargs: dict = {}
        if suffix in (".tif", ".tiff"):
            save_kwargs["compression"] = "tiff_deflate"
        first.save(temp_path, save_all=True, append_images=rest, **save_kwargs)
        _atomic_replace(temp_path, document_path)
    except Exception:
        if os.path.isfile(temp_path):
            os.remove(temp_path)
        raise
