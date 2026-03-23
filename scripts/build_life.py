#!/usr/bin/env python3
"""
Build static HTML for the Life section from content/life/*.md and *.txt.
Run from repo root: python3 scripts/build_life.py
"""
from __future__ import annotations

import html
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import markdown
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = REPO_ROOT / "content" / "life"
OUT_DIR = REPO_ROOT / "life"

# Figma portfolio (same URL as home hub); escaped for HTML attributes in templates.
PORTFOLIO_HTML = (
    "https://www.figma.com/proto/1QYSxK2zIzMW66vPCMEib4/MyPortfolio"
    "?node-id=118%3A2&amp;scaling=min-zoom&amp;page-id=0%3A1&amp;starting-point-node-id=118%3A2"
)


@dataclass
class Post:
    slug: str
    title: str
    date: date
    summary: str
    body_html: str
    source_name: str


def _slug_from_stem(stem: str) -> str:
    s = stem.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "post"


def _parse_date(raw: object) -> date:
    if raw is None:
        return date.today()
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return date.today()


def _parse_txt(text: str) -> tuple[dict[str, str], str]:
    """Parse TITLE:/DATE:/SUMMARY: header and body after first --- line."""
    lines = text.splitlines()
    meta: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(TITLE|DATE|SUMMARY)\s*:\s*(.*)$", line, re.I)
        if m:
            meta[m.group(1).lower()] = m.group(2).strip().strip('"').strip("'")
            i += 1
            continue
        if line.strip() == "---":
            i += 1
            break
        if line.strip() == "" and meta:
            i += 1
            continue
        break
    body = "\n".join(lines[i:]).lstrip("\n")
    return meta, body


def _split_front_matter_md(text: str) -> tuple[str | None, str]:
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    return parts[1], parts[2].lstrip("\n")


def _load_post(path: Path) -> Post:
    raw = path.read_text(encoding="utf-8")
    stem_slug = _slug_from_stem(path.stem)

    if path.suffix.lower() == ".txt":
        meta, body = _parse_txt(raw)
        title = meta.get("title") or stem_slug.replace("-", " ").title()
        d = _parse_date(meta.get("date"))
        summary = meta.get("summary") or ""
        body_html = _render_body_markdown(body)
        return Post(
            slug=stem_slug,
            title=title,
            date=d,
            summary=summary,
            body_html=body_html,
            source_name=path.name,
        )

    # .md: YAML front matter
    fm_raw, body = _split_front_matter_md(raw)
    if fm_raw is None:
        body_html = _render_body_markdown(raw)
        return Post(
            slug=stem_slug,
            title=path.stem.replace("-", " ").title(),
            date=date.today(),
            summary="",
            body_html=body_html,
            source_name=path.name,
        )
    fm = yaml.safe_load(fm_raw) or {}
    title = str(fm.get("title") or path.stem).strip()
    d = _parse_date(fm.get("date"))
    summary = str(fm.get("summary") or "").strip()
    body_html = _render_body_markdown(body)
    slug = str(fm.get("slug") or "").strip() or stem_slug
    slug = _slug_from_stem(slug)
    return Post(
        slug=slug,
        title=title,
        date=d,
        summary=summary,
        body_html=body_html,
        source_name=path.name,
    )


def _render_body_markdown(body: str) -> str:
    body = body.strip()
    if not body:
        return ""
    return markdown.markdown(body, extensions=["extra"], output_format="html5")


def _page_shell(title: str, body_inner: str, relpath_to_root: str) -> str:
    css_href = f"{relpath_to_root}style.css"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} · Life</title>
  <link rel="stylesheet" href="{css_href}">
</head>
<body class="life-page">
  <header class="life-header">
    <a class="life-nav" href="{relpath_to_root}index.html">Home</a>
    <span class="life-nav-sep">·</span>
    <a class="life-nav" href="{relpath_to_root}academia/index.html">Academia</a>
    <span class="life-nav-sep">·</span>
    <a class="life-nav" href="{PORTFOLIO_HTML}" target="_blank" rel="noopener noreferrer">Portfolio</a>
    <span class="life-nav-sep">·</span>
    <a class="life-nav" href="{relpath_to_root}life/index.html">Life</a>
  </header>
  <main class="life-main">
{body_inner}
  </main>
  <footer class="life-footer">
    <p>Rohan Panicker</p>
  </footer>
</body>
</html>
"""


def _build_index(posts: list[Post]) -> str:
    posts = sorted(posts, key=lambda p: (p.date, p.title), reverse=True)
    items = []
    for p in posts:
        href = f"{p.slug}.html"
        sum_line = (
            f'      <p class="life-card-summary">{html.escape(p.summary)}</p>\n'
            if p.summary
            else ""
        )
        items.append(f"""    <article class="life-card">
      <h2 class="life-card-title"><a href="{html.escape(href)}">{html.escape(p.title)}</a></h2>
      <p class="life-card-meta"><time datetime="{p.date.isoformat()}">{p.date.isoformat()}</time></p>
{sum_line}    </article>""")
    list_html = "\n".join(items) if items else "    <p class=\"life-empty\">No posts yet. Add a file under <code>content/life/</code> and run the build script.</p>"
    inner = f"""    <h1 class="life-h1">Life &amp; thoughts</h1>
    <p class="life-lead">Notes on living, habits, and ideas—published as plain files, built to static HTML.</p>
    <section class="life-list">
{list_html}
    </section>"""
    return _page_shell("Life & thoughts", inner, "../")


def _build_post_page(p: Post) -> str:
    inner = f"""    <article class="life-article">
      <h1 class="life-h1">{html.escape(p.title)}</h1>
      <p class="life-meta"><time datetime="{p.date.isoformat()}">{p.date.isoformat()}</time></p>
      <div class="life-body">
{p.body_html}
      </div>
    </article>
    <p class="life-back"><a href="index.html">&larr; All posts</a></p>"""
    return _page_shell(p.title, inner, "../")


def main() -> int:
    if not CONTENT_DIR.is_dir():
        print(f"Missing content directory: {CONTENT_DIR}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    posts: list[Post] = []
    for path in sorted(CONTENT_DIR.iterdir()):
        if path.suffix.lower() not in (".md", ".txt"):
            continue
        if path.name.startswith("."):
            continue
        try:
            posts.append(_load_post(path))
        except Exception as e:
            print(f"Error loading {path}: {e}", file=sys.stderr)
            return 1

    # Unique slugs (second and later duplicates get -2, -3, ...)
    by_slug: dict[str, list[Post]] = {}
    for p in posts:
        by_slug.setdefault(p.slug, []).append(p)
    for base, plist in by_slug.items():
        if len(plist) < 2:
            continue
        for i, p in enumerate(plist):
            if i:
                p.slug = f"{base}-{i + 1}"

    index_html = _build_index(posts)
    (OUT_DIR / "index.html").write_text(index_html, encoding="utf-8")

    for p in posts:
        page = _build_post_page(p)
        (OUT_DIR / f"{p.slug}.html").write_text(page, encoding="utf-8")

    print(f"Wrote {len(posts)} post(s) to {OUT_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
