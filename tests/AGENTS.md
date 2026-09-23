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
- Indexing config / test batch: `test_indexing_config.py` (`save_indexing_config` merge, `all_uppercase` default False, `create_test_batch`, `first_page_index_with_json`, `iter_page_json_paths`, `runtime_field_names`, `export_title_map`)
- Indexer OCR text: `test_ocr_text_utils.py` (`normalize_ocr_text` whitespace + `all_uppercase`)
- Indexer working CSV: `test_csv_manager.py` (`field.name` headers, JSON page gaps, rewrite of title-headed files)
- Indexer OCR feature flag: `test_indexing_assistant_config.py` (`INDEXING_ASSISTANT_ENABLED` defaults and truthy parsing)
- Indexer close-up crop/overlay: `test_index_closeup.py` (`closeup_crop_and_overlay` equal padding; edge clamping; `closeup_abs_on_display` subtracts print_crop origin)
- Indexer text-field focus: `test_index_text_focus.py` (clicking a text field puts the caret in the close-up value box; the under-field dialog does not take focus)
- Indexer drag-fields geometry: `test_field_group_align.py` (group union, edge scale, corner aspect lock, `placed_rect` with frozen logo)
- Indexer centre-panel page fit: `test_index_page_layout.py` (`page_fit_panel_width`, including 10% right padding)
- Indexer comments dialog placement: `test_index_comment_dialog.py` (`pos_left_of_rect`, `clamp_window_to_available`, `capped_dialog_height`)
- Designer Help HTML paths: `test_user_instructions_html.py` (`user_instructions_html_path`, including frozen `_MEIPASS`)
- Designer duplicate field-name check: `test_designer_persistence_duplicates.py` (`find_duplicate_field_names` — cross-page, same-page, and RadioGrid-expansion cases)
- Designer field editor apply: `test_field_edit.py` (`apply_field_edit` preserves JSON metadata; geometry parse)
- Print crop: `test_print_crop.py` (`parse_print_crop`, `prepare_scan_page` paste-into-canvas, `crop_prepared_page_for_display` drops canvas margins, `save_print_crop` merge/clear, crop-normalised registration `canvas_to_crop_uv` / `crop_uv_to_canvas`, `fiducial_bbox_inside_crop`)
- Fiducial paths / detected-patch save: `test_fiducial_paths.py` (`find_fiducial_for_page`, `save_detected_fiducial` overwrites default `fiducial.png`)
- Indexer batch log: `test_batch_log.py` (`current_user`, location labels for job/`_in_progress`/`_qc`/`_qc/_in_progress`/`_complete`, TSV header + append, `read_batch_log`, Open/Complete moves)

## Work Guidance

## Verification

- `pytest tests/` (install dev deps: `uv pip install pytest` or `uv pip install -e ".[dev]"`)
- Headless Indexer smoke: `QT_QPA_PLATFORM=offscreen python scripts/smoke_indexer.py`

## Child DOX Index

- `tests/validations/AGENTS.md` — validation-focused pytest modules
