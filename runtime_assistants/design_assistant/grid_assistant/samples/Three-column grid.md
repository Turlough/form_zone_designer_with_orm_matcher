# Sample: Three-column grid

Companion to [`Three-column grid.png`](Three-column%20grid.png).

## Intent

Classic Likert-style matrix: one stem question, three shared answer columns, five sub-questions as rows.

## Grid Designer / Assistant expected result

| Field | Value |
|-------|--------|
| Orientation | `horizontal` (row = RadioGroup / question; columns = answers) |
| `question_number` | `1.7` |
| `name` / `summary` | `Health and Safety` |
| `full_text` | `From a health and safety perspective, how would you rate the following on your farm?` |
| `n_rows` × `n_cols` | 5 × 3 |
| OpenCV answer rects | 15 checkboxes (5×3) |

### Column labels (answers) — 3

Do **not** include the question number:

1. `Good`
2. `Average`
3. `Poor`

### Row labels (sub-questions) — 5

Do **not** prefix with `1.7`:

1. `Livestock handling facilities`
2. `Slurry/manure storage and handling`
3. `Machinery and PTO safety`
4. `Overhead power line/electrical awareness`
5. `Child/visitor safety on the farmyard`

## Layout notes (for ROI / clustering)

- Stem (`1.7.` + `full_text`) above the matrix.
- Column headings centered above each checkbox column.
- Row labels left of each checkbox row.
- Drawn grid ROI should include: stem, column headings, row labels, and all checkboxes.
- OpenCV rects: checkboxes only (not text).

## Expansion note

Expands to five `RadioGroup`s (one per row label); each has three `RadioButton`s named Good / Average / Poor. `question_number` / stem `full_text` / `summary` belong on the grid (and may be copied to groups), never onto answer buttons.
