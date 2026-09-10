# Export assistant for Designer

## Purpose

Ingest customer Excel export samples into a versioned JSON descriptor, check Designer page fields against that contract, and supply export column context to page Analyse and Grid Assistant when defined.

## Ownership

- `schema.py`, `parse_excel.py`, `enrich.py`, `io.py`, `check.py`, `prompt_context.py`, `__init__.py`
- Plan: `PLAN.md`
- Invoked from `app_designer.py`:
  - **File → Import export format…**
  - **Assistant → Check export format**

## Local Contracts

### Ingest

- Excel at config folder root (file dialog default)
- Deterministic Qualtrics-style two-header parse → `json/export_format.vN.json`
- AI enrich assigns `page_hint` (heuristic fallback when API unavailable)
- `project_config.json` pointer: `export_format.active_version`, `export_format.path`
- Re-import always bumps version; prior files retained

### Descriptor

- `columns[]`: `id`, `header`, `subheader`, `kind`, `page_hint`, optional `group_id`
- `meta_columns[]`: system columns (ignored by Check; Exporter follow-up for delivery)
- `groups[]`: multi-select blocks

### Check

- Page-scoped (1-based `page_hint`)
- Skips meta columns
- Stable match via `export_column_id` on fields after Apply
- Form-only fields → **warning**; propose full text verbatim
- Radio / option labels: full text verbatim; do not change `checked_value`
- Preview → **Apply** writes `column_title`, `full_text`, `summary`, `export_column_id`; does **not** overwrite top-level `field.name` (identity). RadioButton option `name` may still update (cell values).
- Exporter **Deliver** remaps working-CSV `name` headers to `export_display_title` (`column_title` else `name`)

### Analyse / Grid context

- When active descriptor exists, pass page slice into design_assistant and grid_assistant prompts
- If no descriptor, behaviour unchanged

### Field metadata

- `export_column_id` on `Field` (optional, persisted when set)

### VLM

- Reuse `GOOGLE_API_KEY` / `GEMINI_API_KEY`, `DESIGN_ASSISTANT_MODEL`
- No PyQt imports in this package

## Work Guidance

- JSON descriptor is the AI contract after ingest; do not re-read Excel in Check/Analyse
- Tickbox delivery encoding (`Ticked` → `1`) is Exporter scope, not this package

## Verification

- `tests/test_export_assistant_for_designer.py` — parse, io, check, apply (no live API)

## Child DOX Index
