"""Shared post-processing for OCR text returned to the Indexer."""

from __future__ import annotations

import re


def normalize_ocr_text(raw_text: str, *, all_uppercase: bool = False) -> str:
    """Normalize OCR text for storage in batch CSV / detail panel."""
    if not raw_text:
        return ""

    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return text.upper() if all_uppercase else text
