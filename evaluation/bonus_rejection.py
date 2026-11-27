"""Replay the paired 1.5B RAG outputs with a relevance gate on the actual supplied passages."""
import json,sys
from pathlib import Path
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/"app"))
from sop_search import relevance

def main():
    cases=json.loads((D/"qwen-qa-paired.json").read_bytes())["cases"]
    labels=json.loads((D/"qwen-qa-grades.json").read_bytes())["grades"]
    grades={(r["intent"],r["language"]):r for r in labels if r["mode"]=="rag"}
    chunks={r["chunk_id"]:r["text"] for r in map(json.loads,(D.parent/"data/processed/evidence_corpus/chunks.jsonl").read_bytes().splitlines())}
    results=[]
    for c in cases:
        score=float(max(relevance(c["question"],[chunks[k] for k in c["top3"]])))
        label=grades[c["intent"],c["lang"]]
        results.append(dict(question=c["question"],score=score,grade=label["grade"],unsupported=label["material_unsupported_fact"]))
    for threshold in (None,1.0,3.0):
        kept=[r for r in results if threshold is None or r["score"]>=threshold]
        print(threshold,sum(r["grade"]=="full" for r in kept),sum(r["unsupported"] for r in kept))
    (D/"bonus-rejection.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf8")
if __name__=="__main__":main()
