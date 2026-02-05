"""Gemini vision OCR for the Field Indexer.

Uses a vision LLM (Gemini) to read the selected image region as a single
paragraph (left to right, top to bottom). This is often more robust for
handwriting and form layouts than Cloud Vision's DOCUMENT_TEXT_DETECTION.

API key:
    - Set GOOGLE_API_KEY or GEMINI_API_KEY in your environment or .env file.
      You can obtain a key from https://aistudio.google.com/apikey
"""

from __future__ import annotations

import io
import os
from typing import Tuple

from PIL import Image

from util.cloud_vision_client import _normalize_ocr_text

Rect = Tuple[int, int, int, int]

OCR_PROMPT = (
    "Read all the text in this image as a single paragraph, "
    "left to right and top to bottom, as a human would read it. "
    "Output only the raw text, with no commentary."
)


def ocr_image_region(pil_image: Image.Image, rect: Rect) -> str:
    """Run Gemini vision OCR on a rectangular region of a page.

    Args:
        pil_image: Full page image at original scan resolution.
        rect: (x, y, width, height) in page pixel coordinates.

    Returns:
        Normalized OCR text (may be empty string).

    Raises:
        RuntimeError: If google-genai is not available or the API call fails.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:  # pragma: no cover - dependency not installed
        raise RuntimeError(
            "google-genai is not installed. Install it with:\n\n"
            "    pip install google-genai\n"
        ) from e

    api_key = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError(
            "Gemini OCR requires an API key.\n"
            "Set GOOGLE_API_KEY or GEMINI_API_KEY in your environment (or .env),\n"
            "and obtain a key from https://aistudio.google.com/apikey"
        )

    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return ""

    # Crop the region at original resolution
    crop_box = (int(x), int(y), int(x + w), int(y + h))
    cropped = pil_image.crop(crop_box)

    # Encode as PNG bytes
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    client = genai.Client(api_key=api_key)
    try:
        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image_part, OCR_PROMPT],
        )
    finally:
        client.close()

    text = (getattr(response, "text", "") or "").strip().upper()
    return _normalize_ocr_text(text)

