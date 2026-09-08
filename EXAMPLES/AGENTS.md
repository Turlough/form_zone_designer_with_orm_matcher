# EXAMPLES — customer sample packs

## Purpose

Local sample packs for Designer JSON vs customer export-header checks. Not runtime. Survey subfolders are gitignored; this file is tracked.

## Ownership

- One first-level subfolder per survey
- `RoI/` — Republic of Ireland Milk Planning Census
- `NI/` — Northern Ireland survey

Each survey folder typically contains:

- `json/` — Designer page files (`N.json`) and `project_config.json`
- Customer export sample (`.xlsx`, Qualtrics two-row headers)
- Optional: `template.pdf` / `fiducials/`

## Local Contracts

Compare **Designer JSON** to **export headings** in chat. Do not use `runtime_assistants/design_assistant/export_assistant_for_designer` unless asked.

JSON field order (page files in numeric order, then fields in each file) must match Excel column order after Qualtrics meta. Call out missing, extra, and out-of-order fields.

Qualtrics Excel (first sheet):

- Row 1 = question stem (forward-fill blanks)
- Row 2 = `Response` (single choice / radio), `Open-Ended Response` (text), or an option/subfield name
- Named option subheaders on a “tick all that apply” question = tickboxes
- Named subheaders on numeric/matrix blocks (`Owned acres`, `2026`, `Slurry`) are still those fields, not tickboxes
- Leading columns Respondent ID … Custom Data 1 are Qualtrics meta; ignore for field mapping

JSON:

- `Tickbox` → one export option column
- `RadioGroup` / 1-column `RadioGrid` with `orientation: vertical` → one `Response` column
- Horizontal/multi-column `RadioGrid` → one radio per column (matrix)
- A 1-column grid with default **horizontal** orientation expands to N groups; use **vertical** for a single Qualtrics radio

Print-only fields (cover litres, overflow comments, date signed, extra ticks) may stay in JSON with no Excel column. Say so; do not treat them as heading drift.

## Work Guidance

When the user points at a survey folder (or `json/` + an xlsx):

1. Map JSON fields to export columns (question stem, then options)
2. Check field **order**: JSON sequence vs Excel columns (skip meta). Flag any swap, insertion, or skip
3. List JSON-only (missing from Excel) and Excel-only (extra) headings
4. Flag radio vs tickbox mismatches (JSON type vs Excel `Response` vs option columns)
5. Note wording / Other-specify / split-vs-combined extras; do not block on unconfirmed radio **labels** (`Response` columns do not list choices)
6. Say whether a new sample is needed, or live data is enough

A dummy two-row xlsx is enough for **headings and types**. It is not enough for radio option text. Ask for a filled sample or live data when labels must be verified.

Report only mismatches, leftovers, and order drift. Do not dump a full mapping table unless asked.

RoI (parked until new sample or live data): 3km land follow-up still a tickbox vs Excel `Response`; page 21 / AgNav / consent / BTE split; duplicate `Full Name` if those columns are delivered.

## Verification

No automated test. Re-run this checklist after Designer JSON changes, or when a new export sample arrives.

## Child DOX Index

- `RoI/` — gitignored pack (JSON + `ExportSampleROI.xlsx`)
- `NI/` — gitignored pack (fill when samples exist)
