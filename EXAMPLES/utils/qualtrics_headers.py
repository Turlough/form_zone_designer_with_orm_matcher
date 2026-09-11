"""Load Qualtrics-style two-row Excel headers for a chat heading check.

Does not import ``export_assistant_for_designer``. Named row-2 cells stay
``named`` (tick option or matrix/numeric subfield); classify in chat.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

META_STEMS = frozenset(
    {
        "Respondent ID",
        "Collector ID",
        "Start Date",
        "End Date",
        "IP Address",
        "Email Address",
        "First Name",
        "Last Name",
        "Custom Data 1",
    }
)


def _cell(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _forward_fill(headers: list[str]) -> list[str]:
    filled: list[str] = []
    last = ""
    for h in headers:
        if h:
            last = h
        filled.append(last)
    return filled


def _kind(sub: str) -> str:
    if sub == "Response":
        return "radio"
    if sub == "Open-Ended Response":
        return "text"
    if sub:
        return "named"
    return "empty"


@dataclass(frozen=True)
class ExcelColumn:
    col: int
    stem: str
    sub: str
    kind: str


@dataclass(frozen=True)
class ExcelHeaders:
    sheet: str
    columns: list[ExcelColumn]
    meta: list[ExcelColumn]
    data_rows: int
    total_rows: int


def load_qualtrics_headers(path: str | Path, *, sheet: str | None = None) -> ExcelHeaders:
    """Parse row 1 (stems, forward-filled) and row 2 (subheaders) from one sheet."""
    try:
        from openpyxl import load_workbook
    except ImportError as e:
        raise RuntimeError(
            "openpyxl is required for EXAMPLES heading dumps. "
            "Activate the project venv and pip install openpyxl."
        ) from e

    path = Path(path)
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        name = sheet or wb.sheetnames[0]
        ws = wb[name]
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()

    if len(rows) < 2:
        raise ValueError(f"{path} first sheet must have at least two header rows")

    row1 = [_cell(v) for v in rows[0]]
    row2 = [_cell(v) for v in rows[1]]
    width = max(len(row1), len(row2))
    row1 += [""] * (width - len(row1))
    row2 += [""] * (width - len(row2))
    filled = _forward_fill(row1)

    survey: list[ExcelColumn] = []
    meta: list[ExcelColumn] = []
    for i, (stem, sub) in enumerate(zip(filled, row2), start=1):
        if not stem and not sub:
            continue
        col = ExcelColumn(col=i, stem=stem, sub=sub, kind=_kind(sub))
        if stem in META_STEMS:
            meta.append(col)
        else:
            survey.append(col)

    data_rows = 0
    for row in rows[2:]:
        if any(_cell(v) for v in row):
            data_rows += 1

    return ExcelHeaders(
        sheet=name,
        columns=survey,
        meta=meta,
        data_rows=data_rows,
        total_rows=len(rows),
    )
