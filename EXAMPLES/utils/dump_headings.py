"""Print Designer JSON fields and Qualtrics Excel headings for a chat review.

Does not pair or judge mismatches. Matching stays in chat per EXAMPLES/AGENTS.md.

Usage (from repo root, project venv):

    python EXAMPLES/utils/dump_headings.py EXAMPLES/RoI
    python EXAMPLES/utils/dump_headings.py EXAMPLES/NI
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_UTILS = Path(__file__).resolve().parent
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

from designer_fields import (
    duplicate_names,
    load_radio_grids,
    load_runtime_fields,
    missing_column_titles,
)
from qualtrics_headers import load_qualtrics_headers


def _survey_paths(survey_dir: Path) -> tuple[Path, Path]:
    json_dir = survey_dir / "json"
    if not json_dir.is_dir():
        raise SystemExit(f"No json/ folder in {survey_dir}")
    xlsx = sorted(survey_dir.glob("*.xlsx"))
    if not xlsx:
        raise SystemExit(f"No .xlsx in {survey_dir}")
    return json_dir, xlsx[0]


def _clip(text: str, n: int = 100) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("survey_dir", type=Path, help="Survey pack (contains json/ and a .xlsx)")
    args = parser.parse_args(argv)
    survey_dir = args.survey_dir.resolve()
    json_dir, xlsx = _survey_paths(survey_dir)

    fields = load_runtime_fields(json_dir)
    grids = load_radio_grids(json_dir)
    excel = load_qualtrics_headers(xlsx)
    dups = duplicate_names(fields)
    missing = missing_column_titles(fields)

    print(f"SURVEY {survey_dir.name}")
    print(f"JSON   {json_dir}  fields={len(fields)}  grids={len(grids)}")
    print(f"XLSX   {xlsx.name}  sheet={excel.sheet!r}  survey_cols={len(excel.columns)}  meta={len(excel.meta)}")
    print(f"DEPTH  header_rows=2  data_rows={excel.data_rows}  total_rows={excel.total_rows}")
    if excel.data_rows <= 2:
        print("NOTE   dummy/header sample — enough for headings and types, not radio labels")

    print("\n=== JSON fields (page order, RadioGrids expanded) ===")
    for f in fields:
        title = f.column_title or "-"
        print(
            f"p{f.page:02d} {f.type:<16} {f.kind:<5} "
            f"qn={(f.question_number or '-'):<6} "
            f"name={f.name!r}  title={title!r}  full={_clip(f.full_text)!r}"
        )

    print("\n=== Excel survey columns (meta skipped, row1 forward-filled) ===")
    for c in excel.columns:
        print(f"c{c.col:03d} {c.kind:<5} sub={c.sub!r}  stem={_clip(c.stem, 90)!r}")

    print("\n=== RadioGrids (before expand) ===")
    if not grids:
        print("(none)")
    for g in grids:
        print(
            f"p{g.page:02d} {g.orientation:<10} {g.n_rows}x{g.n_cols} "
            f"name={g.name!r}  cols={g.col_labels!r}  qn={g.question_number or '-'}"
        )

    print("\n=== Duplicate name ===")
    if not dups:
        print("(none)")
    for name, pages in sorted(dups.items()):
        print(f"  {name!r} pages={pages}")

    print("\n=== Missing column_title ===")
    if not missing:
        print("(none)")
    for f in missing:
        print(f"  p{f.page:02d} {f.type} {f.name!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
