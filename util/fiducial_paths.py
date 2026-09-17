"""Resolve default and per-page fiducial image paths under a project's fiducials/ folder."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from util.path_utils import find_file_case_insensitive

DEFAULT_LOGO_CANDIDATES = ("logo.png", "logo.tif", "fiducial.png", "fiducial.jpg")
DEFAULT_FIDUCIAL_FILENAME = "fiducial.png"


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


def default_logo_write_path(fiducials_folder: str | Path) -> Path:
    """Existing default logo, or fiducials/fiducial.png when none exists yet."""
    existing = find_default_logo(fiducials_folder)
    if existing is not None:
        return existing
    return Path(fiducials_folder) / DEFAULT_FIDUCIAL_FILENAME


def crop_detected_fiducial(image: Image.Image, bbox: tuple) -> Image.Image:
    """Crop a prepared-scan patch from an ORMMatcher (top_left, bottom_right) box."""
    top_left, bottom_right = bbox
    x0, y0 = int(top_left[0]), int(top_left[1])
    x1, y1 = int(bottom_right[0]), int(bottom_right[1])
    width, height = image.size
    if width < 1 or height < 1:
        raise ValueError("Image is empty")
    x0 = max(0, min(x0, width - 1))
    y0 = max(0, min(y0, height - 1))
    x1 = max(x0 + 1, min(x1, width))
    y1 = max(y0 + 1, min(y1, height))
    return image.crop((x0, y0, x1, y1))


def save_detected_fiducial(
    fiducials_folder: str | Path,
    image: Image.Image,
    bbox: tuple,
) -> Path:
    """Overwrite the default fiducial with the detected patch from a prepared scan."""
    folder = Path(fiducials_folder)
    folder.mkdir(parents=True, exist_ok=True)
    out_path = default_logo_write_path(folder)
    crop = crop_detected_fiducial(image, bbox)
    if out_path.suffix.lower() == ".png":
        crop.save(out_path, "PNG")
    else:
        crop.save(out_path)
    return out_path
