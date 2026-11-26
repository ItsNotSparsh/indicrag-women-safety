"""Train and evaluate a small local Qwen LoRA adapter on reviewed SOP examples."""
import csv
import json
import random
import re
from pathlib import Path

import torch
from torch import nn
from transformers import AutoTokenizer, AutoModelForCausalLM

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "evaluation"
MODEL = ROOT / "data/models/qwen-answer"
WEIGHTS = ROOT / "data/models/qwen-pilot.pt"


class LoRALinear(nn.Module):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.down = nn.Linear(base.in_features, 8, bias=False, device=base.weight.device)
        self.up = nn.Linear(8, base.out_features, bias=False, device=base.weight.device)
        nn.init.zeros_(self.up.weight)

    def forward(self, x):
        delta = self.up(self.down(x.float())).to(x.dtype)
        return self.base(x) + 2 * delta


def attach(model):
    for layer in model.model.layers[-8:]:
        for name in ("q_proj", "v_proj"):
            setattr(layer.self_attn, name, LoRALinear(getattr(layer.self_attn, name)))


def prompt(tok, question, passage, lang):
    system = ("Answer briefly in " + {"hi":"Hindi (Devanagari)", "hinglish":"Roman Hinglish", "en":"English"}[lang]
              + ". Use only the supplied SOP passage. Preserve limits, exceptions and authorization conditions. "
              "If the passage cannot answer the question, reply UNKNOWN.")
    return tok.apply_chat_template([{"role":"system","content":system},
        {"role":"user","content":f"Passage: {passage}\nQuestion: {question}"}],
        tokenize=False,add_generation_prompt=True)


def generate(tok, model, q, passage, lang):
    inputs = tok(prompt(tok,q,passage,lang),return_tensors="pt",add_special_tokens=False).to(model.device)
    with torch.inference_mode():
        out = model.generate(**inputs,do_sample=False,max_new_tokens=160)
    return tok.decode(out[0,inputs.input_ids.shape[1]:],skip_special_tokens=True).strip()


def main():
    random.seed(17)
    torch.manual_seed(17)
    tok = AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(MODEL,dtype=torch.bfloat16,local_files_only=True).to("cuda")
    model.requires_grad_(False)
    chunks = [json.loads(l) for l in (ROOT/"data/processed/evidence_corpus/chunks.jsonl").read_text(encoding="utf8").splitlines()]
    by_id = {r["chunk_id"]:r["text"] for r in chunks}
    examples = json.loads((DIR/"pilot-results.json").read_text(encoding="utf8"))["examples"]
    translations = {r["anchor"]:r for r in csv.DictReader((DIR/"train-answers.tsv").read_text(encoding="utf-8-sig").splitlines(),delimiter="\t")}
    train=[]
    probe=[]
    for e in examples:
        passage = by_id[e["gold_chunks"][0]]
        lang = e["language"]
        if e["split"]=="train":
            target=e["reference"] if lang=="en" else translations[e["anchor"]][lang]
            train.append((e["question"],passage,lang,target))
        if e["split"]=="test" or e["anchor"]=="relocation to Shakti Sadan":
            probe.append(dict(question=e["question"],language=lang,split=e["split"],passage=passage,reference=e["reference"]))
    evidence=train[0][1]
    for q, lang in [("Who is on the phone now?","en"),("आज हेल्पलाइन पर किसने फोन किया?","hi"),("Aaj ka caller kaun hai?","hinglish")]:
        train.append((q,evidence,lang,"UNKNOWN"))
    for r in csv.DictReader((DIR/"pilot.tsv").read_text(encoding="utf-8-sig").splitlines(),delimiter="\t"):
        if r["split"]=="test" and r["doc"]=="-":
            for lang in ("en","hi","hinglish"):
                probe.append(dict(question=r[lang],language=lang,split="test",passage=evidence,reference="UNKNOWN"))
    def evaluate(key):
        model.eval()
        for e in probe:
            e[key]=generate(tok,model,e["question"],e["passage"],e["language"])
        (DIR/"generator-oracle.json").write_text(json.dumps(probe,indent=2,ensure_ascii=False),encoding="utf8")
    evaluate("baseline")
    attach(model)
    model.train()
    opt=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=0.0005)
    for epoch in range(3):
        random.shuffle(train)
        for q,p,lang,answer in train:
            prefix=tok.encode(prompt(tok,q,p,lang),add_special_tokens=False)
            tail=tok.encode(answer,add_special_tokens=False)+[tok.eos_token_id]
            ids=torch.tensor([prefix+tail],device=model.device)
            labels=ids.clone()
            labels[:,:len(prefix)]=-100
            loss=model(input_ids=ids,labels=labels,use_cache=False).loss
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_([v for v in model.parameters() if v.requires_grad],1)
            opt.step()
        print("Epoch",epoch+1,"finished",flush=True)
    torch.save({n:p.detach().cpu() for n,p in model.named_parameters() if p.requires_grad},WEIGHTS)
    evaluate("adapted")


if __name__=="__main__":
    main()

