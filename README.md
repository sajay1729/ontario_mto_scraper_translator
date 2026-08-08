# MTO Driver's Handbook Translator

Scrapes the [Official MTO Driver's Handbook](https://www.ontario.ca/document/official-mto-drivers-handbook)
(landing page + every Table of Contents page), translates it via the Google Cloud
Translation API, and builds a browsable HTML mirror and a printable PDF.

```
scrape.py      -> raw/                     English content, scraped once, shared by all languages
translate.py   -> translated/<lang>/       translated content, cached per page
build.py       -> output/<lang>/*.html     linked HTML site
build_pdf.py   -> output/<lang>/*.pdf      single printable PDF with cover, TOC, page numbers
```

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/playwright install chromium   # needed for the PDF step
```

## Google Cloud Translation API

1. Create a GCP project, enable billing, and enable the **Cloud Translation API**.
2. Create an API key (APIs & Services → Credentials).
3. `cp .env.example .env` and set `GOOGLE_TRANSLATE_API_KEY=...`.

Billed per character — the whole handbook is well under 400K characters (a few dollars).
`.env` is gitignored.

## Run

```bash
./venv/bin/python scrape.py               # once
./venv/bin/python translate.py --lang hi
./venv/bin/python build.py --lang hi
./venv/bin/python build_pdf.py --lang hi
```

`--lang` takes any [language code Google Translate supports](https://cloud.google.com/translate/docs/languages)
(default `hi`). Rerun with a different `--lang` to add more languages — `raw/` is
shared, each language gets its own `translated/<lang>/` and `output/<lang>/`.
Reruns are cheap: both scraping and translation are cached and skip unchanged pages.

## Troubleshooting

- `GOOGLE_TRANSLATE_API_KEY is not set` — create `.env` (see above).
- `403 ... has not been used ... or it is disabled` — the Translation API or billing
  isn't enabled on the GCP project the key belongs to. Already-translated pages are
  cached, so rerunning after fixing this only translates what's missing.
- PDF images are capped at ~170px because that's the native resolution on Ontario's
  own CDN — embedded as-is, not upscaled.
