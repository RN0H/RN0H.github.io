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
| [`scripts/note_to_life.py`](scripts/note_to_life.py) | Used by Actions: OpenAI → `content/life/<slug>.md`, then `build_life.py` |

## Publish from iPad / iPhone (Notes → Pull Request)

Apple Notes does not sync to GitHub. The intended flow is: **copy the note** → run an **Apple Shortcut** that **Base64-encodes** the text and **POSTs** a [`repository_dispatch`](https://docs.github.com/en/rest/repos/repos#create-a-repository-dispatch-event) to GitHub. A workflow ([`.github/workflows/note-to-life-pr.yml`](.github/workflows/note-to-life-pr.yml)) verifies a shared secret, calls **Groq** (or OpenAI) to format the note like [`content/life/welcome.md`](content/life/welcome.md), runs `build_life.py`, commits on a branch, and opens a **Pull Request** for you to merge.

### Repository secrets (Settings → Secrets and variables → Actions)

| Secret | Purpose |
|--------|---------|
| `NOTE_DISPATCH_SECRET` | Same random string you put in the Shortcut payload as `client_payload.secret` |
| `groq_api_key` (or `GROQ_API_KEY`) | **Groq** API key. The workflow maps it into `GROQ_API_KEY` for the script. |
| `OPENAI_API_KEY` | Optional fallback if the Groq secret is unset. |

The workflow uses `secrets.groq_api_key`. If your secret is named **`GROQ_API_KEY`** (all caps), change that line in [`.github/workflows/note-to-life-pr.yml`](.github/workflows/note-to-life-pr.yml) to `GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}`.

Optional: repository **Variables** → `LLM_MODEL` (e.g. `llama-3.1-8b-instant`). Defaults: Groq `llama-3.3-70b-versatile`, OpenAI `gpt-4o-mini`.

### Event: `note-to-life` (create or update a topic)

Each topic has a **stable `slug`** (e.g. `evening-routine`). Reusing the same slug **overwrites** `content/life/<slug>.md` (upsert).

`client_payload` fields:

- `secret` — must match `NOTE_DISPATCH_SECRET`
- `slug` — topic id (letters, numbers, hyphens)
- `raw_text_b64` — **Base64 (UTF-8)** of the full note text. Optional first line `SLUG: my-slug` is stripped before sending to the model.

`event_type` must be `note-to-life`.

### Event: `note-delete-life` (remove a topic)

Deleting a note in Apple Notes **does not** notify GitHub. To remove a published topic, send `repository_dispatch` with `event_type: `**`note-delete-life`** and `client_payload`: `{ "secret", "slug" }`.

### Example `curl` (replace owner, repo, PAT, values)

```bash
export OWNER=RN0H
export REPO=RN0H.github.io
export PAT=github_pat_...
export SECRET='your-long-random-secret'
export SLUG=my-topic
export B64=$(printf '%s' "Your raw note text" | base64 -w0)

curl -sS -X POST \
  -H "Authorization: Bearer $PAT" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-24" \
  "https://api.github.com/repos/$OWNER/$REPO/dispatches" \
  -d "$(jq -n \
    --arg slug "$SLUG" \
    --arg secret "$SECRET" \
    --arg b64 "$B64" \
    '{event_type:"note-to-life", client_payload:{slug:$slug, secret:$secret, raw_text_b64:$b64}}')"
```

The PAT needs **`repo`** scope (or fine-grained: Contents and Metadata, and permission to trigger Actions if required).

### Apple Shortcuts (outline)

1. **Copy** text from Notes (or **Share** into the Shortcut).
2. **Base64 Encode** the text.
3. **Get contents of URL** — POST to `https://api.github.com/repos/<owner>/<repo>/dispatches` with headers `Authorization: Bearer <PAT>`, `Accept: application/vnd.github+json`, body JSON as above.
4. Store the PAT in the Shortcut securely and rotate if it leaks.

Payload size limits apply; very long notes may need to be split or posted from a machine.
