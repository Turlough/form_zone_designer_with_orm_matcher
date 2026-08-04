# Output format compatibility

## Purpose

Document how this suite’s CSV delivery format relates to external survey and data-capture providers. Reference material for mapping, customer handoffs, and future import/export adapters—not runtime code.

## Ownership

- `App_Export.md` — canonical description of Indexer batch CSV and Exporter **Deliver** output (this app’s format)
- Provider-specific notes — one markdown file per external system (e.g. `Qualtrics.md`); add new files here as compatibility is documented

## Local Contracts

- **Documentation only.** No Python modules, tests, or app entry points live in this folder.
- Implementation contracts for export behavior remain in `app_exporter.py`, `util/csv_manager.py`, and `.cursor/mIsc/app_exporter.md`; this folder explains and compares, it does not override code.
- Each provider doc should cover: export file shape, multi-select / checkbox encoding, values vs labels, and how that maps to `App_Export.md`.
- Operator-facing step-by-step instructions stay in `USER_INSTRUCTIONS/`; cross-link when helpful, do not duplicate full workflows here.
- New provider docs: use `{Provider}.md` at this level unless a provider needs its own subfolder later.

## Work Guidance

- When export behavior in code changes, update `App_Export.md` first, then adjust provider comparison sections.
- When adding a provider, add `{Provider}.md` and list it in the Child DOX Index below.
- Prefer comparison tables and explicit mapping notes (column layout, selected/unselected encoding, quoting) over narrative-only prose.

## Verification

## Child DOX Index

- `App_Export.md` — this app’s batch and delivery CSV format
- `Qualtrics.md` — Qualtrics response export formats and mapping notes
