# AI Deployment — OSINT Militaire via NER + Elasticsearch

Pipeline complet de traitement du langage naturel appliqué au renseignement open source (OSINT) : extraction d'un corpus d'articles TASS (rubrique "Guerre"), annotation, fine-tuning d'un modèle NER spaCy sur un schéma personnalisé (armes, unités, organisations militaires), inférence sur le corpus, ingestion dans Elasticsearch et construction de dashboards analytiques.

## Cadre OSINT

TASS est un média d'État russe : les données portent un biais éditorial fort. Ce pipeline extrait **ce que la source affirme**, pas une vérité vérifiée. La fiabilité et l'intention de la source doivent être prises en compte dans toute interprétation (voir `results/intelligence_report.md`).

## Schéma d'entités

| Label      | Définition                        | Exemples                                  |
|------------|------------------------------------|--------------------------------------------|
| `WEAPON`   | Systèmes et matériels d'armement   | missiles, blindés, drones, lance-roquettes |
| `MIL_UNIT` | Unités combattantes                | brigades, bataillons, régiments, divisions |
| `MIL_ORG`  | Organisations militaires de haut niveau | états-majors, ministères de la Défense |

## Pipeline

```
data_set.json → 1_extract.py → data/corpus.json
              → 2_annotate.py (ou 2b_generate_annotations.py) → annotations/annotations.json
              → 3_train.py → output/model-best/
              → 4_infer.py → results/enriched_articles.json
              → 5_ingest.py → Elasticsearch (index tass_war_ner)
              → 6_generate_report.py → results/intelligence_report.md + dashboard_queries.json
```

## Installation

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
cp .env.example .env   # renseigner ANTHROPIC_API_KEY et/ou ES_URL / ES_API_KEY
```

## Utilisation

1. **Extraction du texte**
   ```bash
   python 1_extract.py
   ```
   Parse `data_set.json`, nettoie le texte (unicode, espaces) et produit `data/corpus.json` (un objet par article, champs conservés : id, date, url, title, text_clean).

2. **Annotation du corpus**
   ```bash
   python 2_annotate.py        # pré-annotation via l'API Claude (nécessite ANTHROPIC_API_KEY)
   # ou, sans clé API :
   python 2b_generate_annotations.py   # génération via gazetteer + recherche exacte
   ```
   Produit `annotations/annotations.json` au format spaCy `(text, {"entities": [[start, end, label], ...]})`. **La validation humaine d'un échantillon reste obligatoire avant l'entraînement.**

3. **Entraînement du modèle NER**
   ```bash
   python 3_train.py
   ```
   Split train/dev (80/20), conversion en `.spacy` (DocBin), génère la config à partir de `en_core_web_sm` (transfer learning) et lance `spacy train`. Modèle sauvegardé dans `output/model-best/`.

4. **Inférence sur le corpus complet**
   ```bash
   python 4_infer.py
   ```
   Applique le modèle entraîné à tous les articles → `results/enriched_articles.json` (entités regroupées par label et par article).

5. **Ingestion Elasticsearch**
   ```bash
   python 5_ingest.py
   ```
   Crée l'index `tass_war_ner` (mapping texte/date/entités structurées) et ingère les articles enrichis. Nécessite un cluster Elasticsearch (cloud.elastic.co, essai gratuit 14 jours, ou instance locale).

6. **Génération du rapport**
   ```bash
   python 6_generate_report.py
   ```
   Produit `results/intelligence_report.md` (description des dashboards, analyse de fréquence des entités, note de renseignement) et `results/dashboard_queries.json` (requêtes Kibana/Elasticsearch prêtes à l'emploi).

## Résultats du modèle

| Métrique | Valeur |
|----------|--------|
| F1 global | 91.1 % |
| Precision | 93.2 % |
| Recall | 89.1 % |
| F1 WEAPON | 82.9 % |
| F1 MIL_UNIT | 94.1 % |
| F1 MIL_ORG | 93.2 % |

(voir `output/model-best/meta.json` pour le détail complet)

## Dashboards Kibana

- Top entités par label (agrégation `terms`)
- Histogramme temporel des mentions (`date_histogram`)
- Heatmap de co-occurrence armes × unités
- Filtres par période et par mot-clé

## Structure du projet

```
1_extract.py                    # Étape 1 — extraction & nettoyage
2_annotate.py                   # Étape 2 — pré-annotation LLM (Claude)
2b_generate_annotations.py      # Étape 2 — alternative sans API (gazetteer)
3_train.py                      # Étape 3 — entraînement spaCy NER
4_infer.py                      # Étape 4 — inférence sur le corpus
5_ingest.py                     # Étape 5 — ingestion Elasticsearch
6_generate_report.py            # Étape 6 — génération du rapport & requêtes dashboards
config.cfg                      # Config spaCy (générée)
data/                           # corpus.json, articles.json
annotations/annotations.json    # annotations spaCy
training/                       # train.spacy, dev.spacy, base_config.cfg
output/model-best/              # modèle NER entraîné
results/                        # enriched_articles.json, intelligence_report.md, dashboard_queries.json
```

## Limites

- Le NER ne "comprend" pas le texte : il reconnaît des motifs statistiques appris sur un schéma figé à 3 labels.
- Pas de résolution de coréférence ("la brigade" peut désigner plusieurs unités selon le contexte).
- La fréquence de mention reflète l'emphase éditoriale de TASS, pas un fait opérationnel confirmé — une validation croisée avec d'autres sources est nécessaire.
