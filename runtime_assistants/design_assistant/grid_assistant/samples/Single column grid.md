# Sample: Single column grid

Companion to [`Single column grid.png`](Single%20column%20grid.png).

## Intent

Single-column radio grid used instead of a Radio Group (larger Indexer target). Vertical list of mutually exclusive options under one question.

## Grid Designer / Assistant expected result

| Field | Value |
|-------|--------|
| Orientation | `vertical` (column = RadioGroup / question; rows = answers) |
| `question_number` | `1.2` |
| `name` / `summary` | Short overlay label, e.g. `Age group` (exact short form flexible) |
| `full_text` | `What age group do you fall into?` |
| `n_rows` × `n_cols` | 5 × 1 |
| OpenCV answer rects | 5 checkboxes (one column) |

### Column labels (questions) — 1

Do **not** prefix with `1.2`. The single column heading is the full question text (same idea as `full_text`):

1. `What age group do you fall into?`

### Row labels (answers) — 5

Do **not** include the question number:

1. `Under 35`
2. `35 to 44`
3. `45 to 54`
4. `55 to 64`
5. `Over 65`

## Layout notes (for ROI / clustering)

- Question number and stem appear above the options.
- Answer text sits to the right of each checkbox.
- Drawn grid ROI should include: stem, checkboxes, and answer labels.
- OpenCV rects: checkboxes only (not text).

## Expansion note

Expands to one `RadioGroup` named with the column label; five `RadioButton`s named with the row labels. `question_number` / `full_text` / `summary` live on the group (and grid), not on the buttons.
