# coopernorman.dev

Personal portfolio site for Cooper Norman — founder-engineer (ML, applied-AI, regulated-fintech).
**Static site, zero build toolchain required** to deploy. This is a public repo — no secrets, no PII beyond public contact info.

## Structure
```
index.html              # landing page (hero, lanes, case studies, projects, about, contact)
assets/style.css        # all styles
assets/img/             # case-study figures (generated — copied from content/figures)
assets/snippets/        # sanitized code samples (generated — copied from content/snippets)
case-studies/*.html     # generated from content/*.md by build_site.py
content/*.md            # case-study source (edit these)
content/figures, snippets   # case-study source assets
build_site.py           # regenerates case-studies/ from content/
```

## Update the case studies
Edit the markdown in `content/`, then rebuild:
```
pip install markdown      # one-time
python build_site.py
```
To add a case study: drop a new `.md` in `content/` and add it to `PAGES` in `build_site.py`.
The landing page (`index.html`) is hand-edited directly.

## Deploy (pick one)
All three host static sites for free and connect a custom domain:
- **Vercel** — `vercel` CLI or import the repo at vercel.com; add `coopernorman.dev` in Project → Domains.
- **Netlify** — drag the folder onto app.netlify.com, or connect the repo; add the domain in Site settings → Domains.
- **GitHub Pages** — push to GitHub, enable Pages on the default branch, set the custom domain.

No build command is needed — it's static. (If a host asks, leave build command empty and the output/publish directory as the repo root.)
