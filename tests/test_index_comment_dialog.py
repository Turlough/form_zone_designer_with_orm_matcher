"""Indexer comments dialog placement (no widget smoke)."""

from ui.index_comment_dialog import (
    MIN_DIALOG_HEIGHT,
    capped_dialog_height,
    clamp_window_to_available,
    pos_left_of_rect,
)


def test_pos_left_of_rect_is_left_and_vertically_centered():
    x, y = pos_left_of_rect(
        rect_left=500,
        rect_top=100,
        rect_height=24,
        dialog_w=280,
        dialog_h=400,
        margin=8,
    )
    assert x == 212
    assert y == 100 + (24 - 400) // 2


def test_clamp_window_moves_up_when_bottom_would_overflow():
    x, y = clamp_window_to_available(
        x=100, y=700, width=300, height=200,
        avail_x=0, avail_y=0, avail_w=1000, avail_h=800,
    )
    assert (x, y) == (100, 600)


def test_clamp_window_keeps_left_and_top_on_screen():
    x, y = clamp_window_to_available(
        x=-40, y=-50, width=300, height=200,
        avail_x=0, avail_y=0, avail_w=1000, avail_h=800,
    )
    assert (x, y) == (0, 0)


def test_clamp_window_uses_available_origin_not_zero():
    x, y = clamp_window_to_available(
        x=100, y=100, width=300, height=200,
        avail_x=1920, avail_y=0, avail_w=1080, avail_h=1920,
    )
    assert x == 1920


def test_capped_dialog_height_fits_available_screen():
    assert capped_dialog_height(900, available=800, frame_extra=40) == 760
    assert capped_dialog_height(200, available=800, frame_extra=40) == 200
    assert capped_dialog_height(50, available=800, frame_extra=40) == MIN_DIALOG_HEIGHT
