# Tests

## Purpose

Automated checks for validation and other testable project logic.

## Ownership

- Test modules under `tests/`; run with pytest from repo root (activate `.venv` first per root tooling rules)

## Local Contracts

- Prefer tests that assert real validation and business rules, not PyQt widget smoke unless explicitly requested
- Design assistant: schema/match tests only — no live VLM API in CI (`test_design_assistant_*.py`)

## Work Guidance

## Verification

- `pytest tests/` (install dev deps: `uv pip install pytest` or `uv pip install -e ".[dev]"`)
- Headless Indexer smoke: `QT_QPA_PLATFORM=offscreen python scripts/smoke_indexer.py`

## Child DOX Index

- `tests/validations/AGENTS.md` — validation-focused pytest modules
