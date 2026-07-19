"""
Step 3 — Train a custom spaCy NER model on the annotated corpus.
  3a. Split train/dev (80/20), convert to DocBin
  3b. Generate spaCy config (inherits en_core_web_sm NER weights)
  3c. Run spacy train

Prerequisites:
  pip install spacy
  python -m spacy download en_core_web_sm
"""

import json
import random
import subprocess
import sys
from pathlib import Path

import spacy
from spacy.tokens import DocBin
from spacy.training import Example


# ── 3a  Split & convert ──────────────────────────────────────────────────────

def load_annotations(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def to_docbin(nlp, examples: list[dict], output_path: Path):
    db = DocBin()
    skipped = 0
    for ex in examples:
        text     = ex["text"]
        entities = ex["entities"]   # [[start, end, label], ...]

        doc = nlp.make_doc(text)
        ents = []
        for start, end, label in entities:
            span = doc.char_span(start, end, label=label, alignment_mode="contract")
            if span is None:
                skipped += 1
                continue
            ents.append(span)

        # Remove overlapping spans (keep longest)
        ents = spacy.util.filter_spans(ents)
        doc.ents = ents
        db.add(doc)

    db.to_disk(output_path)
    print(f"  Saved {len(examples)} docs → {output_path}  (skipped {skipped} bad spans)")


def split_and_convert(annotations: list[dict], train_ratio: float = 0.8):
    random.seed(42)
    random.shuffle(annotations)

    split = int(len(annotations) * train_ratio)
    train_data = annotations[:split]
    dev_data   = annotations[split:]

    print(f"Split: {len(train_data)} train / {len(dev_data)} dev")

    # Use blank English model for tokenisation only
    nlp = spacy.blank("en")

    Path("training").mkdir(exist_ok=True)
    to_docbin(nlp, train_data, Path("training/train.spacy"))
    to_docbin(nlp, dev_data,   Path("training/dev.spacy"))


# ── 3b  Generate spaCy config ─────────────────────────────────────────────────

CONFIG_TEMPLATE = """\
[paths]
train = "training/train.spacy"
dev   = "training/dev.spacy"

[system]
gpu_allocator = null

[nlp]
lang    = "en"
pipeline = ["tok2vec", "ner"]

[components]

[components.tok2vec]
source = "en_core_web_sm"

[components.ner]
source = "en_core_web_sm"

[training]
dev_corpus   = "corpora.dev"
train_corpus = "corpora.train"

[training.optimizer]
@optimizers = "Adam.v1"
learn_rate  = 0.001

[training.batcher]
@batchers  = "spacy.batch_by_words.v1"
discard_oversize = false
tolerance        = 0.2

[training.batcher.size]
@schedules = "compounding.v1"
start      = 100
stop       = 1000
compound   = 1.001

[training.score_weights]
ents_per_type = null
ents_f        = 1.0
ents_p        = 0.0
ents_r        = 0.0

[corpora]

[corpora.train]
@readers = "spacy.Corpus.v1"
path = $\{paths.train\}
max_length = 0

[corpora.dev]
@readers = "spacy.Corpus.v1"
path = $\{paths.dev\}
max_length = 0

[initialize]
vectors    = "en_core_web_sm"
init_tok2vec = null
"""

def generate_config():
    """
    Use spacy init fill-config to produce a complete, validated config.
    Falls back to a hand-crafted template if the command fails.
    """
    base_cfg = Path("training/base_config.cfg")
    full_cfg = Path("config.cfg")

    # Write a minimal base config for init fill-config
    base_cfg.write_text(
        "[nlp]\nlang = \"en\"\npipeline = [\"ner\"]\n\n"
        "[components]\n\n[components.ner]\nfactory = \"ner\"\n\n"
        "[corpora]\n\n[corpora.train]\n@readers = \"spacy.Corpus.v1\"\n"
        "path = \"training/train.spacy\"\n\n[corpora.dev]\n@readers = \"spacy.Corpus.v1\"\n"
        "path = \"training/dev.spacy\"\n",
        encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, "-m", "spacy", "init", "fill-config",
         str(base_cfg), str(full_cfg)],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("Config generated via spacy init fill-config")

        # Patch: source from en_core_web_sm
        cfg_text = full_cfg.read_text(encoding="utf-8")
        if '[components.ner]\nfactory = "ner"' in cfg_text:
            cfg_text = cfg_text.replace(
                '[components.ner]\nfactory = "ner"',
                '[components.ner]\nsource = "en_core_web_sm"'
            )
            full_cfg.write_text(cfg_text, encoding="utf-8")
            print("Patched config: NER component will be loaded from en_core_web_sm")
    else:
        print("spacy init fill-config failed — writing manual config")
        print(result.stderr)
        full_cfg.write_text(CONFIG_TEMPLATE.replace("$\\{", "${"), encoding="utf-8")


# ── 3c  Train ─────────────────────────────────────────────────────────────────

def train_model():
    result = subprocess.run(
        [sys.executable, "-m", "spacy", "train", "config.cfg",
         "--output", "output",
         "--paths.train", "training/train.spacy",
         "--paths.dev",   "training/dev.spacy",
         "--training.max_steps", "2000",
         "--gpu-id", "-1"],
        text=True
    )
    if result.returncode == 0:
        print("\nTraining complete. Best model → output/model-best")
    else:
        print("Training failed. Check spaCy output above.")
        sys.exit(1)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ann_path = Path("annotations/annotations.json")

    if not ann_path.exists():
        raise SystemExit(f"ERROR: {ann_path} not found. Run 2_annotate.py first.")

    print("=== Step 3a — Load annotations & convert to DocBin ===")
    annotations = load_annotations(ann_path)
    print(f"Loaded {len(annotations)} annotated examples.")
    split_and_convert(annotations)

    print("\n=== Step 3b — Generate spaCy config ===")
    generate_config()

    print("\n=== Step 3c — Train the model ===")
    train_model()


if __name__ == "__main__":
    main()
