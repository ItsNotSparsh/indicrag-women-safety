"""Paired translation, normalization, reranking and selective retrieval experiments."""
import json,re,sys
import numpy as np
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from compare_retrievers import HERE,load_index,tokens,BM25Okapi
sys.path.insert(0,str(HERE.parent/"app"))
from sop_search import relevance

def main():
    data=json.loads((HERE/"qwen-qa-paired.json").read_bytes())["cases"]
    folder=HERE.parent/"data/models/qwen-answer"
    tok=AutoTokenizer.from_pretrained(folder,padding_side="left",local_files_only=True)
    device="cuda" if torch.cuda.is_available() else "cpu"
    model=AutoModelForCausalLM.from_pretrained(folder,dtype=torch.float16 if device=="cuda" else torch.float32,local_files_only=True).to(device).eval()
    for c in data:
        q=c["question"]
        if c["lang"]=="en":
            c["translation"]=q
            continue
        prompt=tok.apply_chat_template([dict(role="system",content="Translate the question into English. Return only a translation. Preserve numbers and names. Do not answer."),dict(role="user",content=q)],tokenize=False,add_generation_prompt=True)
        batch=tok(prompt,return_tensors="pt",add_special_tokens=False).to(device)
        with torch.inference_mode():
            out=model.generate(**batch,max_new_tokens=72,do_sample=False)
        c["translation"]=tok.decode(out[0,batch.input_ids.shape[1]:],skip_special_tokens=True).strip()
    del model
    encoder,rows,vectors=load_index()
    bm=BM25Okapi([tokens(r["text"]) for r in rows])
    ids=[r["chunk_id"] for r in rows]
    results=[]
    for c in data:
        q=c["question"]
        normalized=re.sub(r"\bkr\b","kar",re.sub(r"\brha\b","raha"," ".join(q.casefold().split())))
        texts=[q,c["translation"],normalized]
        ds=encoder.encode(["query: "+t for t in texts],normalize_embeddings=True)@vectors.T
        lexical=bm.get_scores(tokens(q))
        fused=np.zeros(len(rows))
        for order in (np.argsort(-ds[0],kind="stable"),[i for i in np.argsort(-lexical,kind="stable") if lexical[i]>0]):
            fused[order]+=1/(21+np.arange(len(order)))
        shortlist=np.argsort(-fused,kind="stable")[:10]
        scores=relevance(q,[rows[i]["text"] for i in shortlist])
        order=shortlist[np.argsort(-scores,kind="stable")]
        methods={"direct":np.argsort(-ds[0],kind="stable"),"translated":np.argsort(-ds[1],kind="stable"),"normalized":np.argsort(-ds[2],kind="stable"),"hybrid":shortlist,"reranked":order}
        results.append(dict(question=q,lang=c["lang"],translation=c["translation"],gold=c["gold"],score=float(max(scores)),top3={k:[ids[i] for i in v[:3]] for k,v in methods.items()}))
    (HERE/"bonus-retrieval.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf8")
if __name__=="__main__":main()
