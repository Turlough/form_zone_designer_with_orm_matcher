"""Tests for Indexer Gemini OCR feature flag."""

import os

import pytest

from util.indexing_assistant_config import indexing_assistant_enabled


@pytest.mark.parametrize(
    "value",
    ["", "false", "0", "no", "FALSE", " maybe "],
)
def test_indexing_assistant_disabled_by_default_or_falsy(monkeypatch, value):
    monkeypatch.setenv("INDEXING_ASSISTANT_ENABLED", value)
    assert indexing_assistant_enabled() is False


def test_indexing_assistant_disabled_when_unset(monkeypatch):
    monkeypatch.delenv("INDEXING_ASSISTANT_ENABLED", raising=False)
    assert indexing_assistant_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "True", "YES"])
def test_indexing_assistant_enabled_when_truthy(monkeypatch, value):
    monkeypatch.setenv("INDEXING_ASSISTANT_ENABLED", value)
    assert indexing_assistant_enabled() is True
