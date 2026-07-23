# Util package

## Purpose

Non-UI services: ORM logo matching, document loading, persistence, CSV/index I/O, OCR clients, paths, and shared app state.

## Ownership

- Modules under `util/`; package exports in `util/__init__.py` define the primary import surface for apps
- Field-type definitions and factories live at repo root (`fields.py`, `field_factory.py`, `page.py`), not here

## Local Contracts

- Apps import shared capabilities via `util` (e.g. `ORMMatcher`, `CSVManager`, `ProjectValidations`, designer persistence helpers)
- Validation rules and strategies live in `util/validation/` (see child DOX)
- Environment and project paths: respect `util/path_utils.py` and `util/app_state.py` conventions

## Work Guidance

## Verification

## Child DOX Index

- `util/validation/AGENTS.md` — project- and field-level validation strategies and rules
