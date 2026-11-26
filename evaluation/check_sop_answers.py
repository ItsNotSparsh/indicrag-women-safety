"""Evaluate the live answer router on the labeled regression, challenge and audit questions."""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "evaluation"
sys.path.insert(0, str(ROOT / "app"))
from service import respond
from sop_search import SOURCES, cards


def cases():
    with (DIR / "pilot.tsv").open(encoding="utf-8-sig",newline="") as file:
        for row in csv.DictReader(file,delimiter="\t"):
            if row["split"] == "test":
                for field, lang in (("en","en"),("hi","hi"),("hinglish","mix")):
                    yield "regression", row[field], lang, {"post assessment":"nature of the call shall be transferred", "sign language":"access to trained personnel"}.get(row["anchor"],row["anchor"]) if row["doc"] != "-" else "unknown"
    for suite in ("challenge", "audit", "final-check", "unseen", "release"):
        for q, lang, expect in json.loads((DIR / f"sop-{suite}.json").read_text(encoding="utf-8-sig")):
            yield suite, q, lang, expect


EXCERPT_PAGES = {
    "7 feet x 4 feet": ("O",22), "ramps with handrails": ("O",19),
    "existing administrative fund": ("O",20), "Unique ID Number": ("W",10),
    "6 feet x 4 feet": ("O",22), "breastfeeding or infant care": ("O",20),
    "toys / books": ("O",20), "non-slip flooring": ("O",19), "accessible restrooms": ("O",20)
}


def grade(result, expected, lang):
    if expected in ("unknown","emergency","directory"):
        return result["kind"] == expected
    if expected.startswith("@"):
        phrase = expected[1:]
        doc, page = EXCERPT_PAGES[phrase]
        return (result["kind"] in {"answer","excerpt"} and phrase.casefold() in result["answer"].casefold()
                and result["url"] == f"/source/{SOURCES[doc]}.pdf#page={page}")
    if result["kind"] != "answer" or result["language"] != lang:
        return False
    return any(expected.casefold() in c["anchor"].casefold()
               and result["answer"] == c["answers"][lang]
               and result["url"] == f'/source/{SOURCES[c["doc"]]}.pdf#page={c["page"]}'
               for c in cards())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=DIR / "sop-results.json")
    args = parser.parse_args()
    results=[]
    for suite, question, lang, expected in cases():
        start=time.perf_counter()
        response=respond(question,lang)
        ms=round((time.perf_counter()-start)*1000,1)
        ok=grade(response,expected,lang)
        results.append(dict(suite=suite,question=question,lang=lang,expected=expected,ok=ok,ms=ms,response=response))
        if not ok:
            print("MISS",suite,question,"=>",response["kind"],response["answer"][:180],flush=True)
    args.output.write_text(json.dumps(results,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    for k in ("regression","challenge","audit","final-check","unseen","release"):
        sub=[r for r in results if r["suite"]==k]
        print(k,sum(r["ok"] for r in sub),"/",len(sub))
    warm=[r["ms"] for r in results[1:] if r["response"]["kind"] in ("answer","excerpt")]
    print("First request, ms:",results[0]["ms"],"Warm answer/excerpt median and p95, ms:",np.percentile(warm,[50,95]))
    if any(not r["ok"] for r in results if r["suite"] == "regression"):
        raise SystemExit("An original regression case failed. See the JSON report.")


if __name__ == "__main__":
    main()
