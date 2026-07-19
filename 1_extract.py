"""
Step 1 — Extract and clean text from data_set.json (TASS)
Produces: data/corpus.json  (list of {id, date, url, title, text_clean})

data_set.json field mapping:
  id       -> id
  date     -> Unix timestamp -> ISO date
  link     -> url
  title    -> title
  text     -> text_clean   (+ lead prepended if present)
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path


def clean_text(text: str) -> str:
    # Normalize curly quotes and common Unicode punctuation to ASCII
    text = text.replace('‘', "'").replace('’', "'")
    text = text.replace('“', '"').replace('”', '"')
    text = text.replace('—', '-').replace('–', '-')
    # Strip non-printable / garbage bytes (keep standard Latin + accented)
    text = re.sub(r'[^\x09\x0a\x0d\x20-\x7e\xa0-\xff]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def load_articles(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_corpus(articles: list[dict], sample: int = None) -> list[dict]:
    corpus = []
    skipped = 0

    src = articles[:sample] if sample else articles

    for art in src:
        text_raw = art.get("text", "") or ""
        lead     = art.get("lead", "")  or ""

        # Combine lead + body for richer context
        full_text = f"{lead} {text_raw}".strip() if lead else text_raw

        if len(full_text.split()) < 30:
            skipped += 1
            continue

        # Convert Unix timestamp to ISO date
        ts = art.get("date")
        try:
            date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            date_str = ""

        corpus.append({
            "id":         str(art.get("id", "")),
            "date":       date_str,
            "url":        "https://tass.com" + art.get("link", ""),
            "title":      art.get("title", ""),
            "text_clean": clean_text(full_text),
        })

    print(f"Loaded {len(corpus)} articles  (skipped {skipped} short/empty).")
    return corpus


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=None,
                        help="Only process first N articles (for testing)")
    args = parser.parse_args()

    src  = Path("data_set.json")
    dest = Path("data/corpus.json")

    articles = load_articles(src)
    corpus   = extract_corpus(articles, sample=args.sample)

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)

    print(f"Corpus saved to {dest}  ({len(corpus)} documents)")

    lengths = [len(a["text_clean"].split()) for a in corpus]
    print(f"Avg words/article : {sum(lengths)//len(lengths)}")
    print(f"Min / Max words   : {min(lengths)} / {max(lengths)}")


if __name__ == "__main__":
    main()
