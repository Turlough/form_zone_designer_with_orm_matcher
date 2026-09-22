# UI package

## Purpose

PyQt6 widgets, panels, dialogs, and layouts shared by Designer, Indexer, and related tools.

## Ownership

- Widgets under `ui/`; re-export public surfaces from `ui/__init__.py` (lazy `__getattr__` so Indexer/PyInstaller do not import Designer-only modules unless used)
- Application shells and orchestration stay in repo-root `app_*.py` files

## Local Contracts

- Designer-facing: thumbnails, main image, edit panel, grid designer, print crop window (`PrintCropWindow`), rectangle selection dialog (batch question mode + **Assistant** when drawn frame has inner rects), analyse preview dialog (`DesignerAnalysePreviewDialog`), rectangle detection sensitivity dialog (`DesignerRectangleDetectDialog`), indexing config dialogs (`DesignerIndexingConfigDialog`, `DesignerCreateTestBatchDialog`)
- Designer **Fiducials** menu: **Select rectangle** saves per-page `logo-pN.png`; **Print crop…** opens a two-pane window (template + sample scan). The crop rectangle is one project-wide `print_crop` in `json/project_config.json`. Dragging the crop paints the overlay only (template image is not rescaled). Both panes share vertical and horizontal scroll. Click the prepared scan to drop numbered registration marks (crop-normalised); the same marks are drawn on the template using the current crop so they move as the rectangle is adjusted. **Clear registration marks** drops them. On mouseup the sample is pasted into that rect on a template-sized canvas, then fiducial + field overlays confirm alignment. **Save detected fiducial** (enabled when match score ≥ 0.7) crops that region from the prepared scan and overwrites the default logo (`fiducial.png` / `logo.png` / first `DEFAULT_LOGO_CANDIDATES` hit); confirm first (no app backup); then rematch. **File → Load cropped version** lives on that window (file picker starts at `batch_folder` from `project_config.json`; relative paths are from the project folder). Save/Clear write or remove the key (merge, do not wipe other keys).
- Designer **Indexing Config** menu (after File): **Basic Indexing Config** edits `project_name`, `batch_folder`, `import_filename`, `lookup_list`, `lookup_prime_index`, `pages_without_fiducial`, `all_uppercase` in `json/project_config.json` (merge, do not wipe other keys); **Create Test Batch** writes `<batch_folder>/<batch name>/` with `0001.pdf`–`nnnn.pdf` copies of `template.pdf` and `import_filename` listing those files
- Designer **Help** menu (last): **Designer** (`F1`) and **Templates** open `USER_INSTRUCTIONS/html/designer.html` and `templates.html` in the default browser (Designer only). PyInstaller must bundle the whole `USER_INSTRUCTIONS/html/` folder (`--add-data USER_INSTRUCTIONS/html;USER_INSTRUCTIONS/html` on Windows) so CSS and in-page links keep working.
- Drawn-rect batch mode (`RectangleSelectedDialog`): shared `question_number` / `full_text`, per-answer type+name rows (scroll when the list would exceed the screen; Assistant / Radio group / Radio grid / Submit / Cancel / Delete stay visible); **Assistant** via `question_assistant/`; **Submit** creates one field per inner rectangle; **Radio group** creates one `RadioGroup` (frame bounds, inner rects as `RadioButton`s, names from answer rows; layout need not be a grid; group `name` / `column_title` from `full_text`, `question_number` stored separately); **Radio grid…** closes the dialog and opens Grid Designer seeded with `full_text` as the grid name; inner rects sorted reading-order before naming/Submit
- Existing-field edit: non-modal `RectangleSelectedDialog` plus reshape handles on `ImageDisplayWidget` (standalone fields only). Dialog shows JSON keys except `colour` (type palette via `field_factory`); geometry is one `x, y, width, height` field. Submit preserves unspecified keys (`full_text`, `summary`, `column_title`, `question_number`, `checked_value`, nested `radio_buttons`) via `util/field_edit.py`
- `RadioGrid` click opens Grid Designer for create/edit/reshape; runtime apps expand grids to `RadioGroup`s on load
- Drawn-rect Field Editor submit with type `RadioGrid`: clear the main-image selection, then open Grid Designer pre-seeded with that rect/name (grid is added only when Grid Designer submits)
- Grid Designer scrolls its page viewport to center the grid rectangle when opened with a pre-seeded/existing grid
- Grid Designer metadata: `question_number`, name/summary, `full_text`; row/col labels are not capped at 50 characters (overlay still uses summary ≤50)
- Grid Designer **Assistant** (right of orientation toggles): requires drawn ROI + ≥2 detected answer rects in ROI; autofills/overwrites labels and metadata via `runtime_assistants/design_assistant/grid_assistant/`; shrinks `grid_rect` to tightly frame answer boxes (stem/headings excluded); shows wait cursor while analysing

