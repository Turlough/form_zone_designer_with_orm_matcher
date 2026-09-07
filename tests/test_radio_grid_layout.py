"""Tests for RadioGrid layout and serialization."""

import json

from fields import Field, RadioGrid, RadioGroup
from util.radio_grid_layout import (
    cell_rects_for_grid,
    expand_fields_for_runtime,
    expand_radio_grid,
    build_radio_group_from_frame,
    radio_group_name_from_question,
)


def _sample_grid() -> RadioGrid:
    return RadioGrid(
        colour=(100, 150, 0),
        name="Likert",
        x=10,
        y=20,
        width=300,
        height=90,
        orientation="horizontal",
        row_labels=["Q1", "Q2", "Q3"],
        col_labels=["Small", "Medium", "Large"],
        col_fracs=[1 / 3, 2 / 3],
        row_fracs=[1 / 3, 2 / 3],
        grid_id="test-grid-id",
    )


def test_radio_grid_round_trip_json():
    grid = _sample_grid()
    data = grid.to_dict()
    restored = Field.from_dict(data)
    assert isinstance(restored, RadioGrid)
    assert restored.grid_id == grid.grid_id
    assert restored.row_labels == grid.row_labels
    assert restored.col_fracs == grid.col_fracs


def test_expand_horizontal_grid_to_three_groups():
    grid = _sample_grid()
    groups = expand_radio_grid(grid)
    assert len(groups) == 3
    assert all(isinstance(g, RadioGroup) for g in groups)
    assert [g.name for g in groups] == ["Q1", "Q2", "Q3"]
    assert len(groups[0].radio_buttons) == 3
    assert [rb.name for rb in groups[0].radio_buttons] == ["Small", "Medium", "Large"]


def test_cell_rects_match_grid_shape():
    grid = _sample_grid()
    cells = cell_rects_for_grid(grid)
    assert len(cells) == 3
    assert len(cells[0]) == 3
    assert cells[0][0][0] == grid.x
    assert cells[0][0][1] == grid.y


def test_expand_fields_for_runtime_mixed_page():
    grid = _sample_grid()
    from fields import Tickbox

    tick = Tickbox(name="Agree", x=0, y=0, width=10, height=10, colour=(255, 0, 0))
    expanded = expand_fields_for_runtime([tick, grid])
    assert len(expanded) == 4
    assert isinstance(expanded[0], Tickbox)
    assert all(isinstance(f, RadioGroup) for f in expanded[1:])


def test_question_number_prefix_from_name():
    from ui.grid_designer import question_number_prefix_from_name

    assert question_number_prefix_from_name("1 Section") == "1"
    assert question_number_prefix_from_name("1.2 Likert") == "1.2"
    assert question_number_prefix_from_name("  1.2.3 Grid") == "1.2.3"
    assert question_number_prefix_from_name("Likert") is None
    assert question_number_prefix_from_name("A1") is None


def test_page_json_list_contains_radio_grid():
    grid = _sample_grid()
    payload = [grid.to_dict()]
    raw = json.dumps(payload)
    loaded = Field.from_dict(json.loads(raw)[0])
    assert isinstance(loaded, RadioGrid)


def test_question_number_and_long_labels_round_trip():
    long_row = "Overhead power line/electrical awareness and more detail"
    grid = RadioGrid(
        colour=(100, 150, 0),
        name="Health and Safety",
        x=0,
        y=0,
        width=300,
        height=200,
        orientation="horizontal",
        row_labels=[long_row, "Child/visitor safety on the farmyard"],
        col_labels=["Good", "Average", "Poor"],
        question_number="1.7",
        full_text="From a health and safety perspective, how would you rate the following on your farm?",
        summary="Health and Safety",
    )
    data = grid.to_dict()
    assert data["question_number"] == "1.7"
    assert len(data["row_labels"][0]) > 50
    restored = Field.from_dict(data)
    assert isinstance(restored, RadioGrid)
    assert restored.question_number == "1.7"
    assert restored.row_labels[0] == long_row

    groups = expand_radio_grid(restored)
    assert len(groups) == 2
    assert groups[0].question_number == "1.7"
    assert groups[0].name == long_row
    for rb in groups[0].radio_buttons:
        assert not getattr(rb, "question_number", None)
        assert rb.name in ("Good", "Average", "Poor")


def test_expand_single_column_vertical_copies_stem_meta():
    grid = RadioGrid(
        colour=(100, 150, 0),
        name="Age group",
        x=0,
        y=0,
        width=100,
        height=200,
        orientation="vertical",
        row_labels=["Under 35", "35 to 44", "45 to 54"],
        col_labels=["What age group do you fall into?"],
        question_number="1.2",
        full_text="What age group do you fall into?",
        summary="Age group",
    )
    groups = expand_radio_grid(grid)
    assert len(groups) == 1
    assert groups[0].question_number == "1.2"
    assert groups[0].full_text == "What age group do you fall into?"
    assert groups[0].summary == "Age group"
    assert all(not (rb.question_number or "") for rb in groups[0].radio_buttons)


def test_radio_group_name_from_question():
    assert radio_group_name_from_question("5.1", "stem text") == "stem text"
    assert radio_group_name_from_question("", "Whole farm stocking") == "Whole farm stocking"
    assert radio_group_name_from_question("5.1", "") == "5.1"
    assert radio_group_name_from_question("  ", "") == "RadioGroup"


def test_build_radio_group_from_irregular_frame():
    """Compact 3+2 option layout still yields one RadioGroup."""
    rg = build_radio_group_from_frame(
        x=10,
        y=20,
        width=400,
        height=200,
        options=[
            ("Less than 170", 20, 80, 16, 16),
            ("170-220", 200, 80, 16, 16),
            ("221-250", 20, 120, 16, 16),
            ("More than 250", 200, 120, 16, 16),
            ("Don't know", 20, 160, 16, 16),
        ],
        question_number="5.1",
        full_text="What is your Whole Farm Stocking Rate?",
    )
    assert isinstance(rg, RadioGroup)
    assert rg.name == "What is your Whole Farm Stocking Rate?"
    assert rg.question_number == "5.1"
    assert rg.full_text == "What is your Whole Farm Stocking Rate?"
    assert rg.x == 10 and rg.y == 20 and rg.width == 400 and rg.height == 200
    assert [b.name for b in rg.radio_buttons] == [
        "Less than 170",
        "170-220",
        "221-250",
        "More than 250",
        "Don't know",
    ]
    assert (rg.radio_buttons[4].x, rg.radio_buttons[4].y) == (20, 160)
    assert all(not (rb.question_number or "") for rb in rg.radio_buttons)

    restored = Field.from_dict(rg.to_dict())
    assert isinstance(restored, RadioGroup)
    assert len(restored.radio_buttons) == 5
    assert restored.radio_buttons[4].name == "Don't know"
