"""Tests for find_duplicate_field_names (Designer project-wide duplicate-name check)."""

from fields import RadioButton, RadioGrid, RadioGroup, TextField, Tickbox
from util.designer_persistence import find_duplicate_field_names


def _tickbox(name: str) -> Tickbox:
    return Tickbox(colour=(0, 0, 0), name=name, x=0, y=0, width=10, height=10)


def _text_field(name: str) -> TextField:
    return TextField(colour=(0, 0, 0), name=name, x=0, y=0, width=10, height=10)


def test_no_duplicates_returns_empty_dict():
    page_field_list = [
        [_tickbox("q1_a"), _text_field("2.1 Other Comment")],
        [_tickbox("q2_a"), _text_field("3.4 Other Comment")],
    ]
    assert find_duplicate_field_names(page_field_list) == {}


def test_duplicate_across_pages_detected():
    page_field_list = [
        [_text_field("Other Comment")],
        [_text_field("Other Comment")],
    ]
    assert find_duplicate_field_names(page_field_list) == {"Other Comment": [1, 2]}


def test_duplicate_within_same_page_lists_page_twice():
    page_field_list = [
        [_tickbox("q1_a"), _tickbox("q1_a")],
    ]
    assert find_duplicate_field_names(page_field_list) == {"q1_a": [1, 1]}


def test_empty_project_has_no_duplicates():
    assert find_duplicate_field_names([]) == {}
    assert find_duplicate_field_names([[], []]) == {}


def test_radio_grid_expansion_checked_for_duplicates():
    """RadioGrid expands to one RadioGroup per row/col label; each becomes its own
    CSV column, so duplicate labels across pages must be flagged too."""

    def _grid(name: str) -> RadioGrid:
        return RadioGrid(
            colour=(0, 0, 0),
            name=name,
            x=0,
            y=0,
            width=100,
            height=100,
            orientation="horizontal",
            row_labels=["Q1"],
            col_labels=["Yes", "No"],
        )

    page_field_list = [[_grid("grid1")], [_grid("grid2")]]
    duplicates = find_duplicate_field_names(page_field_list)
    # Both grids expand a horizontal RadioGroup named after the row label "Q1".
    assert duplicates.get("Q1") == [1, 2]


def test_radio_buttons_inside_group_are_not_separate_columns():
    """RadioButtons nested in a RadioGroup are values within that column, not
    separate CSV columns, so identical button names must not be flagged."""
    rb1 = RadioButton(colour=(0, 0, 0), name="Yes", x=0, y=0, width=10, height=10)
    rb2 = RadioButton(colour=(0, 0, 0), name="Yes", x=0, y=0, width=10, height=10)
    group = RadioGroup(
        colour=(0, 0, 0),
        name="q1_group",
        x=0,
        y=0,
        width=50,
        height=50,
        radio_buttons=[rb1, rb2],
    )
    assert find_duplicate_field_names([[group]]) == {}
