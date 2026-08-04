# Qualtrics response export format

Reference for [Qualtrics XM](https://www.qualtrics.com/) survey response exports. Useful when mapping this app’s delivery CSV to customer systems that ingest Qualtrics data.

## File formats

Qualtrics can export response data as **CSV**, **TSV**, **SPSS**, **JSON**, **NDJSON**, or **XML**. Exports are typically **one row per respondent**, with metadata columns (e.g. response ID, status, timestamps) plus one or more columns per question.

Configure format and options each time you download from **Data & Analysis**, or via the [export API / automations](https://www.qualtrics.com/support/survey-platform/data-and-analysis-module/data/download-data/export-options/).

## Export options that matter

| Option | Effect |
|--------|--------|
| **Export values** | Cell contains the numeric **recode value** for the selected choice |
| **Export labels** | Cell contains the **answer choice text** |
| **Split multi-value fields into columns** | Each selectable option gets its own column (see checkboxes below) |
| **Recode seen but unanswered multi-value fields as 0** | Only with split columns; unchecked options shown to the respondent become `0` instead of blank |
| **Recode seen but unanswered questions as -99** | Single-value questions left blank become `-99` |

API equivalent: `breakoutSets: true` splits multi-value fields; `breakoutSets: false` keeps a single comma-separated column. `useLabels: true` exports labels instead of recode values.

## Single-answer multiple choice (radio)

One column per question.

- **Export values:** one recode number per row (e.g. `3`)
- **Export labels:** one answer string per row (e.g. `Strongly agree`)

## Multi-answer multiple choice (checkboxes)

“Select all that apply” questions have **two export shapes**, controlled by **Split multi-value fields into columns** ([Multiple Choice — Downloaded Data Format](https://www.qualtrics.com/support/survey-platform/survey-module/editing-questions/question-types-guide/standard-content/multiple-choice/#DownloadedDataFormat)).

### Single column (split off)

- One column for the whole question
- Selected options are **comma-separated** in one cell
- With **Export values:** e.g. `1,3,5`
- With **Export labels:** e.g. `Option A,Option C,Option E`
- Unselected options are omitted; empty cell if nothing selected

### Split columns (split on)

- One column **per answer choice**
- Column names are usually `{export_tag}_{recode_value}` (e.g. `Q5_1`, `Q5_2`, `Q5_3`)
- Selected = **`1`**; not selected = **blank** (or **`0`** if “recode seen but unanswered multi-value fields as 0” is enabled)
- Custom recode weights on choices appear in **column names**, not in cell values; cells remain `1` / blank / `0`

The same split option applies to other multi-select types (e.g. **matrix multiple answer**).

## Mapping checklist

When importing Qualtrics exports elsewhere:

1. Confirm **split vs single-column** mode for checkbox questions
2. Confirm **values vs labels** for single-answer questions
3. Treat blank split-column cells as “not selected” unless `0` recoding was enabled
4. Do not assume comma-separated and wide binary formats are interchangeable without transformation
