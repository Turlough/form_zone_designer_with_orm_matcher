# Project-Level Validations

## Description

Project-level validations are business rules that apply to specific projects only, unlike global validations (e.g. `contains_text`, `is_integer`) which apply by field type across all projects. Project validations typically involve multiple fields and may span pages. Examples:

- **max_tickboxes**: Of a set of tickboxes, no more than N may be ticked.
- **mutually_exclusive**: If a designated tickbox (e.g. "None of the above") is ticked, none of the other specified tickboxes must be ticked.

When a project validation fails, the result is appended as a QC comment on the invalidated field(s), so QC staff can review and triage using the existing "Review batch comments" workflow.

## High-Level Objectives

1. **Config-driven rules**: Each project defines which validations apply and with what parameters (field names, max count, etc.) via text-based config in its project folder.
2. **Strategy + Registry pattern**: Available validation functions live in `util/project_validations.py`; config references them by name and supplies fields/params.
3. **Comment integration**: Validation failures become `Comment(page, field, message)` entries stored in the CSV Comments column—same format and workflow as manual QC comments.
4. **QC menu actions**: Add "Validate document" and "Validate batch" to the QC menu; these run project validations and append failures as comments.
5. **Cross-page support**: Validations may use field values from any page in the document.

---

## Implementation Plan

### Phase 1: Core validation infrastructure

**1.1 Create `util/project_validations.py`**

- Define a `ProjectValidationStrategy` protocol/interface:
  - Input: `field_values: dict[str, Any]`, `field_names: list[str]`, `params: dict`, `field_to_page: dict[str, int]` (optional; for page attribution)
  - Output: `list[tuple[int, str, str]]` — `(page, field_name, message)` for each invalidated field
- Implement at least two strategies:
  - `max_tickboxes`: count ticked fields in `field_names`; if > `params["max"]`, return invalidations for the last ticked field.
  - `mutually_exclusive`: if `params["exclusive_field"]` is ticked and any of the other `field_names` are ticked, invalidate the exclusive field with message like "None of the above is ticked but some of the above are ticked" (or equivalent).
- Registry: `PROJECT_VALIDATION_REGISTRY: dict[str, Callable]` mapping strategy names to functions.

**1.2 Extend `project_config.json` schema**

- Add optional `validations` array:
  ```json
  "validations": [
    {
      "strategy": "max_tickboxes",
      "field_names": ["q1_a", "q1_b", "q1_c", "q1_d"],
      "params": {"max": 3}
    },
    {
      "strategy": "mutually_exclusive",
      "field_names": ["none_of_above", "option_a", "option_b"],
      "params": {"exclusive_field": "none_of_above"}
    }
  ]
  ```

**1.3 Field-to-page mapping**

- Build a mapping from field name to page (1-based) from JSON descriptors: `util/designer_persistence.load_page_fields` or CSVManager’s `_get_field_names_from_json` logic. Either add a helper or extend CSVManager to expose `field_to_page: dict[str, int]` (or similar) when loading JSON.

### Phase 2: Validation runner and integration

**2.1 Validation runner**

- Create a function (e.g. in `util/project_validations.py` or a small module) that:
  - Takes: `project_config`, `field_values` (from CSV row), `field_to_page`
  - Iterates over `project_config.get("validations", [])`
  - For each rule, calls the registered strategy with `field_values`, `field_names`, `params`, `field_to_page`
  - Collects all `(page, field, message)` tuples
  - Returns `list[tuple[int, str, str]]` — no duplicates

**2.2 Merge with existing comments**

- When appending validation failures: load existing `Comments` from the CSV row, add new `Comment` objects for each failure, merge (avoid duplicates by identity), then `to_csv_string()` and `set_field_value(row_idx, "Comments", new_str)`.

### Phase 3: QC menu and UI actions

**3.1 Add QC menu items**

- In `ui/index_menu_bar.py`, `_init_qc_menu()`:
  - Add "Validate document" action → emit `validate_document_requested`
  - Add "Validate batch" action → emit `validate_batch_requested`

**3.2 Handle signals in Indexer**

- In `app_indexer.py`:
  - Connect `validate_document_requested` → `_on_validate_document_requested`
  - Connect `validate_batch_requested` → `_on_validate_batch_requested`
- **Validate document**: get current row index, `field_values` from CSVManager for that row, run validation runner, merge failures into Comments, save CSV.
- **Validate batch**: loop over all document rows, same for each.

**3.3 User feedback**

- Show a brief message (e.g. QMessageBox) after run: "Validated N documents. X validation failures added as comments." (or "No validation failures found.")

### Phase 4: Edge cases and polish

**4.1 Missing config**

- If `project_config.json` has no `validations` key or empty array: show message "No project validations configured for this project."

**4.2 Unknown strategy / invalid config**

- Log and skip invalid rules; report which rules failed to load.

**4.3 Field value normalization**

- Ensure tickbox values are normalized consistently (e.g. `"Ticked"` vs `True` vs non-empty string) when building `field_values` from CSV for validation. CSV columns may store strings; strategies may expect boolean-like semantics.

**4.4 Testing**

- Unit tests for `max_tickboxes` and `mutually_exclusive` strategies.
- Integration test: run validation on a fixture CSV with known failures, assert expected comments added.

---

## Dependencies / Pre-existing pieces

- `util/index_comments.py`: `Comment`, `Comments`, `from_string`, `to_csv_string` — reuse for persistence.
- `ui/qc_comment_dialog.py` and "Review batch comments" — no changes needed; validation failures appear as comments.
- `project_config.json` / `_load_project_config()` — already loaded in Indexer.
- CSVManager: `get_field_value`, `set_field_value`, `save_csv` — used for reading/writing Comments.

---

## Out of Scope (for now)

- Real-time validation during indexing (e.g. red overlay for project validation failures); only batch/document validation.
- Validation rules embedded in JSON field descriptors (option 3a).
- Separate `validations.json` file; config lives in `project_config.json` unless the project grows large.
