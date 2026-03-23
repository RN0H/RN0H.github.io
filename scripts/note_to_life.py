#!/usr/bin/env python3
"""
Format a raw note into content/life/<slug>.md (YAML + Markdown) via an LLM,
or delete a topic. Run build_life.py after. Used by GitHub Actions (repository_dispatch).

Env (upsert — set one):
  GROQ_API_KEY — Groq (OpenAI-compatible API at api.groq.com); preferred if set
  OPENAI_API_KEY — OpenAI; used if GROQ_API_KEY is unset

Optional:
  LLM_MODEL — model id (Groq default: llama-3.3-70b-versatile; OpenAI default: gpt-4o-mini)
  SLUG — topic slug (Actions)
  NOTE_RAW_FILE — path to raw note text (upsert)
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = REPO_ROOT / "content" / "life"
LIFE_DIR = REPO_ROOT / "life"
EXEMPLAR = CONTENT_DIR / "welcome.md"


def _slug_from_stem(stem: str) -> str:
    s = stem.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "post"


def validate_slug(raw: str) -> str:
    s = _slug_from_stem(raw)
    if not s or len(s) > 80:
        raise SystemExit("invalid slug: empty or too long")
    if ".." in raw or "/" in raw or "\\" in raw:
        raise SystemExit("invalid slug: path characters")
    return s


def strip_slug_line(text: str) -> str:
    """Remove optional first line SLUG: foo from pasted note."""
    lines = text.splitlines()
    if not lines:
        return text
    m = re.match(r"^SLUG:\s*(\S+)\s*$", lines[0], re.I)
    if m:
        return "\n".join(lines[1:]).lstrip("\n")
    return text


def strip_markdown_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines)
    return t.strip()


def validate_front_matter(md: str) -> None:
    if not md.startswith("---"):
        raise SystemExit("model output must start with YAML front matter (---)")
    parts = md.split("---", 2)
    if len(parts) < 3:
        raise SystemExit("invalid markdown: missing closing --- after front matter")
    fm = yaml.safe_load(parts[1]) or {}
    for key in ("title", "date", "summary"):
        if key not in fm:
            raise SystemExit(f"front matter must include {key!r}")
    if not str(fm.get("title", "")).strip():
        raise SystemExit("title must be non-empty")


def run_build() -> None:
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "build_life.py")],
        cwd=str(REPO_ROOT),
        check=False,
    )
    if r.returncode != 0:
        raise SystemExit("build_life.py failed")


def _llm_model(default: str) -> str:
    m = os.environ.get("LLM_MODEL", "").strip()
    return m or default


def _llm_client_and_model() -> tuple[object, str]:
    """Return (OpenAI client, model name)."""
    try:
        from openai import OpenAI
    except ImportError as e:
        raise SystemExit("install openai package: pip install openai") from e

    groq = os.environ.get("GROQ_API_KEY", "").strip()
    oai = os.environ.get("OPENAI_API_KEY", "").strip()
    if groq:
        model = _llm_model("llama-3.3-70b-versatile")
        return OpenAI(api_key=groq, base_url="https://api.groq.com/openai/v1"), model
    if oai:
        model = _llm_model("gpt-4o-mini")
        return OpenAI(api_key=oai), model
    raise SystemExit("Set GROQ_API_KEY or OPENAI_API_KEY for upsert")


def upsert_post(slug: str, raw_text: str) -> Path:
    raw_text = strip_slug_line(raw_text)
    if not raw_text.strip():
        raise SystemExit("raw note is empty")

    exemplar = EXEMPLAR.read_text(encoding="utf-8") if EXEMPLAR.is_file() else ""

    client, model = _llm_client_and_model()
    system = (
        "You convert rough notes into a single Markdown file for a static blog. "
        "Output ONLY the file content, no preamble. "
        "The file MUST start with YAML front matter between --- lines, with keys: "
        "title (string), date (ISO YYYY-MM-DD), summary (one short line). "
        "Then a blank line, then the body in Markdown (paragraphs, optional lists, **bold**, links). "
        "Use today's date if the note has no date. "
        "Infer a clear title and summary from the note. "
        "Do not wrap the output in markdown code fences."
    )
    user = (
        "Here is an exemplar post (match tone and structure, not the topic):\n\n"
        f"{exemplar}\n\n---\n\n"
        f"Filename slug (for reference only; do not repeat as a heading): {slug}\n\n"
        f"Raw note to convert:\n\n{raw_text}"
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
    )
    content = resp.choices[0].message.content
    if not content:
        raise SystemExit("empty model response")
    md = strip_markdown_fences(content)
    validate_front_matter(md)

    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    out = CONTENT_DIR / f"{slug}.md"
    out.write_text(md + ("\n" if not md.endswith("\n") else ""), encoding="utf-8")
    return out


def delete_topic(slug: str) -> None:
    md = CONTENT_DIR / f"{slug}.md"
    html = LIFE_DIR / f"{slug}.html"
    if md.is_file():
        md.unlink()
    if html.is_file():
        html.unlink()


def main() -> int:
    p = argparse.ArgumentParser(description="Note → content/life/*.md (Groq or OpenAI) or delete topic")
    sub = p.add_subparsers(dest="cmd", required=True)

    u = sub.add_parser("upsert", help="Format note and write content/life/<slug>.md")
    u.add_argument("--slug", required=True)
    u.add_argument("--raw-file", required=True, help="Path to raw note text")

    d = sub.add_parser("delete", help="Remove content/life/<slug>.md and life/<slug>.html")
    d.add_argument("--slug", required=True)

    args = p.parse_args()
    slug = validate_slug(args.slug)

    if args.cmd == "upsert":
        raw = Path(args.raw_file).read_text(encoding="utf-8")
        upsert_post(slug, raw)
    else:
        delete_topic(slug)

    run_build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
