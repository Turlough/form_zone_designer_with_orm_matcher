"""Resolve default and per-page fiducial image paths under a project's fiducials/ folder."""

from __future__ import annotations

from pathlib import Path

from util.path_utils import find_file_case_insensitive

DEFAULT_LOGO_CANDIDATES = ("logo.png", "logo.tif", "fiducial.png", "fiducial.jpg")


def per_page_logo_filename(page_index: int) -> str:
    """Return the canonical per-page fiducial filename (page_index is zero-based)."""
    return f"logo-p{page_index + 1}.png"


def find_default_logo(fiducials_folder: str | Path) -> Path | None:
    """First matching global fiducial among DEFAULT_LOGO_CANDIDATES, or None."""
    folder = Path(fiducials_folder)
    for candidate in DEFAULT_LOGO_CANDIDATES:
        found = find_file_case_insensitive(folder, candidate)
        if found is not None:
            return found
    return None


def find_fiducial_for_page(fiducials_folder: str | Path, page_index: int) -> Path | None:
    """
    Per-page fiducial (logo-pN.png) overrides the default logo when present.
    page_index is zero-based.
    """
    folder = Path(fiducials_folder)
    per_page = find_file_case_insensitive(folder, per_page_logo_filename(page_index))
    if per_page is not None:
        return per_page
    return find_default_logo(folder)
