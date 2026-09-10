import os
import json
from pathlib import Path
from fields import Field
import logging

from util.path_utils import find_file_case_insensitive, resolve_path_or_original
from util.rectangle_detection_settings import RectangleDetectionSettings

logger = logging.getLogger(__name__)

DEFAULT_IMPORT_FILENAME = "EXPORT.TXT"
DEFAULT_LOOKUP_PRIME_INDEX = 0
DEFAULT_PAGES_WITHOUT_FIDUCIAL = [0, 1]
DEFAULT_TEST_BATCH_NAME = "test001"


def _project_config_path(json_folder: Path) -> Path:
    return json_folder / "project_config.json"


def load_project_config(json_folder: str | Path) -> dict:
    """Load project_config.json as a dict. Missing or invalid files yield {}."""
    json_folder = Path(resolve_path_or_original(json_folder))
    config_path = find_file_case_insensitive(json_folder, "project_config.json")
    if config_path is None:
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("Could not read project_config.json at %s: %s", config_path, e)
        return {}


def merge_project_config(
    json_folder: str | Path,
    updates: dict,
    *,
    remove_keys: tuple[str, ...] = (),
) -> dict:
    """Merge keys into project_config.json, preserving unrelated entries."""
    json_folder = Path(resolve_path_or_original(json_folder))
    json_folder.mkdir(parents=True, exist_ok=True)
    config_path = find_file_case_insensitive(json_folder, "project_config.json")
    if config_path is None:
        config_path = _project_config_path(json_folder)
        config: dict = {}
    else:
        config = load_project_config(json_folder)
    config.update(updates)
    for key in remove_keys:
        config.pop(key, None)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    logger.info("Updated project_config.json at %s", config_path)
    return config


def parse_pages_without_fiducial(text: str) -> list[int]:
    """Parse a JSON list (or comma-separated ints) of zero-based page indices."""
    raw = (text or "").strip()
    if not raw:
        return []
    if not raw.startswith("["):
        raw = f"[{raw}]"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError("pages_without_fiducial must be a JSON list of integers, e.g. [0, 1]") from e
    if not isinstance(data, list):
        raise ValueError("pages_without_fiducial must be a JSON list of integers, e.g. [0, 1]")
    pages: list[int] = []
    for item in data:
        if isinstance(item, bool) or not isinstance(item, (int, float, str)):
            raise ValueError("pages_without_fiducial entries must be integers")
        try:
            pages.append(int(item))
        except (TypeError, ValueError) as e:
            raise ValueError("pages_without_fiducial entries must be integers") from e
    return pages


def format_pages_without_fiducial(pages: list[int]) -> str:
    return json.dumps([int(x) for x in pages])


def indexing_config_from_project(
    config: dict | None,
    *,
    default_project_name: str = "",
) -> dict:
    """Build Basic Indexing Config values from project_config.json (with defaults)."""
    config = config or {}
    raw_pages = config.get("pages_without_fiducial")
    if raw_pages is None:
        pages = list(DEFAULT_PAGES_WITHOUT_FIDUCIAL)
    else:
        try:
            pages = [int(x) for x in raw_pages]
        except (TypeError, ValueError):
            pages = list(DEFAULT_PAGES_WITHOUT_FIDUCIAL)
    try:
        prime = int(config.get("lookup_prime_index", DEFAULT_LOOKUP_PRIME_INDEX))
    except (TypeError, ValueError):
        prime = DEFAULT_LOOKUP_PRIME_INDEX
    import_filename = str(config.get("import_filename", "") or "").strip() or DEFAULT_IMPORT_FILENAME
    project_name = str(config.get("project_name", "") or "").strip() or default_project_name
    return {
        "project_name": project_name,
        "batch_folder": str(config.get("batch_folder", "") or "").strip(),
        "import_filename": import_filename,
        "lookup_list": str(config.get("lookup_list", "") or "").strip(),
        "lookup_prime_index": prime,
        "pages_without_fiducial": pages,
    }


