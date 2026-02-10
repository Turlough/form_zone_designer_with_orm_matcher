import logging
from pathlib import Path

from PIL import Image
import fitz  # type: ignore[import-not-found]  # PyMuPDF


logger = logging.getLogger(__name__)


class BaseDocumentLoader:
    """Abstract interface for loading multipage documents into PIL images."""

    def load_pages(self, file_path: str) -> list[Image.Image]:
        """Return all pages of a document as a list of PIL Images."""
        raise NotImplementedError


class TiffDocumentLoader(BaseDocumentLoader):
    """Load pages from a multipage TIFF (or other Pillow-supported image)."""

    def load_pages(self, file_path: str) -> list[Image.Image]:
        pages: list[Image.Image] = []
        try:
            img = Image.open(file_path)
            page_num = 0
            while True:
                try:
                    img.seek(page_num)
                    page_img = img.convert("RGB")
                    pages.append(page_img)
                    page_num += 1
                except EOFError:
                    break
        except Exception as exc:  # noqa: BLE001
            msg = f"Failed to load TIFF document {file_path}: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

        logger.info("Loaded %d pages from %s", len(pages), file_path)
        return pages


class PdfDocumentLoader(BaseDocumentLoader):
    """Load pages from a PDF using PyMuPDF."""

    def __init__(self, dpi: int = 200) -> None:
        # 200 DPI is a reasonable default for legible OCR/inspection
        self.dpi = dpi

    def load_pages(self, file_path: str) -> list[Image.Image]:
        pages: list[Image.Image] = []
        try:
            doc = fitz.open(file_path)
            try:
                zoom = self.dpi / 72.0
                matrix = fitz.Matrix(zoom, zoom)
                for page_index in range(len(doc)):
                    page = doc[page_index]
                    pix = page.get_pixmap(matrix=matrix, alpha=False)
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    pages.append(img)
            finally:
                doc.close()
        except Exception as exc:  # noqa: BLE001
            msg = f"Failed to load PDF document {file_path}: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

        logger.info("Loaded %d pages from %s", len(pages), file_path)
        return pages


def get_document_loader_for_path(file_path: str) -> BaseDocumentLoader:
    """
    Return an appropriate document loader based on file extension.

    Currently:
    - .pdf -> PdfDocumentLoader
    - everything else -> TiffDocumentLoader (Pillow-backed multipage images)
    """
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        return PdfDocumentLoader()
    # Default: treat as a Pillow-handled multipage image (e.g., TIFF)
    return TiffDocumentLoader()

