#!/usr/bin/env python3
"""
Headless smoke checks for Indexer lazy page loading and window startup.

Usage (from repo root, with .venv active):
  QT_QPA_PLATFORM=offscreen python scripts/smoke_indexer.py
  python scripts/smoke_indexer.py --quick   # lazy pages only, no Indexer window

Sets INDEXER_SKIP_SESSION_RESTORE=1 so smoke does not reload a real batch or write CSV.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

# Repo root on sys.path when invoked as scripts/smoke_indexer.py
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _check_lazy_document_pages() -> None:
    from PIL import Image

    from util.document_loader import TiffDocumentLoader
    from util.lazy_document_pages import LazyDocumentPages

    tmpdir = Path(tempfile.mkdtemp(prefix="indexer_smoke_"))
    tiff_path = tmpdir / "two_page.tif"
    base = Image.new("RGB", (20, 10), color=(255, 0, 0))
    page2 = Image.new("RGB", (20, 10), color=(0, 0, 255))
    base.save(tiff_path, save_all=True, append_images=[page2])

    loader = TiffDocumentLoader()
    if loader.get_page_count(str(tiff_path)) != 2:
        raise RuntimeError("expected 2 pages in smoke TIFF")

    lazy = LazyDocumentPages(str(tiff_path))
    if len(lazy) != 2:
        raise RuntimeError("LazyDocumentPages page_count mismatch")
    if lazy.is_loaded(1):
        raise RuntimeError("page 1 should not be loaded yet")
    if lazy.get_page(0).size != (20, 10):
        raise RuntimeError("page 0 size mismatch")
    if loader.load_page(str(tiff_path), 1).getpixel((0, 0)) != (0, 0, 255):
        raise RuntimeError("page 1 pixel mismatch")

    print("lazy_document_pages: ok")


def _check_indexer_window() -> None:
    os.environ["INDEXER_SKIP_SESSION_RESTORE"] = "1"

    from PyQt6.QtWidgets import QApplication

    from app_indexer import Indexer

    app = QApplication.instance() or QApplication(sys.argv)
    window = Indexer()
    try:
        if not window._page_navigation_shortcuts_allowed():
            raise RuntimeError("expected page nav shortcuts when no text focus")
        if window._csv_save_queue is None:
            raise RuntimeError("CSV save queue not initialized")
        if not hasattr(window, "_prefetch_page_ahead"):
            raise RuntimeError("missing _prefetch_page_ahead")
    finally:
        window._stop_logo_detection()
        window._stop_page_prefetch()
        window._flush_csv_saves()
        window.close()
        window.deleteLater()
        app.processEvents()

    print("app_indexer Indexer(): ok")


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless Indexer smoke checks")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Only test lazy document pages (no PyQt Indexer window)",
    )
    args = parser.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    _check_lazy_document_pages()
    if not args.quick:
        _check_indexer_window()

    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
