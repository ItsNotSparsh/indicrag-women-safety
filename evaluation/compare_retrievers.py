"""Compare first-stage lexical, dense and hybrid retrieval on frozen, paired queries."""
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
from search_official import CORPUS, MODEL, load_index

HOLDOUT_SHA = "ac3ed18d688b6e009be7697518caab46d09dd85caf209b5a25564cae032d8f5a"


def tokens(text):
    return re.findall(r"\w+", text.casefold())


def main():
    raw = (HERE / "retrieval-holdout-v1.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == HOLDOUT_SHA, "Holdout changed"
    examples = json.loads(raw)
    encoder, rows, vectors = load_index()
    ids = [r["chunk_id"] for r in rows]
    lexical = BM25Okapi([tokens(r["text"]) for r in rows])
    questions = [(r, lang, q) for r in examples for lang, q in r["queries"].items()]
    queries = encoder.encode(["query: " + q for _, _, q in questions], normalize_embeddings=True)
    groups = defaultdict(list)
    records = []
    for (r, lang, q), vec in zip(questions, queries):
        gold = set(r["gold_chunks"])
        assert gold and gold.issubset(ids)
        scores = lexical.get_scores(tokens(q))
        sparse = [i for i in np.argsort(-scores, kind="stable") if scores[i] > 0]
        dense = np.argsort(-(vectors @ vec), kind="stable")
        fusion = np.zeros(len(rows))
        for order in (sparse, dense):
            for rank, i in enumerate(order, 1):
                fusion[i] += 1 / (20 + rank)
        for name, order in [("BM25", sparse), ("E5", dense), ("Hybrid", np.argsort(-fusion, kind="stable"))]:
            ranked = [ids[i] for i in order]
            first = next((n for n, key in enumerate(ranked, 1) if key in gold), None)
            for group in (lang, "all"):
                groups[group, name].append(first)
            records.append(dict(question=q, language=lang, method=name, first_gold_rank=first,
                                top3=ranked[:3], gold_chunks=r["gold_chunks"]))
    summary = []
    for (group, name), ranks in groups.items():
        hits = sum(rank is not None and rank <= 3 for rank in ranks)
        mrr = sum(1/rank for rank in ranks if rank) / len(ranks)
        summary.append(dict(group=group, method=name, queries=len(ranks), hits=hits,
                            hit_rate_at_3=hits/len(ranks), mrr=mrr))
        print(group, name, f"{hits}/{len(ranks)}", round(mrr, 3))
    report = dict(holdout_sha256=HOLDOUT_SHA, corpus_sha256=hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
                  indexed_chunks=len(rows), model=MODEL.name, rrf_constant=20, summary=summary, results=records)
    (HERE / "retrieval-comparison-v1.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")


if __name__ == "__main__":
    main()
