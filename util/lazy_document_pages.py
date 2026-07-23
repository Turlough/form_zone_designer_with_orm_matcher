"""Lazy multipage document access: load pages on demand with optional preload."""

from __future__ import annotations

import logging
from PIL import Image

from util.document_loader import get_document_loader_for_path

logger = logging.getLogger(__name__)


class LazyDocumentPages:
    """On-demand page loader with an in-memory page cache."""

    def __init__(self, document_path: str):
        self.document_path = document_path
        self._loader = get_document_loader_for_path(document_path)
        self._pages: dict[int, Image.Image] = {}
        self._page_count: int | None = None

    @classmethod
    def from_preloaded(cls, document_path: str, images: list[Image.Image]) -> LazyDocumentPages:
        """Wrap an already-loaded document (cache, QC preload, etc.)."""
        store = cls(document_path)
        store._page_count = len(images)
        for index, image in enumerate(images):
            store._pages[index] = image
        return store

    def __len__(self) -> int:
        return self.page_count()

    def __bool__(self) -> bool:
        return self.page_count() > 0

    def page_count(self) -> int:
        if self._page_count is None:
            self._page_count = self._loader.get_page_count(self.document_path)
        return self._page_count

    def has_page(self, page_index: int) -> bool:
        return 0 <= page_index < self.page_count()

    def is_loaded(self, page_index: int) -> bool:
        return page_index in self._pages

    def get_page(self, page_index: int) -> Image.Image:
        if page_index in self._pages:
            return self._pages[page_index]
        image = self._loader.load_page(self.document_path, page_index)
        self._pages[page_index] = image
        return image

    def store_page(self, page_index: int, image: Image.Image) -> None:
        """Store a page loaded by a background prefetch worker."""
        self._pages[page_index] = image