- Grid Designer grid name / row / column label edits have no character max; overlay display still caps via `summary` / `display_label` (50)
- Indexer Batch menu: selecting a batch from the job folder or `_qc` claims it by renaming into that parent’s `_in_progress`, then appends `Open Batch` to `batch.log` (`util/batch_log.py`). Already under `_in_progress` is a resume (no move, no log).
- Indexer **Log → View log**: `IndexBatchLogDialog` tables `batch.log` for the open batch (columns from `LOG_COLUMNS`); dialog sizes to the table (capped to the screen) with one Close button. No batch open: information dialog, no table.
- Indexer-facing: main image panel, details panel, menus, OCR/index/comment/QC dialogs; per-field and page OCR buttons hidden unless `INDEXING_ASSISTANT_ENABLED` is truthy in `.env` (Indexer shell owns visibility)
- Indexer comments (`IndexCommentDialog`): left of the field-list row, then clamped to the available screen so Submit/Cancel stay visible; preset list scrolls if the dialog would be taller than the screen. Submit is the default button.
- Indexer **Page → Drag fields** (`IndexDragFieldsWindow`): opens maximised; the current scan is scaled to fit and centred in the window. Field outlines and one group box. Interior drag moves every field; an edge scales that axis only (opposite edge fixed); a corner scales uniformly so the box keeps its aspect ratio. **Apply** stores a page-visit `FieldGroupAlign` used by the centre panel, close-up, clicks, and OCR. **Cancel** leaves placement unchanged. Leaving the page clears it. Field JSON is not modified.
- Indexer text case: `IndexDetailPanel` / `IndexTextDialog` `all_uppercase` follows `project_config.json` `all_uppercase` (default False). Eircode display/storage stays uppercase regardless.
- Indexer field list (`fields_table`): two equal-width Stretch columns; cell text elides (hover tooltip shows full name/value); on field activation, the table scrolls so the current row is in view
- Indexer columns: after a page is shown, centre width is page-fit plus 10% right padding (`page_fit_panel_width`, `PAGE_FIT_RIGHT_PADDING_RATIO`); right panel keeps the remaining width. Recalculate only on window resize, not on field/page/document change. `IndexDetailPanel` field-name label elides (tooltip has the full name) and must not expand the panel
- Indexer centre page: `MainImageIndexPanel` shows the scanned page with no print_crop canvas borders, left-aligned so the extra page-fit width is empty space on the right for Show Value overlays. Matching still uses the template-sized prepared canvas; display crops to the pasted scan and `canvas_origin` keeps overlays/clicks aligned
- Indexer close-up (`closeup_crop_and_overlay`, `closeup_abs_on_display`): same displayed scan as the centre panel; field origin is logo-relative canvas coords (after any page-visit `FieldGroupAlign`) minus `canvas_origin` (print_crop x, y). Equal padding around the field; overlay size follows the aligned field and is drawn at that position in the crop (not independently recentred)
- Field overlay colours: resolve via `field_factory.get_field_display_color()` (shared with Indexer); do not read `field.colour` for paint
- Designer field list Type column: cell background via `field_factory.get_display_color_for_type()` (same palette as overlays); text contrast black/white by luminance
- Prefer extending existing widgets over duplicating paint or layout logic in entry-point apps

## Work Guidance

## Verification

## Child DOX Index
