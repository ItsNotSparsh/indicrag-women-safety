"""Answer from page-verified translations or display a clearly identified SOP excerpt."""
import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {"O": "One_Stop_Centre_SOP_English", "W": "Women_Helpline_181_SOP_English"}
LABEL = {"en": "Official SOP", "hi": "आधिकारिक एसओपी", "mix": "Official SOP", "ta": "அதிகாரப்பூர்வ நடைமுறை"}
EXCERPT = {"en": "Related passage in English", "hi": "संबंधित मूल अंश (अंग्रेज़ी)", "mix": "Related passage (English)", "ta": "தொடர்புடைய ஆங்கிலப் பகுதி"}


def normalize(text):
    return " ".join(re.sub(r"[?!.।,？–—-]+", " ", text.casefold()).split())


def input_language(question):
    if re.search(r"[\u0900-\u097f]", question):
        return "hi"
    if re.search(r"[\u0b80-\u0bff]", question):
        return "ta"
    if re.search(r"\b(kya|hai|hain|hota|hoti|hoga|hog[aie]|kaise|mein|mujhe|kaun|aur|milti|milega|kitn[aei]|kab|kahan|koi|ka|ki|ke|chahiye|mujh|se|pe|par|haan|nahi|bina|sakta|milta|mujhe|tak|toh)\b",question,re.I):
        return "mix"
    return "en"


@lru_cache(maxsize=1)
def cards():
    records = json.loads((ROOT / "app/sop-answers.json").read_text(encoding="utf-8-sig"))
    pages = {}
    for code, name in SOURCES.items():
        path = ROOT / "data/processed/official_pages" / (name + ".jsonl")
        if path.is_file() and (ROOT / "data/official_sources" / (name + ".pdf")).is_file():
            pages[code] = {p["page"]: p["text"] for p in map(json.loads, path.read_text(encoding="utf8").splitlines())}
    result = []
    for card in records:
        page = pages.get(card["doc"], {}).get(card["page"], "")
        pos = page.casefold().find(card["anchor"].casefold())
        if pos < 0:
            continue
        # Keep the original spelling, including OCR artifacts, in the displayed quotation.
        start = page.rfind(". ", 0, pos) + 2 if ". " in page[:pos] else 0
        end = page.find(". ", pos + len(card["anchor"]))
        if card.get("quote_end"):
            last = page.find(card["quote_end"],pos)
            if last < 0:
                continue
            end = last + len(card["quote_end"]) - 1
        quote = page[start:end+1 if end >= 0 else len(page)]
        result.append(dict(card, quote=quote.strip()))
    return result


def citation(filename, page):
    return {"source": f"{filename} · PDF p. {page}", "url": f"/source/{filename}#page={page}"}


def render(card, lang, confidence=None, basis="Verified rule match"):
    answers = card["answers"]
    return dict(kind="answer", confidence=confidence, confidence_basis=basis, label=LABEL[lang], answer=answers[lang], language=lang,
                speech_text=answers["hi" if lang == "mix" else lang], evidence=card["quote"],
                **citation(SOURCES[card["doc"]]+".pdf", card["page"]))


@lru_cache(maxsize=1)
def index():
    from search_official import load_index
    from rank_bm25 import BM25Okapi
    encoder, rows, vectors = load_index()
    items = [(i, q) for i, card in enumerate(cards()) for q in [*card["questions"].values(), *card.get("alternatives", [])]]
    alias_vectors = encoder.encode(["query: "+q for _, q in items], normalize_embeddings=True) if items else []
    lexical = BM25Okapi([re.findall(r"\w+", row["text"].casefold()) for row in rows])
    # Rare terms present in several retrieved chunks can distinguish nearby
    # topics, e.g. a question about infant care from a generic facilities FAQ.
    from collections import Counter
    frequencies = Counter(word for document in lexical.doc_freqs for word in document)
    specific = {w for w,n in frequencies.items() if len(w)>=5 and 0<n<=4 and w.isascii()}
    return encoder, rows, vectors, lexical, items, alias_vectors, specific


@lru_cache(maxsize=1)
def reranker():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    path = ROOT / "data/models/mmarco-reranker"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModelForSequenceClassification.from_pretrained(path, local_files_only=True).to(device).eval()
    return AutoTokenizer.from_pretrained(path,local_files_only=True), model


def relevance(question, texts):
    import torch
    tokenizer, model = reranker()
    scores = []
    with torch.inference_mode():
        for start in range(0, len(texts), 12):
            group = texts[start:start+12]
            batch = tokenizer([question]*len(group), group, padding=True, truncation=True,
                              max_length=384, return_tensors="pt")
            scores.extend(model(**batch.to(model.device)).logits[:, 0].float().cpu().tolist())
    return np.asarray(scores)


