# Util package

## Purpose

Non-UI services: ORM logo matching, document loading, persistence, CSV/index I/O, OCR clients, paths, and shared app state.

## Ownership

- Modules under `util/`; package exports in `util/__init__.py` define the primary import surface for apps
- Field-type definitions and factories live at repo root (`fields.py`, `field_factory.py`, `page.py`), not here
- `field_factory.FIELD_TYPE_MAP` is the single source for field overlay colours (Designer + Indexer) and JSON `colour` on load/save; stored JSON colours are ignored/overwritten on read

## Local Contracts

- Apps import shared capabilities via `util` (e.g. `ORMMatcher`, `CSVManager`, `ProjectValidations`, designer persistence helpers)
- Designer rectangle detection: `RectangleDetectionSettings` in `util/rectangle_detection_settings.py`; optional per-project `rectangle_detection` key in `json/project_config.json` (load/save via `designer_persistence`)
- Designer Basic Indexing Config: `load_project_config` / `save_indexing_config` / `indexing_config_from_project` in `designer_persistence.py` merge `project_name`, `batch_folder`, `import_filename`, `lookup_list`, `lookup_prime_index`, `pages_without_fiducial` into `json/project_config.json` (blank `lookup_list` removes the key)
- Indexer test batches: `util/test_batch.py` (`create_test_batch`) copies `template.pdf` (or converts `template.tif` / `template.tiff`) to `0001.pdf`–`nnnn.pdf` under `batch_folder/<batch name>/` and writes `import_filename` listing those files
- Validation rules and strategies live in `util/validation/` (see child DOX)
- Environment and project paths: respect `util/path_utils.py` and `util/app_state.py` conventions
- Indexer OCR: gated by `INDEXING_ASSISTANT_ENABLED` in `.env` (default off; see `util/indexing_assistant_config.py`); `util/gemini_ocr_client.py` (`GOOGLE_API_KEY` or `GEMINI_API_KEY` when enabled); text normalization in `util/ocr_text_utils.py`
- Field display/CSV metadata helpers: `util/field_metadata.py` (`summary`, `column_title`, `full_text`, `question_number` with `name` fallbacks; summary overlay ≤50; column titles not short-capped)

- Designer field reshape: `util/field_geometry_edit.py` (grid division drag, resize handles, snapshots for cancel)
- Radio grid layout: `util/radio_grid_layout.py` — expand `RadioGrid` to `RadioGroup`s for Indexer/Exporter; `build_radio_group_from_frame` for a single irregular RadioGroup from a question frame (group name from question text)
- Designer page VLM analysis lives under `runtime_assistants/design_assistant/` (not in this package)
- Document loading: `util/document_loader.py`; lazy page access for Indexer in `util/lazy_document_pages.py`
- Indexer open-document landing page: `first_page_index_with_json` in `designer_persistence.py` (first `{n}.json` in `json/`, else page 1)
- Duplicate field names: `find_duplicate_field_names` in `designer_persistence.py` — `field.name` must be unique project-wide (Indexer/Exporter key CSV columns and values by it); checks top-level fields after RadioGrid expansion. Designer's `_save_page_fields` wrapper (`app_designer.py`) calls this after every page save and warns (non-blocking) on collisions.
- Fiducials: `util/fiducial_paths.py` — default logo candidates and per-page `logo-pN.png` (1-based N) overriding default when present
- Project blank-form template: `find_project_template()` in `path_utils.py` resolves `template.tif`, `template.tiff`, or `template.pdf` (case-insensitive; first listed wins if several exist)
- Operator help HTML: `user_instructions_html_path()` in `path_utils.py` resolves `USER_INSTRUCTIONS/html/<file>` from the repo root, or from `sys._MEIPASS` / next to the exe when frozen (PyInstaller)

## Work Guidance

## Verification

## Child DOX Index

- `util/validation/AGENTS.md` — project- and field-level validation strategies and rules
