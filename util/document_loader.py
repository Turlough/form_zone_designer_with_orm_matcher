import logging
from pathlib import Path

from PIL import Image
import pymupdf as fitz  # type: ignore[import-not-found]  # PyMuPDF


logger = logging.getLogger(__name__)


class BaseDocumentLoader:
    """Abstract interface for loading multipage documents into PIL images."""

    def get_page_count(self, file_path: str) -> int:
        return len(self.load_pages(file_path))

    def load_page(self, file_path: str, page_index: int) -> Image.Image:
        pages = self.load_pages(file_path)
        if page_index < 0 or page_index >= len(pages):
            raise IndexError(f"Page index {page_index} out of range for {file_path}")
        return pages[page_index]

    def load_pages(self, file_path: str) -> list[Image.Image]:
        """Return all pages of a document as a list of PIL Images."""
        raise NotImplementedError


class TiffDocumentLoader(BaseDocumentLoader):
    """Load pages from a multipage TIFF (or other Pillow-supported image)."""

    def get_page_count(self, file_path: str) -> int:
        count = 0
        try:
            img = Image.open(file_path)
            while True:
                try:
                    img.seek(count)
                    count += 1
                except EOFError:
                    break
        except Exception as exc:  # noqa: BLE001
            msg = f"Failed to count pages in {file_path}: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc
        return count

    def load_page(self, file_path: str, page_index: int) -> Image.Image:
        try:
            img = Image.open(file_path)
            img.seek(page_index)
            return img.convert("RGB")
        except Exception as exc:  # noqa: BLE001
            msg = f"Failed to load page {page_index} from {file_path}: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

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

    def get_page_count(self, file_path: str) -> int:
        try:
            doc = fitz.open(file_path)
            try:
                return len(doc)
            finally:
                doc.close()
        except Exception as exc:  # noqa: BLE001
            msg = f"Failed to count PDF pages in {file_path}: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

    def load_page(self, file_path: str, page_index: int) -> Image.Image:
        try:
            doc = fitz.open(file_path)
            try:
                if page_index < 0 or page_index >= len(doc):
                    raise IndexError(f"Page index {page_index} out of range for {file_path}")
                zoom = self.dpi / 72.0
                matrix = fitz.Matrix(zoom, zoom)
                page = doc[page_index]
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            finally:
                doc.close()
        except Exception as exc:  # noqa: BLE001
            msg = f"Failed to load PDF page {page_index} from {file_path}: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

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


def load_page_dimensions(file_path: str) -> list[tuple[int, int]]:
    """
    Return (width, height) in pixels for each page of a multipage template or document.

    PDF sizes match PdfDocumentLoader rasterization (default 200 DPI).
    """
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        loader = PdfDocumentLoader()
        zoom = loader.dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        dimensions: list[tuple[int, int]] = []
        try:
            doc = fitz.open(file_path)
            try:
                for page_index in range(len(doc)):
                    page = doc[page_index]
                    pix = page.get_pixmap(matrix=matrix, alpha=False)
                    dimensions.append((pix.width, pix.height))
            finally:
                doc.close()
        except Exception as exc:  # noqa: BLE001
            msg = f"Failed to read PDF page dimensions from {file_path}: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc
        return dimensions

    dimensions = []
    try:
        img = Image.open(file_path)
        page_num = 0
        while True:
            try:
                img.seek(page_num)
                dimensions.append((img.width, img.height))
                page_num += 1
            except EOFError:
                break
    except Exception as exc:  # noqa: BLE001
        msg = f"Failed to read image page dimensions from {file_path}: {exc}"
        logger.error(msg)
        raise RuntimeError(msg) from exc
    return dimensions


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

