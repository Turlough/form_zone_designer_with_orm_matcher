"""Create Indexer test batches from a Designer template."""

from __future__ import annotations

import csv
import logging
import shutil
from pathlib import Path

import pymupdf as fitz

from util.path_utils import find_file_case_insensitive, find_project_template

logger = logging.getLogger(__name__)


class CreateTestBatchError(Exception):
    """Raised when a test batch cannot be created."""


def resolve_template_pdf_source(config_folder: Path | str) -> Path:
    """Prefer template.pdf; otherwise use the project template (TIFF may be converted)."""
    config_folder = Path(config_folder)
    pdf = find_file_case_insensitive(config_folder, "template.pdf")
    if pdf is not None:
        return pdf
    template = find_project_template(config_folder)
    if template is None:
        raise CreateTestBatchError("No template.pdf (or template.tif / template.tiff) found in the project folder.")
    return template


def _document_pdf_name(index: int, document_count: int) -> str:
    width = max(4, len(str(document_count)))
    return f"{index:0{width}d}.pdf"


def copy_template_as_pdf(src: Path, dest: Path) -> None:
    """Copy a PDF template, or convert another supported template to PDF."""
    if src.suffix.lower() == ".pdf":
        shutil.copy2(src, dest)
        return
    doc = fitz.open(str(src))
    try:
        doc.save(str(dest), deflate=True)
    finally:
        doc.close()


def create_test_batch(
    *,
    batch_folder: Path | str,
    batch_name: str,
    document_count: int,
    template_path: Path | str,
    import_filename: str,
) -> Path:
    """Create `<batch_folder>/<batch_name>` with copied PDFs and an import list file.

    Returns the created batch directory.
    """
    name = (batch_name or "").strip()
    if not name or Path(name).name != name or name in {".", ".."}:
        raise CreateTestBatchError("Enter a batch folder name without path separators.")
    if document_count < 1:
        raise CreateTestBatchError("Number of documents must be at least 1.")
    import_name = (import_filename or "").strip()
    if not import_name or Path(import_name).name != import_name:
        raise CreateTestBatchError("import_filename must be a file name, not a path.")

    template_path = Path(template_path)
    if not template_path.is_file():
        raise CreateTestBatchError(f"Template not found: {template_path}")

    batch_root = Path(batch_folder)
    batch_root.mkdir(parents=True, exist_ok=True)
    dest_dir = batch_root / name
    if dest_dir.exists():
        raise CreateTestBatchError(f"Batch folder already exists:\n{dest_dir}")

    dest_dir.mkdir(parents=False)
    names: list[str] = []
    try:
        for i in range(1, document_count + 1):
            pdf_name = _document_pdf_name(i, document_count)
            copy_template_as_pdf(template_path, dest_dir / pdf_name)
            names.append(pdf_name)
        import_path = dest_dir / import_name
        with open(import_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["File"])
            for pdf_name in names:
                writer.writerow([pdf_name])
    except Exception:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise

    logger.info("Created test batch at %s with %d document(s)", dest_dir, document_count)
    return dest_dir
