# Tests

## Purpose

Automated checks for validation and other testable project logic.

## Ownership

- Test modules under `tests/`; run with pytest from repo root (activate `.venv` first per root tooling rules)

## Local Contracts

- Prefer tests that assert real validation and business rules, not PyQt widget smoke unless explicitly requested
- Design assistant: schema/match tests only — no live VLM API in CI (`test_design_assistant_*.py`)
- Grid assistant: geometry/schema tests only — no live VLM API in CI (`test_grid_assistant_geometry.py`)
- Question assistant: geometry/schema tests only — no live API in CI (`test_question_assistant.py`)
- Radio group from question frame: `test_radio_grid_layout.py` (`build_radio_group_from_frame`)

- Field overlay theming: `test_field_factory_theme.py` (shared Designer/Indexer palette via `field_factory`)

## Work Guidance

## Verification

- `pytest tests/` (install dev deps: `uv pip install pytest` or `uv pip install -e ".[dev]"`)
- Headless Indexer smoke: `QT_QPA_PLATFORM=offscreen python scripts/smoke_indexer.py`

## Child DOX Index

- `tests/validations/AGENTS.md` — validation-focused pytest modules
