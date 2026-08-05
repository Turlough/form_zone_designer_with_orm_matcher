"""Unit tests for Grid Assistant geometry (no live VLM)."""

from runtime_assistants.design_assistant.grid_assistant.geometry import (
    align_labels_to_counts,
    cluster_grid_rects,
    fiducial_rect_to_page,
    filter_rects_in_roi,
    page_rect_to_fiducial,
)
from runtime_assistants.design_assistant.grid_assistant.schema import (
    parse_vlm_response,
    validate_grid_analysis,
)


def test_fiducial_round_trip():
    bbox = ((100, 50), (200, 150))
    page = fiducial_rect_to_page((10, 20, 30, 40), bbox)
    assert page == (110, 70, 30, 40)
    assert page_rect_to_fiducial(page, bbox) == (10, 20, 30, 40)


def test_filter_rects_in_roi_by_center():
    roi = (0, 0, 100, 100)
    inside = (40, 40, 10, 10)
    outside = (200, 200, 10, 10)
    assert filter_rects_in_roi([inside, outside], roi) == [inside]


def test_cluster_single_column():
    # Five stacked boxes — vertical list
    rects = [(50, 20 + i * 30, 12, 12) for i in range(5)]
    roi = (0, 0, 200, 200)
    result = cluster_grid_rects(rects, roi, user_orientation="vertical")
    assert result.n_rows == 5
    assert result.n_cols == 1
    assert len(result.row_fracs) == 4
    assert result.col_fracs == []


def test_cluster_matrix_5x3():
    rects = []
    for r in range(5):
        for c in range(3):
            rects.append((30 + c * 40, 40 + r * 35, 14, 14))
    roi = (0, 0, 200, 250)
    result = cluster_grid_rects(rects, roi, user_orientation="horizontal")
    assert result.n_rows == 5
    assert result.n_cols == 3
    assert len(result.row_fracs) == 4
    assert len(result.col_fracs) == 2


def test_orientation_warning_mismatch():
    rects = [(50, 20 + i * 30, 12, 12) for i in range(5)]
    roi = (0, 0, 200, 200)
    result = cluster_grid_rects(rects, roi, user_orientation="horizontal")
    assert any("vertical" in w.lower() for w in result.warnings)


def test_align_labels_pad_and_truncate():
    rows, cols, warnings = align_labels_to_counts(
        ["A", "B", "C", "D"],
        ["X"],
        n_rows=2,
        n_cols=3,
    )
    assert rows == ["A", "B"]
    assert len(cols) == 3
    assert cols[0] == "X"
    assert warnings


def test_parse_and_validate_grid_json():
    text = """```json
{
  "schema_version": 1,
  "question_number": "1.7",
  "summary": "Health and Safety",
  "full_text": "From a health and safety perspective?",
  "orientation_observed": "horizontal",
  "row_labels": ["Livestock handling facilities"],
  "col_labels": ["Good", "Average", "Poor"],
  "warnings": []
}
```"""
    raw = parse_vlm_response(text)
    result = validate_grid_analysis(raw)
    assert result.question_number == "1.7"
    assert result.summary == "Health and Safety"
    assert len(result.col_labels) == 3
