"""Layout helpers for RadioGrid and simple RadioGroup construction."""

from __future__ import annotations

from fields import RadioButton, RadioGroup, RadioGrid
from util.field_metadata import sanitize_column_title, truncate_summary


def _split_lines(n: int, fracs: list[float]) -> list[float]:
    if n <= 1:
        return [0.0, 1.0]
    if len(fracs) >= n - 1:
        lines = [0.0] + list(fracs[: n - 1]) + [1.0]
    else:
        lines = [i / n for i in range(n + 1)]
    return lines


def cell_rects_for_grid(grid: RadioGrid) -> list[list[tuple[int, int, int, int]]]:
    """Return [row][col] = (x, y, w, h) fiducial-relative from grid layout."""
    gx, gy, gw, gh = grid.x, grid.y, grid.width, grid.height
    n_rows = max(1, len(grid.row_labels))
    n_cols = max(1, len(grid.col_labels))
    cx = _split_lines(n_cols, grid.col_fracs)
    cy = _split_lines(n_rows, grid.row_fracs)
    out: list[list[tuple[int, int, int, int]]] = []
    for i in range(len(cy) - 1):
        row: list[tuple[int, int, int, int]] = []
        y = gy + int(cy[i] * gh)
        h = int(cy[i + 1] * gh) - int(cy[i] * gh)
        for j in range(len(cx) - 1):
            x = gx + int(cx[j] * gw)
            w = int(cx[j + 1] * gw) - int(cx[j] * gw)
            row.append((x, y, w, h))
        out.append(row)
    return out


def _meta_for_group(grid: RadioGrid, label: str, *, n_groups: int) -> dict:
    """Metadata for an expanded RadioGroup (never applied to RadioButtons)."""
    qn = (getattr(grid, "question_number", None) or "").strip()
    grid_full = (getattr(grid, "full_text", None) or "").strip()
    grid_summary = (getattr(grid, "summary", None) or "").strip()
    if n_groups == 1:
        full_text = grid_full or label
        summary = truncate_summary(grid_summary or label)
    else:
        full_text = label
        summary = truncate_summary(label)
    return {
        "question_number": qn,
        "full_text": full_text,
        "summary": summary,
        "column_title": sanitize_column_title(label),
    }


def expand_radio_grid(grid: RadioGrid) -> list[RadioGroup]:
    """Materialize a RadioGrid into RadioGroup fields for Indexer/Exporter."""
    from field_factory import default_colour_tuple_for_type

    rows = list(grid.row_labels)
    cols = list(grid.col_labels)
    cells = cell_rects_for_grid(grid)
    if not cells or not rows or not cols:
        return []
    if len(cells) != len(rows) or len(cells[0]) != len(cols):
        return []
    radio_colour = default_colour_tuple_for_type("RadioButton")
    group_colour = default_colour_tuple_for_type("RadioGroup")
    groups: list[RadioGroup] = []
    if grid.orientation == "vertical":
        n_groups = len(cols)
        for j, col_name in enumerate(cols):
            buttons: list[RadioButton] = []
            for i, row_name in enumerate(rows):
                x, y, w, h = cells[i][j]
                buttons.append(
                    RadioButton(colour=radio_colour, name=row_name, x=x, y=y, width=w, height=h)
                )
            col_height = sum(cells[k][j][3] for k in range(len(rows)))
            meta = _meta_for_group(grid, col_name, n_groups=n_groups)
            groups.append(
                RadioGroup(
                    colour=group_colour,
                    name=col_name,
                    x=cells[0][j][0],
                    y=cells[0][j][1],
                    width=cells[0][j][2],
                    height=col_height,
                    radio_buttons=buttons,
                    **meta,
                )
            )
    else:
        n_groups = len(rows)
        for i, row_name in enumerate(rows):
            buttons: list[RadioButton] = []
            for j, col_name in enumerate(cols):
                x, y, w, h = cells[i][j]
                buttons.append(
                    RadioButton(colour=radio_colour, name=col_name, x=x, y=y, width=w, height=h)
                )
            meta = _meta_for_group(grid, row_name, n_groups=n_groups)
            groups.append(
                RadioGroup(
                    colour=group_colour,
                    name=row_name,
                    x=cells[i][0][0],
                    y=cells[i][0][1],
                    width=sum(cells[i][k][2] for k in range(len(cols))),
                    height=cells[i][0][3],
                    radio_buttons=buttons,
                    **meta,
                )
            )
    return groups


def radio_group_name_from_question(question_number: str, full_text: str) -> str:
    """Group name: question stem, else question number, else RadioGroup."""
    stem = (full_text or "").strip()
    if stem:
        return stem
    qn = (question_number or "").strip()
    return qn or "RadioGroup"


def build_radio_group_from_frame(
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    options: list[tuple[str, int, int, int, int]],
    question_number: str = "",
    full_text: str = "",
) -> RadioGroup:
    """One RadioGroup from a question frame and named answer rectangles.

    Option layout may be irregular; it need not be a rectangular grid.
    Metadata is applied to the group, not the RadioButtons.
    """
    from field_factory import default_colour_tuple_for_type

    name = radio_group_name_from_question(question_number, full_text)
    radio_colour = default_colour_tuple_for_type("RadioButton")
    group_colour = default_colour_tuple_for_type("RadioGroup")
    buttons = [
        RadioButton(
            colour=radio_colour,
            name=opt_name,
            x=int(ox),
            y=int(oy),
            width=int(ow),
            height=int(oh),
        )
        for opt_name, ox, oy, ow, oh in options
    ]
    qn = (question_number or "").strip()
    stem = (full_text or "").strip()
    return RadioGroup(
        colour=group_colour,
        name=name,
        x=int(x),
        y=int(y),
        width=int(width),
        height=int(height),
        radio_buttons=buttons,
        question_number=qn,
        full_text=stem,
        summary=truncate_summary(name),
        column_title=sanitize_column_title(name),
    )


def expand_fields_for_runtime(fields: list) -> list:
    """Expand RadioGrid entries to RadioGroups; pass other fields through."""
    out: list = []
    for field in fields:
        if isinstance(field, RadioGrid):
            out.extend(expand_radio_grid(field))
        else:
            out.append(field)
    return out


def expand_fields_for_display(fields: list) -> list:
    """Expand RadioGrids for canvas/thumbnail rendering."""
    return expand_fields_for_runtime(fields)
