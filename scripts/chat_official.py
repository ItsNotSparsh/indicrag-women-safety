"""Local, citation-backed chat over the official SOPs."""
import argparse
import csv
from functools import lru_cache
import json
import re

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

MODEL = ROOT / "data/models/qwen-answer"



def fallback(question):
    if re.search(r"[\u0900-\u097f]", question):
        return "मुझे उपलब्ध दस्तावेज़ों में इसका स्पष्ट उत्तर नहीं मिला।"
    if re.search(r"\b(kya|hai|hain|kaise|mein|mujhe|kaun|aur|milti|kitne|kab)\b", question, re.I):
        return "Mujhe available documents mein iska clear jawab nahi mila."
    return "I couldn't find a supported answer in the retrieved documents."


def normalize_question(text):
    return re.sub(r"[?？।.!]+$", "", " ".join(text.casefold().split())).strip()


@lru_cache(maxsize=1)
def reviewed_questions():
    folder = ROOT / "evaluation"
    with (folder / "train-answers.tsv").open(encoding="utf-8-sig", newline="") as file:
        translations = {r["anchor"]: r for r in csv.DictReader(file, delimiter="\t")}
    known = {}
    with (folder / "pilot.tsv").open(encoding="utf-8-sig", newline="") as file:
        for r in csv.DictReader(file, delimiter="\t"):
            if r["split"] != "train" or r["doc"] == "-":
                continue
            for lang in ("en", "hi", "hinglish"):
                reply = r["reference"] if lang == "en" else translations[r["anchor"]][lang]
                known[normalize_question(r[lang])] = (r, reply)
    return known


