#!/usr/bin/env python3
"""
Format/edit a Life post under content/life/ via an LLM, or delete a topic.

The dispatch ``slug`` field is a free-form **prompt**. The agent classifies it
into a target slug + optional edit instruction:

  - Empty prompt        -> use the body's first non-blank line as the slug.
                           If the post exists, preserve title/date/summary and
                           rewrite the body. Otherwise create a new post.
  - Non-empty prompt    -> a small LLM router emits JSON with target_slug,
                           instruction, and title_hint. The script then runs
                           one of: create / edit_with_instruction / preserve_meta.

Run build_life.py after writing. Used by GitHub Actions (repository_dispatch).

Env (upsert):
  GROQ_API_KEY    Groq (OpenAI-compatible at api.groq.com); preferred if set
  OPENAI_API_KEY  OpenAI; used if GROQ_API_KEY is unset
  LLM_MODEL       optional model id override
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = REPO_ROOT / "content" / "life"
LIFE_DIR = REPO_ROOT / "life"
EXEMPLAR = CONTENT_DIR / "welcome.md"

MAX_PROMPT_LEN = 500
MAX_HEADINGS_PER_POST = 8


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


def validate_prompt(raw: str) -> str:
    """Prompts are free text. Strip surrounding whitespace and reject path-like input."""
    p = (raw or "").strip()
    if len(p) > MAX_PROMPT_LEN:
        raise SystemExit(f"prompt too long (>{MAX_PROMPT_LEN} chars)")
    if "\x00" in p:
        raise SystemExit("invalid prompt: null byte")
    if ".." in p or "/" in p or "\\" in p:
        raise SystemExit("invalid prompt: path characters not allowed")
    return p


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


def _split_front_matter(text: str) -> tuple[str | None, str]:
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    return parts[1], parts[2].lstrip("\n")


def validate_front_matter(md: str) -> None:
    fm_raw, _ = _split_front_matter(md)
    if fm_raw is None:
        raise SystemExit("model output must start with YAML front matter (---)")
    fm = yaml.safe_load(fm_raw) or {}
    for key in ("title", "date", "summary"):
        if key not in fm:
            raise SystemExit(f"front matter must include {key!r}")
    if not str(fm.get("title", "")).strip():
        raise SystemExit("title must be non-empty")


def _load_existing_md(slug: str) -> tuple[dict, str, str]:
    """Return (front_matter_dict, body_str, full_text) for content/life/<slug>.md."""
    path = CONTENT_DIR / f"{slug}.md"
    if not path.is_file():
        raise SystemExit(f"no existing post for slug {slug!r}")
    raw = path.read_text(encoding="utf-8")
    fm_raw, body = _split_front_matter(raw)
    if fm_raw is None:
        raise SystemExit(f"existing post {slug!r} has no YAML front matter")
    fm = yaml.safe_load(fm_raw) or {}
    return fm, body, raw


def _front_matter_date(fm: dict) -> date | None:
    raw = fm.get("date")
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if raw is None:
        return None
    s = str(raw).strip()
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _extract_atx_headings(body: str, *, limit: int = MAX_HEADINGS_PER_POST) -> list[str]:
    """First N unique ATX Markdown headings (# .. ######) from the body, in order."""
    seen: set[str] = set()
    out: list[str] = []
    for line in body.splitlines():
        m = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
        if not m:
            continue
        text = m.group(2).strip()
        text = re.sub(r"\s+#+\s*$", "", text).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _list_existing_posts() -> list[dict]:
    """Return slug, title, and in-body ATX headings for every parseable post."""
    if not CONTENT_DIR.is_dir():
        return []
    out: list[dict] = []
    for path in sorted(CONTENT_DIR.iterdir()):
        if path.suffix.lower() != ".md" or path.name.startswith("."):
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm_raw, body = _split_front_matter(raw)
        if fm_raw is None:
            continue
        try:
            fm = yaml.safe_load(fm_raw) or {}
        except yaml.YAMLError:
            continue
        title = str(fm.get("title") or "").strip() or path.stem
        headings = _extract_atx_headings(body)
        title_cf = title.casefold()
        headings = [h for h in headings if h.casefold() != title_cf]
        out.append({"slug": path.stem, "title": title, "headings": headings})
    return out


def _stitch_front_matter(fm: dict, body_md: str) -> str:
    fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
    body = body_md.strip()
    return f"---\n{fm_text}\n---\n\n{body}\n"


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


def _llm_call(system: str, user: str, *, temperature: float = 0.4) -> str:
    client, model = _llm_client_and_model()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    content = resp.choices[0].message.content
    if not content:
        raise SystemExit("empty model response")
    return content


def _route_prompt(prompt: str, existing: list[dict], first_line: str) -> dict:
    """Classify the prompt into target_slug, instruction, title_hint via the LLM.

    Falls back to a deterministic slugification if the model returns malformed JSON.
    Always returns a dict with str values for those three keys.
    """
    fallback = {
        "target_slug": _slug_from_stem(prompt or first_line or "post"),
        "instruction": "",
        "title_hint": (first_line or prompt).strip(),
    }

    system = (
        "You route a blog edit dispatch. You receive a free-form PROMPT, the "
        "list of EXISTING posts (each has slug, title, and headings: Markdown "
        "# headings found in that post's body), and the FIRST_LINE of the new "
        "note body. Output ONLY a single JSON object with three string keys: "
        '"target_slug", "instruction", "title_hint". '
        "Rules: "
        "(1) If the PROMPT clearly refers to an existing post (by slug, by title, "
        "or by any string in that post's headings array), set target_slug to "
        "that exact existing slug. "
        "(2) Otherwise, slugify the PROMPT (lowercase, hyphens, alphanumerics only) "
        "into target_slug. If PROMPT is empty, use FIRST_LINE instead. "
        "(3) If the PROMPT reads as an instruction (verbs like 'add', 'remove', "
        "'rewrite', 'shorten', 'expand', 'fix', 'change'), put the instruction "
        "(without the slug part) in 'instruction'. Otherwise leave 'instruction' empty. "
        "(4) Use 'title_hint' as a clean human title for the post when creating; "
        "leave empty when editing an existing post. "
        "(5) Output JSON only, no prose, no code fences."
    )
    user = (
        f"PROMPT: {prompt}\n\n"
        f"EXISTING: {json.dumps(existing, ensure_ascii=False)}\n\n"
        f"FIRST_LINE: {first_line}"
    )

    try:
        raw = _llm_call(system, user, temperature=0)
    except SystemExit:
        raise
    except Exception as e:
        print(f"router LLM call failed: {e}; using deterministic fallback", file=sys.stderr)
        return fallback

    text = strip_markdown_fences(raw)
    start = text.find("{")
    endpos = text.rfind("}")
    if start == -1 or endpos == -1 or endpos < start:
        print(f"router returned non-JSON; using deterministic fallback. raw={text!r}", file=sys.stderr)
        return fallback
    try:
        parsed = json.loads(text[start : endpos + 1])
    except json.JSONDecodeError as e:
        print(f"router JSON decode failed ({e}); using deterministic fallback", file=sys.stderr)
        return fallback

    target = parsed.get("target_slug")
    if not isinstance(target, str) or not target.strip():
        target = fallback["target_slug"]
    target = _slug_from_stem(target)

    instruction = parsed.get("instruction") or ""
    if not isinstance(instruction, str):
        instruction = ""

    title_hint = parsed.get("title_hint") or ""
    if not isinstance(title_hint, str):
        title_hint = ""

    return {
        "target_slug": target,
        "instruction": instruction.strip(),
        "title_hint": title_hint.strip() or fallback["title_hint"],
    }


def _generate_full_post(slug: str, raw_text: str, *, title_hint: str = "") -> str:
    """Full regenerate (used in create mode). Returns full Markdown with front matter."""
    exemplar = EXEMPLAR.read_text(encoding="utf-8") if EXEMPLAR.is_file() else ""
    system = (
        "You convert rough notes into a single Markdown file for a static blog. "
        "Output ONLY the file content, no preamble. "
        "The file MUST start with YAML front matter between --- lines, with keys: "
        "title (string), date (ISO YYYY-MM-DD), summary (one short line). "
        "Then a blank line, then the body in Markdown (paragraphs, optional lists, **bold**, links). "
        "Use today's date if the note has no date. "
        "Infer a clear title and summary from the note. "
        "If a TITLE_HINT is provided, prefer it as the title (lightly cleaned up). "
        "Do not wrap the output in markdown code fences."
    )
    user = (
        "Here is an exemplar post (match tone and structure, not the topic):\n\n"
        f"{exemplar}\n\n---\n\n"
        f"Filename slug (for reference only; do not repeat as a heading): {slug}\n"
        f"TITLE_HINT (use as the title if reasonable): {title_hint}\n\n"
        f"Raw note to convert:\n\n{raw_text}"
    )
    md = strip_markdown_fences(_llm_call(system, user))
    validate_front_matter(md)
    return md


def _edit_post_with_prompt(existing_md: str, existing_date_iso: str, prompt: str, body_text: str) -> str:
    """Edit an existing post per the user's instructions. Preserves date."""
    system = (
        "You are editing an existing Life blog post. "
        "Apply the user's INSTRUCTIONS to the EXISTING FILE, using NEW NOTE TEXT as additional source material when relevant. "
        "Keep unchanged anything the instructions do not ask you to change. "
        "Output ONLY the full updated Markdown file, starting with YAML front matter "
        "between --- lines (keys: title, date, summary), then a blank line, then body. "
        "Do not wrap the output in markdown code fences."
    )
    user = (
        f"INSTRUCTIONS: {prompt}\n\n"
        f"EXISTING FILE (full Markdown with front matter):\n\n{existing_md}\n\n---\n\n"
        f"NEW NOTE TEXT (the user just wrote this; treat as the source of truth for any new content):\n\n{body_text}"
    )
    md = strip_markdown_fences(_llm_call(system, user))
    validate_front_matter(md)

    fm_raw, body = _split_front_matter(md)
    fm = yaml.safe_load(fm_raw) or {}
    fm["date"] = existing_date_iso
    return _stitch_front_matter(fm, body)


def _rewrite_body_only(existing_fm: dict, body_text: str) -> str:
    """Preserve existing front matter; ask LLM for a Markdown body from new note text."""
    system = (
        "You polish rough notes into the body of an existing blog post. "
        "Output ONLY Markdown body text (paragraphs, optional lists, **bold**, links). "
        "Do NOT include YAML front matter, do NOT include a title heading, "
        "do NOT wrap the output in markdown code fences."
    )
    user = (
        f"Existing post title (for tone only, do not repeat as a heading): {existing_fm.get('title', '')}\n\n"
        f"New note text to expand into the post body:\n\n{body_text}"
    )
    body_md = strip_markdown_fences(_llm_call(system, user)).strip()
    if not body_md:
        raise SystemExit("model returned empty body")
    fm = dict(existing_fm)
    d = _front_matter_date(fm)
    if d is not None:
        fm["date"] = d.isoformat()
    return _stitch_front_matter(fm, body_md)


def upsert_post(prompt: str, raw_text: str) -> tuple[Path, str]:
    """Apply the dispatch to content/life/. Returns (path, slug)."""
    body = raw_text.strip()
    first_line = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")

    if not prompt:
        if not first_line:
            raise SystemExit("nothing to update: empty prompt and empty body")
        target_slug = _slug_from_stem(first_line)
        instruction = ""
        title_hint = first_line
    else:
        existing = _list_existing_posts()
        routed = _route_prompt(prompt, existing, first_line)
        target_slug = _slug_from_stem(routed["target_slug"] or first_line or prompt)
        instruction = routed["instruction"]
        title_hint = routed["title_hint"] or first_line or prompt

    out_path = CONTENT_DIR / f"{target_slug}.md"

    if not out_path.is_file():
        if not body:
            raise SystemExit("nothing to create: empty note body")
        md = _generate_full_post(target_slug, body, title_hint=title_hint)
    else:
        existing_fm, _b, existing_md = _load_existing_md(target_slug)
        if instruction:
            existing_date = _front_matter_date(existing_fm)
            existing_date_iso = (existing_date or date.today()).isoformat()
            md = _edit_post_with_prompt(existing_md, existing_date_iso, instruction, body)
        else:
            if not body:
                raise SystemExit("nothing to update: empty body in preserve-meta mode")
            md = _rewrite_body_only(existing_fm, body)

    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md if md.endswith("\n") else md + "\n", encoding="utf-8")
    return out_path, target_slug


