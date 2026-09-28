"""Defaults for Exporter online-compat dialog (template beside export_config)."""

from __future__ import annotations

from pathlib import Path

from util.export_online_compat import load_export_config


def default_template_xlsx(config_path: Path, config_dir: Path) -> Path | None:
    """Prefer export_config template_xlsx in config_dir, else newest .xlsx in that folder."""
    config_dir = config_dir.resolve()
    if config_path.is_file():
        try:
            cfg = load_export_config(config_path)
            name = (cfg.get("template_xlsx") or "").strip()
            if name:
                candidate = (config_dir / name).resolve()
                if candidate.is_file():
                    return candidate
        except (OSError, ValueError):
            pass

    xlsx_files = [p for p in config_dir.glob("*.xlsx") if p.is_file()]
    if not xlsx_files:
        return None
    return max(xlsx_files, key=lambda p: p.stat().st_mtime)
