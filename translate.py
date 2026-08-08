"""Translate scraped pages (raw/*.json) from English into a target language
using the Google Cloud Translation API v2 REST endpoint (API-key auth).
Results are cached in translated/<lang>/*.json, keyed by a hash of the
source content, so reruns only re-translate pages that actually changed.

Usage: python3 translate.py --lang hi   (target language as an ISO 639-1 code)
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://translation.googleapis.com/language/translate/v2"
SOURCE_LANG = "en"

RAW_DIR = Path(__file__).parent / "raw"

CHUNK_MAX_CHARS = 4000       # max size of one HTML chunk sent as a single `q` value
REQUEST_MAX_CHARS = 20000    # max combined size of all `q` values in one request
REQUEST_DELAY = 0.3

# Small UI strings (outside the scraped page content) that also need translating.
UI_STRINGS = {"toc_heading": "Table of Contents"}


def get_api_key() -> str:
    key = os.environ.get("GOOGLE_TRANSLATE_API_KEY")
    if not key:
        sys.exit(
            "GOOGLE_TRANSLATE_API_KEY is not set. Copy .env.example to .env "
            "and fill in your Google Cloud Translation API key."
        )
    return key


def call_translate_api(api_key: str, texts: list[str], target_lang: str, format_: str) -> list[str]:
    data = [("key", api_key), ("target", target_lang), ("source", SOURCE_LANG), ("format", format_)]
    data += [("q", t) for t in texts]
    resp = requests.post(API_URL, data=data, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Translate API error {resp.status_code}: {resp.text[:500]}")
    translations = resp.json()["data"]["translations"]
    return [t["translatedText"] for t in translations]


def translate_batched(api_key: str, texts: list[str], target_lang: str, format_: str) -> list[str]:
    """Translate many strings, batching requests to stay under size limits."""
    results = []
    batch: list[str] = []
    batch_len = 0
    for text in texts:
        if batch and batch_len + len(text) > REQUEST_MAX_CHARS:
            results.extend(call_translate_api(api_key, batch, target_lang, format_))
            time.sleep(REQUEST_DELAY)
            batch, batch_len = [], 0
        batch.append(text)
        batch_len += len(text)
    if batch:
        results.extend(call_translate_api(api_key, batch, target_lang, format_))
        time.sleep(REQUEST_DELAY)
    return results


def chunk_html(html: str, max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    """Split an HTML fragment into chunks along top-level element boundaries
    so each chunk stays valid, translatable HTML."""
    soup = BeautifulSoup(html, "html.parser")
    chunks = []
    buffer = ""
    for child in list(soup.contents):
        piece = str(child)
        if buffer and len(buffer) + len(piece) > max_chars:
            chunks.append(buffer)
            buffer = ""
        buffer += piece
    if buffer:
        chunks.append(buffer)
    return chunks or [html]


def source_hash(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def load_pages() -> list[dict]:
    pages = []
    for path in sorted(RAW_DIR.glob("*.json")):
        if path.name == "_toc.json":
            continue
        pages.append(json.loads(path.read_text(encoding="utf-8")))
    return pages


def already_translated(translated_dir: Path, slug: str, hash_: str) -> bool:
    dest = translated_dir / f"{slug}.json"
    if not dest.exists():
        return False
    existing = json.loads(dest.read_text(encoding="utf-8"))
    return existing.get("source_hash") == hash_


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lang", default="hi", help="Target language as an ISO 639-1 code (default: hi)"
    )
    args = parser.parse_args()
    target_lang = args.lang

    api_key = get_api_key()
    translated_dir = Path(__file__).parent / "translated" / target_lang
    translated_dir.mkdir(parents=True, exist_ok=True)

    pages = load_pages()
    for p in pages:
        p["source_hash"] = source_hash(p["title"], p["body_html"])

    pending = [p for p in pages if not already_translated(translated_dir, p["slug"], p["source_hash"])]

    ui_hash = source_hash(*UI_STRINGS.values())
    ui_pending = not already_translated(translated_dir, "_meta", ui_hash)

    print(f"[{target_lang}] {len(pages)} pages total, {len(pending)} need (re)translation")

    if ui_pending:
        print("Translating UI strings...")
        try:
            keys = list(UI_STRINGS.keys())
            values_translated = translate_batched(
                api_key, [UI_STRINGS[k] for k in keys], target_lang, format_="text"
            )
            meta_out = {"slug": "_meta", "source_hash": ui_hash}
            meta_out.update(dict(zip(keys, values_translated)))
            (translated_dir / "_meta.json").write_text(
                json.dumps(meta_out, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except RuntimeError as e:
            print(f"Warning: could not translate UI strings ({e}). Page content is unaffected; "
                  f"UI labels will fall back to English until this succeeds on a rerun.")

    if not pending:
        print("Nothing to do.")
        return

    print("Translating titles...")
    titles_translated = translate_batched(
        api_key, [p["title"] for p in pending], target_lang, format_="text"
    )
    for p, translated_title in zip(pending, titles_translated):
        p["translated_title"] = translated_title

    for i, page in enumerate(pending):
        print(f"[{i + 1}/{len(pending)}] {page['slug']} ...")
        chunks = chunk_html(page["body_html"])
        translated_chunks = translate_batched(api_key, chunks, target_lang, format_="html")
        translated_body_html = "".join(translated_chunks)

        out = {
            "slug": page["slug"],
            "translated_title": page["translated_title"],
            "translated_body_html": translated_body_html,
            "source_hash": page["source_hash"],
        }
        (translated_dir / f"{page['slug']}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"Done. Wrote {len(pending)} translated pages to {translated_dir}")


if __name__ == "__main__":
    main()
