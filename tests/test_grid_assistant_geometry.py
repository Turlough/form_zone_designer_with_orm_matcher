"""Unit tests for Grid Assistant geometry (no live VLM)."""

from runtime_assistants.design_assistant.grid_assistant.geometry import (
    align_labels_to_counts,
    cluster_grid_rects,
    fiducial_rect_to_page,
    fill_question_axis_label,
    filter_rects_in_roi,
    frame_answer_rects,
    page_rect_to_fiducial,
)
from runtime_assistants.design_assistant.grid_assistant.prompt import build_user_prompt
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
    assert result.framed_rect_page is not None
    fx, fy, fw, fh = result.framed_rect_page
    # Tight frame: top below stem-sized ROI (fy >> 0), bottom above ROI end
    assert fy > 0
    assert fy + fh < 200
    first_top = rects[0][1]
    last_bottom = rects[-1][1] + rects[-1][3]
    assert fy < first_top
    assert fy + fh > last_bottom


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
    assert result.framed_rect_page is not None


def test_frame_excludes_stem_area():
    """Tall ROI with stem above boxes; frame hugs checkboxes only."""
    # Stem-like empty space y=0..80; boxes start at y=100
    rects = [(50, 100 + i * 40, 16, 16) for i in range(4)]
    framed, row_fracs, col_fracs = frame_answer_rects(rects, n_rows=4, n_cols=1)
    fx, fy, fw, fh = framed
    assert fy >= 80  # does not extend into stem band
    assert fy < 100
    assert fy + fh > 100 + 3 * 40 + 16
    assert len(row_fracs) == 3
    assert col_fracs == []
    # First cell: margin above first box ≈ margin below it to first split
    first_top = 100
    first_bottom = 116
    split0_y = fy + row_fracs[0] * fh
    margin_above = first_top - fy
    margin_below = split0_y - first_bottom
    assert abs(margin_above - margin_below) <= 2.0


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


def _axis_kwargs(**overrides):
    base = dict(
        orientation="horizontal",
        n_rows=1,
        n_cols=4,
        full_text="What is your preferred contact method?",
        row_labels=["Row 1"],
        col_labels=["Phone", "Email", "Post", "None"],
    )
    base.update(overrides)
    return base


def test_fill_question_axis_horizontal_single_row_uses_full_text():
    rows, cols = fill_question_axis_label(**_axis_kwargs())
    assert rows == ["What is your preferred contact method?"]
    assert cols == ["Phone", "Email", "Post", "None"]


def test_fill_question_axis_vertical_single_column_uses_full_text():
    rows, cols = fill_question_axis_label(
        **_axis_kwargs(
            orientation="vertical",
            n_rows=5,
            n_cols=1,
            full_text="What age group do you fall into?",
            row_labels=["Under 35", "35 to 44", "45 to 54", "55 to 64", "Over 65"],
            col_labels=["Column 1"],
        )
    )
    assert cols == ["What age group do you fall into?"]
    assert rows[0] == "Under 35"


def test_fill_question_axis_keeps_real_question_label():
    rows, cols = fill_question_axis_label(
        **_axis_kwargs(row_labels=["Preferred contact"])
    )
    assert rows == ["Preferred contact"]
    assert cols[0] == "Phone"


def test_fill_question_axis_skips_multi_row_and_empty_stem():
    rows, cols = fill_question_axis_label(
        **_axis_kwargs(n_rows=2, row_labels=["Row 1", "Row 2"])
    )
    assert rows == ["Row 1", "Row 2"]

    rows, cols = fill_question_axis_label(**_axis_kwargs(full_text=""))
    assert rows == ["Row 1"]


def test_horizontal_single_row_prompt_asks_for_full_text_row_label():
    text = build_user_prompt(
        orientation="horizontal",
        n_rows=1,
        n_cols=4,
        image_width=100,
        image_height=40,
        candidate_rects=[],
    )
    assert "single-row option list" in text
    assert "row label is the full question text" in text
    assert "sub-question texts top-to-bottom" not in text


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
