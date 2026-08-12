"""Load/save versioned export format descriptors."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from util.path_utils import find_file_case_insensitive, resolve_path_or_original

from runtime_assistants.design_assistant.export_assistant_for_designer.enrich import enrich_page_hints
from runtime_assistants.design_assistant.export_assistant_for_designer.parse_excel import (
    parse_excel_workbook,
)
from runtime_assistants.design_assistant.export_assistant_for_designer.schema import (
    ExportFormatDescriptor,
    validate_descriptor,
)

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^export_format\.v(\d+)\.json$", re.IGNORECASE)


def _json_folder(config_folder: Path) -> Path:
    return Path(resolve_path_or_original(config_folder)) / "json"


def _project_config_path(json_folder: Path) -> Path:
    found = find_file_case_insensitive(json_folder, "project_config.json")
    return found if found is not None else json_folder / "project_config.json"


def _load_project_config(json_folder: Path) -> dict:
    path = _project_config_path(json_folder)
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Could not read %s: %s", path, e)
        return {}


def _save_project_config(json_folder: Path, config: dict) -> None:
    json_folder.mkdir(parents=True, exist_ok=True)
    path = _project_config_path(json_folder)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    logger.info("Updated project_config at %s", path)


def next_export_format_version(json_folder: Path) -> int:
    json_folder = Path(resolve_path_or_original(json_folder))
    max_v = 0
    if json_folder.is_dir():
        for p in json_folder.iterdir():
            m = _VERSION_RE.match(p.name)
            if m:
                max_v = max(max_v, int(m.group(1)))
    return max_v + 1


def export_format_path(json_folder: Path, version: int) -> Path:
    return Path(resolve_path_or_original(json_folder)) / f"export_format.v{version}.json"


def save_descriptor(json_folder: Path, descriptor: ExportFormatDescriptor) -> Path:
    validate_descriptor(descriptor.to_dict())
    json_folder = Path(resolve_path_or_original(json_folder))
    json_folder.mkdir(parents=True, exist_ok=True)
    path = export_format_path(json_folder, descriptor.version)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(descriptor.to_dict(), f, indent=2)
    logger.info("Wrote export format descriptor to %s", path)
    return path


def set_active_export_format(
    json_folder: Path,
    *,
    version: int,
    relative_path: str | None = None,
) -> None:
    json_folder = Path(resolve_path_or_original(json_folder))
    rel = relative_path or f"export_format.v{version}.json"
    config = _load_project_config(json_folder)
    config["export_format"] = {
        "active_version": version,
        "path": rel,
    }
    _save_project_config(json_folder, config)


def load_descriptor_file(path: Path | str) -> ExportFormatDescriptor:
    path = Path(resolve_path_or_original(path))
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return validate_descriptor(data)


def load_active_export_format(config_folder: Path | str) -> ExportFormatDescriptor | None:
    json_folder = _json_folder(Path(config_folder))
    config = _load_project_config(json_folder)
    export_cfg = config.get("export_format") or {}
    rel = (export_cfg.get("path") or "").strip()
    if not rel:
        version = export_cfg.get("active_version")
        if version:
            rel = f"export_format.v{int(version)}.json"
        else:
            return None
    path = find_file_case_insensitive(json_folder, rel)
    if path is None:
        logger.warning("Active export format not found: %s", rel)
        return None
    return load_descriptor_file(path)


def import_export_format(
    excel_path: Path | str,
    config_folder: Path | str,
    *,
    page_count: int = 1,
    notes: str = "",
    enrich: bool = True,
) -> ExportFormatDescriptor:
    """Parse Excel, optionally enrich, write versioned JSON, update project_config."""
    config_folder = Path(resolve_path_or_original(config_folder))
    json_folder = _json_folder(config_folder)
    version = next_export_format_version(json_folder)
    descriptor = parse_excel_workbook(excel_path, version=version, notes=notes)
    if enrich:
        descriptor = enrich_page_hints(descriptor, page_count=max(1, page_count))
    save_descriptor(json_folder, descriptor)
    set_active_export_format(json_folder, version=version)
    return descriptor
