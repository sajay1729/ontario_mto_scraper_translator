"""Scrape the MTO Driver's Handbook: the landing page plus every page
listed in its Table of Contents. Writes one JSON file per page to raw/,
downloads referenced images to raw/images/, and rewrites <img src> to
point at the local copies.
"""
import json
import time
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.ontario.ca"
MAIN_PATH = "/document/official-mto-drivers-handbook"
MAIN_URL = BASE_URL + MAIN_PATH

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; driving-lessons-scrapor/1.0)"}
REQUEST_DELAY = 0.5

RAW_DIR = Path(__file__).parent / "raw"
IMAGES_DIR = RAW_DIR / "images"


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def slug_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    if path.rstrip("/") == MAIN_PATH:
        return "index"
    return path.rstrip("/").split("/")[-1]


def extract_toc(soup: BeautifulSoup) -> list[dict]:
    """Return an ordered list of {slug, title, url, depth} from the TOC nav."""
    nav = soup.find("nav", attrs={"aria-label": lambda v: v and v.startswith("Table of contents")})
    if nav is None:
        raise RuntimeError("Could not find the Table of Contents nav on the page")

    top_ul = nav.find("ul", class_="book__tree_toc-main")
    entries = []

    def add_entry(a_tag, depth):
        href = a_tag["href"]
        url = urllib.parse.urljoin(BASE_URL, href)
        entries.append({
            "slug": slug_from_url(url),
            "title": a_tag.get_text(strip=True),
            "url": url,
            "depth": depth,
        })

    for li in top_ul.find_all("li", recursive=False):
        a_tag = li.find("a", recursive=False)
        if a_tag:
            add_entry(a_tag, depth=0)
        inner_ul = li.find("ul", class_="book__tree_toc-inner", recursive=False)
        if inner_ul:
            for inner_li in inner_ul.find_all("li", recursive=False):
                inner_a = inner_li.find("a", recursive=False)
                if inner_a:
                    add_entry(inner_a, depth=1)

    return entries


def download_image(img_url: str, slug: str, index: int) -> str:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(urllib.parse.urlparse(img_url).path).suffix or ".jpg"
    filename = f"{slug}_{index}{ext}"
    dest = IMAGES_DIR / filename
    if not dest.exists():
        resp = requests.get(img_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    return filename


def scrape_page(slug: str, title_hint: str, url: str, depth: int) -> dict:
    soup = fetch(url)

    main = soup.find("main", id="main-content")
    if main is None:
        raise RuntimeError(f"No <main id='main-content'> found on {url}")

    body_field = main.find("div", class_="body-field")
    if body_field is None:
        raise RuntimeError(f"No .body-field found inside <main> on {url}")

    h1 = main.find("h1")
    title = h1.get_text(strip=True) if h1 else title_hint

    for i, img in enumerate(body_field.find_all("img")):
        src = img.get("src")
        if not src:
            continue
        img_url = urllib.parse.urljoin(url, src)
        filename = download_image(img_url, slug, i)
        img["src"] = f"images/{filename}"

    return {
        "slug": slug,
        "title": title,
        "url": url,
        "depth": depth,
        "body_html": body_field.decode_contents(),
    }


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Fetching {MAIN_URL} ...")
    main_soup = fetch(MAIN_URL)
    toc = extract_toc(main_soup)
    print(f"Found {len(toc)} pages in the Table of Contents")

    # The landing page itself has real content too (intro section).
    pages = [{"slug": "index", "title": "The Official MTO Driver's Handbook", "url": MAIN_URL, "depth": -1}] + toc

    toc_out = [{"slug": p["slug"], "title": p["title"], "depth": p["depth"]} for p in pages]
    (RAW_DIR / "_toc.json").write_text(json.dumps(toc_out, ensure_ascii=False, indent=2), encoding="utf-8")

    for i, page in enumerate(pages):
        dest = RAW_DIR / f"{page['slug']}.json"
        print(f"[{i + 1}/{len(pages)}] {page['slug']} ...")
        data = scrape_page(page["slug"], page["title"], page["url"], page["depth"])
        dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(REQUEST_DELAY)

    print(f"Done. Wrote {len(pages)} pages to {RAW_DIR}")


if __name__ == "__main__":
    main()
