# Design assistant

## Purpose

Analyse a Designer template page image and propose backward-compatible `json/N.json` field definitions with upgraded question metadata (`full_text`, `summary`, `column_title`) and answer zone geometry.

## Ownership

- `client.py`, `prompt.py`, `schema.py`, `match.py`, `convert.py`
- Invoked from `app_designer.py` → Assistant → Analyse

## Local Contracts

### Inputs

- Current page PIL image (template resolution)
- Optional fiducial bbox `(top_left, bottom_right)` — output coords fiducial-relative when present
- Optional OpenCV rectangle list (page-absolute) for geometry matching

### Outputs

- `PageAnalysisResult`: `fields: list[dict]`, `warnings: list[str]`, `grid_suggestions: list[dict]`
- Persisted JSON: flat array only; analysis-only keys stripped

### Field metadata

| Key | Max | Use |
|-----|-----|-----|
| full_text | — | Full question text |
| summary | 50 chars | Designer overlay when Field names enabled |
| column_title | — | CSV column header |
| name | — | Legacy identifier; keep populated for Indexer/Exporter |

Read fallbacks: `summary ← name`, `column_title ← name`.

### VLM (external API)

- Default model: `gemini-2.5-flash` (`DESIGN_ASSISTANT_MODEL` override)
- Prompt in `prompt.py`: role, schema, allowed `_type`s, metadata rules, candidate `rect_id` list
- Prefer page-absolute coords or `rect_id` references; convert to fiducial-relative locally
- Structured JSON response; validate with `schema.py` before return

### Matching

- OpenCV supplies candidate boxes; VLM associates questions → `rect_id` (or coarse hint)
- Unmatched questions → warning; Designer preview decides apply policy

## Work Guidance

- Hybrid remote VLM + local CV; do not trust VLM pixel boxes alone
- Downscale upload image; one page per request; retry once on bad JSON
- Radio groups: nested `radio_buttons` matching `Field.from_dict` shape
- Grid opportunities: `grid_suggestions` only; creation stays in GridDesigner

## Verification

- `tests/test_design_assistant_schema.py` — old JSON loads, upgrade round-trip
- `tests/test_design_assistant_match.py` — rect association with synthetic data

## Child DOX Index
