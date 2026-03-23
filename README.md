# RN0H.github.io

Public site: [https://rn0h.github.io/](https://rn0h.github.io/)

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

   Alternatively, if **GitHub Actions** is enabled for Pages (see below), pushing without running the build locally still works—the workflow runs `scripts/build_life.py` before deploy.

### GitHub Pages with Actions

1. Repository **Settings → Pages → Build and deployment → Source**: choose **GitHub Actions**.
2. Pushes to `master` run [`.github/workflows/pages.yml`](.github/workflows/pages.yml): install dependencies, build Life pages, upload the full site as the Pages artifact.

You can still deploy only with `upload.sh` and committed `life/*.html` if you prefer not to use Actions.

## Layout

| Path | Role |
|------|------|
| [`index.html`](index.html) | Home: links to portfolio (Figma) and Life section |
| [`style.css`](style.css) | Shared styles |
| [`content/life/`](content/life/) | **Source** posts (your edits) |
| [`life/`](life/) | **Generated** listing + post pages (run build script) |
| [`scripts/build_life.py`](scripts/build_life.py) | Builds `life/` from `content/life/` |
