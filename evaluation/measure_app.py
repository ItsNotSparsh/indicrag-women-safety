import sys,time,csv,json,os
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/"app"),str(root/"scripts")]
from service import respond
from search_official import load_index,retrieve
folder=root/"evaluation"
qs=[r for r in csv.DictReader((folder/"pilot.tsv").read_text(encoding="utf-8-sig").splitlines(),delimiter="\t") if r["split"]=="test"]
results=[]
for i,r in enumerate(qs):
 for lang in ("en","hi","hinglish"):
    q=r[lang]; start=time.perf_counter()
    a=respond(q,{"hinglish":"mix"}.get(lang,lang))
    results.append(dict(intent=i,lang=lang,q=q,answer=a,ms=round((time.perf_counter()-start)*1000,2),gold=r["reference"]))
    print(i,lang,a["kind"],a.get("label",""),a.get("source",""),flush=True)
idx=load_index()
for r in results:
 label=qs[r["intent"]]
 if label["doc"]=="-":continue
 for mode in ("0","1"):
    os.environ["INDICRAG_PILOT"]=mode
    start=time.perf_counter()
    hits=retrieve(idx,r["q"],len(idx[1]))
    r["retrieval_ms_"+mode]=round(1000*(time.perf_counter()-start),2)
    r["rank_"+mode]=next(n for n,(row,_) in enumerate(hits,1) if row["source_file"].startswith({"O":"One_Stop","W":"Women_Helpline"}[label["doc"]]) and row["page_start"]==int(label["page"]) and label["anchor"].lower() in row["text"].lower())
(folder/"accuracy-after.json").write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding="utf8")
print("first/warm median/p95 ms",results[0]["ms"],np.percentile([r["ms"] for r in results[1:]],[50,95]))
for mode in "01":
 rr=[r for r in results if "rank_"+mode in r];print(mode,sum(r["rank_"+mode]<=3 for r in rr),np.median([r["retrieval_ms_"+mode] for r in rr]))
