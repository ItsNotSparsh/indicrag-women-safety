"""Search the official corpus with multilingual E5. Run from any directory."""
import argparse
import os
import hashlib
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data/processed/evidence_corpus/chunks.jsonl"
MODEL = ROOT / "data/models/multilingual-e5-small"


def load_index():
    raw = CORPUS.read_bytes()
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    rows = [r for r in rows if not r["historical_source"]]
    encoder = SentenceTransformer(str(MODEL), local_files_only=True)
    digest = hashlib.sha256(raw).hexdigest()[:16]
    cache = CORPUS.parent / f"e5-small-614241f-core-v1-{digest}.npy"
    if not cache.exists():
        vectors = encoder.encode(["passage: " + r["text"] for r in rows],
                                 batch_size=8, normalize_embeddings=True)
        np.save(cache, vectors)
    return encoder, rows, np.load(cache)


def retrieve(index, question, limit=3):
    encoder, rows, vectors = index
    query = encoder.encode("query: " + question, normalize_embeddings=True)
    if os.environ.get("INDICRAG_PILOT") == "1":
        with np.load(ROOT / "data/models/e5-query-pilot.npz") as adapter:
            if adapter["corpus"].item() != hashlib.sha256(CORPUS.read_bytes()).hexdigest():
                raise ValueError("Corpus changed. Re-run scripts/train_pilot.py.")
            query = query + query @ adapter["weight"]
            query /= np.linalg.norm(query)
    scores = vectors @ query
    return [(rows[i], float(scores[i])) for i in np.argsort(-scores)[:limit]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    args = parser.parse_args()
    for rank, (row, score) in enumerate(retrieve(load_index(), args.question), 1):
        print(f"{rank}. {row['source_file']} | PDF page {row['page_start']} | {score:.3f}")
        print(row["text"], end="\n\n")


if __name__ == "__main__":
    main()


