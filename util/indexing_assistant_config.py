"""Indexer Gemini OCR / VLM assistant feature flag."""

from __future__ import annotations

import os

_TRUTHY = frozenset({"1", "true", "yes"})


def indexing_assistant_enabled() -> bool:
    """Return True only when INDEXING_ASSISTANT_ENABLED is explicitly truthy."""
    return os.getenv("INDEXING_ASSISTANT_ENABLED", "").strip().lower() in _TRUTHY
