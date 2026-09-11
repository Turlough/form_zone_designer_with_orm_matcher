# Tests

## Purpose

Automated checks for validation and other testable project logic.

## Ownership

- Test modules under `tests/`; run with pytest from repo root (activate `.venv` first per root tooling rules)

## Local Contracts

- Prefer tests that assert real validation and business rules, not PyQt widget smoke unless explicitly requested
- Design assistant: schema/match tests only — no live VLM API in CI (`test_design_assistant_*.py`)
- Grid assistant: geometry/schema tests only — no live VLM API in CI (`test_grid_assistant_geometry.py`, including question-axis label fill)
- Question assistant: geometry/schema tests only — no live API in CI (`test_question_assistant.py`)
- Radio group from question frame: `test_radio_grid_layout.py` (`build_radio_group_from_frame`)

- Field overlay theming: `test_field_factory_theme.py` (shared Designer/Indexer palette via `field_factory`, including `get_display_color_for_type`)
- Indexing config / test batch: `test_indexing_config.py` (`save_indexing_config` merge, `create_test_batch`, `first_page_index_with_json`, `iter_page_json_paths`, `runtime_field_names`, `export_title_map`)
- Indexer working CSV: `test_csv_manager.py` (`field.name` headers, JSON page gaps, rewrite of title-headed files)
- Indexer OCR feature flag: `test_indexing_assistant_config.py` (`INDEXING_ASSISTANT_ENABLED` defaults and truthy parsing)
- Indexer close-up crop/overlay: `test_index_closeup.py` (`closeup_crop_and_overlay` equal padding; edge clamping)
- Designer Help HTML paths: `test_user_instructions_html.py` (`user_instructions_html_path`, including frozen `_MEIPASS`)
- Designer duplicate field-name check: `test_designer_persistence_duplicates.py` (`find_duplicate_field_names` — cross-page, same-page, and RadioGrid-expansion cases)
- Designer field editor apply: `test_field_edit.py` (`apply_field_edit` preserves JSON metadata; geometry parse)

## Work Guidance

## Verification

- `pytest tests/` (install dev deps: `uv pip install pytest` or `uv pip install -e ".[dev]"`)
- Headless Indexer smoke: `QT_QPA_PLATFORM=offscreen python scripts/smoke_indexer.py`

## Child DOX Index

- `tests/validations/AGENTS.md` — validation-focused pytest modules
