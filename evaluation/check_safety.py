"""Run Hindi IndicGuard or SurakshaEval examples without writing prompts or answers."""
import argparse
import collections
import json
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"app"))
from service import respond

def main():
    p=argparse.ArgumentParser()
    p.add_argument("file",type=Path)
    p.add_argument("--question-field",default="prompt")
    p.add_argument("--limit",type=int,default=100)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    text=args.file.read_text(encoding="utf-8-sig")
    rows=json.loads(text) if text.lstrip().startswith("[") else [json.loads(l) for l in text.splitlines() if l.strip()]
    random.Random(17).shuffle(rows)
    counts=collections.Counter()
    for row in rows[:args.limit]:
        q=row[args.question_field]
        if not isinstance(q,str): raise ValueError("Select a text question field.")
        reply=respond(q,"hi")
        counts[(str(row.get("prompt_label","unlabelled")),reply["kind"])]+=1
    report=dict(dataset_file=args.file.name,seed=17,rows=sum(counts.values()),
                route_counts=[dict(label=k[0],route=k[1],count=v) for k,v in sorted(counts.items())],
                interpretation="Route audit only. Prompt safety labels do not establish whether a reply is helpful or an emergency. No safety accuracy inferred.")
    args.output.write_text(json.dumps(report,indent=2),encoding="utf8")
    print(report)
if __name__=="__main__":main()

