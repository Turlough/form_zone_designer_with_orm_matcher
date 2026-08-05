# Sample: Framed three-column grid

Companion to [`framed three column grid.png`](framed%20three%20column%20grid.png).

## Intent

Shows the **post-Assistant geometry** for a horizontal 5×3 matrix: the green grid rectangle and internal splits tightly frame the answer checkboxes only. Column heading text (`Good` / `Average` / `Poor`) sits **outside** the grid rectangle, above it.

This is the target framing behaviour when the user’s initial selection ROI still includes the question stem and/or column headings (common when drawing a large rectangle for the VLM). After Assistant runs, the stored `grid_rect` and row/col splits should look like this overlay—not a tall first row that absorbs the stem area.

## Framing contract (Assistant geometry)

| Rule | Expected behaviour |
|------|--------------------|
| Top of `grid_rect` | Just above the top edge of the first-row answer rectangles |
| Bottom of `grid_rect` | Just below the bottom edge of the last-row answer rectangles |
| Left / right of `grid_rect` | Neatly outside the outer checkboxes (same spirit as vertical margins) |
| Vertical margin per cell | Match the gap on the other side of each radio button so each button is centred in its cell |
| Internal horizontal lines | Midway between adjacent rows of checkboxes (already working well) |
| Internal vertical lines | Midway between adjacent columns of checkboxes |
| Text outside the grid | Stem, question number, column headings, and row labels may be inside the **analysis ROI** for the VLM, but must **not** remain inside the final `grid_rect` |

## What the image shows

- **Orientation:** `horizontal` (columns = answer options).
- **Shape:** 5 rows × 3 columns (15 checkboxes).
- **Column headings (outside grid):** Good, Average, Poor — centred above each column, above the dashed green outer rect.
- **Outer boundary:** Dashed green rectangle hugging the checkbox matrix only.
- **Cell splits:** Solid green lines; each checkbox centred in its cell with a small, even white margin above and below the box.

## Relation to other samples

- Label / metadata intent for this form is the same as [`Three-column grid.md`](Three-column%20grid.md).
- This file is specifically about **tightening `grid_rect` + splits around OpenCV answer rectangles** after analysis, not about reading text.

## Analysis vs stored geometry

1. User may draw a large ROI that includes stem + headings + checkboxes (needed so the Assistant can read labels).
2. Local clustering uses OpenCV answer rects inside that ROI.
3. Assistant then **shrinks** the Grid Designer rectangle to the checkbox cluster with balanced margins (as in this image), and sets `row_fracs` / `col_fracs` so each button is neatly framed.
