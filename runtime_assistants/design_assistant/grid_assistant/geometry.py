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


def cluster_grid_rects(
    rects_in_roi: Sequence[Rect],
    roi_page: Rect,
    *,
    user_orientation: str,
) -> ClusterResult:
    """Infer n_rows, n_cols, and split fractions from answer rectangles."""
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

    rx, ry, rw, rh = roi_page
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

    col_fracs = _fracs_from_centers(xs, float(rx), float(rw), n_cols)
    row_fracs = _fracs_from_centers(ys, float(ry), float(rh), n_rows)

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
