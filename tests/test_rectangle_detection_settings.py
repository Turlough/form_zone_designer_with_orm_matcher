"""Tests for rectangle detection settings persistence."""

import json
from pathlib import Path

from util.rectangle_detection_settings import RectangleDetectionSettings
from util.designer_persistence import (
    load_rectangle_detection_settings,
    save_rectangle_detection_settings,
)


def test_settings_from_dict_defaults_for_missing_keys():
    settings = RectangleDetectionSettings.from_dict({"min_area": 1000})
    assert settings.min_area == 1000
    assert settings.canny_low_threshold == 60
    assert settings.include_adaptive_method is True
    assert settings.auto_remove_inner is True


def test_settings_to_dict_round_trip():
    original = RectangleDetectionSettings(
        blur_kernel_size=5,
        dilate_iterations=4,
        epsilon_factor=0.03,
        canny_low_threshold=40,
        canny_high_threshold=120,
        overlap_threshold_value=0.6,
        min_area=800,
        max_area=40000,
        include_adaptive_method=False,
        auto_remove_inner=False,
    )
    restored = RectangleDetectionSettings.from_dict(original.to_dict())
    assert restored == original


def test_save_merge_preserves_unrelated_config_keys(tmp_path: Path):
    json_folder = tmp_path / "json"
    json_folder.mkdir()
    config_path = json_folder / "project_config.json"
    config_path.write_text(
        json.dumps({"batch_folder": "C:\\\\batches", "import_filename": "OUT.txt"}),
        encoding="utf-8",
    )

    settings = RectangleDetectionSettings(canny_low_threshold=75)
    save_rectangle_detection_settings(str(json_folder), settings)

    with open(config_path, encoding="utf-8") as f:
        saved = json.load(f)

    assert saved["batch_folder"] == "C:\\\\batches"
    assert saved["import_filename"] == "OUT.txt"
    assert saved["rectangle_detection"]["canny_low_threshold"] == 75


def test_load_returns_defaults_when_config_missing(tmp_path: Path):
    settings = load_rectangle_detection_settings(str(tmp_path / "json"))
    assert settings == RectangleDetectionSettings()
