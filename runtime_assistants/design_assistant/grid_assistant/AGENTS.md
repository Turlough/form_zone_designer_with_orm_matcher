# Grid assistant

## Purpose

Fill Grid Designer metadata and row/column labels from a drawn ROI crop plus OpenCV answer rectangles (local clustering + external VLM).

## Ownership

- `geometry.py`, `schema.py`, `prompt.py`, `client.py`, `__init__.py` (`analyse_grid`)
- Intent samples: `samples/*.png` with companion `samples/*.md`
- Plan: `PLAN.md`
- Invoked from `ui/grid_designer.py` → Assistant button

## Local Contracts

### Inputs

- Page PIL image (template resolution)
- Grid ROI fiducial-relative `(x, y, w, h)`
- Fiducial bbox `(top_left, bottom_right)` when present
- OpenCV rectangles (page-absolute); require ≥2 with centers inside ROI
- User orientation: `horizontal` | `vertical`

### Outputs

- `AnalyseGridResult`: `question_number`, `summary`/`name`, `full_text`, `row_labels`, `col_labels`, `n_rows`/`n_cols`, `row_fracs`/`col_fracs`, `grid_rect_fiducial`, `warnings`
- Autofill overwrites Grid Designer fields on success
- After analysis, **shrink** `grid_rect` to tightly frame answer boxes (stem/headings excluded); outer margins match each outer button’s inner gap to the first/last split — see `samples/framed three column grid.md`
- Cluster counts win over VLM label counts (pad/truncate with warnings)
- Single-question grids: if orientation is `vertical` and `n_cols == 1`, or `horizontal` and `n_rows == 1`, a missing or padded (`Column N` / `Row N`) question-axis label is replaced with `full_text`
- `question_number` never appears in answer / `RadioButton` labels

### Field metadata (persisted on RadioGrid)

| Key | Max | Use |
|-----|-----|-----|
| question_number | — | Printed number (e.g. `1.7`) |
| full_text | — | Full stem / question text |
| summary | 50 chars | Overlay when Field names enabled |
| name / column_title | — | Short title; row/col labels may be long |
| row_labels / col_labels | — | No 50-char cap |

### VLM

- Default model: `gemini-2.5-flash` (`DESIGN_ASSISTANT_MODEL` override)
- Upload ROI crop only; candidate rects in crop-absolute coords
- API keys: `GOOGLE_API_KEY` or `GEMINI_API_KEY`
- No PyQt imports in this package

## Work Guidance

- Hybrid: local CV for shape/splits/tight frame; VLM for text (may use a larger analysis ROI than the stored grid)
- Advise (tooltip) that ROI should include question + labels; do not require OpenCV boxes around text
- Warn when orientation toggle disagrees with clustered layout or VLM `orientation_observed`

## Verification

- `tests/test_grid_assistant_geometry.py` — clustering, schema parse, question-axis label fill (no live API)
- `tests/test_radio_grid_layout.py` — long labels, `question_number` on groups not buttons

## Child DOX Index
