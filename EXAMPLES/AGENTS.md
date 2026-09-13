# EXAMPLES — customer sample packs

## Purpose

Local sample packs for Designer JSON vs customer export-header checks. Not runtime. Survey subfolders are gitignored; this file and `utils/` are tracked.

## Ownership

- One first-level subfolder per survey
- `RoI/` — Republic of Ireland Milk Planning Census
- `NI/` — Northern Ireland survey
- `utils/` — heading-check dump helpers (tracked; see `utils/AGENTS.md`)

Each survey folder typically contains:

- `json/` — Designer page files (`N.json`) and `project_config.json`
- Customer export sample (`.xlsx`, Qualtrics two-row headers)
- Optional: `template.pdf` / `fiducials/`
- `current_status.md` — gitignored, overwriteable scratch after each heading check. Outstanding leftovers for the next run, plus long-term pack notes (sample file, sheet, page coverage). Not tracked. Do not park run leftovers in this `AGENTS.md`.

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

Dump both sequences first (`python EXAMPLES/utils/dump_headings.py EXAMPLES/<survey>`). Do not auto-pair from that dump.

Read `EXAMPLES/<survey>/current_status.md` at the start of a check if it exists. After reporting in chat, overwrite that file with current leftovers and useful pack notes. Keep survey-specific run notes out of this `AGENTS.md`.

When the user points at a survey folder (or `json/` + an xlsx):

1. Map JSON fields to export columns (question stem, then options)
2. Check field **order**: JSON sequence vs Excel columns (skip meta). Flag any swap, insertion, or skip. Include the second Excel row in sequence matching.
3. List JSON-only (missing from Excel) and Excel-only (extra) headings
4. Flag radio vs tickbox mismatches (JSON type vs Excel `Response` vs option columns)
5. Note wording / Other-specify / split-vs-combined extras; do not block on unconfirmed radio **labels** (`Response` columns do not list choices)
6. Say whether a new sample is needed, or live data is enough
7. Say where **name** has been duplicated
8. Say where **column_title** is missing
9. Include Page numbers when reporting, where possible.

A dummy two-row xlsx is enough for **headings and types**. It is not enough for radio option text. Ask for a filled sample or live data when labels must be verified.

Report only mismatches, leftovers, and order drift. Do not dump a full mapping table unless asked.

## Verification

No automated test. Re-run this checklist after Designer JSON changes, or when a new export sample arrives.

## Child DOX Index

- `RoI/` — gitignored pack (JSON + `ExportSampleROI.xlsx`; `current_status.md`)
- `NI/` — gitignored pack (JSON `4.json`–`19.json` + `ExportSampleNI.xlsx`; `current_status.md`)
- `utils/AGENTS.md` — dump helpers for JSON fields and Excel headings
