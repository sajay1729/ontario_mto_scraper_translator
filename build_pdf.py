"""Combine all translated pages, in Table-of-Contents order, into a single
printable PDF using headless Chromium (Playwright). Reuses the locally
downloaded images from output/<lang>/images so print quality matches the
native resolution scraped from the source site.

Usage: python3 build_pdf.py --lang hi
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

RAW_DIR = Path(__file__).parent / "raw"

CSS = """
@page { size: A4; }
body { font-family: "Noto Sans", sans-serif; line-height: 1.6; color: #111; margin: 0; }
.cover { break-after: page; padding-top: 100mm; text-align: center; }
.cover h1 { font-size: 32px; }
.toc-page { break-after: page; }
.toc-page h2 { font-size: 22px; }
.toc-page ul { list-style: none; padding-left: 0; }
.toc-page li { margin: 6px 0; }
.toc-page li.depth-1 { margin-left: 24px; }
.toc-page a { color: #111; text-decoration: none; }
.chapter { break-before: page; }
.chapter h1 { font-size: 24px; border-bottom: 2px solid #ccc; padding-bottom: 6px; }
.chapter h2 { font-size: 19px; }
.chapter h3 { font-size: 16px; }
img { max-width: 100%; height: auto; display: block; margin: 10px auto; break-inside: avoid; }
p, li { break-inside: avoid-page; }
"""


def load_pages(translated_dir: Path):
    toc = json.loads((RAW_DIR / "_toc.json").read_text(encoding="utf-8"))
    translations = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in translated_dir.glob("*.json")
        if p.stem != "_meta"
    }
    meta_path = translated_dir / "_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    return toc, translations, meta


def build_html(toc: list[dict], translations: dict[str, dict], meta: dict, lang: str) -> str:
    cover_title = translations["index"]["translated_title"]
    toc_heading = meta.get("toc_heading", "Table of Contents")

    toc_items = []
    for entry in toc:
        if entry["slug"] == "index":
            continue
        title = translations[entry["slug"]]["translated_title"]
        depth_cls = f' class="depth-{entry["depth"]}"' if entry["depth"] > 0 else ""
        toc_items.append(f'<li{depth_cls}><a href="#{entry["slug"]}">{title}</a></li>')

    chapters = []
    for entry in toc:
        t = translations[entry["slug"]]
        # Drop lazy-loading: in one long print document, images that never
        # scroll into view during rendering would otherwise never fetch.
        body = t["translated_body_html"].replace('loading="lazy"', 'loading="eager"')
        chapters.append(
            f'<section class="chapter" id="{entry["slug"]}"><h1>{t["translated_title"]}</h1>{body}</section>'
        )

    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<title>{cover_title}</title>
<style>{CSS}</style>
</head>
<body>
<div class="cover"><h1>{cover_title}</h1></div>
<div class="toc-page"><h2>{toc_heading}</h2><ul>{''.join(toc_items)}</ul></div>
{''.join(chapters)}
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lang", default="hi", help="Target language as an ISO 639-1 code (default: hi)"
    )
    args = parser.parse_args()
    lang = args.lang

    translated_dir = Path(__file__).parent / "translated" / lang
    output_html_dir = Path(__file__).parent / "output" / lang
    pdf_path = Path(__file__).parent / "output" / "pdf" / f"mto-drivers-handbook-{lang}.pdf"
    print_html_path = output_html_dir / "_print.html"

    if not translated_dir.exists():
        raise RuntimeError(f"No translations found at {translated_dir}. Run translate.py --lang {lang} first.")

    toc, translations, meta = load_pages(translated_dir)
    missing = [e["slug"] for e in toc if e["slug"] not in translations]
    if missing:
        raise RuntimeError(f"Missing translations for: {missing}. Run translate.py --lang {lang} first.")

    html = build_html(toc, translations, meta, lang)
    output_html_dir.mkdir(parents=True, exist_ok=True)
    print_html_path.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(print_html_path.as_uri())
        page.wait_for_function(
            "() => Array.from(document.images).every(img => img.complete)",
            timeout=60000,
        )
        page.wait_for_timeout(300)  # let fonts settle
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin={"top": "20mm", "bottom": "20mm", "left": "16mm", "right": "16mm"},
            display_header_footer=True,
            header_template='<span></span>',
            footer_template=(
                '<div style="width:100%; text-align:center; font-size:15px; color:#555;">'
                '<span class="pageNumber"></span></div>'
            ),
        )
        browser.close()

    print_html_path.unlink()
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
