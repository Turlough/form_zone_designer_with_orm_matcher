"""Local geometry for Grid Assistant: ROI filtering and row/col clustering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

Rect = tuple[int, int, int, int]  # x, y, w, h


@dataclass
class ClusterResult:
    n_rows: int
    n_cols: int
    row_fracs: list[float]
    col_fracs: list[float]
    rects_in_roi: list[Rect] = field(default_factory=list)
    # Page-absolute grid rect tightly framing answer boxes (may shrink user ROI).
    framed_rect_page: Rect | None = None
    orientation_hint: str | None = None  # "horizontal" | "vertical" | None
    warnings: list[str] = field(default_factory=list)


def fiducial_top_left(fiducial_bbox: tuple | None) -> tuple[int, int]:
    if not fiducial_bbox:
        return (0, 0)
    tl = fiducial_bbox[0]
    return (int(tl[0]), int(tl[1]))


def fiducial_rect_to_page(
    rect: Rect,
    fiducial_bbox: tuple | None,
) -> Rect:
    """Convert fiducial-relative (x, y, w, h) to page-absolute."""
    ox, oy = fiducial_top_left(fiducial_bbox)
    x, y, w, h = rect
    return (x + ox, y + oy, w, h)


def page_rect_to_fiducial(
    rect: Rect,
    fiducial_bbox: tuple | None,
) -> Rect:
    """Convert page-absolute (x, y, w, h) to fiducial-relative."""
    ox, oy = fiducial_top_left(fiducial_bbox)
    x, y, w, h = rect
    return (x - ox, y - oy, w, h)


def _center(r: Rect) -> tuple[float, float]:
    x, y, w, h = r
    return (x + w / 2.0, y + h / 2.0)


def _intersects(a: Rect, b: Rect) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def filter_rects_in_roi(
    cv_rects: Sequence[Rect],
    roi_page: Rect,
) -> list[Rect]:
    """Return CV rects whose centers lie inside the page-absolute ROI."""
    rx, ry, rw, rh = roi_page
    out: list[Rect] = []
    for r in cv_rects:
        cx, cy = _center(r)
        if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
            out.append(tuple(int(v) for v in r))  # type: ignore[misc]
    return out


def _cluster_1d(values: list[float], min_gap: float) -> list[list[float]]:
    """Group sorted values into clusters separated by gaps >= min_gap."""
    if not values:
        return []
    ordered = sorted(values)
    clusters: list[list[float]] = [[ordered[0]]]
    for v in ordered[1:]:
        if v - clusters[-1][-1] >= min_gap:
            clusters.append([v])
        else:
            clusters[-1].append(v)
    return clusters


def _fracs_from_centers(
    centers: list[float],
    origin: float,
    span: float,
    n: int,
) -> list[float]:
    """Internal division lines (n-1 fracs) from cluster mean centers."""
    if n <= 1 or span <= 0:
        return []
    means = sorted(sum(c) / len(c) for c in _cluster_1d(centers, min_gap=1.0)[:n])
    # Re-cluster with adaptive gap if needed
    if len(means) != n:
        # Use equal-ish quantiles of sorted unique-ish centers
        ordered = sorted(centers)
        means = []
        for i in range(n):
            lo = int(round(i * len(ordered) / n))
            hi = int(round((i + 1) * len(ordered) / n))
            chunk = ordered[lo:hi] or ordered[lo : lo + 1]
            means.append(sum(chunk) / len(chunk))
        means = sorted(means)
    fracs: list[float] = []
    for i in range(n - 1):
        mid = (means[i] + means[i + 1]) / 2.0
        f = (mid - origin) / span
        f = min(max(f, 0.05), 0.95)
        if fracs and f <= fracs[-1] + 0.05:
            f = fracs[-1] + 0.05
        fracs.append(min(f, 0.95))
    # Ensure strictly increasing and within bounds
    cleaned: list[float] = []
    for i, f in enumerate(fracs):
        lo = (cleaned[-1] + 0.05) if cleaned else 0.05
        hi = 0.95 - 0.05 * (len(fracs) - 1 - i)
        cleaned.append(min(max(f, lo), hi))
    return cleaned


def _count_clusters(values: list[float], typical_size: float) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return 1
    gap = max(typical_size * 0.6, 4.0)
    return len(_cluster_1d(values, min_gap=gap))


def _assign_to_bins(values: list[float], n: int, typical_size: float) -> list[int]:
    """Assign each value to bin 0..n-1 by clustering then nearest mean."""
    if n <= 1 or not values:
        return [0] * len(values)
    gap = max(typical_size * 0.6, 4.0)
    clusters = _cluster_1d(values, min_gap=gap)
    means = sorted(sum(c) / len(c) for c in clusters)
    if len(means) != n:
        ordered = sorted(values)
        means = []
        for i in range(n):
            lo = int(round(i * len(ordered) / n))
            hi = int(round((i + 1) * len(ordered) / n))
            chunk = ordered[lo:hi] or [ordered[min(lo, len(ordered) - 1)]]
            means.append(sum(chunk) / len(chunk))
        means = sorted(means)
    out: list[int] = []
    for v in values:
        best_i = min(range(len(means)), key=lambda i: abs(means[i] - v))
        out.append(min(best_i, n - 1))
    return out


def frame_answer_rects(
    rects: Sequence[Rect],
    n_rows: int,
    n_cols: int,
) -> tuple[Rect, list[float], list[float]]:
    """Shrink-wrap a grid rect around answer boxes with balanced cell margins.

    Outer top/bottom (and left/right) margins match the gap from each outer
    button to the adjacent internal split, so each radio is centred in its cell.
    See ``samples/framed three column grid.md``.
    """
    rects = [tuple(int(v) for v in r) for r in rects]  # type: ignore[misc]
    n_rows = max(1, n_rows)
    n_cols = max(1, n_cols)
    if not rects:
        return (0, 0, 10, 10), [], []

    widths = [r[2] for r in rects]
    heights = [r[3] for r in rects]
    med_w = float(sorted(widths)[len(widths) // 2])
    med_h = float(sorted(heights)[len(heights) // 2])
    xs = [_center(r)[0] for r in rects]
    ys = [_center(r)[1] for r in rects]
    row_ids = _assign_to_bins(ys, n_rows, med_h)
    col_ids = _assign_to_bins(xs, n_cols, med_w)

    row_tops = [0.0] * n_rows
    row_bottoms = [0.0] * n_rows
    row_counts = [0] * n_rows
    for r, rid in zip(rects, row_ids):
        x, y, w, h = r
        if row_counts[rid] == 0:
            row_tops[rid] = float(y)
            row_bottoms[rid] = float(y + h)
        else:
            row_tops[rid] = min(row_tops[rid], float(y))
            row_bottoms[rid] = max(row_bottoms[rid], float(y + h))
        row_counts[rid] += 1

    col_lefts = [0.0] * n_cols
    col_rights = [0.0] * n_cols
    col_counts = [0] * n_cols
    for r, cid in zip(rects, col_ids):
        x, y, w, h = r
        if col_counts[cid] == 0:
            col_lefts[cid] = float(x)
            col_rights[cid] = float(x + w)
        else:
            col_lefts[cid] = min(col_lefts[cid], float(x))
            col_rights[cid] = max(col_rights[cid], float(x + w))
        col_counts[cid] += 1

    # Fill empty bins from neighbours / union
    for i in range(n_rows):
        if row_counts[i] == 0:
            row_tops[i] = min(r[1] for r in rects)
            row_bottoms[i] = max(r[1] + r[3] for r in rects)
    for j in range(n_cols):
        if col_counts[j] == 0:
            col_lefts[j] = min(r[0] for r in rects)
            col_rights[j] = max(r[0] + r[2] for r in rects)

    # Internal splits at midpoints between adjacent bands
    y_splits: list[float] = []
    for i in range(n_rows - 1):
        y_splits.append((row_bottoms[i] + row_tops[i + 1]) / 2.0)
    x_splits: list[float] = []
    for j in range(n_cols - 1):
        x_splits.append((col_rights[j] + col_lefts[j + 1]) / 2.0)

    # Outer margins mirror inner margin of the outer cells
    if n_rows >= 2:
        margin_top = max(1.0, y_splits[0] - row_bottoms[0])
        margin_bottom = max(1.0, row_tops[-1] - y_splits[-1])
    else:
        margin_top = margin_bottom = max(2.0, med_h * 0.35)
    if n_cols >= 2:
        margin_left = max(1.0, x_splits[0] - col_rights[0])
        margin_right = max(1.0, col_lefts[-1] - x_splits[-1])
    else:
        margin_left = margin_right = max(2.0, med_w * 0.35)

    # If only one axis has splits, reuse that margin on the other for balance
    if n_rows >= 2 and n_cols == 1:
        m = (margin_top + margin_bottom) / 2.0
        margin_left = margin_right = max(margin_left, m)
    if n_cols >= 2 and n_rows == 1:
        m = (margin_left + margin_right) / 2.0
        margin_top = margin_bottom = max(margin_top, m)

    grid_top = row_tops[0] - margin_top
    grid_bottom = row_bottoms[-1] + margin_bottom
    grid_left = col_lefts[0] - margin_left
    grid_right = col_rights[-1] + margin_right

    gx = int(round(grid_left))
    gy = int(round(grid_top))
    gw = max(1, int(round(grid_right - grid_left)))
    gh = max(1, int(round(grid_bottom - grid_top)))
    framed = (gx, gy, gw, gh)

    row_fracs = [
        min(max((s - grid_top) / gh, 0.05), 0.95) for s in y_splits
    ] if gh > 0 else []
    col_fracs = [
        min(max((s - grid_left) / gw, 0.05), 0.95) for s in x_splits
    ] if gw > 0 else []

    # Enforce strictly increasing fracs
    def _clean(fracs: list[float]) -> list[float]:
        cleaned: list[float] = []
        for i, f in enumerate(fracs):
            lo = (cleaned[-1] + 0.02) if cleaned else 0.02
            hi = 0.98 - 0.02 * (len(fracs) - 1 - i)
            cleaned.append(min(max(f, lo), hi))
        return cleaned

    return framed, _clean(row_fracs), _clean(col_fracs)


def cluster_grid_rects(
    rects_in_roi: Sequence[Rect],
    roi_page: Rect,
    *,
    user_orientation: str,
) -> ClusterResult:
    """Infer n_rows, n_cols, tight frame, and split fractions from answer rectangles.

    ``roi_page`` is the user analysis ROI (may include stem/headings); the returned
    ``framed_rect_page`` hugs answer boxes only.
    """
    del roi_page  # analysis ROI; framing uses answer rects only
    warnings: list[str] = []
    rects = [tuple(int(v) for v in r) for r in rects_in_roi]  # type: ignore[misc]
    if len(rects) < 2:
        return ClusterResult(
            n_rows=1,
            n_cols=1,
            row_fracs=[],
            col_fracs=[],
            rects_in_roi=rects,
            warnings=["Need at least two answer rectangles inside the grid ROI."],
        )

    xs = [_center(r)[0] for r in rects]
    ys = [_center(r)[1] for r in rects]
    widths = [r[2] for r in rects]
    heights = [r[3] for r in rects]
    med_w = sorted(widths)[len(widths) // 2]
    med_h = sorted(heights)[len(heights) // 2]

    n_cols = max(1, _count_clusters(xs, float(med_w)))
    n_rows = max(1, _count_clusters(ys, float(med_h)))

    # Sanity: product should be close to rect count
    product = n_rows * n_cols
    if product != len(rects) and len(rects) >= 2:
        # Try factors of len(rects) closest to current estimate
        best = (n_rows, n_cols)
        best_err = abs(product - len(rects))
        for r in range(1, len(rects) + 1):
            if len(rects) % r != 0:
                continue
            c = len(rects) // r
            err = abs(r - n_rows) + abs(c - n_cols)
            if err < best_err or (err == best_err and abs(r * c - len(rects)) < best_err):
                best = (r, c)
                best_err = err
        if best[0] * best[1] == len(rects):
            if best != (n_rows, n_cols):
                warnings.append(
                    f"Adjusted grid shape from {n_rows}×{n_cols} to {best[0]}×{best[1]} "
                    f"to match {len(rects)} rectangles."
                )
            n_rows, n_cols = best

    framed, row_fracs, col_fracs = frame_answer_rects(rects, n_rows, n_cols)

    # Orientation hint from aspect of the checkbox matrix
    orientation_hint: str | None = None
    if n_cols == 1 and n_rows >= 2:
        orientation_hint = "vertical"
    elif n_rows == 1 and n_cols >= 2:
        orientation_hint = "horizontal"
    elif n_cols >= 2 and n_rows >= 2:
        orientation_hint = "horizontal"  # matrix: row = question is the usual case

    user = (user_orientation or "horizontal").strip().lower()
    if orientation_hint and orientation_hint != user:
        # Single-column stack strongly suggests vertical
        if n_cols == 1 and n_rows >= 2 and user == "horizontal":
            warnings.append(
                "Answer boxes look like a single column (vertical orientation), "
                f"but orientation is set to {user!r}."
            )
        elif n_rows == 1 and n_cols >= 2 and user == "vertical":
            warnings.append(
                "Answer boxes look like a single row (horizontal orientation), "
                f"but orientation is set to {user!r}."
            )

    return ClusterResult(
        n_rows=n_rows,
        n_cols=n_cols,
        row_fracs=row_fracs,
        col_fracs=col_fracs,
        rects_in_roi=rects,
        framed_rect_page=framed,
        orientation_hint=orientation_hint,
        warnings=warnings,
    )


def align_labels_to_counts(
    row_labels: list[str],
    col_labels: list[str],
    n_rows: int,
    n_cols: int,
) -> tuple[list[str], list[str], list[str]]:
    """Pad/truncate label lists to cluster counts; return labels + warnings."""
    warnings: list[str] = []
    rows = [str(x).strip() for x in row_labels if str(x).strip()]
    cols = [str(x).strip() for x in col_labels if str(x).strip()]
    if len(rows) > n_rows:
        warnings.append(f"Truncated row labels from {len(rows)} to {n_rows}.")
        rows = rows[:n_rows]
    while len(rows) < n_rows:
        rows.append(f"Row {len(rows) + 1}")
        warnings.append("Padded missing row labels.")
    if len(cols) > n_cols:
        warnings.append(f"Truncated column labels from {len(cols)} to {n_cols}.")
        cols = cols[:n_cols]
    while len(cols) < n_cols:
        cols.append(f"Column {len(cols) + 1}")
        warnings.append("Padded missing column labels.")
    # Deduplicate padding warnings
    warnings = list(dict.fromkeys(warnings))
    return rows, cols, warnings


def fill_question_axis_label(
    *,
    orientation: str,
    n_rows: int,
    n_cols: int,
    full_text: str,
    row_labels: list[str],
    col_labels: list[str],
) -> tuple[list[str], list[str]]:
    """Replace a padded 1-question axis label with ``full_text``.

    Vertical 1-column grids use the column as the RadioGroup; horizontal 1-row
    grids use the row. Dummy ``Column N`` / ``Row N`` pads from
    ``align_labels_to_counts`` are treated as missing.
    """
    stem = (full_text or "").strip()
    if not stem:
        return row_labels, col_labels
    orient = (orientation or "").strip().lower()
    if orient == "vertical" and n_cols == 1:
        if not col_labels or col_labels[0].startswith("Column "):
            return list(row_labels), [stem]
    if orient == "horizontal" and n_rows == 1:
        if not row_labels or row_labels[0].startswith("Row "):
            return [stem], list(col_labels)
    return row_labels, col_labels
