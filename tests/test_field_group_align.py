"""Group drag/scale math for Indexer Page → Drag fields (no widget smoke)."""

from util.field_group_align import (
    MIN_GROUP_SIZE,
    FieldGroupAlign,
    drag_group_bounds,
    group_bounds,
    hit_group_bounds,
    map_rect,
    placed_rect,
    same_bounds,
    translate_bounds,
)


def test_group_bounds_unions_rects():
    bounds = group_bounds([(10, 20, 30, 40), (0, 5, 10, 10)])
    assert bounds == (0, 5, 40, 55)


def test_group_bounds_empty_is_none():
    assert group_bounds([]) is None


def test_move_translates_without_scaling():
    start = (10, 20, 200, 100)
    moved = drag_group_bounds(start, "move", 15, -4)
    assert moved == (25, 16, 200, 100)


def test_east_edge_scales_width_only_and_keeps_left():
    start = (10, 20, 200, 100)
    resized = drag_group_bounds(start, "e", 40, 999)
    assert resized == (10, 20, 240, 100)


def test_west_edge_keeps_the_right_edge():
    start = (10, 20, 200, 100)
    resized = drag_group_bounds(start, "w", -30, 5)
    assert resized[2] == 230
    assert resized[0] + resized[2] == start[0] + start[2]
    assert resized[1] == start[1]
    assert resized[3] == start[3]


def test_north_edge_keeps_the_bottom_edge():
    start = (10, 20, 200, 100)
    resized = drag_group_bounds(start, "n", 80, -25)
    assert resized[3] == 125
    assert resized[1] + resized[3] == start[1] + start[3]
    assert (resized[0], resized[2]) == (start[0], start[2])


def test_south_edge_scales_height_only():
    start = (10, 20, 200, 100)
    resized = drag_group_bounds(start, "s", -50, 30)
    assert resized == (10, 20, 200, 130)


def test_corner_keeps_aspect_and_opposite_corner():
    start = (0, 0, 200, 100)
    resized = drag_group_bounds(start, "se", 100, 0)
    assert resized[0] == 0 and resized[1] == 0
    assert resized[2] / resized[3] == 2
    assert resized[2] == 300

    nw = drag_group_bounds(start, "nw", -50, 0)
    assert nw[0] + nw[2] == start[0] + start[2]
    assert nw[1] + nw[3] == start[1] + start[3]
    assert nw[2] / nw[3] == 2


def test_corner_does_not_shrink_below_minimum():
    start = (0, 0, 100, 50)
    resized = drag_group_bounds(start, "se", -1000, -1000)
    assert resized[2] >= MIN_GROUP_SIZE
    assert resized[3] >= MIN_GROUP_SIZE
    assert resized[2] / resized[3] == 2


def test_map_rect_scales_and_translates_children():
    source = (0, 0, 100, 50)
    dest = (10, 20, 200, 50)
    assert map_rect(source, dest, (10, 10, 20, 10)) == (30, 30, 40, 10)


def test_placed_rect_uses_frozen_logo_inside_align():
    align = FieldGroupAlign(
        logo=(100, 50),
        source=(100, 50, 200, 100),
        dest=(110, 60, 400, 100),
    )
    assert placed_rect(0, 0, 200, 100, (0, 0), align) == (110, 60, 400, 100)
    assert placed_rect(50, 25, 20, 10, (999, 999), align) == (210, 85, 40, 10)


def test_placed_rect_without_align_adds_live_logo():
    assert placed_rect(5, 6, 7, 8, (10, 20), None) == (15, 26, 7, 8)


def test_same_bounds_and_translate():
    assert same_bounds((0, 0, 10, 10), (0.2, -0.2, 10.1, 9.9))
    assert not same_bounds((0, 0, 10, 10), (2, 0, 10, 10))
    assert translate_bounds((1, 2, 3, 4), 5, -1) == (6, 1, 3, 4)


def test_hit_prefers_corner_then_edge_then_interior():
    bounds = (0, 0, 100, 100)
    assert hit_group_bounds(2, 2, bounds, 8) == "nw"
    assert hit_group_bounds(50, 2, bounds, 8) == "n"
    assert hit_group_bounds(100, 50, bounds, 8) == "e"
    assert hit_group_bounds(50, 50, bounds, 8) == "move"
    assert hit_group_bounds(200, 200, bounds, 8) is None
