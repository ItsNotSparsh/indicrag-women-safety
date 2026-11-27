"""Report macro averages over saved trials. Hindi and Hinglish retrieve English evidence."""
import json
import re
from collections import Counter
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer

D = Path(__file__).resolve().parent
def read(name):
    return json.loads((D/name).read_bytes())

def tokens(text):
    return re.findall(r"\w+", text.casefold())

def main():
    ranks = read("retrieval-comparison-v1.json")["results"]
    cases = read("qwen-qa-paired.json")["cases"]
    grades = {(x["intent"],x["language"],x["mode"]):x["grade"] for x in read("qwen-qa-grades.json")["grades"]}
    lines = (D/"qwen-qa-rubric.txt").read_text(encoding="utf-8-sig").splitlines()
    refs = [line.split(". ",1)[1].split(" Multiple supported")[0] for line in lines if re.match(r"^\d+\. ",line)]
    assert len(refs)==15
    model=SentenceTransformer(str(D.parent/"data/models/multilingual-e5-small"),local_files_only=True)
    texts=sorted(set(refs)|{c[m] for c in cases for m in ("direct","rag")})
    vectors=dict(zip(texts,model.encode(["query: "+s for s in texts],normalize_embeddings=True)))
    out={}
    for lang in ("all","en","hi","hinglish"):
        group=out[lang]={}
        for method in ("BM25","E5","Hybrid"):
            values=[]
            for r in ranks:
                if r["method"]!=method or lang not in ("all",r["language"]):continue
                hits=len(set(r["top3"]) & set(r["gold_chunks"]))
                rank=r["first_gold_rank"]
                values.append([hits/len(r["gold_chunks"]),hits/3,bool(hits),1/rank if rank else 0])
            group[method]=dict(zip(("Recall@3","Precision@3","Hit@3","MRR"),np.mean(values,axis=0)))
        for mode in ("direct","rag"):
            values=[]
            counts=Counter()
            for c in cases:
                if lang not in ("all",c["lang"]):continue
                grade=grades[c["intent"],c["lang"],mode]
                attempt=grade in ("full","partial","incorrect")
                positive=bool(c["gold"])
                counts["TP" if positive and attempt else "FN" if positive else "FP" if attempt else "TN"]+=1
                if positive:
                    ans,ref=c[mode],refs[c["intent"]]
                    a,b=tokens(ans),tokens(ref)
                    overlap=sum((Counter(a)&Counter(b)).values())
                    values.append([a==b,2*overlap/(len(a)+len(b)),float(vectors[ans]@vectors[ref]),grade=="full"])
            tp,fp,fn,tn=[counts[k] for k in ("TP","FP","FN","TN")]
            group[mode]=dict(zip(("normalized_EM","token_F1","semantic_cosine","fully_correct"),np.mean(values,axis=0)))
            group[mode]["answerability"]=dict(TP=tp,FP=fp,FN=fn,TN=tn,accuracy=(tp+tn)/sum(counts.values()),precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn),F1=2*tp/(2*tp+fp+fn))
    (D/"section6-metrics.json").write_text(json.dumps(out,indent=2),encoding="utf8")
    print(out["all"])
if __name__=="__main__":
    main()
