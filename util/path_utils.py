"""Path utilities for case-insensitive file system operations.

On case-sensitive filesystems (Linux, macOS), paths like "File.TIF" and "file.tif"
refer to different files. This module provides resolution so that file operations
work regardless of path casing.
"""
import os
from pathlib import Path


def resolve_path_case_insensitive(path: str | Path) -> Path | None:
    """
    Resolve a path to its actual on-disk representation using case-insensitive
    matching. Returns None if any component does not exist.

    Use when the path may come from user input, CSV, or config and the actual
    file system casing may differ (e.g. files moved from Windows).
    """
    path = Path(path)
    if not path.parts:
        return path

    # Handle absolute vs relative
    if path.is_absolute():
        # On Windows, Path.root is just "\" and Path.drive holds "C:" or
        # "\\server\share". Path.anchor combines them ("C:\" or
        # "\\server\share\"). Using only root breaks drive-letter and UNC
        # paths. On POSIX, anchor and root are both "/".
        anchor = path.anchor or path.root
        resolved = Path(anchor)
        parts = path.parts[1:]  # Skip anchor/root
    else:
        resolved = Path.cwd()
        parts = path.parts

    for part in parts:
        if part in (".", ""):
            continue
        if part == "..":
            resolved = resolved.parent
            if not resolved.exists():
                return None
            continue

        parent = resolved
        target_lower = part.lower()
        found = None

        try:
            for item in parent.iterdir():
                if item.name.lower() == target_lower:
                    found = item
                    break
        except OSError:
            return None

        if found is None:
            return None
        resolved = found

    return resolved


def resolve_path_or_original(path: str | Path) -> Path:
    """
    Resolve path case-insensitively. If resolution fails, return the original
    path as Path (caller may still get FileNotFoundError on open).
    """
    resolved = resolve_path_case_insensitive(path)
    return resolved if resolved is not None else Path(path)


def paths_equal_case_insensitive(a: str | Path, b: str | Path) -> bool:
    """
    Compare two paths for equality ignoring case. Resolves both to their
    canonical form if they exist on disk; otherwise compares normalized strings.
    """
    a = str(a).strip()
    b = str(b).strip()
    if not a and not b:
        return True
    if not a or not b:
        return False

    resolved_a = resolve_path_case_insensitive(a)
    resolved_b = resolve_path_case_insensitive(b)

    if resolved_a is not None and resolved_b is not None:
        return resolved_a.resolve() == resolved_b.resolve()
    # Fallback: compare normalized (lowercase) strings
    return a.lower() == b.lower()


def find_file_case_insensitive(directory: str | Path, filename: str) -> Path | None:
    """
    Find a file in the given directory, matching filename case-insensitively.
    Returns the actual Path if found, else None.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return None
    target_lower = filename.lower()
    try:
        for item in directory.iterdir():
            if item.is_file() and item.name.lower() == target_lower:
                return item
    except OSError:
        pass
    return None
