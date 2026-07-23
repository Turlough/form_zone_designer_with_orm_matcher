# User instructions

## Purpose

End-user and operator documentation for template setup, Designer, Indexer, and Exporter (separate from agent DOX and `.cursor/` notes).

## Ownership

- `INSTRUCTIONS-1-Templates.md` — project folder, template TIFF, fiducials, `project_config.json` (read before Designer)
- `INSTRUCTIONS-2-Designer.md` — Form Zone Designer
- `INSTRUCTIONS-3-Indexer.md` — Indexer and QC workflows
- `INSTRUCTIONS-4-Exporter.md` — Exporter

## Local Contracts

- Numbered instruction files follow setup order: templates → design → indexing → export
- One major topic per file; keep tone and structure consistent across the set
- Do not duplicate binding agent contracts from root or child `AGENTS.md` files here—this folder is for human operators
- When app behaviour or on-disk layout changes, update the nearest instruction file and this index

## Work Guidance

- Derive folder and JSON contracts from `util/designer_config.py`, `util/designer_persistence.py`, and `env.example` when documenting templates
- Use domain terms from `.cursor/rules/domain_terms.md` for operator-facing wording
- After editing operator `.md` files, regenerate static HTML: `python USER_INSTRUCTIONS/build_html.py` (requires `markdown` package). Output lives in `USER_INSTRUCTIONS/html/`; open `index.html` or `templates.html` in a browser.

## Verification

## Child DOX Index
