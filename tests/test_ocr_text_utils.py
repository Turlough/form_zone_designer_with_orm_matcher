"""Tests for Indexer OCR text normalization and project all_uppercase."""

from util.ocr_text_utils import normalize_ocr_text


def test_normalize_ocr_text_collapses_whitespace():
    assert normalize_ocr_text("hello\n\nworld") == "hello world"
    assert normalize_ocr_text("  a   b  ") == "a b"


def test_normalize_ocr_text_preserves_case_by_default():
    assert normalize_ocr_text("Hello World") == "Hello World"
    assert normalize_ocr_text("") == ""


def test_normalize_ocr_text_uppercases_when_enabled():
    assert normalize_ocr_text("Hello World", all_uppercase=True) == "HELLO WORLD"
