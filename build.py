"""Render translated/<lang>/*.json into a self-contained HTML mirror of the
handbook: output/<lang>/index.html + one file per Table-of-Contents page,
all linked together, with images copied locally.

Usage: python3 build.py --lang hi
"""
import argparse
import json
import shutil
from pathlib import Path

RAW_DIR = Path(__file__).parent / "raw"

PAGE_TEMPLATE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{css}</style>
</head>
<body>
<div class="layout">
<nav class="toc">
<a class="toc__home" href="index.html">{home_title}</a>
{nav_html}
</nav>
<main class="content">
<h1>{title}</h1>
{body}
</main>
</div>
</body>
</html>
"""

CSS = """
:root { color-scheme: light dark; }
body { font-family: "Noto Sans", sans-serif; margin: 0; line-height: 1.6; }
.layout { display: flex; max-width: 1100px; margin: 0 auto; align-items: flex-start; }
.toc { width: 280px; flex-shrink: 0; padding: 24px 16px; position: sticky; top: 0; max-height: 100vh; overflow-y: auto; box-sizing: border-box; }
.toc__home { display: block; font-weight: bold; margin-bottom: 16px; text-decoration: none; }
.toc ul { list-style: none; margin: 0; padding-left: 16px; }
.toc > ul { padding-left: 0; }
.toc li { margin: 4px 0; }
.toc a { text-decoration: none; }
.toc a:hover { text-decoration: underline; }
.content { flex: 1; padding: 24px 16px 64px; min-width: 0; box-sizing: border-box; }
.content img { max-width: 100%; height: auto; }
@media (max-width: 800px) {
  .layout { flex-direction: column; }
  .toc { position: static; width: auto; max-height: none; }
}
"""


def load_toc() -> list[dict]:
    entries = json.loads((RAW_DIR / "_toc.json").read_text(encoding="utf-8"))
    return [e for e in entries if e["depth"] >= 0]  # drop the synthetic index entry


def build_toc_tree(toc: list[dict]) -> list[dict]:
    root: list[dict] = []
    stack = [(-1, root)]
    for entry in toc:
        node = {"slug": entry["slug"], "children": []}
        while stack[-1][0] >= entry["depth"]:
            stack.pop()
        stack[-1][1].append(node)
        stack.append((entry["depth"], node["children"]))
    return root


def render_toc_tree(nodes: list[dict], translations: dict[str, dict]) -> str:
    if not nodes:
        return ""
    html = ["<ul>"]
    for node in nodes:
        title = translations[node["slug"]]["translated_title"]
        html.append(f'<li><a href="{node["slug"]}.html">{title}</a>')
        html.append(render_toc_tree(node["children"], translations))
        html.append("</li>")
    html.append("</ul>")
    return "".join(html)


def build_nav_html(toc: list[dict], translations: dict[str, dict]) -> str:
    return render_toc_tree(build_toc_tree(toc), translations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lang", default="hi", help="Target language as an ISO 639-1 code (default: hi)"
    )
    args = parser.parse_args()
    lang = args.lang

    translated_dir = Path(__file__).parent / "translated" / lang
    output_dir = Path(__file__).parent / "output" / lang

    if not translated_dir.exists():
        raise RuntimeError(f"No translations found at {translated_dir}. Run translate.py --lang {lang} first.")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    images_src = RAW_DIR / "images"
    if images_src.exists():
        shutil.copytree(images_src, output_dir / "images")

    toc = load_toc()
    translations = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in translated_dir.glob("*.json")
        if p.stem != "_meta"
    }

    missing = [e["slug"] for e in toc if e["slug"] not in translations] + (
        ["index"] if "index" not in translations else []
    )
    if missing:
        raise RuntimeError(f"Missing translations for: {missing}. Run translate.py --lang {lang} first.")

    nav_html = build_nav_html(toc, translations)
    home_title = translations["index"]["translated_title"]

    all_slugs = ["index"] + [e["slug"] for e in toc]
    for slug in all_slugs:
        t = translations[slug]
        page_html = PAGE_TEMPLATE.format(
            lang=lang,
            title=t["translated_title"],
            css=CSS,
            nav_html=nav_html,
            home_title=home_title,
            body=t["translated_body_html"],
        )
        (output_dir / f"{slug}.html").write_text(page_html, encoding="utf-8")

    print(f"Wrote {len(all_slugs)} pages to {output_dir}")


if __name__ == "__main__":
    main()
