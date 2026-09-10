"""Tests for export assistant parse, io, and check (no live API)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fields import Tickbox, TextField
from runtime_assistants.design_assistant.export_assistant_for_designer.check import (
    apply_export_proposals,
    check_page_export_format,
    export_columns_for_prompt,
)
from runtime_assistants.design_assistant.export_assistant_for_designer.io import (
    import_export_format,
    load_active_export_format,
    next_export_format_version,
)
from runtime_assistants.design_assistant.export_assistant_for_designer.parse_excel import (
    parse_excel_workbook,
)
from runtime_assistants.design_assistant.export_assistant_for_designer.schema import (
    ExportColumn,
    ExportFormatDescriptor,
    KIND_META,
    KIND_MULTI_SELECT_OPTION,
    KIND_OPEN_TEXT,
    KIND_SINGLE_CHOICE,
    validate_descriptor,
)


def _write_sample_xlsx(path: Path) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(
        [
            "Respondent ID",
            "Supplier Name",
            "",
            "Who do you work with?",
            "",
        ]
    )
    ws.append(
        [
            "",
            "Open-Ended Response",
            "Response",
            "Spouse/Partner - Full time",
            "Children - Full time",
        ]
    )
    ws.append(["1", "Acme Farm", "Partnership", "1", ""])
    wb.save(path)
    wb.close()


def test_parse_qualtrics_style_headers(tmp_path: Path):
    xlsx = tmp_path / "sample.xlsx"
    _write_sample_xlsx(xlsx)
    desc = parse_excel_workbook(xlsx, version=1)
    assert desc.version == 1
    assert len(desc.meta_columns) >= 1
    kinds = {c.kind for c in desc.columns}
    assert KIND_OPEN_TEXT in kinds
    assert KIND_SINGLE_CHOICE in kinds
    assert KIND_MULTI_SELECT_OPTION in kinds
    assert any(c.header == "Who do you work with?" for c in desc.columns)
    assert desc.groups


def test_import_creates_versioned_json(tmp_path: Path):
    config = tmp_path / "project"
    json_folder = config / "json"
    json_folder.mkdir(parents=True)
    (json_folder / "project_config.json").write_text("{}", encoding="utf-8")
    xlsx = config / "ExportSample.xlsx"
    _write_sample_xlsx(xlsx)

    desc = import_export_format(
        xlsx,
        config,
        page_count=2,
        enrich=False,
    )
    assert desc.version == 1
    out_path = json_folder / "export_format.v1.json"
    assert out_path.is_file()
    loaded = load_active_export_format(config)
    assert loaded is not None
    assert loaded.version == 1
    assert next_export_format_version(json_folder) == 2


def test_check_applies_export_column_id(tmp_path: Path):
    col = ExportColumn(
        id="col_001",
        ordinal=1,
        header="Supplier Name",
        subheader="Open-Ended Response",
        kind=KIND_OPEN_TEXT,
        page_hint=1,
    )
    desc = ExportFormatDescriptor(
        schema_version=1,
        version=1,
        source={"filename": "t.xlsx"},
        meta_columns=[],
        columns=[col],
        groups=[],
    )
    field = TextField(
        colour=(0, 150, 150),
        name="Supplier",
        x=1,
        y=2,
        width=10,
        height=10,
        column_title="Wrong title",
        full_text="Supplier Name on form",
    )
    result = check_page_export_format(
        [field],
        desc,
        page_number=1,
        use_vlm=False,
    )
    assert result.proposals
    updated = apply_export_proposals([field], result.proposals)
    assert updated[0].column_title == "Supplier Name"
    assert updated[0].export_column_id == "col_001"
    assert updated[0].name == "Supplier"


def test_check_warning_for_unmatched_form_field():
    col = ExportColumn(
        id="col_001",
        ordinal=1,
        header="Only export question",
        subheader="Response",
        kind=KIND_SINGLE_CHOICE,
        page_hint=1,
    )
    desc = ExportFormatDescriptor(
        schema_version=1,
        version=1,
        source={},
        meta_columns=[],
        columns=[col],
        groups=[],
    )
    field = Tickbox(
        colour=(255, 0, 0),
        name="Extra on form",
        x=0,
        y=0,
        width=5,
        height=5,
        full_text="Extra question on printed form",
    )
    result = check_page_export_format(
        [field],
        desc,
        page_number=1,
        use_vlm=False,
    )
    assert any("no export column match" in w.lower() for w in result.warnings)


def test_export_columns_for_prompt_skips_meta():
    desc = ExportFormatDescriptor(
        schema_version=1,
        version=1,
        source={},
        meta_columns=[{"key": "Respondent ID", "role": "system"}],
        columns=[
            ExportColumn(
                id="col_meta",
                ordinal=1,
                header="Respondent ID",
                subheader="",
                kind=KIND_META,
                page_hint=1,
            ),
            ExportColumn(
                id="col_002",
                ordinal=2,
                header="Question A",
                subheader="Response",
                kind=KIND_SINGLE_CHOICE,
                page_hint=1,
            ),
        ],
        groups=[],
    )
    cols = export_columns_for_prompt(desc, 1)
    assert len(cols) == 1
    assert cols[0]["id"] == "col_002"


def test_validate_descriptor_rejects_duplicate_ids():
    data = {
        "schema_version": 1,
        "version": 1,
        "source": {},
        "meta_columns": [],
        "columns": [
            {"id": "col_001", "ordinal": 1, "header": "A", "subheader": "Response", "kind": "single_choice"},
            {"id": "col_001", "ordinal": 2, "header": "B", "subheader": "Response", "kind": "single_choice"},
        ],
        "groups": [],
    }
    with pytest.raises(ValueError, match="Duplicate"):
        validate_descriptor(data)
