"""Tests for util.document_reorder."""

from __future__ import annotations

import pymupdf as fitz  # type: ignore[import-not-found]
from PIL import Image

from util.document_loader import get_document_loader_for_path
from util.document_reorder import move_page_after


def test_move_page_after_pdf(tmp_path) -> None:
    pdf_path = tmp_path / "doc.pdf"
    doc = fitz.open()
    for i in range(5):
        page = doc.new_page(width=100, height=100 + i * 10)
        page.insert_text((10, 20), f"P{i}")
    doc.save(str(pdf_path))
    doc.close()

    move_page_after(str(pdf_path), left_index=1, right_index=3)
    reordered = fitz.open(str(pdf_path))
    try:
        labels = [reordered[i].get_text().strip() for i in range(len(reordered))]
    finally:
        reordered.close()
    assert labels == ["P0", "P1", "P3", "P2", "P4"]


def test_move_page_after_tiff(tmp_path) -> None:
    tiff_path = tmp_path / "doc.tif"
    pages = [
        Image.new("RGB", (40, 50 + i * 10), (i * 40, 0, 0))
        for i in range(4)
    ]
    pages[0].save(tiff_path, save_all=True, append_images=pages[1:])

    move_page_after(str(tiff_path), left_index=0, right_index=2)
    loader = get_document_loader_for_path(str(tiff_path))
    sizes = [img.size for img in loader.load_pages(str(tiff_path))]
    assert sizes == [(40, 50), (40, 70), (40, 60), (40, 80)]


def test_move_page_after_noop_when_already_next(tmp_path) -> None:
    pdf_path = tmp_path / "doc.pdf"
    doc = fitz.open()
    for i in range(3):
        doc.new_page()
    doc.save(str(pdf_path))
    doc.close()

    assert move_page_after(str(pdf_path), left_index=0, right_index=1) is False
    assert fitz.open(str(pdf_path)).page_count == 3
