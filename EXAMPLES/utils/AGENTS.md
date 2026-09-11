# EXAMPLES/utils — heading-check dumps

## Purpose

Local Python helpers for Designer JSON vs Qualtrics Excel heading checks in chat. Not runtime. Not the in-app export assistant.

## Ownership

- `qualtrics_headers.py` — two-row Excel load (forward-fill stems, skip Qualtrics meta)
- `designer_fields.py` — page JSON via `iter_runtime_fields` (RadioGrid expansion)
- `dump_headings.py` — print both sequences plus grids, duplicate `name`, missing `column_title`

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

openpyxl is required for the Excel dump (venv extra; not a product dependency).

## Verification

## Child DOX Index
