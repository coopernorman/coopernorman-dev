"""Build the case-study pages for coopernorman.dev from the markdown in content/.

- converts content/*.md -> case-studies/<slug>.html (styled, with nav + footer)
- strips internal production notes (the "*Portfolio case study for...*" / "*To
  produce...*" lines) so they don't show on the public site
- rewrites figures/ and snippets/ links to the deployed asset paths
- copies content/figures -> assets/img and content/snippets -> assets/snippets

Run:  python build_site.py
Add a case study by dropping a new .md in content/ and adding it to PAGES.
"""
import os, re, shutil
import markdown

ROOT = os.path.dirname(os.path.abspath(__file__))
PAGES = {"money_core": "money-core", "quantshark": "quantshark",
         "model_consolidation": "model-consolidation", "agents_suite": "agents-suite",
         "data_pipeline": "data-pipeline",
         "copula_pricer": "copula-pricer",
         "tjx_valuation": "tjx-valuation"}
NOTE_PREFIXES = ("*Portfolio case study for", "*To produce", "*Figures embedded above",
                 "*Diagrams to produce", "*Portfolio case study")

HEADER = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Cooper Norman</title>
<meta name="description" content="{desc}">
<link rel="stylesheet" href="../assets/style.css">
<link rel="icon" href="../assets/favicon.svg" type="image/svg+xml">
</head>
<body>
<nav class="nav">
  <div class="wrap">
    <a class="brand" href="../index.html" style="color:var(--ink)">Cooper Norman</a>
    <span class="links">
      <a href="../index.html#work">Work</a>
      <a href="../index.html#about">About</a>
      <a href="../index.html#contact">Contact</a>
    </span>
  </div>
</nav>
<article class="article">
  <div class="wrap">
    <a class="back" href="../index.html#work">← All work</a>
"""

FOOTER = """
  </div>
</article>
<footer><div class="wrap">© 2026 Cooper Norman · coopernorman.dev</div></footer>
</body>
</html>
"""

def clean(text):
    title = None
    out = []
    for line in text.splitlines():
        s = line.strip()
        if title is None and line.startswith("# "):
            title = line[2:].strip(); continue
        if any(s.startswith(p) for p in NOTE_PREFIXES):
            continue
        out.append(line)
    body = "\n".join(out).strip()
    body = re.sub(r"^\s*---\s*(\n|$)", "", body)          # drop a leading rule
    body = body.replace("](figures/", "](../assets/img/")
    body = body.replace("](snippets/", "](../assets/snippets/")
    return title or "Case study", body

def build():
    # copy assets
    img_dst = os.path.join(ROOT, "assets", "img")
    snip_dst = os.path.join(ROOT, "assets", "snippets")
    os.makedirs(img_dst, exist_ok=True); os.makedirs(snip_dst, exist_ok=True)
    for f in os.listdir(os.path.join(ROOT, "content", "figures")):
        shutil.copy(os.path.join(ROOT, "content", "figures", f), img_dst)
    for f in os.listdir(os.path.join(ROOT, "content", "snippets")):
        shutil.copy(os.path.join(ROOT, "content", "snippets", f), snip_dst)
    # build pages
    for stem, slug in PAGES.items():
        src = os.path.join(ROOT, "content", f"{stem}.md")
        title, body = clean(open(src, encoding="utf-8").read())
        html_body = markdown.markdown(body, extensions=["tables", "fenced_code", "sane_lists"])
        desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html_body))[:155]
        page = HEADER.format(title=title, desc=desc) + html_body + FOOTER
        out = os.path.join(ROOT, "case-studies", f"{slug}.html")
        open(out, "w", encoding="utf-8").write(page)
        print("built", os.path.relpath(out, ROOT))

if __name__ == "__main__":
    build()