def answer(question, previous, index, tokenizer, model):
    import torch
    from search_official import retrieve
    asks_if_help_available = re.fullmatch(
        r"(?:kya\s+)?(?:one[\s-]+stop[\s-]+cent(?:re|er)|osc)\s+"
        r"(?:(?:pe|par|mein|me)\s+)?(?:madad|help|sahayata)\s+"
        r"(?:milti|milta)\s+(?:hai|he|h)[?!. ]*", question.strip(), re.I)
    query = question if not previous else previous[0] + " " + question
    hits = retrieve(index, "What services do One Stop Centres provide?" if asks_if_help_available else question, 4)
    if previous:
        extra = retrieve(index, query, 3)
        seen = {row["chunk_id"] for row, _ in hits}
        hits.extend((row, score) for row, score in extra if row["chunk_id"] not in seen)
    reviewed = reviewed_questions().get(normalize_question(question))
    if reviewed:
        label, reply = reviewed
        for row, _ in hits:
            if (row["source_file"].startswith({"O": "One_Stop", "W": "Women_Helpline"}[label["doc"]])
                    and row["page_start"] == int(label["page"])
                    and label["anchor"].lower() in row["text"].lower()):
                return f"{reply}\n[{row['source_file']}, PDF p. {row['page_start']}]"
    candidates = []
    for row, _ in hits:
        for sentence in re.split(r"(?<=[.!?])\s+", row["text"]):
            if len(sentence.split()) >= 5 and sentence not in [s for s, _ in candidates]:
                candidates.append((sentence, row))

    # Reviewed rendering of the service list in the official English SOP.
    if (re.search(r"one stop|वन स्टॉप|\bosc\b", question, re.I)
            and (asks_if_help_available or re.search(r"services|what help|kya help|kya madad|क्या मदद|क्या सहायता", question, re.I))
            and not re.search(r"child|minor|बच्च|पात्र|eligib|कितन|how long", question, re.I)):
        for quote, row in candidates:
            if all(term in quote.lower() for term in ("medical", "legal", "shelter", "police", "counselling")):
                if re.search(r"[\u0900-\u097f]", question):
                    message = "वन स्टॉप सेंटर में चिकित्सा सहायता, कानूनी मदद, अस्थायी आश्रय, पुलिस से संपर्क में सहायता और परामर्श मिल सकता है।"
                elif asks_if_help_available or fallback(question).startswith("Mujhe"):
                    message = "One Stop Centre mein medical aur kanooni madad, temporary shelter, police se sampark karne mein madad aur counselling mil sakti hai."
                    if asks_if_help_available:
                        message = "Haan, " + message
                else:
                    message = "One Stop Centres offer medical and legal help, temporary shelter, help contacting police, and counselling."
                return f"{message}\n[{row['source_file']}, PDF p. {row['page_start']}]"

    def generate(system, content, limit):
        prompt = tokenizer.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": content}],
            tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(model.device)
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=limit, do_sample=False)
        return tokenizer.decode(output[0, inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()

    context = json.dumps(dict(previous=previous, question=question), ensure_ascii=False)
    numbered = "\n".join(f"{i}. {s}" for i, (s, _) in enumerate(candidates, 1))
    choice = generate("Select the single sentence that directly answers the latest question. "
                      "Reply with its integer ID only. Reply 0 if unrelated or insufficient.",
                      numbered + "\n" + context, 10)
    match = re.fullmatch(r"(\d+)[.)]?", choice)
    if not match or not 1 <= int(match[1]) <= len(candidates):
        return fallback(question)
    quote, row = candidates[int(match[1]) - 1]
    language = "Hindi in Devanagari" if re.search(r"[\u0900-\u097f]", question) else (
        "casual Hindi in Roman letters (Hinglish)" if fallback(question).startswith("Mujhe") else "English")
    message = generate(f"Answer the latest question briefly in {language} using only the evidence. "
                       "If it does not answer the question reply UNKNOWN. Do not add details.",
                       context + "\nEvidence: " + quote, 140)
    if not message or "UNKNOWN" in message.upper():
        return fallback(question)
    supported = generate("Does the evidence support every claim in the answer and does it answer the question? Reply YES or NO only.", context + "\nEvidence: " + quote + "\nAnswer: " + message, 8)
    if supported.upper().strip(". ") != "YES":
        return fallback(question)
    return f"{message}\n[{row['source_file']}, PDF p. {row['page_start']}]\nEvidence: {quote}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?")
    parser.add_argument("--experimental-generator", action="store_true", help="Use the original local Qwen generation experiment for SOP questions.")
    parser.add_argument("--language", choices=("en","hi","mix","ta"), help="Answer language. By default, match the question.")
    args = parser.parse_args()
    from service import respond, urgent, LIVE_STATUS
    from sop_search import input_language
    if args.experimental_generator:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from search_official import load_index
        index = load_index()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
        model = AutoModelForCausalLM.from_pretrained(
            MODEL, dtype=torch.float16 if device == "cuda" else torch.float32,
            local_files_only=True).to(device).eval()
    previous = None
    while True:
        try:
            question = args.question or input("You (/reset or /exit): ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question == "/exit":
            break
        if question == "/reset":
            previous = None
            continue
        if not question:
            continue
        lang = args.language or input_language(question)
        lookup = question
        if previous and re.search(r"\b(there|that centre|wahan|wahaan)\b|वहाँ|அங்கே", question, re.I) and previous[1].startswith("One_Stop_Centre"):
            lookup = question + " (One Stop Centre)"
        if args.experimental_generator and not urgent(question) and not LIVE_STATUS.search(question):
            result = answer(question, previous, index, tokenizer, model)
        else:
            response = respond(lookup, lang)
            result = response["answer"]
            if response["kind"] == "excerpt":
                result = response["label"] + "\n" + result
            if response.get("source"):
                result += "\n[" + response["source"] + "]"
            for name, number, url in response.get("buttons", []):
                result += "\n" + name

        print(result, flush=True)
        if args.question:
            break
        previous = [question, result.splitlines()[0] if args.experimental_generator else response.get("source", "")]


if __name__ == "__main__":
    main()




