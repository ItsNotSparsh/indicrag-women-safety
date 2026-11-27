"""Paired direct-vs-hybrid-RAG inference with the local base Qwen checkpoint."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import torch
from rank_bm25 import BM25Okapi
from transformers import AutoModelForCausalLM, AutoTokenizer
from compare_retrievers import HERE, CORPUS, HOLDOUT_SHA, load_index, tokens

NEGATIVES = [
    ("How many beds are empty at my nearest OSC right now?", "अभी मेरे सबसे पास वाले केंद्र में कितने बिस्तर खाली हैं?", "Mere nearest OSC mein abhi kitne beds khali hain?"),
    ("Who is on duty at my local helpline desk this morning?", "आज सुबह मेरी स्थानीय हेल्पलाइन डेस्क पर किसकी ड्यूटी है?", "Aaj subah meri local helpline desk par kiski duty hai?"),
    ("Has my complaint from yesterday been closed yet?", "क्या मेरी कल की शिकायत अब बंद हो चुकी है?", "Meri kal wali complaint ab tak close ho gayi hai kya?"),
]
SYSTEM = ("The questions concern India's One Stop Centre and Women Helpline operating procedures. "
          "Answer briefly in English. If the question cannot be answered reliably, reply UNKNOWN. "
          "When passages are provided, use only those passages and add the supporting passage number in brackets. "
          "Never invent live or personal records.")


def prepare():
    frozen = (HERE/"retrieval-holdout-v1.json").read_bytes()
    assert hashlib.sha256(frozen).hexdigest() == HOLDOUT_SHA
    benchmark = json.loads((HERE/"retrieval-comparison-v1.json").read_text(encoding="utf8"))
    assert benchmark["corpus_sha256"] == hashlib.sha256(CORPUS.read_bytes()).hexdigest()
    prior = {r["question"]: r["top3"] for r in benchmark["results"] if r["method"]=="Hybrid"}
    encoder, chunks, vectors = load_index()
    bm = BM25Okapi([tokens(r["text"]) for r in chunks])
    cases = []
    for i, item in enumerate(json.loads(frozen)):
        for lang, q in item["queries"].items():
            cases.append(dict(intent=i, lang=lang, question=q, gold=item["gold_chunks"], top3=prior[q]))
    for i, versions in enumerate(NEGATIVES,15):
        for lang,q in zip(("en","hi","hinglish"), versions):
            dense = vectors @ encoder.encode("query: "+q, normalize_embeddings=True)
            sparse = bm.get_scores(tokens(q))
            ranks = np.zeros(len(chunks))
            for order in (np.argsort(-dense,kind="stable"), [k for k in np.argsort(-sparse,kind="stable") if sparse[k]>0]):
                for rank,k in enumerate(order,1):
                    ranks[k] += 1/(20+rank)
            top = [chunks[k]["chunk_id"] for k in np.argsort(-ranks,kind="stable")[:3]]
            cases.append(dict(intent=i,lang=lang,question=q,gold=[],top3=top))
    return cases,{r["chunk_id"]:r["text"] for r in chunks}


def main():
    cases, passages = prepare()
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--small",action="store_true")
    small=parser.parse_args().small
    folder = HERE.parent/"data/models"/("qwen-small" if small else "qwen-answer")
    tok = AutoTokenizer.from_pretrained(folder,local_files_only=True,padding_side="left")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModelForCausalLM.from_pretrained(folder,local_files_only=True,
                dtype=torch.float16 if device=="cuda" else torch.float32).to(device).eval()
    result = dict(model=str(model.config.model_type), checkpoint=folder.name, device=device,
                  system=SYSTEM, max_new_tokens=80, do_sample=False, holdout_sha256=HOLDOUT_SHA,cases=cases)
    for mode in ("direct","rag"):
        start=time.perf_counter()
        for offset in range(0,len(cases),3):
            group=cases[offset:offset+3]
            prompts=[]
            for case in group:
                content="Question: "+case["question"]
                if mode=="rag":
                    content+="\nPassages:\n"+"\n".join(f"[{n}] {passages[k]}" for n,k in enumerate(case["top3"],1))
                prompts.append(tok.apply_chat_template([dict(role="system",content=SYSTEM),dict(role="user",content=content)],
                                                      tokenize=False,add_generation_prompt=True))
            inputs=tok(prompts,padding=True,add_special_tokens=False,return_tensors="pt").to(device)
            with torch.inference_mode():
                out=model.generate(**inputs,max_new_tokens=80,do_sample=False,pad_token_id=tok.pad_token_id)
            for case,reply in zip(group,tok.batch_decode(out[:,inputs.input_ids.shape[1]:],skip_special_tokens=True)):
                case[mode]=reply.strip()
        result[mode+"_batch_seconds"]=time.perf_counter()-start
        print(mode,"finished",flush=True)
    (HERE/("qwen-small-paired.json" if small else "qwen-qa-paired.json")).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")


if __name__=="__main__":
    main()