def delete_topic(slug: str) -> None:
    md = CONTENT_DIR / f"{slug}.md"
    html = LIFE_DIR / f"{slug}.html"
    if md.is_file():
        md.unlink()
    if html.is_file():
        html.unlink()


def main() -> int:
    p = argparse.ArgumentParser(description="Note -> content/life/*.md (Groq or OpenAI) or delete topic")
    sub = p.add_subparsers(dest="cmd", required=True)

    u = sub.add_parser("upsert", help="Edit (or create) a post under content/life/")
    u.add_argument(
        "--prompt",
        "--slug",
        dest="prompt",
        default="",
        help="Free-form prompt. Empty => use the body's first line as the slug.",
    )
    u.add_argument("--raw-file", required=True, help="Path to raw note text")

    d = sub.add_parser("delete", help="Remove content/life/<slug>.md and life/<slug>.html")
    d.add_argument("--slug", required=True)

    args = p.parse_args()

    if args.cmd == "upsert":
        prompt = validate_prompt(args.prompt)
        raw = Path(args.raw_file).read_text(encoding="utf-8")
        _path, slug = upsert_post(prompt, raw)
        run_build()
        print(f"slug={slug}")
    else:
        slug = validate_slug(args.slug)
        delete_topic(slug)
        run_build()
        print(f"slug={slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
