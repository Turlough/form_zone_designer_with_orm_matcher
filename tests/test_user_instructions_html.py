"""Tests for USER_INSTRUCTIONS HTML path resolution (Designer Help)."""

import sys
from pathlib import Path

from util.path_utils import application_root, user_instructions_html_path


def test_user_instructions_html_path_finds_designer_and_templates():
    designer = user_instructions_html_path("designer.html")
    templates = user_instructions_html_path("templates.html")
    assert designer is not None and designer.is_file()
    assert templates is not None and templates.is_file()
    assert designer.parent == templates.parent
    assert designer.parent.name == "html"
    assert designer.parent.parent.name == "USER_INSTRUCTIONS"


def test_user_instructions_html_path_rejects_missing():
    assert user_instructions_html_path("no-such-help.html") is None


def test_user_instructions_html_path_uses_meipass_when_frozen(tmp_path: Path, monkeypatch):
    html_dir = tmp_path / "USER_INSTRUCTIONS" / "html"
    html_dir.mkdir(parents=True)
    target = html_dir / "designer.html"
    target.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    found = user_instructions_html_path("designer.html")
    assert found == target


def test_application_root_is_repo_when_not_frozen():
    assert (application_root() / "app_designer.py").is_file()
