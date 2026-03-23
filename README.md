# RN0H.github.io

Public site: [https://rn0h.github.io/](https://rn0h.github.io/)

## Site map

| Section | Description |
|--------|-------------|
| [index.html](index.html) | **Home** — links to Academia, Portfolio (Figma), and Life |
| [academia/index.html](academia/index.html) | Research, experience, projects, publications |
| Portfolio | Interactive **Figma** prototype (external) |
| [life/index.html](life/index.html) | **Life & thoughts** — posts built from plain files |

Branches **master** and **new_website** can stay in sync; merge into **master** for the default GitHub Pages branch if you use branch-based publishing.

## Life & thoughts (file-based posts)

Posts live in [`content/life/`](content/life/). You do **not** edit HTML for each new article.

### Add a new post

1. Create a new file in `content/life/`:

   - **Markdown (recommended):** `something.md` with YAML front matter and Markdown body:

     ```markdown
     ---
     title: "Your title"
     date: 2025-03-22
     summary: "Optional one line for the index."
     ---

     Your paragraphs here. Use **Markdown** for emphasis, lists, and links.
     ```

   - **Plain text:** `something.txt` with this shape:

     ```text
     TITLE: Your title
     DATE: 2025-03-22
     SUMMARY: Optional one line

     ---

     Body paragraphs separated by blank lines.
     ```

2. **Build** static HTML (from the repo root):

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/python scripts/build_life.py
   ```

   This updates [`life/`](life/) (`index.html` plus one HTML file per post).

3. **Publish:** commit the changes (including generated files under `life/`) and push, e.g. `./upload.sh "Add life post"`.

   If **GitHub Actions** is enabled for Pages, pushing without running the build locally still works—the workflow runs `scripts/build_life.py` before deploy.

### GitHub Pages with Actions

1. Repository **Settings → Pages → Build and deployment → Source**: choose **GitHub Actions**.
2. Pushes to `master` (and `new_website` if listed in the workflow) run [`.github/workflows/pages.yml`](.github/workflows/pages.yml): install dependencies, build Life pages, upload the full site as the Pages artifact.

## Layout

| Path | Role |
|------|------|
| [`index.html`](index.html) | Home hub |
| [`style.css`](style.css) | Dark theme for home + Life |
| [`stylesheet.css`](stylesheet.css) | Academia page styling |
| [`content/life/`](content/life/) | **Source** posts (your edits) |
| [`life/`](life/) | **Generated** listing + post pages |
| [`scripts/build_life.py`](scripts/build_life.py) | Builds `life/` from `content/life/` |