# Short forms and bilingual terms used by the SOPs. Preserve the original query
# for the reranker and evaluate the requested attribute against the candidate.
TERMS = [
    (r"(?:how long|how many (?:days|nights)).{0,65}(?:sleep|stay|spend|shelter)|(?:sleep|stay|shelter).{0,30}how long", r"stay|staying|shelter for", "duration of temporary shelter stay"),
    (r"\b(?:salary|salaries|wages?|payroll|bonus|vetan|tankh[wa]+h?)\b|वेतन|तनख्वाह|बोनस|சம்பளம்", r"salary|wages|remuneration|bonus", "staff compensation"),
    (r"\b(?:text the|text message|sms|email|e-mail)\b|एसएमएस|ईमेल", r"SMS|email", "SMS email"),
    (r"overhear|eavesdrop|(?:koi|कोई).{0,30}(?:sun sak|सुन सक)|\b(?:privacy|private conversation)\b", r"audio and visual privacy", "counselling privacy"),
    (r"non[- ]emergency|non[- ]urgent|गैर[- ]?आपात", r"non[- ]emergency", "non-emergency"),
]


def helpline_routing(question):
    if not re.search(r"\bcalls?\b|कॉल|கால்|அழைப்ப",question,re.I):
        return None
    if not re.search(r"forward|transfer|refer|where|who handles|kahan|किस|कहाँ|भेज|எங்கே|அனுப்ப",question,re.I):
        return None
    if re.search(r"non[- ]*(?:urgent|emergency)|गैर.{0,4}आपात|ग़ैर.{0,4}आपात",question,re.I):
        return "nature of the call shall be transferred to WHL Units of OSCs"
    if re.search(r"\bemergency\b|आपात|அவசர",question,re.I):
        return "forwarded by the WHL"
    return None


def requested_terms(question):
    return [(support, hint) for expression, support, hint in TERMS if re.search(expression,question,re.I)]


def candidates(question):
    encoder, rows, vectors, lexical, aliases, alias_vectors, specific = index()
    hints = requested_terms(question)
    search_text = re.sub(r"\bSakhi cent(?:er|re)\b", "One Stop Centre", question, flags=re.I)
    if re.search(r"how long.*sleep (?:at|in).*(?:centre|center|shelter|OSC)", search_text, re.I):
        search_text = re.sub(r"\bsleep\b", "stay in temporary shelter", search_text, flags=re.I)
    search_text += "".join(" / " + hint for _,hint in hints)
    query = encoder.encode("query: "+search_text, normalize_embeddings=True)
    sim = {}
    closest = {}
    if aliases:
        for (group, alias), score in zip(aliases, alias_vectors @ query):
            if score > sim.get(group, 0.0):
                sim[group] = float(score)
                closest[group] = alias
    ids = sorted(sim, key=sim.get, reverse=True)[:6]
    language = input_language(question)
    texts = []
    for i in ids:
        item = cards()[i]
        title = item["questions"].get(language, item["questions"]["en"])
        if closest[i] in item.get("alternatives", []) and input_language(closest[i]) == language:
            title += " " + closest[i]
        texts.append(title+" "+item["answers"][language])
    dense = vectors @ query
    bm = lexical.get_scores(re.findall(r"\w+", question.casefold()))
    # Reciprocal rank fusion avoids mixing the scales of BM25 and cosine scores.
    fusion = np.zeros(len(rows))
    for scores in [dense, bm] if bm.max() > 0 else [dense]:
        fusion[np.argsort(-scores)] += 1 / (20 + np.arange(1, len(rows)+1))
    selected = []
    for i in np.argsort(-fusion):
        row = rows[i]
        if Path(row["source_file"]).stem not in SOURCES.values() or not (ROOT/"data/official_sources"/row["source_file"]).is_file():
            continue
        selected.append(row)
        if len(selected) == 5:
            break
    scores = relevance(search_text, texts + [r["text"] for r in selected])
    for j,i in enumerate(ids):
        card = cards()[i]
        support = card["answers"]["en"] + " " + card["questions"]["en"] + " " + card["quote"]
        if any(not re.search(pattern, support, re.I) for pattern,_ in hints):
            scores[j] = -float("inf")
    ranked = sorted([(float(s), sim[i], i) for i, s in zip(ids, scores)], reverse=True)
    raw = sorted(zip(scores[len(ids):], range(len(selected))), reverse=True)
    return ranked, [(float(s), selected[i]) for s,i in raw]


