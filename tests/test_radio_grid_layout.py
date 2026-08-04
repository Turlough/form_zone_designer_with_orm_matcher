"""Tests for RadioGrid layout and serialization."""

import json

from fields import Field, RadioGrid, RadioGroup
from util.radio_grid_layout import (
    cell_rects_for_grid,
    expand_fields_for_runtime,
    expand_radio_grid,
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