def save_indexing_config(json_folder: str | Path, values: dict) -> dict:
    """Merge Basic Indexing Config fields into project_config.json."""
    updates = {
        "project_name": str(values.get("project_name", "") or "").strip(),
        "batch_folder": str(values.get("batch_folder", "") or "").strip(),
        "import_filename": str(values.get("import_filename", "") or "").strip()
        or DEFAULT_IMPORT_FILENAME,
        "lookup_prime_index": int(values.get("lookup_prime_index", DEFAULT_LOOKUP_PRIME_INDEX)),
        "pages_without_fiducial": [int(x) for x in values.get("pages_without_fiducial", [])],
    }
    lookup_list = str(values.get("lookup_list", "") or "").strip()
    remove_keys: tuple[str, ...] = ()
    if lookup_list:
        updates["lookup_list"] = lookup_list
    else:
        remove_keys = ("lookup_list",)
    return merge_project_config(json_folder, updates, remove_keys=remove_keys)


def load_rectangle_detection_settings(json_folder: str) -> RectangleDetectionSettings:
    """Load rectangle_detection from project_config.json, or defaults."""
    config = load_project_config(json_folder)
    return RectangleDetectionSettings.from_dict(config.get("rectangle_detection"))


def save_rectangle_detection_settings(
    json_folder: str, settings: RectangleDetectionSettings
) -> None:
    """Merge rectangle_detection into project_config.json, preserving other keys."""
    settings.normalize()
    merge_project_config(json_folder, {"rectangle_detection": settings.to_dict()})


def first_page_index_with_json(json_folder: str | Path, page_count: int) -> int:
    """Return 0-based index of the first page that has `{n}.json`, or 0 if none."""
    if page_count <= 0:
        return 0
    json_folder = Path(resolve_path_or_original(json_folder))
    for idx in range(page_count):
        if find_file_case_insensitive(json_folder, f"{idx + 1}.json") is not None:
            return idx
    return 0


def load_page_fields(json_folder, page_idx, config_folder=None, *, expand_grids: bool = False):
    """Load fields for a specific page from JSON file.
    
    Args:
        json_folder: Path to folder containing JSON files
        page_idx: Zero-based page index
        config_folder: Optional Path to config folder for converting relative fiducial_paths
        expand_grids: When True, expand RadioGrid objects to RadioGroups (Indexer/Exporter)
    """
    json_folder = Path(resolve_path_or_original(json_folder))
    json_path = find_file_case_insensitive(json_folder, f"{page_idx + 1}.json")
    
    if json_path is None:
        logger.error(f"No JSON file found for page {page_idx + 1}")
        return []
    
    try:
        with open(json_path, 'r') as f:
            fields_data = json.load(f)
        
        # Convert config_folder to Path if it's a string
        if config_folder and not isinstance(config_folder, Path):
            config_folder = Path(config_folder)
        
        # Convert JSON data to Field objects
        fields = []
        for field_dict in fields_data:
            field_obj = Field.from_dict(field_dict)
            if type(field_obj) != Field:
                fields.append(field_obj)
        
        logger.info(f"Loaded {len(fields)} fields from {json_path}")
        if expand_grids:
            from util.radio_grid_layout import expand_fields_for_runtime
            fields = expand_fields_for_runtime(fields)
        return fields
    except Exception as e:
        logger.error(f"Error loading fields from {json_path}: {e}")
        return []

def save_page_fields(json_folder, page_idx, page_field_list, config_folder=None):
    """Save fields for a specific page to JSON file.
    
    Args:
        json_folder: Path to folder containing JSON files
        page_idx: Zero-based page index
        page_field_list: List of field lists for all pages
        config_folder: Optional Path to config folder for converting fiducial_paths to relative paths
    """
    if page_idx < 0 or page_idx >= len(page_field_list):
        logger.error(f"Invalid page index: {page_idx}")
        return

    json_folder = Path(resolve_path_or_original(json_folder))
    json_path = json_folder / f"{page_idx + 1}.json"
    
    # Convert config_folder to Path if it's a string
    if config_folder and not isinstance(config_folder, Path):
        config_folder = Path(config_folder)
    
    # Convert field list to Field objects and then to dict
    fields_data = []
    for field_obj in page_field_list[page_idx]:
        if isinstance(field_obj, Field):
            if type(field_obj) != Field:
                fields_data.append(field_obj.to_dict())
    
    try:
        with open(json_path, 'w') as f:
            json.dump(fields_data, f, indent=2, default=str)
        logger.info(f"Saved {len(fields_data)} fields to {json_path}")
    except Exception as e:
        logger.error(f"Error saving fields to {json_path}: {e}")