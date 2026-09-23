"""Print-crop parse/clamp/paste and project_config persistence."""

from pathlib import Path

from PIL import Image

from util.designer_persistence import load_print_crop, merge_project_config, save_print_crop
from util.print_crop import (
    MIN_PRINT_CROP_SIZE,
    canvas_to_crop_uv,
    clamp_print_crop,
    crop_prepared_page_for_display,
    crop_uv_to_canvas,
    default_print_crop,
    display_origin,
    fiducial_bbox_inside_crop,
    move_rect,
    parse_print_crop,
    prepare_scan_page,
    print_crop_to_dict,
    resize_rect_by_handle,
)


def test_parse_print_crop_valid_and_missing():
    assert parse_print_crop(None) is None
    assert parse_print_crop({"x": 10, "y": 20, "width": 100, "height": 200}) == (10, 20, 100, 200)
    assert parse_print_crop({"x": "10", "y": "20", "width": "100", "height": "200"}) == (
        10,
        20,
        100,
        200,
    )


def test_parse_print_crop_rejects_invalid():
    assert parse_print_crop({}) is None
    assert parse_print_crop([10, 20, 100, 200]) is None
    assert parse_print_crop({"x": 0, "y": 0, "width": 5, "height": 100}) is None
    assert parse_print_crop({"x": 0, "y": 0, "width": "nope", "height": 100}) is None


def test_clamp_print_crop_stays_on_page():
    assert clamp_print_crop((-10, -10, 50, 50), (100, 80)) == (0, 0, 50, 50)
    clamped = clamp_print_crop((90, 70, 40, 40), (100, 80))
    x, y, w, h = clamped
    assert x >= 0 and y >= 0
    assert x + w <= 100
    assert y + h <= 80
    assert w >= MIN_PRINT_CROP_SIZE
    assert h >= MIN_PRINT_CROP_SIZE


def test_default_print_crop_is_inset():
    crop = default_print_crop((200, 100))
    x, y, w, h = crop
    assert x > 0 and y > 0
    assert x + w < 200
    assert y + h < 100


def test_prepare_scan_page_resizes_without_crop():
    scan = Image.new("RGB", (50, 40), (10, 20, 30))
    out = prepare_scan_page(scan, (100, 80), None)
    assert out.size == (100, 80)


def test_prepare_scan_page_pastes_into_crop():
    scan = Image.new("RGB", (10, 10), (255, 0, 0))
    crop = (20, 10, 40, 30)
    out = prepare_scan_page(scan, (100, 80), crop)
    assert out.size == (100, 80)
    assert out.getpixel((0, 0)) == (255, 255, 255)
    assert out.getpixel((20, 10)) == (255, 0, 0)
    assert out.getpixel((59, 39)) == (255, 0, 0)
    assert out.getpixel((60, 40)) == (255, 255, 255)


def test_crop_prepared_page_for_display_drops_canvas_margins():
    scan = Image.new("RGB", (10, 10), (255, 0, 0))
    crop = (20, 10, 40, 30)
    prepared = prepare_scan_page(scan, (100, 80), crop)
    shown = crop_prepared_page_for_display(prepared, crop)
    assert shown.size == (40, 30)
    assert shown.getpixel((0, 0)) == (255, 0, 0)
    assert shown.getpixel((39, 29)) == (255, 0, 0)
    assert display_origin(crop, (100, 80)) == (20, 10)


def test_crop_prepared_page_for_display_noop_without_crop():
    img = Image.new("RGB", (100, 80), (1, 2, 3))
    assert crop_prepared_page_for_display(img, None) is img
    assert display_origin(None, (100, 80)) == (0, 0)


def test_resize_and_move_rect():
    start = (20, 20, 40, 40)
    east = resize_rect_by_handle(start, "e", 80, 40, (100, 100))
    assert east == (20, 20, 60, 40)
    moved = move_rect(start, 10, -5, (100, 100))
    assert moved == (30, 15, 40, 40)


def test_crop_uv_round_trip():
    crop = (20, 10, 40, 30)
    u, v = canvas_to_crop_uv(40, 25, crop)
    assert u == 0.5
    assert v == 0.5
    x, y = crop_uv_to_canvas(u, v, crop)
    assert (x, y) == (40.0, 25.0)
    assert canvas_to_crop_uv(0, 0, crop) is None
    wider = (10, 10, 80, 30)
    x2, y2 = crop_uv_to_canvas(0.5, 0.5, wider)
    assert (x2, y2) == (50.0, 25.0)


def test_fiducial_bbox_inside_crop():
    crop = (10, 20, 100, 80)
    assert fiducial_bbox_inside_crop(((10, 20), (110, 100)), crop)
    assert fiducial_bbox_inside_crop(((40, 40), (70, 60)), crop)
    assert not fiducial_bbox_inside_crop(((9, 20), (110, 100)), crop)
    assert not fiducial_bbox_inside_crop(((10, 20), (111, 100)), crop)
    assert not fiducial_bbox_inside_crop(((50, 50), (80, 101)), crop)


def test_save_print_crop_merges_and_clears(tmp_path: Path):
    json_folder = tmp_path / "json"
    json_folder.mkdir()
    merge_project_config(json_folder, {"project_name": "KeepMe", "pages_without_fiducial": [0]})
    crop = (5, 6, 70, 80)
    on_disk = save_print_crop(json_folder, crop)
    assert on_disk["project_name"] == "KeepMe"
    assert on_disk["print_crop"] == print_crop_to_dict(crop)
    assert load_print_crop(json_folder) == crop
    cleared = save_print_crop(json_folder, None)
    assert "print_crop" not in cleared
    assert load_print_crop(json_folder) is None
    assert cleared["project_name"] == "KeepMe"
