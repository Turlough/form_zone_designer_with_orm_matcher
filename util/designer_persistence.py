import os
import json
from pathlib import Path
from fields import Field
import logging

from util.path_utils import find_file_case_insensitive, resolve_path_or_original
from util.rectangle_detection_settings import RectangleDetectionSettings

logger = logging.getLogger(__name__)


def _project_config_path(json_folder: Path) -> Path:
    return json_folder / "project_config.json"


def load_rectangle_detection_settings(json_folder: str) -> RectangleDetectionSettings:
    """Load rectangle_detection from project_config.json, or defaults."""
    json_folder = Path(resolve_path_or_original(json_folder))
    config_path = find_file_case_insensitive(json_folder, "project_config.json")
    if config_path is None:
        return RectangleDetectionSettings()
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return RectangleDetectionSettings.from_dict(config.get("rectangle_detection"))
    except Exception as e:
        logger.warning("Could not read rectangle_detection from %s: %s", config_path, e)
        return RectangleDetectionSettings()


def save_rectangle_detection_settings(
    json_folder: str, settings: RectangleDetectionSettings
) -> None:
    """Merge rectangle_detection into project_config.json, preserving other keys."""
    json_folder = Path(resolve_path_or_original(json_folder))
    json_folder.mkdir(parents=True, exist_ok=True)
    config_path = find_file_case_insensitive(json_folder, "project_config.json")
    if config_path is None:
        config_path = _project_config_path(json_folder)
        config: dict = {}
    else:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            logger.warning("Could not read %s for merge: %s", config_path, e)
            config = {}
    settings.normalize()
    config["rectangle_detection"] = settings.to_dict()
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    logger.info("Saved rectangle_detection settings to %s", config_path)

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