# Validation

## Purpose

Project-wide and per-field validation used during indexing and QC.

## Ownership

- `project_validations.py`, `field_validations.py`, `strategies.py`, and package `__init__.py`
- Exported to apps as `ProjectValidations` from `util`

## Local Contracts

- Add or change rules here rather than scattering validation in UI or `app_indexer.py`
- Keep strategies pluggable; field validators should align with types in `fields.py`

## Work Guidance

## Verification

- `tests/validations/` — pytest coverage for project and indexer validation behavior

## Child DOX Index