def source_excerpt(question, lang, passages):
    # Select a contiguous citation-sized window from the leading chunks. Every
    # displayed character comes from the cited chunk, including any OCR spelling.
    windows = {}
    for _, row in passages[:4]:
        passage = row["text"]
        boundaries = [0] + [m.end() for m in re.finditer(r"(?<=[.!?])\s+|(?<=\s)(?=[●•·] )", passage)]
        boundaries.append(len(passage))
        for position, start in enumerate(boundaries[:-1],1):
            stop = boundaries[position]
            while stop - start < 160 and position + 1 < len(boundaries):
                position += 1
                stop = boundaries[position]
            snippet = passage[start:stop].strip()
            if len(snippet) >= 40:
                windows.setdefault(snippet, row)
    if not windows:
        return None
    hints = requested_terms(question)
    snippets = [snippet for snippet in windows if all(re.search(p,snippet,re.I) for p,_ in hints)]
    if not snippets:
        return None
    def source_title(snippet):
        return Path(windows[snippet]["source_file"]).stem.replace("_SOP_English", "").replace("_"," ")
    scores = relevance(question, [source_title(s) + ". " + s for s in snippets])
    best = int(scores.argmax())
    origin = windows[snippets[best]]
    same_passage = origin is passages[0][1]
    gap = scores[best] - np.partition(scores,-2)[-2] if len(scores) > 1 else 0
    if scores[best] < 3.0 and not (scores[best] >= 0.75 and same_passage and gap >= 1.5):
        return None
    snippet = snippets[best]
    row = windows[snippet]
    return dict(kind="excerpt", confidence=round(float(scores[best]),3), confidence_basis="Reranker relevance logit", label=EXCERPT[lang], language="en", answer=snippet,
                **citation(row["source_file"], row["page_start"]))


def evidence(question, lang):
    routing_anchor = helpline_routing(question)
    if re.search(r"papers|documents?|\bID(?: proof| card)?\b|kagaz|काग[ज़ज]|पहचान पत्र", question, re.I) and re.search(
        r"without|no (?:papers|documents|ID)|lack of|don.t have|refuse|turn me away|bina|nahi|बिना|नहीं", question, re.I
    ) and re.search(r"OSC|Sakhi|cent(?:re|er)|services|assistance|मदद|सेंटर|केंद्र", question, re.I):
        routing_anchor = "no woman shall be denied services due to lack of documentation"
    for card in cards():
        if routing_anchor and card["anchor"] == routing_anchor:
            return render(card,lang)
        if any(normalize(question) == normalize(q) for q in card["questions"].values()):
            return render(card, lang, 1.0, "Exact question match")
    if routing_anchor:
        return None
    ranked, passages = candidates(question)
    if ranked and np.isfinite(ranked[0][0]):
        score, similarity, i = ranked[0]
        gap = score - ranked[1][0] if len(ranked)>1 else float("inf")
        card = cards()[i]
        # Corroborate borderline card matches against independently retrieved PDF passages.
        corroborated = bool(passages and passages[0][1]["source_file"] == SOURCES[card["doc"]]+".pdf"
                            and passages[0][1]["page_start"] == card["page"]
                            and card["anchor"].casefold() in passages[0][1]["text"].casefold())
        confident = similarity >= 0.85 and score >= 1.0 and gap >= 0.65
        separated = similarity >= 0.875 and score >= -2 and gap >= 3
        confirmed = corroborated and similarity >= 0.86 and (
            (gap >= 3 and score >= -4.25) or (score >= 0 and passages[0][0] >= -2))
        agreement = corroborated and score >= 2.0 and gap >= 4 and similarity >= 0.80
        stronger_source = passages and passages[0][0] >= 4 and passages[0][0] >= score+4
        # Let a strongly relevant passage override a weak FAQ only when it
        # explicitly mentions a distinctive detail the FAQ omits.
        terms = set(re.findall(r"[a-z]+", question.casefold())) & index()[-1]
        detail_missing = any(t in passages[0][1]["text"].casefold() and t not in
                             (card["quote"]+" "+card["answers"]["en"]).casefold() for t in terms) if passages else False
        if stronger_source and score < 1 and detail_missing:
            extract = source_excerpt(question, lang, passages)
            if extract:
                return extract
        if confident or separated or confirmed or agreement:
            return render(cards()[i], lang, round(float(similarity), 3), "Question embedding cosine similarity")
    if passages and passages[0][0] >= -1.0:
        return source_excerpt(question, lang, passages)
    return None
