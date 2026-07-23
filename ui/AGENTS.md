# UI package

## Purpose

PyQt6 widgets, panels, dialogs, and layouts shared by Designer, Indexer, and related tools.

## Ownership

- Widgets under `ui/`; re-export public surfaces from `ui/__init__.py`
- Application shells and orchestration stay in repo-root `app_*.py` files

## Local Contracts

- Designer-facing: thumbnails, main image, edit panel, grid designer, rectangle selection dialog
- Indexer-facing: main image panel, details panel, menus, OCR/index/comment/QC dialogs
- Prefer extending existing widgets over duplicating paint or layout logic in entry-point apps

## Work Guidance

## Verification

## Child DOX Index
