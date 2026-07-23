"""Associate VLM field proposals with OpenCV candidate rectangles."""

from __future__ import annotations

from typing import Sequence

Rect = tuple[int, int, int, int]  # x, y, w, h page-absolute


def _iou(a: Rect, b: Rect) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _center_distance(a: Rect, b: Rect) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    acx, acy = ax + aw / 2, ay + ah / 2
    bcx, bcy = bx + bw / 2, by + bh / 2
    return ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5


def resolve_rect(
    field: dict,
    cv_rects: Sequence[Rect],
    *,
    used_ids: set[int] | None = None,
    max_center_dist: float = 80.0,
) -> tuple[Rect | None, int | None, bool]:
    """Resolve page-absolute geometry for one field.

    Returns (rect, rect_id, answer_located).
    """
    used_ids = used_ids if used_ids is not None else set()

    explicit_located = field.get("answer_located")
    if explicit_located is False:
        return None, None, False

    rect_id = field.get("rect_id")
    if rect_id is not None:
        try:
            rid = int(rect_id)
        except (TypeError, ValueError):
            rid = -1
        if 0 <= rid < len(cv_rects) and rid not in used_ids:
            return cv_rects[rid], rid, True

    # Coarse page hint from VLM
    if all(k in field for k in ("page_x", "page_y", "page_width", "page_height")):
        try:
            hint: Rect = (
                int(field["page_x"]),
                int(field["page_y"]),
                int(field["page_width"]),
                int(field["page_height"]),
            )
        except (TypeError, ValueError):
            hint = None  # type: ignore[assignment]
        if hint and hint[2] > 0 and hint[3] > 0:
            best_i, best_score = -1, 0.0
            for i, r in enumerate(cv_rects):
                if i in used_ids:
                    continue
                score = _iou(hint, r)
                if score > best_score:
                    best_score = score
                    best_i = i
            if best_i >= 0 and best_score >= 0.15:
                return cv_rects[best_i], best_i, True
            # Fall back to nearest center among unused
            best_i, best_dist = -1, float("inf")
            for i, r in enumerate(cv_rects):
                if i in used_ids:
                    continue
                dist = _center_distance(hint, r)
                if dist < best_dist:
                    best_dist = dist
                    best_i = i
            if best_i >= 0 and best_dist <= max_center_dist:
                return cv_rects[best_i], best_i, True
            # Use hint geometry itself
            return hint, None, True

    if explicit_located is True:
        return None, None, False
    # Default: not located if no rect_id / hint
    return None, None, False


def apply_geometry(
    field: dict,
    rect: Rect | None,
    *,
    fiducial_top_left: tuple[int, int] | None,
) -> dict:
    """Write fiducial-relative x/y/width/height onto a copy of field."""
    out = dict(field)
    if rect is None:
        out["answer_located"] = False
        out.setdefault("x", 0)
        out.setdefault("y", 0)
        out.setdefault("width", 10)
        out.setdefault("height", 10)
        return out

    x, y, w, h = rect
    if fiducial_top_left:
        x -= fiducial_top_left[0]
        y -= fiducial_top_left[1]
    out["x"] = int(x)
    out["y"] = int(y)
    out["width"] = max(1, int(w))
    out["height"] = max(1, int(h))
    out["answer_located"] = True
    return out


def match_fields_to_rects(
    fields: list[dict],
    cv_rects: Sequence[Rect],
    *,
    fiducial_top_left: tuple[int, int] | None,
) -> tuple[list[dict], list[str]]:
    """Match proposed fields to CV rects; convert to fiducial-relative coords.

    Returns (matched_fields, warnings).
    """
    warnings: list[str] = []
    used: set[int] = set()
    matched: list[dict] = []

    for field in fields:
        out = dict(field)
        rbs = out.get("radio_buttons")
        if isinstance(rbs, list) and rbs:
            new_rbs = []
            for rb in rbs:
                if not isinstance(rb, dict):
                    continue
                rect, rid, located = resolve_rect(rb, cv_rects, used_ids=used)
                if rid is not None:
                    used.add(rid)
                rb_out = apply_geometry(rb, rect, fiducial_top_left=fiducial_top_left)
                if not located:
                    label = rb.get("summary") or rb.get("name") or "radio option"
                    warnings.append(f"No answer rectangle matched for radio option: {label}")
                new_rbs.append(rb_out)
            out["radio_buttons"] = new_rbs
            # Group bbox = union of children if any located
            located_rbs = [rb for rb in new_rbs if rb.get("answer_located")]
            if located_rbs:
                xs = [rb["x"] for rb in located_rbs]
                ys = [rb["y"] for rb in located_rbs]
                x2 = [rb["x"] + rb["width"] for rb in located_rbs]
                y2 = [rb["y"] + rb["height"] for rb in located_rbs]
                out["x"] = min(xs)
                out["y"] = min(ys)
                out["width"] = max(1, max(x2) - out["x"])
                out["height"] = max(1, max(y2) - out["y"])
                out["answer_located"] = True
            else:
                out = apply_geometry(out, None, fiducial_top_left=fiducial_top_left)
                label = out.get("summary") or out.get("name") or "RadioGroup"
                warnings.append(f"No answer rectangles matched for: {label}")
        else:
            rect, rid, located = resolve_rect(out, cv_rects, used_ids=used)
            if rid is not None:
                used.add(rid)
            out = apply_geometry(out, rect, fiducial_top_left=fiducial_top_left)
            if not located:
                label = out.get("summary") or out.get("name") or out.get("full_text") or "field"
                warnings.append(f"No answer rectangle matched for: {label}")

        matched.append(out)

    return matched, warnings
