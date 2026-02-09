"""Persist app state (last config folder, last page) in local AppData."""

import json
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

APP_NAME = "Designer"
STATE_FILENAME = "app_state.json"


def _app_state_dir() -> Path:
    """Return the app state directory (local AppData / config)."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    elif os.name == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_state() -> dict:
    """Load persisted state. Returns dict with designer and indexer keys."""
    path = _app_state_dir() / STATE_FILENAME
    default = {
        "last_config_folder": "",
        "last_page_index": None,
        "last_import_file": "",
        "last_indexer_config_folder": "",
        "last_indexer_json_folder": "",
        "last_indexer_tiff_index": None,
        "last_indexer_page_index": None,
    }
    if not path.exists():
        return default
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return {
            "last_config_folder": data.get("last_config_folder", ""),
            "last_page_index": data.get("last_page_index"),
            "last_import_file": data.get("last_import_file", ""),
            "last_indexer_config_folder": data.get("last_indexer_config_folder", ""),
            "last_indexer_json_folder": data.get("last_indexer_json_folder", ""),
            "last_indexer_tiff_index": data.get("last_indexer_tiff_index"),
            "last_indexer_page_index": data.get("last_indexer_page_index"),
        }
    except Exception as e:
        logger.warning("Could not load app state: %s", e)
        return default


def save_state(
    *,
    last_config_folder: str | None = None,
    last_page_index: int | None = None,
    last_import_file: str | None = None,
    last_indexer_config_folder: str | None = None,
    last_indexer_json_folder: str | None = None,
    last_indexer_tiff_index: int | None = None,
    last_indexer_page_index: int | None = None,
) -> None:
    """Save state. Pass only keys to update; others are preserved."""
    path = _app_state_dir() / STATE_FILENAME
    current = load_state()
    if last_config_folder is not None:
        current["last_config_folder"] = last_config_folder
    if last_page_index is not None:
        current["last_page_index"] = last_page_index
    if last_import_file is not None:
        current["last_import_file"] = last_import_file
    if last_indexer_config_folder is not None:
        current["last_indexer_config_folder"] = last_indexer_config_folder
    if last_indexer_json_folder is not None:
        current["last_indexer_json_folder"] = last_indexer_json_folder
    if last_indexer_tiff_index is not None:
        current["last_indexer_tiff_index"] = last_indexer_tiff_index
    if last_indexer_page_index is not None:
        current["last_indexer_page_index"] = last_indexer_page_index
    try:
        with open(path, "w") as f:
            json.dump(current, f, indent=2)
    except Exception as e:
        logger.warning("Could not save app state: %s", e)
