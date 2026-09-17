"""Tests for per-page and default fiducial path resolution."""

from pathlib import Path

from PIL import Image

from util.fiducial_paths import (
    crop_detected_fiducial,
    default_logo_write_path,
    find_default_logo,
    find_fiducial_for_page,
    per_page_logo_filename,
    save_detected_fiducial,
)


def test_per_page_logo_filename_is_one_based(tmp_path: Path) -> None:
    assert per_page_logo_filename(0) == "logo-p1.png"
    assert per_page_logo_filename(2) == "logo-p3.png"


def test_per_page_overrides_default(tmp_path: Path) -> None:
    fid = tmp_path / "fiducials"
    fid.mkdir()
    (fid / "logo.png").write_bytes(b"x")
    (fid / "logo-p2.png").write_bytes(b"y")

    assert find_default_logo(fid) == fid / "logo.png"
    assert find_fiducial_for_page(fid, 0) == fid / "logo.png"
    assert find_fiducial_for_page(fid, 1) == fid / "logo-p2.png"


def test_per_page_only_without_default(tmp_path: Path) -> None:
    fid = tmp_path / "fiducials"
    fid.mkdir()
    (fid / "logo-p1.png").write_bytes(b"x")

    assert find_default_logo(fid) is None
    assert find_fiducial_for_page(fid, 0) == fid / "logo-p1.png"
    assert find_fiducial_for_page(fid, 1) is None


def test_default_logo_write_path_uses_existing_or_fiducial_png(tmp_path: Path) -> None:
    fid = tmp_path / "fiducials"
    fid.mkdir()
    assert default_logo_write_path(fid) == fid / "fiducial.png"
    (fid / "logo.png").write_bytes(b"x")
    assert default_logo_write_path(fid) == fid / "logo.png"


def test_crop_detected_fiducial_extracts_bbox() -> None:
    img = Image.new("RGB", (100, 80), (0, 0, 0))
    for x in range(10, 30):
        for y in range(20, 50):
            img.putpixel((x, y), (255, 0, 0))
    crop = crop_detected_fiducial(img, ((10, 20), (30, 50)))
    assert crop.size == (20, 30)
    assert crop.getpixel((0, 0)) == (255, 0, 0)
    assert crop.getpixel((19, 29)) == (255, 0, 0)


def test_save_detected_fiducial_overwrites_fiducial_png(tmp_path: Path) -> None:
    fid = tmp_path / "fiducials"
    fid.mkdir()
    Image.new("RGB", (8, 8), (0, 255, 0)).save(fid / "fiducial.png")
    scan = Image.new("RGB", (40, 40), (1, 2, 3))
    for x in range(5, 13):
        for y in range(6, 14):
            scan.putpixel((x, y), (9, 9, 9))
    path = save_detected_fiducial(fid, scan, ((5, 6), (13, 14)))
    assert path == fid / "fiducial.png"
    saved = Image.open(path)
    assert saved.size == (8, 8)
    assert saved.getpixel((0, 0)) == (9, 9, 9)
    assert saved.getpixel((7, 7)) == (9, 9, 9)
