"""Unit tests for Question Assistant (no live VLM)."""

from runtime_assistants.design_assistant.question_assistant.geometry import (
    guess_field_type_from_geometry,
    sort_rects_reading_order,
)
from runtime_assistants.design_assistant.question_assistant.schema import (
    align_fields_to_rect_count,
    parse_vlm_response,
    validate_question_analysis,
)


def test_sort_rects_reading_order():
    rects = [(50, 100, 10, 10), (50, 20, 10, 10), (50, 60, 10, 10)]
    assert sort_rects_reading_order(rects) == [
        (50, 20, 10, 10),
        (50, 60, 10, 10),
        (50, 100, 10, 10),
    ]


def test_guess_field_type_wide_box():
    assert guess_field_type_from_geometry((10, 10, 80, 12), median_width=12) == "TextField"
    assert guess_field_type_from_geometry((10, 10, 12, 12), median_width=12) == "Tickbox"


def test_validate_question_analysis():
    raw = parse_vlm_response(
        """
        {
          "question_number": "6.9",
          "full_text": "When reviewing the health status...",
          "fields": [
            {"rect_id": 0, "_type": "Tickbox", "name": "Mastitis", "column_title": "Mastitis"},
            {"rect_id": 1, "_type": "TextField", "name": "Other", "column_title": "Other"}
          ],
          "warnings": []
        }
        """
    )
    result = validate_question_analysis(raw)
    assert result.question_number == "6.9"
    assert len(result.fields) == 2
    assert result.fields[0].field_type == "Tickbox"
    assert result.fields[1].field_type == "TextField"


def test_align_fields_to_rect_count_pads():
    proposals, warnings = align_fields_to_rect_count([], 3)
    assert len(proposals) == 3
    assert any("Padding" in w for w in warnings)
