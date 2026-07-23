# Tests

## Purpose

Automated checks for validation and other testable project logic.

## Ownership

- Test modules under `tests/`; run with pytest from repo root (activate `.venv` first per root tooling rules)

## Local Contracts

- Prefer tests that assert real validation and business rules, not PyQt widget smoke unless explicitly requested

## Work Guidance

## Verification

- `pytest tests/`

## Child DOX Index

- `tests/validations/AGENTS.md` — validation-focused pytest modules
