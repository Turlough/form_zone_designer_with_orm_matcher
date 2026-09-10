"""CSVManager header generation: field.name, JSON page gaps, in-memory rewrite."""

import json
from pathlib import Path

from fields import Tickbox
from util.csv_manager import CSVManager


def _write_page_json(json_folder: Path, page: int, field: Tickbox) -> None:
    json_folder.mkdir(parents=True, exist_ok=True)
    (json_folder / f"{page}.json").write_text(
        json.dumps([field.to_dict()]),
        encoding="utf-8",
    )


def test_load_csv_keys_columns_by_name_and_skips_missing_page_json(tmp_path: Path):
    json_folder = tmp_path / "json"
    field = Tickbox(
        colour=(0, 0, 0),
        name="Supplier Name",
        x=0,
        y=0,
        width=10,
        height=10,
        column_title="Customer Supplier Heading",
    )
    _write_page_json(json_folder, 4, field)
    csv_path = tmp_path / "EXPORT.TXT"
    csv_path.write_text("File\n0001.pdf\n", encoding="utf-8")

    mgr = CSVManager()
    mgr.load_csv(str(csv_path), str(json_folder))
    assert mgr.headers == ["File", "Supplier Name", "Comments"]
    assert mgr.field_names == ["Supplier Name"]
    assert mgr.set_field_value(0, "Supplier Name", "BOB")
    assert mgr.get_field_value(0, "Supplier Name") == "BOB"


def test_load_csv_rewrites_title_headers_to_names_without_shifting_values(tmp_path: Path):
    json_folder = tmp_path / "json"
    field = Tickbox(
        colour=(0, 0, 0),
        name="2.1 Other Comment",
        x=0,
        y=0,
        width=10,
        height=10,
        column_title="Other Comment",
    )
    _write_page_json(json_folder, 1, field)
    csv_path = tmp_path / "EXPORT.TXT"
    csv_path.write_text(
        "File,Other Comment,Comments\n0001.pdf,hello,\n",
        encoding="utf-8",
    )

    mgr = CSVManager()
    mgr.load_csv(str(csv_path), str(json_folder))
    assert mgr.headers == ["File", "2.1 Other Comment", "Comments"]
    assert mgr.get_field_value(0, "2.1 Other Comment") == "hello"
