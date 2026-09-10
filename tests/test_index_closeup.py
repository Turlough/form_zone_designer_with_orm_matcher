"""Indexer close-up crop/overlay geometry (no widget smoke)."""

from ui.index_details_panel import CLOSEUP_PADDING, closeup_crop_and_overlay


def _pads(crop_x1, crop_y1, crop_x2, crop_y2, box_x, box_y, field_w, field_h):
    left = box_x
    top = box_y
    right = crop_x2 - crop_x1 - box_x - field_w
    bottom = crop_y2 - crop_y1 - box_y - field_h
    return left, top, right, bottom


def test_interior_field_has_equal_padding():
    field_w, field_h = 80, 30
    crop_x1, crop_y1, crop_x2, crop_y2, box_x, box_y = closeup_crop_and_overlay(
        abs_x=100,
        abs_y=200,
        field_width=field_w,
        field_height=field_h,
        image_width=1000,
        image_height=800,
    )
    left, top, right, bottom = _pads(
        crop_x1, crop_y1, crop_x2, crop_y2, box_x, box_y, field_w, field_h
    )
    assert (left, top, right, bottom) == (
        CLOSEUP_PADDING,
        CLOSEUP_PADDING,
        CLOSEUP_PADDING,
        CLOSEUP_PADDING,
    )
    assert (crop_x1, crop_y1) == (100 - CLOSEUP_PADDING, 200 - CLOSEUP_PADDING)
    assert (crop_x2, crop_y2) == (180 + CLOSEUP_PADDING, 230 + CLOSEUP_PADDING)


def test_near_left_edge_shrinks_left_padding_only():
    field_w, field_h = 50, 20
    abs_x = 5
    result = closeup_crop_and_overlay(
        abs_x=abs_x,
        abs_y=100,
        field_width=field_w,
        field_height=field_h,
        image_width=400,
        image_height=300,
    )
    crop_x1, crop_y1, crop_x2, crop_y2, box_x, box_y = result
    left, top, right, bottom = _pads(
        crop_x1, crop_y1, crop_x2, crop_y2, box_x, box_y, field_w, field_h
    )
    assert crop_x1 == 0
    assert box_x == abs_x
    assert left == abs_x
    assert right == CLOSEUP_PADDING
    assert top == bottom == CLOSEUP_PADDING


def test_near_right_edge_shrinks_right_padding_only():
    field_w, field_h = 40, 20
    image_w = 200
    abs_x = 155
    result = closeup_crop_and_overlay(
        abs_x=abs_x,
        abs_y=50,
        field_width=field_w,
        field_height=field_h,
        image_width=image_w,
        image_height=300,
    )
    crop_x1, crop_y1, crop_x2, crop_y2, box_x, box_y = result
    left, _top, right, _bottom = _pads(
        crop_x1, crop_y1, crop_x2, crop_y2, box_x, box_y, field_w, field_h
    )
    assert crop_x2 == image_w
    assert left == CLOSEUP_PADDING
    assert right == image_w - abs_x - field_w
    assert box_x == CLOSEUP_PADDING
