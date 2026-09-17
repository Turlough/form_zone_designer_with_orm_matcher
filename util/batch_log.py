"""Batch folder movement log and Windows user identity for the Indexer."""

from __future__ import annotations

import csv
import getpass
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

BATCH_LOG_FILENAME = "batch.log"
EVENT_OPEN_BATCH = "Open Batch"
EVENT_COMPLETE_BATCH = "Complete Batch"
COORDINATION_FOLDERS = ("_in_progress", "_complete", "_qc")
COORDINATION_FOLDER_SET = frozenset(COORDINATION_FOLDERS)
LOG_COLUMNS = ("Datetime", "User", "Event", "Previous location", "New location")


def current_user() -> str:
    """Return the OS account running the Indexer, or ``unknown``."""
    try:
        name = getpass.getuser()
    except Exception:
        name = ""
    if not name:
        name = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    return str(name).strip() or "unknown"


def batch_location_label(batch_dir: Path) -> str:
    """Stage folder of a batch: job name, ``_in_progress``, ``_qc/_in_progress``, etc."""
    parent = Path(batch_dir).parent
    parts: list[str] = []
    current = parent
    while current.name in COORDINATION_FOLDER_SET:
        parts.append(current.name)
        nxt = current.parent
        if nxt == current:
            break
        current = nxt
    if not parts:
        return parent.name or str(parent)
    return "/".join(reversed(parts))


def append_batch_log(
    batch_dir: Path,
    event: str,
    previous_location: str,
    new_location: str,
    *,
    user: str | None = None,
    when: datetime | None = None,
) -> None:
    """Append one TSV row to ``batch.log`` beside the import file. Never raises."""
    log_path = Path(batch_dir) / BATCH_LOG_FILENAME
    stamp = (when or datetime.now().astimezone()).isoformat(timespec="seconds")
    row = (
        stamp,
        user if user is not None else current_user(),
        event,
        previous_location,
        new_location,
    )
    try:
        write_header = not log_path.exists() or log_path.stat().st_size == 0
        with open(log_path, "a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
            if write_header:
                writer.writerow(LOG_COLUMNS)
            writer.writerow(row)
    except Exception:
        logger.warning("Could not append batch log %s", log_path, exc_info=True)


def read_batch_log(batch_dir: Path) -> list[tuple[str, ...]]:
    """Return data rows from ``batch.log``. Empty if missing or unreadable."""
    log_path = Path(batch_dir) / BATCH_LOG_FILENAME
    if not log_path.is_file():
        return []
    try:
        with open(log_path, "r", encoding="utf-8", newline="") as fh:
            raw = list(csv.reader(fh, delimiter="\t"))
    except Exception:
        logger.warning("Could not read batch log %s", log_path, exc_info=True)
        return []
    if not raw:
        return []
    start = 1 if tuple(raw[0]) == LOG_COLUMNS else 0
    rows: list[tuple[str, ...]] = []
    for row in raw[start:]:
        padded = (list(row) + [""] * len(LOG_COLUMNS))[: len(LOG_COLUMNS)]
        rows.append(tuple(padded))
    return rows


def log_batch_move(source_dir: Path, dest_dir: Path, event: str) -> None:
    """Record a completed folder rename. ``source_dir`` may already be gone."""
    append_batch_log(
        dest_dir,
        event,
        batch_location_label(source_dir),
        batch_location_label(dest_dir),
    )
