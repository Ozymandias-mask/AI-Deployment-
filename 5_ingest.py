"""
Step 5 — Ingest enriched articles into Elasticsearch and print Kibana dashboard hints.

Prerequisites:
  pip install elasticsearch
  A running Elasticsearch 8.x cluster (cloud.elastic.co free trial or local Docker)

Set credentials via .env:
  ES_URL      = https://<cluster-id>.es.<region>.aws.elastic-cloud.com:443
  ES_API_KEY  = <your API key>
  # OR:
  ES_USER     = elastic
  ES_PASSWORD = <password>
"""

import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch, helpers

load_dotenv()

INDEX_NAME = "tass_war_ner"

# ── Index mapping ──────────────────────────────────────────────────────────────
MAPPING = {
    "mappings": {
        "properties": {
            "article_id": {"type": "keyword"},
            "date":       {"type": "date", "format": "yyyy-MM-dd"},
            "url":        {"type": "keyword"},
            "title":      {"type": "text"},
            "text":       {"type": "text"},
            # Flat arrays for easy aggregation in Kibana
            "weapons":    {"type": "keyword"},
            "mil_units":  {"type": "keyword"},
            "mil_orgs":   {"type": "keyword"},
            # Nested for frequency analysis
            "entities": {
                "type": "nested",
                "properties": {
                    "label": {"type": "keyword"},
                    "text":  {"type": "keyword"},
                    "count": {"type": "integer"},
                }
            }
        }
    }
}


def build_es_client() -> Elasticsearch:
    url     = os.getenv("ES_URL")
    api_key = os.getenv("ES_API_KEY")
    user    = os.getenv("ES_USER")
    password = os.getenv("ES_PASSWORD")

    if not url:
        raise SystemExit(
            "ERROR: ES_URL not set.\n"
            "Add to .env:\n"
            "  ES_URL=https://<your-cluster>.elastic-cloud.com:443\n"
            "  ES_API_KEY=<your-key>"
        )

    if api_key:
        return Elasticsearch(url, api_key=api_key)
    elif user and password:
        return Elasticsearch(url, basic_auth=(user, password))
    else:
        raise SystemExit("ERROR: Provide ES_API_KEY or ES_USER + ES_PASSWORD in .env")


def create_index(es: Elasticsearch):
    if es.indices.exists(index=INDEX_NAME):
        print(f"Index '{INDEX_NAME}' already exists — deleting and recreating …")
        es.indices.delete(index=INDEX_NAME)
    es.indices.create(index=INDEX_NAME, body=MAPPING)
    print(f"Index '{INDEX_NAME}' created.")


def article_to_doc(article: dict) -> dict:
    """Convert enriched article to flat Elasticsearch document."""
    entities_flat = []
    weapons   = []
    mil_units = []
    mil_orgs  = []

    for label, items in article.get("entities", {}).items():
        for item in items:
            entities_flat.append({
                "label": label,
                "text":  item["text"],
                "count": item["count"],
            })
            if label == "WEAPON":
                weapons.extend([item["text"]] * item["count"])
            elif label == "MIL_UNIT":
                mil_units.extend([item["text"]] * item["count"])
            elif label == "MIL_ORG":
                mil_orgs.extend([item["text"]] * item["count"])

    return {
        "article_id": article["id"],
        "date":       article["date"],
        "url":        article["url"],
        "title":      article["title"],
        "text":       article["text_clean"],
        "weapons":    weapons,
        "mil_units":  mil_units,
        "mil_orgs":   mil_orgs,
        "entities":   entities_flat,
    }


def bulk_ingest(es: Elasticsearch, articles: list[dict]):
    def generate():
        for article in articles:
            yield {
                "_index": INDEX_NAME,
                "_id":    article["id"],
                "_source": article_to_doc(article),
            }

    success, errors = helpers.bulk(es, generate(), raise_on_error=False)
    print(f"Ingested {success} documents.")
    if errors:
        print(f"Errors: {errors}")


def print_kibana_guide():
    guide = """
╔══════════════════════════════════════════════════════════════════════╗
║              KIBANA DASHBOARD SETUP GUIDE                          ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  1. Go to Kibana → Stack Management → Data Views                   ║
║     Create a data view: tass_war_ner  (time field: date)           ║
║                                                                    ║
║  2. DASHBOARD 1 — Top Entities                                     ║
║     • Bar chart: field=weapons,    aggregation=terms, top 20       ║
║     • Bar chart: field=mil_units,  aggregation=terms, top 20       ║
║     • Bar chart: field=mil_orgs,   aggregation=terms, top 20       ║
║                                                                    ║
║  3. DASHBOARD 2 — Timeline of mentions                             ║
║     • Date histogram: X=date (monthly), Y=count of weapons         ║
║     • Split series by: weapons (top 5) to compare trends           ║
║                                                                    ║
║  4. DASHBOARD 3 — Co-occurrences                                   ║
║     • Heatmap: rows=weapons top 10 × cols=mil_units top 10         ║
║       (requires scripted field or Data Transform)                  ║
║                                                                    ║
║  5. DASHBOARD 4 — Filters                                          ║
║     • Add filter controls: date range, weapon type, unit type      ║
║                                                                    ║
╚══════════════════════════════════════════════════════════════════════╝
"""
    print(guide)


def main():
    in_path = Path("results/enriched_articles.json")
    if not in_path.exists():
        raise SystemExit("ERROR: results/enriched_articles.json not found. Run 4_infer.py first.")

    with open(in_path, encoding="utf-8") as f:
        articles = json.load(f)

    print(f"Loaded {len(articles)} enriched articles.")

    es = build_es_client()
    info = es.info()
    print(f"Connected to Elasticsearch {info['version']['number']} at {os.getenv('ES_URL')}")

    create_index(es)
    bulk_ingest(es, articles)

    print_kibana_guide()


if __name__ == "__main__":
    main()
