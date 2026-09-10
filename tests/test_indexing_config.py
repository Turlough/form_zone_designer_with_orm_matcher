"""Tests for Basic Indexing Config persistence and test-batch creation."""

import csv
import json
from pathlib import Path

import pymupdf as fitz

from util.designer_persistence import (
    DEFAULT_IMPORT_FILENAME,
    DEFAULT_PAGES_WITHOUT_FIDUCIAL,
    export_title_map,
    first_page_index_with_json,
    indexing_config_from_project,
    iter_page_json_paths,
    parse_pages_without_fiducial,
    remap_delivery_headers,
    runtime_field_names,
    save_indexing_config,
    save_rectangle_detection_settings,
)
from util.rectangle_detection_settings import RectangleDetectionSettings
from util.test_batch import CreateTestBatchError, create_test_batch


def _write_pdf(path: Path) -> None:
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(str(path))
    doc.close()


def test_parse_pages_without_fiducial_json_and_csv():
    assert parse_pages_without_fiducial("[0, 1]") == [0, 1]
    assert parse_pages_without_fiducial("0, 1") == [0, 1]
    assert parse_pages_without_fiducial("[]") == []
    assert parse_pages_without_fiducial("") == []


def test_parse_pages_without_fiducial_rejects_invalid():
    try:
        parse_pages_without_fiducial("not-a-list")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_indexing_config_defaults_when_keys_missing():
    values = indexing_config_from_project({}, default_project_name="MyForm")
    assert values["project_name"] == "MyForm"
    assert values["import_filename"] == DEFAULT_IMPORT_FILENAME
    assert values["lookup_prime_index"] == 0
    assert values["pages_without_fiducial"] == DEFAULT_PAGES_WITHOUT_FIDUCIAL
    assert values["batch_folder"] == ""
    assert values["lookup_list"] == ""


def test_save_indexing_config_merges_and_removes_blank_lookup(tmp_path: Path):
    json_folder = tmp_path / "json"
    json_folder.mkdir()
    config_path = json_folder / "project_config.json"
    config_path.write_text(
        json.dumps(
            {
                "always_review": ["Field3"],
                "lookup_list": "old.csv",
                "rectangle_detection": {"min_area": 9},
            }
        ),
        encoding="utf-8",
    )

    saved = save_indexing_config(
        json_folder,
        {
            "project_name": "HerdForm",
            "batch_folder": r"C:\jobs\batches",
            "import_filename": "EXPORT.TXT",
            "lookup_list": "",
            "lookup_prime_index": 2,
            "pages_without_fiducial": [0, 1],
        },
    )

    with open(config_path, encoding="utf-8") as f:
        on_disk = json.load(f)

    assert saved["project_name"] == "HerdForm"
    assert on_disk["always_review"] == ["Field3"]
    assert on_disk["rectangle_detection"]["min_area"] == 9
    assert on_disk["batch_folder"] == r"C:\jobs\batches"
    assert on_disk["import_filename"] == "EXPORT.TXT"
    assert on_disk["lookup_prime_index"] == 2
    assert on_disk["pages_without_fiducial"] == [0, 1]
    assert "lookup_list" not in on_disk


