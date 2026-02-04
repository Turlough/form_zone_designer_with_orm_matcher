"""Google Cloud Vision client utilities for the Field Indexer.

This module provides a small wrapper around the Google Cloud Vision
`document_text_detection` API, taking a PIL image and a rectangle
in page pixel coordinates and returning normalized text suitable
for use in `IndexDetailPanel.value_text_edit`.

The behavior matches the specification in `util/cloud_vision.md`:
  - Use DOCUMENT_TEXT_DETECTION
  - Language hint: English, region Ireland (en-IE)
  - Work on the original scanned resolution (no rescaling)
  - Remove layout/formatting; collapse whitespace
  - Replace newlines with full stops
  - Text is assembled in reading order (top-to-bottom, left-to-right) so
    handwritten or form text is read as a single paragraph, not by columns.
"""

from __future__ import annotations

from typing import Tuple, Any
import io
import re
import logging

logger = logging.getLogger(__name__)    

from PIL import Image

try:
    # Imported lazily by callers, but we type-check here.
    from google.cloud import vision  # type: ignore
except Exception:  # pragma: no cover - allow import to fail at runtime if package missing
    vision = None  # type: ignore


Rect = Tuple[int, int, int, int]


def _get_text_in_reading_order(annotation: Any) -> str:
    """Build text from full_text_annotation in top-to-bottom, left-to-right order.

    Ignores the API's default block/paragraph order so handwritten or form
    text is read as a single paragraph (line by line, left to right).
    """
    if not annotation or not getattr(annotation, "pages", None):
        return ""
    words_with_pos: list[tuple[float, float, str]] = []
    for page in annotation.pages:
        logger.info(f"Page: {page}")
        for block in getattr(page, "blocks", []) or []:
            logger.info(f"Block: {block}")
            for paragraph in getattr(block, "paragraphs", []) or []:
                logger.info(f"Paragraph: {paragraph}")
                for word in getattr(paragraph, "words", []) or []:
                    logger.info(f"Word: {word}")
                    word_text = "".join(
                        getattr(s, "text", "") for s in getattr(word, "symbols", []) or []
                    )
                    logger.info(f"Word text: {word_text}")
                    verts = getattr(getattr(word, "bounding_poly", None), "vertices", None) or []
                    if not verts:
                        words_with_pos.append((0.0, 0.0, word_text))
                        continue
                    v0 = verts[0]
                    y = getattr(v0, "y", 0) or 0
                    x = getattr(v0, "x", 0) or 0
                    words_with_pos.append((y, x, word_text))
    if not words_with_pos:
        return ""
    words_with_pos.sort(key=lambda t: (t[1], t[0]))
    return " ".join(t[2] for t in words_with_pos)


def _normalize_ocr_text(raw_text: str) -> str:
    """Normalize OCR text according to project rules.

    Rules (see cloud_vision.md):
      - Newline characters are treated as sentence boundaries.
      - All consecutive whitespace characters are collapsed.
      - Leading and trailing whitespace is trimmed.
      - Consecutive newlines/spaces are collapsed into a single separator.
    """
    if not raw_text:
        return ""

    # Normalize line endings first
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    # Treat any run of one or more newlines as a sentence break -> ". "
    text = re.sub(r"\n+", " ", text)

    # Collapse remaining whitespace (spaces, tabs, etc.) to a single space
    text = re.sub(r"\s+", " ", text)

    # Trim leading / trailing spaces and stray periods
    text = text.strip()

    return text


def ocr_image_region(pil_image: Image.Image, rect: Rect) -> str:
    """Run Google Cloud Vision OCR on a rectangular region of a page.

    Args:
        pil_image: Full page image at original scan resolution.
        rect: (x, y, width, height) in page pixel coordinates.

    Returns:
        Normalized OCR text (may be empty string).

    Raises:
        RuntimeError: If Google Cloud Vision is not available or returns an error.
    """
    if vision is None:
        raise RuntimeError(
            "google-cloud-vision is not installed or could not be imported. "
            "Install it with 'pip install google-cloud-vision' and ensure "
            "Google Cloud credentials are configured."
        )

    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return ""

    # Crop the region at original resolution
    crop_box = (int(x), int(y), int(x + w), int(y + h))
    cropped = pil_image.crop(crop_box)

    # Convert to bytes (PNG to preserve quality, but JPEG would also work)
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    content = buf.getvalue()

    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=content)

    response = client.document_text_detection(
        image=image,
        image_context={"language_hints": ["en-IE"]},
    )

    if response.error.message:
        raise RuntimeError(f"Cloud Vision error: {response.error.message}")

    text = ""
    if response.full_text_annotation:
        text = _get_text_in_reading_order(response.full_text_annotation)
    if not text and response.text_annotations:
        # Fallback: use first annotation if full_text_annotation is missing or empty
        text = response.text_annotations[0].description

    return _normalize_ocr_text(text)

