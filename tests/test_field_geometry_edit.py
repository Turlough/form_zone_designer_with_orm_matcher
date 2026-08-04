"""Tests for util.field_geometry_edit."""

from fields import RadioButton, RadioGroup, Tickbox
from util.field_geometry_edit import (
    drag_vertical_division,
    geometry_edit_target,
    grid_division_lines,
    group_bounds_from_buttons,
    resize_field_by_handle,
    resize_radio_group_by_handle,
    snapshot_field_geometry,
    restore_field_geometry,
    sync_radio_group_bounds,
)


def _row_group() -> RadioGroup:
    buttons = [
        RadioButton(name="a", x=0, y=0, width=30, height=20, colour=(100, 150, 0)),
        RadioButton(name="b", x=30, y=0, width=30, height=20, colour=(100, 150, 0)),
        RadioButton(name="c", x=60, y=0, width=30, height=20, colour=(100, 150, 0)),
    ]
    return RadioGroup(name="q1", x=0, y=0, width=90, height=20, colour=(100, 150, 0), radio_buttons=buttons)


def test_geometry_edit_target_prefers_parent_for_multi_button_group():
    rg = _row_group()
    rb = rg.radio_buttons[1]
    assert geometry_edit_target(rb, rg) is rg


def test_grid_division_lines_single_row():
    rg = _row_group()
    cols, rows = grid_division_lines(rg)
    assert cols == [30, 60]
    assert rows == []


def test_drag_vertical_division_moves_shared_boundary():
    rg = _row_group()
    assert drag_vertical_division(rg, 30, 40)
    assert rg.radio_buttons[0].width == 40
    assert rg.radio_buttons[1].x == 40
    assert rg.radio_buttons[1].width == 20


def test_drag_vertical_division_rejects_too_small():
    rg = _row_group()
    assert not drag_vertical_division(rg, 30, 5)


def test_snapshot_restore_round_trip():
    rg = _row_group()
    snap = snapshot_field_geometry(rg)
    drag_vertical_division(rg, 30, 40)
    restore_field_geometry(rg, snap)
    assert rg.radio_buttons[0].width == 30
    assert rg.radio_buttons[1].x == 30


def test_resize_simple_field():
    tb = Tickbox(name="t", x=10, y=10, width=40, height=30, colour=(255, 0, 0))
    resize_field_by_handle(tb, "se", 0, 0, 60, 50)
    assert tb.width == 50
    assert tb.height == 40


def test_sync_radio_group_bounds():
    rg = _row_group()
    rg.radio_buttons[2].width = 40
    sync_radio_group_bounds(rg)
    assert rg.width == 100


def test_resize_radio_group_scales_divisions_proportionally():
    rg = _row_group()
    start_buttons = [(rb.x, rb.y, rb.width, rb.height) for rb in rg.radio_buttons]
    start_bounds = group_bounds_from_buttons(start_buttons)
    resize_radio_group_by_handle(rg, "e", start_bounds, start_buttons, start_bounds[0] + start_bounds[2] * 2, start_bounds[1])
    assert rg.width == start_bounds[2] * 2
    assert rg.radio_buttons[0].width == 60
    assert rg.radio_buttons[1].x == 60
    assert rg.radio_buttons[1].width == 60
    assert rg.radio_buttons[2].x == 120
    assert rg.radio_buttons[2].width == 60


def test_resize_radio_group_from_snapshot_not_current_state():
    """Repeated apply from the same snapshot must not drift."""
    rg = _row_group()
    start_buttons = [(rb.x, rb.y, rb.width, rb.height) for rb in rg.radio_buttons]
    start_bounds = group_bounds_from_buttons(start_buttons)
    target_x = start_bounds[0] + int(start_bounds[2] * 1.5)
    resize_radio_group_by_handle(rg, "e", start_bounds, start_buttons, target_x, start_bounds[1])
    first = [(rb.x, rb.y, rb.width, rb.height) for rb in rg.radio_buttons]
    resize_radio_group_by_handle(rg, "e", start_bounds, start_buttons, target_x, start_bounds[1])
    second = [(rb.x, rb.y, rb.width, rb.height) for rb in rg.radio_buttons]
    assert first == second
