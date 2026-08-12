"""Schema validation for export format descriptors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = 1

KNOWN_META_KEYS = frozenset(
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

KIND_OPEN_TEXT = "open_text"
KIND_SINGLE_CHOICE = "single_choice"
KIND_MULTI_SELECT_OPTION = "multi_select_option"
KIND_META = "meta"
KIND_UNKNOWN = "unknown"


@dataclass
class ExportColumn:
    id: str
    ordinal: int
    header: str
    subheader: str
    kind: str
    page_hint: int | None = None
    group_id: str | None = None
    notes: str = ""

    def delivery_title(self) -> str:
        """Column heading as it should appear in delivery export."""
        header = (self.header or "").strip()
        sub = (self.subheader or "").strip()
        if self.kind == KIND_MULTI_SELECT_OPTION and sub:
            return sub
        if self.kind == KIND_SINGLE_CHOICE:
            return header
        if self.kind == KIND_OPEN_TEXT:
            return header
        if sub and sub not in ("Response", "Open-Ended Response"):
            return sub
        return header or sub

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "ordinal": self.ordinal,
            "header": self.header,
            "subheader": self.subheader,
            "kind": self.kind,
            "notes": self.notes or "",
        }
        if self.page_hint is not None:
            data["page_hint"] = self.page_hint
        if self.group_id:
            data["group_id"] = self.group_id
        return data

    @staticmethod
    def from_dict(data: dict) -> "ExportColumn":
        return ExportColumn(
            id=str(data.get("id") or ""),
            ordinal=int(data.get("ordinal") or 0),
            header=str(data.get("header") or "").strip(),
            subheader=str(data.get("subheader") or "").strip(),
            kind=str(data.get("kind") or KIND_UNKNOWN),
            page_hint=data.get("page_hint"),
            group_id=data.get("group_id") or None,
            notes=str(data.get("notes") or ""),
        )


@dataclass
class ExportGroup:
    id: str
    header: str
    kind: str
    column_ids: list[str] = field(default_factory=list)
    page_hint: int | None = None

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "header": self.header,
            "kind": self.kind,
            "column_ids": list(self.column_ids),
        }
        if self.page_hint is not None:
            data["page_hint"] = self.page_hint
        return data

    @staticmethod
    def from_dict(data: dict) -> "ExportGroup":
        return ExportGroup(
            id=str(data.get("id") or ""),
            header=str(data.get("header") or "").strip(),
            kind=str(data.get("kind") or "unknown"),
            column_ids=[str(x) for x in (data.get("column_ids") or [])],
            page_hint=data.get("page_hint"),
        )


@dataclass
class ExportFormatDescriptor:
    schema_version: int
    version: int
    source: dict
    meta_columns: list[dict]
    columns: list[ExportColumn]
    groups: list[ExportGroup]
    warnings_from_ingest: list[str] = field(default_factory=list)

    def column_by_id(self, column_id: str) -> ExportColumn | None:
        for col in self.columns:
            if col.id == column_id:
                return col
        return None

    def columns_for_page(self, page_number: int) -> list[ExportColumn]:
        """Return non-meta columns with matching page_hint (1-based)."""
        out = []
        for col in self.columns:
            if col.kind == KIND_META:
                continue
            if col.page_hint == page_number:
                out.append(col)
        return out

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "version": self.version,
            "source": dict(self.source),
            "meta_columns": list(self.meta_columns),
            "columns": [c.to_dict() for c in self.columns],
            "groups": [g.to_dict() for g in self.groups],
            "warnings_from_ingest": list(self.warnings_from_ingest),
        }

    @staticmethod
    def from_dict(data: dict) -> "ExportFormatDescriptor":
        return ExportFormatDescriptor(
            schema_version=int(data.get("schema_version") or SCHEMA_VERSION),
            version=int(data.get("version") or 1),
            source=dict(data.get("source") or {}),
            meta_columns=list(data.get("meta_columns") or []),
            columns=[ExportColumn.from_dict(c) for c in (data.get("columns") or [])],
            groups=[ExportGroup.from_dict(g) for g in (data.get("groups") or [])],
            warnings_from_ingest=list(data.get("warnings_from_ingest") or []),
        )


def validate_descriptor(data: dict) -> ExportFormatDescriptor:
    desc = ExportFormatDescriptor.from_dict(data)
    if desc.schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported export format schema_version: {desc.schema_version}")
    if not desc.columns:
        raise ValueError("Export format descriptor has no columns")
    seen_ids: set[str] = set()
    for col in desc.columns:
        if not col.id:
            raise ValueError("Export column missing id")
        if col.id in seen_ids:
            raise ValueError(f"Duplicate export column id: {col.id}")
        seen_ids.add(col.id)
    return desc


def new_source_metadata(filename: str, *, notes: str = "") -> dict:
    return {
        "filename": filename,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "notes": notes,
    }
