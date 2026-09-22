# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Repository purpose

PyQt6 suite for scanned multipage forms: **Designer** (`app_designer.py`) for templates and field zones, **Indexer** (`app_indexer.py`) for data entry and QC, **Exporter** (`app_exporter.py`) for CSV export. Shared field model (`fields.py`, `page.py`, `field_factory.py`) and ORM logo matching (`util/orm_matcher.py`).

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:

- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## User Preferences

When the user requests a durable behavior change, record it here or in the relevant child AGENTS.md

- Indexer: opening a document jumps to the first page that has a `{n}.json` file (1-based page JSON in the project `json/` folder). If none exist, stay on page 1. Session restore and QC navigation still go to the requested page after open.
- Indexer: typed and OCR text is converted to uppercase only when `project_config.json` `all_uppercase` is true (default false if missing). Eircode fields stay uppercase regardless.
- Designer: after every field save, warn (non-blocking dialog, does not block the save) if any `field.name` is duplicated across pages or repeated within a page. `field.name` is the single project-wide identity key Indexer and Exporter rely on; `column_title` may legitimately repeat (e.g. export-format matching) but `name` must not.
- Designer/Indexer: optional `print_crop` `{x, y, width, height}` in `json/project_config.json` (Designer **Fiducials → Print crop**). When set, Indexer and Field Review resize each scan to that size and paste it at `(x, y)` on a template-sized canvas before fiducial matching. The Indexer centre panel and field close-up then show that pasted scan only (no white canvas borders); overlays stay aligned by subtracting the crop origin. Missing key keeps the previous full-page resize.
- Indexer: after a page is shown, lock the centre (page-fit plus 10% right padding so Show Value overlays beside edge fields stay visible) and right panel widths. Do not change them when switching fields, pages, or documents. Recalculate only when the window is resized. Long field names elide in the right panel and must not widen it. The scan is left-aligned in the centre pane; extra width stays on the right.
- Designer Print crop: **Save detected fiducial** overwrites the project default logo (`fiducial.png` / `logo.png`) with the matched patch from the prepared scan. Use a page where the green box is on the mark; the app does not back up the previous file.
- Indexer: uses the Windows logged-in account (`getpass.getuser()`). Window title includes that user. After a successful batch folder rename, append a TSV line to `batch.log` beside the import file (`Datetime`, `User`, `Event`, `Previous location`, `New location`). Open Batch: job folder → `_in_progress`, or `_qc` → `_qc/_in_progress`. Complete Batch: `_in_progress` → `_qc`, or `_qc` / `_qc/_in_progress` → `_complete`. Do not log resume (already in `_in_progress`) or session restore. Log write failure must not undo the move. **Log → View log** opens a table of that file (size to contents, Close only); ask to open a batch first if none is loaded.
- Indexer: comments dialog (`IndexCommentDialog`) stays fully on the available screen when opened (Submit/Cancel must not sit below the visible area). Presets scroll if the list would make the dialog taller than the screen.
- Indexer: **Page → Drag fields** opens a maximised window (current page centred) to move and scale that page's field outlines as one group when a fiducial is missed (drag inside the box to move; an edge scales that axis only; a corner keeps the box aspect ratio). Apply affects overlays, clicks, the close-up, and OCR for this page visit only. Leaving the page discards it. It is not written to JSON; revisiting the page starts from the fiducial placement, or the original field positions if no fiducial was found.

## Child DOX Index

- `ui/AGENTS.md` — PyQt6 widgets, panels, and dialogs
- `util/AGENTS.md` — services, I/O, OCR, ORM matching, app state
  - `util/validation/AGENTS.md` — project and field validation
- `runtime_assistants/AGENTS.md` — external VLM assistants invoked from apps
 - `runtime_assistants/design_assistant/AGENTS.md` — Designer page analysis
  - `runtime_assistants/design_assistant/grid_assistant/AGENTS.md` — Grid Designer ROI assistant
  - `runtime_assistants/design_assistant/question_assistant/AGENTS.md` — drawn-question frame assistant
- `tests/AGENTS.md` — automated tests
  - `tests/validations/AGENTS.md` — validation pytest modules
- `USER_INSTRUCTIONS/AGENTS.md` — operator docs (templates setup, Designer, Indexer, Exporter); static HTML in `USER_INSTRUCTIONS/html/`
- `OUTPUT_FORMATS/AGENTS.md` — export compatibility reference (provider formats vs app delivery CSV); documentation only
- `EXAMPLES/AGENTS.md` — local customer sample packs; Designer JSON vs export-header checks (survey folders gitignored; `utils/` dump helpers tracked)
- `.cursor/AGENTS.md` — Cursor rules, notes, samples (non-runtime)
  - `.cursor/rules/AGENTS.md` — `.mdc` rule modules
  - `.cursor/mIsc/AGENTS.md` — misc design notes
  - `.cursor/future_plans/AGENTS.md` — draft plans
  - `.cursor/samples/AGENTS.md` — sample inputs
  - `.cursor/workspace/AGENTS.md` — session scratch (may be empty)
