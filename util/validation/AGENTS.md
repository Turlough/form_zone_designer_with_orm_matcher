# Validation

## Purpose

Project-wide and per-field validation used during indexing and QC.

## Ownership

- `project_validations.py`, `field_validations.py`, `strategies.py`, and package `__init__.py`
- Exported to apps as `ProjectValidations` from `util`

## Local Contracts

- Add or change rules here rather than scattering validation in UI or `app_indexer.py`
- Keep strategies pluggable; field validators should align with types in `fields.py`
- `sum_should_equal_total`: `field_names[0]` is the total; the rest are added. A blank total counts as 0, so a non-zero sum is a fault on the total field's page. Non-numeric parts are their own faults and are not added in.

## Work Guidance

## Verification

- `tests/validations/` — pytest coverage for project and indexer validation behavior

## Child DOX Index
