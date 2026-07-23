"""Generate static HTML operator docs from USER_INSTRUCTIONS/*.md."""

from __future__ import annotations

import html
import re
from pathlib import Path

try:
    import markdown
except ImportError as e:
    raise SystemExit(
        "Install markdown: pip install markdown (then re-run build_html.py)"
    ) from e

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "html"

PAGES: list[tuple[str, str, Path]] = [
    ("templates.html", "1. Templates & setup", ROOT / "INSTRUCTIONS-1-Templates.md"),
    ("designer.html", "2. Designer", ROOT / "INSTRUCTIONS-2-Designer.md"),
    ("indexer.html", "3. Indexer", ROOT / "INSTRUCTIONS-3-Indexer.md"),
    ("exporter.html", "4. Exporter", ROOT / "INSTRUCTIONS-4-Exporter.md"),
    ("agents.html", "Documentation index", ROOT / "AGENTS.md"),
]

NAV = [(filename, label) for filename, label, _ in PAGES]


def md_to_body(source: str, *, empty_message: str = "TODO") -> str:
    text = source.strip()
    if not text:
        return f'<p class="todo">{html.escape(empty_message)}</p>'
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "nl2br"],
        extension_configs={"fenced_code": {"lang_prefix": "language-"}},
    )
    return md.convert(text)


def render_page(active: str, title: str, body_html: str) -> str:
    nav_items = "\n".join(
        f'        <li><a href="{fn}" class="{"active" if fn == active else ""}">{html.escape(lbl)}</a></li>'
        for fn, lbl in NAV
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} — Form indexing suite</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <nav class="sidebar" aria-label="Instructions">
    <div class="sidebar-brand">User instructions</div>
    <ul class="nav-list">
{nav_items}
    </ul>
  </nav>
  <main class="content">
    <article class="doc">
{body_html}
    </article>
  </main>
</body>
</html>
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for filename, nav_label, md_path in PAGES:
        source = md_path.read_text(encoding="utf-8") if md_path.is_file() else ""
        body = md_to_body(source)
        # First h1 from markdown for document title if present
        m = re.search(r"^#\s+(.+)$", source.strip(), re.MULTILINE)
        doc_title = m.group(1).strip() if m else nav_label.split(". ", 1)[-1]
        page = render_page(filename, doc_title, body)
        (OUT / filename).write_text(page, encoding="utf-8", newline="\n")
        print(f"Wrote {OUT / filename}")

    index = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url=templates.html">
  <title>User instructions</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <p><a href="templates.html">Continue to instructions</a></p>
</body>
</html>
"""
    (OUT / "index.html").write_text(index, encoding="utf-8", newline="\n")
    print(f"Wrote {OUT / 'index.html'}")


if __name__ == "__main__":
    main()
