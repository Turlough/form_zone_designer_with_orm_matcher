"""Tests for per-page and default fiducial path resolution."""

from pathlib import Path

from util.fiducial_paths import find_default_logo, find_fiducial_for_page, per_page_logo_filename


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
