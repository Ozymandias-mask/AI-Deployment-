"""
Step 2 — Pre-annotate the corpus with Claude, then validate offsets.
Produces: annotations/annotations.json  (spaCy training format)

Format:
[
  {
    "text": "...",
    "entities": [[start, end, "LABEL"], ...]
  },
  ...
]

Labels:
  WEAPON   — weapons systems and equipment (missiles, tanks, drones…)
  MIL_UNIT — combat units (brigades, battalions, regiments…)
  MIL_ORG  — high-level organisations (ministries, general staffs, armed forces…)
"""

import json
import os
import re
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """You are a military Named Entity Recognition (NER) annotator.
Your task: annotate entities in English military news texts using EXACTLY these 3 labels:
  - WEAPON   : weapons systems and materiel (missiles, tanks, aircraft, artillery, drones, rockets, launchers…)
  - MIL_UNIT : combat/tactical units (brigades, battalions, regiments, divisions, companies, squadrons…)
  - MIL_ORG  : high-level military organisations (general staffs, ministries of defence, armed forces, fleets, armies at top level…)

Rules:
  1. Return ONLY a JSON array. No markdown fences, no explanations.
  2. Each element: {"text": "<entity_string>", "start": <int>, "end": <int>, "label": "<LABEL>"}
  3. start/end are character offsets INTO THE PROVIDED TEXT (0-indexed, end is exclusive).
  4. Verify each offset: text[start:end] MUST equal the entity_string exactly.
  5. Do NOT annotate people (commanders, politicians), locations (cities, countries), or events.
  6. Annotate only the most specific span — no nested or overlapping spans.
  7. If no entities, return an empty array: []
"""

USER_TEMPLATE = 'Annotate the following text:\n\n"""\n{text}\n"""'


def llm_annotate(client: anthropic.Anthropic, text: str) -> list[dict]:
    """Call Claude to produce raw entity annotations for one article."""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": USER_TEMPLATE.format(text=text)}],
    )
    raw = response.content[0].text.strip()
    return json.loads(raw)


def validate_annotations(text: str, raw: list[dict]) -> list[list]:
    """
    Convert raw LLM output to spaCy format [[start, end, label], ...].
    Drops entries with wrong offsets or unknown labels.
    """
    VALID_LABELS = {"WEAPON", "MIL_UNIT", "MIL_ORG"}
    valid = []
    seen = set()

    for ent in raw:
        try:
            s, e, label = int(ent["start"]), int(ent["end"]), ent["label"]
            span = ent.get("text", "")
        except (KeyError, ValueError):
            continue

        if label not in VALID_LABELS:
            continue
        if s < 0 or e > len(text) or s >= e:
            continue
        if text[s:e] != span:
            # Try to fix: search nearby
            found = text.find(span, max(0, s - 5))
            if found == -1 or abs(found - s) > 20:
                continue
            s, e = found, found + len(span)
        key = (s, e)
        if key in seen:
            continue
        seen.add(key)
        valid.append([s, e, label])

    return sorted(valid, key=lambda x: x[0])


def annotate_corpus(corpus: list[dict], client: anthropic.Anthropic, max_articles: int = None) -> list[dict]:
    """Annotate each article and return spaCy-format training examples."""
    results = []
    items = corpus[:max_articles] if max_articles else corpus

    for i, article in enumerate(items):
        text = article["text_clean"]
        print(f"[{i+1}/{len(items)}] Annotating article {article['id']} ...", end=" ")

        try:
            raw = llm_annotate(client, text)
            entities = validate_annotations(text, raw)
            results.append({"text": text, "entities": entities, "article_id": article["id"]})
            print(f"{len(entities)} entities")
        except json.JSONDecodeError as e:
            print(f"JSON parse error — skipping ({e})")
        except Exception as e:
            print(f"Error — {e}")

        # Small delay to avoid rate limiting
        if i < len(items) - 1:
            time.sleep(0.3)

    return results


def print_stats(annotations: list[dict]):
    """Print label distribution across all annotations."""
    from collections import Counter
    counter = Counter()
    for ann in annotations:
        for _, _, label in ann["entities"]:
            counter[label] += 1
    print("\n=== Annotation statistics ===")
    total = sum(counter.values())
    for label, count in sorted(counter.items()):
        print(f"  {label:<12} {count:>5}  ({100*count/total:.1f}%)")
    print(f"  {'TOTAL':<12} {total:>5}")
    print(f"  Articles with ≥1 entity: {sum(1 for a in annotations if a['entities'])}/{len(annotations)}")


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ERROR: ANTHROPIC_API_KEY not set. Add it to a .env file or environment.")

    client = anthropic.Anthropic(api_key=api_key)

    corpus_path = Path("data/corpus.json")
    out_path    = Path("annotations/annotations.json")

    with open(corpus_path, encoding="utf-8") as f:
        corpus = json.load(f)

    print(f"Annotating {len(corpus)} articles via Claude …")
    annotations = annotate_corpus(corpus, client)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(annotations, f, ensure_ascii=False, indent=2)

    print(f"\nAnnotations saved → {out_path}")
    print_stats(annotations)
    print("\n⚠  MANDATORY: Manually review a sample of annotations before training.")
    print("   Open annotations/annotations.json and verify that text[start:end] == entity text.")


if __name__ == "__main__":
    main()
