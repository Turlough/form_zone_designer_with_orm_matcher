# Question assistant

## Purpose

Fill multi-answer question metadata when the Designer draws a frame around detected answer rectangles: shared `question_number` / `full_text`, per-answer type and name, batch field creation on Submit.

## Ownership

- `geometry.py`, `schema.py`, `prompt.py`, `client.py`, `__init__.py` (`analyse_question`)
- Invoked from `RectangleSelectedDialog` → **Assistant** (batch mode when drawn frame has ≥1 inner rect)

## Local Contracts

### Inputs

- Page PIL image (template resolution)
- Question ROI fiducial-relative `(x, y, w, h)` — user-drawn frame
- Fiducial bbox `(top_left, bottom_right)` when present
- Inner answer rectangles fiducial-relative (from Designer detection inside the frame)
- Optional export-format column slice for this page (when active descriptor exists)

### Outputs

- `AnalyseQuestionResult`: `question_number`, `full_text`, `fields[]` (`field_type`, `name`, `summary`, `column_title`), `warnings`
- Autofill overwrites batch dialog entries; **Submit** creates one persisted field per inner rectangle; **Radio group** on the same dialog creates one `RadioGroup` from the frame (not via this assistant)

### Field types

- Allowed: Tickbox, TextField, IntegerField, DecimalField, DateField, etc.
- Not allowed: RadioGroup, RadioButton, RadioGrid, NumericRadioGroup (Designer **Radio group** for one exclusive question; Grid Designer for matrices)

### VLM

- Default model: `gemini-2.5-flash` (`DESIGN_ASSISTANT_MODEL` override)
- Upload question ROI crop only; candidate rects in crop-absolute coords
- API keys: `GOOGLE_API_KEY` or `GEMINI_API_KEY`
- No PyQt imports in this package

## Work Guidance

- Hybrid: local CV for rect count/order; VLM for question stem and option labels
- Designer sorts inner answer rects into reading order (top-to-bottom, left-to-right) before batch dialog rows / Submit so Option N and Assistant proposals align with on-page geometry
- Assume Tickbox when in doubt; wide boxes → TextField heuristic as fallback when VLM returns no fields
- Rect count wins over VLM field count (pad/truncate with warnings)

## Verification

- `tests/test_question_assistant.py` — geometry, schema parse (no live API)

## Child DOX Index