def test_save_indexing_config_then_rectangle_detection_preserves_keys(tmp_path: Path):
    json_folder = tmp_path / "json"
    json_folder.mkdir()
    save_indexing_config(
        json_folder,
        {
            "project_name": "P",
            "batch_folder": "batches",
            "import_filename": "EXPORT.TXT",
            "lookup_list": "lookup.csv",
            "lookup_prime_index": 0,
            "pages_without_fiducial": [0],
        },
    )
    save_rectangle_detection_settings(
        str(json_folder), RectangleDetectionSettings(canny_low_threshold=75)
    )
    with open(json_folder / "project_config.json", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["batch_folder"] == "batches"
    assert saved["lookup_list"] == "lookup.csv"
    assert saved["rectangle_detection"]["canny_low_threshold"] == 75


def test_create_test_batch_copies_pdfs_and_writes_import_file(tmp_path: Path):
    template = tmp_path / "template.pdf"
    _write_pdf(template)
    batch_root = tmp_path / "batches"
    dest = create_test_batch(
        batch_folder=batch_root,
        batch_name="test001",
        document_count=2,
        template_path=template,
        import_filename="EXPORT.TXT",
    )

    assert dest == batch_root / "test001"
    assert (dest / "0001.pdf").is_file()
    assert (dest / "0002.pdf").is_file()
    import_path = dest / "EXPORT.TXT"
    with open(import_path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows == [["File"], ["0001.pdf"], ["0002.pdf"]]


def test_create_test_batch_refuses_existing_folder(tmp_path: Path):
    template = tmp_path / "template.pdf"
    _write_pdf(template)
    existing = tmp_path / "batches" / "test001"
    existing.mkdir(parents=True)
    try:
        create_test_batch(
            batch_folder=tmp_path / "batches",
            batch_name="test001",
            document_count=1,
            template_path=template,
            import_filename="EXPORT.TXT",
        )
    except CreateTestBatchError as e:
        assert "already exists" in str(e)
    else:
        raise AssertionError("expected CreateTestBatchError")


def test_create_test_batch_rejects_invalid_name(tmp_path: Path):
    template = tmp_path / "template.pdf"
    _write_pdf(template)
    try:
        create_test_batch(
            batch_folder=tmp_path / "batches",
            batch_name="../escape",
            document_count=1,
            template_path=template,
            import_filename="EXPORT.TXT",
        )
    except CreateTestBatchError:
        pass
    else:
        raise AssertionError("expected CreateTestBatchError")


def test_first_page_index_with_json_skips_pages_without_files(tmp_path: Path):
    json_folder = tmp_path / "json"
    json_folder.mkdir()
    (json_folder / "3.json").write_text("[]", encoding="utf-8")
    (json_folder / "project_config.json").write_text("{}", encoding="utf-8")
    assert first_page_index_with_json(json_folder, 5) == 2


def test_first_page_index_with_json_uses_page_one_when_present(tmp_path: Path):
    json_folder = tmp_path / "json"
    json_folder.mkdir()
    (json_folder / "1.json").write_text("[]", encoding="utf-8")
    (json_folder / "2.json").write_text("[]", encoding="utf-8")
    assert first_page_index_with_json(json_folder, 2) == 0


def test_first_page_index_with_json_defaults_to_zero_when_none(tmp_path: Path):
    json_folder = tmp_path / "json"
    json_folder.mkdir()
    assert first_page_index_with_json(json_folder, 4) == 0
    assert first_page_index_with_json(json_folder, 0) == 0


def test_iter_page_json_paths_skips_gaps_and_non_page_files(tmp_path: Path):
    json_folder = tmp_path / "json"
    json_folder.mkdir()
    (json_folder / "4.json").write_text("[]", encoding="utf-8")
    (json_folder / "6.json").write_text("[]", encoding="utf-8")
    (json_folder / "project_config.json").write_text("{}", encoding="utf-8")
    pages = [n for n, _ in iter_page_json_paths(json_folder)]
    assert pages == [4, 6]


def test_runtime_field_names_and_export_title_map_use_name_not_title(tmp_path: Path):
    from fields import Tickbox

    json_folder = tmp_path / "json"
    json_folder.mkdir()
    field = Tickbox(
        colour=(0, 0, 0),
        name="2.1 Other Comment",
        x=0,
        y=0,
        width=10,
        height=10,
        column_title="Other Comment",
    )
    (json_folder / "4.json").write_text(json.dumps([field.to_dict()]), encoding="utf-8")
    assert runtime_field_names(json_folder) == ["2.1 Other Comment"]
    assert export_title_map(json_folder) == {"2.1 Other Comment": "Other Comment"}
    assert remap_delivery_headers(
        ["File", "2.1 Other Comment", "Comments"],
        export_title_map(json_folder),
    ) == ["File", "Other Comment", "Comments"]
