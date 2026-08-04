# App export format

How this suite captures and delivers indexed form data, with notes on alignment with [Qualtrics export formats](Qualtrics.md).

Implementation: **Indexer** (`app_indexer.py`) writes batch CSV during data entry; **Exporter** (`app_exporter.py`) **Deliver** prepares customer-facing files. Field layout comes from project `json/` descriptors; column headings from `util/field_metadata.column_header` (`column_title`, else `name`).

## Pipeline

1. **Indexer** — operator indexes scanned forms; each batch is a CSV beside its TIFF/PDF images.
2. **Validate** (Exporter) — headers are checked against the project JSON field list.
3. **Deliver** (Exporter) — TIFFs become PDFs; clean and exception rows are written to separate CSVs under `_deliveries/<job_name>/`.

## Batch CSV (Indexer output)

One row per scanned document (multipage TIFF/PDF). Headers are created or normalised on load (`util/csv_manager.py`):

| Column | Content |
|--------|---------|
| **File** | Relative path to the source document (legacy headers `tiff_path`, `path`, `document_path` are accepted) |
| *field columns* | One column per field in JSON page order (first occurrence wins if names repeat) |
| **Comments** | QC comments (structured page+field keys) |

Encoding: UTF-8. Python `csv` module handles quoting on save.

### Field types and cell values

| Field type | Columns | Checked / selected | Unchecked / empty |
|------------|---------|------------------|-------------------|
| **Tickbox** | One per tickbox | `checked_value` (default `"Ticked"`) | Empty string |
| **SignatureField** | One | `"Signed"` (default) | Empty |
| **RadioGroup** | One per group | Selected **radio button name** (label) | Empty |
| **NumericRadioGroup** | One per group | Selected button name (treated as numeric on delivery) | Empty |
| **TextField** and subclasses | One per field | Entered text | Empty |

**Multi-option checkboxes (“select all that apply”):** each option is a separate **Tickbox** field with its own column. This matches Qualtrics **split multi-value fields into columns**, but differs in cell encoding (see comparison below).

**Radio groups:** one column with the chosen option’s **label**, similar to Qualtrics **Export labels** for single-answer multiple choice—not recode numbers.

Indexer reload accepts several truthy spellings for tickboxes when reading existing CSV (`ticked`, `true`, `1`, `yes`, `checked`, `tick`, or a match to `checked_value`).

## Delivery export (Exporter Deliver)

Output directory: `<batch_root>/_deliveries/<job_name>/`

| Artifact | Purpose |
|----------|---------|
| `<job_name>.csv` | Rows with **no** Comments |
| `<job_name>_exceptions.csv` | Rows with one or more Comments |
| `PDF/` | Multipage PDFs named `0001.pdf`, `0002.pdf`, … |

Both CSVs share the same headers as the batch import files. The **File** column is rewritten to a relative path under `PDF/` (e.g. `PDF/0001.pdf`). Source TIFFs are never modified; PDFs are copies/conversions.

### Cell formatting rules (`app_exporter._format_cell`)

| Field category | Quoting | Empty cell |
|----------------|---------|------------|
| **File**, **Comments** | Double-quoted if non-empty | Empty |
| **IntegerField**, **DecimalField**, **NumericRadioGroup** | No quotes | Empty (not `0`) |
| All other fields (tickboxes, text, radio labels, etc.) | Double-quoted if non-empty | Empty |

Tickboxes remain **quoted text** (`"Ticked"`) in delivery CSV, not bare `1`.

## Comparison with Qualtrics

| Aspect | This app | Qualtrics |
|--------|----------|-----------|
| Checkbox layout | One column per option (wide) | Wide **or** single comma-separated column (export option) |
| Checkbox selected value | Label string (`Ticked`, or custom `checked_value`) | `1` in split mode; recode list in single-column mode |
| Checkbox not selected | Blank | Blank, or `0` if recode-unanswered enabled |
| Single-choice (radio) | One column; **label** of selected button | One column; **label** or **recode value** (export option) |
| Row grain | One row per scanned form | One row per survey response |
| Document reference | **File** → PDF path in delivery | N/A (online survey) |
| QC / exceptions | **Comments** column; commented rows → `_exceptions.csv` | Separate workflows / flags |

### Transforming app export → Qualtrics-like wide binary

If a downstream system expects Qualtrics split-column semantics:

- Map non-empty tickbox cells to `1`, empty to blank or `0`
- Optionally rename columns to `{questionId}_{recode}` if the customer supplies a mapping from field names to Qualtrics export tags

### Transforming app export → Qualtrics-like single column

Group tickbox columns that belong to one “select all that apply” question and join selected **labels** or **names** with commas. Radio groups already resemble Qualtrics **Export labels** single-column format.

## Related docs

- Design notes: `.cursor/mIsc/app_exporter.md`
- Indexer CSV behaviour: `.cursor/mIsc/FIELDINDEXER.md`
- Operator steps: `USER_INSTRUCTIONS/` (Exporter section when populated)
