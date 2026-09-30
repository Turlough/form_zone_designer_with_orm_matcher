# EXAMPLES/utils — heading-check dumps

## Purpose

Local Python helpers for Designer JSON vs Qualtrics Excel heading checks in chat. Not runtime. Not the in-app export assistant.

## Ownership

- `qualtrics_headers.py` — two-row Excel load (forward-fill stems, skip Qualtrics meta)
- `designer_fields.py` — page JSON via `iter_runtime_fields` (RadioGrid expansion)
- `dump_headings.py` — print both sequences plus grids, duplicate `name`, missing `column_title`
- `generate_export_config.py` — build `export_config.json` for a survey folder (json + Qualtrics `.xlsx`). Per-survey fixes live in `SURVEYS[<folder name>]`: `columns`, `tickbox_checked`, `radio`, `merge_columns`, and optionally `match: "order"` + `skip_fields` (pair fields to columns by position when JSON order already matches Excel, as for NI). `value_maps` are derived from the xlsx data rows: single online value per tick column; fuzzy radio-label match only onto online labels no scan button already matches exactly. Regenerate after edits and review printed warnings — a warning means the label was not seen online and passes through unchanged. Each survey pack keeps its own copy (`EXAMPLES/RoI/`, `EXAMPLES/NI/`); those copies import `qualtrics_headers.py` from here, so keep its API stable.

## Local Contracts

- Do not pair or judge mismatches here. Matching stays in chat (`EXAMPLES/AGENTS.md`).
- Do not import `runtime_assistants/design_assistant/export_assistant_for_designer`.
- Named Excel row-2 cells stay `named`; chat decides tickbox vs numeric/matrix.
- Survey packs stay gitignored; this folder is tracked.

## Work Guidance

From repo root, project venv:

```powershell
.\.venv\Scripts\python.exe EXAMPLES\utils\dump_headings.py EXAMPLES\RoI
```

openpyxl is required for the Excel dump (also a product dependency for the Exporter's online-compat transform).

## Verification

## Child DOX Index
