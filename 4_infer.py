"""
Step 4 — Run inference with the trained NER model on the full corpus.
Produces: results/enriched_articles.json

Each enriched article:
{
  "id": ..., "date": ..., "url": ..., "title": ..., "text_clean": ...,
  "entities": {
    "WEAPON":   [{"text": "Kalibr", "start": 12, "end": 18, "count": 1}, ...],
    "MIL_UNIT": [...],
    "MIL_ORG":  [...]
  }
}
"""

import json
from collections import defaultdict
from pathlib import Path

import spacy


def load_model(model_path: str = "output/model-best"):
    path = Path(model_path)
    if not path.exists():
        raise SystemExit(
            f"ERROR: Model not found at '{model_path}'.\n"
            "Run 3_train.py first, or point --model to a valid spaCy model directory."
        )
    print(f"Loading model from {path} …")
    return spacy.load(path)


def aggregate_entities(doc) -> dict[str, list[dict]]:
    """Group entities by label, counting mentions of the same surface form."""
    groups: dict[str, dict[str, dict]] = defaultdict(dict)

    for ent in doc.ents:
        label = ent.label_
        surface = ent.text.strip()
        if surface not in groups[label]:
            groups[label][surface] = {"text": surface, "count": 0, "offsets": []}
        groups[label][surface]["count"] += 1
        groups[label][surface]["offsets"].append([ent.start_char, ent.end_char])

    return {
        label: sorted(list(items.values()), key=lambda x: -x["count"])
        for label, items in groups.items()
    }


def run_inference(corpus: list[dict], nlp) -> list[dict]:
    enriched = []
    texts = [art["text_clean"] for art in corpus]

    for art, doc in zip(corpus, nlp.pipe(texts, batch_size=16)):
        entities = aggregate_entities(doc)
        enriched.append({
            "id":         art["id"],
            "date":       art["date"],
            "url":        art["url"],
            "title":      art["title"],
            "text_clean": art["text_clean"],
            "entities":   entities,
        })

    return enriched


def print_top_entities(enriched: list[dict], n: int = 10):
    from collections import Counter
    counters = {label: Counter() for label in ["WEAPON", "MIL_UNIT", "MIL_ORG"]}

    for art in enriched:
        for label, items in art["entities"].items():
            for item in items:
                counters[label][item["text"]] += item["count"]

    for label, counter in counters.items():
        print(f"\nTop {n} {label}:")
        for text, count in counter.most_common(n):
            print(f"  {count:>4}x  {text}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="output/model-best", help="Path to trained model")
    args = parser.parse_args()

    corpus_path = Path("data/corpus.json")
    out_path    = Path("results/enriched_articles.json")
    out_path.parent.mkdir(exist_ok=True)

    with open(corpus_path, encoding="utf-8") as f:
        corpus = json.load(f)

    nlp = load_model(args.model)
    print(f"Running inference on {len(corpus)} articles …")

    enriched = run_inference(corpus, nlp)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    print(f"\nEnriched articles saved → {out_path}")
    print_top_entities(enriched)


if __name__ == "__main__":
    main()
