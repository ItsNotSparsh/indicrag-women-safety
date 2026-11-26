"""Train a residual query projection over frozen E5 embeddings. Run from project venv."""
import csv
import json
import hashlib
from pathlib import Path

import torch
import torch.nn.functional as F
from search_official import ROOT, CORPUS, load_index

def main():
    torch.manual_seed(17)
    encoder, chunks, vectors = load_index()
    device = encoder.device
    docs = torch.tensor(vectors, device=device)
    pilot = ROOT / "evaluation/pilot.tsv"
    labels = list(csv.DictReader(pilot.read_text(encoding="utf-8-sig").splitlines(), delimiter="\t"))
    examples = []
    for item in labels:
        if item["doc"] == "-":
            continue
        gold = [i for i,r in enumerate(chunks) if r["source_file"].startswith({"O":"One_Stop","W":"Women_Helpline"}[item["doc"]]) and r["page_start"] == int(item["page"]) and item["anchor"].lower() in r["text"].lower()]
        if not gold:
            raise ValueError(item)
        for lang in ("en","hi","hinglish"):
            examples.append(dict(item,language=lang,question=item[lang],gold=gold))
    q = encoder.encode(["query: "+e["question"] for e in examples],normalize_embeddings=True,convert_to_tensor=True)
    q = q.detach().clone()
    mask = torch.zeros((len(q),len(docs)),device=device,dtype=torch.bool)
    for i,e in enumerate(examples):
        mask[i,e["gold"]] = True
    train = [i for i,e in enumerate(examples) if e["split"]=="train"]
    dev = [i for i,e in enumerate(examples) if e["split"]=="dev"]
    def ranks(x):
        order = (x @ docs.T).argsort(descending=True)
        return mask.gather(1,order).int().argmax(1)+1
    base = ranks(q)
    width = q.shape[1]
    a = torch.nn.Parameter(torch.randn(width,32,device=device)*0.01)
    b = torch.nn.Parameter(torch.zeros(32,width,device=device))
    optimizer = torch.optim.AdamW([a,b],lr=0.003)
    best_score = (1/base[dev].float()).mean().item()
    best = torch.zeros(width,width,device=device)
    epoch = 0
    for step in range(1,81):
        projected = F.normalize(q[train]+q[train]@a@b)
        logits = projected @ docs.T / 0.025
        loss = (logits.logsumexp(1)-logits.masked_fill(~mask[train],-torch.inf).logsumexp(1)).mean()
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        if step%5==0:
            with torch.no_grad():
                weight = a@b
                score = (1/ranks(F.normalize(q+q@weight))[dev].float()).mean().item()
                if score > best_score:
                    best_score, best, epoch = score,weight.clone(),step
    after = ranks(F.normalize(q+q@best))
    import numpy as np
    artifact=ROOT/"data/models/e5-query-pilot.npz"
    np.savez(artifact,weight=best.cpu().numpy(),corpus=hashlib.sha256(CORPUS.read_bytes()).hexdigest())
    for i,e in enumerate(examples):
        e["baseline_rank"],e["adapted_rank"]=int(base[i]),int(after[i])
        e["gold_chunks"]=[chunks[j]["chunk_id"] for j in e.pop("gold")]
    report=dict(selected_step=epoch,metric="rank of first annotated supporting chunk",examples=examples)
    (ROOT/"evaluation/pilot-results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    print("selected step",epoch,"stay ranks",[(int(x),int(y)) for x,y in zip(base[:3],after[:3])])
    for split in ["train","dev","test"]:
        for lang in ["en","hi","hinglish"]:
            rows=[e for e in examples if e["split"]==split and e["language"]==lang]
            print(split,lang,len(rows),*[sum(e[k]<=3 for e in rows) for k in ("baseline_rank","adapted_rank")])

if __name__=="__main__":
    main()

