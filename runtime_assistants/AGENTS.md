# Runtime assistants

## Purpose

Optional AI-assisted runtime modules invoked from apps (not Cursor-only rules under `.cursor/`).

## Ownership

- One subfolder per assistant; shared env keys documented here

## Local Contracts

- Assistants call **external** VLMs over the network (PyInstaller builds ship no local model)
- Assistants are side-effect free until the host app applies results
- API keys: reuse project `.env` conventions (`GOOGLE_API_KEY`, `GEMINI_API_KEY`); never embed keys in the binary
- No PyQt imports inside assistant packages

## Work Guidance

- Keep prompts and JSON schema versioned in the assistant subfolder
- Host apps run long calls off the UI thread; handle offline/missing-key gracefully

## Verification

- Unit tests under `tests/` for schema and conversion; no live API in CI

## Child DOX Index

- `runtime_assistants/design_assistant/AGENTS.md` — Designer page analysis VLM pipeline
