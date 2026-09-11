"""Load Designer page JSON the same way Indexer/Exporter expand RadioGrids."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from fields import Field, RadioGrid
from util.designer_persistence import iter_page_json_paths, iter_runtime_fields


def _kind(field: Field) -> str:
    name = type(field).__name__
    if name in {"Tickbox", "SignatureField", "RadioButton"}:
        return "tick"
    if name in {"RadioGroup", "NumericRadioGroup"}:
        return "radio"
    return "text"


@dataclass(frozen=True)
class JsonField:
    page: int
    type: str
    kind: str
    name: str
    column_title: str
    full_text: str
    question_number: str


@dataclass(frozen=True)
class RadioGridInfo:
    page: int
    name: str
    orientation: str
    n_rows: int
    n_cols: int
    row_labels: list[str]
    col_labels: list[str]
    column_title: str
    full_text: str
    question_number: str


def load_runtime_fields(json_dir: str | Path) -> list[JsonField]:
    out: list[JsonField] = []
    for page, field in iter_runtime_fields(json_dir):
        out.append(
            JsonField(
                page=page,
                type=type(field).__name__,
                kind=_kind(field),
                name=(field.name or "").strip(),
                column_title=(getattr(field, "column_title", None) or "").strip(),
                full_text=(getattr(field, "full_text", None) or "").strip(),
                question_number=(getattr(field, "question_number", None) or "").strip(),
            )
        )
    return out


def load_radio_grids(json_dir: str | Path) -> list[RadioGridInfo]:
    out: list[RadioGridInfo] = []
    for page, path in iter_page_json_paths(json_dir):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            field = Field.from_dict(item)
            if not isinstance(field, RadioGrid):
                continue
            out.append(
                RadioGridInfo(
                    page=page,
                    name=(field.name or "").strip(),
                    orientation=(field.orientation or "").strip(),
                    n_rows=len(field.row_labels or []),
                    n_cols=len(field.col_labels or []),
                    row_labels=list(field.row_labels or []),
                    col_labels=list(field.col_labels or []),
                    column_title=(field.column_title or "").strip(),
                    full_text=(field.full_text or "").strip(),
                    question_number=(field.question_number or "").strip(),
                )
            )
    return out


def duplicate_names(fields: list[JsonField]) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for f in fields:
        if not f.name:
            continue
        found.setdefault(f.name, []).append(f.page)
    return {n: pages for n, pages in found.items() if len(pages) > 1}


def missing_column_titles(fields: list[JsonField]) -> list[JsonField]:
    return [f for f in fields if not f.column_title]
