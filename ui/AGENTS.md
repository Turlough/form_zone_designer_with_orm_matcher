# UI package

## Purpose

PyQt6 widgets, panels, dialogs, and layouts shared by Designer, Indexer, and related tools.

## Ownership

- Widgets under `ui/`; re-export public surfaces from `ui/__init__.py`
- Application shells and orchestration stay in repo-root `app_*.py` files

## Local Contracts

- Designer-facing: thumbnails, main image, edit panel, grid designer, rectangle selection dialog (batch question mode + **Assistant** when drawn frame has inner rects), analyse preview dialog (`DesignerAnalysePreviewDialog`), rectangle detection sensitivity dialog (`DesignerRectangleDetectDialog`), indexing config dialogs (`DesignerIndexingConfigDialog`, `DesignerCreateTestBatchDialog`)
- Designer **Indexing Config** menu (after File): **Basic Indexing Config** edits `project_name`, `batch_folder`, `import_filename`, `lookup_list`, `lookup_prime_index`, `pages_without_fiducial` in `json/project_config.json` (merge, do not wipe other keys); **Create Test Batch** writes `<batch_folder>/<batch name>/` with `0001.pdf`–`nnnn.pdf` copies of `template.pdf` and `import_filename` listing those files
- Designer **Help** menu (last): **Designer** (`F1`) and **Templates** open `USER_INSTRUCTIONS/html/designer.html` and `templates.html` in the default browser (Designer only). PyInstaller must bundle the whole `USER_INSTRUCTIONS/html/` folder (`--add-data USER_INSTRUCTIONS/html;USER_INSTRUCTIONS/html` on Windows) so CSS and in-page links keep working.
- Drawn-rect batch mode (`RectangleSelectedDialog`): shared `question_number` / `full_text`, per-answer type+name rows (scroll when the list would exceed the screen; Assistant / Radio group / Radio grid / Submit / Cancel / Delete stay visible); **Assistant** via `question_assistant/`; **Submit** creates one field per inner rectangle; **Radio group** creates one `RadioGroup` (frame bounds, inner rects as `RadioButton`s, names from answer rows; layout need not be a grid; group `name` / `column_title` from `full_text`, `question_number` stored separately); **Radio grid…** closes the dialog and opens Grid Designer seeded with `full_text` as the grid name; inner rects sorted reading-order before naming/Submit
- Existing-field edit: non-modal `RectangleSelectedDialog` plus reshape handles on `ImageDisplayWidget` (standalone fields only)
- `RadioGrid` click opens Grid Designer for create/edit/reshape; runtime apps expand grids to `RadioGroup`s on load
- Drawn-rect Field Editor submit with type `RadioGrid`: clear the main-image selection, then open Grid Designer pre-seeded with that rect/name (grid is added only when Grid Designer submits)
- Grid Designer scrolls its page viewport to center the grid rectangle when opened with a pre-seeded/existing grid
- Grid Designer metadata: `question_number`, name/summary, `full_text`; row/col labels are not capped at 50 characters (overlay still uses summary ≤50)
- Grid Designer **Assistant** (right of orientation toggles): requires drawn ROI + ≥2 detected answer rects in ROI; autofills/overwrites labels and metadata via `runtime_assistants/design_assistant/grid_assistant/`; shrinks `grid_rect` to tightly frame answer boxes (stem/headings excluded); shows wait cursor while analysing

- Grid Designer grid name / row / column label edits have no character max; overlay display still caps via `summary` / `display_label` (50)
- Indexer-facing: main image panel, details panel, menus, OCR/index/comment/QC dialogs; per-field and page OCR buttons hidden unless `INDEXING_ASSISTANT_ENABLED` is truthy in `.env` (Indexer shell owns visibility)
- Field overlay colours: resolve via `field_factory.get_field_display_color()` (shared with Indexer); do not read `field.colour` for paint
- Designer field list Type column: cell background via `field_factory.get_display_color_for_type()` (same palette as overlays); text contrast black/white by luminance
- Prefer extending existing widgets over duplicating paint or layout logic in entry-point apps

## Work Guidance

## Verification

## Child DOX Index
